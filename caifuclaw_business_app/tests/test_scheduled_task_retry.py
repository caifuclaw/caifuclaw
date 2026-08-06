# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from contextlib import contextmanager
from datetime import datetime, timedelta

from types import SimpleNamespace
import zipfile

import pytest

import app.task_runner as task_runner
import app.wanbang as wanbang_module
from app import email_service
from app import sync_engine
from app.connectors.base import ShipmentResult
from app.models import ScheduledTask, ScheduledTaskRun, ScheduledTaskRunOrder
from app.wanbang import (
    WANBANG_DEFAULT_BASE_URL,
    WanbangClient,
    WanbangApiError,
    WanbangLabelNotReady,
    WanbangReferenceLookupResult,
    allegro_order_uses_wanbang,
    build_wanbang_parcel_payload,
    create_wanbang_shipment_for_order,
    fetch_existing_wanbang_shipment_for_order,
    fetch_wanbang_label_for_order,
    order_uses_wanbang,
    run_wanbang_test_flow_for_order,
)
from app.email_service import apply_provider_preset, list_email_provider_presets
from app.pdf_tools import orient_pdf_bytes
from app.print_options import label_orientation_for_platform, label_size_mm_for_platform
from app.task_runner import (
    STEP_SYNC_ORDERS,
    _auto_order_pipeline_async,
    _ordered_platforms_for_print,
    _run_dto,
    _task_retry_count,
    _task_retry_interval_minutes,
    _task_logistics_ready_timeout_seconds,
    _task_timeout_seconds,
    _task_poll_interval_seconds,
    mark_stale_scheduled_task_runs,
)


@pytest.fixture(autouse=True)
def _stub_postgres_advisory_locks(monkeypatch):
    @contextmanager
    def acquired_lock(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(sync_engine, "sync_job_lock", acquired_lock)


def _blank_pdf(width: int, height: int) -> bytes:
    import io
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _first_page_size(pdf_bytes: bytes) -> tuple[int, int]:
    import io
    from pypdf import PdfReader

    page = PdfReader(io.BytesIO(pdf_bytes)).pages[0]
    return round(float(page.mediabox.width)), round(float(page.mediabox.height))


def test_scheduled_chinese_label_uses_mercado_payment_date_plus_three_days(monkeypatch):
    row = SimpleNamespace(
        id=101,
        platform="mercadolibre",
        payment_at=datetime(2026, 6, 10, 23, 30),
        platform_created_at=datetime(2026, 6, 9),
        created_at=datetime(2026, 6, 8),
        shipping_deadline_at=datetime(2026, 6, 30),
        raw_payload={},
    )
    monkeypatch.setattr(task_runner, "_order_chinese_product_name_map", lambda db, rows: {101: "测试商品"})
    monkeypatch.setattr(task_runner, "_order_tracking_number_value", lambda db, order: "TRACK-101")

    label_rows = task_runner._chinese_label_rows_for_orders(object(), [row])

    assert len(label_rows) == 1
    assert label_rows[0].deadline == datetime(2026, 6, 14).date()


def test_queue_joom_fbj_follow_up_export_skips_label_and_purchase_workflow(monkeypatch):
    order = SimpleNamespace(
        id=801,
        platform="joom_logistics",
        platform_order_no="DEMO-ORDER-0046",
        biz_status="待处理",
        local_status="shipment_created",
        error_message="面单同步失败",
        label_printed_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        updated_at=None,
    )
    run_orders = []
    logs = []

    class FakeDb:
        def commit(self):
            pass

    monkeypatch.setattr(
        task_runner,
        "_upsert_run_order",
        lambda _db, _run_id, row, **values: run_orders.append((row.id, values)),
    )
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: logs.append(kwargs))

    stats = {}
    task_runner._queue_joom_fbj_follow_up_export(FakeDb(), SimpleNamespace(id=81), [order], stats)

    assert order.biz_status == "待处理"
    assert order.local_status == "fbj_follow_up_pending"
    assert order.error_message == ""
    assert order.label_printed_at is None
    assert order.shipped_at is None
    assert order.marked_shipped_at is None
    assert stats["joom_fbj_follow_up_export_count"] == 1
    assert run_orders[-1][1]["print_submitted"] is False
    assert "不打印" in run_orders[0][1]["print_message"]
    assert logs[0]["operation_type"] == "fbj_follow_up_export_queued"


@pytest.mark.asyncio
async def test_auto_pipeline_keeps_fbj_pending_and_out_of_print_purchase_flow(monkeypatch):
    order = SimpleNamespace(
        id=802,
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        shop_id="JOOM-DEMO-001",
        shop_name="Joom Demo Shop",
        platform_order_id="DEMO-ORDER-0047",
        platform_order_no="DEMO-ORDER-0047",
        posting_number="",
        platform_status="fulfilledOnline",
        biz_status="待处理",
        local_status="new",
        fulfillment_type="FBJ",
        is_overseas_warehouse=False,
        raw_payload={
            "fulfillmentType": "FBJ",
            "shippingOption": {"warehouseName": "Joom Logistics CN Warehouse", "warehouseType": "fulfillment"},
        },
        error_message="",
        label_printed_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        updated_at=None,
    )
    run_orders = []

    class FakeDb:
        def commit(self):
            pass

    async def unexpected_normal_flow(*_args, **_kwargs):
        raise AssertionError("FBJ order must not enter the label, print, or purchase workflow")

    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda _db, _run: ([order], False))
    monkeypatch.setattr(task_runner, "_start_step", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(task_runner, "_finish_step", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        task_runner,
        "_upsert_run_order",
        lambda _db, _run_id, row, **values: run_orders.append((row.id, values)),
    )
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(task_runner, "load_enabled_logistics_rules", lambda _db: [])
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", unexpected_normal_flow)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", unexpected_normal_flow)

    status, _summary, stats = await task_runner._auto_order_pipeline_async(
        FakeDb(),
        SimpleNamespace(id=1),
        SimpleNamespace(id=82),
    )

    assert status == "success"
    assert order.biz_status == "待处理"
    assert order.local_status == "fbj_follow_up_pending"
    assert order.label_printed_at is None
    assert order.shipped_at is None
    assert order.marked_shipped_at is None
    assert stats["joom_fbj_follow_up_export_count"] == 1
    assert run_orders[-1][1]["print_submitted"] is False


def test_orient_pdf_bytes_rotates_page_to_requested_orientation():
    portrait_pdf = _blank_pdf(100, 200)
    landscape_pdf = orient_pdf_bytes(portrait_pdf, "landscape")

    assert _first_page_size(landscape_pdf) == (200, 100)
    assert orient_pdf_bytes(landscape_pdf, "landscape") == landscape_pdf
    assert _first_page_size(orient_pdf_bytes(landscape_pdf, "portrait")) == (100, 200)


def test_orient_pdf_bytes_resizes_ozon_label_to_80x100mm_stock():
    source_pdf = _blank_pdf(164, 113)
    resized = orient_pdf_bytes(
        source_pdf,
        label_orientation_for_platform("ozon", "landscape"),
        target_size_mm=label_size_mm_for_platform("ozon"),
    )

    assert _first_page_size(resized) == (227, 283)


def test_ozon_label_orientation_uses_stock_direction():
    assert label_orientation_for_platform("ozon", "landscape") == "portrait"


def test_allegro_order_uses_wanbang_only_when_rule_selected_wanbang():
    order = SimpleNamespace(
        platform="allegro",
        logistics_channel="万邦速达(新) / DEMO-CARRIER",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
    )
    assert allegro_order_uses_wanbang(order) is True

    order.logistics_channel = "BSI海外仓 / DEMO-CARRIER-3"
    order.logistics_carrier_code = "bsi_overseas"
    assert allegro_order_uses_wanbang(order) is False

    order.logistics_channel = "万邦速达(新) / DEMO-CARRIER"
    order.logistics_carrier_code = "wanbang_suda_new"
    order.logistics_match_status = "manual"
    assert allegro_order_uses_wanbang(order) is True

    order.logistics_match_status = "unmatched"
    assert allegro_order_uses_wanbang(order) is False

    order.platform = "ozon"
    order.logistics_match_status = "matched"
    assert allegro_order_uses_wanbang(order) is False


def test_dmsmatrix_order_uses_wanbang_when_internal_no_is_process_code():
    order = SimpleNamespace(
        platform="dmsmatrix",
        internal_order_no="WNBAA0000000001AA",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
    )
    assert order_uses_wanbang(order) is True

    order.logistics_carrier_code = "bsi_overseas"
    assert order_uses_wanbang(order) is False

    order.logistics_carrier_code = "wanbang_suda_new"
    order.internal_order_no = "LOCALORDER123456"
    assert order_uses_wanbang(order) is False


def test_dmsmatrix_wanbang_process_code_without_tracking_does_not_skip_sync(monkeypatch):
    order = SimpleNamespace(
        id=1,
        platform="dmsmatrix",
        internal_order_no="WNBAA0000000001AA",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
        shipment_tracking_number="",
        raw_payload={},
    )
    shipment = SimpleNamespace(
        platform_shipment_id="WNBAA0000000001AA",
        tracking_number="",
        carrier="WanbExpress",
        status="Confirmed",
    )

    monkeypatch.setattr(sync_engine, "_latest_shipment_for_order", lambda db, order_id: shipment)

    assert sync_engine._has_existing_platform_shipment(object(), order) is False

    shipment.tracking_number = "DEMO-TRACKING-0017"
    assert sync_engine._has_existing_platform_shipment(object(), order) is True


def test_move_logistics_rule_unmatched_to_shipped_updates_status_and_stats(monkeypatch):
    row = SimpleNamespace(
        id=1,
        platform="wildberries",
        platform_order_id="DEMO-ORDER-0015",
        platform_order_no="DEMO-ORDER-0015",
        posting_number="",
        biz_status=task_runner.ORDER_STATUS_PENDING,
        local_status="new",
        logistics_match_status="unmatched",
        logistics_channel="",
        shipped_at=None,
        marked_shipped_at=None,
        updated_at=None,
    )
    run = SimpleNamespace(id=9)
    stats = {}

    class FakeDb:
        def __init__(self):
            self.commits = 0

        def commit(self):
            self.commits += 1

    upserted = []
    monkeypatch.setattr(task_runner, "_upsert_run_order", lambda *args, **kwargs: upserted.append(kwargs))
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)

    db = FakeDb()
    task_runner._move_logistics_rule_unmatched_to_shipped(db, run, [row], stats)

    assert row.biz_status == task_runner.ORDER_STATUS_SHIPPED
    assert row.local_status == "shipped"
    assert row.shipped_at is not None
    assert row.marked_shipped_at is not None
    assert stats["logistics_rule_unmatched_shipped_count"] == 1
    assert stats["shipped_count"] == 1
    assert upserted[0]["status_after"] == task_runner.ORDER_STATUS_SHIPPED
    assert db.commits >= 1


def test_bsi_draft_records_provider_number_without_changing_order_flow(monkeypatch):
    row = SimpleNamespace(
        id=1,
        platform="joom_logistics",
        platform_order_id="DEMO-ORDER-0006",
        platform_order_no="DEMO-ORDER-0006",
        posting_number="",
        biz_status=task_runner.ORDER_STATUS_PENDING,
        local_status="new",
        shipment_tracking_number="",
        label_printed_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        error_message="existing issue",
        updated_at=None,
    )
    group = task_runner.BsiDraftGroupResult(
        rows=[row],
        status="succeeded",
        message="BSI draft created",
        provider_order_no="DEMO-ORDER-0003",
    )
    run = SimpleNamespace(id=9)
    stats = {"shipped_count": 3}

    class FakeDb:
        def __init__(self):
            self.commits = 0

        def commit(self):
            self.commits += 1

    run_orders = []
    logs = []
    monkeypatch.setattr(task_runner, "_upsert_run_order", lambda *args, **kwargs: run_orders.append(kwargs))
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: logs.append(kwargs))

    db = FakeDb()
    task_runner._record_bsi_draft_created(db, run, group, stats)

    assert row.biz_status == task_runner.ORDER_STATUS_PENDING
    assert row.local_status == "new"
    assert row.shipment_tracking_number == ""
    assert row.label_printed_at is None
    assert row.shipped_at is None
    assert row.marked_shipped_at is None
    assert row.error_message == "existing issue"
    assert row.updated_at is None
    assert row.bsi_order_no == "DEMO-ORDER-0003"
    assert row.bsi_submitted_at is not None
    assert stats["bsi_draft_succeeded_count"] == 1
    assert stats["bsi_draft_logged_count"] == 1
    assert stats["shipped_count"] == 3
    assert run_orders[0]["status_before"] == task_runner.ORDER_STATUS_PENDING
    assert run_orders[0]["status_after"] == task_runner.ORDER_STATUS_PENDING
    assert logs[0]["extra"]["provider_order_no"] == "DEMO-ORDER-0003"
    assert "不改变订单状态" in logs[0]["description"](row)
    assert db.commits >= 1


def test_wanbang_client_normalizes_sandbox_base_url_to_production():
    client = WanbangClient(
        {"customer_code": "DEMO-CARRIER", "token": "token"},
        {"base_url": "http://api-sbx.wanbexpress.com"},
    )

    assert client.base_url == WANBANG_DEFAULT_BASE_URL


def test_wanbang_client_allows_sandbox_base_url_for_explicit_test_script():
    client = WanbangClient(
        {"customer_code": "DEMO-CARRIER", "token": "token"},
        {"base_url": "http://api-sbx.wanbexpress.com", "allow_sandbox": True},
    )

    assert client.base_url == "http://api-sbx.wanbexpress.com"


def test_wanbang_trackpoints_extracts_reference_id():
    result = wanbang_module.wanbang_reference_lookup_from_trackpoints(
        {
            "Data": {
                "Match": "ParcelTrackingNumber",
                "TrackingNumber": "TRK-1",
                "Metadata": {
                    "ReferenceId": "REF-1",
                    "TrackItemId": "WNBAA0000000001AA",
                    "TrackingNumber": "TRK-1",
                },
            }
        }
    )

    assert result.reference_id == "REF-1"
    assert result.track_item_id == "WNBAA0000000001AA"
    assert result.tracking_number == "TRK-1"


def test_wanbang_trackpoints_unknown_does_not_extract_reference_id():
    result = wanbang_module.wanbang_reference_lookup_from_trackpoints(
        {"Data": {"Match": "Unknown", "Metadata": {"ReferenceId": "REF-1"}}}
    )

    assert result.reference_id == ""
    assert result.match == "Unknown"


@pytest.mark.asyncio
async def test_backfill_wanbang_reference_id_updates_generated_internal_no(monkeypatch):
    order = SimpleNamespace(
        id=1,
        platform="dmsmatrix",
        internal_order_no="1111111111111111",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
        shipment_tracking_number="TRK-1",
        raw_payload={},
        error_message="old",
        updated_at=None,
    )
    added_logs = []

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

        def flush(self):
            pass

    async def fake_lookup(db, row, tracking_number):
        assert row is order
        assert tracking_number == "TRK-1"
        return WanbangReferenceLookupResult(
            reference_id="REF-1",
            tracking_number="TRK-1",
            match="ParcelTrackingNumber",
            track_item_id="WNBAA0000000001AA",
            raw_response={"Data": {"Metadata": {"ReferenceId": "REF-1"}}},
        )

    monkeypatch.setattr(sync_engine, "fetch_wanbang_reference_id_by_tracking", fake_lookup)
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: added_logs.append(kwargs))

    stats = await sync_engine.backfill_wanbang_reference_id_for_order(FakeDb(), order, job_log_id=9)

    assert stats["attempted"] == 1
    assert stats["updated"] == 1
    assert order.internal_order_no == "REF-1"
    assert order.error_message == ""
    assert order.raw_payload["wanbang_trackpoints"]["track_item_id"] == "WNBAA0000000001AA"
    assert added_logs[0]["extra"]["job_log_id"] == 9


@pytest.mark.asyncio
async def test_backfill_wanbang_reference_id_skips_conflict(monkeypatch):
    order = SimpleNamespace(
        id=1,
        platform="dmsmatrix",
        internal_order_no="1111111111111111",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
        shipment_tracking_number="TRK-1",
        raw_payload={},
        error_message="",
    )
    conflict = SimpleNamespace(id=2, internal_order_no="REF-1")
    added_logs = []

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return conflict

    async def fake_lookup(db, row, tracking_number):
        return WanbangReferenceLookupResult(reference_id="REF-1", tracking_number=tracking_number, match="ParcelTrackingNumber")

    monkeypatch.setattr(sync_engine, "fetch_wanbang_reference_id_by_tracking", fake_lookup)
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: added_logs.append(kwargs))

    stats = await sync_engine.backfill_wanbang_reference_id_for_order(FakeDb(), order)

    assert stats["conflict"] == 1
    assert order.internal_order_no == "1111111111111111"
    assert "已被订单 2 使用" in order.error_message
    assert added_logs[0]["extra"]["conflict_order_id"] == 2


@pytest.mark.asyncio
async def test_backfill_wanbang_reference_id_skips_unknown_match(monkeypatch):
    order = SimpleNamespace(
        id=1,
        platform="dmsmatrix",
        internal_order_no="1111111111111111",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
        shipment_tracking_number="TRK-1",
        raw_payload={},
        error_message="",
    )

    class FakeDb:
        def scalar(self, *args, **kwargs):
            raise AssertionError("conflict query should not run without ReferenceId")

    async def fake_lookup(db, row, tracking_number):
        return WanbangReferenceLookupResult(match="Unknown", raw_response={"Data": {"Match": "Unknown"}})

    monkeypatch.setattr(sync_engine, "fetch_wanbang_reference_id_by_tracking", fake_lookup)

    stats = await sync_engine.backfill_wanbang_reference_id_for_order(FakeDb(), order)

    assert stats["attempted"] == 1
    assert stats["skipped"] == 1
    assert order.internal_order_no == "1111111111111111"
    assert order.raw_payload["wanbang_trackpoints"]["match"] == "Unknown"


@pytest.mark.asyncio
async def test_wanbang_label_uses_imported_internal_order_no_as_process_code(monkeypatch):
    order = SimpleNamespace(
        id=1,
        platform="allegro",
        internal_order_no="WNBAA0000000002BB",
        posting_number="DEMO-ORDER-0112",
        platform_order_id="DEMO-ORDER-0113",
        platform_order_no="DEMO-ORDER-0113",
        shipment_tracking_number="DEMO-TRACKING-0018",
        raw_payload={},
    )
    shipment = SimpleNamespace(
        platform_shipment_id="WNBAA0000000002BB",
        tracking_number="DEMO-TRACKING-0018",
        carrier="WanbExpress",
    )
    auth = SimpleNamespace(
        encrypted_credentials="encrypted",
        config_json={"base_url": "http://api-sbx.wanbexpress.com"},
        settings_json={},
    )
    calls = []

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return shipment

    class FakeClient:
        def __init__(self, credentials, settings):
            assert settings["base_url"] == "http://api-sbx.wanbexpress.com"

        async def get_parcel(self, process_code):
            calls.append(("parcel", process_code))
            if process_code == "WNBAA0000000002BB":
                return {
                    "Data": {
                        "ProcessCode": "WNBAA0000000002BB",
                        "FinalTrackingNumber": "DEMO-TRACKING-WB-0002",
                        "Status": "Created",
                    }
                }
            raise AssertionError("tracking number must not be queried as Wanbang ProcessCode")

        async def get_label(self, number, *, parcel_number_type="ProcessCode"):
            calls.append(("label", number, parcel_number_type))
            if number == "WNBAA0000000002BB" and parcel_number_type == "ProcessCode":
                return b"%PDF-1.4\nprocess label\n"
            raise AssertionError(f"unexpected label lookup: {number} {parcel_number_type}")

    monkeypatch.setattr("app.wanbang.resolve_wanbang_authorization", lambda db, row: auth)
    monkeypatch.setattr("app.wanbang._decrypt_credentials", lambda row: {"customer_code": "DEMO-CARRIER", "token": "token"})
    monkeypatch.setattr("app.wanbang.WanbangClient", FakeClient)

    label_result, shipment_result = await fetch_wanbang_label_for_order(FakeDb(), order)

    assert label_result.content.startswith(b"%PDF")
    assert label_result.raw_payload["wanbang_label_number"] == "WNBAA0000000002BB"
    assert label_result.raw_payload["wanbang_label_number_type"] == "ProcessCode"
    assert shipment_result.tracking_number == "DEMO-TRACKING-WB-0002"
    assert calls == [("parcel", "WNBAA0000000002BB"), ("label", "WNBAA0000000002BB", "ProcessCode")]


