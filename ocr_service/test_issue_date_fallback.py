import parse_sds


def test_fallback_date_from_section_16():
    sect16 = "Date of issue / Date of\n13/04/2023 revision."
    result = parse_sds._resolve_issue_date(sect16, "")
    assert result == "2023-04-13"
