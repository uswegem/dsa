import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.models import CommissionAdjustment, CommissionRun, MatchedTransaction, User
from app.models.enums import MatchStatus, RunStatus, RunType
from app.schemas.commission import AdjustmentCreate, CommissionRunCreate, CommissionRunOut
from app.services.audit import log_action
from app.services.commission import (
    CommissionRunError,
    calculate_commission_run,
    lock_run,
    mark_paid,
    review_run,
)

router = APIRouter(prefix="/api/commission", tags=["commission"])


def _scope_runs_query(db: Session, current_user: User):
    q = db.query(CommissionRun)
    if current_user.branch_id is not None:
        q = q.filter(CommissionRun.branch_id == current_user.branch_id)
    return q


def _check_run_access(run: CommissionRun, current_user: User) -> None:
    if current_user.branch_id is not None and run.branch_id != current_user.branch_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this branch's runs")


@router.post("/runs", response_model=CommissionRunOut)
def create_run(payload: CommissionRunCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("OPERATE_COMMISSION_RUNS"))):
    if current_user.branch_id is not None:
        if payload.run_type != RunType.BRANCH or payload.branch_id != current_user.branch_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Branch-scoped users may only create BRANCH runs for their own branch")
    if payload.run_type == RunType.BRANCH and payload.branch_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "branch_id is required for a BRANCH run")

    existing = (
        db.query(CommissionRun)
        .filter(
            CommissionRun.period == payload.period,
            CommissionRun.branch_id == payload.branch_id,
            CommissionRun.run_type == payload.run_type,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A {payload.run_type.value} run for period {payload.period} already exists (id={existing.id}, status={existing.status.value})",
        )

    run = CommissionRun(
        run_type=payload.run_type,
        branch_id=payload.branch_id,
        period=payload.period,
        status=RunStatus.DRAFT,
        created_by_user_id=current_user.id,
    )
    db.add(run)
    db.flush()
    log_action(db, current_user.id, "RUN_CREATED", "CommissionRun", run.id, period=run.period, run_type=run.run_type.value)
    db.commit()
    db.refresh(run)
    return run


@router.get("/runs", response_model=list[CommissionRunOut])
def list_runs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("OPERATE_COMMISSION_RUNS"))):
    return _scope_runs_query(db, current_user).order_by(CommissionRun.created_at.desc()).all()


@router.get("/runs/{run_id}", response_model=CommissionRunOut)
def get_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("OPERATE_COMMISSION_RUNS"))):
    run = db.get(CommissionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    _check_run_access(run, current_user)
    return run


@router.post("/runs/{run_id}/calculate", response_model=CommissionRunOut)
def calculate_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("OPERATE_COMMISSION_RUNS"))):
    run = db.get(CommissionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    _check_run_access(run, current_user)
    try:
        result = calculate_commission_run(db, run)
    except CommissionRunError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    log_action(
        db, current_user.id, "RUN_CALCULATED", "CommissionRun", run.id,
        lines_created=result.lines_created, skipped_no_dsa=result.skipped_no_dsa,
        skipped_no_dtl=result.skipped_no_dtl, skipped_zero_or_missing_base=result.skipped_zero_or_missing_base,
    )
    db.commit()
    db.refresh(run)
    return run


@router.post("/runs/{run_id}/review", response_model=CommissionRunOut)
def review(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("REVIEW_COMMISSION_RUN"))):
    run = db.get(CommissionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    try:
        review_run(db, run, current_user.id)
    except CommissionRunError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    log_action(db, current_user.id, "RUN_REVIEWED", "CommissionRun", run.id)
    db.commit()
    db.refresh(run)
    return run


@router.post("/runs/{run_id}/lock", response_model=CommissionRunOut)
def lock(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("LOCK_COMMISSION_RUN"))):
    run = db.get(CommissionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")

    open_exceptions = (
        db.query(MatchedTransaction)
        .filter(
            MatchedTransaction.match_status.in_(
                [MatchStatus.UNMATCHED_IN_BUSINESS_FILE, MatchStatus.UNMATCHED_IN_BRANCH_FILE, MatchStatus.DUPLICATE]
            ),
            MatchedTransaction.commission_period == run.period,
        )
        .count()
    )
    # Exceptions never BLOCK a lock (per spec) - they just must have been
    # visible, which the exceptions endpoints/report already guarantee.
    # We still surface the count so the locking admin sees it.

    try:
        lock_run(db, run, current_user.id)
    except CommissionRunError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    log_action(db, current_user.id, "RUN_LOCKED", "CommissionRun", run.id, open_exceptions_at_lock_time=open_exceptions)
    db.commit()
    db.refresh(run)
    return run


@router.post("/runs/{run_id}/mark-paid", response_model=CommissionRunOut)
def mark_run_paid(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MARK_RUN_PAID"))):
    run = db.get(CommissionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    try:
        mark_paid(db, run)
    except CommissionRunError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    log_action(db, current_user.id, "RUN_MARKED_PAID", "CommissionRun", run.id)
    db.commit()
    db.refresh(run)
    return run


@router.post("/adjustments", status_code=status.HTTP_201_CREATED)
def create_adjustment(payload: AdjustmentCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("MANAGE_ADJUSTMENTS"))):
    run = db.get(CommissionRun, payload.commission_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target run not found")
    if run.status in (RunStatus.LOCKED, RunStatus.PAID):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot attach an adjustment to a LOCKED/PAID run - target a later DRAFT/REVIEWED run instead",
        )
    adjustment = CommissionAdjustment(
        commission_run_id=payload.commission_run_id,
        original_commission_line_id=payload.original_commission_line_id,
        payee_type=payload.payee_type,
        dsa_id=payload.dsa_id,
        dtl_id=payload.dtl_id,
        amount=payload.amount,
        reason=payload.reason,
        created_by_user_id=current_user.id,
    )
    db.add(adjustment)
    db.flush()
    log_action(db, current_user.id, "ADJUSTMENT_CREATED", "CommissionAdjustment", adjustment.id, amount=payload.amount)
    db.commit()
    return {"id": adjustment.id}
