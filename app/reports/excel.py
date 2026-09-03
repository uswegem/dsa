"""
Excel report generation (openpyxl).

Four report types:
  - Transaction Detail: every matched transaction, base used, rate, DSA/DTL commission, totals row
  - DSA Summary: one row per DSA - deal counts by type, total commission
  - DTL Summary: one row per DTL - DSAs supervised, deal counts, total commission
  - Exceptions: unmatched / match-quality-warning rows, separated by category

Branch-scoped exports filter everything to one branch; org-wide exports
(Business Manager) include all branches, with a Branch column for context.
"""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.models import (
    BranchSale,
    BusinessTransaction,
    CommissionLine,
    CommissionRun,
    Dsa,
    Dtl,
    MatchedTransaction,
)
from app.models.enums import MatchStatus, PayeeType

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TOTAL_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
TOTAL_FONT = Font(bold=True)


def _write_header(ws, headers: list[str], row: int = 1) -> None:
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _autosize(ws, headers: list[str]) -> None:
    for col, title in enumerate(headers, start=1):
        letter = get_column_letter(col)
        max_len = max([len(str(title))] + [len(str(c.value)) for c in ws[letter] if c.value is not None])
        ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 45)


def _commission_lines_query(db: Session, run: CommissionRun, branch_id: int | None):
    q = (
        db.query(CommissionLine)
        .join(MatchedTransaction, CommissionLine.matched_transaction_id == MatchedTransaction.id)
        .join(BranchSale, MatchedTransaction.branch_sale_id == BranchSale.id)
        .filter(CommissionLine.commission_run_id == run.id)
    )
    if branch_id is not None:
        q = q.filter(BranchSale.branch_id == branch_id)
    return q


def _add_transaction_detail_sheet(wb: Workbook, db: Session, run: CommissionRun, branch_id: int | None) -> None:
    ws = wb.active
    ws.title = "Transaction Detail"
    headers = [
        "Branch", "DSA Code", "DSA Name", "DTL Code", "DTL Name", "Client Name",
        "Client Account No", "Loan Type", "Disbursement Date", "Base Used",
        "Base Amount", "Payee", "Rate", "Commission Amount", "Match Status",
    ]
    _write_header(ws, headers)

    lines = _commission_lines_query(db, run, branch_id).order_by(CommissionLine.matched_transaction_id).all()

    row_idx = 2
    total = 0.0
    for line in lines:
        mt = line.matched_transaction
        bs = mt.branch_sale
        bt = mt.business_transaction
        dsa = line.dsa
        dtl = line.dtl
        values = [
            bs.branch.name if bs and bs.branch else "",
            bs.dsa_code if bs else "",
            dsa.dsa_name if dsa else (bs.dsa_name if bs else ""),
            dtl.dtl_code if dtl else "",
            dtl.dtl_name if dtl else "",
            bs.client_name if bs else "",
            bs.client_account_no if bs else "",
            line.loan_type.value,
            bt.disbursement_date.isoformat() if bt else "",
            line.base_used.value,
            float(line.base_amount),
            line.payee_type.value,
            float(line.rate),
            float(line.commission_amount),
            mt.match_status.value,
        ]
        for col, v in enumerate(values, start=1):
            ws.cell(row=row_idx, column=col, value=v)
        total += float(line.commission_amount)
        row_idx += 1

    total_row = row_idx
    ws.cell(row=total_row, column=13, value="TOTAL").font = TOTAL_FONT
    total_cell = ws.cell(row=total_row, column=14, value=round(total, 2))
    total_cell.font = TOTAL_FONT
    for col in range(1, len(headers) + 1):
        ws.cell(row=total_row, column=col).fill = TOTAL_FILL

    _autosize(ws, headers)


def _add_dsa_summary_sheet(wb: Workbook, db: Session, run: CommissionRun, branch_id: int | None) -> None:
    ws = wb.create_sheet("DSA Summary")
    headers = ["DSA Code", "DSA Name", "Branch", "NL Deals", "RF Deals", "Total Deals", "Total Commission"]
    _write_header(ws, headers)

    lines = (
        _commission_lines_query(db, run, branch_id).filter(CommissionLine.payee_type == PayeeType.DSA).all()
    )
    by_dsa: dict[int, dict] = {}
    for line in lines:
        dsa = line.dsa
        agg = by_dsa.setdefault(
            dsa.id,
            {"dsa": dsa, "nl": 0, "rf": 0, "total_commission": 0.0, "branch": dsa.branch.name if dsa.branch else ""},
        )
        if line.loan_type.value == "NL":
            agg["nl"] += 1
        else:
            agg["rf"] += 1
        agg["total_commission"] += float(line.commission_amount)

    row_idx = 2
    grand_total = 0.0
    for agg in sorted(by_dsa.values(), key=lambda a: a["dsa"].dsa_name):
        dsa = agg["dsa"]
        values = [
            dsa.dsa_code, dsa.dsa_name, agg["branch"], agg["nl"], agg["rf"],
            agg["nl"] + agg["rf"], round(agg["total_commission"], 2),
        ]
        for col, v in enumerate(values, start=1):
            ws.cell(row=row_idx, column=col, value=v)
        grand_total += agg["total_commission"]
        row_idx += 1

    ws.cell(row=row_idx, column=6, value="TOTAL").font = TOTAL_FONT
    ws.cell(row=row_idx, column=7, value=round(grand_total, 2)).font = TOTAL_FONT
    for col in range(1, len(headers) + 1):
        ws.cell(row=row_idx, column=col).fill = TOTAL_FILL

    _autosize(ws, headers)


