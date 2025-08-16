from parse_sds import _extract_product_use


def test_extract_product_use_multiline():
    sect = "Product use:\n Antiseptic and disinfectant"
    assert _extract_product_use(sect) == "Antiseptic and disinfectant"


def test_extract_product_use_simple_use_label():
    sect = "Formulation Item Number: 2NPK001\nUse\nAntibacterial rub preparation for topical human use."
    assert _extract_product_use(sect) == "Antibacterial rub preparation for topical human use."
