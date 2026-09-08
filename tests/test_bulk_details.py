"""
Bulk update (Admin -> DSAs/DTLs -> Bulk Update): matches an uploaded CSV/
Excel row to an EXISTING record by (name, branch) - case-insensitive,
whitespace-trimmed - and updates only its code/account number. Never
creates a new DSA/DTL; an unmatched row is reported back, not guessed at.
"""
import io

import pytest

from app.models import Branch, Dsa, Dtl, Role, User
from app.services.bulk_details import (
    apply_bulk_update,
    normalize_match_key,
    parse_bulk_detail_file,
    sanitize_numeric_like,
)


def _admin(db):
    role = db.query(Role).filter(Role.name == "ADMIN").one()
    u = User(email="admin@example.com", hashed_password="x", full_name="Admin", role_id=role.id)
    db.add(u)
    db.flush()
    return u


def _csv_bytes(rows: list[str]) -> bytes:
    header = "DTL_NAME,BRANCH,DTL_CODE,DTL_ACCOUNT_NO\n"
    return (header + "\n".join(rows)).encode("utf-8")


# ---------------------------------------------------------------------
# sanitize_numeric_like / normalize_match_key
# ---------------------------------------------------------------------

def test_sanitize_numeric_like_strips_stray_tab_and_quote():
    cleaned, was_malformed = sanitize_numeric_like("\t21710145716\"")
    assert cleaned == "21710145716"
    assert was_malformed is True


def test_sanitize_numeric_like_leaves_clean_value_alone():
    cleaned, was_malformed = sanitize_numeric_like("21710145716")
    assert cleaned == "21710145716"
    assert was_malformed is False


def test_normalize_match_key_case_insensitive_and_trimmed():
    assert normalize_match_key("  RUVUMA ") == normalize_match_key("Ruvuma") == "ruvuma"


# ---------------------------------------------------------------------
# parse_bulk_detail_file
# ---------------------------------------------------------------------

def test_parse_missing_columns_raises():
    contents = b"NAME,PLACE\nFoo,Bar\n"
    with pytest.raises(ValueError):
        parse_bulk_detail_file(contents, "x.csv", "dtl")


def test_parse_skips_blank_name_or_branch_as_an_issue_not_a_crash():
    contents = _csv_bytes([
        ",Ruvuma,123,456",  # blank name
        "Someone,,123,456",  # blank branch
        "Real Person,Ruvuma,123,456",
    ])
    parsed = parse_bulk_detail_file(contents, "x.csv", "dtl")
    assert len(parsed.rows) == 1
    assert parsed.rows[0].name == "Real Person"
    assert len(parsed.issues) == 2


# ---------------------------------------------------------------------
# apply_bulk_update
# ---------------------------------------------------------------------

def _seed_dtl(db, name, branch, code="PENDING-001", account=None):
    b = db.query(Branch).filter(Branch.name == branch).first()
    if b is None:
        b = Branch(name=branch)
        db.add(b)
        db.flush()
    dtl = Dtl(dtl_code=code, dtl_name=name, dtl_account_no=account, branch_id=b.id)
    db.add(dtl)
    db.flush()
    return dtl


def test_matches_case_insensitive_whitespace_trimmed_branch_and_updates(db_session):
    """The exact scenario called out in the task: RUVUMA (upload) vs Ruvuma
    (existing branch record) must match, not create a duplicate."""
    db = db_session
    admin = _admin(db)
    dtl = _seed_dtl(db, "Francis Andrew Simfukwe", "Ruvuma", code="PENDING-026")

    contents = _csv_bytes(["Francis Andrew Simfukwe,RUVUMA,5010260235,21710144752"])
    parsed = parse_bulk_detail_file(contents, "x.csv", "dtl")
    summary = apply_bulk_update(
        db, parsed, model=Dtl, name_field="dtl_name", code_field="dtl_code", account_field="dtl_account_no",
        entity_label="DTL", entity_type_for_audit="Dtl", log_action_name="DTL_BULK_UPDATED", current_user_id=admin.id,
    )

    assert len(summary.updated) == 1
    assert summary.unmatched == []
    db.refresh(dtl)
    assert dtl.dtl_code == "5010260235"
    assert dtl.dtl_account_no == "21710144752"
    # No duplicate branch was created for the casing mismatch.
    assert db.query(Branch).filter(Branch.name.ilike("ruvuma")).count() == 1


def test_unmatched_row_is_reported_not_created(db_session):
    db = db_session
    admin = _admin(db)
    _seed_dtl(db, "Existing Person", "Arusha")

    contents = _csv_bytes(["Nobody Here,Arusha,999,111"])
    parsed = parse_bulk_detail_file(contents, "x.csv", "dtl")
    summary = apply_bulk_update(
        db, parsed, model=Dtl, name_field="dtl_name", code_field="dtl_code", account_field="dtl_account_no",
        entity_label="DTL", entity_type_for_audit="Dtl", log_action_name="DTL_BULK_UPDATED", current_user_id=admin.id,
    )

    assert len(summary.unmatched) == 1
    assert summary.updated == []
    assert db.query(Dtl).filter(Dtl.dtl_name == "Nobody Here").first() is None