def _add_dtl_summary_sheet(wb: Workbook, db: Session, run: CommissionRun, branch_id: int | None) -> None:
    ws = wb.create_sheet("DTL Summary")
    headers = ["DTL Code", "DTL Name", "DSAs Supervised", "NL Deals", "RF Deals", "Total Deals", "Total Commission"]
    _write_header(ws, headers)

    lines = (
        _commission_lines_query(db, run, branch_id).filter(CommissionLine.payee_type == PayeeType.DTL).all()
    )
    by_dtl: dict[int, dict] = {}
    for line in lines:
        dtl = line.dtl
        agg = by_dtl.setdefault(dtl.id, {"dtl": dtl, "nl": 0, "rf": 0, "total_commission": 0.0, "dsas": set()})
        agg["dsas"].add(line.matched_transaction.branch_sale.dsa_code)
        if line.loan_type.value == "NL":
            agg["nl"] += 1
        else:
            agg["rf"] += 1
        agg["total_commission"] += float(line.commission_amount)

    row_idx = 2
    grand_total = 0.0
    for agg in sorted(by_dtl.values(), key=lambda a: a["dtl"].dtl_name):
        dtl = agg["dtl"]
        values = [
            dtl.dtl_code, dtl.dtl_name, len(agg["dsas"]), agg["nl"], agg["rf"],
            agg["nl"] + agg["rf"], round(agg["total_commission"], 2),
        ]
        for col, v in enumerate(values, start=1):
            ws.cell(row=row_idx, column=col, value=v)
        grand_total += agg["total_commission"]
        row_idx += 1

    ws.cell(row=row_idx, column=6, value="TOTAL").font = TOTAL_FONT
    ws.cell(row=row_idx, column=7, value=round(grand_total, 2)).font = TOTAL_FONT
    for col in range(1, len(headers) + 1):
        ws.cell(row=row_idx, column=col).fill = TOTAL_FILL

    _autosize(ws, headers)


EXCEPTION_CATEGORY_LABELS = {
    MatchStatus.UNMATCHED_IN_BUSINESS_FILE: "Unmatched - in Branch Manager file only (no Business Manager transaction)",
    MatchStatus.UNMATCHED_IN_BRANCH_FILE: "Unmatched - in Business Manager file only (no DSA/DTL attribution)",
    MatchStatus.DUPLICATE: "Duplicate - multiple Business Manager candidates for one Branch Manager row",
    MatchStatus.MATCHED_WITH_WARNING: "Matched with warning - secondary check (CLIENT_CHECK_NO vs EMPLOYEE_NO) failed",
}


def add_exceptions_sheet(wb: Workbook, db: Session, period: str, branch_id: int | None, include_matched_with_warning: bool = True) -> None:
    ws = wb.create_sheet("Exceptions")
    headers = [
        "Category", "Branch", "Client Name", "Client Account No (Branch)",
        "Client Account No (Business)", "DSA Code", "DSA Name", "Loan Type",
        "Disbursement Date", "Reported Amount", "Disbursement Amt", "Notes",
    ]
    _write_header(ws, headers)

    statuses = [MatchStatus.UNMATCHED_IN_BUSINESS_FILE, MatchStatus.UNMATCHED_IN_BRANCH_FILE, MatchStatus.DUPLICATE]
    if include_matched_with_warning:
        statuses.append(MatchStatus.MATCHED_WITH_WARNING)

    q = db.query(MatchedTransaction).filter(MatchedTransaction.match_status.in_(statuses))
    # Exceptions aren't all tied to a resolved commission_period (e.g.
    # UNMATCHED_IN_BUSINESS_FILE has none), so scope by period OR by branch
    # via whichever side of the match is present.
    rows = q.all()

    row_idx = 2
    for mt in rows:
        bs = mt.branch_sale
        bt = mt.business_transaction

        if branch_id is not None:
            row_branch_id = bs.branch_id if bs else None
            if row_branch_id != branch_id:
                continue
        if period is not None:
            row_period = mt.commission_period or (bs.loan_date.strftime("%Y-%m") if bs and bs.loan_date else None)
            if row_period != period:
                continue

        values = [
            EXCEPTION_CATEGORY_LABELS.get(mt.match_status, mt.match_status.value),
            bs.branch.name if bs and bs.branch else "",
            bs.client_name if bs else (f"(business txn only, acct {bt.client_disb_ext_account_no})" if bt else ""),
            bs.client_account_no if bs else "",
            bt.client_disb_ext_account_no if bt else "",
            bs.dsa_code if bs else "",
            bs.dsa_name if bs else "",
            bt.loan_type.value if bt else "",
            bt.disbursement_date.isoformat() if bt else "",
            float(bs.reported_amount) if bs and bs.reported_amount is not None else "",
            float(bt.disbursement_amt) if bt and bt.disbursement_amt is not None else "",
            mt.match_notes or "",
        ]
        for col, v in enumerate(values, start=1):
            ws.cell(row=row_idx, column=col, value=v)
        row_idx += 1

    _autosize(ws, headers)


def generate_commission_report(db: Session, run: CommissionRun, branch_id: int | None = None) -> io.BytesIO:
    """Full 4-sheet workbook for a commission run, optionally filtered to one branch."""
    wb = Workbook()
    _add_transaction_detail_sheet(wb, db, run, branch_id)
    _add_dsa_summary_sheet(wb, db, run, branch_id)
    _add_dtl_summary_sheet(wb, db, run, branch_id)
    add_exceptions_sheet(wb, db, run.period, branch_id)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def generate_exceptions_only_report(db: Session, period: str, branch_id: int | None = None) -> io.BytesIO:
    """Standalone exceptions workbook - usable before any commission run exists,
    so exceptions can be reviewed and resolved before a run is locked."""
    wb = Workbook()
    wb.remove(wb.active)
    add_exceptions_sheet(wb, db, period, branch_id)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
