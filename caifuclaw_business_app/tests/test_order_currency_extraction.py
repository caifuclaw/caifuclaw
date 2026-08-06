# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app import sync_engine
from app.main import _extract_order_fields as main_extract_order_fields
from app.connectors.base import LabelResult, NormalizedOrder, OrderStatusUpdate
from app.label_platforms import label_shipment_id_for_order
from app.label_tracking import apply_label_result_tracking
from app.models import Order, Shipment
from app.sync_engine import (
    _apply_status_update_to_order,
    _compute_biz_status,
    _extract_order_fields as sync_extract_order_fields,
    _has_existing_platform_shipment,
    _record_fulfillment_failure,
)
from app.order_types import order_is_logistics_label_exempt


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def test_extract_order_currency_from_nested_product_price():
    raw_payload = {
        "order_amount": "108.00",
        "products": [
            {
                "price": {"amount": "108", "currency": "CNY"},
                "quantity": 1,
            }
        ],
    }

    assert main_extract_order_fields(raw_payload)["currency"] == "CNY"
    assert sync_extract_order_fields(raw_payload)["currency"] == "CNY"


def test_extract_tracking_number_from_allegro_shipments_waybill():
    raw_payload = {
        "id": "cf-1",
        "shipments": [{"id": "shipment-1", "waybill": "WAYBILL-1"}],
    }

    assert main_extract_order_fields(raw_payload)["shipment_tracking_number"] == "WAYBILL-1"
    assert sync_extract_order_fields(raw_payload)["shipment_tracking_number"] == "WAYBILL-1"


def test_extract_tracking_number_from_allegro_shipments_payload_waybill():
    raw_payload = {
        "id": "cf-1",
        "shipments_payload": {"shipments": [{"id": "shipment-1", "waybill": "WAYBILL-1"}]},
    }

    assert main_extract_order_fields(raw_payload)["shipment_tracking_number"] == "WAYBILL-1"
    assert sync_extract_order_fields(raw_payload)["shipment_tracking_number"] == "WAYBILL-1"


def test_find_existing_allegro_order_matches_manual_import_without_posting_number():
    from app.database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Order.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        existing = Order(
            tenant_id="default",
            platform="allegro",
            account_id="allegro-demo",
            shop_id="allegro-demo",
            platform_order_id="cf-1",
            platform_order_no="cf-1",
            posting_number="",
            platform_status="shipped",
            raw_payload={"source": "excel_import"},
        )
        db.add(existing)
        db.commit()

        normalized = NormalizedOrder(
            platform_order_id="cf-1",
            platform_order_no="cf-1",
            posting_number="cf-1",
            platform_status="READY_FOR_PROCESSING",
            raw_payload={},
        )

        assert sync_engine._find_existing_order(db, "allegro", "allegro-demo", normalized).id == existing.id
    finally:
        db.close()


def test_find_existing_joom_order_matches_when_posting_number_changes():
    from app.database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Order.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        existing = Order(
            tenant_id="default",
            platform="joom_logistics",
            account_id="JOOM-DEMO-001",
            shop_id="JOOM-DEMO-001",
            platform_order_id="joom-1",
            platform_order_no="joom-1",
            posting_number="DEMO-ORDER-0016",
            platform_status="approved",
            raw_payload={},
        )
        db.add(existing)
        db.commit()

        normalized = NormalizedOrder(
            platform_order_id="joom-1",
            platform_order_no="joom-1",
            posting_number="",
            platform_status="approved",
            raw_payload={},
        )

        assert sync_engine._find_existing_order(db, "joom_logistics", "JOOM-DEMO-001", normalized).id == existing.id
    finally:
        db.close()


