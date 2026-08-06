# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import app.main as main_module
from app.credential_manager import CredentialManager, init_credential_manager
from app.models import LogisticsAuthorization


def test_seed_payloads_contain_demo_only_credentials():
    init_credential_manager(CredentialManager.generate_key())
    manager = main_module.get_credential_manager()
    rows = []
    for item in main_module.LOGISTICS_AUTH_SEED_DATA:
        row = LogisticsAuthorization(
            carrier_code=item["carrier_code"],
            carrier_name=item["carrier_name"],
            account_name=item["account_name"],
            encrypted_credentials=manager.encrypt_credentials(item["credentials"]),
            config_json=item.get("config_json") or {},
        )
        main_module._apply_logistics_authorization_result(row, item["credentials"])
        rows.append(row)

    assert {row.carrier_code for row in rows} == {"qianhai_weishi", "wanbang_suda_new", "bsi_overseas"}
    qianhai = next(row for row in rows if row.carrier_code == "qianhai_weishi")
    wanbang = next(row for row in rows if row.carrier_code == "wanbang_suda_new")
    bsi = next(row for row in rows if row.carrier_code == "bsi_overseas")
    assert qianhai.carrier_name == "深圳前海纬狮物流网络科技有限公司"
    assert qianhai.account_name == "DEMO-CARRIER-1"
    assert qianhai.authorization_status == "failed"
    assert main_module._logistics_credentials(qianhai)["token"] == ""
    assert wanbang.carrier_name == "万邦速达(新)"
    assert wanbang.account_name == "DEMO-CARRIER"
    assert main_module._logistics_credentials(wanbang)["token"] == ""
    assert bsi.carrier_name == "BSI海外仓"
    assert bsi.account_name == "DEMO-CARRIER-3"
    assert bsi.authorization_status == "failed"
    assert main_module._logistics_credentials(bsi)["customer_secret"] == ""


def test_verify_logistics_credentials_requires_carrier_schema_fields():
    valid, missing, message = main_module._verify_logistics_credentials("wanbang_suda_new", {"customer_code": "DEMO-CARRIER"})

    assert valid is False
    assert missing == ["token"]
    assert "token" in message


def test_logistics_channel_option_uses_enabled_authorization_display_fields():
    row = LogisticsAuthorization(
        carrier_code="qianhai_weishi",
        carrier_name="深圳前海纬狮物流网络科技有限公司",
        account_name="DEMO-CARRIER-1",
        enabled=True,
    )

    option = main_module._logistics_channel_option_dto(row)

    assert option.value == "深圳前海纬狮物流网络科技有限公司 / DEMO-CARRIER-1"
    assert option.label == "深圳前海纬狮物流网络科技有限公司 / DEMO-CARRIER-1 / qianhai_weishi"
    assert option.carrier_code == "qianhai_weishi"
    assert option.account_name == "DEMO-CARRIER-1"


def test_logistics_channel_options_include_only_enabled_authorizations():
    rows = [
        LogisticsAuthorization(
            carrier_code="qianhai_weishi",
            carrier_name="深圳前海纬狮物流网络科技有限公司",
            account_name="DEMO-CARRIER-1",
            enabled=True,
        ),
        LogisticsAuthorization(
            carrier_code="wanbang_suda_new",
            carrier_name="万邦速达(新)",
            account_name="DEMO-CARRIER",
            enabled=False,
        ),
    ]

    options = main_module._enabled_logistics_channel_options(rows)

    assert [option.value for option in options] == ["深圳前海纬狮物流网络科技有限公司 / DEMO-CARRIER-1"]
