"""
Ingestion of the Business Manager upload ("Payout Report by Branch" system export).

Every upload is tagged with an explicit period (month/year) chosen by the
uploader. Disbursement date is validated against that selected period per
row - a row whose date falls outside it, or is missing/unparseable, is a
validation ERROR and is excluded from ingestion.

Defends against the other known real-world quirks:
  - 4 rows of report metadata before the real header row -> detect it
  - LOANTYPE values are 'NL : New' / 'RF : Topup' -> match by prefix
  - string fields padded with trailing whitespace -> strip on ingestion
"""
import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from app.services.header_utils import coerce_date_flexible, display_header, header_key, is_blank
from app.services.ingest_branch_manager import IngestIssue  # reuse the same issue shape

# canonical field -> aggressive header key(s) it may appear as
EXPECTED_COLUMNS: dict[str, list[str]] = {
    "branch": ["BRANCH"],
    "employee_no": ["EMPLOYEE_NO", "EMPLOYEENO"],
    "customer_no": ["CUSTOMER_NO", "CUSTOMERNO"],
    "account_no": ["ACCOUNTNO", "ACCOUNT_NO"],
    "loan_type": ["LOANTYPE"],
    "disbursement_date": ["DISBURSEMENTDATE"],
    "disbursement_amt": ["DISBURSEMENTAMT"],
    "payout_to_client": ["PAYOUTTOCLIENT"],
    "letshego_topup": ["LETSHEGOTOPUP"],
    "appl_amount": ["APPLAMOUNT"],
    "client_disb_ext_account_no": ["CLIENT_DISB_EXT_ACCOUNT_NO", "CLIENTDISBEXTACCOUNTNO"],
}
REQUIRED_FIELDS = ["client_disb_ext_account_no", "loan_type", "disbursement_date"]

HEADER_ROW_MARKERS = {"BR_NO", "BRANCH"}
MIN_POPULATED_CELLS_IN_DATA_ROW = 10  # "many populated columns" heuristic


@dataclass
class ParsedBusinessRow:
    row_number: int
    branch_raw: str | None
    employee_no: str | None
    customer_no: str | None
    account_no: str | None
    loan_type: str  # "NL" | "RF"
    disbursement_date: dt.date
    disbursement_amt: float | None
    payout_to_client: float | None
    letshego_topup: float | None
    appl_amount: float | None
    client_disb_ext_account_no: str


@dataclass
class BusinessManagerIngestResult:
    rows: list[ParsedBusinessRow] = field(default_factory=list)
    issues: list[IngestIssue] = field(default_factory=list)
    total_data_rows_seen: int = 0
    header_row_index: int | None = None  # 0-based, within the raw sheet


def _find_header_row(raw: pd.DataFrame) -> int:
    """First row where a cell reads Br_no/Branch, and the following row has
    many populated columns (i.e. it's really a header, not a stray mention
    of the word in the report-metadata block above it)."""
    n_rows, n_cols = raw.shape
    for i in range(n_rows - 1):
        row_vals = [header_key(v) for v in raw.iloc[i].tolist()]
        if any(v in HEADER_ROW_MARKERS for v in row_vals):
            next_row = raw.iloc[i + 1]
            populated = sum(0 if is_blank(v) else 1 for v in next_row.tolist())
            if populated >= min(MIN_POPULATED_CELLS_IN_DATA_ROW, n_cols):
                return i
    raise ValueError(
        "Could not locate the Business Manager header row (looked for a cell "
        "reading 'Br_no' or 'Branch' followed by a densely-populated data row)."
    )


def _coerce_text(value) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


_coerce_date = coerce_date_flexible


def _coerce_amount(value) -> float | None:
    if is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_loan_type(value) -> str | None:
    """LOANTYPE values are 'NL : New' / 'RF : Topup', not bare NL/RF -
    match by prefix, tolerant of whitespace/case."""
    if is_blank(value):
        return None
    text = str(value).strip().upper()
    if text.startswith("NL"):
        return "NL"
    if text.startswith("RF"):
        return "RF"
    return None


