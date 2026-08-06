# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime

from app.models import Order
from caifuclaw_business_app.scripts.import_excel_history_orders import order_tracking_candidates, parse_excel_local_datetime


def test_excel_picking_date_parses_as_local_midnight_in_utc_storage():
    assert parse_excel_local_datetime(datetime(2026, 1, 1, 0, 0, 0)) == datetime(2025, 12, 31, 16, 0, 0)


def test_order_tracking_candidates_deduplicates_order_numbers():
    order = Order(
        shipment_tracking_number="TRACK-1",
        posting_number="ORDER-1",
        platform_order_no="ORDER-1",
        platform_order_id="ORDER-1",
    )

    assert order_tracking_candidates(order) == [
        ("shipment_tracking_number", "TRACK-1"),
        ("posting_number", "ORDER-1"),
    ]
