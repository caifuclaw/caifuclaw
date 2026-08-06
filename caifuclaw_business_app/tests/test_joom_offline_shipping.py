from datetime import datetime
from types import SimpleNamespace

import pytest

from app import main, task_runner
from app.models import Order, ScheduledTask, ScheduledTaskRun
from app.order_types import (
    joom_offline_shipping_target_status,
    order_is_joom_fbj_warehouse,
    order_is_joom_offline_shipping,
)
from app.sync_engine import _refresh_biz_status_from_platform_snapshot, submit_platform_shipments_and_refresh_logistics


def _joom_order(**overrides):
    values = {
        "id": 1,
        "tenant_id": "default",
        "platform": "joom_logistics",
        "account_id": "JOOM-DEMO-001",
        "shop_id": "JOOM-DEMO-001",
        "shop_name": "Joom Demo Shop",
        "platform_order_id": "DEMO-ORDER-0014",
        "platform_order_no": "DEMO-ORDER-0014",
        "posting_number": "",
        "platform_status": "shipped",
        "biz_status": "待处理",
        "local_status": "shipment_created",
        "shipment_tracking_number": "DEMO-TRACKING-0004",
        "raw_payload": {
            "status": "shipped",
            "onlineShippingRequired": False,
            "onlineShippingRequirement": "offlineOnly",
            "allowedShippingTypes": "offlineOnly",
            "shippingMethod": "manual",
            "trackingNumber": "DEMO-TRACKING-001",
            "shipped_at": "2026-07-14T02:33:58Z",
        },
    }
    values.update(overrides)
    return Order(**values)


def test_joom_offline_shipping_detection_requires_authoritative_offline_fields():
    order = _joom_order()
    assert order_is_joom_offline_shipping(order)

    order.raw_payload = {"onlineShippingRequired": False, "shippingMethod": "manual"}
    assert order_is_joom_offline_shipping(order)

    order.raw_payload = {"onlineShippingRequired": True, "shippingMethod": "manual"}
    assert not order_is_joom_offline_shipping(order)


def test_joom_fbj_snapshot_stays_pending_until_follow_up_export_succeeds():
    order = _joom_order(
        platform_status="fulfilledOnline",
        fulfillment_type="FBJ",
        raw_payload={
            "fulfillmentType": "FBJ",
            "shippingOption": {"warehouseName": "Joom Logistics CN Warehouse", "warehouseType": "fulfillment"},
            "onlineShippingRequired": True,
        },
    )

    assert order_is_joom_fbj_warehouse(order)
    assert not _refresh_biz_status_from_platform_snapshot(order)
    assert order.biz_status == "待处理"

    order.biz_status = "FBJ待导出"
    assert _refresh_biz_status_from_platform_snapshot(order)
    assert order.biz_status == "待处理"

    order.biz_status = "已发货"
    assert not _refresh_biz_status_from_platform_snapshot(order)
    assert order.biz_status == "已发货"

    order.platform = "ozon"
    order.raw_payload = {"onlineShippingRequirement": "offlineOnly"}
    assert not order_is_joom_offline_shipping(order)


def test_joom_offline_shipped_requires_tracking_number():
    order = _joom_order(shipment_tracking_number="", raw_payload={
        "status": "shipped",
        "onlineShippingRequirement": "offlineOnly",
        "shippingMethod": "manual",
    })
    assert joom_offline_shipping_target_status(order) == ""

    order.shipment_tracking_number = "DEMO-TRACKING-0004"
    assert joom_offline_shipping_target_status(order) == "已发货"


def test_joom_offline_terminal_status_mapping():
    order = _joom_order(platform_status="delivered")
    assert joom_offline_shipping_target_status(order) == "已妥投"

    order.platform_status = "completed"
    assert joom_offline_shipping_target_status(order) == "已完成"

    order.platform_status = "cancelled"
    assert joom_offline_shipping_target_status(order) == "已作废"


def test_order_dto_exposes_joom_offline_shipping_flag():
    dto = main._order_dto(_joom_order())

    assert dto.is_joom_offline_shipping is True


