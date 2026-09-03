import datetime as dt

from pydantic import BaseModel

from app.models.enums import UploadStatus, UploadType


class UploadErrorOut(BaseModel):
    row_number: int
    severity: str
    column_name: str | None
    message: str

    model_config = {"from_attributes": True}


class UploadOut(BaseModel):
    id: int
    upload_type: UploadType
    branch_id: int | None
    period_month: int | None
    period_year: int | None
    original_filename: str
    status: UploadStatus
    total_rows: int
    rows_accepted: int
    rows_rejected: int
    warning_rows: int
    failure_reason: str | None
    uploaded_at: dt.datetime
    processed_at: dt.datetime | None

    model_config = {"from_attributes": True}


class UploadDetailOut(UploadOut):
    errors: list[UploadErrorOut] = []


class UploadSubmitResult(UploadDetailOut):
    """Returned right after a submission - adds the created/updated
    breakdown (not persisted columns; computed for this response only) so
    the uploader can see at a glance how much of this upload was new data
    vs corrections to rows from an earlier upload for the same period."""

    rows_created: int = 0
    rows_updated: int = 0
    rows_unchanged: int = 0
