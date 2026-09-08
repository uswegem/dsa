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
from app.services.commission import calculate_commission_run
from app.services.matching import run_matching


def _seed_base(db):
    branch = Branch(name="Arusha", code="ARU")
    db.add(branch)
    db.flush()

    dsa = Dsa(dsa_code="DSA01", dsa_name="Amos", dsa_account_no="AC-DSA01", branch_id=branch.id)
    dtl = Dtl(dtl_code="DTL01", dtl_name="Grace T")
    db.add_all([dsa, dtl])

    admin_role = db.query(Role).filter(Role.name == "ADMIN").one()
    admin = User(email="admin@test.local", hashed_password="x", full_name="Admin", role_id=admin_role.id)
    db.add(admin)
    db.flush()

    branch_upload = Upload(
        upload_type=UploadType.BRANCH_MANAGER, uploaded_by_user_id=admin.id, branch_id=branch.id,
        original_filename="branch.xlsx", storage_path="x", status=UploadStatus.PROCESSED,
    )
    biz_upload = Upload(
        upload_type=UploadType.BUSINESS_MANAGER, uploaded_by_user_id=admin.id, branch_id=None,
        original_filename="biz.xlsx", storage_path="x", status=UploadStatus.PROCESSED,
    )
    db.add_all([branch_upload, biz_upload])
    db.flush()
    return branch, dsa, dtl, admin, branch_upload, biz_upload


def test_matching_classifies_all_four_statuses(db_session):
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)

    # MATCHED
    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=2, period_month=8, period_year=2026, loan_date=dt.date(2026, 8, 5),
        client_name="Client A", client_check_no="871", client_account_no="ACC001",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    # MATCHED_WITH_WARNING (secondary check mismatches)
    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=3, period_month=8, period_year=2026, loan_date=dt.date(2026, 8, 6),
        client_name="Client B", client_check_no="872", client_account_no="ACC002",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    # UNMATCHED_IN_BUSINESS_FILE (no business row for ACC003)
    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=4, period_month=8, period_year=2026, loan_date=dt.date(2026, 8, 7),
        client_name="Client C", client_check_no="873", client_account_no="ACC003",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))

    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=2, branch_name_raw="Arusha", employee_no="871",
        loan_type=LoanType.NL, disbursement_date=dt.date(2026, 8, 5), disbursement_amt=1_000_000,
        client_disb_ext_account_no="ACC001",
    ))
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=3, branch_name_raw="Arusha", employee_no="999",  # mismatch vs 872
        loan_type=LoanType.RF, disbursement_date=dt.date(2026, 8, 6), payout_to_client=200_000,
        client_disb_ext_account_no="ACC002",
    ))
    # UNMATCHED_IN_BRANCH_FILE (no branch sale claims ACC004)
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=4, branch_name_raw="Arusha", employee_no="555",
        loan_type=LoanType.NL, disbursement_date=dt.date(2026, 8, 1), disbursement_amt=400_000,
        client_disb_ext_account_no="ACC004",
    ))
    db.flush()

    run_matching(db, branch_upload_id=branch_upload.id, business_upload_id=biz_upload.id)
    db.flush()

    statuses = {m.match_status for m in db.query(MatchedTransaction).all()}
    assert statuses == {
        MatchStatus.MATCHED,
        MatchStatus.MATCHED_WITH_WARNING,
        MatchStatus.UNMATCHED_IN_BUSINESS_FILE,
        MatchStatus.UNMATCHED_IN_BRANCH_FILE,
    }

    matched = db.query(MatchedTransaction).filter(MatchedTransaction.match_status == MatchStatus.MATCHED).one()
    assert matched.commission_period == "2026-08"


