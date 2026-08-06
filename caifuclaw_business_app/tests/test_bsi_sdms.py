from datetime import datetime
from types import SimpleNamespace

import pytest

import app.bsi_sdms as bsi
import app.sync_engine as sync_engine


def _order(order_id: int = 1, transaction_id: str = "TX-100", platform_order_no: str = ""):
    return SimpleNamespace(
        id=order_id,
        tenant_id="tenant-1",
        platform="joom_logistics",
        account_id="shop-1",
        shop_id="shop-1",
        platform_order_id=f"JOOM-{order_id}",
        platform_order_no=platform_order_no,
        country_code="PL",
        raw_payload={
            "transactionId": transaction_id,
            "shippingOption": {"warehouseName": "BSI-PL", "warehouseType": "physical"},
            "shippingAddress": {
                "name": "Jan Kowalski",
                "country": "PL",
                "state": "Mazowieckie",
                "city": "Warsaw",
                "streetAddress1": "Main 12",
                "streetAddress2": "Unit 3",
                "zipCode": "00-001",
                "phoneNumber": "+48123456789",
                "email": "demo@example.invalid",
            },
        },
        last_api_payload={},
    )


def _allegro_order(order_id: int = 10):
    return SimpleNamespace(
        id=order_id,
        tenant_id="tenant-1",
        platform="allegro",
        account_id="allegro0001",
        shop_id="allegro0001",
        platform_order_id="DEMO-ORDER-0005",
        platform_order_no="DEMO-ORDER-0005",
        country_code="PL",
        raw_payload={
            "buyer": {"name": "Demo Buyer", "email": "demo@example.invalid"},
            "delivery": {
                "address": {
                    "firstName": "Edyta",
                    "lastName": "Wojnilowicz",
                    "city": "Gdansk",
                    "street": "Hokejowa 20/27",
                    "zipCode": "80-180",
                    "countryCode": "PL",
                    "phoneNumber": "+48123456789",
                }
            },
        },
        last_api_payload={},
    )


def test_sdms_signing_is_recursive_compact_and_stable():
    payload = {
        "CustomerCode": "CUST",
        "DeliveryInfo": {"ReceiverName": "测试", "Callback": "https://a.test/x"},
        "GoodsList": [{"SkuCode": "SKU-1", "Quantity": 2}],
        "AppId": "1",
        "RequestTime": "20260724123045",
        "Sign": "ignored",
    }

    assert bsi.sdms_signing_json(payload) == (
        '{"AppId":"1","CustomerCode":"CUST",'
        '"DeliveryInfo":{"Callback":"https:\\/\\/a.test\\/x","ReceiverName":"测试"},'
        '"GoodsList":[{"Quantity":2,"SkuCode":"SKU-1"}]}'
    )
    assert bsi.generate_sdms_sign(
        payload,
        customer_code="CUST",
        customer_secret="SECRET",
        request_time="20260724123045",
    ) == "374ede4f1cbe17d08a27b60f53fdd472"


def test_grouping_and_address_use_joom_transaction_and_fallback_province():
    first = _order(1, "TX-1")
    second = _order(2, "TX-1")
    first.raw_payload["shippingAddress"].pop("state")

    groups = bsi.group_bsi_orders([first, second])
    delivery = bsi.build_bsi_delivery_info(first)

    assert groups == [("TX-1", [first, second])]
    assert delivery["ProvinceName"] == "Warsaw"
    assert delivery["AddressLineOne"] == "Main 12"
    assert bsi.missing_bsi_delivery_fields(delivery) == []


def test_bsi_customer_order_no_prefers_joom_order_number_and_falls_back_to_id():
    assert bsi.bsi_customer_order_no([_order(1, platform_order_no="DEMO-ORDER-0006")]) == "DEMO-ORDER-0006"
    assert bsi.bsi_customer_order_no([_order(2)]) == "JOOM-2"


def test_bsi_customer_order_no_rejects_transaction_with_multiple_joom_orders():
    with pytest.raises(ValueError, match="多个订单编号"):
        bsi.bsi_customer_order_no([_order(1, "TX-1"), _order(2, "TX-1")])


