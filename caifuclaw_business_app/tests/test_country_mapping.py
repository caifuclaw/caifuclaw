# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from app.country_mapping import COUNTRY_NAME_CN_BY_CODE, country_name_cn, country_name_to_code


def test_country_name_cn_covers_common_marketplace_countries():
    assert country_name_cn("RU") == "俄罗斯"
    assert country_name_cn("AR") == "阿根廷"
    assert country_name_cn("MX") == "墨西哥"
    assert country_name_cn("TR") == "土耳其"
    assert country_name_cn("KZ") == "哈萨克斯坦"


def test_country_name_to_code_supports_chinese_and_platform_aliases():
    assert country_name_to_code("俄罗斯") == "RU"
    assert country_name_to_code("Россия") == "RU"
    assert country_name_to_code("United States of America") == "US"
    assert country_name_to_code("España") == "ES"
    assert country_name_to_code("阿根廷") == "AR"
    assert country_name_to_code("mx") == "MX"


def test_country_mapping_contains_full_iso_alpha2_set():
    assert len(COUNTRY_NAME_CN_BY_CODE) >= 249
    assert all(len(code) == 2 and code.isupper() for code in COUNTRY_NAME_CN_BY_CODE)
