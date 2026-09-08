import datetime as dt

from app.models import (
    Branch,
    BranchSale,
    BusinessTransaction,
    CommissionLine,
    CommissionRun,
    Dsa,
    Dtl,
    MatchedTransaction,
    Role,
    Upload,
    User,
)
from app.models.enums import LoanType, MatchStatus, RunStatus, RunType, UploadStatus, UploadType
from app.reports.excel import aggregate_dsa_summary, aggregate_dtl_summary
from app.services.commission import calculate_commission_run, get_topup_net_base
from app.services.exceptions import INVALID_TOPUP_BASE, find_exceptions
from app.services.matching import run_matching


def _seed_base(db):
    branch = Branch(name="Arusha", code="ARU")
    db.add(branch)
    db.flush()

    dsa = Dsa(dsa_code="DSA01", dsa_name="Amos", dsa_account_no="AC-DSA01", branch_id=branch.id)
    dtl = Dtl(dtl_code="DTL01", dtl_name="Grace T", dtl_account_no="AC-DTL01")
    db.add_all([dsa, dtl])

    admin_role = db.query(Role).filter(Role.name == "ADMIN").one()
    admin = User(email="admin@test.local", hashed_password="x", full_name="Admin", role_id=admin_role.id)
    db.add(admin)
    db.flush()

    branch_upload = Upload(
        upload_type=UploadType.BRANCH_MANAGER, uploaded_by_user_id=admin.id, branch_id=branch.id,
        period_month=8, period_year=2026, original_filename="branch.xlsx", storage_path="x", status=UploadStatus.PROCESSED,
    )
    biz_upload = Upload(
        upload_type=UploadType.BUSINESS_MANAGER, uploaded_by_user_id=admin.id, branch_id=None,
        period_month=8, period_year=2026, original_filename="biz.xlsx", storage_path="x", status=UploadStatus.PROCESSED,
    )
    db.add_all([branch_upload, biz_upload])
    db.flush()
    return branch, dsa, dtl, admin, branch_upload, biz_upload


# ---------------------------------------------------------------------
# get_topup_net_base formula
# ---------------------------------------------------------------------

def test_topup_net_base_is_appl_amount_minus_letshego_topup():
    bt = BusinessTransaction(
        upload_id=1, row_number=1, loan_type=LoanType.RF, disbursement_date=dt.date(2026, 8, 1),
        appl_amount=250_000, letshego_topup=50_000, payout_to_client=999_999,  # payout_to_client must NOT be used anymore
        client_disb_ext_account_no="ACC1",
    )
    assert get_topup_net_base(bt) == 200_000.0


def test_topup_net_base_none_if_a_component_is_missing():
    bt = BusinessTransaction(
        upload_id=1, row_number=1, loan_type=LoanType.RF, disbursement_date=dt.date(2026, 8, 1),
        appl_amount=250_000, letshego_topup=None,
        client_disb_ext_account_no="ACC1",
    )
    assert get_topup_net_base(bt) is None


# ---------------------------------------------------------------------
# Negative/zero net base: excluded from commission, surfaced as an exception
# ---------------------------------------------------------------------

def test_invalid_topup_base_excluded_from_commission_and_flagged_as_exception(db_session):
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)

    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=2, period_month=8, period_year=2026,
        loan_date=dt.date(2026, 8, 5), client_name="Client A", client_check_no="871", client_account_no="ACC001",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    # Letshego Topup >= Appl Amount -> net base <= 0, a data problem upstream
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=2, branch_name_raw="Arusha", employee_no="871",
        loan_type=LoanType.RF, disbursement_date=dt.date(2026, 8, 5),
        appl_amount=200_000, letshego_topup=250_000,
        client_disb_ext_account_no="ACC001",
    ))
    db.flush()
    run_matching(db, branch_upload_id=branch_upload.id, business_upload_id=biz_upload.id)

    mt = db.query(MatchedTransaction).one()
    assert mt.match_status == MatchStatus.MATCHED  # matching itself is unaffected - the accounts DID match

    run = CommissionRun(run_type=RunType.ORG_WIDE, branch_id=None, period="2026-08", status=RunStatus.DRAFT, created_by_user_id=admin.id)
    db.add(run)
    db.flush()
    result = calculate_commission_run(db, run)

    assert result.lines_created == 0  # no DSA or DTL line for this transaction
    assert result.skipped_zero_or_missing_base == 1
    assert db.query(CommissionLine).filter(CommissionLine.commission_run_id == run.id).count() == 0

    exceptions = find_exceptions(db)
    assert len(exceptions) == 1
    assert exceptions[0].category == INVALID_TOPUP_BASE
    assert exceptions[0].matched_transaction.id == mt.id
    assert "Appl Amount" in exceptions[0].note and "Letshego Topup" in exceptions[0].note


