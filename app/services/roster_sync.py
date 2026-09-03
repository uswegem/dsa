"""
Keeps the dsas / dtls / dsa_dtl_assignments tables in sync with what the
latest Branch Manager upload says, without corrupting prior months'
commission history.

Assumption (no explicit spec for this - documented so it can be revisited):
each upload's DSA/DTL pairings become effective as of the earliest loan_date
seen in that upload (falling back to the upload's date if loan_date is
missing everywhere). If a DSA's DTL changes, the previous open-ended
assignment is closed the day before the new one starts; it is never deleted
or mutated in a way that would change a past commission_period's supervisor.

PENDING- placeholder codes: some DTLs were seeded from a name-only
reference list with no DTL_CODE available, using generated codes of the
form "PENDING-001". The first time a real Branch Manager upload carries an
actual DTL_CODE for a name that currently only has a PENDING- code (same
name, same branch), upsert_dtl() adopts the real code onto that existing
record instead of creating a duplicate Dtl row for the same person.
"""
import datetime as dt

from sqlalchemy.orm import Session

from app.models import Dsa, Dtl, DsaDtlAssignment


def upsert_dsa(db: Session, dsa_code: str, dsa_name: str, dsa_account_no: str | None, branch_id: int | None) -> Dsa:
    dsa = db.query(Dsa).filter(Dsa.dsa_code == dsa_code).first()
    if dsa is None:
        dsa = Dsa(dsa_code=dsa_code, dsa_name=dsa_name, dsa_account_no=dsa_account_no, branch_id=branch_id)
        db.add(dsa)
        db.flush()
    else:
        # Keep the latest-seen name/account/branch - rosters are re-uploaded
        # monthly and are the source of truth for current DSA details.
        dsa.dsa_name = dsa_name
        if dsa_account_no:
            dsa.dsa_account_no = dsa_account_no
        if branch_id:
            dsa.branch_id = branch_id
        db.flush()
    return dsa


PENDING_CODE_PREFIX = "PENDING-"


def upsert_dtl(db: Session, dtl_code: str, dtl_name: str, branch_id: int | None = None) -> Dtl:
    dtl = db.query(Dtl).filter(Dtl.dtl_code == dtl_code).first()
    if dtl is not None:
        if dtl.dtl_name != dtl_name:
            dtl.dtl_name = dtl_name
        if branch_id and not dtl.branch_id:
            dtl.branch_id = branch_id
        db.flush()
        return dtl

    # No record with this exact code exists yet. Before creating a new one,
    # check whether this is really an already-known DTL whose code is only
    # a PENDING- placeholder - if so, adopt the real code onto that record
    # rather than creating a duplicate for the same person. Matched by name
    # (case-insensitive) and, when known, branch.
    placeholder_query = db.query(Dtl).filter(
        Dtl.dtl_code.startswith(PENDING_CODE_PREFIX),
        Dtl.dtl_name.ilike(dtl_name.strip()),
    )
    if branch_id is not None:
        placeholder_query = placeholder_query.filter((Dtl.branch_id == branch_id) | (Dtl.branch_id.is_(None)))
    placeholder = placeholder_query.first()
    if placeholder is not None:
        placeholder.dtl_code = dtl_code
        if branch_id:
            placeholder.branch_id = branch_id
        db.flush()
        return placeholder

    dtl = Dtl(dtl_code=dtl_code, dtl_name=dtl_name, branch_id=branch_id)
    db.add(dtl)
    db.flush()
    return dtl


def sync_assignment(db: Session, dsa: Dsa, dtl: Dtl, effective_from: dt.date) -> None:
    current = (
        db.query(DsaDtlAssignment)
        .filter(DsaDtlAssignment.dsa_id == dsa.id, DsaDtlAssignment.effective_to.is_(None))
        .order_by(DsaDtlAssignment.effective_from.desc())
        .first()
    )

    if current is not None and current.dtl_id == dtl.id:
        return  # unchanged, nothing to do

    if current is not None:
        if effective_from <= current.effective_from:
            # A row from an earlier period than the current open assignment
            # arrived late; don't rewrite supervision history out from under
            # already-run commissions. No-op, but this is worth surfacing.
            return
        current.effective_to = effective_from - dt.timedelta(days=1)

    db.add(DsaDtlAssignment(dsa_id=dsa.id, dtl_id=dtl.id, effective_from=effective_from, effective_to=None))
    db.flush()


def sync_roster_from_branch_sales(db: Session, branch_sale_rows: list, upload_date: dt.date) -> None:
    """branch_sale_rows: list of app.models.BranchSale ORM instances already flushed."""
    for row in branch_sale_rows:
        dsa = upsert_dsa(db, row.dsa_code, row.dsa_name, row.dsa_account_no, row.branch_id)
        if row.dtl_code and row.dtl_name:
            dtl = upsert_dtl(db, row.dtl_code, row.dtl_name, branch_id=row.branch_id)
            effective_from = row.loan_date or upload_date
            sync_assignment(db, dsa, dtl, effective_from)