def test_joom_bsi_follow_up_shipped_status_is_not_regressed_by_sync():
    row = _order()
    row.platform_status = "approved"
    row.fulfillment_type = "PHYSICAL"
    row.biz_status = "已发货"
    row.bsi_order_no = "BSI-JOOM-1"

    assert sync_engine._platform_snapshot_biz_status(row) == "已发货"


def test_allegro_bsi_grouping_and_delivery_use_platform_order_number() -> None:
    row = _allegro_order()

    groups = bsi.group_bsi_orders([row])
    delivery = bsi.build_bsi_delivery_info(row)

    assert groups == [(f"allegro:allegro0001:{row.platform_order_no}", [row])]
    assert bsi.bsi_customer_order_no([row]) == row.platform_order_no
    assert delivery == {
        "ReceiverName": "Edyta Wojnilowicz",
        "CountryCode": "PL",
        "ProvinceName": "Gdansk",
        "CityName": "Gdansk",
        "AddressLineOne": "Hokejowa 20/27",
        "AddressLineTwo": "",
        "ReceiverPostcode": "80-180",
        "ReceiverPhone": "+48123456789",
        "ReceiverEmail": "demo@example.invalid",
        "BusinessMode": 1,
        "LabelObtainMethod": 1,
        "ShippingMethod": 1,
    }


@pytest.mark.parametrize(
    ("address", "expected_code"),
    [
        ("12345", "numeric_only"),
        ("１２３４５", "numeric_only"),
        ("Warszawska", "single_word"),
        ("  Hokejowa\t", "single_word"),
    ],
)
def test_bsi_address_anomaly_detection(address, expected_code):
    anomaly = bsi.detect_bsi_address_anomaly({"AddressLineOne": address})

    assert anomaly is not None
    assert anomaly.code == expected_code


def test_bsi_address_anomaly_detection_accepts_normal_address():
    assert bsi.detect_bsi_address_anomaly({"AddressLineOne": "Hokejowa 20/27"}) is None
    assert bsi.detect_bsi_address_anomaly({"AddressLineOne": ""}) is None


def test_normal_bsi_address_never_loads_email_settings(monkeypatch):
    monkeypatch.setattr(
        bsi,
        "get_email_setting",
        lambda _db: (_ for _ in ()).throw(AssertionError("normal addresses must not load email settings")),
    )

    sent, message = bsi.send_bsi_address_anomaly_alert(
        object(),
        [_allegro_order()],
        "ORDER-1",
        {"AddressLineOne": "Hokejowa 20/27"},
        bsi_result="BSI草稿创建成功",
    )

    assert sent is False
    assert message == "地址正常，无需发送邮件"


