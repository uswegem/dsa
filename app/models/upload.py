import datetime as dt

from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum as SAEnum, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import UploadType, UploadStatus


class Upload(Base):
    """Full audit trail of every file uploaded, whatever happened to it."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_type: Mapped[UploadType] = mapped_column(SAEnum(UploadType, name="upload_type"), nullable=False)
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Set for BRANCH_MANAGER uploads (a branch manager only uploads their own
    # branch's roster). NULL for BUSINESS_MANAGER uploads (org-wide file).
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    status: Mapped[UploadStatus] = mapped_column(
        SAEnum(UploadStatus, name="upload_status"), nullable=False, default=UploadStatus.PENDING
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    warning_rows: Mapped[int] = mapped_column(Integer, default=0)

    failure_reason: Mapped[str | None] = mapped_column(Text)

    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    errors: Mapped[list["UploadError"]] = relationship(back_populates="upload", cascade="all, delete-orphan")


class UploadError(Base):
    """One row that failed validation (or produced a warning) during ingestion."""

    __tablename__ = "upload_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based, as seen in the source file
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR")  # ERROR | WARNING
    column_name: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_row_json: Mapped[str | None] = mapped_column(Text)

    upload: Mapped[Upload] = relationship(back_populates="errors")