def test_upsert_order_generates_stable_internal_order_no(monkeypatch):
    from app.database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Order.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    monkeypatch.setattr(sync_engine, "get_settings", lambda: type("Settings", (), {"default_tenant_id": "default"})())
    monkeypatch.setattr(sync_engine, "load_shipping_deadline_settings", lambda _db: [])
    monkeypatch.setattr(sync_engine, "load_enabled_logistics_rules", lambda _db: [])
    monkeypatch.setattr(sync_engine, "update_order_dispatch_deadline", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync_engine, "_replace_order_items", lambda *args, **kwargs: None)
    try:
        normalized = NormalizedOrder(
            platform_order_id="order-1",
            platform_order_no="order-1",
            posting_number="DEMO-ORDER-0017",
            platform_status="awaiting_packaging",
            raw_payload={},
        )
        config = {"platform": "ozon", "account_id": "shop-1", "display_name": "Shop 1", "settings": {}}

        created = sync_engine.upsert_order(db, config, normalized)
        db.commit()
        first_internal_no = created.internal_order_no

        updated = sync_engine.upsert_order(db, config, normalized)

        assert len(first_internal_no) == 16
        assert first_internal_no.isalnum()
        assert first_internal_no == first_internal_no.upper()
        assert updated.internal_order_no == first_internal_no
    finally:
        db.close()


def test_compute_biz_status_never_moves_picking_back_to_pending():
    assert _compute_biz_status("awaiting_deliver", "FBS", "none", "配货中") == "配货中"
    assert _compute_biz_status("awaiting_packaging", "FBO", "to_unshipped", "配货中") == "配货中"
    assert _compute_biz_status("fulfilledOnline", "FBS", "none", "配货中") == "配货中"
    assert _compute_biz_status("shipped", "FBS", "none", "配货中") == "已妥投"


def test_compute_biz_status_maps_joom_historical_statuses():
    assert _compute_biz_status("complete", "FBS", "none", "待处理") == "已妥投"
    assert _compute_biz_status("completed", "FBS", "none", "待处理") == "已妥投"
    assert _compute_biz_status("delivered", "FBS", "none", "待处理") == "已妥投"
    assert _compute_biz_status("Shipped", "FBS", "none", "待处理") == "已妥投"
    assert _compute_biz_status("fulfilledOnline", "FBS", "none", "待处理") == "待处理"
    assert _compute_biz_status("cancel", "FBS", "none", "待处理") == "已作废"
    assert _compute_biz_status("canceled", "FBS", "none", "待处理") == "已作废"
    assert _compute_biz_status("Cancel", "FBS", "none", "待处理") == "已作废"
    assert _compute_biz_status("refunded", "FBS", "none", "待处理") == "已作废"
    assert _compute_biz_status("paidByJoomRefund", "FBS", "none", "待处理") == "已作废"
    assert _compute_biz_status("cancelled", "FBS", "none", "待处理") == "已作废"


def test_compute_biz_status_maps_allegro_sent_and_picked_up():
    assert _compute_biz_status("SENT", "FBS", "none", "待处理", "allegro") == "已发货"
    assert _compute_biz_status("SENT", "FBS", "none", "配货中", "allegro") == "已发货"
    assert _compute_biz_status("SENT", "FBS", "none", "已妥投", "allegro") == "已发货"
    assert _compute_biz_status("PICKED_UP", "FBS", "none", "已发货", "allegro") == "已妥投"


def test_compute_biz_status_keeps_wildberries_complete_pending():
    assert _compute_biz_status("complete", "FBS", "none", "待处理", "wildberries") == "待处理"
    assert _compute_biz_status("complete", "FBS", "none", "已发货", "wildberries") == "已发货"
    assert _compute_biz_status("sold", "FBS", "none", "待处理", "wildberries") == "已妥投"
    assert _compute_biz_status("complete", "FBS", "none", "待处理", "ozon") == "已妥投"


def test_fulfillment_failure_keeps_downstream_status():
    order = Order(
        tenant_id="default",
        platform="ozon",
        account_id="100001",
        shop_id="100001",
        platform_order_id="DEMO-ORDER-0018",
        platform_order_no="DEMO-ORDER-0019",
        posting_number="DEMO-ORDER-0020",
        platform_status="awaiting_deliver",
        biz_status="配货中",
        local_status="picking",
    )

    _record_fulfillment_failure(
        order,
        RuntimeError("HAS_INCORRECT_STATUS"),
        previous_biz_status="配货中",
        previous_local_status="picking",
    )

    assert order.biz_status == "配货中"
    assert order.local_status == "picking"
    assert order.error_message == "HAS_INCORRECT_STATUS"


