from datetime import datetime, timedelta
from types import SimpleNamespace

from app import sync_runtime


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return _FakeScalarResult(self._rows)


def test_overdue_enabled_sync_accounts_marks_window(monkeypatch):
    now = datetime(2026, 6, 10, 8, 0, 0)
    monkeypatch.setattr(sync_runtime, "datetime", SimpleNamespace(utcnow=lambda: now))
    monkeypatch.setattr(
        sync_runtime,
        "get_settings",
        lambda: SimpleNamespace(
            order_sync_min_interval_seconds=600,
            sync_overdue_grace_seconds=300,
            sync_catchup_overlap_seconds=3600,
            sync_catchup_max_window_seconds=259200,
        ),
    )

    setting = SimpleNamespace(platform="joom_logistics", account_id="JOOM-DEMO-001", interval_seconds=600)
    account = SimpleNamespace(last_sync_at=now - timedelta(hours=2))
    state = SimpleNamespace(last_success_at=now - timedelta(hours=2), last_started_at=None, next_due_at=None)

    rows = sync_runtime.overdue_enabled_sync_accounts(_FakeDb([(setting, account, state)]))

    assert len(rows) == 1
    assert rows[0]["platform"] == "joom_logistics"
    assert rows[0]["account_id"] == "JOOM-DEMO-001"
    assert rows[0]["catchup_from"] == now - timedelta(hours=3)
    assert rows[0]["catchup_to"] == now


def test_overdue_enabled_sync_accounts_ignores_recent_success(monkeypatch):
    now = datetime(2026, 6, 10, 8, 0, 0)
    monkeypatch.setattr(sync_runtime, "datetime", SimpleNamespace(utcnow=lambda: now))
    monkeypatch.setattr(
        sync_runtime,
        "get_settings",
        lambda: SimpleNamespace(
            order_sync_min_interval_seconds=600,
            sync_overdue_grace_seconds=300,
            sync_catchup_overlap_seconds=3600,
            sync_catchup_max_window_seconds=259200,
        ),
    )

    setting = SimpleNamespace(platform="ozon", account_id="100002", interval_seconds=600)
    account = SimpleNamespace(last_sync_at=now - timedelta(minutes=5))
    state = SimpleNamespace(last_success_at=now - timedelta(minutes=5), last_started_at=None, next_due_at=None)

    assert sync_runtime.overdue_enabled_sync_accounts(_FakeDb([(setting, account, state)])) == []
