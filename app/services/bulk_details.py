"""
Generic "bulk update" for DSA/DTL detail-correction files (Admin -> DSAs /
DTLs -> Bulk Update).

This is a correction path, not an onboarding one: it never creates a new
DSA/DTL record. Each row is matched to an EXISTING record by (name, branch)
- case-insensitive and whitespace-trimmed, since real exports mix casing
across branch names (e.g. "RUVUMA" vs "Ruvuma") and that must never be
treated as a different branch/DTL. A row that doesn't match an existing
record by name+branch is reported back as UNMATCHED rather than silently
creating one - it's an admin decision (new record? typo? branch mismatch?),
not something this parser should guess.

Shared by both entity kinds (see BULK_UPDATE_SPECS) so the same matching/
sanitization logic doesn't drift between the two - only the column aliases
and the model fields touched differ.
"""
import io
import re
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from app.services.audit import log_action
from app.services.header_utils import header_key, is_blank

# Characters that show up as copy-paste artifacts around an otherwise-clean
# numeric-looking field (a stray tab, straight/curly quotes) - stripped
# before validation so a pasted "\t21710145716\"" doesn't need manual
# cleanup before upload. Never touches the digits themselves.
_JUNK_CHARS = "\t\n\r\"'‘’“”"
_JUNK_TRANSLATION = str.maketrans("", "", _JUNK_CHARS)


@dataclass(frozen=True)
class BulkUpdateSpec:
    entity_label: str  # "DTL" | "DSA" - used in aliases and messages
    name_aliases: list[str]
    code_aliases: list[str]
    account_aliases: list[str]


BULK_UPDATE_SPECS: dict[str, BulkUpdateSpec] = {
    "dtl": BulkUpdateSpec("DTL", ["DTL_NAME", "DTLNAME"], ["DTL_CODE", "DTLCODE"], ["DTL_ACCOUNT_NO", "DTLACCOUNTNO"]),
    "dsa": BulkUpdateSpec("DSA", ["DSA_NAME", "DSANAME"], ["DSA_CODE", "DSACODE"], ["DSA_ACCOUNT_NO", "DSAACCOUNTNO"]),
}
BRANCH_ALIASES = ["BRANCH"]


@dataclass
class BulkDetailRow:
    row_number: int  # 1-based, matches the source file (header = row 1)
    name: str
    branch_raw: str
    code: str | None
    account_no: str | None


@dataclass
class ParsedBulkDetailFile:
    rows: list[BulkDetailRow] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)  # row-level parse problems (blank name/branch) - never block the rest of the file


def sanitize_numeric_like(value) -> tuple[str | None, bool]:
    """Strips known copy-paste junk from a numeric-looking field, then
    trims. Returns (cleaned_value, looked_malformed) - looked_malformed is
    True if junk characters had to be removed, purely for surfacing in the
    upload summary (the cleaned value is still used either way)."""
    if is_blank(value):
        return None, False
    text = str(value)
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    cleaned = text.translate(_JUNK_TRANSLATION).strip()
    return (cleaned or None), (cleaned != text.strip())


def normalize_match_key(value) -> str:
    """case-insensitive, whitespace-trimmed - the exact rule the matching
    logic is required to use (see module docstring)."""
    if value is None:
        return ""
    return str(value).strip().lower()


def _resolve_column(keyed: dict[str, int], aliases: list[str]) -> int | None:
    for alias in aliases:
        if alias in keyed:
            return keyed[alias]
    for key, idx in keyed.items():
        if any(key.startswith(alias) for alias in aliases):
            return idx
    return None


def _read_dataframe(contents: bytes, filename: str) -> pd.DataFrame:
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    buf = io.BytesIO(contents)
    if ext == "csv":
        return pd.read_csv(buf, dtype=object)
    return pd.read_excel(buf, header=0, dtype=object)


def parse_bulk_detail_file(contents: bytes, filename: str, entity_kind: str) -> ParsedBulkDetailFile:
    spec = BULK_UPDATE_SPECS[entity_kind]
    df = _read_dataframe(contents, filename)
    if df.shape[1] == 0:
        raise ValueError("File has no columns.")

    keyed = {header_key(h): idx for idx, h in enumerate(df.columns)}
    name_idx = _resolve_column(keyed, spec.name_aliases)
    branch_idx = _resolve_column(keyed, BRANCH_ALIASES)
    code_idx = _resolve_column(keyed, spec.code_aliases)
    account_idx = _resolve_column(keyed, spec.account_aliases)

    missing = [
        label for label, idx in (
            (spec.name_aliases[0], name_idx), ("BRANCH", branch_idx),
            (spec.code_aliases[0], code_idx), (spec.account_aliases[0], account_idx),
        ) if idx is None
    ]
    if missing:
        raise ValueError(
            f"File is missing expected column(s): {missing}. Expected headers like "
            f"{spec.name_aliases[0]}, BRANCH, {spec.code_aliases[0]}, {spec.account_aliases[0]}."
        )

    result = ParsedBulkDetailFile()
    for i, raw_row in enumerate(df.itertuples(index=False, name=None)):
        row_number = i + 2  # +1 for 1-based, +1 for the header row
        if all(is_blank(v) for v in raw_row):
            continue

        # Outer-whitespace-trimmed only - deliberately NOT collapsed
        # (unlike display_header, used for spreadsheet *headers* elsewhere):
        # matching compares this against existing record names/branches
        # with the same trim-only rule (normalize_match_key), and real DTL
        # names in this data legitimately contain internal double spaces
        # (e.g. "Neema Jonas  Mussa") - collapsing here would silently
        # break a match that should succeed.
        name_raw, branch_raw_val = raw_row[name_idx], raw_row[branch_idx]
        name = None if is_blank(name_raw) else (str(name_raw).strip() or None)
        branch_raw = None if is_blank(branch_raw_val) else (str(branch_raw_val).strip() or None)
        code, _ = sanitize_numeric_like(raw_row[code_idx])
        account_no, _ = sanitize_numeric_like(raw_row[account_idx])

        if name is None:
            result.issues.append(f"Row {row_number}: {spec.name_aliases[0]} is blank - skipped.")
            continue
        if branch_raw is None:
            result.issues.append(f"Row {row_number} ({name}): BRANCH is blank - skipped.")
            continue

        result.rows.append(BulkDetailRow(row_number=row_number, name=name, branch_raw=branch_raw, code=code, account_no=account_no))

    return result


