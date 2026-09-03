import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_any_permission, require_permission
from app.models import Branch, BranchSale, Upload, UploadError, User
from app.models.enums import UploadStatus, UploadType
from app.schemas.upload import UploadDetailOut, UploadOut, UploadSubmitResult
from app.services.audit import log_action
from app.services.ingest_branch_manager import parse_branch_manager_file
from app.services.ingest_business_manager import parse_business_manager_file
from app.services.matching import run_matching
from app.services.permissions import user_has_permission
from app.services.roster_sync import sync_roster_from_branch_sales
from app.services.storage import save_upload_file
from app.services.upsert import upsert_branch_sale, upsert_business_transaction

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

MIN_PERIOD_YEAR = 2000
MAX_PERIOD_YEAR = 2100


def _validate_period(period_month: int, period_year: int) -> None:
    if not (1 <= period_month <= 12):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "period_month must be between 1 and 12")
    if not (MIN_PERIOD_YEAR <= period_year <= MAX_PERIOD_YEAR):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"period_year must be between {MIN_PERIOD_YEAR} and {MAX_PERIOD_YEAR}")


def _scope_uploads_query(db: Session, current_user: User):
    q = db.query(Upload)
    if not user_has_permission(current_user, "VIEW_ALL_UPLOADS"):
        q = q.filter(Upload.branch_id == current_user.branch_id)
    return q


def _resolve_branch_by_name(db: Session, name: str) -> Branch | None:
    return db.query(Branch).filter(func.lower(Branch.name) == name.strip().lower()).first()


@router.post("/branch-manager", response_model=UploadSubmitResult)
async def upload_branch_manager_file(
    file: UploadFile = File(...),
    period_month: int = Form(...),
    period_year: int = Form(...),
    branch_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("UPLOAD_BRANCH_FILE")),
):
    """Roster/attribution upload. Accepts a single-sheet file (one branch)
    or a multi-sheet workbook (one sheet per branch, sheet name = branch
    name) for bulk/migration loads. Every row is upserted on
    (client_account_no, period_month, period_year) - a re-upload for a
    period already in progress updates existing rows rather than
    duplicating them. Rows whose DATE falls outside period_month/period_year
    (or is missing/unparseable) are rejected, not silently accepted.

    Branch scoping: a user with a branch_id assigned (e.g. a Branch
    Manager) is always restricted to their own branch, regardless of what
    the form/sheets say. A user with no branch_id (org-wide, e.g. Admin)
    may target any branch - explicitly via branch_id, or via matching
    sheet names for a multi-sheet bulk/migration upload.
    """
    _validate_period(period_month, period_year)
    is_branch_scoped = current_user.branch_id is not None

    contents = await file.read()
    storage_path = save_upload_file(contents, file.filename, "branch_manager")

    upload = Upload(
        upload_type=UploadType.BRANCH_MANAGER,
        uploaded_by_user_id=current_user.id,
        branch_id=current_user.branch_id if is_branch_scoped else branch_id,
        period_month=period_month,
        period_year=period_year,
        original_filename=file.filename,
        storage_path=storage_path,
        status=UploadStatus.PROCESSING,
    )
    db.add(upload)
    db.flush()
    log_action(
        db, current_user.id, "UPLOAD_CREATED", "Upload", upload.id,
        upload_type="BRANCH_MANAGER", period=f"{period_year}-{period_month:02d}",
    )

    try:
        parsed = parse_branch_manager_file(storage_path, period_month, period_year)
    except ValueError as e:
        upload.status = UploadStatus.FAILED
        upload.failure_reason = str(e)
        db.commit()
        db.refresh(upload)
        return UploadSubmitResult.model_validate(upload)

    # group parsed rows by their source sheet, then resolve one branch per sheet
    rows_by_sheet: dict[str, list] = {}
    for row in parsed.rows:
        rows_by_sheet.setdefault(row.sheet_name, []).append(row)

    sheet_names = list(rows_by_sheet.keys())
    is_multi_sheet = len(sheet_names) > 1
    sheet_level_rejected_rows = 0  # rows excluded because their sheet's branch couldn't be used/resolved

    if is_branch_scoped:
        own_branch = db.get(Branch, current_user.branch_id)
        for sheet_name in sheet_names:
            if is_multi_sheet and (own_branch is None or sheet_name.strip().lower() != own_branch.name.strip().lower()):
                skipped_rows = rows_by_sheet.pop(sheet_name)
                sheet_level_rejected_rows += len(skipped_rows)
                db.add(UploadError(
                    upload_id=upload.id, row_number=0, severity="ERROR", column_name=None,
                    message=f"Sheet '{sheet_name}' ({len(skipped_rows)} rows) skipped - you can only upload data for your own branch.",
                ))
        sheet_branch: dict[str, Branch] = {s: own_branch for s in rows_by_sheet}
    else:  # org-wide user (e.g. Admin)
        sheet_branch = {}
        if not is_multi_sheet:
            sole_sheet = sheet_names[0] if sheet_names else None
            resolved = None
            if branch_id is not None:
                resolved = db.get(Branch, branch_id)
            elif sole_sheet is not None:
                resolved = _resolve_branch_by_name(db, sole_sheet)
            if resolved is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Could not determine the target branch - pass branch_id, or name the sheet after an existing branch.",
                )
            if sole_sheet is not None:
                sheet_branch[sole_sheet] = resolved
        else:
            for sheet_name in sheet_names:
                resolved = _resolve_branch_by_name(db, sheet_name)
                if resolved is None:
                    skipped_rows = rows_by_sheet.pop(sheet_name)
                    sheet_level_rejected_rows += len(skipped_rows)
                    db.add(UploadError(
                        upload_id=upload.id, row_number=0, severity="ERROR", column_name=None,
                        message=f"Sheet '{sheet_name}' ({len(skipped_rows)} rows) skipped - no branch named '{sheet_name}' exists.",
                    ))
                else:
                    sheet_branch[sheet_name] = resolved

    created = updated = unchanged = 0
    touched_rows: list[BranchSale] = []
    for sheet_name, rows in rows_by_sheet.items():
        branch = sheet_branch[sheet_name]
        for parsed_row in rows:
            saved_row, outcome = upsert_branch_sale(
                db, upload.id, branch.id, period_month, period_year, parsed_row, current_user.id
            )
            touched_rows.append(saved_row)
            if outcome.created:
                created += 1
            elif outcome.changed:
                updated += 1
            else:
                unchanged += 1
    db.flush()

    for issue in parsed.issues:
        db.add(UploadError(
            upload_id=upload.id, row_number=issue.row_number, severity=issue.severity,
            column_name=issue.column_name, message=f"[{issue.sheet_name}] {issue.message}" if issue.sheet_name else issue.message,
        ))

    sync_roster_from_branch_sales(db, touched_rows, upload.uploaded_at.date() if upload.uploaded_at else dt.date.today())

    upload.total_rows = parsed.total_data_rows_seen
    upload.rows_accepted = created + updated + unchanged
    upload.rows_rejected = sum(1 for i in parsed.issues if i.severity == "ERROR") + sheet_level_rejected_rows
    upload.warning_rows = sum(1 for i in parsed.issues if i.severity == "WARNING")
    upload.status = UploadStatus.PROCESSED
    upload.processed_at = dt.datetime.now(dt.timezone.utc)

    run_matching(db, branch_upload_id=upload.id, business_upload_id=None)

    db.commit()
    db.refresh(upload)
    result = UploadSubmitResult.model_validate(upload)
    result.rows_created = created
    result.rows_updated = updated
    result.rows_unchanged = unchanged
    return result


