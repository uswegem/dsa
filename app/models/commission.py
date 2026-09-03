import datetime as dt

from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, Enum as SAEnum, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import RunType, RunStatus, PayeeType, LoanType, CommissionBase


class CommissionRun(Base):
    """A commission calculation run for one period, scoped to a branch or
    org-wide. State machine: DRAFT -> REVIEWED -> LOCKED -> PAID.

    A LOCKED run's commission_lines are never mutated. Corrections are new
    commission_adjustments rows absorbed by a later run.
    """

    __tablename__ = "commission_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[RunType] = mapped_column(SAEnum(RunType, name="run_type"), nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))  # NULL for ORG_WIDE
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # 'YYYY-MM'
    status: Mapped[RunStatus] = mapped_column(SAEnum(RunStatus, name="run_status"), nullable=False, default=RunStatus.DRAFT)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    locked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    locked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["CommissionLine"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    adjustments: Mapped[list["CommissionAdjustment"]] = relationship(
        back_populates="run", foreign_keys="CommissionAdjustment.commission_run_id"
    )


class CommissionLine(Base):
    """One DSA-or-DTL payout for one matched transaction, within one run."""

    __tablename__ = "commission_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    commission_run_id: Mapped[int] = mapped_column(ForeignKey("commission_runs.id"), nullable=False)
    matched_transaction_id: Mapped[int] = mapped_column(ForeignKey("matched_transactions.id"), nullable=False)

    payee_type: Mapped[PayeeType] = mapped_column(SAEnum(PayeeType, name="payee_type"), nullable=False)
    dsa_id: Mapped[int | None] = mapped_column(ForeignKey("dsas.id"))
    dtl_id: Mapped[int | None] = mapped_column(ForeignKey("dtls.id"))

    loan_type: Mapped[LoanType] = mapped_column(SAEnum(LoanType, name="commission_line_loan_type"), nullable=False)
    base_used: Mapped[CommissionBase] = mapped_column(SAEnum(CommissionBase, name="commission_base"), nullable=False)
    base_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    commission_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[CommissionRun] = relationship(back_populates="lines")
    matched_transaction = relationship("MatchedTransaction")
    dsa = relationship("Dsa")
    dtl = relationship("Dtl")


class CommissionAdjustment(Base):
    """A reversal / clawback / correction. Applied as a new entry against a
    later (non-locked) run rather than mutating a locked run's numbers.
    """

    __tablename__ = "commission_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)

    # The run this adjustment is absorbed into (must not be LOCKED/PAID at
    # the time it's created).
    commission_run_id: Mapped[int] = mapped_column(ForeignKey("commission_runs.id"), nullable=False)

    # The original locked line being corrected, if applicable.
    original_commission_line_id: Mapped[int | None] = mapped_column(ForeignKey("commission_lines.id"))

    payee_type: Mapped[PayeeType] = mapped_column(SAEnum(PayeeType, name="adjustment_payee_type"), nullable=False)
    dsa_id: Mapped[int | None] = mapped_column(ForeignKey("dsas.id"))
    dtl_id: Mapped[int | None] = mapped_column(ForeignKey("dtls.id"))

    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)  # signed: negative = clawback
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[CommissionRun] = relationship(back_populates="adjustments", foreign_keys=[commission_run_id])
