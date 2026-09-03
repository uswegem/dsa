import datetime as dt

from app.models import Branch, BranchSale, BusinessTransaction, Role, Upload, User
from app.models.enums import LoanType, UploadStatus, UploadType
from app.services.ingest_branch_manager import ParsedBranchRow
from app.services.ingest_business_manager import ParsedBusinessRow
from app.services.upsert import upsert_branch_sale, upsert_business_transaction


def _seed(db):
    branch = Branch(name="Arusha")
    admin_role = db.query(Role).filter(Role.name == "ADMIN").one()
    admin = User(email="admin@test.local", hashed_password="x", full_name="Admin", role_id=admin_role.id)
    db.add_all([branch, admin])
    db.flush()
    upload1 = Upload(
        upload_type=UploadType.BRANCH_MANAGER, uploaded_by_user_id=admin.id, branch_id=branch.id,
        period_month=8, period_year=2026, original_filename="a.xlsx", storage_path="x", status=UploadStatus.PROCESSING,
    )
    upload2 = Upload(
        upload_type=UploadType.BRANCH_MANAGER, uploaded_by_user_id=admin.id, branch_id=branch.id,
        period_month=8, period_year=2026, original_filename="b.xlsx", storage_path="x", status=UploadStatus.PROCESSING,
    )
    db.add_all([upload1, upload2])
    db.flush()
    return branch, admin, upload1, upload2


def _row(**overrides):
    defaults = dict(
        row_number=2, sheet_name="Arusha", loan_date=dt.date(2026, 8, 5),
        client_name="Jane Doe", client_check_no="871", client_account_no="ACC001",
        application_number_ess=None, reported_amount=500000.0, branch_raw="Arusha",
        dsa_code="DSA01", dsa_account_no="AC1", dsa_name="Amos", dtl_name="Grace", dtl_code="DTL01",
    )
    defaults.update(overrides)
    return ParsedBranchRow(**defaults)


def test_second_upload_for_same_period_updates_not_duplicates(db_session):
    """The core incremental-upload guarantee: re-uploading a row for a
    period already in progress must update it in place, never insert a
    second row that would double-count commission."""
    db = db_session
    branch, admin, upload1, upload2 = _seed(db)

    row1, outcome1 = upsert_branch_sale(db, upload1.id, branch.id, 8, 2026, _row(), admin.id)
    assert outcome1.created is True

    # Same natural key (client_account_no, period), different DSA this time
    # - a legitimate correction submitted in a later upload for the period.
    row2, outcome2 = upsert_branch_sale(db, upload2.id, branch.id, 8, 2026, _row(dsa_code="DSA02", dsa_name="Beatrice"), admin.id)

    assert outcome2.created is False
    assert outcome2.changed is True
    assert row2.id == row1.id  # same row, updated - not a duplicate
    assert db.query(BranchSale).count() == 1
    assert row2.dsa_code == "DSA02"
    assert "dsa_code" in outcome2.changes
    assert outcome2.changes["dsa_code"] == {"old": "DSA01", "new": "DSA02"}


def test_reupload_of_identical_row_is_a_no_op(db_session):
    db = db_session
    branch, admin, upload1, upload2 = _seed(db)

    upsert_branch_sale(db, upload1.id, branch.id, 8, 2026, _row(), admin.id)
    _row2, outcome = upsert_branch_sale(db, upload2.id, branch.id, 8, 2026, _row(), admin.id)

    assert outcome.created is False
    assert outcome.changed is False
    assert outcome.changes == {}


def test_different_period_is_a_different_row_not_an_update(db_session):
    """Same account number, different period -> genuinely new data (the
    natural key includes period_month/period_year), not an update."""
    db = db_session
    branch, admin, upload1, upload2 = _seed(db)

    upsert_branch_sale(db, upload1.id, branch.id, 8, 2026, _row(), admin.id)
    _row2, outcome = upsert_branch_sale(db, upload2.id, branch.id, 9, 2026, _row(), admin.id)

    assert outcome.created is True
    assert db.query(BranchSale).count() == 2


def test_business_transaction_upsert_on_natural_key(db_session):
    db = db_session
    branch, admin, upload1, upload2 = _seed(db)

    biz_row = ParsedBusinessRow(
        row_number=2, branch_raw="Arusha", employee_no="871", customer_no="C001", account_no="ACC010",
        loan_type="NL", disbursement_date=dt.date(2026, 8, 5), disbursement_amt=1_000_000,
        payout_to_client=None, letshego_topup=None, appl_amount=1_000_000, client_disb_ext_account_no="ACC001",
    )
    row1, outcome1 = upsert_business_transaction(db, upload1.id, biz_row, admin.id)
    assert outcome1.created is True

    corrected = ParsedBusinessRow(**{**biz_row.__dict__, "disbursement_amt": 1_100_000.0})
    row2, outcome2 = upsert_business_transaction(db, upload2.id, corrected, admin.id)

    assert outcome2.created is False
    assert outcome2.changed is True
    assert row2.id == row1.id
    assert db.query(BusinessTransaction).count() == 1
    assert float(row2.disbursement_amt) == 1_100_000.0
