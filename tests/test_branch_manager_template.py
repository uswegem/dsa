"""
The Branch Manager upload template (served from frontend/static/templates/,
linked off the Uploads page) must always match what
app/services/ingest_branch_manager.py actually expects - this is the same
check scripts/generate_branch_manager_template.py runs on itself before
writing the file, kept here too so CI catches drift if EXPECTED_COLUMNS
ever changes without the template being regenerated.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from generate_branch_manager_template import COLUMNS, build_workbook  # noqa: E402

from app.services.ingest_branch_manager import EXPECTED_COLUMNS, parse_branch_manager_file


def test_template_headers_cover_every_expected_column():
    header_keys = {h for h, _note, _required in COLUMNS}
    assert len(COLUMNS) == len(EXPECTED_COLUMNS)
    assert len(header_keys) == len(COLUMNS)  # no accidental duplicate headers


def test_generated_template_parses_with_zero_rows_and_zero_issues(tmp_path):
    path = tmp_path / "template.xlsx"
    build_workbook().save(path)

    result = parse_branch_manager_file(str(path), period_month=1, period_year=2000)
    assert result.rows == []
    assert result.issues == []


def test_required_columns_match_the_parser_s_own_required_fields():
    # Mirrors ingest_branch_manager._parse_sheet's row_errors checks -
    # these five are the only ones that reject a row when blank.
    required_in_template = {h for h, _note, required in COLUMNS if required}
    assert required_in_template == {
        "DATE", "CLIENT_CHECK_NO", "CLIENT_ACCOUNT_NO", "DSA_CODE", "DSA_NAME",
    }
