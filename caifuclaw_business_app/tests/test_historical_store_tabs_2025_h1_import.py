import asyncio
from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.utils.datetime import to_excel

from app.models import Order
from scripts.import_historical_store_tabs_2025_h1 import (
    SHEET_CONFIGS,
    add_order_to_index,
    build_groups,
    connector_post_with_retries,
    deduplicated_rows,
    existing_match,
    group_amount,
    group_cancelled,
    group_items,
    initial_identity,
    parse_amount,
    parse_sheet_rows,
    reconciliation_report_stem,
    tracking_values,
)


def _config(sheet_name):
    return next(config for config in SHEET_CONFIGS if config.sheet == sheet_name)


def _worksheet(headers, rows, title="Sheet1"):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = title
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    return workbook, worksheet


def test_parse_amount_normalizes_currency_text_and_excel_serial_dates():
    excel_date = datetime(1900, 6, 1, 17, 47, 2, 400000)

    assert parse_amount("1 027") == Decimal("1027")
    assert parse_amount("131,00 ¥") == Decimal("131.00")
    assert parse_amount(excel_date) == Decimal(str(to_excel(excel_date)))


def test_fbp_groups_by_posting_and_uses_first_nonzero_order_total():
    config = _config("FBP订单")
    workbook, worksheet = _worksheet(
        [
            "Processing",
            "Shipment number",
            "Shipment details",
            "Order total ¥",
            "Warehouse",
            "Delivery agent and method",
            "中文名称",
            "备注",
            "客户确认",
        ],
        [
            [datetime(2025, 1, 1), "100-0001-1", "SKU-1", 331, "WH", "FBP", "One", None, "100"],
            [datetime(2025, 1, 1), "100-0001-1", "SKU-2", 0, "WH", "FBP", "Two", None, "100"],
            [datetime(2025, 1, 1), "100-0001-2", "SKU-3", 120, "WH", "FBP", "Three", None, "100"],
        ],
        config.sheet,
    )

    rows, issues = parse_sheet_rows(worksheet, config)
    groups = build_groups(rows)

    assert issues == []
    assert len(groups) == 2
    first_group = groups[0]
    assert first_group.order_no == "100-0001-1"
    assert group_amount(first_group) == Decimal("331")
    assert len(group_items(first_group)) == 2
    assert tracking_values(first_group) == []
    assert initial_identity(first_group) == ("100-0001-1", "100-0001", "100-0001-1")
    workbook.close()


def test_ozon_line_totals_are_summed_after_duplicate_rows_are_removed():
    config = _config("OZON-ECOMANGO")
    headers = [
        "Created Date",
        "Order number",
        "Shipment details",
        "Product quantity",
        "Order total",
        "Tracking number",
        "Warehouse",
        "Delivery agent and method",
        "Deadline",
        "中文名称",
        "待采购数量",
        "预警",
        "Shipping time",
        "status",
        "客户确认",
        "备注",
    ]
    row_one = [datetime(2025, 1, 1), "100-0001-1", "SKU-1", 1, 305, "T1", "WH", "L", None, "One", 1, "Delivered", None, "", "100", None]
    row_two = [datetime(2025, 1, 1), "100-0001-1", "SKU-2", 1, 330, "T1", "WH", "L", None, "Two", 1, "Delivered", None, "", "100", None]
    workbook, worksheet = _worksheet(headers, [row_one, row_one, row_two], config.sheet)

    rows, issues = parse_sheet_rows(worksheet, config)
    group = build_groups(rows)[0]
    deduped, removed = deduplicated_rows(group)

    assert issues == []
    assert len(deduped) == 2
    assert removed == [2]
    assert group_amount(group) == Decimal("635")
    assert [item["sku"] for item in group_items(group)] == ["SKU-1", "SKU-2"]
    workbook.close()


