"""
Excel report generation (openpyxl).

Four report types:
  - Transaction Detail: every matched transaction, base used, rate, DSA/DTL commission, totals row
  - DSA Summary: one row per DSA - deal counts by type, total commission
  - DTL Summary: one row per DTL - DSAs supervised, deal counts, total commission
  - Exceptions: unmatched / match-quality-warning rows, separated by category

Branch-scoped exports filter everything to one branch; org-wide exports
(Business Manager) include all branches, with a Branch column for context.

Every sheet starts with a 2-row banner: the period covered and the
generation timestamp, then a status line - a period's data is "current, so
far" until its run is finalized (REVIEWED/LOCKED/PAID), so a report
generated against a DRAFT run is visibly marked as in-progress rather than
implying it's complete.
"""
import datetime as dt
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    BranchSale,
    BusinessTransaction,
    CommissionAdjustment,
    CommissionLine,
    CommissionRun,
    Dsa,
    Dtl,
    MatchedTransaction,
)
from app.models.enums import LoanType, MatchStatus, PayeeType, RunStatus
from app.services.exceptions import EXCEPTION_CATEGORY_LABELS, find_exceptions

settings = get_settings()

SDL_WCF_FOOTNOTE = "SDL and WCF are statutory reporting figures only - not deducted from the DSA's payout."

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TOTAL_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
TOTAL_FONT = Font(bold=True)
IN_PROGRESS_FILL = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
FINALIZED_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
CURRENCY_FORMAT = "#,##0.00"

BANNER_ROWS = 3  # 1: period/generated-at, 2: status note, 3: blank spacer
HEADER_ROW = BANNER_ROWS + 1
DATA_START_ROW = HEADER_ROW + 1

_FINALIZED_STATUSES = (RunStatus.LOCKED, RunStatus.PAID)


def _write_meta_banner(ws, num_cols: int, period: str, status: RunStatus | None) -> None:
    generated_at = dt.datetime.now(dt.timezone.utc)
    num_cols = max(num_cols, 1)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=num_cols)
    title_cell = ws.cell(row=1, column=1, value=f"Period: {period}    |    Generated: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    title_cell.font = Font(bold=True, size=11)

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=num_cols)
    if status is None:
        note = "Reflects data received to date across all uploads for this period - not tied to a specific commission run."
        fill = IN_PROGRESS_FILL
        font_color = "9C4500"
    elif status in _FINALIZED_STATUSES:
        note = f"Status: {status.value} — finalized."
        fill = FINALIZED_FILL
        font_color = "006100"
    else:
        note = f"Status: {status.value} — reflects data received so far. NOT finalized; numbers may still change as more uploads arrive."
        fill = IN_PROGRESS_FILL
        font_color = "9C4500"
    note_cell = ws.cell(row=2, column=1, value=note)
    note_cell.font = Font(bold=True, color=font_color)
    for col in range(1, num_cols + 1):
        ws.cell(row=2, column=col).fill = fill


def _write_header(ws, headers: list[str], row: int = HEADER_ROW) -> None:
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
    _write_meta_banner(ws, len(headers), run.period, run.status)
    _write_header(ws, headers)

    lines = _commission_lines_query(db, run, branch_id).order_by(CommissionLine.matched_transaction_id).all()

    row_idx = DATA_START_ROW
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
            cell = ws.cell(row=row_idx, column=col, value=v)
            if col in (11, 14):  # Base Amount, Commission Amount
                cell.number_format = CURRENCY_FORMAT
        total += float(line.commission_amount)
        row_idx += 1

    total_row = row_idx
    ws.cell(row=total_row, column=13, value="TOTAL").font = TOTAL_FONT
    total_cell = ws.cell(row=total_row, column=14, value=round(total, 2))
    total_cell.font = TOTAL_FONT
    total_cell.number_format = CURRENCY_FORMAT
    for col in range(1, len(headers) + 1):
        ws.cell(row=total_row, column=col).fill = TOTAL_FILL

    _autosize(ws, headers)