@pytest.mark.asyncio
async def test_fetch_existing_wanbang_shipment_uses_imported_internal_order_no(monkeypatch):
    order = SimpleNamespace(
        id=1,
        platform="dmsmatrix",
        internal_order_no="WNBAA0000000001AA",
        posting_number="DEMO-ORDER-0115",
        platform_order_id="DEMO-ORDER-0115",
        platform_order_no="DEMO-ORDER-0116",
        shipment_tracking_number="",
        raw_payload={},
    )
    auth = SimpleNamespace(
        encrypted_credentials="encrypted",
        config_json={"base_url": "http://api-sbx.wanbexpress.com"},
        settings_json={},
    )
    calls = []

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

    class FakeClient:
        def __init__(self, credentials, settings):
            assert settings["base_url"] == "http://api-sbx.wanbexpress.com"

        async def get_parcel(self, process_code):
            calls.append(("parcel", process_code))
            if process_code == "WNBAA0000000001AA":
                return {
                    "Data": {
                        "ProcessCode": "WNBAA0000000001AA",
                        "FinalTrackingNumber": "DEMO-TRACKING-WB-0001",
                        "Status": "Confirmed",
                    }
                }
            raise AssertionError(f"unexpected parcel lookup: {process_code}")

        async def create_parcel(self, payload):
            raise AssertionError("DMSMatrix imported Wanbang orders must not create another parcel")

    monkeypatch.setattr("app.wanbang.resolve_wanbang_authorization", lambda db, row: auth)
    monkeypatch.setattr("app.wanbang._decrypt_credentials", lambda row: {"customer_code": "DEMO-CARRIER", "token": "token"})
    monkeypatch.setattr("app.wanbang.WanbangClient", FakeClient)

    shipment_result = await fetch_existing_wanbang_shipment_for_order(FakeDb(), order)

    assert shipment_result.platform_shipment_id == "WNBAA0000000001AA"
    assert shipment_result.tracking_number == "DEMO-TRACKING-WB-0001"
    assert shipment_result.carrier == "WanbExpress"
    assert shipment_result.status == "Confirmed"
    assert calls == [("parcel", "WNBAA0000000001AA")]


@pytest.mark.asyncio
async def test_wanbang_label_keeps_reference_id_for_non_process_internal_order_no(monkeypatch):
    order = SimpleNamespace(
        id=1,
        platform="allegro",
        internal_order_no="LOCALORDER123456",
        posting_number="",
        platform_order_id="DEMO-ORDER-0113",
        platform_order_no="DEMO-ORDER-0113",
        shipment_tracking_number="DEMO-TRACKING-0018",
        raw_payload={},
    )
    shipment = SimpleNamespace(
        platform_shipment_id="DEMO-TRACKING-0018",
        tracking_number="DEMO-TRACKING-0018",
        carrier="WanbExpress",
    )
    auth = SimpleNamespace(
        encrypted_credentials="encrypted",
        config_json={"base_url": "http://api-sbx.wanbexpress.com"},
        settings_json={},
    )
    calls = []

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return shipment

    class FakeClient:
        def __init__(self, credentials, settings):
            assert settings["base_url"] == "http://api-sbx.wanbexpress.com"

        async def get_parcel(self, process_code):
            calls.append(("parcel", process_code))
            if process_code == "LOCALORDER123456":
                return {
                    "Data": {
                        "ProcessCode": "WNBAA0000000002BB",
                        "FinalTrackingNumber": "DEMO-TRACKING-WB-0002",
                        "Status": "Created",
                    }
                }
            raise AssertionError("tracking number must not be queried as Wanbang ProcessCode")

        async def get_label(self, number, *, parcel_number_type="ProcessCode"):
            calls.append(("label", number, parcel_number_type))
            if number == "LOCALORDER123456" and parcel_number_type == "ReferenceId":
                return b"%PDF-1.4\nreference label\n"
            raise AssertionError(f"unexpected label lookup: {number} {parcel_number_type}")

    monkeypatch.setattr("app.wanbang.resolve_wanbang_authorization", lambda db, row: auth)
    monkeypatch.setattr("app.wanbang._decrypt_credentials", lambda row: {"customer_code": "DEMO-CARRIER", "token": "token"})
    monkeypatch.setattr("app.wanbang.WanbangClient", FakeClient)

    label_result, shipment_result = await fetch_wanbang_label_for_order(FakeDb(), order)

    assert label_result.content.startswith(b"%PDF")
    assert label_result.raw_payload["wanbang_label_number"] == "LOCALORDER123456"
    assert label_result.raw_payload["wanbang_label_number_type"] == "ReferenceId"
    assert shipment_result.tracking_number == "DEMO-TRACKING-WB-0002"
    assert calls == [("parcel", "LOCALORDER123456"), ("label", "LOCALORDER123456", "ReferenceId")]


@pytest.mark.asyncio
async def test_wanbang_test_flow_confirms_waits_for_status_and_retries_label(monkeypatch):
    order = SimpleNamespace(id=1, platform_order_no="ORDER-1", posting_number="POST-1", platform_order_id="DEMO-ORDER-0080")
    auth = SimpleNamespace(account_name="万邦(测试用)", encrypted_credentials="encrypted", config_json={}, settings_json={})
    calls = []
    parcel_calls = {"count": 0}
    label_calls = {"count": 0}

    class FakeClient:
        def __init__(self, credentials, settings):
            pass

        async def create_parcel(self, payload):
            calls.append(("create", payload["AutoConfirm"]))
            return {"Data": {"ProcessCode": "PC-1", "Status": "Created"}}

        async def confirm_parcel(self, process_code):
            calls.append(("confirm", process_code))
            return {"Data": {"Status": "Confirmed"}}

        async def get_parcel(self, process_code):
            parcel_calls["count"] += 1
            calls.append(("parcel", process_code))
            status = "Created" if parcel_calls["count"] == 1 else "Confirmed"
            return {"Data": {"ProcessCode": process_code, "Status": status, "FinalTrackingNumber": "TRK-1"}}

        async def get_label(self, process_code, *, parcel_number_type="ProcessCode"):
            label_calls["count"] += 1
            calls.append(("label", process_code, parcel_number_type))
            if label_calls["count"] == 1:
                raise WanbangLabelNotReady("not ready")
            return b"%PDF-1.4\nwanbang label\n"

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("app.wanbang.resolve_wanbang_test_authorization", lambda db, row: auth)
    monkeypatch.setattr("app.wanbang._decrypt_credentials", lambda row: {"customer_code": "DEMO-CARRIER", "token": "token"})
    monkeypatch.setattr("app.wanbang.build_wanbang_parcel_payload", lambda db, row, config: {"ReferenceId": "REF-1", "AutoConfirm": False})
    monkeypatch.setattr("app.wanbang.WanbangClient", FakeClient)
    monkeypatch.setattr("app.wanbang.asyncio.sleep", fake_sleep)

    test_result, label_result, shipment_result = await run_wanbang_test_flow_for_order(None, order)

    assert test_result.process_code == "PC-1"
    assert test_result.parcel_status == "Confirmed"
    assert test_result.label_attempts == 2
    assert label_result.raw_payload["wanbang_label_number_type"] == "ProcessCode"
    assert shipment_result.tracking_number == "TRK-1"
    assert calls == [
        ("create", False),
        ("confirm", "PC-1"),
        ("parcel", "PC-1"),
        ("parcel", "PC-1"),
        ("label", "PC-1", "ProcessCode"),
        ("label", "PC-1", "ProcessCode"),
    ]


@pytest.mark.asyncio
async def test_wanbang_test_flow_does_not_fetch_label_until_status_processable(monkeypatch):
    order = SimpleNamespace(id=1, platform_order_no="ORDER-1", posting_number="POST-1", platform_order_id="DEMO-ORDER-0080")
    auth = SimpleNamespace(account_name="万邦(测试用)", encrypted_credentials="encrypted", config_json={}, settings_json={})
    calls = []

    class FakeClient:
        def __init__(self, credentials, settings):
            pass

        async def create_parcel(self, payload):
            calls.append(("create", payload["AutoConfirm"]))
            return {"Data": {"ProcessCode": "PC-1", "Status": "Created"}}

        async def get_parcel(self, process_code):
            calls.append(("parcel", process_code))
            return {"Data": {"ProcessCode": process_code, "Status": "Created"}}

        async def get_label(self, process_code, *, parcel_number_type="ProcessCode"):
            raise AssertionError("label must not be requested while Wanbang status is Created")

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("app.wanbang.resolve_wanbang_test_authorization", lambda db, row: auth)
    monkeypatch.setattr("app.wanbang._decrypt_credentials", lambda row: {"customer_code": "DEMO-CARRIER", "token": "token"})
    monkeypatch.setattr("app.wanbang.build_wanbang_parcel_payload", lambda db, row, config: {"ReferenceId": "REF-1", "AutoConfirm": True})
    monkeypatch.setattr("app.wanbang.WanbangClient", FakeClient)
    monkeypatch.setattr("app.wanbang.asyncio.sleep", fake_sleep)

    with pytest.raises(WanbangApiError, match="not ready for label"):
        await run_wanbang_test_flow_for_order(None, order, status_retry_attempts=2)

    assert calls == [("create", True), ("parcel", "PC-1"), ("parcel", "PC-1")]


def test_wanbang_tracking_ignores_tracking_process_status_code():
    result = wanbang_module._shipment_from_parcel(
        {
            "ProcessCode": "WNBAA0000000003CC",
            "Status": "Confirmed",
            "TrackingNumber": "",
            "FinalTrackingNumber": "",
            "TrackingNoProcessResult": {"Code": "Processing", "Message": ""},
        }
    )

    assert result.tracking_number == ""


def test_build_wanbang_payload_from_allegro_order():
    order = SimpleNamespace(
        id=1,
        platform="allegro",
        internal_order_no="WNBAA0000000002BB",
        platform_order_id="DEMO-ORDER-0113",
        platform_order_no="DEMO-ORDER-0113",
        posting_number="DEMO-ORDER-0113",
        currency="PLN",
        raw_payload={
            "delivery": {
                "address": {
                    "name": "Jan Kowalski",
                    "street": "Main 12",
                    "city": "Warsaw",
                    "zipCode": "00-001",
                    "countryCode": "PL",
                    "phoneNumber": "+48123456789",
                }
            },
            "buyer": {"email": "demo@example.invalid"},
            "products": [
                {"offer_id": "SKU-1", "name": "Demo product", "quantity": 2, "price": "3.50", "currency_code": "PLN"}
            ],
        },
    )

    class FakeDb:
        def scalars(self, *args, **kwargs):
            raise AssertionError("raw Allegro products should be used before querying order_items")

    payload = build_wanbang_parcel_payload(
        FakeDb(),
        order,
        {
            "warehouse_code": "SZ",
            "shipping_method": "3HPA",
            "default_weight_kg": "0.2",
            "default_declared_name_en": "book",
            "default_declared_name_cn": "goods",
            "default_declared_currency": "USD",
        },
    )

    assert payload["ReferenceId"] == "WNBAA0000000002BB"
    assert payload["WarehouseCode"] == "SZ"
    assert payload["ShippingMethod"] == "3HPA"
    assert payload["ShippingAddress"]["CountryCode"] == "PL"
    assert payload["ShippingAddress"]["Contacter"] == "Jan Kowalski"
    assert payload["ItemDetails"][0]["GoodsId"] == "SKU-1"
    assert payload["ItemDetails"][0]["GoodsTitle"] == "Demo product"
    assert payload["ItemDetails"][0]["DeclaredNameEn"] == "book"
    assert payload["ItemDetails"][0]["DeclaredNameCn"] == "goods"
    assert payload["ItemDetails"][0]["Quantity"] == 2
    assert payload["ItemDetails"][0]["DeclaredValue"] == {"Code": "PLN", "Value": 3.5}
    assert payload["TotalValue"] == {"Code": "PLN", "Value": 7.0}


def test_build_wanbang_payload_requires_order_or_item_declared_currency():
    order = SimpleNamespace(
        id=1,
        platform="allegro",
        internal_order_no="DEMO-ORDER-0117",
        platform_order_id="DEMO-ORDER-0113",
        platform_order_no="DEMO-ORDER-0113",
        posting_number="DEMO-ORDER-0113",
        currency="",
        raw_payload={
            "delivery": {
                "address": {
                    "name": "Jan Kowalski",
                    "street": "Main 12",
                    "city": "Warsaw",
                    "zipCode": "00-001",
                    "countryCode": "PL",
                    "phoneNumber": "+48123456789",
                }
            },
            "buyer": {"email": "demo@example.invalid"},
            "products": [{"offer_id": "SKU-1", "name": "Demo product", "quantity": 1, "price": "3.50"}],
        },
    )

    class FakeDb:
        def scalars(self, *args, **kwargs):
            raise AssertionError("raw Allegro products should be used before querying order_items")

    with pytest.raises(WanbangApiError, match="declared currency is required"):
        build_wanbang_parcel_payload(
            FakeDb(),
            order,
            {
                "warehouse_code": "SZ",
                "shipping_method": "3HPA",
                "default_declared_currency": "USD",
            },
        )


def test_build_wanbang_payload_infers_album_declared_names_from_allegro_item_reference_data():
    order = SimpleNamespace(
        id=1,
        platform="allegro",
        internal_order_no="DEMO-ORDER-0117",
        platform_order_id="DEMO-ORDER-0113",
        platform_order_no="DEMO-ORDER-0113",
        posting_number="DEMO-ORDER-0113",
        currency="PLN",
        raw_payload={
            "delivery": {
                "address": {
                    "name": "Jan Kowalski",
                    "street": "Main 12",
                    "city": "Warsaw",
                    "zipCode": "00-001",
                    "countryCode": "PL",
                    "phoneNumber": "+48123456789",
                }
            },
            "buyer": {"email": "demo@example.invalid"},
            "products": [
                {
                    "offer_id": "DEMO-OFFER-0001",
                    "name": "STRAY KIDS - [KARMA] 4th Album COMPACT",
                    "quantity": 1,
                    "price": "60.00",
                    "currency_code": "PLN",
                    "raw_payload": {
                        "offer": {
                            "external": {"id": "POP_Straykids_KRAMA_Compact"},
                        }
                    },
                }
            ],
        },
    )

    class FakeDb:
        def scalars(self, *args, **kwargs):
            raise AssertionError("raw Allegro products should be used before querying order_items")

    payload = build_wanbang_parcel_payload(
        FakeDb(),
        order,
        {
            "warehouse_code": "SZ",
            "shipping_method": "EUSLPHR",
            "default_declared_name_en": "goods",
            "default_declared_name_cn": "goods",
        },
    )

    assert payload["ItemDetails"][0]["DeclaredNameEn"] == "album"
    assert payload["ItemDetails"][0]["DeclaredNameCn"] == "相册"


@pytest.mark.asyncio
async def test_create_wanbang_payload_uses_allegro_product_offer_api(monkeypatch):
    order = SimpleNamespace(
        id=1,
        platform="allegro",
        account_id="allegro-demo",
        shop_id="allegro-demo",
        internal_order_no="DEMO-ORDER-0117",
        platform_order_id="DEMO-ORDER-0113",
        platform_order_no="DEMO-ORDER-0113",
        posting_number="DEMO-ORDER-0113",
        currency="PLN",
        raw_payload={
            "delivery": {
                "address": {
                    "firstName": "Jan",
                    "lastName": "Kowalski",
                    "street": "Main 12",
                    "city": "Warsaw",
                    "zipCode": "00-001",
                    "countryCode": "PL",
                    "phoneNumber": "+48123456789",
                }
            },
            "buyer": {"email": "demo@example.invalid"},
            "products": [
                {"offer_id": "DEMO-OFFER-0001", "name": "Demo product", "quantity": 2, "price": "3.50", "currency_code": "PLN"}
            ],
        },
    )
    auth = SimpleNamespace(
        encrypted_credentials=b"wanbang-creds",
        config_json={
            "warehouse_code": "SZ",
            "shipping_method": "3HPA",
            "default_weight_kg": "0.2",
            "length_cm": "1",
            "width_cm": "1",
            "height_cm": "1",
            "default_declared_name_cn": "goods",
        },
        settings_json={},
    )
    account = SimpleNamespace(
        account_id="allegro-demo",
        encrypted_credentials=b"allegro-creds",
        settings={"base_url": "https://api.allegro.test"},
    )
    captured = {}

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return account

        def scalars(self, *args, **kwargs):
            raise AssertionError("raw Allegro products should be used before querying order_items")

    class FakeCredentialManager:
        def decrypt_credentials(self, encrypted):
            if encrypted == b"allegro-creds":
                return {"access_token": "token"}
            return {"customer_code": "DEMO-CARRIER", "token": "wanbang-token"}

    class FakeWanbangClient:
        def __init__(self, credentials, settings):
            captured["wanbang_credentials"] = credentials
            captured["wanbang_settings"] = settings

        async def create_parcel(self, payload):
            captured["payload"] = payload
            return {"Data": {"ProcessCode": "PROC-1", "TrackingNumber": "TRACK-1"}}

        async def get_parcel(self, process_code):
            return {"Data": {"ProcessCode": process_code, "TrackingNumber": "TRACK-1"}}

    class FakeResponse:
        status_code = 200
        content = b"{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "DEMO-OFFER-0001",
                "name": "Demo product",
                "external": {"id": "SKU-FROM-ALLEGRO"},
                "productSet": [
                    {
                        "product": {
                            "parameters": [
                                {"id": "17448", "name": "Product weight with unit packaging", "values": ["0.23"]},
                                {"id": "223329", "name": "Product height", "values": ["30"]},
                                {"id": "223333", "name": "Product width", "values": ["23"]},
                                {"id": "223331", "name": "Product length", "values": ["2"]},
                            ]
                        }
                    }
                ],
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            captured["allegro_url"] = url
            captured["allegro_auth"] = headers.get("Authorization") if headers else ""
            return FakeResponse()

    monkeypatch.setattr("app.wanbang.resolve_wanbang_authorization", lambda db, row: auth)
    monkeypatch.setattr("app.wanbang._decrypt_credentials", lambda row: {"customer_code": "DEMO-CARRIER", "token": "wanbang-token"})
    monkeypatch.setattr("app.wanbang.get_credential_manager", lambda: FakeCredentialManager())
    monkeypatch.setattr("app.wanbang.WanbangClient", FakeWanbangClient)
    monkeypatch.setattr("app.wanbang.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.wanbang.log_api_call", lambda **kwargs: None)

    result = await create_wanbang_shipment_for_order(FakeDb(), order)

    assert result.platform_shipment_id == "PROC-1"
    assert result.tracking_number == "TRACK-1"
    assert captured["allegro_url"] == "https://api.allegro.test/sale/product-offers/DEMO-OFFER-0001"
    assert captured["allegro_auth"] == "Bearer token"
    payload = captured["payload"]
    assert payload["WeightInKg"] == 0.46
    assert payload["TotalVolume"] == {"Length": 2.0, "Width": 23.0, "Height": 30.0, "Unit": "CM"}
    assert payload["ItemDetails"][0]["GoodsId"] == "SKU-FROM-ALLEGRO"
    assert payload["ItemDetails"][0]["WeightInKg"] == 0.23


def test_ordered_platforms_for_print_groups_by_printer_setting_id_order():
    rows = [
        SimpleNamespace(platform="wildberries"),
        SimpleNamespace(platform="shein"),
        SimpleNamespace(platform="mercadolibre"),
        SimpleNamespace(platform="ozon"),
        SimpleNamespace(platform="joom_logistics"),
    ]
    printer_map = {
        "ozon": SimpleNamespace(platform="ozon", printer_name="Thermal-A"),
        "shein": SimpleNamespace(platform="shein", printer_name="Thermal-A"),
        "joom_logistics": SimpleNamespace(platform="joom_logistics", printer_name="Thermal-C"),
        "chinese_label": SimpleNamespace(platform="chinese_label", printer_name="A4"),
        "wildberries": SimpleNamespace(platform="wildberries", printer_name="Thermal-B"),
    }

    assert _ordered_platforms_for_print(rows, printer_map) == [
        "ozon",
        "shein",
        "joom_logistics",
        "wildberries",
        "mercadolibre",
    ]


def test_task_retry_settings_defaults_and_bounds():
    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})

    assert _task_retry_count(task) == 0
    assert _task_retry_interval_minutes(task) == 10
    assert _task_timeout_seconds(task) == 30 * 60
    assert _task_logistics_ready_timeout_seconds(task) == 10 * 60
    assert _task_poll_interval_seconds(task) == 180

    task.settings = {"retry_count": 99, "retry_interval_minutes": 0, "timeout_minutes": 0, "poll_interval_seconds": 1}

    assert _task_retry_count(task) == 20
    assert _task_retry_interval_minutes(task) == 1
    assert _task_timeout_seconds(task) == 60
    assert _task_poll_interval_seconds(task) == 10

    task.settings = {"interval_minutes": 7, "poll_interval_seconds": 1}

    assert _task_poll_interval_seconds(task) == 7 * 60


