# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import hashlib
import os
import socket
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .database import engine
from .models import PlatformAccount, SchedulerHeartbeat, SyncAccountState, SyncAuditLog, SyncJobLog, SyncSetting
from .settings import get_settings

SCHEDULER_LOCK_NAME = "caifuclaw_ai_scheduler_leader"
JOB_TYPE_SYNC_ORDERS = "sync_orders"
JOB_TYPE_CATCHUP_ORDERS = "catchup_orders"
_scheduler_leader_connection = None


def runtime_owner_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _advisory_key(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _try_advisory_lock(conn, name: str) -> bool:
    return bool(conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _advisory_key(name)}).scalar())


def _advisory_unlock(conn, name: str) -> None:
    conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _advisory_key(name)})


def try_acquire_scheduler_leader(db: Session) -> bool:
    global _scheduler_leader_connection
    settings = get_settings()
    if not settings.scheduler_leader_lock_enabled:
        return True
    if _scheduler_leader_connection is not None:
        return True
    conn = engine.connect()
    try:
        acquired = _try_advisory_lock(conn, SCHEDULER_LOCK_NAME)
    except Exception:
        conn.close()
        raise
    if not acquired:
        conn.close()
        return False
    _scheduler_leader_connection = conn
    return True


def release_scheduler_leader(db: Session) -> None:
    global _scheduler_leader_connection
    settings = get_settings()
    if settings.scheduler_leader_lock_enabled and _scheduler_leader_connection is not None:
        try:
            _advisory_unlock(_scheduler_leader_connection, SCHEDULER_LOCK_NAME)
        finally:
            _scheduler_leader_connection.close()
            _scheduler_leader_connection = None


@contextmanager
def sync_job_lock(db: Session, platform: str, account_id: str, job_type: str) -> Iterator[bool]:
    lock_name = f"caifuclaw_ai:{job_type}:{platform}:{account_id}"
    conn = engine.connect()
    acquired = False
    try:
        acquired = _try_advisory_lock(conn, lock_name)
    except Exception:
        conn.close()
        raise
    try:
        yield acquired
    finally:
        if acquired:
            _advisory_unlock(conn, lock_name)
        conn.close()


def audit_sync_event(
    db: Session,
    event_type: str,
    *,
    platform: str = "",
    account_id: str = "",
    job_type: str = "",
    status: str = "",
    message: str = "",
    owner_id: str = "",
    extra: dict | None = None,
    commit: bool = False,
) -> SyncAuditLog:
    row = SyncAuditLog(
        event_type=event_type,
        platform=platform or "",
        account_id=account_id or "",
        job_type=job_type or "",
        status=status or "",
        message=message or "",
        owner_id=owner_id or runtime_owner_id(),
        extra=extra or {},
    )
    db.add(row)
    if commit:
        db.commit()
    return row


def write_scheduler_heartbeat(db: Session, *, is_leader: bool, message: str = "") -> SchedulerHeartbeat:
    owner_id = runtime_owner_id()
    now = datetime.utcnow()
    row = db.scalar(select(SchedulerHeartbeat).where(SchedulerHeartbeat.owner_id == owner_id))
    if not row:
        row = SchedulerHeartbeat(
            owner_id=owner_id,
            host=socket.gethostname(),
            pid=os.getpid(),
            is_leader=is_leader,
            started_at=now,
        )
        db.add(row)
    row.is_leader = is_leader
    row.last_seen_at = now
    row.message = message or ("leader" if is_leader else "standby")
    return row


def get_or_create_sync_state(db: Session, platform: str, account_id: str, job_type: str = JOB_TYPE_SYNC_ORDERS) -> SyncAccountState:
    row = db.scalar(
        select(SyncAccountState).where(
            SyncAccountState.platform == platform,
            SyncAccountState.account_id == account_id,
            SyncAccountState.job_type == job_type,
        )
    )
    if row:
        return row
    row = SyncAccountState(platform=platform, account_id=account_id, job_type=job_type)
    db.add(row)
    db.flush()
    return row


def mark_sync_scheduled(
    db: Session,
    platform: str,
    account_id: str,
    *,
    run_at: datetime,
    job_type: str = JOB_TYPE_SYNC_ORDERS,
    commit: bool = False,
) -> SyncAccountState:
    row = get_or_create_sync_state(db, platform, account_id, job_type)
    row.next_due_at = run_at.replace(tzinfo=None)
    row.last_status = row.last_status or "scheduled"
    row.updated_at = datetime.utcnow()
    if commit:
        db.commit()
    return row


