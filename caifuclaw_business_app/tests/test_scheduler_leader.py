from datetime import timedelta, timezone
from types import SimpleNamespace

import app.scheduler as scheduler_module


class FakeDb:
    def __init__(self, events, rows=None):
        self.events = events
        self.rows = rows or []

    def commit(self):
        self.events.append(("commit",))

    def rollback(self):
        self.events.append(("rollback",))

    def close(self):
        self.events.append(("close",))

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: list(self.rows))

    def execute(self, _stmt):
        return SimpleNamespace(all=lambda: list(self.rows))


class FakeScheduler:
    def __init__(self):
        self.jobs = {}
        self.running = False
        self.timezone = timezone(timedelta(hours=8))

    def add_job(self, func, trigger, **kwargs):
        self.jobs[kwargs["id"]] = (func, trigger, kwargs)

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def get_jobs(self):
        return [SimpleNamespace(id=job_id) for job_id in self.jobs]

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)

    def start(self):
        self.running = True


def test_start_scheduler_keeps_election_loop_when_startup_is_standby(monkeypatch):
    fake_scheduler = FakeScheduler()
    events = []

    monkeypatch.setattr(scheduler_module, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler_module, "_scheduler_is_leader", False)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: SimpleNamespace(scheduler_enabled=True, scheduler_heartbeat_interval_seconds=60),
    )
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: FakeDb(events))
    monkeypatch.setattr(scheduler_module, "try_acquire_scheduler_leader", lambda db: False)
    monkeypatch.setattr(
        scheduler_module,
        "write_scheduler_heartbeat",
        lambda db, *, is_leader, message: events.append(("heartbeat", is_leader, message)),
    )
    monkeypatch.setattr(
        scheduler_module,
        "audit_sync_event",
        lambda db, event_type, **kwargs: events.append(("audit", event_type, kwargs["status"])),
    )
    monkeypatch.setattr(scheduler_module, "reload_jobs", lambda: events.append(("reload_jobs",)))

    scheduler_module.start_scheduler()

    assert fake_scheduler.running is True
    assert scheduler_module.SCHEDULER_LEADER_ELECTION_JOB_ID in fake_scheduler.jobs
    assert fake_scheduler.jobs[scheduler_module.SCHEDULER_LEADER_ELECTION_JOB_ID][2]["seconds"] == 10
    assert scheduler_module._scheduler_is_leader is False
    assert ("audit", "scheduler_startup", "standby") in events
    assert ("reload_jobs",) not in events


def test_leader_election_promotes_standby_and_reloads_jobs(monkeypatch):
    events = []

    monkeypatch.setattr(scheduler_module, "_scheduler_is_leader", False)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: FakeDb(events))
    monkeypatch.setattr(scheduler_module, "try_acquire_scheduler_leader", lambda db: True)
    monkeypatch.setattr(
        scheduler_module,
        "write_scheduler_heartbeat",
        lambda db, *, is_leader, message: events.append(("heartbeat", is_leader, message)),
    )
    monkeypatch.setattr(
        scheduler_module,
        "audit_sync_event",
        lambda db, event_type, **kwargs: events.append(("audit", event_type, kwargs["status"])),
    )
    monkeypatch.setattr(scheduler_module, "reload_jobs", lambda: events.append(("reload_jobs",)))

    scheduler_module._run_scheduler_leader_election()

    assert scheduler_module._scheduler_is_leader is True
    assert ("heartbeat", True, "leader") in events
    assert ("audit", "scheduler_leader_promoted", "leader") in events
    assert ("reload_jobs",) in events


def test_recent_missed_cron_task_is_scheduled_as_catchup(monkeypatch):
    fake_scheduler = FakeScheduler()
    fake_scheduler.running = True
    events = []
    task = SimpleNamespace(id=2, enabled=True, cron_expr="40 12 * * *", settings={"schedule_mode": "cron"})

    monkeypatch.setattr(scheduler_module, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler_module, "_scheduler_is_leader", True)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: FakeDb(events, rows=[task]))
    monkeypatch.setattr(scheduler_module, "_recent_cron_fire_times", lambda cron_expr, *, now, lookback: [now])
    monkeypatch.setattr(scheduler_module, "_scheduled_task_has_run_since", lambda db, task_id, scheduled_at, now: False)
    monkeypatch.setattr(
        scheduler_module,
        "audit_sync_event",
        lambda db, event_type, **kwargs: events.append(("audit", event_type, kwargs["status"], kwargs["extra"]["task_id"])),
    )

    scheduled_count = scheduler_module._schedule_recent_missed_cron_tasks()

    catchup_jobs = [job for job_id, job in fake_scheduler.jobs.items() if job_id.startswith("scheduled_task_catchup:")]
    assert scheduled_count == 1
    assert catchup_jobs[0][2]["args"] == [2]
    assert ("audit", "scheduled_task_catchup_scheduled", "scheduled", 2) in events


def test_recent_missed_cron_task_skips_when_manual_run_already_exists(monkeypatch):
    fake_scheduler = FakeScheduler()
    fake_scheduler.running = True
    events = []
    task = SimpleNamespace(id=2, enabled=True, cron_expr="40 12 * * *", settings={"schedule_mode": "cron"})

    monkeypatch.setattr(scheduler_module, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler_module, "_scheduler_is_leader", True)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: FakeDb(events, rows=[task]))
    monkeypatch.setattr(scheduler_module, "_recent_cron_fire_times", lambda cron_expr, *, now, lookback: [now])
    monkeypatch.setattr(scheduler_module, "_scheduled_task_has_run_since", lambda db, task_id, scheduled_at, now: True)
    monkeypatch.setattr(
        scheduler_module,
        "audit_sync_event",
        lambda db, event_type, **kwargs: events.append(("audit", event_type)),
    )

    scheduled_count = scheduler_module._schedule_recent_missed_cron_tasks()

    assert scheduled_count == 0
    assert not any(job_id.startswith("scheduled_task_catchup:") for job_id in fake_scheduler.jobs)
    assert not any(event[0] == "audit" for event in events)


