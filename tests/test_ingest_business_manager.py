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
    result = parse_business_manager_file(str(path))
    assert result.header_row_index == 4
    assert len(result.rows) == 2
    assert not any(i.severity == "ERROR" for i in result.issues)


def test_loan_type_prefix_match_and_whitespace_strip(tmp_path):
    path = tmp_path / "business.xlsx"
    _write_business_workbook(
        path,
        [[1, "Arusha", "871", "C001", "ACC010", "NL : New", "2026-08-05", 500000, None, None, 500000, "ACC001  "]],
    )
    result = parse_business_manager_file(str(path))
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
    result = parse_business_manager_file(str(path))
    assert len(result.rows) == 0
    assert any("Unrecognized LOANTYPE" in i.message for i in result.issues)