def test_existing_platform_shipment_detects_order_level_tracking():
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="wb-1",
        shop_id="wb-1",
        platform_order_id="DEMO-ORDER-0021",
        posting_number="DEMO-ORDER-0021",
        shipment_tracking_number="DEMO-TRACKING-0005",
        raw_payload={},
    )

    assert _has_existing_platform_shipment(object(), order)

    order.shipment_tracking_number = ""
    order.raw_payload = {"shipment": {"id": "shipment-1"}}
    assert _has_existing_platform_shipment(object(), order)


def test_wildberries_russia_order_is_logistics_label_exempt():
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="wb-1",
        shop_id="wb-1",
        shop_name="Any WB Store",
        platform_order_id="DEMO-ORDER-0021",
        posting_number="DEMO-ORDER-0021",
        country_code="RU",
        country_name_cn="俄罗斯",
        raw_payload={},
    )

    assert order_is_logistics_label_exempt(order)


def test_allegro_order_shipment_id_is_used_for_label_download():
    order = Order(
        tenant_id="default",
        platform="allegro",
        account_id="allegro-demo",
        shop_id="allegro-demo",
        platform_order_id="DEMO-ORDER-0022",
        posting_number="DEMO-ORDER-0022",
        shipment_tracking_number="DEMO-TRACKING-0006",
        raw_payload={
            "shipments": [
                {
                    "id": "DEMO-SHIPMENT-001",
                    "waybill": "DEMO-WAYBILL-001",
                    "carrierId": "WANB_EXPRESS",
                }
            ]
        },
    )

    shipment_id, reason = label_shipment_id_for_order(order)

    assert shipment_id == "DEMO-SHIPMENT-001"
    assert reason == ""


def test_wildberries_russia_exemption_matches_payload_values():
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="wb-1",
        shop_id="wb-1",
        shop_name="",
        platform_order_id="DEMO-ORDER-0023",
        posting_number="DEMO-ORDER-0023",
        raw_payload={"shop_name": "Other Store", "country": "俄罗斯(RU)"},
    )

    assert order_is_logistics_label_exempt(order)


def test_wildberries_demo_shop_china_order_is_not_logistics_label_exempt():
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="WB DEMO SHOP CN",
        shop_id="WB DEMO SHOP CN",
        shop_name="WB DEMO SHOP CN",
        platform_order_id="DEMO-ORDER-0024",
        posting_number="DEMO-ORDER-0024",
        country_code="CN",
        country_name_cn="中国",
        raw_payload={"country": "中国(CN)"},
    )

    assert not order_is_logistics_label_exempt(order)


def test_wildberries_beijing_cross_border_payload_overrides_stale_ru_country():
    raw_payload = {
        "site": "wildberries",
        "country_code": "RU",
        "currencyCode": 643,
        "convertedCurrencyCode": 156,
        "crossBorderType": 1,
        "offices": ["\u041f\u0435\u043a\u0438\u043d"],
    }
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="WB DEMO SHOP CN",
        shop_id="WB DEMO SHOP CN",
        shop_name="WB DEMO SHOP CN",
        platform_order_id="DEMO-ORDER-0025",
        posting_number="DEMO-ORDER-0025",
        country_code="RU",
        country_name_cn="俄罗斯",
        raw_payload=raw_payload,
    )

    assert main_extract_order_fields(raw_payload)["country_code"] == "CN"
    assert sync_extract_order_fields(raw_payload)["country_code"] == "CN"
    assert not order_is_logistics_label_exempt(order)


