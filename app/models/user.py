import datetime as dt

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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

    # What this user can DO - see app/models/rbac.py. Replaces the old
    # fixed UserRole enum column.
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)

    # Which branch's data this user can act on. Not tied to role identity -
    # a role's permissions decide what; branch_id decides where. NULL means
    # org-wide (no single-branch restriction).
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    branch: Mapped[Branch | None] = relationship(back_populates="users")
    role: Mapped["Role"] = relationship(back_populates="users")


from app.models.dsa import Dsa  # noqa: E402  (avoid circular import at module load)
from app.models.rbac import Role  # noqa: E402  (avoid circular import at module load)