def test_valid_topup_base_is_not_flagged_as_an_exception(db_session):
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)

    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=2, period_month=8, period_year=2026,
        loan_date=dt.date(2026, 8, 5), client_name="Client A", client_check_no="871", client_account_no="ACC001",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=2, branch_name_raw="Arusha", employee_no="871",
        loan_type=LoanType.RF, disbursement_date=dt.date(2026, 8, 5),
        appl_amount=250_000, letshego_topup=50_000,
        client_disb_ext_account_no="ACC001",
    ))
    db.flush()
    run_matching(db, branch_upload_id=branch_upload.id, business_upload_id=biz_upload.id)

    assert find_exceptions(db) == []


def test_correcting_the_upstream_figures_clears_the_exception_without_a_rematch(db_session):
    """The flag is computed fresh every call, never stored - so a later
    upload that corrects Letshego Topup (via the existing upsert path)
    clears it automatically, the same way UNMATCHED_* self-resolves."""
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)

    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=2, period_month=8, period_year=2026,
        loan_date=dt.date(2026, 8, 5), client_name="Client A", client_check_no="871", client_account_no="ACC001",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    bt = BusinessTransaction(
        upload_id=biz_upload.id, row_number=2, branch_name_raw="Arusha", employee_no="871",
        loan_type=LoanType.RF, disbursement_date=dt.date(2026, 8, 5),
        appl_amount=200_000, letshego_topup=250_000,  # bad
        client_disb_ext_account_no="ACC001",
    )
    db.add(bt)
    db.flush()
    run_matching(db, branch_upload_id=branch_upload.id, business_upload_id=biz_upload.id)
    assert len(find_exceptions(db)) == 1

    bt.letshego_topup = 50_000  # corrected, as if a later upload upserted this field
    db.flush()
    assert find_exceptions(db) == []


# ---------------------------------------------------------------------
# DSA/DTL Summary aggregation: amounts reconcile with Total Commission
# ---------------------------------------------------------------------

def test_dsa_and_dtl_summary_amounts_reconcile_with_total_commission(db_session):
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)

    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=2, period_month=8, period_year=2026,
        loan_date=dt.date(2026, 8, 5), client_name="Client A", client_check_no="871", client_account_no="ACC001",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=3, period_month=8, period_year=2026,
        loan_date=dt.date(2026, 8, 6), client_name="Client B", client_check_no="872", client_account_no="ACC002",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=2, branch_name_raw="Arusha", employee_no="871",
        loan_type=LoanType.NL, disbursement_date=dt.date(2026, 8, 5), disbursement_amt=1_000_000,
        client_disb_ext_account_no="ACC001",
    ))
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=3, branch_name_raw="Arusha", employee_no="872",
        loan_type=LoanType.RF, disbursement_date=dt.date(2026, 8, 6),
        appl_amount=250_000, letshego_topup=50_000,
        client_disb_ext_account_no="ACC002",
    ))
    db.flush()
    run_matching(db, branch_upload_id=branch_upload.id, business_upload_id=biz_upload.id)

    run = CommissionRun(run_type=RunType.ORG_WIDE, branch_id=None, period="2026-08", status=RunStatus.DRAFT, created_by_user_id=admin.id)
    db.add(run)
    db.flush()
    calculate_commission_run(db, run)

    from app.core.config import get_settings
    settings = get_settings()

    dsa_lines = db.query(CommissionLine).filter(CommissionLine.commission_run_id == run.id, CommissionLine.dsa_id.isnot(None)).all()
    dtl_lines = db.query(CommissionLine).filter(CommissionLine.commission_run_id == run.id, CommissionLine.dtl_id.isnot(None)).all()

    dsa_agg = aggregate_dsa_summary(dsa_lines)[dsa.id]
    dtl_agg = aggregate_dtl_summary(dtl_lines)[dtl.id]

    # New Loans Amount * NL rate + Topup Loans Amount * RF rate must equal
    # Total Commission for that row - the whole point of the sanity check.
    dsa_expected = round(dsa_agg["nl_amount"] * settings.dsa_nl_rate + dsa_agg["rf_amount"] * settings.dsa_rf_rate, 2)
    assert round(dsa_agg["total_commission"], 2) == dsa_expected

    dtl_expected = round(dtl_agg["nl_amount"] * settings.dtl_nl_rate + dtl_agg["rf_amount"] * settings.dtl_rf_rate, 2)
    assert round(dtl_agg["total_commission"], 2) == dtl_expected

    # And the underlying figures are exactly what was on the business file.
    assert dsa_agg["nl_amount"] == 1_000_000.0
    assert dsa_agg["rf_amount"] == 200_000.0  # 250,000 - 50,000
    assert dtl_agg["nl_amount"] == 1_000_000.0
    assert dtl_agg["rf_amount"] == 200_000.0


def test_locked_run_keeps_its_original_amounts_when_formula_changes_later(db_session):
    """A formula change never retroactively touches a LOCKED run - its
    stored CommissionLine values are whatever was computed at calc time,
    and recalculation is refused once locked (existing guard, re-asserted
    here in the context of this formula change)."""
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)
    run = CommissionRun(run_type=RunType.ORG_WIDE, branch_id=None, period="2026-08", status=RunStatus.LOCKED, created_by_user_id=admin.id)
    db.add(run)
    db.flush()

    import pytest
    from app.services.commission import CommissionRunError

    with pytest.raises(CommissionRunError):
        calculate_commission_run(db, run)