def test_logistics_ready_timeout_leaves_task_completion_buffer():
    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"timeout_minutes": 10},
    )

    assert _task_logistics_ready_timeout_seconds(task) == 9 * 60


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _StaleRunFakeDb:
    def __init__(self, *, tasks, runs, steps):
        self.tasks = {task.id: task for task in tasks}
        self.runs = runs
        self.steps = steps
        self.scalar_calls = 0

    def scalars(self, _stmt):
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return _FakeScalarResult(self.runs)
        return _FakeScalarResult([step for step in self.steps if step.status == "running" and step.ended_at is None])

    def get(self, model, item_id):
        if model is ScheduledTask:
            return self.tasks.get(item_id)
        return None


def test_mark_stale_scheduled_task_runs_fails_old_running_run_and_step():
    now = datetime(2026, 7, 1, 8, 0, 0)
    task = ScheduledTask(
        id=1,
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"timeout_minutes": 10},
        last_run_at=now - timedelta(minutes=30),
        last_status="running",
    )
    run = ScheduledTaskRun(
        id=10,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        status="running",
        stats_json={},
        started_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=20),
    )
    step = task_runner.ScheduledTaskRunStep(
        id=20,
        run_id=10,
        step_code="logistics_ready_wait",
        step_name="同步物流和面单并等待就绪",
        status="running",
        started_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=20),
    )
    db = _StaleRunFakeDb(tasks=[task], runs=[run], steps=[step])

    marked = mark_stale_scheduled_task_runs(db, now=now)

    assert marked == 1
    assert run.status == "failed"
    assert run.ended_at == now
    assert "watchdog 标记失败" in run.summary
    assert step.status == "failed"
    assert step.ended_at == now
    assert "watchdog 标记失败" in step.message
    assert task.last_status == "failed"
    assert task.last_run_at == now


def test_mark_stale_scheduled_task_runs_preserves_newer_task_status_and_recent_runs():
    now = datetime(2026, 7, 1, 8, 0, 0)
    task = ScheduledTask(
        id=1,
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"timeout_minutes": 10},
        last_run_at=now - timedelta(minutes=1),
        last_status="success",
        last_message="newer success",
    )
    stale_run = ScheduledTaskRun(
        id=10,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        status="running",
        stats_json={},
        started_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=20),
    )
    recent_run = ScheduledTaskRun(
        id=11,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        status="running",
        stats_json={},
        started_at=now - timedelta(minutes=5),
        created_at=now - timedelta(minutes=5),
    )
    db = _StaleRunFakeDb(tasks=[task], runs=[stale_run, recent_run], steps=[])

    marked = mark_stale_scheduled_task_runs(db, now=now)

    assert marked == 1
    assert stale_run.status == "failed"
    assert recent_run.status == "running"
    assert recent_run.ended_at is None
    assert task.last_status == "success"
    assert task.last_message == "newer success"


def test_run_dto_includes_retry_and_email_fields():
    now = datetime.utcnow()
    run = ScheduledTaskRun(
        id=10,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        trigger_mode="retry",
        status="waiting_retry",
        summary="boom",
        stats_json={},
        attempt_no=1,
        max_retry_count=3,
        parent_run_id=9,
        original_run_id=8,
        next_retry_at=now,
        retry_reason="boom",
        email_sent=False,
        email_error="",
        started_at=now,
        created_at=now,
    )

    data = _run_dto(run)

    assert data["attempt_no"] == 1
    assert data["max_retry_count"] == 3
    assert data["parent_run_id"] == 9
    assert data["original_run_id"] == 8
    assert data["next_retry_at"]
    assert data["retry_reason"] == "boom"
    assert data["email_sent"] is False


@pytest.mark.asyncio
async def test_auto_order_pipeline_skips_platform_fetch(monkeypatch):
    started_steps = []
    finished_steps = []

    def fake_start_step(db, run_id, step_key, step_name, stats):
        step = SimpleNamespace(step_key=step_key, step_name=step_name)
        started_steps.append((step_key, step_name, stats))
        return step

    def fake_finish_step(db, step, *, status, message, stats):
        finished_steps.append((step.step_key, status, message, stats))

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", fake_finish_step)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([], False))

    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})
    run = ScheduledTaskRun(id=25, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(object(), task, run)

    assert status == "success"
    assert summary == "没有待处理订单"
    assert stats["selected_orders"] == 0
    assert started_steps[0][0] == STEP_SYNC_ORDERS
    assert started_steps[0][1] == "跳过平台订单同步"
    assert finished_steps[0] == (
        STEP_SYNC_ORDERS,
        "success",
        "已跳过平台接口取数，仅处理系统已有订单",
        {"skipped": True, "source": "existing_orders"},
    )


@pytest.mark.asyncio
async def test_auto_order_pipeline_fails_when_print_submit_fails(monkeypatch):
    order = SimpleNamespace(
        id=101,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="DEMO-TRACKING-0019",
        picking_at=None,
        updated_at=None,
    )
    finished_steps = []
    run_orders = {}

    def fake_start_step(db, run_id, step_code, step_name, payload):
        return SimpleNamespace(step_code=step_code, step_name=step_name)

    def fake_finish_step(db, step, *, status, message, stats, payload=None):
        finished_steps.append((step.step_code, status, message, stats))

    def fake_upsert_run_order(db, run_id, order, **updates):
        row = run_orders.setdefault(order.id, SimpleNamespace(order_id=order.id))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    async def fake_logistics(db, rows, **kwargs):
        assert kwargs["eligible_statuses"] == {"待处理", "待打印"}
        return {}

    async def fake_refresh_status(db, rows, **kwargs):
        assert kwargs["eligible_statuses"] == {"待处理", "待打印"}
        return {}

    def fake_move_to_printing(db, rows):
        for row in rows:
            row.biz_status = "待打印"

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        return {order.id: _blank_pdf(164, 113)}, 0, 1, 0

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", fake_finish_step)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "load_enabled_logistics_rules", lambda db: [])
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_move_to_printing", fake_move_to_printing)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh_status)
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", fake_logistics)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)
    monkeypatch.setattr(task_runner, "_backup_merged_pdf", lambda platform, run_id, pdf_bytes: "/tmp/failed.pdf")
    monkeypatch.setattr(task_runner, "_printer_setting_map", lambda db: {"ozon": SimpleNamespace(printer_name="DemoPrinter")})
    monkeypatch.setattr(task_runner, "_run_printer_monitor_step", lambda db, task, run, printer_names: [])
    monkeypatch.setattr(task_runner, "_previous_printed_rows", lambda db, run: {})
    monkeypatch.setattr(task_runner, "_submit_pdf_to_printer", lambda *args, **kwargs: (False, "提交打印失败: offline"))
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))

    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"logistics_ready_timeout_seconds": 0},
    )
    run = ScheduledTaskRun(id=30, scheduled_task_id=1, task_type="auto_order_pipeline")

    with pytest.raises(RuntimeError, match="打印提交失败 1 个PDF"):
        await _auto_order_pipeline_async(object(), task, run)

    assert run_orders[order.id].pdf_generated is True
    assert run_orders[order.id].print_submitted is False
    assert run_orders[order.id].needs_reprint is True
    assert any(item[0] == task_runner.STEP_SUBMIT_PRINT and item[1] == "success" for item in finished_steps)
    assert not any(
        item[0] in {"generate_purchase_order", task_runner.STEP_MOVE_TO_PICKING}
        for item in finished_steps
    )


@pytest.mark.asyncio
async def test_auto_order_pipeline_generates_purchase_order_then_moves_to_picking(monkeypatch):
    order = SimpleNamespace(
        id=101,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="DEMO-TRACKING-0019",
        picking_at=None,
        updated_at=None,
    )
    finished_steps = []
    run_orders = {}
    run_documents = {}
    moved_order_ids = []
    purchase = SimpleNamespace(id=55, purchase_no="PO20260531-001")
    submitted_jobs = []

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([order])

        def commit(self):
            pass

    def fake_start_step(db, run_id, step_code, step_name, payload):
        return SimpleNamespace(step_code=step_code, step_name=step_name)

    def fake_finish_step(db, step, *, status, message, stats, payload=None):
        finished_steps.append((step.step_code, status, message, stats))

    def fake_upsert_run_order(db, run_id, order, **updates):
        row = run_orders.setdefault(order.id, SimpleNamespace(order_id=order.id))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    def fake_upsert_run_document(db, run_id, platform, **updates):
        row = run_documents.setdefault(platform, SimpleNamespace(order_id=0, platform=platform))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    async def fake_logistics(db, rows, **kwargs):
        return {"eligible": len(rows), "submitted": 0}

    async def fake_refresh_status(db, rows, **kwargs):
        return {"eligible": len(rows), "updated": 0}

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        return {order.id: _blank_pdf(164, 113)}, 0, 1, 0

    def fake_move_to_printing(db, rows):
        for row in rows:
            row.biz_status = "待打印"

    def fake_move_to_picking_after_purchase(db, rows, purchase_row):
        moved_order_ids.extend(row.id for row in rows)
        for row in rows:
            row.biz_status = "配货中"

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", fake_finish_step)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "_upsert_run_document", fake_upsert_run_document)
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_move_to_printing", fake_move_to_printing)
    monkeypatch.setattr(task_runner, "_generate_purchase_order_for_orders", lambda db, rows: purchase)
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", fake_move_to_picking_after_purchase)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh_status)
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", fake_logistics)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)
    monkeypatch.setattr(task_runner, "_chinese_label_rows_for_orders", lambda db, rows: [])
    monkeypatch.setattr(task_runner, "generate_chinese_label_pdf", lambda rows: _blank_pdf(100, 20))
    monkeypatch.setattr(task_runner, "_backup_merged_pdf", lambda platform, run_id, pdf_bytes: "/tmp/success.pdf")
    monkeypatch.setattr(
        task_runner,
        "_printer_setting_map",
        lambda db: {
            "ozon": SimpleNamespace(printer_name="DemoPrinter"),
            task_runner.PRINT_PLATFORM_CHINESE_LABEL: SimpleNamespace(printer_name="ChinesePrinter"),
        },
    )
    monkeypatch.setattr(task_runner, "_run_printer_monitor_step", lambda db, task, run, printer_names: [])
    monkeypatch.setattr(task_runner, "_previous_printed_rows", lambda db, run: {})
    monkeypatch.setattr(task_runner, "_local_now", lambda: datetime(2026, 6, 4, 10, 20, 30, 123456))
    monkeypatch.setattr(
        task_runner,
        "_submit_pdf_to_printer",
        lambda *args, **kwargs: submitted_jobs.append(kwargs.get("job_name")) or (True, "已提交打印队列"),
    )
    monkeypatch.setattr(task_runner, "_mark_labels_printed", lambda db, order_ids: None)
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))

    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"logistics_ready_timeout_seconds": 0},
    )
    run = ScheduledTaskRun(id=31, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert moved_order_ids == [order.id]
    assert stats["picking_count"] == 1
    assert stats["purchase_order_id"] == 55
    assert submitted_jobs == [
        "label_print_ozon_20260604102030123456.pdf",
        "label_print_chinese_label_20260604102030123456.pdf",
    ]
    assert run_orders[order.id].print_job_name == "label_print_ozon_20260604102030123456.pdf"
    assert run_documents[task_runner.PRINT_PLATFORM_CHINESE_LABEL].print_job_name == "label_print_chinese_label_20260604102030123456.pdf"
    assert "采购单 PO20260531-001" in summary
    assert any(item[0] == "generate_purchase_order" and item[1] == "success" for item in finished_steps)
    assert any(item[0] == task_runner.STEP_MOVE_TO_PICKING and item[1] == "success" for item in finished_steps)


@pytest.mark.asyncio
async def test_auto_order_pipeline_only_prints_logistics_and_label_ready_orders(monkeypatch):
    ready_order = SimpleNamespace(
        id=101,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="DEMO-TRACKING-0019",
        picking_at=None,
        updated_at=None,
    )
    pending_order = SimpleNamespace(
        id=102,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="",
        error_message="",
        picking_at=None,
        updated_at=None,
        created_at=datetime.utcnow() - timedelta(hours=25),
        payment_at=None,
        platform_created_at=None,
    )
    run_orders = {}
    moved_to_printing = []
    notices = []
    purchase = SimpleNamespace(id=77, purchase_no="PO20260531-002")

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([ready_order])

        def commit(self):
            pass

    def fake_start_step(db, run_id, step_code, step_name, payload):
        return SimpleNamespace(step_code=step_code, step_name=step_name)

    def fake_finish_step(db, step, *, status, message, stats, payload=None):
        return None

    def fake_upsert_run_order(db, run_id, order, **updates):
        row = run_orders.setdefault(order.id, SimpleNamespace(order_id=order.id))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    async def fake_logistics(db, rows, **kwargs):
        assert {row.id for row in rows} == {pending_order.id}
        assert kwargs["eligible_statuses"] == {"待处理", "待打印"}
        return {"eligible": len(rows), "submitted": 0}

    async def fake_refresh_status(db, rows, **kwargs):
        assert {row.id for row in rows} == {ready_order.id, pending_order.id}
        assert kwargs["eligible_statuses"] == {"待处理", "待打印"}
        return {"eligible": len(rows), "updated": 0}

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        return {ready_order.id: _blank_pdf(164, 113)}, 0, 1, 0

    def fake_move_to_printing(db, rows):
        moved_to_printing.extend(row.id for row in rows)
        for row in rows:
            row.biz_status = "待打印"

    def fake_notice(db, task, rows):
        notices.extend(row.id for row in rows)
        return len(rows), "已发送24小时物流/面单超时通知 1 条"

    def fake_move_to_picking_after_purchase(db, rows, purchase_row):
        for row in rows:
            row.biz_status = "配货中"

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", fake_finish_step)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([ready_order, pending_order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_move_to_printing", fake_move_to_printing)
    monkeypatch.setattr(task_runner, "_notify_stale_logistics_pending_orders", fake_notice)
    monkeypatch.setattr(task_runner, "_latest_shipment", lambda db, order_id: None)
    monkeypatch.setattr(task_runner, "_generate_purchase_order_for_orders", lambda db, rows: purchase)
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", fake_move_to_picking_after_purchase)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh_status)
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", fake_logistics)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)
    monkeypatch.setattr(task_runner, "_backup_merged_pdf", lambda platform, run_id, pdf_bytes: "/tmp/ready-only.pdf")
    monkeypatch.setattr(task_runner, "_printer_setting_map", lambda db: {"ozon": SimpleNamespace(printer_name="DemoPrinter")})
    monkeypatch.setattr(task_runner, "_run_printer_monitor_step", lambda db, task, run, printer_names: [])
    monkeypatch.setattr(task_runner, "_previous_printed_rows", lambda db, run: {})
    monkeypatch.setattr(task_runner, "_submit_pdf_to_printer", lambda *args, **kwargs: (True, "已提交打印队列"))
    monkeypatch.setattr(task_runner, "_mark_labels_printed", lambda db, order_ids: None)
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))

    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"logistics_ready_timeout_seconds": 0},
    )
    run = ScheduledTaskRun(id=32, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert moved_to_printing == [ready_order.id]
    assert notices == [pending_order.id]
    assert not getattr(run_orders[pending_order.id], "print_submitted", False)
    assert run_orders[pending_order.id].error_message == "待平台返回货运单号和真实面单，暂不打印"
    assert stats["logistics_ready_count"] == 1
    assert stats["tracking_pending_count"] == 1
    assert stats["stale_logistics_notice_count"] == 1
    assert stats["purchase_order_id"] == 77
    assert "PO20260531-002" in summary


@pytest.mark.asyncio
async def test_readiness_only_resolves_mercadolibre_delivered_tracking_without_label(monkeypatch):
    delivered_order = SimpleNamespace(
        id=101,
        platform="mercadolibre",
        platform_status="delivered",
        shipment_tracking_number="MEL-TRACK-101",
        raw_payload={},
        is_overseas_warehouse=False,
    )
    shipped_order = SimpleNamespace(
        id=102,
        platform="mercadolibre",
        platform_status="shipped",
        shipment_tracking_number="MEL-TRACK-102",
        raw_payload={},
        is_overseas_warehouse=False,
    )
    other_platform_order = SimpleNamespace(
        id=103,
        platform="ozon",
        platform_status="delivered",
        shipment_tracking_number="OZON-TRACK-103",
        raw_payload={},
        is_overseas_warehouse=False,
    )

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        assert {row.id for row in rows} == {102, 103}
        return {}, 0, 0, 2

    monkeypatch.setattr(task_runner, "_latest_shipment", lambda db, order_id: None)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)

    stats = await task_runner._append_readiness_stats(
        object(),
        [delivered_order, shipped_order, other_platform_order],
        {"stage": "status_refresh"},
    )
    ready_rows, readiness = task_runner._ready_rows_from_sync_stats(
        [delivered_order, shipped_order, other_platform_order],
        stats,
    )

    assert ready_rows == []
    assert stats["delivered_without_label_order_ids"] == [delivered_order.id]
    assert readiness["delivered_without_label_order_ids"] == [delivered_order.id]
    assert readiness["resolved_order_ids"] == [delivered_order.id]
    assert readiness["label_pending_count"] == 2


