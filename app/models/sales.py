import datetime as dt

from sqlalchemy import String, Integer, Date, DateTime, Numeric, ForeignKey, Enum as SAEnum, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import MatchStatus, LoanType


class BranchSale(Base):
    """One raw parsed row from a Branch Manager (roster/attribution) upload.

    This is the ONLY source of DSA/DTL identity in the system.
    """

    __tablename__ = "branch_sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    loan_date: Mapped[dt.date | None] = mapped_column(Date)  # DATE column - informational only, never used for bucketing
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_check_no: Mapped[str] = mapped_column(String(100), nullable=False)  # always text: mixes numeric/alphanumeric
    client_account_no: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # primary join key
    application_number_ess: Mapped[str | None] = mapped_column(String(255))  # reference only, never matched on

    reported_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))  # reconciliation only, never a commission base

    branch_name_raw: Mapped[str | None] = mapped_column(String(255))  # BRANCH column as typed in the file
    dsa_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dsa_account_no: Mapped[str | None] = mapped_column(String(100))
    dsa_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dtl_name: Mapped[str | None] = mapped_column(String(255))
    dtl_code: Mapped[str | None] = mapped_column(String(100))

    date_out_of_period_warning: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    matches: Mapped[list["MatchedTransaction"]] = relationship(back_populates="branch_sale")
    branch = relationship("Branch")


class BusinessTransaction(Base):
    """One raw parsed row from a Business Manager ("Payout Report by Branch") upload.

    Source of loan type and financial amounts. No reliable DSA/DTL
    attribution - CONSULTANT / CIF_REL_MANAGER are deliberately not stored
    for attribution purposes.
    """

    __tablename__ = "business_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    branch_name_raw: Mapped[str | None] = mapped_column(String(255))
    employee_no: Mapped[str | None] = mapped_column(String(100), index=True)  # secondary cross-check field
    customer_no: Mapped[str | None] = mapped_column(String(100))
    account_no: Mapped[str | None] = mapped_column(String(100))

    loan_type: Mapped[LoanType] = mapped_column(SAEnum(LoanType, name="loan_type"), nullable=False)

    disbursement_date: Mapped[dt.date] = mapped_column(Date, nullable=False)  # THE field used for period bucketing
    disbursement_amt: Mapped[float | None] = mapped_column(Numeric(18, 2))  # gross base for NL
    payout_to_client: Mapped[float | None] = mapped_column(Numeric(18, 2))  # current net basis for RF - see Settings.net_topup_basis_field
    letshego_topup: Mapped[float | None] = mapped_column(Numeric(18, 2))
    appl_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))

    client_disb_ext_account_no: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # primary join key

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    matches: Mapped[list["MatchedTransaction"]] = relationship(back_populates="business_transaction")


class MatchedTransaction(Base):
    """Resolved join result between a BranchSale and a BusinessTransaction,
    with match-quality classification. Only MATCHED and MATCHED_WITH_WARNING
    rows are eligible for commission calculation.
    """

    __tablename__ = "matched_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    branch_sale_id: Mapped[int | None] = mapped_column(ForeignKey("branch_sales.id"))
    business_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("business_transactions.id"))

    match_status: Mapped[MatchStatus] = mapped_column(SAEnum(MatchStatus, name="match_status"), nullable=False)
    match_notes: Mapped[str | None] = mapped_column(Text)

    # Commission period this transaction belongs to, derived from the
    # Business Manager file's Disbursement date - NULL when there is no
    # business transaction to derive it from (UNMATCHED_IN_BUSINESS_FILE).
    commission_period: Mapped[str | None] = mapped_column(String(7), index=True)  # 'YYYY-MM'

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    branch_sale: Mapped[BranchSale | None] = relationship(back_populates="matches")
    business_transaction: Mapped[BusinessTransaction | None] = relationship(back_populates="matches")