def mark_sync_started(db: Session, platform: str, account_id: str, job_type: str = JOB_TYPE_SYNC_ORDERS) -> SyncAccountState:
    row = get_or_create_sync_state(db, platform, account_id, job_type)
    now = datetime.utcnow()
    row.last_started_at = now
    row.last_status = "running"
    row.last_message = ""
    row.updated_at = now
    return row


def mark_sync_success(
    db: Session,
    platform: str,
    account_id: str,
    *,
    job_type: str = JOB_TYPE_SYNC_ORDERS,
    message: str = "",
) -> SyncAccountState:
    row = get_or_create_sync_state(db, platform, account_id, job_type)
    now = datetime.utcnow()
    row.last_finished_at = now
    row.last_success_at = now
    row.last_status = "success"
    row.consecutive_failures = 0
    row.overdue_since = None
    row.catchup_required = False
    row.catchup_to = None
    row.last_message = message or ""
    row.updated_at = now
    return row


def mark_sync_failed(
    db: Session,
    platform: str,
    account_id: str,
    *,
    job_type: str = JOB_TYPE_SYNC_ORDERS,
    message: str = "",
) -> SyncAccountState:
    row = get_or_create_sync_state(db, platform, account_id, job_type)
    now = datetime.utcnow()
    row.last_finished_at = now
    row.last_failed_at = now
    row.last_status = "failed"
    row.consecutive_failures = int(row.consecutive_failures or 0) + 1
    row.last_message = message or ""
    row.updated_at = now
    return row


def mark_sync_skipped_locked(db: Session, platform: str, account_id: str, *, job_type: str = JOB_TYPE_SYNC_ORDERS) -> None:
    row = get_or_create_sync_state(db, platform, account_id, job_type)
    row.last_status = "skipped_locked"
    row.last_message = "sync already running"
    row.updated_at = datetime.utcnow()
    audit_sync_event(
        db,
        "job_skipped_locked",
        platform=platform,
        account_id=account_id,
        job_type=job_type,
        status="skipped",
        message="sync already running",
    )


def mark_catchup_required(
    db: Session,
    platform: str,
    account_id: str,
    *,
    catchup_from: datetime,
    catchup_to: datetime,
    message: str,
) -> SyncAccountState:
    row = get_or_create_sync_state(db, platform, account_id, JOB_TYPE_SYNC_ORDERS)
    now = datetime.utcnow()
    row.catchup_required = True
    row.catchup_from = catchup_from.replace(tzinfo=None)
    row.catchup_to = catchup_to.replace(tzinfo=None)
    row.last_message = message
    row.updated_at = now
    audit_sync_event(
        db,
        "catchup_required",
        platform=platform,
        account_id=account_id,
        job_type=JOB_TYPE_SYNC_ORDERS,
        status="warning",
        message=message,
        extra={"catchup_from": row.catchup_from.isoformat(), "catchup_to": row.catchup_to.isoformat()},
    )
    return row


def _account_interval(setting: SyncSetting) -> int:
    settings = get_settings()
    min_interval = max(1, int(settings.order_sync_min_interval_seconds or 1))
    return max(min_interval, int(setting.interval_seconds or min_interval))


def overdue_enabled_sync_accounts(db: Session) -> list[dict]:
    settings = get_settings()
    now = datetime.utcnow()
    rows = db.execute(
        select(SyncSetting, PlatformAccount, SyncAccountState)
        .join(
            PlatformAccount,
            (PlatformAccount.platform == SyncSetting.platform) & (PlatformAccount.account_id == SyncSetting.account_id),
        )
        .outerjoin(
            SyncAccountState,
            (SyncAccountState.platform == SyncSetting.platform)
            & (SyncAccountState.account_id == SyncSetting.account_id)
            & (SyncAccountState.job_type == JOB_TYPE_SYNC_ORDERS),
        )
        .where(SyncSetting.enabled == True, PlatformAccount.enabled == True)
    ).all()
    overdue: list[dict] = []
    for setting, account, state in rows:
        interval = _account_interval(setting)
        grace = max(0, int(settings.sync_overdue_grace_seconds or 0))
        last_success = state.last_success_at if state else None
        last_started = state.last_started_at if state else None
        next_due = state.next_due_at if state else None
        reference = last_success or account.last_sync_at or setting.last_run_at or last_started
        if not reference:
            continue
        threshold = reference + timedelta(seconds=interval * 2 + grace)
        if now <= threshold:
            continue
        catchup_from = reference - timedelta(seconds=max(0, int(settings.sync_catchup_overlap_seconds or 0)))
        max_window = timedelta(seconds=max(interval, int(settings.sync_catchup_max_window_seconds or interval)))
        if now - catchup_from > max_window:
            catchup_from = now - max_window
        overdue.append(
            {
                "platform": setting.platform,
                "account_id": setting.account_id,
                "interval_seconds": interval,
                "last_success_at": last_success,
                "reference_at": reference,
                "threshold_at": threshold,
                "catchup_from": catchup_from,
                "catchup_to": now,
                "state": state,
            }
        )
    return overdue


