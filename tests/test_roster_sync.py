import datetime as dt

from app.models import Branch, Dsa, Dtl, DsaDtlAssignment
from app.services.roster_sync import sync_assignment, upsert_dtl


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


def test_same_day_reassignment_overwrites_in_place_not_silently_dropped(db_session):
    """Regression test: two DTL assignment changes on the SAME calendar day
    (e.g. an admin correcting a DSA's DTL right after creating them, or two
    Branch Manager uploads in one day) must both take effect. A naive
    effective_from <= current.effective_from guard (meant to reject stale,
    late-arriving upload data) would silently no-op the second change."""
    db = db_session
    branch = Branch(name="Arusha")
    db.add(branch)
    db.flush()
    dsa = Dsa(dsa_code="DSA01", dsa_name="Test DSA", branch_id=branch.id)
    dtl_a = Dtl(dtl_code="DTL-A", dtl_name="Alice", branch_id=branch.id)
    dtl_b = Dtl(dtl_code="DTL-B", dtl_name="Bob", branch_id=branch.id)
    db.add_all([dsa, dtl_a, dtl_b])
    db.flush()

    today = dt.date(2026, 9, 3)
    sync_assignment(db, dsa, dtl_a, today)
    sync_assignment(db, dsa, dtl_b, today)  # same-day correction

    assignments = db.query(DsaDtlAssignment).filter(DsaDtlAssignment.dsa_id == dsa.id).all()
    assert len(assignments) == 1  # corrected in place, not a second (invalid) history row
    assert assignments[0].dtl_id == dtl_b.id
    assert assignments[0].effective_from == today
    assert assignments[0].effective_to is None


def test_next_day_reassignment_still_closes_prior_assignment(db_session):
    """Make sure the same-day fix didn't break the normal effective-dated
    history behavior for a genuinely later change."""
    db = db_session
    branch = Branch(name="Arusha")
    db.add(branch)
    db.flush()
    dsa = Dsa(dsa_code="DSA01", dsa_name="Test DSA", branch_id=branch.id)
    dtl_a = Dtl(dtl_code="DTL-A", dtl_name="Alice", branch_id=branch.id)
    dtl_b = Dtl(dtl_code="DTL-B", dtl_name="Bob", branch_id=branch.id)
    db.add_all([dsa, dtl_a, dtl_b])
    db.flush()

    sync_assignment(db, dsa, dtl_a, dt.date(2026, 9, 3))
    sync_assignment(db, dsa, dtl_b, dt.date(2026, 9, 10))

    assignments = db.query(DsaDtlAssignment).filter(DsaDtlAssignment.dsa_id == dsa.id).order_by(DsaDtlAssignment.effective_from).all()
    assert len(assignments) == 2
    assert assignments[0].dtl_id == dtl_a.id
    assert assignments[0].effective_to == dt.date(2026, 9, 9)
    assert assignments[1].dtl_id == dtl_b.id
    assert assignments[1].effective_to is None