@router.post("/business-manager", response_model=UploadSubmitResult)
async def upload_business_manager_file(
    file: UploadFile = File(...),
    period_month: int = Form(...),
    period_year: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("UPLOAD_BUSINESS_FILE")),
):
    """Org-wide payout report upload. Every row is upserted on
    (client_disb_ext_account_no, loan_type, disbursement_date) - a
    re-upload for a period already in progress updates existing rows.
    Rows whose Disbursement date falls outside period_month/period_year
    (or is missing/unparseable) are rejected, not silently accepted.
    """
    _validate_period(period_month, period_year)

    contents = await file.read()
    storage_path = save_upload_file(contents, file.filename, "business_manager")

    upload = Upload(
        upload_type=UploadType.BUSINESS_MANAGER,
        uploaded_by_user_id=current_user.id,
        branch_id=None,
        period_month=period_month,
        period_year=period_year,
        original_filename=file.filename,
        storage_path=storage_path,
        status=UploadStatus.PROCESSING,
    )
    db.add(upload)
    db.flush()
    log_action(
        db, current_user.id, "UPLOAD_CREATED", "Upload", upload.id,
        upload_type="BUSINESS_MANAGER", period=f"{period_year}-{period_month:02d}",
    )

    try:
        parsed = parse_business_manager_file(storage_path, period_month, period_year)
    except ValueError as e:
        upload.status = UploadStatus.FAILED
        upload.failure_reason = str(e)
        db.commit()
        db.refresh(upload)
        return UploadSubmitResult.model_validate(upload)

    created = updated = unchanged = 0
    for parsed_row in parsed.rows:
        _saved_row, outcome = upsert_business_transaction(db, upload.id, parsed_row, current_user.id)
        if outcome.created:
            created += 1
        elif outcome.changed:
            updated += 1
        else:
            unchanged += 1
    db.flush()

    for issue in parsed.issues:
        db.add(UploadError(
            upload_id=upload.id, row_number=issue.row_number, severity=issue.severity,
            column_name=issue.column_name, message=issue.message,
        ))

    upload.total_rows = parsed.total_data_rows_seen
    upload.rows_accepted = created + updated + unchanged
    upload.rows_rejected = sum(1 for i in parsed.issues if i.severity == "ERROR")
    upload.warning_rows = sum(1 for i in parsed.issues if i.severity == "WARNING")
    upload.status = UploadStatus.PROCESSED
    upload.processed_at = dt.datetime.now(dt.timezone.utc)

    run_matching(db, branch_upload_id=None, business_upload_id=upload.id)

    db.commit()
    db.refresh(upload)
    result = UploadSubmitResult.model_validate(upload)
    result.rows_created = created
    result.rows_updated = updated
    result.rows_unchanged = unchanged
    return result


@router.get("", response_model=list[UploadOut])
def list_uploads(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("VIEW_ALL_UPLOADS", "VIEW_OWN_BRANCH_UPLOADS")),
):
    return _scope_uploads_query(db, current_user).order_by(Upload.uploaded_at.desc()).all()


@router.get("/{upload_id}", response_model=UploadDetailOut)
def get_upload(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("VIEW_ALL_UPLOADS", "VIEW_OWN_BRANCH_UPLOADS")),
):
    upload = _scope_uploads_query(db, current_user).filter(Upload.id == upload_id).first()
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return upload
