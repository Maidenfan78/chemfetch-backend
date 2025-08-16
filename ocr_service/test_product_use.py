from parse_sds import _extract_product_use


def test_extract_product_use_multiline():
    sect = "Product use:\n Antiseptic and disinfectant"
    assert _extract_product_use(sect) == "Antiseptic and disinfectant"