def test_wildberries_russia_order_does_not_persist_supply_as_tracking(monkeypatch):
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="wb-ru-store",
        shop_id="wb-ru-store",
        shop_name="Any WB Store",
        platform_order_id="DEMO-ORDER-0026",
        posting_number="DEMO-ORDER-0026",
        shipment_tracking_number="",
        raw_payload={},
    )
    normalized = NormalizedOrder(
        platform_order_id="DEMO-ORDER-0026",
        platform_order_no="DEMO-ORDER-0026",
        posting_number="DEMO-ORDER-0026",
        platform_status="new",
        raw_payload={
            "country_code": "RU",
            "shipment_tracking_number": "DEMO-TRACKING-0007",
            "tracking_number": "DEMO-TRACKING-0007",
        },
    )

    monkeypatch.setattr(sync_engine, "_find_existing_order", lambda *args, **kwargs: order)
    monkeypatch.setattr(sync_engine, "_replace_order_items", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync_engine, "get_settings", lambda: type("Settings", (), {"default_tenant_id": "default"})())
    monkeypatch.setattr(sync_engine, "load_shipping_deadline_settings", lambda db: [])
    monkeypatch.setattr(sync_engine, "load_enabled_logistics_rules", lambda db: [])
    monkeypatch.setattr(sync_engine, "update_order_dispatch_deadline", lambda *args, **kwargs: None)

    result = sync_engine.upsert_order(
        object(),
        {
            "platform": "wildberries",
            "account_id": "wb-ru-store",
            "display_name": "Any WB Store",
            "settings": {},
            "_shipping_deadline_settings": [],
        },
        normalized,
    )

    assert order_is_logistics_label_exempt(result)
    assert result.shipment_tracking_number == ""


def test_wildberries_demo_shop_china_order_does_not_persist_supply_as_tracking(monkeypatch):
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="WB DEMO SHOP CN",
        shop_id="WB DEMO SHOP CN",
        shop_name="WB DEMO SHOP CN",
        platform_order_id="DEMO-ORDER-0027",
        posting_number="DEMO-ORDER-0027",
        shipment_tracking_number="",
        raw_payload={},
    )
    normalized = NormalizedOrder(
        platform_order_id="DEMO-ORDER-0027",
        platform_order_no="DEMO-ORDER-0027",
        posting_number="DEMO-ORDER-0027",
        platform_status="new",
        raw_payload={
            "country_code": "CN",
            "site": "wildberries",
            "shipment_tracking_number": "WB-GI-456",
            "tracking_number": "WB-GI-456",
        },
    )

    monkeypatch.setattr(sync_engine, "_find_existing_order", lambda *args, **kwargs: order)
    monkeypatch.setattr(sync_engine, "_replace_order_items", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync_engine, "get_settings", lambda: type("Settings", (), {"default_tenant_id": "default"})())
    monkeypatch.setattr(sync_engine, "load_shipping_deadline_settings", lambda db: [])
    monkeypatch.setattr(sync_engine, "load_enabled_logistics_rules", lambda db: [])
    monkeypatch.setattr(sync_engine, "update_order_dispatch_deadline", lambda *args, **kwargs: None)

    result = sync_engine.upsert_order(
        object(),
        {
            "platform": "wildberries",
            "account_id": "WB DEMO SHOP CN",
            "display_name": "WB DEMO SHOP CN",
            "settings": {},
            "_shipping_deadline_settings": [],
        },
        normalized,
    )

    assert not order_is_logistics_label_exempt(result)
    assert result.shipment_tracking_number == ""


def test_wildberries_label_barcode_updates_tracking_number():
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="WB DEMO SHOP CN",
        shop_id="WB DEMO SHOP CN",
        shop_name="WB DEMO SHOP CN",
        platform_order_id="DEMO-ORDER-0028",
        posting_number="DEMO-ORDER-0028",
        shipment_tracking_number="WB-GI-DEMO-001",
        raw_payload={
            "site": "wildberries",
            "country_code": "CN",
            "supply_id": "WB-GI-DEMO-001",
            "shipment_tracking_number": "WB-GI-DEMO-001",
        },
    )
    shipment = Shipment(
        order_id=15600,
        platform_shipment_id="DEMO-ORDER-0028",
        tracking_number="",
        carrier="wildberries",
        status="label_ready",
    )
    label_result = LabelResult(
        content=b"%PDF-1.4\n",
        raw_payload={
            "waybillNumber": "DEMO-TRACKING-0101",
            "stickers": [
                {
                    "id": 5155000001,
                    "barcode": "*DMcSAMpW",
                    "partA": "5487945",
                    "partB": "3386",
                }
            ]
        },
    )

    changed = apply_label_result_tracking(order, shipment, label_result)

    assert changed is True
    assert order.shipment_tracking_number == "DEMO-TRACKING-0101"
    assert shipment.tracking_number == "DEMO-TRACKING-0101"
    assert order.raw_payload["supply_id"] == "WB-GI-DEMO-001"
    assert order.raw_payload["shipment_tracking_number"] == "DEMO-TRACKING-0101"
    assert order.raw_payload["waybill_number"] == "DEMO-TRACKING-0101"