@pytest.mark.asyncio
async def test_auto_order_pipeline_marks_delivered_mercadolibre_without_label_shipped(monkeypatch):
    order = SimpleNamespace(
        id=104,
        platform="mercadolibre",
        account_id="mercado-demo",
        shop_id="mercado-demo",
        shop_name="Mercado Demo Shop",
        platform_order_id="DEMO-ORDER-0118",
        platform_order_no="DEMO-ORDER-0118",
        posting_number="DEMO-ORDER-0119",
        platform_status="delivered",
        biz_status="待处理",
        local_status="shipment_created",
        shipment_tracking_number="DEMO-TRACKING-0020",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        picking_at=None,
        handover_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        label_printed_at=None,
        error_message="面单同步失败：401 Unauthorized",
        updated_at=None,
    )
    run_orders = {}
    operation_logs = []
    label_fetches = []

    class FakeDb:
        def commit(self):
            pass

    def fake_upsert_run_order(db, run_id, row, **updates):
        run_order = run_orders.setdefault(row.id, SimpleNamespace(order_id=row.id))
        for key, value in updates.items():
            setattr(run_order, key, value)
        return run_order

    async def fake_refresh_status(db, rows, **kwargs):
        assert [row.id for row in rows] == [order.id]
        return {"eligible": 1, "updated": 0}

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        label_fetches.extend(row.id for row in rows)
        return {}, 0, 0, 1

    monkeypatch.setattr(task_runner, "_start_step", lambda *args, **kwargs: SimpleNamespace(step_code=args[2]))
    monkeypatch.setattr(task_runner, "_finish_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: operation_logs.append((args, kwargs)))
    monkeypatch.setattr(task_runner, "load_enabled_logistics_rules", lambda db: [])
    monkeypatch.setattr(task_runner, "_latest_shipment", lambda db, order_id: None)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh_status)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)
    monkeypatch.setattr(
        task_runner,
        "submit_platform_shipments_and_refresh_logistics",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("delivered order should not submit logistics")),
    )

    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"logistics_ready_timeout_seconds": 600},
    )
    run = ScheduledTaskRun(id=39, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert label_fetches == []
    assert order.biz_status == "已发货"
    assert order.local_status == "shipped"
    assert order.shipped_at is not None
    assert order.marked_shipped_at is not None
    assert order.label_printed_at is None
    assert order.error_message == ""
    assert run_orders[order.id].status_after == "已发货"
    assert run_orders[order.id].print_message == "MercadoLibre订单已妥投且无法再下载真实面单，跳过打印、采购和配货并转为已发货"
    assert stats["delivered_without_label_shipped_count"] == 1
    assert stats["shipped_count"] == 1
    assert stats["purchase_order_id"] is None
    assert "已直接转为已发货 1 条" in summary
    assert operation_logs


@pytest.mark.asyncio
async def test_auto_order_pipeline_waits_until_timeout_before_partial_print(monkeypatch):
    ready_order = SimpleNamespace(
        id=101,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="DEMO-TRACKING-0019",
        picking_at=None,
        updated_at=None,
        created_at=datetime.utcnow(),
        payment_at=None,
        platform_created_at=None,
    )
    pending_order = SimpleNamespace(
        id=102,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="",
        picking_at=None,
        updated_at=None,
        created_at=datetime.utcnow(),
        payment_at=None,
        platform_created_at=None,
    )
    run_orders = {}
    moved_to_printing = []
    sleep_calls = []
    clock = {"value": 0.0}
    purchase = SimpleNamespace(id=78, purchase_no="PO20260531-004")

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([ready_order])

        def commit(self):
            pass

    def fake_start_step(db, run_id, step_code, step_name, payload):
        return SimpleNamespace(step_code=step_code, step_name=step_name)

    def fake_upsert_run_order(db, run_id, order, **updates):
        row = run_orders.setdefault(order.id, SimpleNamespace(order_id=order.id))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    async def fake_refresh_status(db, rows, **kwargs):
        return {"eligible": len(rows), "updated": 0}

    async def fake_logistics(db, rows, **kwargs):
        return {"eligible": len(rows), "submitted": 0}

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        return {ready_order.id: _blank_pdf(164, 113)}, 0, 1, 0

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        clock["value"] += seconds

    def fake_monotonic():
        return clock["value"]

    def fake_move_to_printing(db, rows):
        moved_to_printing.extend(row.id for row in rows)
        for row in rows:
            row.biz_status = "待打印"

    def fake_move_to_picking_after_purchase(db, rows, purchase_row):
        for row in rows:
            row.biz_status = "配货中"

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([ready_order, pending_order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_move_to_printing", fake_move_to_printing)
    monkeypatch.setattr(task_runner, "_notify_stale_logistics_pending_orders", lambda db, task, rows: (0, "没有超过24小时仍未就绪的订单"))
    monkeypatch.setattr(task_runner, "_latest_shipment", lambda db, order_id: None)
    monkeypatch.setattr(task_runner, "_generate_purchase_order_for_orders", lambda db, rows: purchase)
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", fake_move_to_picking_after_purchase)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh_status)
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", fake_logistics)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)
    monkeypatch.setattr(task_runner.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(task_runner.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(task_runner, "_backup_merged_pdf", lambda platform, run_id, pdf_bytes: "/tmp/waited-partial.pdf")
    monkeypatch.setattr(task_runner, "_printer_setting_map", lambda db: {"ozon": SimpleNamespace(printer_name="DemoPrinter")})
    monkeypatch.setattr(task_runner, "_run_printer_monitor_step", lambda db, task, run, printer_names: [])
    monkeypatch.setattr(task_runner, "_previous_printed_rows", lambda db, run: {})
    monkeypatch.setattr(task_runner, "_submit_pdf_to_printer", lambda *args, **kwargs: (True, "已提交打印队列"))
    monkeypatch.setattr(task_runner, "_mark_labels_printed", lambda db, order_ids: None)
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))

    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"logistics_ready_timeout_seconds": 2, "logistics_ready_poll_seconds": 1},
    )
    run = ScheduledTaskRun(id=36, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert len(sleep_calls) >= 1
    assert sum(sleep_calls) == pytest.approx(2, abs=0.01)
    assert moved_to_printing == [ready_order.id]
    assert run_orders[pending_order.id].error_message == "待平台返回货运单号和真实面单，暂不打印"
    assert stats["logistics_wait_timed_out"] is True
    assert stats["tracking_pending_count"] == 1
    assert stats["purchase_order_id"] == 78
    assert "PO20260531-004" in summary


@pytest.mark.asyncio
async def test_auto_order_pipeline_creates_joom_bsi_draft_before_generic_overseas_handling(monkeypatch):
    order = SimpleNamespace(
        id=201,
        platform="joom_logistics",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="",
        picking_at=None,
        updated_at=None,
        label_printed_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        is_overseas_warehouse=False,
        fulfillment_type="PHYSICAL",
        raw_payload={"shippingOption": {"warehouseName": "BSI-PL", "warehouseType": "physical"}},
    )
    run_orders = {}

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([order])

        def commit(self):
            pass

    def fake_upsert_run_order(db, run_id, order, **updates):
        row = run_orders.setdefault(order.id, SimpleNamespace(order_id=order.id))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    monkeypatch.setattr(task_runner, "_start_step", lambda db, run_id, step_code, step_name, payload: SimpleNamespace(step_code=step_code, step_name=step_name))
    monkeypatch.setattr(task_runner, "_finish_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(
        task_runner,
        "load_enabled_logistics_rules",
        lambda _db: [
            SimpleNamespace(
                id=1,
                name="Joom BSI",
                platform="joom_logistics",
                priority=10,
                enabled=True,
                shop_names=[],
                is_overseas_warehouse=True,
                country_codes=[],
                logistics_channel="BSI海外仓 / DEMO-CARRIER-3",
                carrier_code="bsi_overseas",
            )
        ],
    )
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        task_runner,
        "_generate_purchase_order_for_orders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("BSI draft should not generate purchase orders")),
    )
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("BSI draft should not refresh logistics")))
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("BSI draft should not sync logistics")))
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("BSI draft should not fetch labels")))

    async def fake_process_bsi_drafts(_db, rows):
        assert rows == [order]
        group = task_runner.BsiDraftGroupResult(
            rows=[order],
            status="succeeded",
            message="created",
            provider_order_no="BSI-JOOM-201",
        )
        return SimpleNamespace(groups=[group], succeeded_group_count=1, waiting_group_count=0, succeeded_rows=[order])

    monkeypatch.setattr(task_runner, "process_bsi_drafts", fake_process_bsi_drafts)

    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})
    run = ScheduledTaskRun(id=35, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert order.label_printed_at is None
    assert order.biz_status == "待处理"
    assert order.local_status == "new"
    assert order.shipped_at is None
    assert order.marked_shipped_at is None
    assert order.bsi_order_no == "BSI-JOOM-201"
    assert run_orders[order.id].status_before == "待处理"
    assert run_orders[order.id].status_after == "待处理"
    assert run_orders[order.id].print_submitted is False
    assert run_orders[order.id].pdf_generated is False
    assert stats["selected_orders"] == 1
    assert stats["bsi_draft_succeeded_count"] == 1
    assert stats["overseas_warehouse_skipped_count"] == 0
    assert stats["purchase_order_id"] is None
    assert stats["shipped_count"] == 0
    assert summary.startswith("任务完成")


@pytest.mark.asyncio
async def test_auto_order_pipeline_skips_wildberries_russia_logistics_and_label(monkeypatch):
    order = SimpleNamespace(
        id=202,
        platform="wildberries",
        account_id="wb-ru-store",
        shop_id="wb-ru-store",
        shop_name="Any WB Store",
        biz_status="待处理",
        local_status="new",
        country_code="RU",
        country_name_cn="俄罗斯",
        shipment_tracking_number="",
        picking_at=None,
        updated_at=None,
        label_printed_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        is_overseas_warehouse=False,
        fulfillment_type="FBS",
        raw_payload={},
    )
    run_orders = {}
    moved_order_ids = []

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([order])

        def commit(self):
            pass

    def fake_upsert_run_order(db, run_id, order, **updates):
        row = run_orders.setdefault(order.id, SimpleNamespace(order_id=order.id))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    def fake_move_to_picking_after_purchase(db, rows, purchase_row):
        moved_order_ids.extend(row.id for row in rows)
        for row in rows:
            row.biz_status = "配货中"

    monkeypatch.setattr(task_runner, "_start_step", lambda db, run_id, step_code, step_name, payload: SimpleNamespace(step_code=step_code, step_name=step_name))
    monkeypatch.setattr(task_runner, "_finish_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        task_runner,
        "_generate_purchase_order_for_orders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("exempt order should not generate purchase orders")),
    )
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", fake_move_to_picking_after_purchase)
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("exempt order should not refresh logistics")))
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("exempt order should not sync logistics")))
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("exempt order should not fetch labels")))

    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})
    run = ScheduledTaskRun(id=37, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert order.label_printed_at is not None
    assert order.biz_status == "已发货"
    assert order.local_status == "shipped"
    assert order.shipped_at is not None
    assert order.marked_shipped_at is not None
    assert moved_order_ids == []
    assert run_orders[order.id].print_message == "该订单无需获取平台货运单号、面单和采购，已转为已发货"
    assert stats["logistics_label_exempt_skipped_count"] == 1
    assert stats["purchase_order_id"] is None
    assert stats["shipped_count"] == 1
    assert "已直接转为已发货 1 条" in summary


@pytest.mark.asyncio
async def test_auto_order_pipeline_ships_waiting_purchase_label_exempt_without_purchase(monkeypatch):
    order = SimpleNamespace(
        id=203,
        platform="wildberries",
        account_id="wb-ru-store",
        shop_id="wb-ru-store",
        shop_name="Any WB Store",
        biz_status="待采购",
        local_status="label_saved",
        country_code="RU",
        country_name_cn="俄罗斯",
        shipment_tracking_number="",
        picking_at=None,
        updated_at=None,
        label_printed_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        is_overseas_warehouse=False,
        fulfillment_type="FBS",
        raw_payload={},
    )
    run_orders = {}

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([order])

        def commit(self):
            pass

    def fake_upsert_run_order(db, run_id, order, **updates):
        row = run_orders.setdefault(order.id, SimpleNamespace(order_id=order.id))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    monkeypatch.setattr(task_runner, "_start_step", lambda db, run_id, step_code, step_name, payload: SimpleNamespace(step_code=step_code, step_name=step_name))
    monkeypatch.setattr(task_runner, "_finish_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "load_enabled_logistics_rules", lambda db: [])
    monkeypatch.setattr(
        task_runner,
        "_generate_purchase_order_for_orders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("waiting-purchase exempt order should not generate purchase orders")),
    )
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("waiting-purchase exempt order should not move to picking")))

    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})
    run = ScheduledTaskRun(id=38, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert order.biz_status == "已发货"
    assert order.local_status == "shipped"
    assert order.label_printed_at is not None
    assert order.shipped_at is not None
    assert order.marked_shipped_at is not None
    assert run_orders[order.id].print_message == "该订单无需获取平台货运单号、面单和采购，已转为已发货"
    assert stats["purchase_order_id"] is None
    assert stats["shipped_count"] == 1
    assert "已直接转为已发货 1 条" in summary


@pytest.mark.asyncio
async def test_auto_order_pipeline_refreshes_status_before_logistics_sync(monkeypatch):
    ready_order = SimpleNamespace(
        id=101,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="",
        picking_at=None,
        updated_at=None,
    )
    pending_order = SimpleNamespace(
        id=102,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="",
        picking_at=None,
        updated_at=None,
        created_at=datetime.utcnow(),
        payment_at=None,
        platform_created_at=None,
    )
    synced_order_ids = []
    moved_to_printing = []
    notices = []
    call_order = []
    purchase = SimpleNamespace(id=79, purchase_no="PO20260531-005")
    submitted_jobs = []

    def fake_start_step(db, run_id, step_code, step_name, payload):
        return SimpleNamespace(step_code=step_code, step_name=step_name)

    def fake_upsert_run_order(db, run_id, order, **updates):
        return SimpleNamespace(order_id=order.id, **updates)

    async def fake_refresh_status(db, rows, **kwargs):
        call_order.append("refresh_status")
        assert {row.id for row in rows} == {ready_order.id, pending_order.id}
        ready_order.shipment_tracking_number = "DEMO-TRACKING-0019"
        ready_order.biz_status = "已发货"
        return {"eligible": len(rows), "updated": 1, "tracking_updated": 1}

    async def fake_logistics(db, rows, **kwargs):
        call_order.append("sync_logistics")
        synced_order_ids.extend(row.id for row in rows)
        return {"eligible": len(rows), "submitted": 0}

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        return {ready_order.id: _blank_pdf(164, 113)}, 0, 1, 0

    def fake_move_to_printing(db, rows):
        moved_to_printing.extend(row.id for row in rows)
        for row in rows:
            row.biz_status = "待打印"

    def fake_notice(db, task, rows):
        notices.extend(row.id for row in rows)
        return 0, "没有超过24小时仍未就绪的订单"

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([ready_order, pending_order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_move_to_printing", fake_move_to_printing)
    monkeypatch.setattr(task_runner, "_notify_stale_logistics_pending_orders", fake_notice)
    monkeypatch.setattr(task_runner, "_latest_shipment", lambda db, order_id: None)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh_status)
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", fake_logistics)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)
    monkeypatch.setattr(task_runner, "_backup_merged_pdf", lambda platform, run_id, pdf_bytes: "/tmp/refreshed-ready.pdf")
    monkeypatch.setattr(task_runner, "_printer_setting_map", lambda db: {"ozon": SimpleNamespace(printer_name="DemoPrinter")})
    monkeypatch.setattr(task_runner, "_run_printer_monitor_step", lambda db, task, run, printer_names: [])
    monkeypatch.setattr(task_runner, "_previous_printed_rows", lambda db, run: {})
    monkeypatch.setattr(
        task_runner,
        "_submit_pdf_to_printer",
        lambda *args, **kwargs: submitted_jobs.append(kwargs.get("job_name")) or (True, "已提交打印队列"),
    )
    monkeypatch.setattr(task_runner, "_mark_labels_printed", lambda db, order_ids: None)
    monkeypatch.setattr(task_runner, "_generate_purchase_order_for_orders", lambda db, rows: purchase)
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", lambda db, rows, purchase_row: None)
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))

    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"logistics_ready_timeout_seconds": 0},
    )
    run = ScheduledTaskRun(id=34, scheduled_task_id=1, task_type="auto_order_pipeline")

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([ready_order])

        def commit(self):
            pass

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert call_order == ["refresh_status", "sync_logistics"]
    assert synced_order_ids == [pending_order.id]
    assert moved_to_printing == [ready_order.id]
    assert notices == [pending_order.id]
    assert stats["logistics_ready_count"] == 1
    assert stats["tracking_pending_count"] == 1
    assert stats["print_success_count"] == 1
    assert submitted_jobs
    assert "PO20260531-005" in summary


def test_generate_purchase_filters_missing_product_name_after_waiting_purchase(monkeypatch):
    purchasable_order = SimpleNamespace(id=101, biz_status="待打印")
    missing_order = SimpleNamespace(id=102, biz_status="待打印")
    run_orders = {}
    moved_to_waiting_purchase = []
    moved_to_picking = []
    purchase = SimpleNamespace(id=88, purchase_no="PO20260531-003")

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([purchasable_order])

    def fake_start_step(db, run_id, step_code, step_name, payload):
        return SimpleNamespace(step_code=step_code, step_name=step_name)

    def fake_upsert_run_order(db, run_id, order, **updates):
        row = run_orders.setdefault(order.id, SimpleNamespace(order_id=order.id))
        for key, value in updates.items():
            setattr(row, key, value)
        return row

    def fake_move_to_waiting_purchase(db, rows):
        moved_to_waiting_purchase.extend(row.id for row in rows)
        for row in rows:
            row.biz_status = "待采购"

    def fake_move_to_picking_after_purchase(db, rows, purchase_row):
        moved_to_picking.extend(row.id for row in rows)
        for row in rows:
            row.biz_status = "配货中"

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_upsert_run_order", fake_upsert_run_order)
    monkeypatch.setattr(task_runner, "_move_to_waiting_purchase", fake_move_to_waiting_purchase)
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: ([purchasable_order], [missing_order], [{"order_id": missing_order.id}]))
    monkeypatch.setattr(task_runner, "_notify_missing_product_names", lambda *args, **kwargs: (True, "sent"))
    monkeypatch.setattr(task_runner, "_generate_purchase_order_for_orders", lambda db, rows: purchase)
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", fake_move_to_picking_after_purchase)

    stats = {}
    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})
    run = ScheduledTaskRun(id=33, scheduled_task_id=1, task_type="auto_order_pipeline")

    result = task_runner._generate_purchase_and_move_to_picking(
        FakeDb(),
        task,
        run,
        [purchasable_order, missing_order],
        stats,
    )

    assert result is purchase
    assert moved_to_waiting_purchase == [purchasable_order.id, missing_order.id]
    assert moved_to_picking == [purchasable_order.id]
    assert missing_order.biz_status == "待采购"
    assert run_orders[missing_order.id].error_message == "采购单生成已跳过：存在产品中文名称为空的明细"
    assert stats["waiting_purchase_count"] == 2
    assert stats["missing_product_name_count"] == 1
    assert stats["purchase_order_id"] == 88


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "platform_status", "expected_biz_status"),
    [
        ("ozon", "cancel", "已作废"),
        ("ozon", "Shipped", "已妥投"),
        ("ozon", "fulfilledOnline", "待处理"),
        ("allegro", "SENT", "已发货"),
        ("allegro", "PICKED_UP", "已妥投"),
        ("wildberries", "complete", "待处理"),
    ],
)
async def test_status_sync_updates_pending_orders_from_platform_status(
    monkeypatch,
    platform,
    platform_status,
    expected_biz_status,
):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform=platform,
        account_id="100001" if platform == "ozon" else "wildberries-demo",
        posting_number="POST-1",
        platform_status="awaiting_packaging",
        raw_payload={},
        country_code="",
        country_name_cn="",
        shipment_tracking_number="",
        handover_at=None,
        fulfillment_type="FBS",
        buyer_selected_logistics="",
        logistics_last_synced_at=None,
    )

    class FakeDb:
        def scalar(self, stmt):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_order_status_updates(self, lookup_numbers):
            assert lookup_numbers == ["POST-1"]
            return [
                sync_engine.OrderStatusUpdate(
                    posting_number="POST-1",
                    platform_order_id="ORDER-1",
                    platform_status=platform_status,
                    raw_payload={"status": platform_status},
                )
            ]

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())
    monkeypatch.setattr(
        sync_engine,
        "_upsert_shipment_info",
        lambda *args, **kwargs: {"created": False, "updated": False, "tracking_updated": False},
    )

    result = await sync_engine.refresh_order_logistics_for_rows(FakeDb(), [row])

    assert result["eligible"] == 1
    assert result["requested"] == 1
    assert result["received"] == 1
    assert result["updated"] == 1
    assert row.platform_status == platform_status
    assert row.biz_status == expected_biz_status


@pytest.mark.asyncio
async def test_status_sync_applies_ozon_pending_registration_fallback(monkeypatch, tmp_path):
    row = SimpleNamespace(
        id=1,
        tenant_id="default",
        biz_status="待处理",
        platform="ozon",
        account_id="100001",
        platform_order_id="ORDER-1",
        platform_order_no="ORDER-NO-1",
        posting_number="POST-1",
        platform_status="awaiting_registration",
        raw_payload={
            "posting_number": "POST-1",
            "status": "awaiting_registration",
            "substatus": "posting_awaiting_registration",
        },
        country_code="",
        country_name_cn="",
        shipment_tracking_number="",
        handover_at=None,
        fulfillment_type="FBS",
        buyer_selected_logistics="",
        logistics_last_synced_at=None,
        is_overseas_warehouse=False,
        last_api_payload={},
        local_status="failed_retryable",
        error_message="HAS_INCORRECT_STATUS",
        updated_at=None,
    )
    shipment = SimpleNamespace(id=10, platform_shipment_id="", tracking_number="", carrier="", status="created")
    labels = []

    class FakeDb:
        def scalar(self, stmt):
            model = getattr(stmt, "column_descriptions", [{}])[0].get("entity")
            if model is sync_engine.Shipment:
                return shipment
            return None

        def add(self, value):
            labels.append(value)

        def flush(self):
            pass

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_order_status_updates(self, lookup_numbers):
            assert lookup_numbers == ["POST-1"]
            return [
                sync_engine.OrderStatusUpdate(
                    posting_number="POST-1",
                    platform_order_id="ORDER-1",
                    platform_order_no="ORDER-NO-1",
                    platform_status="awaiting_registration",
                    shipment_tracking_number="",
                    raw_payload={
                        "posting_number": "POST-1",
                        "status": "awaiting_registration",
                        "substatus": "posting_awaiting_registration",
                        "tracking_number": "",
                    },
                )
            ]

        async def fetch_label(self, shipment_result, normalized):
            assert shipment_result.platform_shipment_id == "POST-1"
            assert normalized.posting_number == "POST-1"
            return SimpleNamespace(content=_blank_pdf(100, 100), content_type="application/pdf")

    saved_path = tmp_path / "POST-1.pdf"
    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())
    monkeypatch.setattr(sync_engine, "save_label_pdf", lambda *args, **kwargs: (str(saved_path), "sha"))
    monkeypatch.setattr(sync_engine, "_pdf_text_contains", lambda content, text: text == "POST-1")
    added_logs = []
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: added_logs.append(kwargs))

    result = await sync_engine.refresh_order_logistics_for_rows(FakeDb(), [row])

    assert result["eligible"] == 1
    assert result["received"] == 1
    assert result["tracking_updated"] == 1
    assert result["ozon_tracking_fallback_applied"] == 1
    assert row.shipment_tracking_number == "POST-1"
    assert row.raw_payload["ozon_tracking_fallback"]["tracking_number"] == "POST-1"
    assert row.local_status == "label_saved"
    assert row.error_message == ""
    assert shipment.tracking_number == "POST-1"
    assert labels
    assert added_logs


