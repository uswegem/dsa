import openpyxl

from app.services.ingest_business_manager import parse_business_manager_file

BIZ_HEADERS = [
    "Br_no", "Branch", "EMPLOYEE_NO", "CUSTOMER_NO", "Account No", "LOANTYPE",
    "Disbursement date", "Disbursement Amt", "Payout To Client", "Letshego Topup",
    "Appl Amount", "CLIENT_DISB_EXT_ACCOUNT_NO",
]


def _write_business_workbook(path, data_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    # 4 rows of report metadata before the real header, per spec
    ws.append(["Payout Report by Branch"])
    ws.append(["Period:", "August 2026"])
    ws.append(["Branch Filter:", "All"])
    ws.append(["Report Date:", "2026-09-01"])
    ws.append(BIZ_HEADERS)
    for row in data_rows:
        ws.append(row)
    wb.save(path)


def test_detects_header_row_past_metadata_block(tmp_path):
    path = tmp_path / "business.xlsx"
    _write_business_workbook(
        path,
        [
            [1, "Arusha  ", "871  ", "C001", "ACC010", "NL : New", "2026-08-05", 500000, None, None, 500000, "ACC001  "],
            [1, "Arusha", "NCAA1680", "C002", "ACC020", "RF : Topup", "2026-08-07", None, 200000, 250000, 250000, "ACC002"],
        ],
    )
    result = parse_business_manager_file(str(path), period_month=8, period_year=2026)
    assert result.header_row_index == 4
    assert len(result.rows) == 2
    assert not any(i.severity == "ERROR" for i in result.issues)


def test_loan_type_prefix_match_and_whitespace_strip(tmp_path):
    path = tmp_path / "business.xlsx"
    _write_business_workbook(
        path,
        [[1, "Arusha", "871", "C001", "ACC010", "NL : New", "2026-08-05", 500000, None, None, 500000, "ACC001  "]],
    )
    result = parse_business_manager_file(str(path), period_month=8, period_year=2026)
    row = result.rows[0]
    assert row.loan_type == "NL"
    assert row.client_disb_ext_account_no == "ACC001"  # trailing whitespace stripped
    assert row.employee_no == "871"


def test_unrecognized_loan_type_is_flagged(tmp_path):
    path = tmp_path / "business.xlsx"
    _write_business_workbook(
        path,
        [[1, "Arusha", "871", "C001", "ACC010", "UNKNOWN", "2026-08-05", 500000, None, None, 500000, "ACC001"]],
    )
    result = parse_business_manager_file(str(path), period_month=8, period_year=2026)
    assert len(result.rows) == 0
    assert any("Unrecognized LOANTYPE" in i.message for i in result.issues)


def test_disbursement_date_outside_selected_period_is_rejected(tmp_path):
    path = tmp_path / "business.xlsx"
    _write_business_workbook(
        path,
        [
            [1, "Arusha", "871", "C001", "ACC010", "NL : New", "2026-08-05", 500000, None, None, 500000, "ACC001"],
            [1, "Arusha", "872", "C002", "ACC020", "NL : New", "2026-07-31", 300000, None, None, 300000, "ACC002"],  # wrong month
        ],
    )
    result = parse_business_manager_file(str(path), period_month=8, period_year=2026)
    assert len(result.rows) == 1
    assert result.rows[0].client_disb_ext_account_no == "ACC001"
    errors = [i for i in result.issues if i.severity == "ERROR"]
    assert len(errors) == 1
    assert "outside the selected period" in errors[0].message


def test_missing_disbursement_date_is_rejected(tmp_path):
    path = tmp_path / "business.xlsx"
    _write_business_workbook(
        path,
        [
            # a companion well-formed row keeps the sheet's data block densely
            # populated enough for header-row detection, matching how a real
            # 50+ column export behaves even when one row has a blank date
            [1, "Arusha", "870", "C000", "ACC000", "NL : New", "2026-08-01", 400000, None, None, 400000, "ACC000"],
            [1, "Arusha", "871", "C001", "ACC010", "NL : New", None, 500000, None, None, 500000, "ACC001"],
        ],
    )
    result = parse_business_manager_file(str(path), period_month=8, period_year=2026)
    assert len(result.rows) == 1
    assert result.rows[0].client_disb_ext_account_no == "ACC000"
    assert any("Disbursement date is blank" in i.message for i in result.issues)