def test_wildberries_label_parcel_id_updates_tracking_number():
    order = Order(
        tenant_id="default",
        platform="wildberries",
        account_id="WB DEMO SHOP CN",
        shop_id="WB DEMO SHOP CN",
        shop_name="WB DEMO SHOP CN",
        platform_order_id="DEMO-ORDER-0029",
        posting_number="DEMO-ORDER-0029",
        shipment_tracking_number="",
        raw_payload={
            "site": "wildberries",
            "country_code": "CN",
            "crossBorderType": 1,
        },
    )
    shipment = Shipment(
        order_id=16350,
        platform_shipment_id="DEMO-ORDER-0029",
        tracking_number="",
        carrier="wildberries",
        status="label_ready",
    )
    label_result = LabelResult(
        content=b"%PDF-1.4\n",
        raw_payload={
            "cross_border": True,
            "stickers": [
                {
                    "id": 5155000002,
                    "barcode": "*DObv4SBB",
                    "parcelId": "DEMO-TRACKING-0102",
                }
            ]
        },
    )

    changed = apply_label_result_tracking(order, shipment, label_result)

    assert changed is True
    assert order.shipment_tracking_number == "DEMO-TRACKING-0102"
    assert shipment.tracking_number == "DEMO-TRACKING-0102"
    assert order.raw_payload["shipment_tracking_number"] == "DEMO-TRACKING-0102"


def test_wildberries_status_refresh_clears_legacy_supply_tracking(monkeypatch):
    order = Order(
        id=5155000001,
        tenant_id="default",
        platform="wildberries",
        account_id="WB DEMO SHOP CN",
        shop_id="WB DEMO SHOP CN",
        platform_order_id="DEMO-ORDER-0028",
        posting_number="DEMO-ORDER-0028",
        platform_status="complete",
        shipment_tracking_number="WB-GI-DEMO-001",
        raw_payload={
            "site": "wildberries",
            "supplyId": "WB-GI-DEMO-001",
            "shipment_tracking_number": "WB-GI-DEMO-001",
        },
        fulfillment_type="FBS",
    )
    update = OrderStatusUpdate(
        posting_number="DEMO-ORDER-0028",
        platform_order_id="DEMO-ORDER-0028",
        platform_order_no="DEMO-ORDER-0028",
        platform_status="complete",
        raw_payload={
            "id": 5155000001,
            "site": "wildberries",
            "supplierStatus": "complete",
            "supplyId": "WB-GI-DEMO-001",
        },
    )

    def fail_upsert(*args, **kwargs):
        raise AssertionError("Wildberries supply id is not a tracking number")

    monkeypatch.setattr(sync_engine, "_upsert_shipment_info", fail_upsert)

    result = _apply_status_update_to_order(object(), order, update)

    assert result["tracking_updated"] is True
    assert order.shipment_tracking_number == ""


def test_joom_placeholder_shipment_without_tracking_does_not_skip_submit(monkeypatch):
    order = Order(
        id=4416,
        tenant_id="default",
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        shop_id="JOOM-DEMO-001",
        platform_order_id="DEMO-ORDER-0030",
        platform_order_no="DEMO-ORDER-0030",
        posting_number="DEMO-ORDER-0030",
        platform_status="approved",
        biz_status="配货中",
        local_status="shipment_created",
        raw_payload={},
    )
    shipment = Shipment(
        order_id=4416,
        platform_shipment_id="DEMO-ORDER-0030",
        tracking_number="",
        carrier="Standard Shipping",
        status="approved",
    )
    monkeypatch.setattr(sync_engine, "_latest_shipment_for_order", lambda db, order_id: shipment)

    assert not _has_existing_platform_shipment(object(), order)

    shipment.tracking_number = "DEMO-TRACKING-0002"
    assert _has_existing_platform_shipment(object(), order)


