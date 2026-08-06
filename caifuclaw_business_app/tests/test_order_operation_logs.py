# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime
from types import SimpleNamespace

import app.task_runner as task_runner
from app.order_operation_logs import (
    MAX_ORDER_LOG_EXTRA_BYTES,
    ORDER_LOG_SYSTEM_SOURCE,
    SYSTEM_OPERATOR,
    add_order_operation_log,
    compact_order_log_extra,
    order_log_changes,
    safe_exception_message,
)
from app.sync_engine import _order_sync_log_changes, _order_sync_log_description
from scripts.cleanup_order_operation_logs import candidate_cte_sql, cleanup_reason


class FakeDb:
    def __init__(self):
        self.rows = []

    def scalar(self, _statement):
        return None

    def add(self, row):
        self.rows.append(row)


def order(**overrides):
    values = {
        "id": 7,
        "platform": "mercadolibre",
        "platform_order_no": "ORDER-7",
        "posting_number": "DEMO-ORDER-0045",
        "platform_order_id": "PLATFORM-7",
        "biz_status": "待处理",
        "platform_status": "ready_to_ship",
        "shipment_tracking_number": "DEMO-TRACKING-0009",
        "fulfillment_type": "FBS",
        "buyer_selected_logistics": "standard",
        "raw_payload": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_system_operator_and_generated_event_key_are_unambiguous():
    db = FakeDb()

    row = add_order_operation_log(
        db,
        order_id=7,
        operation_type="sync_logistics",
        operation_attribute="同步物流信息",
        description="订单 ORDER-7 状态更新",
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
    )

    assert SYSTEM_OPERATOR == "系统任务"
    assert row is not None
    assert row.event_key.startswith("system:7:sync_logistics:")


def test_large_extra_payload_is_replaced_with_a_small_summary():
    compact = compact_order_log_extra({"run_id": 8, "wait_stats": {"attempts": ["x" * 1000] * 20}})

    assert compact["payload_truncated"] is True
    assert compact["run_id"] == 8
    assert "wait_stats" not in compact
    assert len(str(compact).encode("utf-8")) < MAX_ORDER_LOG_EXTRA_BYTES


def test_order_log_changes_returns_only_real_field_differences():
    changes = order_log_changes(
        {"status": "待处理", "tracking": "-"},
        {"status": "已发货", "tracking": "-"},
        {"status": "当前状态", "tracking": "货运单号"},
    )

    assert changes == [{"field": "status", "label": "当前状态", "before": "待处理", "after": "已发货"}]


def test_order_sync_change_detection_suppresses_unchanged_updates():
    row = order()
    before = {
        "biz_status": "待处理",
        "platform_status": "ready_to_ship",
        "posting_number": "DEMO-ORDER-0045",
        "shipment_tracking_number": "DEMO-TRACKING-0009",
        "fulfillment_type": "FBS",
        "buyer_selected_logistics": "standard",
    }

    assert _order_sync_log_changes(row, before) == []
    assert "核心状态和物流信息无变化" in _order_sync_log_description(row, before, created=False)


def test_cleanup_classifier_never_matches_manual_or_meaningful_events():
    assert cleanup_reason("order_sync", "manual", "订单同步更新") is None
    assert cleanup_reason("mark_shipped", "system", "订单 A 已标记发货") is None
    assert cleanup_reason("order_sync", "system", "订单同步更新") == "legacy_generic_update"
    assert (
        cleanup_reason(
            "sync_logistics",
            "system",
            "定时同步状态刷新：请求 2376 条，返回 777 条，更新 0 条",
        )
        == "global_status_batch"
    )


def test_system_repeat_cleanup_is_limited_to_unkeyed_system_logs():
    sql = candidate_cte_sql()

    assert "source = 'system'" in sql
    assert "coalesce(event_key, '') = ''" in sql
    assert "source = 'manual'" not in sql


def test_mark_labels_printed_logs_only_the_first_system_print(monkeypatch):
    already_printed_at = datetime(2026, 6, 1, 8, 0, 0)
    already_printed = SimpleNamespace(id=1, label_printed_at=already_printed_at, updated_at=None)
    first_print = SimpleNamespace(id=2, label_printed_at=None, updated_at=None)
    captured = {}

    class ScalarRows:
        def all(self):
            return [already_printed, first_print]

    class MarkDb:
        def scalars(self, _statement):
            return ScalarRows()

        def commit(self):
            captured["committed"] = True

    def capture_logs(_db, rows, **_kwargs):
        captured["rows"] = list(rows)

    monkeypatch.setattr(task_runner, "add_order_operation_logs", capture_logs)

    task_runner._mark_labels_printed(MarkDb(), [1, 2])

    assert already_printed.label_printed_at == already_printed_at
    assert first_print.label_printed_at is not None
    assert captured["rows"] == [first_print]
    assert captured["committed"] is True


def test_empty_exception_message_uses_exception_class_name():
    assert safe_exception_message(RuntimeError()) == "RuntimeError"
