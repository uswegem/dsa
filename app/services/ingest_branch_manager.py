"""
Ingestion of the Branch Manager upload (roster/attribution file).

The only source of DSA/DTL identity in the system. Defends against the
known real-world quirks:
  - trailing fully-blank rows at the end of the sheet
  - inconsistent header whitespace ("DSA  CODE   ")
  - CLIENT_CHECK_NO mixing numeric and alphanumeric values -> always text
  - stray dates outside the batch's dominant month -> warning, not silent accept
"""
import collections
import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from app.services.header_utils import coerce_date_flexible, display_header, header_key, is_blank

# canonical field -> aggressive header key(s) it may appear as
EXPECTED_COLUMNS: dict[str, list[str]] = {
    "loan_date": ["DATE"],
    "client_name": ["CLIENTNAME"],
    "client_check_no": ["CLIENT_CHECK_NO", "CLIENTCHECKNO"],
    "client_account_no": ["CLIENT_ACCOUNT_NO", "CLIENTACCOUNTNO"],
    "application_number_ess": ["APPLICATIONNUMBER/ESS", "APPLICATIONNUMBERESS"],
    "reported_amount": ["REPORTED_AMOUNT", "REPORTEDAMOUNT"],
    "branch": ["BRANCH"],
    "dsa_code": ["DSA_CODE", "DSACODE"],
    "dsa_account_no": ["DSA_ACCOUNT_NO", "DSAACCOUNTNO"],
    "dsa_name": ["DSA_NAME", "DSANAME"],
    "dtl_name": ["DTL_NAME", "DTLNAME"],
    "dtl_code": ["DTL_CODE", "DTLCODE"],
}
REQUIRED_FIELDS = ["client_account_no", "client_check_no", "dsa_code", "dsa_name"]


@dataclass
class IngestIssue:
    row_number: int  # 1-based, matches the source spreadsheet (including header offset)
    severity: str  # "ERROR" | "WARNING"
    message: str
    column_name: str | None = None


@dataclass
class ParsedBranchRow:
    row_number: int
    loan_date: dt.date | None
    client_name: str
    client_check_no: str
    client_account_no: str
    application_number_ess: str | None
    reported_amount: float | None
    branch_raw: str | None
    dsa_code: str
    dsa_account_no: str | None
    dsa_name: str
    dtl_name: str | None
    dtl_code: str | None
    date_out_of_period_warning: bool = False


@dataclass
class BranchManagerIngestResult:
    rows: list[ParsedBranchRow] = field(default_factory=list)
    issues: list[IngestIssue] = field(default_factory=list)
    total_data_rows_seen: int = 0


def _resolve_columns(header_row: list) -> dict[str, int]:
    """Map canonical field name -> column index, tolerating header whitespace noise."""
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
            # fallback: startswith match, for headers with trailing notes
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
            "Branch Manager file is missing expected columns: "
            + ", ".join(missing)
            + f". Headers found: {[display_header(h) for h in header_row]}"
        )
    return resolved


def _coerce_text(value) -> str | None:
    """Always ingest as text - defends against pandas silently turning
    "871" into 871.0 while leaving "NCAA1680" as a string in the same column.
    """
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


def parse_branch_manager_file(file_path: str) -> BranchManagerIngestResult:
    df = pd.read_excel(file_path, header=0, dtype=object)
    header_row = list(df.columns)
    columns = _resolve_columns(header_row)

    result = BranchManagerIngestResult()
    parsed_dates: list[dt.date] = []
    pending_rows: list[dict] = []

    for i, raw_row in enumerate(df.itertuples(index=False, name=None)):
        row_number = i + 2  # +1 for 1-based, +1 for header row occupying row 1
        result.total_data_rows_seen += 1

        # Filter out rows that are entirely empty.
        if all(is_blank(v) for v in raw_row):
            continue

        def get(field_name):
            return raw_row[columns[field_name]]

        row_errors: list[IngestIssue] = []

        client_name = _coerce_text(get("client_name"))
        client_check_no = _coerce_text(get("client_check_no"))
        client_account_no = _coerce_text(get("client_account_no"))
        dsa_code = _coerce_text(get("dsa_code"))
        dsa_name = _coerce_text(get("dsa_name"))

        if client_account_no is None:
            row_errors.append(IngestIssue(row_number, "ERROR", "CLIENT_ACCOUNT_NO is blank", "CLIENT_ACCOUNT_NO"))
        if client_check_no is None:
            row_errors.append(IngestIssue(row_number, "ERROR", "CLIENT_CHECK_NO is blank", "CLIENT_CHECK_NO"))
        if dsa_code is None:
            row_errors.append(IngestIssue(row_number, "ERROR", "DSA_CODE is blank", "DSA_CODE"))
        if dsa_name is None:
            row_errors.append(IngestIssue(row_number, "ERROR", "DSA_NAME is blank", "DSA_NAME"))

        if row_errors:
            result.issues.extend(row_errors)
            continue

        loan_date = _coerce_date(get("loan_date"))
        if loan_date is not None:
            parsed_dates.append(loan_date)

        pending_rows.append(
            dict(
                row_number=row_number,
                loan_date=loan_date,
                client_name=client_name or "",
                client_check_no=client_check_no,
                client_account_no=client_account_no,
                application_number_ess=_coerce_text(get("application_number_ess")),
                reported_amount=_coerce_amount(get("reported_amount")),
                branch_raw=_coerce_text(get("branch")),
                dsa_code=dsa_code,
                dsa_account_no=_coerce_text(get("dsa_account_no")),
                dsa_name=dsa_name,
                dtl_name=_coerce_text(get("dtl_name")),
                dtl_code=_coerce_text(get("dtl_code")),
            )
        )

    # Flag dates outside the batch's dominant (year, month) - e.g. a stray
    # 13.01.2026 among a batch of August dates - as a warning, not silently
    # accepted. With no dates at all there's nothing to compare against.
    dominant_ym = None
    if parsed_dates:
        counts = collections.Counter((d.year, d.month) for d in parsed_dates)
        dominant_ym = counts.most_common(1)[0][0]

    for row in pending_rows:
        warning = False
        if dominant_ym is not None and row["loan_date"] is not None:
            ym = (row["loan_date"].year, row["loan_date"].month)
            if ym != dominant_ym:
                warning = True
                result.issues.append(
                    IngestIssue(
                        row["row_number"],
                        "WARNING",
                        f"DATE {row['loan_date'].isoformat()} falls outside the batch's dominant reporting month "
                        f"({dominant_ym[0]}-{dominant_ym[1]:02d}); informational field only, row still ingested.",
                        "DATE",
                    )
                )
        result.rows.append(ParsedBranchRow(date_out_of_period_warning=warning, **row))

    return result
