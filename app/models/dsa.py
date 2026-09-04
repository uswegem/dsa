import datetime as dt

from sqlalchemy import String, Date, ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Dsa(Base):
    """A Direct Sales Agent. Keyed by dsa_code - there is no DSA employee
    number in the real data, dsa_code is the only stable identifier."""

    __tablename__ = "dsas"

    id: Mapped[int] = mapped_column(primary_key=True)
    dsa_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    dsa_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dsa_account_no: Mapped[str | None] = mapped_column(String(100))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    branch = relationship("Branch", back_populates="dsas")
    assignments: Mapped[list["DsaDtlAssignment"]] = relationship(back_populates="dsa")


class Dtl(Base):
    """A Team Leader supervising a group of DSAs."""

    __tablename__ = "dtls"

    id: Mapped[int] = mapped_column(primary_key=True)
    dtl_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    dtl_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # The DTL's account for commission payment, shown on the DTL Summary
    # report. Not in any upload format - captured/edited via Admin > DTLs.
    # NULL until backfilled for existing records.
    dtl_account_no: Mapped[str | None] = mapped_column(String(30))

    # Not in the original Branch Manager file schema (a DTL's branch is
    # otherwise only implied through the DSAs currently assigned to them).
    # Added on request to record it directly, e.g. from an org chart /
    # roster reference list that isn't itself an upload.
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    branch = relationship("Branch")

    assignments: Mapped[list["DsaDtlAssignment"]] = relationship(back_populates="dtl")


class DsaDtlAssignment(Base):
    """Effective-dated DSA -> DTL supervision mapping.

    A DSA reassigned to a different DTL mid-month must not corrupt prior
    months' commission history: each row is valid for
    [effective_from, effective_to) - effective_to NULL means "still current".
    Commission calculation picks the assignment whose range covers the
    transaction's commission period, never just "the current one".
    """

    __tablename__ = "dsa_dtl_assignments"
    __table_args__ = (
        UniqueConstraint("dsa_id", "effective_from", name="uq_dsa_assignment_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dsa_id: Mapped[int] = mapped_column(ForeignKey("dsas.id"), nullable=False)
    dtl_id: Mapped[int] = mapped_column(ForeignKey("dtls.id"), nullable=False)
    effective_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dsa: Mapped[Dsa] = relationship(back_populates="assignments")
    dtl: Mapped[Dtl] = relationship(back_populates="assignments")
