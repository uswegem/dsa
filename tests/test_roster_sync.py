from app.models import Branch, Dtl
from app.services.roster_sync import upsert_dtl


def test_real_dtl_code_reconciles_onto_existing_placeholder(db_session):
    """A DTL seeded from a name-only reference list (PENDING- code) must
    adopt its real code the first time it appears in an actual upload,
    rather than getting a second, duplicate Dtl row for the same person."""
    db = db_session
    branch = Branch(name="Arusha")
    db.add(branch)
    db.flush()

    placeholder = Dtl(dtl_code="PENDING-001", dtl_name="Vicent Ngonyani", branch_id=branch.id)
    db.add(placeholder)
    db.flush()
    placeholder_id = placeholder.id

    resolved = upsert_dtl(db, dtl_code="DTL07", dtl_name="Vicent Ngonyani", branch_id=branch.id)

    assert resolved.id == placeholder_id  # same record, not a new one
    assert resolved.dtl_code == "DTL07"
    assert db.query(Dtl).count() == 1


def test_real_dtl_code_for_different_branch_does_not_reconcile(db_session):
    """Two different people can share a name across branches - a placeholder
    in one branch must not be silently claimed by a same-named DTL from
    another branch."""
    db = db_session
    branch_a = Branch(name="Arusha")
    branch_b = Branch(name="Dodoma")
    db.add_all([branch_a, branch_b])
    db.flush()

    db.add(Dtl(dtl_code="PENDING-001", dtl_name="John Doe", branch_id=branch_a.id))
    db.flush()

    resolved = upsert_dtl(db, dtl_code="DTL99", dtl_name="John Doe", branch_id=branch_b.id)

    assert resolved.dtl_code == "DTL99"
    assert db.query(Dtl).count() == 2  # a new record for the Dodoma John Doe, placeholder untouched