def test_joom_status_refresh_without_tracking_does_not_create_placeholder_shipment(monkeypatch):
    order = Order(
        id=4416,
        tenant_id="default",
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        shop_id="JOOM-DEMO-001",
        platform_order_id="DEMO-ORDER-0030",
        platform_order_no="DEMO-ORDER-0030",
        posting_number="DEMO-ORDER-0030",
        platform_status="approved",
        biz_status="配货中",
        local_status="picking",
        raw_payload={},
    )
    update = OrderStatusUpdate(
        posting_number="DEMO-ORDER-0030",
        platform_order_id="DEMO-ORDER-0030",
        platform_order_no="DEMO-ORDER-0030",
        platform_status="approved",
        raw_payload={"id": "26VE349M", "status": "approved"},
    )

    def fail_upsert(*args, **kwargs):
        raise AssertionError("Joom status refresh without tracking should not create a shipment")

    monkeypatch.setattr(sync_engine, "_upsert_shipment_info", fail_upsert)

    result = _apply_status_update_to_order(object(), order, update)

    assert result["shipment_created"] is False
    assert result["shipment_updated"] is False


def test_ozon_pending_status_refresh_does_not_backfill_posting_as_tracking(monkeypatch):
    order = Order(
        id=15688,
        tenant_id="default",
        platform="ozon",
        account_id="100001",
        shop_id="100001",
        platform_order_id="DEMO-ORDER-0031",
        platform_order_no="DEMO-ORDER-0032",
        posting_number="DEMO-ORDER-0033",
        platform_status="awaiting_registration",
        biz_status="待处理",
        shipment_tracking_number="",
        raw_payload={},
        fulfillment_type="FBS",
    )
    update = OrderStatusUpdate(
        posting_number="DEMO-ORDER-0033",
        platform_order_id="DEMO-ORDER-0031",
        platform_order_no="DEMO-ORDER-0032",
        platform_status="awaiting_packaging",
        raw_payload={
            "posting_number": "DEMO-ORDER-0033",
            "status": "awaiting_packaging",
            "substatus": "posting_created",
        },
    )

    def fail_upsert(*args, **kwargs):
        raise AssertionError("Ozon pending posting number is not a real tracking number")

    monkeypatch.setattr(sync_engine, "_upsert_shipment_info", fail_upsert)

    result = _apply_status_update_to_order(object(), order, update)

    assert order.shipment_tracking_number == ""
    assert result["tracking_updated"] is False
    assert result["shipment_created"] is False