def test_allegro_blank_order_line_attaches_by_tracking_and_duplicate_is_removed():
    config = _config("Allegro")
    headers = [
        "Country",
        "Order date",
        "Order number",
        "SKU",
        "产品标题",
        "Units",
        "Buyer",
        "是否预售",
        "物流商",
        "Tracking number",
        "应收款金额",
        "产品名称",
        "备注",
        "采购成本",
        "备货时间",
        "预警",
        "发货时间",
    ]
    parent = ["Poland", datetime(2025, 6, 9), "ABCDEF", "SKU-1", "One", 1, "Buyer", None, "WB", "TRACK-1", 201.48, "One", None, 50, 3, "Delivered", datetime(2025, 6, 10)]
    child = [None, datetime(2025, 6, 9), None, "SKU-2", "Two", 1, None, None, None, "TRACK-1", None, "Two", None, 50, 3, "Delivered", datetime(2025, 6, 10)]
    workbook, worksheet = _worksheet(headers, [parent, child, parent], config.sheet)

    rows, issues = parse_sheet_rows(worksheet, config)
    groups = build_groups(rows)

    assert issues == []
    assert len(groups) == 1
    assert [row.order_no for row in rows] == ["ABCDEF", "ABCDEF", "ABCDEF"]
    assert group_amount(groups[0]) == Decimal("201.48")
    assert len(group_items(groups[0])) == 2
    assert tracking_values(groups[0]) == ["TRACK-1"]
    workbook.close()


def test_cancel_marker_is_detected_in_an_unlabelled_workbook_column():
    config = _config("OZON-SUPREME")
    headers = [
        "Created Date",
        "Order number",
        "Shipment details",
        "数量",
        "Order total",
        "Tracking number",
        "Warehouse",
        "Delivery agent and method",
        "Deadline",
        "Product name",
        "待采购数量",
        "预警",
        "Shipping time",
        "status",
        "客户确认",
        "备注",
        "采购成本",
        None,
    ]
    row = [datetime(2025, 1, 7), "100-0001-1", "SKU", 1, 21.48, "T1", "WH", "L", None, "Product", 1, "", None, "", "100", None, 30, "取消订单"]
    workbook, worksheet = _worksheet(headers, [row], config.sheet)

    rows, issues = parse_sheet_rows(worksheet, config)
    group = build_groups(rows)[0]

    assert issues == []
    assert group_cancelled(group)
    workbook.close()


def test_existing_allegro_order_is_matched_with_or_without_uuid_hyphens():
    config = _config("Allegro")
    workbook, worksheet = _worksheet(
        ["Country", "Order date", "Order number", "SKU", "Units", "Tracking number", "应收款金额"],
        [["Poland", datetime(2025, 1, 1), "11111111-2222-3333-4444-555555555555", "SKU", 1, "TRACK", 10]],
        config.sheet,
    )
    rows, issues = parse_sheet_rows(worksheet, config)
    group = build_groups(rows)[0]
    existing = Order(
        id=42,
        platform="allegro",
        account_id="allegro0002",
        shop_id="allegro0002",
        platform_order_id="11111111222233334444555555555555",
        platform_order_no="11111111222233334444555555555555",
        posting_number="11111111222233334444555555555555",
    )
    index = {}
    add_order_to_index(index, existing)

    match = existing_match(group, index)

    assert issues == []
    assert match.order_id == 42
    assert match.reason == "platform_order_id_same_account"
    workbook.close()


def test_connector_post_retries_transient_failures(monkeypatch):
    class Connector:
        calls = 0

        async def _post(self, _path, _payload):
            self.calls += 1
            if self.calls < 3:
                raise ConnectionError("temporary")
            return {"ok": True}

    async def no_sleep(_delay):
        return None

    connector = Connector()
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    result = asyncio.run(connector_post_with_retries(connector, "/orders", {}, attempts=3))

    assert result == {"ok": True}
    assert connector.calls == 3


def test_filtered_reconciliation_uses_a_separate_report_name():
    assert reconciliation_report_stem([], []) == "status_reconciliation"
    assert reconciliation_report_stem(["ozon"], ["100001"]) == "status_reconciliation_ozon_100001"
