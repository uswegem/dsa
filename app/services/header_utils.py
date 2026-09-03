"""
Shared header-normalization and value-coercion helpers.

Real-world exports have inconsistent whitespace in headers (e.g.
"DSA  CODE   "). We match headers by an aggressive normalized key (all
whitespace stripped, uppercased) so layout noise doesn't break ingestion,
while keeping the original header text around for error messages.
"""
import datetime as dt
import re


def display_header(raw) -> str:
    """Trim + collapse internal whitespace, keep readable for logging."""
    if raw is None:
        return ""
    s = str(raw).strip()
    return re.sub(r"\s+", " ", s)


def header_key(raw) -> str:
    """Aggressive key used for matching: uppercase, all whitespace removed."""
    return re.sub(r"\s+", "", display_header(raw).upper())


def is_blank(value) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


_ISO_DATE_PREFIX = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}")


def coerce_date_flexible(value) -> "dt.date | None":
    """Parses a date cell that may be an Excel date object or free text.

    Real-world roster/report dates are typically day-first (e.g.
    "13.01.2026"), so free text is parsed with dayfirst=True - EXCEPT
    unambiguous ISO "YYYY-MM-DD" text, which is parsed year-first regardless
    of dayfirst (pandas' per-value dayfirst heuristic can otherwise
    misinterpret "2026-08-02" as day=08/month=02).
    """
    import pandas as pd

    if is_blank(value):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    dayfirst = not _ISO_DATE_PREFIX.match(text)
    try:
        parsed = pd.to_datetime(text, dayfirst=dayfirst, errors="coerce")
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed.date()