def aggregate_dsa_summary(lines: list[CommissionLine]) -> dict[int, dict]:
    """Pure aggregation, kept separate from sheet-writing so it's directly
    unit-testable: New Loans Amount / Topup Loans Amount are summed from
    the exact same CommissionLine.base_amount values used to produce
    total_commission (the gross figure), so `nl_amount * dsa_nl_rate +
    rf_amount * dsa_rf_rate == total_commission` always holds by
    construction - see tests/test_report_aggregation.py.

    wht_amount/net_salary are likewise summed straight from each line's
    wht_amount/net_commission_amount (set at calc time - see
    app/services/commission.py), so total_commission - wht_amount ==
    net_salary holds the same way.

    lines: CommissionLine rows for payee_type == DSA.
    Returns {dsa_id: {"dsa", "branch_name", "nl_amount", "rf_amount",
    "total_commission" (gross), "wht_amount", "net_salary"}}.
    """
    by_dsa: dict[int, dict] = {}
    for line in lines:
        dsa = line.dsa
        agg = by_dsa.setdefault(
            dsa.id,
            {
                "dsa": dsa, "branch_name": dsa.branch.name if dsa.branch else "",
                "nl_amount": 0.0, "rf_amount": 0.0,
                "total_commission": 0.0, "wht_amount": 0.0, "net_salary": 0.0,
            },
        )
        if line.loan_type == LoanType.NL:
            agg["nl_amount"] += float(line.base_amount)
        else:
            agg["rf_amount"] += float(line.base_amount)
        agg["total_commission"] += float(line.commission_amount)
        agg["wht_amount"] += float(line.wht_amount or 0.0)
        agg["net_salary"] += float(line.net_commission_amount or 0.0)
    return by_dsa


def aggregate_dtl_summary(lines: list[CommissionLine]) -> dict[int, dict]:
    """Same contract as aggregate_dsa_summary, for payee_type == DTL lines.
    Returns {dtl_id: {"dtl", "branch_name", "dsas", "nl_amount", "rf_amount", "total_commission"}}.
    """
    by_dtl: dict[int, dict] = {}
    for line in lines:
        dtl = line.dtl
        agg = by_dtl.setdefault(
            dtl.id,
            {"dtl": dtl, "branch_name": dtl.branch.name if dtl.branch else "", "dsas": set(), "nl_amount": 0.0, "rf_amount": 0.0, "total_commission": 0.0},
        )
        agg["dsas"].add(line.matched_transaction.branch_sale.dsa_code)
        if line.loan_type == LoanType.NL:
            agg["nl_amount"] += float(line.base_amount)
        else:
            agg["rf_amount"] += float(line.base_amount)
        agg["total_commission"] += float(line.commission_amount)
    return by_dtl


def _dsa_adjustment_totals(db: Session, run: CommissionRun) -> dict[int, float]:
    """Manual commission_adjustments (see app/api/commission.py::create_adjustment)
    already applied to this specific run, summed per DSA. amount is signed
    (negative = clawback). Used only to derive the SDL/WCF basis below - see
    Settings.dsa_sdl_rate/dsa_wcf_rate docstring for why this run-scoped
    default was chosen (no automatic drop/clawback-from-transactions
    mechanism exists yet, only this manual one)."""
    totals: dict[int, float] = {}
    rows = (
        db.query(CommissionAdjustment)
        .filter(CommissionAdjustment.commission_run_id == run.id, CommissionAdjustment.payee_type == PayeeType.DSA, CommissionAdjustment.dsa_id.isnot(None))
        .all()
    )
    for adj in rows:
        totals[adj.dsa_id] = totals.get(adj.dsa_id, 0.0) + float(adj.amount)
    return totals


def _add_dsa_summary_sheet(wb: Workbook, db: Session, run: CommissionRun, branch_id: int | None) -> None:
    ws = wb.create_sheet("DSA Summary")
    headers = [
        "DSA Code", "DSA Name", "Branch", "DSA Bank Account",
        "New Loans Amount", "Topup Loans Amount",
        "Commission Total (Gross)", "WHT (5%)", "Net Salary",
        "SDL (informational only)", "WCF (informational only)",
    ]
    _write_meta_banner(ws, len(headers), run.period, run.status)
    _write_header(ws, headers)

    lines = _commission_lines_query(db, run, branch_id).filter(CommissionLine.payee_type == PayeeType.DSA).all()
    by_dsa = aggregate_dsa_summary(lines)
    adjustment_totals = _dsa_adjustment_totals(db, run)

    amount_cols = (
        (5, "nl_amount"), (6, "rf_amount"), (7, "total_commission"),
        (8, "wht_amount"), (9, "net_salary"), (10, "sdl"), (11, "wcf"),
    )

    row_idx = DATA_START_ROW
    totals = {key: 0.0 for _, key in amount_cols}
    for agg in sorted(by_dsa.values(), key=lambda a: a["dsa"].dsa_name):
        dsa = agg["dsa"]
        # SDL/WCF basis = Net Salary (post-WHT), plus any manual adjustment
        # already applied to this DSA on this run - never the gross figure.
        total_amount = agg["net_salary"] + adjustment_totals.get(dsa.id, 0.0)
        agg["sdl"] = round(total_amount * settings.dsa_sdl_rate, 2)
        agg["wcf"] = round(total_amount * settings.dsa_wcf_rate, 2)

        row = [dsa.dsa_code, dsa.dsa_name, agg["branch_name"], dsa.dsa_account_no or "Not set"]
        for col, v in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col, value=v)
        for col, key in amount_cols:
            cell = ws.cell(row=row_idx, column=col, value=round(agg[key], 2))
            cell.number_format = CURRENCY_FORMAT
            totals[key] += agg[key]
        row_idx += 1

    ws.cell(row=row_idx, column=4, value="TOTAL").font = TOTAL_FONT
    for col, key in amount_cols:
        cell = ws.cell(row=row_idx, column=col, value=round(totals[key], 2))
        cell.font = TOTAL_FONT
        cell.number_format = CURRENCY_FORMAT
    for col in range(1, len(headers) + 1):
        ws.cell(row=row_idx, column=col).fill = TOTAL_FILL
    row_idx += 1

    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=len(headers))
    footnote_cell = ws.cell(row=row_idx, column=1, value=SDL_WCF_FOOTNOTE)
    footnote_cell.font = Font(italic=True, color="7A756A")

    _autosize(ws, headers)


