import datetime as dt

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. 'UPLOAD_CREATED', 'RUN_LOCKED'
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
