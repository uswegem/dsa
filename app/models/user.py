import datetime as dt

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import UserRole


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="branch")
    dsas: Mapped[list["Dsa"]] = relationship(back_populates="branch")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), nullable=False)

    # Only meaningful (and required) for BRANCH_MANAGER users - scopes them
    # to a single branch. NULL for BUSINESS_MANAGER / ADMIN.
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    branch: Mapped[Branch | None] = relationship(back_populates="users")


from app.models.dsa import Dsa  # noqa: E402  (avoid circular import at module load)