def _resolve_columns(header_row: list) -> dict[str, int]:
    keyed = {header_key(h): idx for idx, h in enumerate(header_row)}
    resolved: dict[str, int] = {}
    missing: list[str] = []
    for field_name, aliases in EXPECTED_COLUMNS.items():
        found_idx = None
        for alias in aliases:
            if alias in keyed:
                found_idx = keyed[alias]
                break
        if found_idx is None:
            for key, idx in keyed.items():
                if any(key.startswith(alias) for alias in aliases):
                    found_idx = idx
                    break
        if found_idx is None:
            missing.append(field_name)
        else:
            resolved[field_name] = found_idx
    if missing:
        raise ValueError(
            "Business Manager file is missing expected columns: "
            + ", ".join(missing)
            + f". Headers found: {[display_header(h) for h in header_row]}"
        )
    return resolved


def parse_business_manager_file(file_path: str, period_month: int, period_year: int) -> BusinessManagerIngestResult:
    raw = pd.read_excel(file_path, header=None, dtype=object)
    header_idx = _find_header_row(raw)

    header_row = raw.iloc[header_idx].tolist()
    columns = _resolve_columns(header_row)
    data = raw.iloc[header_idx + 1 :].reset_index(drop=True)

    result = BusinessManagerIngestResult(header_row_index=header_idx)

    for i, raw_row in enumerate(data.itertuples(index=False, name=None)):
        row_number = header_idx + 2 + i + 1  # 1-based sheet row number of this data row
        result.total_data_rows_seen += 1

        if all(is_blank(v) for v in raw_row):
            continue

        def get(field_name):
            return raw_row[columns[field_name]]

        row_errors: list[IngestIssue] = []

        client_disb_ext_account_no = _coerce_text(get("client_disb_ext_account_no"))
        loan_type = _parse_loan_type(get("loan_type"))
        disbursement_date = _coerce_date(get("disbursement_date"))

        if client_disb_ext_account_no is None:
            row_errors.append(
                IngestIssue(row_number, "ERROR", "CLIENT_DISB_EXT_ACCOUNT_NO is blank", "CLIENT_DISB_EXT_ACCOUNT_NO")
            )
        if loan_type is None:
            row_errors.append(
                IngestIssue(
                    row_number,
                    "ERROR",
                    f"Unrecognized LOANTYPE value: {get('loan_type')!r} (expected to start with 'NL' or 'RF')",
                    "LOANTYPE",
                )
            )
        if disbursement_date is None:
            row_errors.append(IngestIssue(row_number, "ERROR", "Disbursement date is blank or unparseable", "Disbursement date"))
        elif (disbursement_date.year, disbursement_date.month) != (period_year, period_month):
            row_errors.append(
                IngestIssue(
                    row_number, "ERROR",
                    f"Disbursement date {disbursement_date.isoformat()} falls outside the selected period "
                    f"{period_year}-{period_month:02d} - row excluded. Re-submit it in an upload for the correct period.",
                    "Disbursement date",
                )
            )

        if row_errors:
            result.issues.extend(row_errors)
            continue

        result.rows.append(
            ParsedBusinessRow(
                row_number=row_number,
                branch_raw=_coerce_text(get("branch")),
                employee_no=_coerce_text(get("employee_no")),
                customer_no=_coerce_text(get("customer_no")),
                account_no=_coerce_text(get("account_no")),
                loan_type=loan_type,
                disbursement_date=disbursement_date,
                disbursement_amt=_coerce_amount(get("disbursement_amt")),
                payout_to_client=_coerce_amount(get("payout_to_client")),
                letshego_topup=_coerce_amount(get("letshego_topup")),
                appl_amount=_coerce_amount(get("appl_amount")),
                client_disb_ext_account_no=client_disb_ext_account_no,
            )
        )

    return result
