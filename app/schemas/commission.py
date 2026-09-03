import datetime as dt

from pydantic import BaseModel

from app.models.enums import RunStatus, RunType


class CommissionRunCreate(BaseModel):
    run_type: RunType
    branch_id: int | None = None
    period: str  # 'YYYY-MM'


class CommissionRunOut(BaseModel):
    id: int
    run_type: RunType
    branch_id: int | None
    period: str
    status: RunStatus
    created_at: dt.datetime
    reviewed_at: dt.datetime | None
    locked_at: dt.datetime | None
    paid_at: dt.datetime | None

    model_config = {"from_attributes": True}


class AdjustmentCreate(BaseModel):
    commission_run_id: int
    original_commission_line_id: int | None = None
    payee_type: str
    dsa_id: int | None = None
    dtl_id: int | None = None
    amount: float
    reason: str


class ExceptionRow(BaseModel):
    match_status: str
    branch_name: str | None
    client_name: str | None
    client_account_no_branch: str | None
    client_account_no_business: str | None
    dsa_code: str | None
    dsa_name: str | None
    loan_type: str | None
    disbursement_date: str | None
    notes: str | None