def test_code_conflict_with_another_existing_record_is_an_error_not_applied(db_session):
    db = db_session
    admin = _admin(db)
    target = _seed_dtl(db, "Target Person", "Arusha", code="PENDING-001")
    _seed_dtl(db, "Other Person", "Arusha", code="ALREADY-TAKEN")

    contents = _csv_bytes(["Target Person,Arusha,ALREADY-TAKEN,111"])
    parsed = parse_bulk_detail_file(contents, "x.csv", "dtl")
    summary = apply_bulk_update(
        db, parsed, model=Dtl, name_field="dtl_name", code_field="dtl_code", account_field="dtl_account_no",
        entity_label="DTL", entity_type_for_audit="Dtl", log_action_name="DTL_BULK_UPDATED", current_user_id=admin.id,
    )

    assert len(summary.errors) == 1
    db.refresh(target)
    assert target.dtl_code == "PENDING-001"  # unchanged


def test_malformed_account_number_is_an_error_not_applied(db_session):
    db = db_session
    admin = _admin(db)
    dtl = _seed_dtl(db, "Target Person", "Arusha")

    contents = _csv_bytes(["Target Person,Arusha,999,ABC123"])
    parsed = parse_bulk_detail_file(contents, "x.csv", "dtl")
    summary = apply_bulk_update(
        db, parsed, model=Dtl, name_field="dtl_name", code_field="dtl_code", account_field="dtl_account_no",
        entity_label="DTL", entity_type_for_audit="Dtl", log_action_name="DTL_BULK_UPDATED", current_user_id=admin.id,
    )

    assert len(summary.errors) == 1
    db.refresh(dtl)
    assert dtl.dtl_account_no is None  # unchanged


def test_stray_tab_and_quote_in_account_number_is_sanitized_before_validation(db_session):
    """The exact copy-paste artifact from the source data - a stray tab and
    quote around the account number - must not require manual cleanup."""
    db = db_session
    admin = _admin(db)
    dtl = _seed_dtl(db, "Jumanne Johnson Maziku", "Mara")

    contents = _csv_bytes(['Jumanne Johnson Maziku,Mara,5000921204,"\t21710145716"""'])
    parsed = parse_bulk_detail_file(contents, "x.csv", "dtl")
    summary = apply_bulk_update(
        db, parsed, model=Dtl, name_field="dtl_name", code_field="dtl_code", account_field="dtl_account_no",
        entity_label="DTL", entity_type_for_audit="Dtl", log_action_name="DTL_BULK_UPDATED", current_user_id=admin.id,
    )

    assert len(summary.updated) == 1
    db.refresh(dtl)
    assert dtl.dtl_account_no == "21710145716"


def test_ambiguous_duplicate_name_branch_pair_is_an_error(db_session):
    db = db_session
    admin = _admin(db)
    _seed_dtl(db, "Same Name", "Arusha", code="PENDING-001")
    _seed_dtl(db, "Same Name", "Arusha", code="PENDING-002")

    contents = _csv_bytes(["Same Name,Arusha,999,111"])
    parsed = parse_bulk_detail_file(contents, "x.csv", "dtl")
    summary = apply_bulk_update(
        db, parsed, model=Dtl, name_field="dtl_name", code_field="dtl_code", account_field="dtl_account_no",
        entity_label="DTL", entity_type_for_audit="Dtl", log_action_name="DTL_BULK_UPDATED", current_user_id=admin.id,
    )

    assert len(summary.errors) == 1
    assert "duplicate" in summary.errors[0].message.lower() or "multiple" in summary.errors[0].message.lower()


def test_unchanged_row_when_values_already_match(db_session):
    db = db_session
    admin = _admin(db)
    _seed_dtl(db, "Target Person", "Arusha", code="999", account="111")

    contents = _csv_bytes(["Target Person,Arusha,999,111"])
    parsed = parse_bulk_detail_file(contents, "x.csv", "dtl")
    summary = apply_bulk_update(
        db, parsed, model=Dtl, name_field="dtl_name", code_field="dtl_code", account_field="dtl_account_no",
        entity_label="DTL", entity_type_for_audit="Dtl", log_action_name="DTL_BULK_UPDATED", current_user_id=admin.id,
    )

    assert len(summary.unchanged) == 1
    assert summary.updated == []


def test_same_pattern_works_generically_for_dsa(db_session):
    """The DSA side of the same feature - generic over the model."""
    db = db_session
    admin = _admin(db)
    branch = Branch(name="Arusha")
    db.add(branch)
    db.flush()
    dsa = Dsa(dsa_code="PENDING-DSA-1", dsa_name="Some Dsa", branch_id=branch.id)
    db.add(dsa)
    db.flush()

    header = "DSA_NAME,BRANCH,DSA_CODE,DSA_ACCOUNT_NO\n"
    contents = (header + "Some Dsa,ARUSHA,DSA-REAL-CODE,55555").encode("utf-8")
    parsed = parse_bulk_detail_file(contents, "x.csv", "dsa")
    summary = apply_bulk_update(
        db, parsed, model=Dsa, name_field="dsa_name", code_field="dsa_code", account_field="dsa_account_no",
        entity_label="DSA", entity_type_for_audit="Dsa", log_action_name="DSA_BULK_UPDATED", current_user_id=admin.id,
    )

    assert len(summary.updated) == 1
    db.refresh(dsa)
    assert dsa.dsa_code == "DSA-REAL-CODE"
    assert dsa.dsa_account_no == "55555"