def test_reload_jobs_schedules_background_jobs(monkeypatch):
    fake_scheduler = FakeScheduler()
    events = []

    monkeypatch.setattr(scheduler_module, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler_module, "_scheduler_is_leader", True)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: SimpleNamespace(
            order_sync_startup_stagger_seconds=15,
            scheduler_heartbeat_interval_seconds=60,
            scheduler_watchdog_interval_seconds=60,
            oauth_token_maintenance_interval_seconds=1800,
            scheduled_task_retry_scan_interval_seconds=60,
            exchange_rate_sync_cron_exprs=[],
        ),
    )
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: FakeDb(events))

    scheduler_module.reload_jobs()

    post_print_job = fake_scheduler.jobs[scheduler_module.POST_PRINT_MONITOR_JOB_ID]
    assert post_print_job[0] is scheduler_module._run_post_print_monitors
    assert post_print_job[1] == "interval"
    assert post_print_job[2]["seconds"] == scheduler_module.POST_PRINT_MONITOR_INTERVAL_SECONDS
    assert post_print_job[2]["max_instances"] == 1
    traffic_job = fake_scheduler.jobs[scheduler_module.TRAFFIC_ANALYTICS_SYNC_JOB_ID]
    assert traffic_job[0] is scheduler_module._run_traffic_analytics_sync
    assert traffic_job[1] == "cron"
    assert traffic_job[2]["hour"] == 6
    assert traffic_job[2]["minute"] == 0
    assert traffic_job[2]["max_instances"] == 1
    traffic_retry_job = fake_scheduler.jobs[scheduler_module.TRAFFIC_ANALYTICS_RETRY_JOB_ID]
    assert traffic_retry_job[0] is scheduler_module._run_traffic_analytics_retry
    assert traffic_retry_job[1] == "cron"
    assert traffic_retry_job[2]["hour"] == "7-11"
    assert traffic_retry_job[2]["minute"] == 30
    assert traffic_retry_job[2]["max_instances"] == 1
    catalog_full_job = fake_scheduler.jobs[scheduler_module.PLATFORM_PRODUCT_CATALOG_SYNC_JOB_ID]
    assert catalog_full_job[0] is scheduler_module._run_platform_product_catalog_sync
    assert catalog_full_job[1] == "cron"
    assert catalog_full_job[2]["hour"] == 4
    assert catalog_full_job[2]["minute"] == 0
    assert catalog_full_job[2]["args"] == [scheduler_module.CATALOG_SYNC_MODE_FULL]
    catalog_incremental_job = fake_scheduler.jobs[scheduler_module.PLATFORM_PRODUCT_CATALOG_INCREMENTAL_SYNC_JOB_ID]
    assert catalog_incremental_job[0] is scheduler_module._run_platform_product_catalog_sync
    assert catalog_incremental_job[1] == "cron"
    assert catalog_incremental_job[2]["minute"] == 30
    assert catalog_incremental_job[2]["args"] == [scheduler_module.CATALOG_SYNC_MODE_INCREMENTAL]
    assert "ozon_category_cache_sync" not in fake_scheduler.jobs


def test_traffic_retry_submits_only_on_scheduler_leader(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler_module, "_scheduler_is_leader", True)
    monkeypatch.setattr(
        scheduler_module,
        "run_scheduled_traffic_sync",
        lambda **kwargs: calls.append(kwargs) or 2,
    )

    scheduler_module._run_traffic_analytics_retry()

    assert calls == [{"triggered_by": "scheduler:retry"}]

    calls.clear()
    monkeypatch.setattr(scheduler_module, "_scheduler_is_leader", False)
    scheduler_module._run_traffic_analytics_retry()
    assert calls == []


def test_sync_watchdog_marks_stale_scheduled_task_runs(monkeypatch):
    fake_scheduler = FakeScheduler()
    events = []

    monkeypatch.setattr(scheduler_module, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler_module, "_scheduler_is_leader", True)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: FakeDb(events))
    monkeypatch.setattr(scheduler_module, "mark_stale_running_jobs", lambda db: 2)
    monkeypatch.setattr(scheduler_module, "mark_stale_scheduled_task_runs", lambda db: 1)
    monkeypatch.setattr(scheduler_module, "overdue_enabled_sync_accounts", lambda db: [])
    monkeypatch.setattr(scheduler_module, "runtime_owner_id", lambda: "owner-1")

    async def fake_run_due_catchups(db):
        return []

    monkeypatch.setattr(scheduler_module, "run_due_catchups", fake_run_due_catchups)
    monkeypatch.setattr(
        scheduler_module,
        "audit_sync_event",
        lambda db, event_type, **kwargs: events.append(("audit", event_type, kwargs["message"], kwargs["extra"])),
    )

    scheduler_module._run_sync_watchdog()

    audits = [event for event in events if event[0] == "audit" and event[1] == "sync_watchdog_scan"]
    assert audits
    assert "stale_tasks=1" in audits[0][2]
    assert audits[0][3]["stale_tasks"] == 1
    assert ("commit",) in events


