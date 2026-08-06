from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from scripts import sync_pending_ozon_tracking as script


def _args(**overrides):
    values = {
        "status": "待处理",
        "account_id": [],
        "shop": [],
        "order": [],
        "include_tracked": False,
        "limit": 0,
        "show_orders": 50,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_rows_for_sync_skips_tracked_orders_by_default(monkeypatch):
    missing = SimpleNamespace(id=1)
    tracked = SimpleNamespace(id=2)

    monkeypatch.setattr(
        script,
        "_safe_tracking_number",
        lambda _db, row: "TRACK-2" if row.id == tracked.id else "",
    )

    assert script._rows_for_sync(object(), [missing, tracked], include_tracked=False, limit=0) == [missing]


def test_rows_for_sync_can_include_tracked_and_apply_limit(monkeypatch):
    rows = [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)]
    monkeypatch.setattr(script, "_safe_tracking_number", lambda _db, _row: "TRACK")

    assert script._rows_for_sync(object(), rows, include_tracked=True, limit=2) == rows[:2]


def test_compact_stats_replaces_order_results_with_count():
    stats = {
        "tracking_updated": 2,
        "order_results": {"1": {"tracking_updated": 1}, "2": {"tracking_updated": 1}},
    }

    assert script._compact_stats(stats) == {"tracking_updated": 2, "order_result_count": 2}


def test_build_summary_counts_tracking_changes():
    args = _args()
    before = [
        {"id": 1, "tracking_number": ""},
        {"id": 2, "tracking_number": "DEMO-TRACKING-0028"},
        {"id": 3, "tracking_number": "DEMO-TRACKING-0029"},
    ]
    after = [
        {"id": 1, "tracking_number": "DEMO-TRACKING-0030"},
        {"id": 2, "tracking_number": "DEMO-TRACKING-0031"},
        {"id": 3, "tracking_number": "DEMO-TRACKING-0029"},
    ]

    summary = script._build_summary(
        args=args,
        started_at=datetime.now(timezone.utc),
        mode="sync",
        before=before,
        after=after,
        trigger_stats={"tracking_updated": 2, "order_results": {"1": {}, "2": {}}},
    )

    assert summary["selected_orders"] == 3
    assert summary["tracking_before"] == 2
    assert summary["tracking_after"] == 3
    assert summary["tracking_updated_orders"] == 2
    assert summary["trigger_stats"]["order_result_count"] == 2