# ---------------------------------------------------------------------
# Matching + apply
# ---------------------------------------------------------------------

ACCOUNT_NO_PATTERN = re.compile(r"^\d+$")


@dataclass
class BulkUpdateRowOutcome:
    row_number: int
    name: str
    branch: str
    status: str  # "UPDATED" | "UNCHANGED" | "UNMATCHED" | "ERROR"
    message: str | None = None


@dataclass
class BulkUpdateSummary:
    total_rows: int = 0
    parse_issues: list[str] = field(default_factory=list)  # rows skipped before matching (blank name/branch)
    updated: list[BulkUpdateRowOutcome] = field(default_factory=list)
    unchanged: list[BulkUpdateRowOutcome] = field(default_factory=list)
    unmatched: list[BulkUpdateRowOutcome] = field(default_factory=list)
    errors: list[BulkUpdateRowOutcome] = field(default_factory=list)


def apply_bulk_update(
    db: Session,
    parsed: ParsedBulkDetailFile,
    *,
    model,
    name_field: str,
    code_field: str,
    account_field: str,
    entity_label: str,  # "DTL" | "DSA" - for messages
    entity_type_for_audit: str,  # "Dtl" | "Dsa" - matches log_action's entity_type elsewhere
    log_action_name: str,
    current_user_id: int,
) -> BulkUpdateSummary:
    """Matches each parsed row to an existing `model` record by
    (name_field, branch) - see normalize_match_key - and updates
    code_field/account_field on the match. Never creates a record. Flushes
    but does not commit - the caller commits, same as every other admin
    write in this app."""
    summary = BulkUpdateSummary(total_rows=len(parsed.rows), parse_issues=list(parsed.issues))

    records = db.query(model).options(joinedload(model.branch)).all()
    lookup: dict[tuple[str, str], object] = {}
    ambiguous: set[tuple[str, str]] = set()
    code_owner: dict[str, object] = {}
    for rec in records:
        key = (normalize_match_key(getattr(rec, name_field)), normalize_match_key(rec.branch.name if rec.branch else None))
        if key in ambiguous:
            continue
        if key in lookup:
            ambiguous.add(key)
            del lookup[key]
        else:
            lookup[key] = rec
        existing_code = getattr(rec, code_field)
        if existing_code:
            code_owner[existing_code] = rec

    for row in parsed.rows:
        key = (normalize_match_key(row.name), normalize_match_key(row.branch_raw))

        if key in ambiguous:
            summary.errors.append(BulkUpdateRowOutcome(
                row.row_number, row.name, row.branch_raw, "ERROR",
                f"Multiple existing {entity_label}s share this name+branch - resolve the duplicate manually before bulk-updating.",
            ))
            continue

        record = lookup.get(key)
        if record is None:
            summary.unmatched.append(BulkUpdateRowOutcome(
                row.row_number, row.name, row.branch_raw, "UNMATCHED",
                f"No existing {entity_label} matches this name + branch - not created (review: new record, typo, or branch mismatch?).",
            ))
            continue

        if row.account_no is not None and not ACCOUNT_NO_PATTERN.match(row.account_no):
            summary.errors.append(BulkUpdateRowOutcome(
                row.row_number, row.name, row.branch_raw, "ERROR",
                f"Malformed account number {row.account_no!r} (expected digits only) - row not applied.",
            ))
            continue

        if row.code is not None:
            conflicting = code_owner.get(row.code)
            if conflicting is not None and conflicting.id != record.id:
                summary.errors.append(BulkUpdateRowOutcome(
                    row.row_number, row.name, row.branch_raw, "ERROR",
                    f"Code {row.code!r} is already used by another {entity_label} - row not applied.",
                ))
                continue

        changes = {}
        if row.code is not None and row.code != getattr(record, code_field):
            changes[code_field] = {"old": getattr(record, code_field), "new": row.code}
            setattr(record, code_field, row.code)
            code_owner[row.code] = record
        if row.account_no is not None and row.account_no != getattr(record, account_field):
            changes[account_field] = {"old": getattr(record, account_field), "new": row.account_no}
            setattr(record, account_field, row.account_no)

        if changes:
            db.flush()
            log_action(db, current_user_id, log_action_name, entity_type_for_audit, record.id, changes=changes)
            summary.updated.append(BulkUpdateRowOutcome(row.row_number, row.name, row.branch_raw, "UPDATED"))
        else:
            summary.unchanged.append(BulkUpdateRowOutcome(row.row_number, row.name, row.branch_raw, "UNCHANGED"))

    return summary