@pytest.mark.asyncio
async def test_logistics_refresh_skips_terminal_orders():
    rows = [
        SimpleNamespace(id=1, biz_status="已完成", platform="ozon", account_id="100001"),
        SimpleNamespace(id=2, biz_status="已作废", platform="ozon", account_id="100001"),
    ]

    result = await sync_engine.refresh_order_logistics_for_rows(object(), rows)

    assert result["eligible"] == 0
    assert result["skipped_terminal"] == 2
    assert result["requested"] == 0


@pytest.mark.asyncio
async def test_logistics_refresh_skips_wildberries_russia_orders(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform="wildberries",
        account_id="wb-ru-store",
        shop_id="wb-ru-store",
        shop_name="Any WB Store",
        country_code="RU",
        country_name_cn="俄罗斯",
        posting_number="DEMO-ORDER-0015",
        shipment_tracking_number="",
        raw_payload={},
        fulfillment_type="FBS",
        logistics_last_synced_at=None,
    )

    monkeypatch.setattr(
        sync_engine,
        "_connector_for_account",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("exempt order should not initialize connector")),
    )

    result = await sync_engine.refresh_order_logistics_for_rows(object(), [row])

    assert result["eligible"] == 0
    assert result["skipped_logistics_label_exempt"] == 1
    assert result["requested"] == 0


@pytest.mark.asyncio
async def test_logistics_refresh_does_not_skip_wildberries_demo_shop_china_orders(monkeypatch):
    row = SimpleNamespace(
        id=2,
        biz_status="待处理",
        platform="wildberries",
        account_id="WB DEMO SHOP CN",
        shop_id="WB DEMO SHOP CN",
        shop_name="WB DEMO SHOP CN",
        country_code="CN",
        country_name_cn="中国",
        posting_number="WB-CN-1",
        shipment_tracking_number="",
        raw_payload={},
        fulfillment_type="FBS",
        logistics_last_synced_at=None,
    )

    class FakeDb:
        def scalar(self, stmt):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_order_status_updates(self, lookup_numbers):
            assert lookup_numbers == ["WB-CN-1"]
            return []

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())

    result = await sync_engine.refresh_order_logistics_for_rows(FakeDb(), [row])

    assert result["eligible"] == 1
    assert result["skipped_logistics_label_exempt"] == 0
    assert result["requested"] == 1


@pytest.mark.asyncio
async def test_status_sync_recomputes_existing_platform_status_before_cooldown(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="已发货",
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        posting_number="POST-1",
        platform_status="complete",
        shipment_tracking_number="DEMO-TRACKING-0002",
        raw_payload={},
        fulfillment_type="FBS",
        logistics_last_synced_at=datetime.utcnow(),
    )

    result = await sync_engine.refresh_order_logistics_for_rows(object(), [row])

    assert result["eligible"] == 0
    assert result["requested"] == 0
    assert result["updated"] == 1
    assert result["snapshot_status_updated"] == 1
    assert result["skipped_delivered_confirmed"] == 1
    assert row.biz_status == "已妥投"


@pytest.mark.asyncio
async def test_low_frequency_orders_wait_six_hours(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="配货中",
        platform="ozon",
        account_id="100001",
        posting_number="POST-1",
        shipment_tracking_number="DEMO-TRACKING-0002",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(hours=5, minutes=59),
    )

    result = await sync_engine.refresh_order_logistics_for_rows(object(), [row])

    assert result["eligible"] == 0
    assert result["skipped_low_frequency_cooldown"] == 1
    assert result["requested"] == 0


@pytest.mark.asyncio
async def test_low_frequency_orders_refresh_after_six_hours(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="配货中",
        platform="ozon",
        account_id="100001",
        posting_number="POST-1",
        shipment_tracking_number="DEMO-TRACKING-0002",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(hours=6, minutes=1),
    )

    class FakeDb:
        def scalar(self, stmt):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_order_status_updates(self, lookup_numbers):
            return []

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())

    result = await sync_engine.refresh_order_logistics_for_rows(FakeDb(), [row])

    assert result["eligible"] == 1
    assert result["requested"] == 1
    assert row.logistics_last_synced_at is not None


def test_order_logistics_refresh_description_uses_per_order_stats():
    first = SimpleNamespace(id=1)
    second = SimpleNamespace(id=2)
    stats = {
        "requested": 2,
        "received": 1,
        "updated": 1,
        "order_results": {
            "1": {"requested": 1, "received": 1, "updated": 1},
            "2": {"requested": 1, "received": 0, "updated": 0},
        },
    }

    assert (
        sync_engine.order_logistics_refresh_description(stats, first, prefix="定时同步状态刷新")
        == "定时同步状态刷新：本订单请求 1 条，返回 1 条，更新 1 条"
    )
    assert (
        sync_engine.order_logistics_refresh_description(stats, second, prefix="定时同步状态刷新")
        == "定时同步状态刷新：本订单请求 1 条，返回 0 条，更新 0 条"
    )
    assert sync_engine.order_logistics_refresh_log_extra(stats, second) == {
        "result": {"requested": 2, "received": 1, "updated": 1},
        "order_result": {"requested": 1, "received": 0, "updated": 0},
    }


@pytest.mark.asyncio
async def test_refresh_order_logistics_records_per_order_stats(monkeypatch):
    first = SimpleNamespace(
        id=1,
        biz_status="配货中",
        platform="ozon",
        account_id="100001",
        posting_number="POST-1",
        shipment_tracking_number="DEMO-TRACKING-0002",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(hours=6, minutes=1),
    )
    second = SimpleNamespace(
        id=2,
        biz_status="配货中",
        platform="ozon",
        account_id="100001",
        posting_number="DEMO-ORDER-0083",
        shipment_tracking_number="DEMO-TRACKING-0021",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(hours=6, minutes=1),
    )

    class FakeDb:
        def scalar(self, stmt):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_order_status_updates(self, lookup_numbers):
            return [SimpleNamespace(posting_number="DEMO-ORDER-0083")]

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())
    monkeypatch.setattr(
        sync_engine,
        "_apply_status_update_to_order",
        lambda *args, **kwargs: {
            "updated": True,
            "tracking_updated": False,
            "shipment_created": False,
            "shipment_updated": False,
        },
    )

    result = await sync_engine.refresh_order_logistics_for_rows(FakeDb(), [first, second])

    assert result["requested"] == 2
    assert result["received"] == 1
    assert result["updated"] == 1
    assert result["order_results"]["1"] == {
        "requested": 1,
        "received": 0,
        "updated": 0,
        "snapshot_status_updated": 0,
        "tracking_updated": 0,
        "shipment_created": 0,
        "shipment_updated": 0,
    }
    assert result["order_results"]["2"] == {
        "requested": 1,
        "received": 1,
        "updated": 1,
        "snapshot_status_updated": 0,
        "tracking_updated": 0,
        "shipment_created": 0,
        "shipment_updated": 0,
    }


@pytest.mark.asyncio
async def test_low_frequency_orders_do_not_require_cached_label(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="配货中",
        platform="ozon",
        account_id="100001",
        posting_number="POST-1",
        shipment_tracking_number="DEMO-TRACKING-0002",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(minutes=10),
    )

    monkeypatch.setattr(sync_engine, "_latest_real_label_for_order", lambda db, order: None)

    result = await sync_engine.refresh_order_logistics_for_rows(object(), [row])

    assert result["eligible"] == 0
    assert result["skipped_low_frequency_cooldown"] == 1
    assert result["requested"] == 0


@pytest.mark.asyncio
async def test_only_pending_orders_without_tracking_use_high_frequency(monkeypatch):
    waiting_print = SimpleNamespace(
        id=1,
        biz_status="待打印",
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        posting_number="POST-1",
        shipment_tracking_number="",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(minutes=10),
    )
    pending = SimpleNamespace(
        id=2,
        biz_status="待处理",
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        posting_number="DEMO-ORDER-0083",
        shipment_tracking_number="",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(minutes=10),
    )

    class FakeDb:
        def scalar(self, stmt):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_order_status_updates(self, lookup_numbers):
            return []

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())

    result = await sync_engine.refresh_order_logistics_for_rows(FakeDb(), [waiting_print, pending])

    assert result["eligible"] == 1
    assert result["requested"] == 1
    assert result["skipped_low_frequency_cooldown"] == 1
    assert result["refreshed_order_ids"] == [pending.id]


@pytest.mark.asyncio
async def test_pending_orders_with_tracking_use_low_frequency_cooldown(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform="ozon",
        account_id="100001",
        posting_number="POST-1",
        shipment_tracking_number="DEMO-TRACKING-0002",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(minutes=10),
    )

    result = await sync_engine.refresh_order_logistics_for_rows(object(), [row])

    assert result["eligible"] == 0
    assert result["skipped_low_frequency_cooldown"] == 1
    assert result["requested"] == 0


@pytest.mark.asyncio
async def test_failed_low_frequency_refresh_marks_attempt_without_marking_high_frequency(monkeypatch):
    low_frequency = SimpleNamespace(
        id=1,
        biz_status="配货中",
        platform="ozon",
        account_id="100001",
        posting_number="POST-1",
        shipment_tracking_number="DEMO-TRACKING-0002",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(hours=6, minutes=1),
    )
    high_frequency = SimpleNamespace(
        id=2,
        biz_status="待处理",
        platform="joom_logistics",
        account_id="100001",
        posting_number="DEMO-ORDER-0083",
        shipment_tracking_number="",
        raw_payload={},
        logistics_last_synced_at=datetime.utcnow() - timedelta(minutes=10),
    )

    class FakeDb:
        def scalar(self, stmt):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_order_status_updates(self, lookup_numbers):
            raise RuntimeError("temporary platform error")

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())

    result = await sync_engine.refresh_order_logistics_for_rows(FakeDb(), [low_frequency, high_frequency])

    assert result["eligible"] == 2
    assert result["requested"] == 2
    assert result["received"] == 0
    assert result["failed_accounts"] == 2
    assert result["low_frequency_attempted"] == 1
    assert low_frequency.logistics_last_synced_at is not None
    assert high_frequency.logistics_last_synced_at < datetime.utcnow() - timedelta(minutes=5)


@pytest.mark.asyncio
async def test_delivered_orders_stop_after_one_confirming_refresh():
    row = SimpleNamespace(
        id=1,
        biz_status="已妥投",
        platform="ozon",
        account_id="100001",
        logistics_last_synced_at=datetime.utcnow() - timedelta(days=1),
    )

    result = await sync_engine.refresh_order_logistics_for_rows(object(), [row])

    assert result["eligible"] == 0
    assert result["skipped_delivered_confirmed"] == 1
    assert result["requested"] == 0


@pytest.mark.asyncio
async def test_delivered_orders_skip_even_without_previous_refresh():
    row = SimpleNamespace(
        id=1,
        biz_status="已妥投",
        platform="ozon",
        account_id="100001",
        logistics_last_synced_at=None,
    )

    result = await sync_engine.refresh_order_logistics_for_rows(object(), [row])

    assert result["eligible"] == 0
    assert result["skipped_delivered_confirmed"] == 1
    assert result["requested"] == 0


@pytest.mark.asyncio
async def test_pending_logistics_refresh_preserves_biz_status(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform="ozon",
        account_id="100001",
        posting_number="POST-1",
        raw_payload={},
    )

    class FakeDb:
        def scalar(self, stmt):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_order_status_updates(self, lookup_numbers):
            return [SimpleNamespace(posting_number="POST-1")]

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())

    def fake_apply_status_update_to_order(db, order, update, *, connector_settings=None):
        order.biz_status = "已发货"
        return {"updated": True, "tracking_updated": False, "shipment_created": False, "shipment_updated": False}

    monkeypatch.setattr(sync_engine, "_apply_status_update_to_order", fake_apply_status_update_to_order)

    result = await sync_engine.refresh_order_logistics_for_rows(
        FakeDb(),
        [row],
        eligible_statuses={"待处理"},
        preserve_biz_status=True,
    )

    assert result["eligible"] == 1
    assert result["updated"] == 1
    assert row.biz_status == "待处理"


@pytest.mark.asyncio
async def test_platform_shipment_creation_enabled_submits_create(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform="ozon",
        account_id="100001",
        platform_order_id="ORDER-1",
        platform_order_no="ORDER-NO-1",
        posting_number="POST-1",
        platform_status="awaiting_packaging",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="",
        handover_at=None,
        local_status="new",
    )

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def create_platform_shipment(self, order):
            assert order.posting_number == "POST-1"
            return SimpleNamespace(
                platform_shipment_id="POST-1",
                tracking_number="TRACK-1",
                carrier="Ozon",
                status="created",
                raw_payload={},
            )

    async def fake_refresh(db, rows, **kwargs):
        assert rows == [row]
        return {"tracking_updated": 0, "shipment_created": 0, "shipment_updated": 0}

    monkeypatch.setattr(sync_engine, "_latest_shipment_for_order", lambda db, order_id: None)
    monkeypatch.setattr(sync_engine, "_has_existing_platform_shipment", lambda db, order: False)
    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())
    monkeypatch.setattr(
        sync_engine,
        "_upsert_shipment_info",
        lambda *args, **kwargs: {"created": True, "updated": True, "tracking_updated": False},
    )
    monkeypatch.setattr(sync_engine, "refresh_order_logistics_for_rows", fake_refresh)

    result = await sync_engine.submit_platform_shipments_and_refresh_logistics(
        FakeDb(),
        [row],
        eligible_statuses={"待处理"},
        preserve_biz_status_on_refresh=True,
    )

    assert result["submitted"] == 1
    assert result["skipped_creation_disabled"] == 0
    assert result["submit_failed"] == 0
    assert row.shipment_tracking_number == "TRACK-1"
    assert row.local_status == "shipment_created"


@pytest.mark.asyncio
async def test_allegro_logistics_rule_uses_wanbang_shipment(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform="allegro",
        account_id="ALG-1",
        platform_order_id="DEMO-ORDER-0113",
        platform_order_no="DEMO-ORDER-0113",
        posting_number="DEMO-ORDER-0113",
        platform_status="READY_FOR_PROCESSING",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="",
        logistics_channel="万邦速达(新) / DEMO-CARRIER",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
        handover_at=None,
        local_status="new",
        error_message="",
        updated_at=None,
    )

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

        def commit(self):
            pass

    class PlatformConnectorShouldNotBeUsed:
        settings = {}

        async def create_platform_shipment(self, order):
            raise AssertionError("Allegro platform shipment API should not be called for Wanbang-routed orders")

    async def fake_wanbang_create(db, order):
        assert order is row
        return ShipmentResult(
            platform_shipment_id="WB-PROC-1",
            tracking_number="WB-TRACK-1",
            carrier="WanbExpress",
            status="Confirmed",
            raw_payload={},
        )

    async def fake_refresh(db, rows, **kwargs):
        assert rows == [row]
        return {"tracking_updated": 0, "shipment_created": 0, "shipment_updated": 0}

    backfill_calls = []

    async def fake_platform_backfill(db, order, **kwargs):
        backfill_calls.append((order, kwargs))
        return {"attempted": 1, "registered": 1, "existing": 0, "skipped": 0, "unsupported": 0, "failed": 0}

    monkeypatch.setattr(sync_engine, "_latest_shipment_for_order", lambda db, order_id: None)
    monkeypatch.setattr(sync_engine, "_has_existing_platform_shipment", lambda db, order: False)
    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: PlatformConnectorShouldNotBeUsed())
    monkeypatch.setattr(sync_engine, "create_wanbang_shipment_for_order", fake_wanbang_create)
    monkeypatch.setattr(sync_engine, "backfill_wanbang_tracking_to_platform", fake_platform_backfill)
    monkeypatch.setattr(
        sync_engine,
        "_upsert_shipment_info",
        lambda *args, **kwargs: {"created": True, "updated": True, "tracking_updated": False},
    )
    monkeypatch.setattr(sync_engine, "refresh_order_logistics_for_rows", fake_refresh)

    result = await sync_engine.submit_platform_shipments_and_refresh_logistics(
        FakeDb(),
        [row],
        eligible_statuses={"待处理"},
        preserve_biz_status_on_refresh=True,
    )

    assert result["submitted"] == 1
    assert result["submit_failed"] == 0
    assert result["platform_tracking_registered"] == 1
    assert row.shipment_tracking_number == "WB-TRACK-1"
    assert row.local_status == "shipment_created"
    assert backfill_calls == [(row, {"tracking_number": "WB-TRACK-1", "source": "shipment_create"})]


@pytest.mark.asyncio
async def test_wanbang_order_with_existing_tracking_skips_all_wanbang_calls(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform="allegro",
        account_id="ALG-1",
        platform_order_id="DEMO-ORDER-0113",
        platform_order_no="DEMO-ORDER-0113",
        posting_number="DEMO-ORDER-0113",
        platform_status="READY_FOR_PROCESSING",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="DEMO-TRACKING-0022",
        logistics_channel="万邦速达(新) / DEMO-CARRIER",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
        handover_at=None,
        local_status="new",
        error_message="",
        updated_at=None,
    )
    existing_shipment = SimpleNamespace(
        tracking_number="DEMO-TRACKING-0022",
        carrier="Other carrier",
        created_at=datetime.utcnow(),
    )

    class FakeDb:
        def commit(self):
            pass

    async def fake_refresh(db, rows, **kwargs):
        assert rows == [row]
        return {"tracking_updated": 0, "shipment_created": 0, "shipment_updated": 0}

    def wanbang_must_not_be_called(*args, **kwargs):
        raise AssertionError("existing waybill must not trigger Wanbang")

    monkeypatch.setattr(sync_engine, "_latest_shipment_for_order", lambda db, order_id: existing_shipment)
    monkeypatch.setattr(sync_engine, "_has_existing_platform_shipment", wanbang_must_not_be_called)
    monkeypatch.setattr(sync_engine, "create_wanbang_shipment_for_order", wanbang_must_not_be_called)
    monkeypatch.setattr(sync_engine, "fetch_existing_wanbang_shipment_for_order", wanbang_must_not_be_called)
    monkeypatch.setattr(sync_engine, "backfill_wanbang_tracking_to_platform", wanbang_must_not_be_called)
    monkeypatch.setattr(sync_engine, "refresh_order_logistics_for_rows", fake_refresh)

    result = await sync_engine.submit_platform_shipments_and_refresh_logistics(
        FakeDb(),
        [row],
        eligible_statuses={"待处理"},
        preserve_biz_status_on_refresh=True,
    )

    assert result["submitted"] == 0
    assert result["skipped_existing"] == 1
    assert result["platform_tracking_attempted"] == 0
    assert row.local_status == "shipment_created"
    assert row.handover_at == existing_shipment.created_at


@pytest.mark.asyncio
async def test_wanbang_tracking_backfill_persists_success_and_skips_duplicate(monkeypatch):
    row = SimpleNamespace(
        id=3101,
        platform="allegro",
        account_id="ALG-1",
        platform_order_id="DEMO-ORDER-0120",
        platform_order_no="DEMO-ORDER-0120",
        posting_number="DEMO-ORDER-0120",
        platform_status="READY_FOR_PROCESSING",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="WB-TRACK-3101",
        logistics_channel="万邦速达(新) / DEMO-CARRIER",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
    )

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

    class FakeConnector:
        settings = {"dry_run_fulfillment": True}

        def __init__(self):
            self.calls = []

        async def register_tracking_number(self, order, tracking_number, carrier):
            self.calls.append((order, tracking_number, carrier))
            return ShipmentResult(
                platform_shipment_id="shipment-wanbang-3101",
                tracking_number=tracking_number,
                carrier=carrier,
                status="registered",
            )

    connector = FakeConnector()
    api_logs = []
    operation_logs = []
    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: connector)
    monkeypatch.setattr(sync_engine, "log_api_call", lambda **kwargs: api_logs.append(kwargs))
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: operation_logs.append(kwargs))

    result = await sync_engine.backfill_wanbang_tracking_to_platform(
        FakeDb(),
        row,
        tracking_number="WB-TRACK-3101",
        source="shipment_create",
    )
    repeated = await sync_engine.backfill_wanbang_tracking_to_platform(
        FakeDb(),
        row,
        tracking_number="WB-TRACK-3101",
        source="label_fetch",
    )

    assert result == {"attempted": 1, "registered": 1, "existing": 0, "skipped": 0, "unsupported": 0, "failed": 0}
    assert repeated["skipped"] == 1
    assert len(connector.calls) == 1
    assert connector.settings["dry_run_fulfillment"] is False
    assert row.raw_payload["wanbang_platform_tracking"]["status"] == "registered"
    assert row.raw_payload["wanbang_platform_tracking"]["platform_shipment_id"] == "shipment-wanbang-3101"
    assert api_logs[0]["operation"] == "wanbang_platform_tracking_backfill"
    assert operation_logs[0]["operation_attribute"] == "回填平台货运单号"