def test_refresh_joom_offline_snapshot_marks_shipped_without_fake_print_or_manual_ship():
    order = _joom_order()

    changed = _refresh_biz_status_from_platform_snapshot(order)

    assert changed
    assert order.biz_status == "已发货"
    assert order.local_status == "shipped"
    assert order.shipped_at == datetime(2026, 7, 14, 2, 33, 58)
    assert order.label_printed_at is None
    assert order.marked_shipped_at is None


def test_refresh_joom_offline_snapshot_advances_existing_picking_order():
    order = _joom_order(biz_status="配货中", local_status="picking")

    changed = _refresh_biz_status_from_platform_snapshot(order)

    assert changed
    assert order.biz_status == "已发货"
    assert order.local_status == "shipped"


@pytest.mark.asyncio
async def test_submit_platform_shipments_skips_joom_offline_shipping():
    order = _joom_order()

    stats = await submit_platform_shipments_and_refresh_logistics(
        object(),
        [order],
        eligible_statuses={"待处理"},
    )

    assert stats["eligible"] == 0
    assert stats["submitted"] == 0
    assert stats["skipped_joom_offline_shipping"] == 1


@pytest.mark.asyncio
async def test_label_cache_skips_joom_offline_shipping_without_database_lookup():
    order = _joom_order()

    pdf_map, cached, fetched, failed = await main._ensure_labels_cached(object(), [order])

    assert pdf_map == {order.id: b""}
    assert (cached, fetched, failed) == (0, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("biz_status", "label_printed_at"),
    [("待处理", None), ("待采购", datetime(2026, 7, 14, 2, 35))],
)
async def test_auto_pipeline_marks_shipped_joom_offline_order_without_label_or_purchase(
    monkeypatch,
    biz_status,
    label_printed_at,
):
    order = SimpleNamespace(
        id=1,
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        shop_id="JOOM-DEMO-001",
        shop_name="Joom Demo Shop",
        platform_order_id="DEMO-ORDER-0014",
        platform_order_no="DEMO-ORDER-0014",
        posting_number="",
        platform_status="shipped",
        biz_status=biz_status,
        local_status="shipment_created",
        shipment_tracking_number="DEMO-TRACKING-0004",
        raw_payload={
            "onlineShippingRequirement": "offlineOnly",
            "shippingMethod": "manual",
            "trackingNumber": "DEMO-TRACKING-001",
        },
        handover_at=datetime(2026, 7, 14, 2, 33, 58),
        shipped_at=None,
        marked_shipped_at=None,
        label_printed_at=label_printed_at,
        error_message="old online label error",
        updated_at=None,
        is_overseas_warehouse=False,
        fulfillment_type="FBS",
    )
    run_orders = {}

    class FakeDb:
        def commit(self):
            pass

    def fake_upsert_run_order(db, run_id, row, **updates):
        run_order = run_orders.setdefault(row.id, SimpleNamespace(order_id=row.id))
        for key, value in updates.items():
            setattr(run_order, key, value)
        return run_order

    async def fake_refresh(*args, **kwargs):
        return {"eligible": 0}

    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_start_step", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(task_runner, "_finish_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "load_enabled_logistics_rules", lambda db: [])
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh)
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        task_runner,
        "split_logistics_rule_eligible_orders",
        lambda rows, *args, **kwargs: (
            (_ for _ in ()).throw(AssertionError("offline order must bypass logistics rules"))
            if order in rows
            else (rows, [])
        ),
    )
    monkeypatch.setattr(
        task_runner,
        "submit_platform_shipments_and_refresh_logistics",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("offline order must not submit logistics")),
    )
    monkeypatch.setattr(
        task_runner,
        "_ensure_labels_cached",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("offline order must not fetch labels")),
    )
    monkeypatch.setattr(
        task_runner,
        "_generate_purchase_order_for_orders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("offline shipped order must not create purchase")),
    )

    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})
    run = ScheduledTaskRun(id=1, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await task_runner._auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert order.biz_status == "已发货"
    assert order.local_status == "shipped"
    assert order.shipped_at == order.handover_at
    assert order.label_printed_at is label_printed_at
    assert order.marked_shipped_at is None
    assert order.error_message == ""
    assert stats["joom_offline_shipped_count"] == 1
    assert stats["shipped_count"] == 1
    assert "已直接转为已发货 1 条" in summary
    assert run_orders[order.id].print_message == "Joom 线下物流订单已由平台发货，跳过在线面单、打印和采购"