def test_unmatched_rows_are_re_resolved_when_the_other_file_arrives_later(db_session):
    """Regression test: the two files are uploaded independently, often far
    apart. A branch sale that's UNMATCHED_IN_BUSINESS_FILE today must still
    get paired up once the business transaction shows up in a later upload -
    that classification must never be treated as permanent."""
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)

    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=2, period_month=8, period_year=2026, loan_date=dt.date(2026, 8, 5),
        client_name="Client A", client_check_no="871", client_account_no="ACC001",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    db.flush()

    # First matching pass: only the branch file has landed so far.
    run_matching(db, branch_upload_id=branch_upload.id, business_upload_id=None)
    db.flush()
    mt = db.query(MatchedTransaction).one()
    assert mt.match_status == MatchStatus.UNMATCHED_IN_BUSINESS_FILE

    # The business file arrives later, in a separate upload.
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=2, branch_name_raw="Arusha", employee_no="871",
        loan_type=LoanType.NL, disbursement_date=dt.date(2026, 8, 5), disbursement_amt=1_000_000,
        client_disb_ext_account_no="ACC001",
    ))
    db.flush()
    run_matching(db, branch_upload_id=None, business_upload_id=biz_upload.id)
    db.flush()

    mt = db.query(MatchedTransaction).one()
    assert mt.match_status == MatchStatus.MATCHED
    assert mt.commission_period == "2026-08"


def test_commission_calculation_rates_and_exclusions(db_session):
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)

    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=2, period_month=8, period_year=2026, loan_date=dt.date(2026, 8, 5),
        client_name="Client A", client_check_no="871", client_account_no="ACC001",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    db.add(BranchSale(
        upload_id=branch_upload.id, branch_id=branch.id, row_number=3, period_month=8, period_year=2026, loan_date=dt.date(2026, 8, 6),
        client_name="Client B", client_check_no="872", client_account_no="ACC002",
        dsa_code="DSA01", dsa_name="Amos", dtl_code="DTL01", dtl_name="Grace T",
    ))
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=2, branch_name_raw="Arusha", employee_no="871",
        loan_type=LoanType.NL, disbursement_date=dt.date(2026, 8, 5), disbursement_amt=1_000_000,
        client_disb_ext_account_no="ACC001",
    ))
    db.add(BusinessTransaction(
        upload_id=biz_upload.id, row_number=3, branch_name_raw="Arusha", employee_no="999",
        loan_type=LoanType.RF, disbursement_date=dt.date(2026, 8, 6),
        appl_amount=250_000, letshego_topup=50_000,  # net base = 250,000 - 50,000 = 200,000
        client_disb_ext_account_no="ACC002",
    ))
    db.flush()
    run_matching(db, branch_upload_id=branch_upload.id, business_upload_id=biz_upload.id)

    run = CommissionRun(run_type=RunType.ORG_WIDE, branch_id=None, period="2026-08", status=RunStatus.DRAFT, created_by_user_id=admin.id)
    db.add(run)
    db.flush()

    result = calculate_commission_run(db, run)
    assert result.lines_created == 4  # 2 transactions x (DSA + DTL)

    lines = db.query(CommissionLine).filter(CommissionLine.commission_run_id == run.id).all()
    dsa_nl = [l for l in lines if l.dsa_id and l.loan_type == LoanType.NL][0]
    dtl_nl = [l for l in lines if l.dtl_id and l.loan_type == LoanType.NL][0]
    dsa_rf = [l for l in lines if l.dsa_id and l.loan_type == LoanType.RF][0]
    dtl_rf = [l for l in lines if l.dtl_id and l.loan_type == LoanType.RF][0]

    assert float(dsa_nl.commission_amount) == 70_000.0   # 7% of 1,000,000 gross
    assert float(dtl_nl.commission_amount) == 10_000.0   # 1% of 1,000,000 gross
    assert float(dsa_rf.commission_amount) == 6_000.0    # 3% of 200,000 net (Appl Amount - Letshego Topup)
    assert float(dtl_rf.commission_amount) == 2_000.0    # 1% of 200,000 net

    total = sum(float(l.commission_amount) for l in lines)
    assert total == 88_000.0


def test_recalculating_a_locked_run_is_rejected(db_session):
    db = db_session
    branch, dsa, dtl, admin, branch_upload, biz_upload = _seed_base(db)
    run = CommissionRun(run_type=RunType.ORG_WIDE, branch_id=None, period="2026-08", status=RunStatus.LOCKED, created_by_user_id=admin.id)
    db.add(run)
    db.flush()

    import pytest
    from app.services.commission import CommissionRunError

    with pytest.raises(CommissionRunError):
        calculate_commission_run(db, run)