def test_bsi_address_alert_failure_does_not_raise(monkeypatch):
    row = _allegro_order()

    class FakeDb:
        def __init__(self):
            self.logs = []
            self.commits = 0

        def scalar(self, _statement):
            return None

        def add(self, value):
            self.logs.append(value)

        def commit(self):
            self.commits += 1

    monkeypatch.setattr(
        bsi,
        "get_email_setting",
        lambda _db: SimpleNamespace(
            notification_recipients={"bsi_address_anomaly": "demo@example.invalid;demo@example.invalid"}
        ),
    )
    monkeypatch.setattr(bsi, "send_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("smtp down")))

    db = FakeDb()
    sent, message = bsi.send_bsi_address_anomaly_alert(
        db,
        [row],
        row.platform_order_no,
        {"AddressLineOne": "12345"},
        bsi_result="BSI草稿创建成功",
        provider_order_no="BSI-DRAFT-1",
    )

    assert sent is False
    assert message == "地址异常邮件发送失败：smtp down"
    assert db.commits == 1
    assert db.logs[0].operation_attribute == "BSI收货地址异常邮件发送失败"


def test_bsi_address_alert_without_recipient_does_not_raise(monkeypatch):
    row = _allegro_order()

    class FakeDb:
        def __init__(self):
            self.logs = []
            self.commits = 0

        def scalar(self, _statement):
            return None

        def add(self, value):
            self.logs.append(value)

        def commit(self):
            self.commits += 1

    monkeypatch.setattr(
        bsi,
        "get_email_setting",
        lambda _db: SimpleNamespace(notification_recipients={"bsi_address_anomaly": ""}),
    )
    monkeypatch.setattr(bsi, "send_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("email must not be sent")))

    db = FakeDb()
    sent, message = bsi.send_bsi_address_anomaly_alert(
        db,
        [row],
        row.platform_order_no,
        {"AddressLineOne": "12345"},
        bsi_result="BSI草稿创建成功",
    )

    assert sent is False
    assert message == "地址异常邮件发送失败：未配置 BSI 收货地址异常的邮件收件人"
    assert db.commits == 1
    assert db.logs[0].operation_attribute == "BSI收货地址异常邮件发送失败"


def test_bsi_address_alert_is_not_sent_twice_for_same_address(monkeypatch):
    row = _allegro_order()
    sent_messages = []

    class FakeDb:
        def __init__(self):
            self.logs = []

        def scalar(self, _statement):
            return 1 if any(log.operation_attribute == "发送BSI收货地址异常邮件" for log in self.logs) else None

        def add(self, value):
            self.logs.append(value)

        def commit(self):
            return None

    monkeypatch.setattr(
        bsi,
        "get_email_setting",
        lambda _db: SimpleNamespace(
            notification_recipients={"bsi_address_anomaly": "demo@example.invalid;demo@example.invalid"}
        ),
    )
    monkeypatch.setattr(bsi, "send_email", lambda *args, **kwargs: sent_messages.append((args, kwargs)))

    db = FakeDb()
    first = bsi.send_bsi_address_anomaly_alert(
        db,
        [row],
        row.platform_order_no,
        {"AddressLineOne": "Warszawska"},
        bsi_result="BSI草稿创建成功",
        provider_order_no="BSI-DRAFT-1",
    )
    second = bsi.send_bsi_address_anomaly_alert(
        db,
        [row],
        row.platform_order_no,
        {"AddressLineOne": "Warszawska"},
        bsi_result="复用已有BSI草稿",
        provider_order_no="BSI-DRAFT-1",
    )

    assert first == (True, "地址异常邮件已发送")
    assert second == (False, "地址异常邮件已发送，跳过重复通知")
    assert len(sent_messages) == 1
    assert sent_messages[0][0][1] == ["demo@example.invalid", "demo@example.invalid"]


def test_channel_refresh_tracks_changed_pan_eu_id_by_saved_name():
    channels = [
        {"ChannelId": 1061, "ChannelNameZh": "波兰本地", "ChannelNameEn": "Poland"},
        {"ChannelId": 4102, "ChannelNameZh": "泛欧预付", "ChannelNameEn": "Pan EU Prepaid"},
    ]

    refreshed = bsi.refresh_bsi_channel_config(
        channels,
        {
            "poland_channel_id": 1061,
            "poland_channel_name": "波兰本地",
            "pan_eu_channel_id": 3102,
            "pan_eu_channel_name": "泛欧预付",
        },
    )

    assert refreshed["poland_channel_id"] == 1061
    assert refreshed["pan_eu_channel_id"] == 4102
    assert refreshed["pan_eu_channel_name"] == "Pan EU Prepaid"


@pytest.mark.asyncio
async def test_existing_bsi_draft_skips_all_remote_validation_and_backfills_order_number(monkeypatch):
    row = _allegro_order()
    existing = SimpleNamespace(
        status="succeeded",
        provider_order_no="DEMO-ORDER-0007",
        submitted_at=None,
    )

    class FakeDb:
        def __init__(self):
            self.commits = 0

        def scalar(self, _statement):
            return existing

        def commit(self):
            self.commits += 1

    monkeypatch.setattr(
        bsi,
        "load_bsi_authorization",
        lambda _db: (_ for _ in ()).throw(AssertionError("existing BSI drafts must not load BSI authorization")),
    )

    db = FakeDb()
    result = await bsi.process_bsi_drafts(db, [row])

    assert result.succeeded_group_count == 1
    assert result.groups[0].reused is True
    assert result.groups[0].provider_order_no == "DEMO-ORDER-0007"
    assert row.bsi_order_no == "DEMO-ORDER-0007"
    assert row.bsi_submitted_at is not None
    assert db.commits == 1


@pytest.mark.asyncio
async def test_backfilled_bsi_order_number_skips_submission_without_submission_record(monkeypatch):
    row = _allegro_order()
    submitted_at = datetime(2026, 7, 27, 18, 0, 0)
    row.bsi_order_no = "DEMO-ORDER-0008"
    row.bsi_submitted_at = submitted_at

    class FakeDb:
        def __init__(self):
            self.commits = 0

        def scalar(self, _statement):
            raise AssertionError("backfilled BSI order numbers must skip submission-record and remote checks")

        def commit(self):
            self.commits += 1

    monkeypatch.setattr(
        bsi,
        "load_bsi_authorization",
        lambda _db: (_ for _ in ()).throw(AssertionError("backfilled BSI order numbers must not load BSI authorization")),
    )

    db = FakeDb()
    result = await bsi.process_bsi_drafts(db, [row])

    assert result.succeeded_group_count == 1
    assert result.groups[0].reused is True
    assert result.groups[0].provider_order_no == "DEMO-ORDER-0008"
    assert row.bsi_submitted_at == submitted_at
    assert db.commits == 1


@pytest.mark.asyncio
async def test_sku_resolution_uses_unique_normalized_product_name(monkeypatch):
    client = bsi.SdmsClient(bsi.SdmsCredentials("1", "CUSTOMER", "SECRET"))

    async def no_direct_matches(_warehouse_code, _sku_codes):
        return set()

    async def catalog(_warehouse_code):
        return [
            {
                "SkuCode": "TEST-SKU-001",
                "ProductCode": "000000000001",
                "ProductName": "Demo Album White",
                "IsEnable": 1,
            }
        ]

    monkeypatch.setattr(client, "query_skus", no_direct_matches)
    monkeypatch.setattr(client, "query_sku_catalog", catalog)

    resolved = await client.resolve_sku_codes(
        "DEMO-WAREHOUSE",
        ["TEST-PRODUCT-001"],
        lookup_names={"test-product-001": "Demo Album White"},
    )

    assert resolved["test-product-001"] == "TEST-SKU-001"


@pytest.mark.asyncio
async def test_process_creates_status_two_draft_and_records_success(monkeypatch):
    row = _order()
    row.raw_payload["shippingAddress"]["streetAddress1"] = "12345"
    auth_row = SimpleNamespace(config_json={})
    authorization = bsi.SdmsAuthorization(
        row=auth_row,
        credentials=bsi.SdmsCredentials("1", "CUSTOMER", "SECRET"),
        config={
            "base_url": bsi.SDMS_DEFAULT_BASE_URL,
            "auto_create_drafts": True,
            "warehouse_code": "DEMO-WAREHOUSE",
            "callback_url": "https://auth.example.test/api/logistics/bsi/callback/token",
            "poland_channel_id": 1061,
            "poland_channel_name": "Poland",
            "pan_eu_channel_id": 3102,
            "pan_eu_channel_name": "Pan EU Prepaid",
        },
    )
    submission = SimpleNamespace(
        status="",
        attempts=0,
        error_message="",
        response_json={},
        provider_order_no="",
        submitted_at=None,
        updated_at=None,
    )
    captured = {}
    captured_email = {}

    class FakeDb:
        def flush(self):
            return None

        def commit(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def query_warehouses(self, warehouse_code):
            return [{"WarehouseCode": warehouse_code}]

        async def query_channels(self, warehouse_code):
            return [
                {"ChannelId": 1061, "ChannelNameEn": "Poland"},
                {"ChannelId": 3102, "ChannelNameEn": "Pan EU Prepaid"},
            ]

        async def resolve_sku_codes(self, warehouse_code, sku_codes, *, lookup_names=None):
            return {sku.casefold(): "SDMS-SKU-1" for sku in sku_codes}

        async def create_draft(self, payload):
            captured.update(payload)
            return "PLE-100", {"Status": 200, "Value": {"Result": {"IsSuccess": True}, "Data": "PLE-100"}}

    async def no_refresh(_db, _rows):
        return None

    monkeypatch.setattr(bsi, "load_bsi_authorization", lambda db: authorization)
    monkeypatch.setattr(bsi, "_refresh_missing_joom_payloads", no_refresh)
    monkeypatch.setattr(bsi, "_goods_for_rows", lambda db, rows: ([{"SkuCode": "SKU-1", "Quantity": 2}], []))
    monkeypatch.setattr(bsi, "_submission_for", lambda *args, **kwargs: None)
    monkeypatch.setattr(bsi, "_upsert_submission", lambda *args, **kwargs: submission)
    monkeypatch.setattr(bsi, "SdmsClient", FakeClient)
    monkeypatch.setattr(
        bsi,
        "get_email_setting",
        lambda _db: SimpleNamespace(
            notification_recipients={"bsi_address_anomaly": "demo@example.invalid"}
        ),
    )

    def fake_send_email(_setting, recipients, subject, body, attachments=None):
        captured_email.update(
            recipients=recipients,
            subject=subject,
            body=body,
            attachments=attachments,
        )

    monkeypatch.setattr(bsi, "send_email", fake_send_email)

    result = await bsi.process_bsi_drafts(FakeDb(), [row])

    assert result.succeeded_group_count == 1
    assert result.groups[0].provider_order_no == "PLE-100"
    assert captured["Status"] == 2
    assert captured["Mode"] == 1
    assert captured["PoType"] == 1
    assert captured["DeliveryInfo"]["ChannelId"] == 1061
    assert captured["CustomerOrderNo"] == "JOOM-1"
    assert captured["GoodsList"] == [{"SkuCode": "SDMS-SKU-1", "Quantity": 2}]
    assert submission.status == "succeeded"
    assert row.bsi_order_no == "PLE-100"
    assert row.bsi_submitted_at == submission.submitted_at
    assert captured_email["recipients"] == ["demo@example.invalid"]
    assert captured_email["subject"] == "BSI收货地址异常：JOOM-1订单收货地址异常"
    assert "异常原因：收货地址为纯数字" in captured_email["body"]
    assert "BSI提交结果：BSI草稿创建成功" in captured_email["body"]
    assert "BSI草稿单号：PLE-100" in captured_email["body"]
    assert "地址一：12345" in captured_email["body"]


@pytest.mark.asyncio
async def test_process_does_not_call_sdms_when_auto_create_is_disabled(monkeypatch):
    row = _order()
    authorization = bsi.SdmsAuthorization(
        row=SimpleNamespace(config_json={}),
        credentials=bsi.SdmsCredentials("1", "CUSTOMER", "SECRET"),
        config={
            "auto_create_drafts": False,
            "warehouse_code": "DEMO-WAREHOUSE",
            "callback_url": "https://auth.example.test/api/logistics/bsi/callback/token",
        },
    )
    monkeypatch.setattr(bsi, "load_bsi_authorization", lambda db: authorization)

    class FakeDb:
        def scalar(self, _statement):
            return None

        def commit(self):
            return None

    result = await bsi.process_joom_bsi_drafts(FakeDb(), [row])

    assert result.succeeded_group_count == 0
    assert result.groups[0].status == "disabled"
    assert "尚未启用" in result.groups[0].message


@pytest.mark.asyncio
async def test_process_does_not_retry_previously_pending_submission(monkeypatch):
    row = _order()
    authorization = bsi.SdmsAuthorization(
        row=SimpleNamespace(config_json={}),
        credentials=bsi.SdmsCredentials("1", "CUSTOMER", "SECRET"),
        config={
            "auto_create_drafts": True,
            "warehouse_code": "DEMO-WAREHOUSE",
            "callback_url": "https://auth.example.test/api/logistics/bsi/callback/token",
            "poland_channel_id": 1061,
            "pan_eu_channel_id": 3102,
        },
    )
    existing = SimpleNamespace(status="pending", provider_order_no="")

    class FakeDb:
        def commit(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def query_warehouses(self, warehouse_code):
            return [{"WarehouseCode": warehouse_code}]

        async def query_channels(self, _warehouse_code):
            return [
                {"ChannelId": 1061, "ChannelNameEn": "Poland"},
                {"ChannelId": 3102, "ChannelNameEn": "Pan EU Prepaid"},
            ]

        async def resolve_sku_codes(self, _warehouse_code, sku_codes, *, lookup_names=None):
            return {sku.casefold(): sku for sku in sku_codes}

        async def create_draft(self, _payload):
            raise AssertionError("pending submissions must not be retried")

    async def no_refresh(_db, _rows):
        return None

    monkeypatch.setattr(bsi, "load_bsi_authorization", lambda _db: authorization)
    monkeypatch.setattr(bsi, "_refresh_missing_joom_payloads", no_refresh)
    monkeypatch.setattr(bsi, "_goods_for_rows", lambda _db, _rows: ([{"SkuCode": "SKU-1", "Quantity": 1}], []))
    monkeypatch.setattr(bsi, "_submission_for", lambda *args, **kwargs: existing)
    monkeypatch.setattr(bsi, "SdmsClient", FakeClient)

    result = await bsi.process_joom_bsi_drafts(FakeDb(), [row])

    assert result.groups[0].status == "uncertain"
    assert "避免重复下单" in result.groups[0].message


@pytest.mark.asyncio
async def test_query_sku_tracking_uses_the_bsi_documented_order_no_field(monkeypatch):
    client = bsi.SdmsClient(bsi.SdmsCredentials("1", "CUSTOMER", "SECRET"))
    captured = {}

    async def fake_post(path, payload, *, creates_order=False):
        captured.update({"path": path, "payload": payload, "creates_order": creates_order})
        return {"Status": 200, "Value": {"Result": {"IsSuccess": True}}}

    monkeypatch.setattr(client, "_post", fake_post)

    await client.query_sku_tracking("DEMO-WAREHOUSE", "DEMO-TRACKING-001")

    assert captured == {
        "path": "/apitask/v1/QuerySkuTracking",
        "payload": {
            "AppId": "1",
            "WarehouseCode": "DEMO-WAREHOUSE",
            "CustomerCode": "CUSTOMER",
            "OrderNO": "DEMO-TRACKING-001",
        },
        "creates_order": False,
    }


@pytest.mark.asyncio
async def test_cancel_and_delete_draft_use_bsi_modes(monkeypatch):
    client = bsi.SdmsClient(bsi.SdmsCredentials("1", "CUSTOMER", "SECRET"))
    captured = []

    async def fake_post(path, payload, *, creates_order=False):
        captured.append({"path": path, "payload": payload, "creates_order": creates_order})
        return {"Status": 200, "Value": {"Result": {"IsSuccess": True}}}

    monkeypatch.setattr(client, "_post", fake_post)

    await client.cancel_draft({"Mode": 1, "CustomerOrderNo": "demo-order-id-0001", "Status": 2})
    await client.delete_draft({"Mode": 1, "CustomerOrderNo": "demo-order-id-0001", "Status": 2})

    assert captured == [
        {
            "path": "/apitask/v1/ReceiveStockOrderOut",
            "payload": {"Mode": 3, "CustomerOrderNo": "demo-order-id-0001", "Status": 2},
            "creates_order": False,
        },
        {
            "path": "/apitask/v1/ReceiveStockOrderOut",
            "payload": {"Mode": 4, "CustomerOrderNo": "demo-order-id-0001", "Status": 2},
            "creates_order": False,
        },
    ]
