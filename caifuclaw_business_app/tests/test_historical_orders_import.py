# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime
from types import SimpleNamespace

from app.models import Order
from scripts.import_historical_orders_2025_and_2026_gap import (
    LiveUpdate,
    OrderGroup,
    SourceRow,
    existing_match,
    group_items,
    identity_for_group,
    is_voided_status,
    normalize_allegro,
    parse_excel_local_datetime,
)


def _row(**overrides):
    values = {
        "row_no": 2,
        "platform_label": "allegro",
        "platform": "allegro",
        "shop_name": "Demo Shop",
        "account_id": "allegro-demo",
        "order_no": "DEMO-ORDER-0010",
        "country_code": "PL",
        "buyer_name": "Buyer",
        "sku": "SKU-1",
        "quantity": 1,
        "unit_price": "10",
        "currency": "PLN",
        "buyer_selected_logistics": "",
        "logistics_channel": "",
        "platform_deadline_at": None,
        "tracking_number": "DEMO-TRACKING-0002",
        "dispatch_deadline_at": None,
        "product_name": "Product",
        "order_type": "",
        "excel_status": "",
        "picking_at": None,
        "platform_created_at": datetime(2025, 1, 1),
        "shipped_at": None,
    }
    values.update(overrides)
    return SourceRow(**values)


def test_allegro_uuid_normalization_removes_hyphens_case_insensitively():
    assert normalize_allegro("ABC-def") == "abcdef"
    assert normalize_allegro("abcdef") == "abcdef"


def test_existing_match_skips_allegro_uuid_that_is_stored_with_hyphens():
    group = OrderGroup("allegro", "allegro0001", "Allegro Demo Shop", "abcdef", [_row(account_id="allegro0001", order_no="DEMO-ORDER-0011")])
    existing = Order(
        id=42,
        platform="allegro",
        account_id="allegro-demo",
        platform_order_id="DEMO-ORDER-0012",
        platform_order_no="DEMO-ORDER-0012",
        posting_number="DEMO-ORDER-0012",
        shipment_tracking_number="DEMO-TRACKING-0003",
    )
    indexes = {field: {} for field in ("platform_order_id", "platform_order_no", "posting_number", "tracking_number")}
    for field in ("platform_order_id", "platform_order_no", "posting_number"):
        indexes[field][("allegro", "allegro-demo", "ab-cd-ef")] = [existing]

    match = existing_match(group, indexes)

    assert match.row is existing
    assert match.reason == "allegro_uuid_normalized"


def test_group_items_sums_duplicate_sku_rows_without_touching_other_orders():
    group = OrderGroup(
        "joom_logistics",
        "JOOM-DEMO-001",
        "Joom Demo Shop",
        "ORDER-1",
        [
            _row(platform="joom_logistics", platform_label="Joom", account_id="JOOM-DEMO-001", order_no="ORDER-1", sku="SKU-1", quantity=1),
            _row(platform="joom_logistics", platform_label="Joom", account_id="JOOM-DEMO-001", order_no="ORDER-1", sku="SKU-1", quantity=2, row_no=3),
        ],
    )

    items = group_items(group)

    assert len(items) == 1
    assert items[0]["quantity"] == 3
    assert items[0]["row_numbers"] == [2, 3]


def test_2026_identity_uses_live_platform_fields():
    group = OrderGroup("joom_logistics", "JOOM-DEMO-001", "Joom Demo Shop", "DEMO-ORDER-001", [_row(platform="joom_logistics", account_id="JOOM-DEMO-001", order_no="DEMO-ORDER-001")], source="order_follow_up_2026_gap")
    live = LiveUpdate("shipped", "DEMO-ORDER-001", "DEMO-ORDER-001", "DEMO-ORDER-001", "DEMO-TRACK-001")

    assert identity_for_group(group, live) == ("DEMO-ORDER-001", "DEMO-ORDER-001", "DEMO-ORDER-001", "shipped")


def test_voided_status_detection_is_conservative_for_shipping_statuses():
    assert is_voided_status("cancelled_by_customer")
    assert is_voided_status("refunded")
    assert not is_voided_status("shipped")
    assert not is_voided_status("delivered")


def test_excel_picking_datetime_is_stored_as_utc_naive_value():
    assert parse_excel_local_datetime(datetime(2025, 1, 1, 0, 0, 0)) == datetime(2024, 12, 31, 16, 0, 0)
