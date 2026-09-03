"""
Role-based access control.

roles / permissions / role_permissions replace the old fixed UserRole enum
column on users. A role's permissions determine what a user can DO; their
assigned branch (users.branch_id - unchanged) still determines which
branch's data they can do it to. A user has no branch (org-wide) or
exactly one branch.

The three roles seeded by the migration that introduced this (ADMIN,
BRANCH_MANAGER, BUSINESS_MANAGER) are marked is_system_role=True: their
permissions can be edited, but the role itself can't be deleted, so the
app's baseline assumptions (e.g. "some role can always manage roles") can't
be broken by accident. See app/services/permissions.py for the guard that
prevents removing the last account's MANAGE_ROLES access.
"""
import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Table, Column, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, back_populates="roles")
    users: Mapped[list["User"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    roles: Mapped[list["Role"]] = relationship(secondary=role_permissions, back_populates="permissions")
