"""
Ingestion of the Branch Manager upload (roster/attribution file).

Every upload is tagged with an explicit period (month/year) chosen by the
uploader. The file's own DATE column is validated against that selected
period per row - a row whose date falls outside it, or is missing/
unparseable, is a validation ERROR and is excluded from ingestion (never
silently accepted or defaulted). This replaces any attempt to infer the
period from the file's own contents.

Defends against the other known real-world quirks:
  - trailing fully-blank rows at the end of the sheet
  - inconsistent header whitespace ("DSA  CODE   ")
  - CLIENT_CHECK_NO mixing numeric and alphanumeric values -> always text
  - real multi-branch exports have one sheet per branch (sheet name =
    branch name); a single-sheet upload is also supported
"""
import collections
import datetime as dt
from dataclasses import dataclass, field

import openpyxl
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


@dataclass
class IngestIssue:
    row_number: int  # 1-based, matches the source spreadsheet (including header offset); 0 for sheet/file-level issues
    severity: str  # "ERROR" | "WARNING"
    message: str
    column_name: str | None = None
    sheet_name: str | None = None


@dataclass
class ParsedBranchRow:
    row_number: int
    sheet_name: str  # source sheet - used to resolve the branch for this row
    loan_date: dt.date
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


@dataclass
class BranchManagerIngestResult:
    rows: list[ParsedBranchRow] = field(default_factory=list)
    issues: list[IngestIssue] = field(default_factory=list)
    total_data_rows_seen: int = 0
    sheet_names: list[str] = field(default_factory=list)


def _resolve_columns(header_row: list) -> dict[str, int] | None:
    """Map canonical field name -> column index, tolerating header whitespace
    noise. Returns None (rather than raising) if this doesn't look like a
    Branch Manager sheet at all, so multi-sheet workbooks can skip
    non-matching sheets instead of failing the whole upload."""
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
        return None
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


def _coerce_amount(value) -> float | None:
    if is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_sheet(
    sheet_name: str,
    df: pd.DataFrame,
    period_month: int,
    period_year: int,
    result: BranchManagerIngestResult,
) -> None:
    """row_number in every issue/row below is 1-based WITHIN this sheet
    (row 1 = header) - sheet_name disambiguates which sheet it came from,
    since Excel row numbers reset per sheet."""
    header_row = list(df.columns)
    columns = _resolve_columns(header_row)
    if columns is None:
        result.issues.append(
            IngestIssue(
                0, "WARNING",
                f"Sheet '{sheet_name}' does not look like a Branch Manager sheet (expected columns not found) - skipped.",
                sheet_name=sheet_name,
            )
        )
        return

    for i, raw_row in enumerate(df.itertuples(index=False, name=None)):
        row_number = i + 2  # +1 for 1-based, +1 for header row occupying row 1
        result.total_data_rows_seen += 1

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
            row_errors.append(IngestIssue(row_number, "ERROR", "CLIENT_ACCOUNT_NO is blank", "CLIENT_ACCOUNT_NO", sheet_name))
        if client_check_no is None:
            row_errors.append(IngestIssue(row_number, "ERROR", "CLIENT_CHECK_NO is blank", "CLIENT_CHECK_NO", sheet_name))
        if dsa_code is None:
            row_errors.append(IngestIssue(row_number, "ERROR", "DSA_CODE is blank", "DSA_CODE", sheet_name))
        if dsa_name is None:
            row_errors.append(IngestIssue(row_number, "ERROR", "DSA_NAME is blank", "DSA_NAME", sheet_name))

        loan_date = coerce_date_flexible(get("loan_date"))
        if loan_date is None:
            row_errors.append(
                IngestIssue(row_number, "ERROR", "DATE is missing or could not be parsed", "DATE", sheet_name)
            )
        elif (loan_date.year, loan_date.month) != (period_year, period_month):
            row_errors.append(
                IngestIssue(
                    row_number, "ERROR",
                    f"DATE {loan_date.isoformat()} falls outside the selected period {period_year}-{period_month:02d} "
                    f"- row excluded. Re-submit it in an upload for the correct period.",
                    "DATE", sheet_name,
                )
            )

        if row_errors:
            result.issues.extend(row_errors)
            continue

        result.rows.append(
            ParsedBranchRow(
                row_number=row_number,
                sheet_name=sheet_name,
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


def parse_branch_manager_file(file_path: str, period_month: int, period_year: int) -> BranchManagerIngestResult:
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    result = BranchManagerIngestResult(sheet_names=wb.sheetnames)
    wb.close()

    matched_any_sheet = False
    for sheet_name in result.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=0, dtype=object)
        if df.shape[1] == 0:
            continue
        before = len(result.issues)
        _parse_sheet(sheet_name, df, period_month, period_year, result)
        # a sheet "matched" if it didn't produce the "skipped" warning above
        if not (len(result.issues) > before and result.issues[before].message.endswith("- skipped.")):
            matched_any_sheet = True

    if not matched_any_sheet:
        raise ValueError(
            f"No sheet in this workbook looks like a Branch Manager sheet. Sheets found: {result.sheet_names}"
        )

    return result