def _add_dtl_summary_sheet(wb: Workbook, db: Session, run: CommissionRun, branch_id: int | None) -> None:
    ws = wb.create_sheet("DTL Summary")
    headers = ["DTL Name", "Branch", "DSAs Supervised", "DTL Bank Account", "New Loans Amount", "Topup Loans Amount", "Total Commission"]
    _write_meta_banner(ws, len(headers), run.period, run.status)
    _write_header(ws, headers)

    lines = _commission_lines_query(db, run, branch_id).filter(CommissionLine.payee_type == PayeeType.DTL).all()
    by_dtl = aggregate_dtl_summary(lines)

    row_idx = DATA_START_ROW
    totals = {"nl_amount": 0.0, "rf_amount": 0.0, "total_commission": 0.0}
    for agg in sorted(by_dtl.values(), key=lambda a: a["dtl"].dtl_name):
        dtl = agg["dtl"]
        row = [dtl.dtl_name, agg["branch_name"], len(agg["dsas"]), dtl.dtl_account_no or "Not set"]
        for col, v in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col, value=v)
        for col, key in ((5, "nl_amount"), (6, "rf_amount"), (7, "total_commission")):
            cell = ws.cell(row=row_idx, column=col, value=round(agg[key], 2))
            cell.number_format = CURRENCY_FORMAT
            totals[key] += agg[key]
        row_idx += 1

    ws.cell(row=row_idx, column=4, value="TOTAL").font = TOTAL_FONT
    for col, key in ((5, "nl_amount"), (6, "rf_amount"), (7, "total_commission")):
        cell = ws.cell(row=row_idx, column=col, value=round(totals[key], 2))
        cell.font = TOTAL_FONT
        cell.number_format = CURRENCY_FORMAT
    for col in range(1, len(headers) + 1):
        ws.cell(row=row_idx, column=col).fill = TOTAL_FILL

    _autosize(ws, headers)


def add_exceptions_sheet(
    wb: Workbook, db: Session, period: str, branch_id: int | None,
    include_matched_with_warning: bool = True, run: CommissionRun | None = None,
) -> None:
    ws = wb.create_sheet("Exceptions")
    headers = [
        "Category", "Branch", "Client Name", "Client Account No (Branch)",
        "Client Account No (Business)", "DSA Code", "DSA Name", "Loan Type",
        "Disbursement Date", "Reported Amount", "Disbursement Amt", "Notes",
    ]
    _write_meta_banner(ws, len(headers), period, run.status if run else None)
    _write_header(ws, headers)

    entries = find_exceptions(db)
    if not include_matched_with_warning:
        entries = [e for e in entries if e.category != MatchStatus.MATCHED_WITH_WARNING.value]

    row_idx = DATA_START_ROW
    for entry in entries:
        mt = entry.matched_transaction
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
            EXCEPTION_CATEGORY_LABELS.get(entry.category, entry.category),
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
            entry.note or "",
        ]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col, value=v)
            if col in (10, 11):  # Reported Amount, Disbursement Amt
                cell.number_format = CURRENCY_FORMAT
        row_idx += 1

    _autosize(ws, headers)


def generate_commission_report(db: Session, run: CommissionRun, branch_id: int | None = None) -> io.BytesIO:
    """Full 4-sheet workbook for a commission run, optionally filtered to one branch."""
    wb = Workbook()
    _add_transaction_detail_sheet(wb, db, run, branch_id)
    _add_dsa_summary_sheet(wb, db, run, branch_id)
    _add_dtl_summary_sheet(wb, db, run, branch_id)
    add_exceptions_sheet(wb, db, run.period, branch_id, run=run)

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