def mark_stale_running_jobs(db: Session) -> int:
    settings = get_settings()
    timeout = max(60, int(settings.sync_running_timeout_seconds or 1800))
    cutoff = datetime.utcnow() - timedelta(seconds=timeout)
    rows = db.scalars(
        select(SyncJobLog).where(
            SyncJobLog.status == "running",
            SyncJobLog.started_at < cutoff,
            SyncJobLog.ended_at.is_(None),
        )
    ).all()
    for row in rows:
        row.status = "failed"
        row.message = (row.message or "") + f" | marked stale after {timeout}s"
        row.ended_at = datetime.utcnow()
        audit_sync_event(
            db,
            "stale_running_job_marked_failed",
            platform=row.platform,
            account_id=row.account_id,
            job_type=row.job_type,
            status="failed",
            message=row.message,
            extra={"job_log_id": row.id, "started_at": row.started_at.isoformat() if row.started_at else None},
        )
        mark_sync_failed(db, row.platform, row.account_id, job_type=row.job_type or JOB_TYPE_SYNC_ORDERS, message=row.message)
    return len(rows)


def sync_health_snapshot(db: Session) -> dict:
    now = datetime.utcnow()
    heartbeats = db.scalars(select(SchedulerHeartbeat).order_by(SchedulerHeartbeat.last_seen_at.desc())).all()
    rows = db.execute(
        select(SyncSetting, PlatformAccount, SyncAccountState)
        .outerjoin(
            PlatformAccount,
            (PlatformAccount.platform == SyncSetting.platform) & (PlatformAccount.account_id == SyncSetting.account_id),
        )
        .outerjoin(
            SyncAccountState,
            (SyncAccountState.platform == SyncSetting.platform)
            & (SyncAccountState.account_id == SyncSetting.account_id)
            & (SyncAccountState.job_type == JOB_TYPE_SYNC_ORDERS),
        )
        .order_by(SyncSetting.platform, SyncSetting.account_id)
    ).all()
    accounts = []
    for setting, account, state in rows:
        interval = _account_interval(setting)
        reference = (state.last_success_at if state else None) or (account.last_sync_at if account else None) or setting.last_run_at
        overdue = False
        if setting.enabled and account and account.enabled and reference:
            overdue = now > reference + timedelta(seconds=interval * 2 + max(0, int(get_settings().sync_overdue_grace_seconds or 0)))
        accounts.append(
            {
                "platform": setting.platform,
                "account_id": setting.account_id,
                "display_name": account.display_name if account else "",
                "sync_enabled": bool(setting.enabled),
                "account_enabled": bool(account.enabled) if account else False,
                "interval_seconds": interval,
                "last_run_at": setting.last_run_at.isoformat() if setting.last_run_at else None,
                "last_sync_at": account.last_sync_at.isoformat() if account and account.last_sync_at else None,
                "last_started_at": state.last_started_at.isoformat() if state and state.last_started_at else None,
                "last_success_at": state.last_success_at.isoformat() if state and state.last_success_at else None,
                "last_failed_at": state.last_failed_at.isoformat() if state and state.last_failed_at else None,
                "next_due_at": state.next_due_at.isoformat() if state and state.next_due_at else None,
                "last_status": state.last_status if state else "",
                "consecutive_failures": int(state.consecutive_failures or 0) if state else 0,
                "overdue": overdue,
                "catchup_required": bool(state.catchup_required) if state else False,
                "catchup_from": state.catchup_from.isoformat() if state and state.catchup_from else None,
                "catchup_to": state.catchup_to.isoformat() if state and state.catchup_to else None,
                "last_message": state.last_message if state else "",
            }
        )
    return {
        "now": now.isoformat(),
        "scheduler_enabled": bool(get_settings().scheduler_enabled),
        "leader_lock_enabled": bool(get_settings().scheduler_leader_lock_enabled),
        "heartbeats": [
            {
                "owner_id": row.owner_id,
                "host": row.host,
                "pid": row.pid,
                "is_leader": row.is_leader,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "message": row.message,
            }
            for row in heartbeats
        ],
        "accounts": accounts,
    }
