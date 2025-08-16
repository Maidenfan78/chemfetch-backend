from pathlib import Path
from parse_sds import parse_sds_path

def test_issue_date_extracted():
    pdf_path = Path(__file__).with_name("G20_sds.pdf")
    result = parse_sds_path(str(pdf_path), product_id=176)
    assert result.issue_date == "2023-04-13"
