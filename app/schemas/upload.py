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
    original_filename: str
    status: UploadStatus
    total_rows: int
    valid_rows: int
    error_rows: int
    warning_rows: int
    failure_reason: str | None
    uploaded_at: dt.datetime
    processed_at: dt.datetime | None

    model_config = {"from_attributes": True}


class UploadDetailOut(UploadOut):
    errors: list[UploadErrorOut] = []