@pytest.mark.asyncio
async def test_wanbang_tracking_backfill_sends_one_failure_email_per_waybill(monkeypatch):
    row = SimpleNamespace(
        id=3102,
        platform="allegro",
        account_id="ALG-1",
        platform_order_id="DEMO-ORDER-0121",
        platform_order_no="DEMO-ORDER-0121",
        posting_number="DEMO-ORDER-0121",
        platform_status="READY_FOR_PROCESSING",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="WB-TRACK-3102",
        logistics_channel="万邦速达(新) / DEMO-CARRIER",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
    )

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

    class FailingConnector:
        settings = {}

        async def register_tracking_number(self, *args, **kwargs):
            raise RuntimeError("Allegro returned 503")

    sent_emails = []
    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FailingConnector())
    monkeypatch.setattr(sync_engine, "log_api_call", lambda **kwargs: None)
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sync_engine,
        "get_email_setting",
        lambda db: SimpleNamespace(
            notification_recipients={"wanbang_tracking_failure": "demo@example.invalid; demo@example.invalid"}
        ),
    )
    monkeypatch.setattr(
        sync_engine,
        "send_email",
        lambda setting, recipients, subject, body: sent_emails.append((recipients, subject, body)),
    )

    first = await sync_engine.backfill_wanbang_tracking_to_platform(
        FakeDb(), row, tracking_number="WB-TRACK-3102", source="shipment_create"
    )
    retried = await sync_engine.backfill_wanbang_tracking_to_platform(
        FakeDb(), row, tracking_number="WB-TRACK-3102", source="retry"
    )

    assert first["failed"] == 1
    assert retried["failed"] == 1
    assert len(sent_emails) == 1
    assert sent_emails[0][0] == ["demo@example.invalid", "demo@example.invalid"]
    assert "WB-TRACK-3102" in sent_emails[0][2]
    assert row.raw_payload["wanbang_platform_tracking"]["failure_email_recipient"] == "demo@example.invalid, demo@example.invalid"
    assert row.raw_payload["wanbang_platform_tracking"]["failure_email_sent_at"]


@pytest.mark.asyncio
async def test_wanbang_tracking_backfill_without_recipient_does_not_interrupt_retry(monkeypatch):
    row = SimpleNamespace(
        id=3103,
        platform="allegro",
        account_id="ALG-1",
        platform_order_id="DEMO-ORDER-0122",
        platform_order_no="DEMO-ORDER-0122",
        posting_number="DEMO-ORDER-0122",
        platform_status="READY_FOR_PROCESSING",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="WB-TRACK-3103",
        logistics_channel="万邦速达(新) / DEMO-CARRIER",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
    )

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

    class FailingConnector:
        settings = {}

        async def register_tracking_number(self, *args, **kwargs):
            raise RuntimeError("Allegro returned 503")

    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FailingConnector())
    monkeypatch.setattr(sync_engine, "log_api_call", lambda **kwargs: None)
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sync_engine,
        "get_email_setting",
        lambda _db: SimpleNamespace(notification_recipients={"wanbang_tracking_failure": ""}),
    )
    monkeypatch.setattr(sync_engine, "send_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("email must not be sent")))

    result = await sync_engine.backfill_wanbang_tracking_to_platform(
        FakeDb(), row, tracking_number="WB-TRACK-3103", source="shipment_create"
    )

    state = row.raw_payload["wanbang_platform_tracking"]
    assert result["failed"] == 1
    assert state["status"] == "failed"
    assert state["failure_email_error"] == "未配置万邦接口 / 运单回填异常的邮件收件人"
    assert state["failure_email_attempt_count"] == 1
    assert "failure_email_sent_at" not in state


@pytest.mark.asyncio
async def test_dmsmatrix_imported_wanbang_order_syncs_existing_shipment(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform="dmsmatrix",
        account_id="dms0001",
        platform_order_id="DEMO-ORDER-0115",
        platform_order_no="DEMO-ORDER-0116",
        posting_number="DEMO-ORDER-0115",
        platform_status="delivered",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        internal_order_no="WNBAA0000000001AA",
        logistics_carrier_code="wanbang_suda_new",
        logistics_match_status="matched",
        shipment_tracking_number="",
        handover_at=None,
        local_status="new",
        error_message="",
        updated_at=None,
    )

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

        def commit(self):
            pass

    async def fake_existing_wanbang_shipment(db, order):
        assert order is row
        return ShipmentResult(
            platform_shipment_id="WNBAA0000000001AA",
            tracking_number="DEMO-TRACKING-WB-0001",
            carrier="WanbExpress",
            status="Confirmed",
            raw_payload={},
        )

    async def fake_wanbang_create(db, order):
        raise AssertionError("DMSMatrix imported Wanbang orders must not create another parcel")

    async def fake_refresh(db, rows, **kwargs):
        assert rows == [row]
        return {"tracking_updated": 0, "shipment_created": 0, "shipment_updated": 0}

    monkeypatch.setattr(sync_engine, "_latest_shipment_for_order", lambda db, order_id: None)
    monkeypatch.setattr(sync_engine, "_has_existing_platform_shipment", lambda db, order: False)
    monkeypatch.setattr(sync_engine, "fetch_existing_wanbang_shipment_for_order", fake_existing_wanbang_shipment)
    monkeypatch.setattr(sync_engine, "create_wanbang_shipment_for_order", fake_wanbang_create)
    monkeypatch.setattr(
        sync_engine,
        "_upsert_shipment_info",
        lambda *args, **kwargs: {"created": True, "updated": True, "tracking_updated": False},
    )
    monkeypatch.setattr(sync_engine, "refresh_order_logistics_for_rows", fake_refresh)

    result = await sync_engine.submit_platform_shipments_and_refresh_logistics(
        FakeDb(),
        [row],
        eligible_statuses={"待处理"},
        preserve_biz_status_on_refresh=True,
    )

    assert result["submitted"] == 1
    assert result["submit_failed"] == 0
    assert row.shipment_tracking_number == "DEMO-TRACKING-WB-0001"
    assert row.local_status == "shipment_created"


@pytest.mark.asyncio
async def test_ozon_pending_placeholder_shipment_does_not_skip_create(monkeypatch):
    row = SimpleNamespace(
        id=1,
        biz_status="待处理",
        platform="ozon",
        account_id="100001",
        platform_order_id="ORDER-1",
        platform_order_no="ORDER-NO-1",
        posting_number="POST-1",
        platform_status="awaiting_packaging",
        raw_payload={"posting_number": "POST-1", "status": "awaiting_packaging", "substatus": "posting_created"},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="POST-1",
        handover_at=None,
        local_status="shipment_created",
        error_message="",
        updated_at=None,
    )
    placeholder = SimpleNamespace(
        platform_shipment_id="POST-1",
        tracking_number="POST-1",
        status="awaiting_packaging",
        created_at=datetime.utcnow(),
    )
    created_orders = []

    class FakeDb:
        def scalar(self, *args, **kwargs):
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def create_platform_shipment(self, order):
            created_orders.append(order.posting_number)
            return SimpleNamespace(
                platform_shipment_id="POST-1",
                tracking_number="",
                carrier="Ozon",
                status="created",
                raw_payload={},
            )

    async def fake_refresh(db, rows, **kwargs):
        return {"tracking_updated": 0, "shipment_created": 0, "shipment_updated": 0}

    monkeypatch.setattr(sync_engine, "_latest_shipment_for_order", lambda db, order_id: placeholder)
    monkeypatch.setattr(sync_engine, "_connector_for_account", lambda *args, **kwargs: FakeConnector())
    monkeypatch.setattr(
        sync_engine,
        "_upsert_shipment_info",
        lambda *args, **kwargs: {"created": False, "updated": True, "tracking_updated": False},
    )
    monkeypatch.setattr(sync_engine, "refresh_order_logistics_for_rows", fake_refresh)

    result = await sync_engine.submit_platform_shipments_and_refresh_logistics(
        FakeDb(),
        [row],
        eligible_statuses={"待处理"},
        preserve_biz_status_on_refresh=True,
    )

    assert created_orders == ["POST-1"]
    assert result["submitted"] == 1
    assert result["skipped_existing"] == 0
    assert row.local_status == "shipment_created"


@pytest.mark.asyncio
async def test_auto_cache_labels_includes_shipment_created_pending_orders(monkeypatch, tmp_path):
    row = SimpleNamespace(
        id=1,
        tenant_id="default",
        biz_status="待处理",
        platform="wildberries",
        account_id="wildberries-demo",
        platform_order_id="900000003",
        platform_order_no="900000003",
        posting_number="900000003",
        platform_status="complete",
        raw_payload={"site": "wildberries", "country_code": "CN"},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="",
        local_status="shipment_created",
        error_message="old error",
    )
    shipment = SimpleNamespace(id=10, tracking_number="", status="created")
    labels = []

    class FakeQuery:
        def __init__(self, model):
            self.model = model

        def where(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

    class FakeDb:
        def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [row])

        def scalar(self, stmt):
            return None

        def scalar(self, stmt):
            model = getattr(stmt, "column_descriptions", [{}])[0].get("entity")
            if model is sync_engine.Shipment:
                return shipment
            return None

        def add(self, value):
            labels.append(value)

        def flush(self):
            pass

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_label(self, shipment_result, normalized):
            assert normalized.posting_number == "900000003"
            return SimpleNamespace(
                content=_blank_pdf(100, 100),
                raw_payload={"parcelId": "DEMO-TRACKING-WB-0003"},
                content_type="application/pdf",
            )

    saved_path = tmp_path / "900000003.pdf"
    monkeypatch.setattr(sync_engine, "save_label_pdf", lambda *args, **kwargs: (str(saved_path), "sha"))

    saved = await sync_engine._auto_cache_labels(FakeDb(), FakeConnector(), "wildberries", "wildberries-demo")

    assert saved == 1
    assert labels
    assert row.shipment_tracking_number == "DEMO-TRACKING-WB-0003"
    assert shipment.tracking_number == "DEMO-TRACKING-WB-0003"
    assert row.local_status == "shipment_created"
    assert row.error_message == ""


@pytest.mark.asyncio
async def test_auto_cache_labels_skips_delivered_mercadolibre_with_tracking():
    row = SimpleNamespace(
        id=1,
        tenant_id="default",
        biz_status="已发货",
        platform="mercadolibre",
        account_id="mercado-demo",
        platform_order_id="DEMO-ORDER-0118",
        platform_order_no="DEMO-ORDER-0118",
        posting_number="DEMO-ORDER-0119",
        platform_status="delivered",
        raw_payload={"shipment_tracking_number": "DEMO-TRACKING-0020"},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="DEMO-TRACKING-0020",
        local_status="shipped",
        error_message="old error",
    )

    class FakeDb:
        def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [row])

        def scalar(self, stmt):
            return None

    class FakeConnector:
        settings = {}

        async def fetch_label(self, shipment_result, normalized):
            raise AssertionError("delivered MercadoLibre labels must not be fetched")

    saved = await sync_engine._auto_cache_labels(FakeDb(), FakeConnector(), "mercadolibre", "mercado-demo")

    assert saved == 0


@pytest.mark.asyncio
async def test_auto_cache_labels_skips_allegro_without_wza_shipment_id():
    row = SimpleNamespace(
        id=1,
        tenant_id="default",
        biz_status="已发货",
        platform="allegro",
        account_id="allegro-demo",
        platform_order_id="DEMO-ORDER-0022",
        platform_order_no="DEMO-ORDER-0022",
        posting_number="DEMO-ORDER-0022",
        platform_status="SENT",
        raw_payload={
            "id": "DEMO-ORDER-0022",
            "shipments": [
                {
                    "id": "DEMO-SHIPMENT-ALLEGRO-1",
                    "waybill": "DEMO-TRACKING-0006",
                    "carrierId": "WANB_EXPRESS",
                }
            ],
            "shipment_tracking_number": "DEMO-TRACKING-0006",
        },
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="DEMO-TRACKING-0006",
        local_status="shipment_created",
        error_message="old error",
    )

    shipment = SimpleNamespace(
        id=10,
        platform_shipment_id="DEMO-ORDER-0022",
        tracking_number="DEMO-TRACKING-0006",
        status="created",
    )

    class FakeDb:
        def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [row])

        def scalar(self, stmt):
            model = getattr(stmt, "column_descriptions", [{}])[0].get("entity")
            if model is sync_engine.Shipment:
                return shipment
            return None

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_label(self, shipment_result, normalized):
            assert shipment_result.platform_shipment_id == "DEMO-SHIPMENT-ALLEGRO-1"
            assert normalized.platform_order_id == "DEMO-ORDER-0022"
            raise RuntimeError("Allegro 订单 shipment 面单接口不可用：HTTP 404 Feature unavailable")

    saved = await sync_engine._auto_cache_labels(FakeDb(), FakeConnector(), "allegro", "allegro-demo")

    assert saved == 0
    assert "Feature unavailable" in row.error_message


@pytest.mark.asyncio
async def test_auto_cache_labels_applies_ozon_pending_registration_fallback(monkeypatch, tmp_path):
    row = SimpleNamespace(
        id=1,
        tenant_id="default",
        biz_status="待处理",
        platform="ozon",
        account_id="100001",
        platform_order_id="ORDER-1",
        platform_order_no="ORDER-NO-1",
        posting_number="POST-1",
        platform_status="awaiting_registration",
        raw_payload={"posting_number": "POST-1", "status": "awaiting_registration", "substatus": "posting_awaiting_registration"},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        shipment_tracking_number="",
        local_status="shipment_created",
        logistics_last_synced_at=None,
        last_api_payload={},
        error_message="old error",
        updated_at=None,
    )
    shipment = SimpleNamespace(id=10, platform_shipment_id="", tracking_number="", carrier="", status="created")
    labels = []

    class FakeDb:
        def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [row])

        def scalar(self, stmt):
            model = getattr(stmt, "column_descriptions", [{}])[0].get("entity")
            if model is sync_engine.Shipment:
                return shipment
            return None

        def add(self, value):
            labels.append(value)

        def flush(self):
            pass

        def commit(self):
            pass

    class FakeConnector:
        settings = {}

        async def fetch_label(self, shipment_result, normalized):
            assert shipment_result.platform_shipment_id == "POST-1"
            assert shipment_result.tracking_number == "POST-1"
            return SimpleNamespace(content=_blank_pdf(100, 100), content_type="application/pdf")

    saved_path = tmp_path / "POST-1.pdf"
    monkeypatch.setattr(sync_engine, "save_label_pdf", lambda *args, **kwargs: (str(saved_path), "sha"))
    monkeypatch.setattr(sync_engine, "_pdf_text_contains", lambda content, text: text == "POST-1")
    added_logs = []
    monkeypatch.setattr(sync_engine, "add_order_operation_log", lambda *args, **kwargs: added_logs.append(kwargs))
    saved = await sync_engine._auto_cache_labels(FakeDb(), FakeConnector(), "ozon", "100001")

    assert saved == 1
    assert row.shipment_tracking_number == "POST-1"
    assert row.raw_payload["ozon_tracking_fallback"]["tracking_number"] == "POST-1"
    assert row.local_status == "label_saved"
    assert row.error_message == ""
    assert shipment.tracking_number == "POST-1"
    assert labels
    assert added_logs


def test_email_provider_presets_are_extensible():
    providers = {item["code"]: item for item in list_email_provider_presets()}

    assert providers["qq"]["smtp_host"] == "smtp.qq.com"
    assert providers["163"]["smtp_host"] == "smtp.163.com"
    assert apply_provider_preset("163", "", None, None) == ("smtp.163.com", 465, True)
    assert apply_provider_preset("custom", "smtp.example.com", 587, False) == ("smtp.example.com", 587, False)


def test_final_failure_email_attaches_failed_print_pdfs(monkeypatch, tmp_path):
    pdf_path = tmp_path / "failed.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    sent = {}

    db = _FakeSession(
        [
            ScheduledTaskRunOrder(
                id=1,
                run_id=7,
                order_id=101,
                platform="ozon",
                pdf_generated=True,
                pdf_file_path=str(pdf_path),
                needs_reprint=True,
            ),
            ScheduledTaskRunOrder(
                id=2,
                run_id=7,
                order_id=102,
                platform="ozon",
                pdf_generated=True,
                pdf_file_path=str(pdf_path),
                needs_reprint=True,
            ),
        ]
    )
    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"failure_email_enabled": True, "failure_email_recipients": "demo@example.invalid"},
    )
    run = ScheduledTaskRun(
        id=7,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        trigger_mode="scheduler",
        status="failed",
        summary="打印提交失败 1 个PDF",
        attempt_no=1,
        max_retry_count=1,
        started_at=datetime.utcnow(),
        ended_at=datetime.utcnow(),
    )

    monkeypatch.setattr(email_service, "get_email_setting", lambda db: SimpleNamespace(enabled=True))

    def fake_send_email(setting, recipients, subject, body, attachments=None):
        sent["recipients"] = recipients
        sent["subject"] = subject
        sent["body"] = body
        sent["attachments"] = attachments or []

    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    ok, message = email_service.send_final_failure_email(db, task, run)

    assert ok is True
    assert message == "邮件已发送，附件 1 个"
    assert sent["recipients"] == ["demo@example.invalid"]
    assert "打印失败的 PDF" in sent["body"]
    assert len(sent["attachments"]) == 1
    assert sent["attachments"][0].filename == "ozon_failed.pdf"
    assert sent["attachments"][0].content.startswith(b"%PDF")


def test_uncertain_print_email_uses_recipients_without_failure_toggle(monkeypatch, tmp_path):
    pdf_path = tmp_path / "uncertain.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    sent = {}
    task = ScheduledTask(
        name="轮巡打印",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"failure_email_enabled": False, "failure_email_recipients": "demo@example.invalid"},
    )
    run = ScheduledTaskRun(id=9, scheduled_task_id=1, task_type="auto_order_pipeline")
    rows = [SimpleNamespace(id=101, shipment_tracking_number="DEMO-TRACKING-0019", platform_order_no="", posting_number="", platform_order_id="")]

    monkeypatch.setattr(task_runner, "get_email_setting", lambda db: SimpleNamespace(enabled=True))

    def fake_send_email(setting, recipients, subject, body, attachments=None):
        sent["recipients"] = recipients
        sent["subject"] = subject
        sent["body"] = body
        sent["attachments"] = attachments or []

    monkeypatch.setattr(task_runner, "send_email", fake_send_email)

    ok, message = task_runner._notify_uncertain_prints(
        object(),
        task,
        run,
        printer_name="DemoPrinter",
        platform="ozon",
        rows=rows,
        pdf_path=str(pdf_path),
        print_message="已提交但未检测到队列任务，需人工确认",
    )

    assert ok is True
    assert message == "已发送人工确认邮件，附件 1 个"
    assert sent["recipients"] == ["demo@example.invalid"]
    assert "无法确认是否已经实际打印" in sent["body"]
    assert sent["attachments"][0].filename == "uncertain.pdf"


def test_scheduled_task_treats_ozon_posting_number_as_tracking(monkeypatch):
    order = SimpleNamespace(
        id=15688,
        platform="ozon",
        posting_number="DEMO-ORDER-0033",
        platform_status="awaiting_deliver",
        shipment_tracking_number="",
    )

    monkeypatch.setattr(task_runner, "_latest_shipment", lambda db, order_id: None)

    assert task_runner._order_tracking_number(object(), order) == "DEMO-ORDER-0033"
    assert task_runner._orders_with_tracking(object(), [order]) == [order]


