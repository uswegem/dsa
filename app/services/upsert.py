"""
Upsert-on-natural-key logic for incremental uploads.

Branch Managers and the Business Manager upload repeatedly through the
month; a later upload's row for the same natural key is treated as the
more current version of that row and updates it in place, rather than
being inserted as a duplicate (which would double-count commission).

Natural keys:
  branch_sales:          (client_account_no, period_month, period_year)
  business_transactions: (client_disb_ext_account_no, loan_type, disbursement_date)

Every update that actually changes a field is logged to audit_log with the
old and new values, via app.services.audit.log_action.
"""
import datetime as dt
import decimal
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import BranchSale, BusinessTransaction
from app.services.audit import log_action


def _jsonable(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def _apply_and_diff(existing, new_values: dict) -> dict:
    """Sets each field on `existing` from new_values, returning {field: {old, new}} for those that actually changed."""
    changes = {}
    for key, new_val in new_values.items():
        old_val = getattr(existing, key)
        if old_val != new_val:
            changes[key] = {"old": _jsonable(old_val), "new": _jsonable(new_val)}
            setattr(existing, key, new_val)
    return changes


@dataclass
class UpsertOutcome:
    created: bool
    changed: bool
    changes: dict


def upsert_branch_sale(
    db: Session,
    upload_id: int,
    branch_id: int,
    period_month: int,
    period_year: int,
    parsed_row,  # ingest_branch_manager.ParsedBranchRow
    actor_user_id: int,
) -> tuple[BranchSale, UpsertOutcome]:
    existing = (
        db.query(BranchSale)
        .filter(
            BranchSale.client_account_no == parsed_row.client_account_no,
            BranchSale.period_month == period_month,
            BranchSale.period_year == period_year,
        )
        .first()
    )

    new_values = dict(
        upload_id=upload_id,
        branch_id=branch_id,
        row_number=parsed_row.row_number,
        period_month=period_month,
        period_year=period_year,
        loan_date=parsed_row.loan_date,
        client_name=parsed_row.client_name,
        client_check_no=parsed_row.client_check_no,
        client_account_no=parsed_row.client_account_no,
        application_number_ess=parsed_row.application_number_ess,
        reported_amount=parsed_row.reported_amount,
        branch_name_raw=parsed_row.branch_raw,
        dsa_code=parsed_row.dsa_code,
        dsa_account_no=parsed_row.dsa_account_no,
        dsa_name=parsed_row.dsa_name,
        dtl_name=parsed_row.dtl_name,
        dtl_code=parsed_row.dtl_code,
    )

    if existing is None:
        row = BranchSale(**new_values)
        db.add(row)
        db.flush()
        return row, UpsertOutcome(created=True, changed=False, changes={})

    # upload_id/row_number always "change" (they point at this upload) but
    # that's bookkeeping, not a meaningful business change - diff only the
    # substantive fields.
    diffable = {k: v for k, v in new_values.items() if k not in ("upload_id", "row_number")}
    changes = _apply_and_diff(existing, diffable)
    existing.upload_id = upload_id
    existing.row_number = parsed_row.row_number
    db.flush()

    if changes:
        log_action(
            db, actor_user_id, "BRANCH_SALE_UPDATED", "BranchSale", existing.id,
            client_account_no=parsed_row.client_account_no, period=f"{period_year}-{period_month:02d}",
            changes=changes,
        )
    return existing, UpsertOutcome(created=False, changed=bool(changes), changes=changes)


def upsert_business_transaction(
    db: Session,
    upload_id: int,
    parsed_row,  # ingest_business_manager.ParsedBusinessRow
    actor_user_id: int,
) -> tuple[BusinessTransaction, UpsertOutcome]:
    existing = (
        db.query(BusinessTransaction)
        .filter(
            BusinessTransaction.client_disb_ext_account_no == parsed_row.client_disb_ext_account_no,
            BusinessTransaction.loan_type == parsed_row.loan_type,
            BusinessTransaction.disbursement_date == parsed_row.disbursement_date,
        )
        .first()
    )

    new_values = dict(
        upload_id=upload_id,
        row_number=parsed_row.row_number,
        branch_name_raw=parsed_row.branch_raw,
        employee_no=parsed_row.employee_no,
        customer_no=parsed_row.customer_no,
        account_no=parsed_row.account_no,
        loan_type=parsed_row.loan_type,
        disbursement_date=parsed_row.disbursement_date,
        disbursement_amt=parsed_row.disbursement_amt,
        payout_to_client=parsed_row.payout_to_client,
        letshego_topup=parsed_row.letshego_topup,
        appl_amount=parsed_row.appl_amount,
        client_disb_ext_account_no=parsed_row.client_disb_ext_account_no,
    )

    if existing is None:
        row = BusinessTransaction(**new_values)
        db.add(row)
        db.flush()
        return row, UpsertOutcome(created=True, changed=False, changes={})

    diffable = {k: v for k, v in new_values.items() if k not in ("upload_id", "row_number")}
    changes = _apply_and_diff(existing, diffable)
    existing.upload_id = upload_id
    existing.row_number = parsed_row.row_number
    db.flush()

    if changes:
        log_action(
            db, actor_user_id, "BUSINESS_TRANSACTION_UPDATED", "BusinessTransaction", existing.id,
            client_disb_ext_account_no=parsed_row.client_disb_ext_account_no,
            loan_type=parsed_row.loan_type, disbursement_date=parsed_row.disbursement_date.isoformat(),
            changes=changes,
        )
    return existing, UpsertOutcome(created=False, changed=bool(changes), changes=changes)