@pytest.mark.asyncio
async def test_order_sync_skips_existing_orders_with_tracking_and_real_label(monkeypatch):
    completed_order = Order(
        id=100,
        tenant_id="default",
        platform="ozon",
        account_id="100001",
        shop_id="100001",
        platform_order_id="DEMO-ORDER-0034",
        posting_number="DEMO-ORDER-0035",
        shipment_tracking_number="DEMO-TRACKING-0002",
        raw_payload={},
    )
    new_normalized = NormalizedOrder(
        platform_order_id="DEMO-ORDER-0036",
        posting_number="DEMO-ORDER-0037",
        platform_status="awaiting_deliver",
        raw_payload={},
    )
    completed_normalized = NormalizedOrder(
        platform_order_id="DEMO-ORDER-0034",
        posting_number="DEMO-ORDER-0035",
        platform_status="awaiting_deliver",
        raw_payload={},
    )
    upserted_order_ids: list[str] = []

    class FakeDb:
        def add(self, row):
            if isinstance(row, sync_engine.SyncJobLog):
                row.id = 99

        def commit(self):
            pass

        def flush(self):
            pass

        def scalar(self, _stmt):
            return None

    class FakeConnector:
        settings = {}

        async def fetch_unprocessed_orders(self, since=None):
            return [completed_normalized, new_normalized]

    def fake_find_existing_order(_db, _platform, _shop_id, normalized):
        if normalized.platform_order_id == completed_order.platform_order_id:
            return completed_order
        return None

    def fake_upsert_order(_db, _config, normalized):
        upserted_order_ids.append(normalized.platform_order_id)
        return Order(
            id=200,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id=normalized.platform_order_id,
            posting_number=normalized.posting_number,
            biz_status="已发货",
            local_status="label_saved",
            raw_payload={},
        )

    async def fake_repair_mercado_legacy_orders(*args, **kwargs):
        return 0

    async def fake_retry_wanbang_tracking_backfill_for_account(*args, **kwargs):
        return {"attempted": 0, "registered": 0, "existing": 0, "skipped": 0, "unsupported": 0, "failed": 0}

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())
    monkeypatch.setattr(sync_engine, "_repair_mercado_legacy_orders", fake_repair_mercado_legacy_orders)
    monkeypatch.setattr(sync_engine, "retry_wanbang_tracking_backfill_for_account", fake_retry_wanbang_tracking_backfill_for_account)
    monkeypatch.setattr(sync_engine, "_find_existing_order", fake_find_existing_order)
    monkeypatch.setattr(sync_engine, "_has_tracking_and_real_label", lambda _db, order: order is completed_order)
    monkeypatch.setattr(sync_engine, "upsert_order", fake_upsert_order)
    monkeypatch.setattr(sync_engine, "log_api_call", lambda **kwargs: None)
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: None)

    result = await sync_engine._sync_account_locked(
        FakeDb(),
        {
            "platform": "ozon",
            "account_id": "100001",
            "display_name": "Ozon",
            "settings": {},
        },
    )

    assert upserted_order_ids == ["DEMO-ORDER-0036"]
    assert result["orders"] == 1
    assert result["new"] == 1
    assert result["updated"] == 0
    assert result["skipped_completed_labels"] == 1


@pytest.mark.asyncio
async def test_order_sync_does_not_sync_logistics(monkeypatch):
    normalized = NormalizedOrder(
        platform_order_id="NEW-LOGISTICS-1",
        posting_number="DEMO-ORDER-0038",
        platform_status="awaiting_deliver",
        raw_payload={},
    )

    class FakeDb:
        def add(self, row):
            if isinstance(row, sync_engine.SyncJobLog):
                row.id = 100

        def commit(self):
            pass

        def flush(self):
            pass

        def scalar(self, _stmt):
            return None

    class FakeConnector:
        settings = {}

        async def fetch_unprocessed_orders(self, since=None):
            return [normalized]

        async def create_platform_shipment(self, order):
            raise AssertionError("order sync must not create platform shipments")

        async def fetch_label(self, shipment, order):
            raise AssertionError("order sync must not fetch labels")

    async def fake_repair_mercado_legacy_orders(*args, **kwargs):
        return 0

    async def fake_retry_wanbang_tracking_backfill_for_account(*args, **kwargs):
        return {"attempted": 0, "registered": 0, "existing": 0, "skipped": 0, "unsupported": 0, "failed": 0}

    def fake_upsert_order(_db, _config, normalized_order):
        return Order(
            id=201,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id=normalized_order.platform_order_id,
            posting_number=normalized_order.posting_number,
            biz_status="待处理",
            local_status="new",
            raw_payload={},
        )

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())
    monkeypatch.setattr(sync_engine, "_repair_mercado_legacy_orders", fake_repair_mercado_legacy_orders)
    monkeypatch.setattr(sync_engine, "retry_wanbang_tracking_backfill_for_account", fake_retry_wanbang_tracking_backfill_for_account)
    monkeypatch.setattr(sync_engine, "_find_existing_order", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync_engine, "upsert_order", fake_upsert_order)
    monkeypatch.setattr(sync_engine, "log_api_call", lambda **kwargs: None)
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: None)

    result = await sync_engine._sync_account_locked(
        FakeDb(),
        {
            "platform": "ozon",
            "account_id": "100001",
            "display_name": "Ozon",
            "settings": {},
        },
    )

    assert result["orders"] == 1
    assert "logistics" not in result