@pytest.mark.asyncio
async def test_wildberries_cross_border_readiness_fetches_label_before_tracking(monkeypatch):
    order = SimpleNamespace(
        id=16479,
        platform="wildberries",
        account_id="wildberries-demo",
        posting_number="DEMO-ORDER-0123",
        shipment_tracking_number="",
        raw_payload={
            "site": "wildberries",
            "country_code": "CN",
            "crossBorderType": 1,
        },
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
    )
    fetched_order_ids = []

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        fetched_order_ids.extend(row.id for row in rows)
        order.shipment_tracking_number = "DEMO-TRACKING-0024"
        order.raw_payload["shipment_tracking_number"] = "WBCNRUCLBCF2500SCV"
        return {order.id: _blank_pdf(164, 113)}, 0, 1, 0

    monkeypatch.setattr(task_runner, "_latest_shipment", lambda db, order_id: None)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)

    stats = await task_runner._append_readiness_stats(object(), [order], {"stage": "status_refresh"})

    assert fetched_order_ids == [order.id]
    assert stats["tracking_ready_count"] == 1
    assert stats["tracking_ready_order_ids"] == [order.id]
    assert stats["label_ready_order_ids"] == [order.id]
    assert stats["label_fetched"] == 1


def test_manual_reprint_resume_generates_purchase_and_completes_run(monkeypatch):
    task = ScheduledTask(id=1, name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})
    run = ScheduledTaskRun(
        id=7,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        trigger_mode="manual",
        status="failed",
        summary="打印提交失败 1 个PDF",
        stats_json={"selected_orders": 1},
    )
    order = SimpleNamespace(id=101, biz_status="待打印", label_printed_at=datetime.utcnow())
    purchase = SimpleNamespace(id=55, purchase_no="PO20260602-001")
    calls = {}

    class FakeDb:
        def get(self, model, item_id):
            if model is task_runner.ScheduledTask and item_id == 1:
                return task
            return None

        def commit(self):
            calls["commit"] = calls.get("commit", 0) + 1

        def refresh(self, row):
            calls.setdefault("refresh", []).append(row)

    def fake_generate(db, task_arg, run_arg, rows, stats):
        calls["generate_args"] = (task_arg, run_arg, rows)
        stats["picking_count"] = len(rows)
        return purchase

    monkeypatch.setattr(task_runner, "_manual_reprint_resume_candidates", lambda db, run_id: [order])
    monkeypatch.setattr(task_runner, "_remaining_reprint_count", lambda db, run_id: 0)
    monkeypatch.setattr(task_runner, "_generate_purchase_and_move_to_picking", fake_generate)
    monkeypatch.setattr(task_runner, "load_enabled_logistics_rules", lambda db: [])

    result = task_runner._resume_run_after_manual_reprint(FakeDb(), run)

    assert result is purchase
    assert calls["generate_args"] == (task, run, [order])
    assert run.status == "success"
    assert run.next_retry_at is None
    assert "已继续生成采购单 PO20260602-001" in run.summary
    assert run.stats_json["manual_reprint_resume_order_count"] == 1
    assert run.stats_json["remaining_reprint_count"] == 0
    assert task.last_status == "success"
    assert task.last_message == run.summary


def test_manual_reprint_resume_keeps_failed_run_when_other_reprints_remain(monkeypatch):
    task = ScheduledTask(id=1, name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={})
    run = ScheduledTaskRun(
        id=7,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        trigger_mode="manual",
        status="failed",
        summary="打印提交失败 2 个PDF",
        stats_json={},
    )
    order = SimpleNamespace(id=101, biz_status="待打印", label_printed_at=datetime.utcnow())
    purchase = SimpleNamespace(id=55, purchase_no="PO20260602-001")

    class FakeDb:
        def get(self, model, item_id):
            if model is task_runner.ScheduledTask and item_id == 1:
                return task
            return None

        def commit(self):
            pass

        def refresh(self, row):
            pass

    monkeypatch.setattr(task_runner, "_manual_reprint_resume_candidates", lambda db, run_id: [order])
    monkeypatch.setattr(task_runner, "_remaining_reprint_count", lambda db, run_id: 1)
    monkeypatch.setattr(task_runner, "_generate_purchase_and_move_to_picking", lambda db, task, run, rows, stats: purchase)
    monkeypatch.setattr(task_runner, "load_enabled_logistics_rules", lambda db: [])

    result = task_runner._resume_run_after_manual_reprint(FakeDb(), run)

    assert result is purchase
    assert run.status == "failed"
    assert "仍有 1 条需要重打" in run.summary
    assert run.stats_json["remaining_reprint_count"] == 1
    assert task.last_status == "failed"


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, stmt):
        return _ScalarResult(self.rows)


