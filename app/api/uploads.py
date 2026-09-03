from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_business_manager, require_branch_manager, require_any
from app.models import Branch, BranchSale, BusinessTransaction, Upload, UploadError, User
from app.models.enums import UploadStatus, UploadType, UserRole
from app.schemas.upload import UploadDetailOut, UploadOut
from app.services.audit import log_action
from app.services.ingest_branch_manager import parse_branch_manager_file
from app.services.ingest_business_manager import parse_business_manager_file
from app.services.matching import run_matching
from app.services.roster_sync import sync_roster_from_branch_sales
from app.services.storage import save_upload_file

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def _scope_uploads_query(db: Session, current_user: User):
    q = db.query(Upload)
    if current_user.role == UserRole.BRANCH_MANAGER:
        q = q.filter(Upload.branch_id == current_user.branch_id)
    return q


@router.post("/branch-manager", response_model=UploadDetailOut)
async def upload_branch_manager_file(
    file: UploadFile = File(...),
    branch_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_branch_manager),
):
    if current_user.role == UserRole.BRANCH_MANAGER:
        target_branch_id = current_user.branch_id
    else:  # ADMIN
        if branch_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "branch_id is required for admin uploads")
        target_branch_id = branch_id

    branch = db.get(Branch, target_branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")

    contents = await file.read()
    storage_path = save_upload_file(contents, file.filename, "branch_manager")

    upload = Upload(
        upload_type=UploadType.BRANCH_MANAGER,
        uploaded_by_user_id=current_user.id,
        branch_id=target_branch_id,
        original_filename=file.filename,
        storage_path=storage_path,
        status=UploadStatus.PROCESSING,
    )
    db.add(upload)
    db.flush()
    log_action(db, current_user.id, "UPLOAD_CREATED", "Upload", upload.id, upload_type="BRANCH_MANAGER", branch_id=target_branch_id)

    try:
        parsed = parse_branch_manager_file(storage_path)
    except ValueError as e:
        upload.status = UploadStatus.FAILED
        upload.failure_reason = str(e)
        db.commit()
        db.refresh(upload)
        return upload

    saved_rows: list[BranchSale] = []
    for row in parsed.rows:
        bs = BranchSale(
            upload_id=upload.id,
            branch_id=target_branch_id,
            row_number=row.row_number,
            loan_date=row.loan_date,
            client_name=row.client_name,
            client_check_no=row.client_check_no,
            client_account_no=row.client_account_no,
            application_number_ess=row.application_number_ess,
            reported_amount=row.reported_amount,
            branch_name_raw=row.branch_raw,
            dsa_code=row.dsa_code,
            dsa_account_no=row.dsa_account_no,
            dsa_name=row.dsa_name,
            dtl_name=row.dtl_name,
            dtl_code=row.dtl_code,
            date_out_of_period_warning=row.date_out_of_period_warning,
        )
        db.add(bs)
        saved_rows.append(bs)
    db.flush()

    for issue in parsed.issues:
        db.add(
            UploadError(
                upload_id=upload.id,
                row_number=issue.row_number,
                severity=issue.severity,
                column_name=issue.column_name,
                message=issue.message,
            )
        )

    sync_roster_from_branch_sales(db, saved_rows, upload.uploaded_at.date() if upload.uploaded_at else __import__("datetime").date.today())

    upload.total_rows = parsed.total_data_rows_seen
    upload.valid_rows = len(saved_rows)
    upload.error_rows = sum(1 for i in parsed.issues if i.severity == "ERROR")
    upload.warning_rows = sum(1 for i in parsed.issues if i.severity == "WARNING")
    upload.status = UploadStatus.PROCESSED
    import datetime as _dt

    upload.processed_at = _dt.datetime.now(_dt.timezone.utc)

    run_matching(db, branch_upload_id=upload.id, business_upload_id=None)

    db.commit()
    db.refresh(upload)
    return upload


@router.post("/business-manager", response_model=UploadDetailOut)
async def upload_business_manager_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_manager),
):
    contents = await file.read()
    storage_path = save_upload_file(contents, file.filename, "business_manager")

    upload = Upload(
        upload_type=UploadType.BUSINESS_MANAGER,
        uploaded_by_user_id=current_user.id,
        branch_id=None,
        original_filename=file.filename,
        storage_path=storage_path,
        status=UploadStatus.PROCESSING,
    )
    db.add(upload)
    db.flush()
    log_action(db, current_user.id, "UPLOAD_CREATED", "Upload", upload.id, upload_type="BUSINESS_MANAGER")

    try:
        parsed = parse_business_manager_file(storage_path)
    except ValueError as e:
        upload.status = UploadStatus.FAILED
        upload.failure_reason = str(e)
        db.commit()
        db.refresh(upload)
        return upload

    for row in parsed.rows:
        db.add(
            BusinessTransaction(
                upload_id=upload.id,
                row_number=row.row_number,
                branch_name_raw=row.branch_raw,
                employee_no=row.employee_no,
                customer_no=row.customer_no,
                account_no=row.account_no,
                loan_type=row.loan_type,
                disbursement_date=row.disbursement_date,
                disbursement_amt=row.disbursement_amt,
                payout_to_client=row.payout_to_client,
                letshego_topup=row.letshego_topup,
                appl_amount=row.appl_amount,
                client_disb_ext_account_no=row.client_disb_ext_account_no,
            )
        )
    db.flush()

    for issue in parsed.issues:
        db.add(
            UploadError(
                upload_id=upload.id,
                row_number=issue.row_number,
                severity=issue.severity,
                column_name=issue.column_name,
                message=issue.message,
            )
        )

    upload.total_rows = parsed.total_data_rows_seen
    upload.valid_rows = len(parsed.rows)
    upload.error_rows = sum(1 for i in parsed.issues if i.severity == "ERROR")
    upload.warning_rows = sum(1 for i in parsed.issues if i.severity == "WARNING")
    upload.status = UploadStatus.PROCESSED
    import datetime as _dt

    upload.processed_at = _dt.datetime.now(_dt.timezone.utc)

    run_matching(db, branch_upload_id=None, business_upload_id=upload.id)

    db.commit()
    db.refresh(upload)
    return upload


@router.get("", response_model=list[UploadOut])
def list_uploads(db: Session = Depends(get_db), current_user: User = Depends(require_any)):
    return _scope_uploads_query(db, current_user).order_by(Upload.uploaded_at.desc()).all()


@router.get("/{upload_id}", response_model=UploadDetailOut)
def get_upload(upload_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_any)):
    upload = _scope_uploads_query(db, current_user).filter(Upload.id == upload_id).first()
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return upload