def test_submit_pdf_to_printer_uses_cups_on_non_windows(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["/usr/bin/lpstat", "-p"]:
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter is idle. enabled since today", stderr="")
        if args[:3] == ["/usr/bin/lpstat", "-p", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout=f"printer {args[2]} is idle. enabled since today", stderr="")
        if args[:3] == ["/usr/bin/lpstat", "-W", "not-completed"]:
            return SimpleNamespace(returncode=0, stdout="DemoPrinter-42 system 1024 Fri May 29 10:00:00 2026\n", stderr="")
        if args[:3] == ["/usr/bin/lp", "-d", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="request id is DemoPrinter-42 (1 file(s))", stderr="")
        raise AssertionError(f"unexpected subprocess args: {args}")

    monkeypatch.setattr(task_runner.sys, "platform", "darwin")
    monkeypatch.setattr(task_runner, "_cups_command", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(task_runner.subprocess, "run", fake_run)

    submitted, message = task_runner._submit_pdf_to_printer(
        "/tmp/demo.pdf",
        "DemoPrinter",
        require_queue_observed=True,
        job_name="demo-job",
    )

    assert submitted is True
    assert "已提交打印队列: DemoPrinter" in message
    assert any(call[:3] == ["/usr/bin/lp", "-d", "DemoPrinter"] for call in calls)


def test_submit_pdf_to_printer_cups_orients_pdf_without_cups_orientation(monkeypatch, tmp_path):
    calls = []
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(_blank_pdf(100, 200))

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["/usr/bin/lpstat", "-p"]:
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter is idle. enabled since today", stderr="")
        if args[:3] == ["/usr/bin/lpstat", "-p", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter is idle. enabled since today", stderr="")
        if args[:3] == ["/usr/bin/lp", "-d", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="request id is DemoPrinter-42 (1 file(s))", stderr="")
        raise AssertionError(f"unexpected subprocess args: {args}")

    monkeypatch.setattr(task_runner.sys, "platform", "darwin")
    monkeypatch.setattr(task_runner, "_cups_command", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(task_runner.subprocess, "run", fake_run)

    submitted, message = task_runner._submit_pdf_to_printer(
        str(pdf_path),
        "DemoPrinter",
        job_name="demo-job",
        page_orientation="landscape",
    )

    lp_call = next(call for call in calls if call[:3] == ["/usr/bin/lp", "-d", "DemoPrinter"])
    assert submitted is True
    assert "已提交打印队列: DemoPrinter" in message
    assert "orientation-requested=4" not in lp_call
    assert lp_call[-1] != str(pdf_path)


def test_submit_pdf_to_printer_cups_sets_custom_media_from_label_stock(monkeypatch, tmp_path):
    calls = []
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(_blank_pdf(164, 113))

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["/usr/bin/lpstat", "-p"]:
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter is idle. enabled since today", stderr="")
        if args[:3] == ["/usr/bin/lpstat", "-p", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter is idle. enabled since today", stderr="")
        if args[:3] == ["/usr/bin/lp", "-d", "DemoPrinter"]:
            assert _first_page_size(open(args[-1], "rb").read()) == (227, 283)
            return SimpleNamespace(returncode=0, stdout="request id is DemoPrinter-42 (1 file(s))", stderr="")
        raise AssertionError(f"unexpected subprocess args: {args}")

    monkeypatch.setattr(task_runner.sys, "platform", "darwin")
    monkeypatch.setattr(task_runner, "_cups_command", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(task_runner.subprocess, "run", fake_run)

    submitted, message = task_runner._submit_pdf_to_printer(
        str(pdf_path),
        "DemoPrinter",
        job_name="demo-job",
        page_orientation=label_orientation_for_platform("ozon", "landscape"),
        target_size_mm=(80.0, 100.0),
    )

    lp_call = next(call for call in calls if call[:3] == ["/usr/bin/lp", "-d", "DemoPrinter"])
    assert submitted is True
    assert "已提交打印队列: DemoPrinter" in message
    assert "media=Custom.226.77x283.46" in lp_call
    assert "PageSize=Custom.226.77x283.46" in lp_call
    assert "orientation-requested=4" not in lp_call
    assert lp_call[-1] != str(pdf_path)


def test_reprint_endpoint_refreshes_session_after_retry(monkeypatch):
    import app.main as main_module

    stale_row = SimpleNamespace(id=178, order_id=4427, print_message="old")
    fresh_row = SimpleNamespace(id=178, order_id=4427, print_message="new")
    order = SimpleNamespace(platform_order_no="DEMO-ORDER-0124", platform_order_id="")

    class FakeDb:
        expired = False

        def get(self, model, item_id):
            if model is main_module.ScheduledTaskRunOrder:
                return fresh_row if self.expired else stale_row
            if model is main_module.Order:
                return order
            raise AssertionError(f"unexpected model lookup: {model!r}, {item_id!r}")

        def expire_all(self):
            self.expired = True

    db = FakeDb()
    monkeypatch.setattr(main_module, "retry_run_order_print", lambda run_order_id: None)
    monkeypatch.setattr(
        main_module,
        "_scheduled_task_run_order_dto",
        lambda row, platform_order_no: {"row": row, "platform_order_no": platform_order_no},
    )

    result = main_module.reprint_scheduled_task_run_order(178, object(), db)

    assert db.expired is True
    assert result["row"] is fresh_row
    assert result["platform_order_no"] == "DEMO-ORDER-0124"


def test_scheduled_task_run_platform_rows_groups_failed_prints(monkeypatch):
    import app.main as main_module

    rows = [
        (
            ScheduledTaskRunOrder(
                id=1,
                run_id=54,
                order_id=101,
                platform="ozon",
                pdf_generated=True,
                pdf_file_path="/tmp/ozon.pdf",
                printer_name="Printer A",
                print_submitted=False,
                print_message="打印机离线",
                needs_reprint=True,
            ),
            "OZ-101",
            "OZ-ID-101",
            "",
        ),
        (
            ScheduledTaskRunOrder(
                id=2,
                run_id=54,
                order_id=102,
                platform="ozon",
                pdf_generated=True,
                pdf_file_path="/tmp/ozon.pdf",
                printer_name="Printer A",
                print_submitted=False,
                print_message="打印机离线",
                needs_reprint=True,
            ),
            "OZ-102",
            "OZ-ID-102",
            "",
        ),
        (
            ScheduledTaskRunOrder(
                id=3,
                run_id=54,
                order_id=201,
                platform="allegro",
                pdf_generated=True,
                pdf_file_path="/tmp/allegro.pdf",
                printer_name="Printer B",
                print_submitted=True,
                print_message="已提交",
                needs_reprint=False,
            ),
            "AL-201",
            "AL-ID-201",
            "",
        ),
    ]

    class FakeDb:
        def execute(self, _stmt):
            return _ScalarResult(rows)

    monkeypatch.setattr(main_module, "refresh_reprint_candidates", lambda db, run_id: None)

    result = main_module._scheduled_task_run_platform_rows(54, FakeDb())

    assert len(result) == 2
    ozon = next(item for item in result if item.platform == "ozon")
    assert ozon.total_count == 2
    assert ozon.pdf_count == 2
    assert ozon.failed_count == 2
    assert ozon.needs_reprint is True
    assert ozon.order_nos == ["OZ-101", "OZ-102"]
    allegro = next(item for item in result if item.platform == "allegro")
    assert allegro.print_submitted is True
    assert allegro.failed_count == 0


def test_retry_run_order_print_uses_business_job_name(monkeypatch, tmp_path):
    pdf_path = tmp_path / "system" / "scheduled-task" / "ozon" / "202606" / "run-88.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    run_order = ScheduledTaskRunOrder(
        id=188,
        run_id=88,
        order_id=4427,
        platform="ozon",
        pdf_generated=True,
        pdf_file_path=str(pdf_path),
        printer_name="FallbackPrinter",
        needs_reprint=True,
    )
    print_setting = SimpleNamespace(printer_name="DemoPrinter", page_orientation="auto")
    captured = {}

    class FakeDb:
        def get(self, model, item_id):
            if model is ScheduledTaskRunOrder and item_id == run_order.id:
                return run_order
            if model is ScheduledTaskRun and item_id == run_order.run_id:
                return ScheduledTaskRun(id=run_order.run_id, scheduled_task_id=1, task_type="auto_order_pipeline")
            return None

        def scalar(self, _stmt):
            return print_setting

        def scalars(self, _stmt):
            return _ScalarResult([run_order])

        def commit(self):
            pass

        def refresh(self, _row):
            pass

        def close(self):
            pass

    def fake_submit(pdf_path_arg, printer_name, **kwargs):
        captured["pdf_path"] = pdf_path_arg
        captured["printer_name"] = printer_name
        captured["job_name"] = kwargs.get("job_name")
        return True, "已提交打印队列"

    monkeypatch.setattr(task_runner, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(task_runner, "_submit_pdf_to_printer", fake_submit)
    monkeypatch.setattr(task_runner, "_mark_labels_printed", lambda db, order_ids: None)
    monkeypatch.setattr(task_runner, "_resume_run_after_manual_reprint", lambda db, run: None)
    monkeypatch.setattr(task_runner, "_local_now", lambda: datetime(2026, 6, 4, 10, 22, 30, 654321))

    result = task_runner.retry_run_order_print(run_order.id)

    assert captured == {
        "pdf_path": str(pdf_path),
        "printer_name": "DemoPrinter",
        "job_name": "label_print_ozon_20260604102230654321.pdf",
    }
    assert run_order.print_job_name == "label_print_ozon_20260604102230654321.pdf"
    assert result["print_job_name"] == "label_print_ozon_20260604102230654321.pdf"


def test_retry_run_platform_print_only_reprints_failed_target_platform(monkeypatch, tmp_path):
    ozon_pdf = tmp_path / "ozon.pdf"
    allegro_pdf = tmp_path / "allegro.pdf"
    ozon_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    allegro_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

    ozon_rows = [
        ScheduledTaskRunOrder(
            id=201,
            run_id=90,
            order_id=501,
            platform="ozon",
            pdf_generated=True,
            pdf_file_path=str(ozon_pdf),
            printer_name="FallbackPrinter",
            needs_reprint=True,
        ),
        ScheduledTaskRunOrder(
            id=202,
            run_id=90,
            order_id=502,
            platform="ozon",
            pdf_generated=True,
            pdf_file_path=str(ozon_pdf),
            printer_name="FallbackPrinter",
            needs_reprint=True,
        ),
    ]
    allegro_row = ScheduledTaskRunOrder(
        id=203,
        run_id=90,
        order_id=601,
        platform="allegro",
        pdf_generated=True,
        pdf_file_path=str(allegro_pdf),
        printer_name="OtherPrinter",
        needs_reprint=True,
    )
    print_setting = SimpleNamespace(printer_name="OzonPrinter", page_orientation="auto")
    submitted = []

    class FakeDb:
        def get(self, model, item_id):
            if model is ScheduledTaskRun and item_id == 90:
                return ScheduledTaskRun(id=90, scheduled_task_id=1, task_type="auto_order_pipeline")
            return None

        def scalar(self, _stmt):
            return print_setting

        def scalars(self, _stmt):
            return _ScalarResult(ozon_rows)

        def commit(self):
            pass

        def close(self):
            pass

    def fake_submit(pdf_path_arg, printer_name, **kwargs):
        submitted.append((pdf_path_arg, printer_name, kwargs.get("job_name")))
        return True, "已提交打印队列"

    monkeypatch.setattr(task_runner, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(task_runner, "refresh_reprint_candidates", lambda db, run_id: None)
    monkeypatch.setattr(task_runner, "_submit_pdf_to_printer", fake_submit)
    monkeypatch.setattr(task_runner, "_mark_labels_printed", lambda db, order_ids: submitted.append(("marked", tuple(order_ids), "")))
    monkeypatch.setattr(task_runner, "_resume_run_after_manual_reprint", lambda db, run: None)
    monkeypatch.setattr(task_runner, "_local_now", lambda: datetime(2026, 6, 4, 10, 22, 30, 654321))

    result = task_runner.retry_run_platform_print(90, "ozon")

    print_calls = [item for item in submitted if item[0] != "marked"]
    assert len(print_calls) == 1
    assert print_calls[0][0] == str(ozon_pdf)
    assert print_calls[0][1] == "OzonPrinter"
    assert ("marked", (501, 502), "") in submitted
    assert ozon_rows[0].needs_reprint is False
    assert ozon_rows[1].needs_reprint is False
    assert allegro_row.needs_reprint is True
    assert result["platform"] == "ozon"
    assert result["pdf_count"] == 1


def test_scheduled_task_run_pdf_entries_falls_back_to_backup_files(monkeypatch, tmp_path):
    import app.main as main_module

    pdf_path = tmp_path / "system" / "scheduled-task" / "ozon" / "202606" / "run-54.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    class FakeScalars:
        def all(self):
            return []

    class FakeDb:
        def scalars(self, _stmt):
            return FakeScalars()

    monkeypatch.setattr(main_module, "get_settings", lambda: SimpleNamespace(label_storage_path=tmp_path))

    entries = main_module._scheduled_task_run_pdf_entries(FakeDb(), 54)

    assert entries == [("ozon", pdf_path)]


def test_scheduled_task_run_pdf_archive_uses_platform_timestamp_names(monkeypatch, tmp_path):
    import app.main as main_module

    joom_pdf_path = tmp_path / "system" / "scheduled-task" / "joom_logistics" / "202606" / "run-54.pdf"
    ozon_pdf_path = tmp_path / "system" / "scheduled-task" / "ozon" / "202606" / "run-54.pdf"
    for path in (joom_pdf_path, ozon_pdf_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n%%EOF")

    class FakeScalars:
        def all(self):
            return [
                SimpleNamespace(platform="joom_logistics", pdf_generated=True, pdf_file_path=str(joom_pdf_path)),
                SimpleNamespace(platform="ozon", pdf_generated=True, pdf_file_path=str(ozon_pdf_path)),
            ]

    class FakeDb:
        def get(self, model, item_id):
            if model is main_module.ScheduledTaskRun and item_id == 54:
                return SimpleNamespace(id=54)
            return None

        def scalars(self, _stmt):
            return FakeScalars()

    monkeypatch.setattr(main_module, "get_settings", lambda: SimpleNamespace(label_storage_path=tmp_path))
    monkeypatch.setattr(main_module, "_local_now", lambda: datetime(2026, 6, 2, 12, 0, 0))

    archive_bytes, filename = main_module._build_scheduled_task_run_pdf_archive(54, FakeDb())

    assert filename == "label_print_20260602_120000.zip"
    with zipfile.ZipFile(archive_bytes) as archive:
        assert archive.namelist() == ["Joom_20260602_120000.pdf", "Ozon_20260602_120000.pdf"]


def test_scheduled_task_run_pdf_download_token_round_trips(monkeypatch):
    import app.security as security

    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(sync_secret_key="test-secret-key-01234567890123456789"),
    )

    token = security.create_scheduled_task_run_pdf_download_token("admin", 54)

    assert security.decode_scheduled_task_run_pdf_download_token(token) == ("admin", 54)


def test_submit_pdf_to_printer_reports_missing_cups_command(monkeypatch):
    monkeypatch.setattr(task_runner.sys, "platform", "linux")
    monkeypatch.setattr(task_runner, "_cups_command", lambda command: None)

    submitted, message = task_runner._submit_pdf_to_printer("/tmp/demo.pdf", "DemoPrinter")

    assert submitted is False
    assert "CUPS 打印命令 lp 不可用" in message


def test_resolve_cups_printer_name_tolerates_separators(monkeypatch):
    def fake_run(args, **kwargs):
        assert args == ["/usr/bin/lpstat", "-p"]
        return SimpleNamespace(returncode=0, stdout="打印机WanChen_QR_488闲置，启用时间始于today\n", stderr="")

    monkeypatch.setattr(task_runner.subprocess, "run", fake_run)

    assert task_runner._resolve_cups_printer_name("WanChen QR-488", "/usr/bin/lpstat") == "WanChen_QR_488"


def test_submit_pdf_to_printer_uses_powershell_on_windows(monkeypatch):
    powershell_calls = []

    def fake_run_powershell(command, *, timeout):
        powershell_calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_submit_gdi(pdf_path, printer_name, document_name, page_orientation=None):
        assert page_orientation == "auto"
        return True, f"gdi submitted {printer_name} {document_name}"

    monkeypatch.setattr(task_runner.sys, "platform", "win32")
    monkeypatch.setattr(task_runner, "_run_powershell", fake_run_powershell)
    monkeypatch.setattr(task_runner, "_submit_pdf_to_printer_gdi", fake_submit_gdi)

    submitted, message = task_runner._submit_pdf_to_printer("/tmp/demo.pdf", "WinPrinter", job_name="win-job")

    assert submitted is True
    assert "gdi submitted WinPrinter win-job.pdf" == message
    assert powershell_calls


def test_submit_pdf_to_printer_reports_missing_powershell_on_windows(monkeypatch):
    monkeypatch.setattr(task_runner.sys, "platform", "win32")
    monkeypatch.setattr(task_runner, "_run_powershell", lambda command, *, timeout: None)

    submitted, message = task_runner._submit_pdf_to_printer("/tmp/demo.pdf", "WinPrinter")

    assert submitted is False
    assert "Windows PowerShell 不可用" in message


def test_monitor_printer_status_recovers_paused_cups_printer(monkeypatch):
    calls = []
    status_checks = {"count": 0}

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["/usr/bin/lpstat", "-p"]:
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter is idle. enabled since today\n", stderr="")
        if args == ["/usr/bin/lpstat", "-v"]:
            return SimpleNamespace(returncode=0, stdout="device for DemoPrinter: usb://Demo/Printer\n", stderr="")
        if args == ["/usr/bin/lpstat", "-p", "DemoPrinter"]:
            status_checks["count"] += 1
            if status_checks["count"] == 1:
                return SimpleNamespace(returncode=0, stdout="printer DemoPrinter disabled since today - paused\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter is idle. enabled since today\n", stderr="")
        if args == ["/usr/bin/lpstat", "-a", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="DemoPrinter accepting requests since today\n", stderr="")
        if args == ["/usr/bin/lpstat", "-W", "not-completed", "-o", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args == ["/usr/bin/cupsenable", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args == ["/usr/bin/cupsaccept", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess args: {args}")

    monkeypatch.setattr(task_runner.sys, "platform", "darwin")
    monkeypatch.setattr(task_runner, "_cups_command", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(task_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(task_runner.time, "sleep", lambda seconds: None)

    result = task_runner.monitor_printer_status(object(), "DemoPrinter", auto_recover=True, max_retries=3)

    assert result["status"] == "recovered"
    assert result["recovered"] is True
    assert result["recovery_attempts"] == 1
    assert ["/usr/bin/cupsenable", "DemoPrinter"] in calls
    assert ["/usr/bin/cupsaccept", "DemoPrinter"] in calls


def test_monitor_printer_status_sends_email_after_failed_recovery(monkeypatch):
    calls = []
    sent = {}

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["/usr/bin/lpstat", "-p"]:
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter disabled since today - paused\n", stderr="")
        if args == ["/usr/bin/lpstat", "-v"]:
            return SimpleNamespace(returncode=0, stdout="device for DemoPrinter: usb://Demo/Printer\n", stderr="")
        if args == ["/usr/bin/lpstat", "-p", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="printer DemoPrinter disabled since today - paused\n", stderr="")
        if args == ["/usr/bin/lpstat", "-a", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="DemoPrinter not accepting requests since today\n", stderr="")
        if args == ["/usr/bin/lpstat", "-W", "not-completed", "-o", "DemoPrinter"]:
            return SimpleNamespace(returncode=0, stdout="DemoPrinter-42 user 1024 today\n", stderr="")
        if args in (["/usr/bin/cupsenable", "DemoPrinter"], ["/usr/bin/cupsaccept", "DemoPrinter"]):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess args: {args}")

    def fake_send_email(setting, recipients, subject, body, attachments=None):
        sent["recipients"] = recipients
        sent["subject"] = subject
        sent["body"] = body

    task = ScheduledTask(
        name="demo",
        task_type="auto_order_pipeline",
        cron_expr="0 9 * * *",
        settings={"failure_email_recipients": "demo@example.invalid"},
    )

    monkeypatch.setattr(task_runner.sys, "platform", "darwin")
    monkeypatch.setattr(task_runner, "_cups_command", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(task_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(task_runner.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(task_runner, "get_email_setting", lambda db: SimpleNamespace(enabled=True))
    monkeypatch.setattr(task_runner, "send_email", fake_send_email)

    result = task_runner.monitor_printer_status(object(), "DemoPrinter", task=task, auto_recover=True, max_retries=3)

    assert result["status"] == "failed"
    assert result["recovery_attempts"] == 3
    assert result["email_sent"] is True
    assert sent["recipients"] == ["demo@example.invalid"]
    assert "打印机状态异常" in sent["subject"]
    assert calls.count(["/usr/bin/cupsenable", "DemoPrinter"]) == 3
    assert calls.count(["/usr/bin/cupsaccept", "DemoPrinter"]) == 3


def test_send_printer_monitor_wecom_uses_simple_message_without_mentions(monkeypatch):
    sent = {}

    class DummyWeComClient:
        def __init__(self, settings):
            sent["settings"] = settings

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def send_text(self, content, **kwargs):
            sent["content"] = content
            sent["kwargs"] = kwargs
            return {"errcode": 0}

    settings = object()
    monkeypatch.setattr(task_runner, "load_wecom_robot_settings_from_db", lambda db: settings)
    monkeypatch.setattr(task_runner, "WeComRobotClient", DummyWeComClient)

    ok, message = task_runner._send_printer_monitor_wecom(
        object(),
        result={
            "printer_name": "OldPrinter",
            "resolved_printer_name": "DemoPrinter",
            "message": "打印任务已提交队列，但打印机当前离线或连接异常",
        },
    )

    assert ok is True
    assert message == "打印机异常企业微信通知已发送"
    assert sent["settings"] is settings
    assert sent["content"] == "打印机异常：DemoPrinter，打印任务已提交队列，但打印机当前离线或连接异常。"
    assert sent["kwargs"]["use_default_mentions"] is False


def test_cups_queue_job_id_supports_english_and_chinese_output():
    assert task_runner._cups_queue_job_id("request id is DemoPrinter-42 (1 file(s))") == "DemoPrinter-42"
    assert task_runner._cups_queue_job_id("请求id是WanChen_QR_586_2-448（1个文件）") == "WanChen_QR_586_2-448"
    assert task_runner._cups_queue_job_id("已提交打印队列") == ""


def test_initialize_post_print_monitor_groups_jobs_and_sets_finite_window(monkeypatch):
    now = datetime(2026, 7, 31, 0, 12, 8)
    rows = [
        SimpleNamespace(
            printer_name="PrinterA",
            print_job_name="labels-a.pdf",
            print_message="request id is PrinterA-41 (1 file(s))",
        ),
        SimpleNamespace(
            printer_name="PrinterA",
            print_job_name="labels-a.pdf",
            print_message="request id is PrinterA-41 (1 file(s))",
        ),
        SimpleNamespace(
            printer_name="PrinterB",
            print_job_name="labels-b.pdf",
            print_message="请求id是PrinterB-52（1个文件）",
        ),
    ]

    class FakeDb:
        def scalars(self, _stmt):
            return _ScalarResult(rows)

    monkeypatch.setattr(task_runner, "_is_windows", lambda: False)
    run = ScheduledTaskRun(id=182, task_type="auto_order_pipeline")

    stats = task_runner._initialize_post_print_monitor(FakeDb(), run, {"print_success_count": 3}, now=now)
    monitor = stats[task_runner.POST_PRINT_MONITOR_KEY]

    assert monitor["status"] == "active"
    assert monitor["check_interval_seconds"] == 60
    assert monitor["expires_at"] == "2026-07-31T00:27:08"
    assert [item["printer_name"] for item in monitor["printers"]] == ["PrinterA", "PrinterB"]
    assert monitor["printers"][0]["jobs"] == [
        {"queue_job_id": "PrinterA-41", "document_name": "labels-a.pdf"}
    ]


def test_post_print_pending_jobs_only_matches_current_run_queue_ids(monkeypatch):
    monkeypatch.setattr(task_runner, "_is_windows", lambda: False)
    monkeypatch.setattr(task_runner, "_cups_not_completed_job_ids", lambda _printer: {"PrinterA-41", "PrinterA-99"})
    printer = {
        "printer_name": "PrinterA",
        "jobs": [
            {"queue_job_id": "PrinterA-40", "document_name": "old.pdf"},
            {"queue_job_id": "PrinterA-41", "document_name": "current.pdf"},
        ],
    }

    assert task_runner._post_print_pending_jobs(printer) == [
        {"queue_job_id": "PrinterA-41", "document_name": "current.pdf"}
    ]


def test_post_print_monitor_aggregates_printers_and_deduplicates_per_run(monkeypatch):
    now = datetime(2026, 7, 31, 0, 13, 0)
    run = ScheduledTaskRun(
        id=182,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        stats_json={
            task_runner.POST_PRINT_MONITOR_KEY: {
                "status": "active",
                "expires_at": "2026-07-31T00:27:08",
                "notified_printers": [],
                "notification_count": 0,
                "check_count": 0,
                "printers": [
                    {
                        "printer_name": "PrinterA",
                        "jobs": [{"queue_job_id": "PrinterA-41", "document_name": "labels-a.pdf"}],
                    },
                    {
                        "printer_name": "PrinterB",
                        "jobs": [{"queue_job_id": "PrinterB-52", "document_name": "labels-b.pdf"}],
                    },
                ],
            }
        },
    )
    task = ScheduledTask(id=1, name="订单处理流水线-上午", task_type="auto_order_pipeline", cron_expr="10 8 * * *")
    sent = []

    class FakeDb:
        def get(self, model, item_id):
            assert model is ScheduledTask
            assert item_id == 1
            return task

    def fake_snapshot(printer_name):
        return {
            "printer_name": printer_name,
            "resolved_printer_name": printer_name,
            "exists": True,
            "paused": True,
            "offline": True,
            "printer_status": f"printer {printer_name} stopped - unable to send data",
            "job_status": "printer-stopped",
            "message": "打印机状态已读取",
        }

    def fake_send(_db, *, run, task, incidents):
        sent.append((run.id, task.name, list(incidents)))
        return True, "sent"

    monkeypatch.setattr(task_runner, "_post_print_pending_jobs", lambda printer: list(printer["jobs"]))
    monkeypatch.setattr(task_runner, "_monitor_printer_snapshot", fake_snapshot)
    monkeypatch.setattr(
        task_runner,
        "_recover_post_print_printer",
        lambda printer_name, snapshot: (False, [{"attempt": 1}], snapshot),
    )
    monkeypatch.setattr(task_runner, "_send_post_print_monitor_wecom", fake_send)

    assert task_runner._process_post_print_monitor_run(FakeDb(), run, now=now) is True
    assert len(sent) == 1
    assert [item["printer_name"] for item in sent[0][2]] == ["PrinterA", "PrinterB"]
    monitor = run.stats_json[task_runner.POST_PRINT_MONITOR_KEY]
    assert monitor["notification_count"] == 1
    assert monitor["notified_printers"] == ["PrinterA", "PrinterB"]

    assert task_runner._process_post_print_monitor_run(FakeDb(), run, now=now + timedelta(minutes=1)) is True
    assert len(sent) == 1
    assert run.stats_json[task_runner.POST_PRINT_MONITOR_KEY]["check_count"] == 2


def test_post_print_monitor_only_notifies_for_abnormal_printer_with_current_pending_job(monkeypatch):
    now = datetime(2026, 7, 31, 0, 13, 0)
    run = ScheduledTaskRun(
        id=183,
        scheduled_task_id=1,
        task_type="auto_order_pipeline",
        stats_json={
            task_runner.POST_PRINT_MONITOR_KEY: {
                "status": "active",
                "expires_at": "2026-07-31T00:27:08",
                "notified_printers": [],
                "printers": [
                    {"printer_name": "OfflineNoJob", "jobs": [{"queue_job_id": "OfflineNoJob-1"}]},
                    {"printer_name": "NormalWithJob", "jobs": [{"queue_job_id": "NormalWithJob-2"}]},
                ],
            }
        },
    )
    sent = []

    class FakeDb:
        def get(self, _model, _item_id):
            return None

    monkeypatch.setattr(
        task_runner,
        "_post_print_pending_jobs",
        lambda printer: [] if printer["printer_name"] == "OfflineNoJob" else list(printer["jobs"]),
    )
    monkeypatch.setattr(
        task_runner,
        "_monitor_printer_snapshot",
        lambda printer_name: {
            "exists": True,
            "paused": False,
            "offline": False,
            "printer_name": printer_name,
        },
    )
    monkeypatch.setattr(
        task_runner,
        "_send_post_print_monitor_wecom",
        lambda *args, **kwargs: sent.append(kwargs) or (True, "sent"),
    )

    assert task_runner._process_post_print_monitor_run(FakeDb(), run, now=now) is True
    assert sent == []
    monitor = run.stats_json[task_runner.POST_PRINT_MONITOR_KEY]
    assert monitor["status"] == "active"
    assert monitor["last_results"] == [
        {"printer_name": "OfflineNoJob", "status": "queue_cleared", "pending_job_count": 0},
        {
            "printer_name": "NormalWithJob",
            "status": "pending",
            "pending_job_count": 1,
            "pending_job_ids": ["NormalWithJob-2"],
        },
    ]


def test_post_print_monitor_expires_without_scanning_after_fifteen_minutes(monkeypatch):
    run = ScheduledTaskRun(
        id=184,
        task_type="auto_order_pipeline",
        stats_json={
            task_runner.POST_PRINT_MONITOR_KEY: {
                "status": "active",
                "expires_at": "2026-07-31T00:27:08",
                "printers": [{"printer_name": "PrinterA", "jobs": [{"queue_job_id": "PrinterA-1"}]}],
            }
        },
    )
    monkeypatch.setattr(
        task_runner,
        "_post_print_pending_jobs",
        lambda _printer: (_ for _ in ()).throw(AssertionError("expired monitor must not scan")),
    )

    assert task_runner._process_post_print_monitor_run(object(), run, now=datetime(2026, 7, 31, 0, 27, 9)) is True
    assert run.stats_json[task_runner.POST_PRINT_MONITOR_KEY]["status"] == "expired"


@pytest.mark.asyncio
async def test_auto_order_pipeline_records_printer_monitor_failure_without_blocking(monkeypatch):
    order = SimpleNamespace(
        id=101,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="DEMO-TRACKING-0019",
        picking_at=None,
        updated_at=None,
    )
    finished_steps = []
    submitted_jobs = []
    purchase = SimpleNamespace(id=56, purchase_no="PO20260701-001")

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([order])

        def commit(self):
            pass

    def fake_start_step(db, run_id, step_code, step_name, payload):
        return SimpleNamespace(step_code=step_code, step_name=step_name)

    def fake_finish_step(db, step, *, status, message, stats, payload=None):
        finished_steps.append((step.step_code, status, message, stats))

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        return {order.id: _blank_pdf(164, 113)}, 0, 1, 0

    async def fake_refresh_status(db, rows, **kwargs):
        return {}

    async def fake_logistics(db, rows, **kwargs):
        return {}

    def fake_move_to_printing(db, rows):
        for row in rows:
            row.biz_status = "待打印"

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", fake_finish_step)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", lambda db, run_id, order, **updates: SimpleNamespace(order_id=order.id, **updates))
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_move_to_printing", fake_move_to_printing)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh_status)
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", fake_logistics)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)
    monkeypatch.setattr(task_runner, "_backup_merged_pdf", lambda platform, run_id, pdf_bytes: "/tmp/success.pdf")
    monkeypatch.setattr(task_runner, "_printer_setting_map", lambda db: {"ozon": SimpleNamespace(printer_name="DemoPrinter")})
    monkeypatch.setattr(task_runner, "_previous_printed_rows", lambda db, run: {})
    monkeypatch.setattr(task_runner, "_run_printer_monitor_step", lambda db, task, run, printer_names: (_ for _ in ()).throw(RuntimeError("monitor down")))
    monkeypatch.setattr(
        task_runner,
        "_submit_pdf_to_printer",
        lambda *args, **kwargs: submitted_jobs.append(kwargs.get("job_name")) or (True, "已提交打印队列"),
    )
    monkeypatch.setattr(task_runner, "_mark_labels_printed", lambda db, order_ids: None)
    monkeypatch.setattr(task_runner, "_generate_purchase_order_for_orders", lambda db, rows: purchase)
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", lambda db, rows, purchase_row: None)
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))

    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={"logistics_ready_timeout_seconds": 0})
    run = ScheduledTaskRun(id=38, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)

    assert status == "success"
    assert submitted_jobs
    assert stats["printer_monitor"][0]["status"] == "error"
    assert "monitor down" in stats["printer_monitor"][0]["message"]
    assert any(item[0] == task_runner.STEP_SUBMIT_PRINT for item in finished_steps)


@pytest.mark.asyncio
async def test_auto_order_pipeline_defers_post_submit_notifications_to_aggregate_monitor(monkeypatch):
    order = SimpleNamespace(
        id=102,
        platform="ozon",
        biz_status="待处理",
        local_status="new",
        shipment_tracking_number="DEMO-TRACKING-0025",
        picking_at=None,
        updated_at=None,
    )
    finished_steps = []
    purchase = SimpleNamespace(id=57, purchase_no="PO20260701-002")

    class FakeDb:
        def scalars(self, stmt):
            return _ScalarResult([order])

        def commit(self):
            pass

    def fake_start_step(db, run_id, step_code, step_name, payload):
        return SimpleNamespace(step_code=step_code, step_name=step_name)

    def fake_finish_step(db, step, *, status, message, stats, payload=None):
        finished_steps.append((step.step_code, status, message, stats))

    async def fake_ensure_labels_cached(db, rows, load_bytes=True):
        return {order.id: _blank_pdf(164, 113)}, 0, 1, 0

    async def fake_refresh_status(db, rows, **kwargs):
        return {}

    async def fake_logistics(db, rows, **kwargs):
        return {}

    def fake_move_to_printing(db, rows):
        for row in rows:
            row.biz_status = "待打印"

    monkeypatch.setattr(task_runner, "_start_step", fake_start_step)
    monkeypatch.setattr(task_runner, "_finish_step", fake_finish_step)
    monkeypatch.setattr(task_runner, "_select_orders_for_run", lambda db, run: ([order], False))
    monkeypatch.setattr(task_runner, "_upsert_run_order", lambda db, run_id, order, **updates: SimpleNamespace(order_id=order.id, **updates))
    monkeypatch.setattr(task_runner, "add_order_operation_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_runner, "_move_to_printing", fake_move_to_printing)
    monkeypatch.setattr(task_runner, "refresh_order_logistics_for_rows", fake_refresh_status)
    monkeypatch.setattr(task_runner, "submit_platform_shipments_and_refresh_logistics", fake_logistics)
    monkeypatch.setattr(task_runner, "_ensure_labels_cached", fake_ensure_labels_cached)
    monkeypatch.setattr(task_runner, "_backup_merged_pdf", lambda platform, run_id, pdf_bytes: "/tmp/success.pdf")
    monkeypatch.setattr(task_runner, "_printer_setting_map", lambda db: {"ozon": SimpleNamespace(printer_name="DemoPrinter")})
    monkeypatch.setattr(task_runner, "_previous_printed_rows", lambda db, run: {})
    monkeypatch.setattr(task_runner, "_run_printer_monitor_step", lambda db, task, run, printer_names: [])
    monkeypatch.setattr(task_runner, "_submit_pdf_to_printer", lambda *args, **kwargs: (True, "已提交打印队列"))
    monkeypatch.setattr(task_runner, "_mark_labels_printed", lambda db, order_ids: None)
    monkeypatch.setattr(task_runner, "_generate_purchase_order_for_orders", lambda db, rows: purchase)
    monkeypatch.setattr(task_runner, "_move_to_picking_after_purchase", lambda db, rows, purchase_row: None)
    monkeypatch.setattr(task_runner, "_purchase_missing_product_name_rows", lambda db, rows: (rows, [], []))

    task = ScheduledTask(name="demo", task_type="auto_order_pipeline", cron_expr="0 9 * * *", settings={"logistics_ready_timeout_seconds": 0})
    run = ScheduledTaskRun(id=39, scheduled_task_id=1, task_type="auto_order_pipeline")

    status, summary, stats = await _auto_order_pipeline_async(FakeDb(), task, run)
    submit_stats = next(item[3] for item in finished_steps if item[0] == task_runner.STEP_SUBMIT_PRINT)

    assert status == "success"
    assert "打印成功 1 条" in summary
    assert stats["print_success_count"] == 1
    assert stats["print_failed_count"] == 0
    assert stats["post_submit_printer_notifications"] == []
    assert submit_stats["post_submit_printer_notification_count"] == 0
