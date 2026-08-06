# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from .api_logger import purge_old_logs
from .database import SessionLocal
from .models import PlatformAccount, ScheduledTask, ScheduledTaskRun, SyncSetting
from .oauth_tokens import maintain_oauth_tokens
from .settings import get_settings
from .sync_engine import run_due_catchups, sync_account
from .sync_runtime import (
    audit_sync_event,
    mark_catchup_required,
    mark_stale_running_jobs,
    mark_sync_scheduled,
    overdue_enabled_sync_accounts,
    release_scheduler_leader,
    runtime_owner_id,
    try_acquire_scheduler_leader,
    write_scheduler_heartbeat,
)
from .task_runner import (
    POST_PRINT_MONITOR_INTERVAL_SECONDS,
    TASK_TYPE_AUTO_ORDER_PIPELINE,
    _task_poll_interval_seconds,
    mark_stale_scheduled_task_runs,
    process_due_task_retries,
    process_post_print_monitors,
    run_scheduled_task,
)
from .traffic_analytics import run_scheduled_traffic_sync
from .exchange_rates import sync_exchange_rates_from_provider_sync
from .platform_product_catalog import (
    CATALOG_SYNC_MODE_FULL,
    CATALOG_SYNC_MODE_INCREMENTAL,
    synchronize_platform_catalog_sync,
)


logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
_scheduler_is_leader = False
SCHEDULER_LEADER_ELECTION_JOB_ID = "scheduler_leader_election"
SCHEDULED_TASK_CATCHUP_LOOKBACK_MINUTES = 30
TRAFFIC_ANALYTICS_SYNC_JOB_ID = "traffic_analytics_daily_sync"
TRAFFIC_ANALYTICS_RETRY_JOB_ID = "traffic_analytics_current_period_retry"
PLATFORM_PRODUCT_CATALOG_SYNC_JOB_ID = "platform_product_catalog_sync"
PLATFORM_PRODUCT_CATALOG_INCREMENTAL_SYNC_JOB_ID = "platform_product_catalog_incremental_sync"
POST_PRINT_MONITOR_JOB_ID = "post_print_monitor"


def _sync_job_id(platform: str, account_id: str) -> str:
    return f"sync_account:{platform}:{account_id}"


def _scheduled_task_job_id(task_id: int) -> str:
    return f"scheduled_task:{task_id}"


def _schedule_account_once(platform: str, account_id: str, delay_seconds: int) -> None:
    run_at = datetime.now(scheduler.timezone) + timedelta(seconds=max(0, delay_seconds))
    run_at_utc = run_at.astimezone(timezone.utc).replace(tzinfo=None)
    scheduler.add_job(
        _run_account,
        "date",
        run_date=run_at,
        args=[platform, account_id],
        id=_sync_job_id(platform, account_id),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    db = SessionLocal()
    try:
        mark_sync_scheduled(db, platform, account_id, run_at=run_at_utc)
        audit_sync_event(
            db,
            "account_job_scheduled",
            platform=platform,
            account_id=account_id,
            job_type="sync_orders",
            status="scheduled",
            message=f"next run at {run_at.isoformat()}",
            owner_id=runtime_owner_id(),
        )
        db.commit()
    finally:
        db.close()


def _schedule_custom_task_once(task_id: int, delay_seconds: int) -> None:
    scheduler.add_job(
        _run_custom_task,
        "date",
        run_date=datetime.now(scheduler.timezone) + timedelta(seconds=max(0, delay_seconds)),
        args=[task_id],
        id=_scheduled_task_job_id(task_id),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def _task_schedule_mode(task: ScheduledTask) -> str:
    settings = task.settings if isinstance(task.settings, dict) else {}
    mode = str(settings.get("schedule_mode") or "").strip().lower()
    if mode:
        return mode
    if "poll_interval_seconds" in settings:
        return "interval"
    return "cron"


def _schedule_next_account_run(platform: str, account_id: str) -> None:
    if not scheduler.running:
        return
    db = SessionLocal()
    try:
        setting = db.scalar(
            select(SyncSetting).where(SyncSetting.platform == platform, SyncSetting.account_id == account_id)
        )
        account = db.scalar(
            select(PlatformAccount).where(PlatformAccount.platform == platform, PlatformAccount.account_id == account_id)
        )
        if not setting or not setting.enabled or not account or not account.enabled:
            return
        settings = get_settings()
        min_interval = max(1, int(settings.order_sync_min_interval_seconds or 1))
        delay_seconds = max(min_interval, int(setting.interval_seconds or min_interval))
    finally:
        db.close()
    _schedule_account_once(platform, account_id, delay_seconds)


def _schedule_next_custom_task_run(task_id: int) -> None:
    if not scheduler.running:
        return
    db = SessionLocal()
    try:
        task = db.get(ScheduledTask, task_id)
        if not task or not task.enabled or task.task_type != TASK_TYPE_AUTO_ORDER_PIPELINE:
            return
        if _task_schedule_mode(task) != "interval":
            return
        delay_seconds = max(10, _task_poll_interval_seconds(task))
    finally:
        db.close()
    _schedule_custom_task_once(task_id, delay_seconds)


def _run_account(platform: str, account_id: str) -> None:
    async def runner() -> None:
        db = SessionLocal()
        try:
            account = db.scalar(
                select(PlatformAccount).where(PlatformAccount.platform == platform, PlatformAccount.account_id == account_id)
            )
            setting = db.scalar(
                select(SyncSetting).where(SyncSetting.platform == platform, SyncSetting.account_id == account_id)
            )
            if not account or not account.enabled or not setting or not setting.enabled:
                return
            config = {
                "platform": account.platform,
                "account_id": account.account_id,
                "display_name": account.display_name,
                "enabled": account.enabled,
                "auth_type": account.credential_type,
                "settings": account.settings or {},
            }
            await sync_account(db, config)
        finally:
            db.close()

    try:
        asyncio.run(runner())
    finally:
        _schedule_next_account_run(platform, account_id)


def cron_trigger_from_expr(cron_expr: str) -> CronTrigger:
    expr = (cron_expr or "").strip()
    if not expr:
        raise ValueError("Cron 表达式不能为空")
    try:
        return CronTrigger.from_crontab(expr, timezone="Asia/Shanghai")
    except ValueError as exc:
        raise ValueError("Cron 表达式无效，请使用标准 5 段格式") from exc


def _run_custom_task(task_id: int) -> None:
    try:
        run_scheduled_task(task_id, "scheduler")
    finally:
        _schedule_next_custom_task_run(task_id)


def _run_catchup_task(task_id: int) -> None:
    try:
        run_scheduled_task(task_id, "catchup")
    finally:
        _schedule_next_custom_task_run(task_id)


def _run_due_task_retries() -> None:
    process_due_task_retries()


def _run_post_print_monitors() -> None:
    process_post_print_monitors()


def _run_exchange_rate_sync() -> None:
    try:
        result = sync_exchange_rates_from_provider_sync()
        if result.get("failed"):
            print(f"[business_app] exchange rate sync partial failure: {result}")
    except Exception as exc:
        print(f"[business_app] exchange rate sync failed: {exc}")


def _run_platform_product_catalog_sync(mode: str = CATALOG_SYNC_MODE_FULL) -> None:
    if not _scheduler_is_leader:
        return
    sync_mode = CATALOG_SYNC_MODE_INCREMENTAL if mode == CATALOG_SYNC_MODE_INCREMENTAL else CATALOG_SYNC_MODE_FULL
    try:
        result = synchronize_platform_catalog_sync(mode=sync_mode)
        if result.get("failed"):
            logger.warning("Platform product catalog %s sync partial failure: %s", sync_mode, result)
        else:
            logger.info("Platform product catalog %s sync completed: %s", sync_mode, result)
    except Exception:
        logger.exception("Platform product catalog %s sync failed", sync_mode)


def _run_traffic_analytics_sync() -> None:
    if not _scheduler_is_leader:
        return
    try:
        created_count = run_scheduled_traffic_sync()
        logger.info("Daily traffic analytics sync submitted %s account runs", created_count)
    except Exception:
        logger.exception("Daily traffic analytics sync failed")


def _run_traffic_analytics_retry() -> None:
    if not _scheduler_is_leader:
        return
    try:
        created_count = run_scheduled_traffic_sync(triggered_by="scheduler:retry")
        if created_count:
            logger.info("Traffic analytics retry submitted %s account runs", created_count)
    except Exception:
        logger.exception("Traffic analytics retry failed")


def _run_oauth_token_maintenance() -> None:
    db = SessionLocal()
    try:
        result = maintain_oauth_tokens(db)
        if result.get("failed") or result.get("reauthorization_required"):
            print(f"[business_app] oauth token maintenance warning: {result}")
    except Exception as exc:
        print(f"[business_app] oauth token maintenance failed: {exc}")
    finally:
        db.close()


def _run_scheduler_heartbeat() -> None:
    db = SessionLocal()
    try:
        write_scheduler_heartbeat(db, is_leader=_scheduler_is_leader, message="leader" if _scheduler_is_leader else "standby")
        db.commit()
    finally:
        db.close()


def _try_become_scheduler_leader(*, event_type: str, audit_standby: bool) -> bool:
    global _scheduler_is_leader
    if _scheduler_is_leader:
        return True

    acquired = False
    db = SessionLocal()
    try:
        acquired = try_acquire_scheduler_leader(db)
        _scheduler_is_leader = acquired
        write_scheduler_heartbeat(db, is_leader=acquired, message="leader" if acquired else "standby")
        if acquired or audit_standby:
            audit_sync_event(
                db,
                event_type,
                job_type="scheduler",
                status="leader" if acquired else "standby",
                message="scheduler leader acquired" if acquired else "scheduler leader already held by another process",
                owner_id=runtime_owner_id(),
            )
        db.commit()
    finally:
        db.close()

    if acquired:
        reload_jobs()
        _schedule_recent_missed_cron_tasks()
    return acquired


def _run_scheduler_leader_election() -> None:
    try:
        _try_become_scheduler_leader(event_type="scheduler_leader_promoted", audit_standby=False)
    except Exception:
        logger.exception("Scheduler leader election failed")


def _run_sync_watchdog() -> None:
    if not _scheduler_is_leader:
        return
    db = SessionLocal()
    try:
        enabled_rows = db.execute(
            select(SyncSetting.platform, SyncSetting.account_id)
            .join(
                PlatformAccount,
                (PlatformAccount.platform == SyncSetting.platform) & (PlatformAccount.account_id == SyncSetting.account_id),
            )
            .where(SyncSetting.enabled == True, PlatformAccount.enabled == True)
        ).all()
        enabled_keys = {(row.platform, row.account_id) for row in enabled_rows}
        for job in scheduler.get_jobs():
            if not job.id.startswith("sync_account:"):
                continue
            _, platform, account_id = job.id.split(":", 2)
            if (platform, account_id) not in enabled_keys:
                scheduler.remove_job(job.id)
                audit_sync_event(
                    db,
                    "account_job_removed",
                    platform=platform,
                    account_id=account_id,
                    job_type="sync_orders",
                    status="removed",
                    message="account or sync setting disabled",
                    owner_id=runtime_owner_id(),
                )
        restored_count = 0
        for platform, account_id in enabled_keys:
            if not scheduler.get_job(_sync_job_id(platform, account_id)):
                _schedule_next_account_run(platform, account_id)
                restored_count += 1
        stale_count = mark_stale_running_jobs(db)
        stale_task_count = mark_stale_scheduled_task_runs(db)
        catchup_count = 0
        for item in overdue_enabled_sync_accounts(db):
            platform = item["platform"]
            account_id = item["account_id"]
            state = item.get("state")
            if not state or not state.catchup_required:
                mark_catchup_required(
                    db,
                    platform,
                    account_id,
                    catchup_from=item["catchup_from"],
                    catchup_to=item["catchup_to"],
                    message=f"sync overdue since {item['threshold_at'].isoformat()}",
                )
                catchup_count += 1
        audit_sync_event(
            db,
            "sync_watchdog_scan",
            job_type="watchdog",
            status="success",
            message=f"stale={stale_count}, stale_tasks={stale_task_count}, restored={restored_count}, catchup={catchup_count}",
            owner_id=runtime_owner_id(),
            extra={"stale": stale_count, "stale_tasks": stale_task_count, "restored": restored_count, "catchup": catchup_count},
        )
        db.commit()
        catchup_results = asyncio.run(run_due_catchups(db))
        if catchup_results:
            audit_sync_event(
                db,
                "catchup_scan_completed",
                job_type="catchup_orders",
                status="success",
                message=f"catchup jobs={len(catchup_results)}",
                owner_id=runtime_owner_id(),
                extra={"results": catchup_results},
                commit=True,
            )
    except Exception as exc:
        db.rollback()
        logger.exception("Sync watchdog failed")
        try:
            audit_sync_event(
                db,
                "sync_watchdog_failed",
                job_type="watchdog",
                status="failed",
                message=str(exc),
                owner_id=runtime_owner_id(),
                commit=True,
            )
        except Exception:
            logger.exception("Failed to write watchdog failure audit")
    finally:
        db.close()


def run_scheduled_task_now(task_id: int) -> dict:
    run_scheduled_task(task_id, "manual")
    db = SessionLocal()
    try:
        task = db.get(ScheduledTask, task_id)
        return {
            "id": task.id if task else task_id,
            "last_run_at": task.last_run_at.isoformat() if task and task.last_run_at else None,
            "last_status": task.last_status if task else "",
            "last_message": task.last_message if task else "",
        }
    finally:
        db.close()


def reload_jobs() -> None:
    if not _scheduler_is_leader:
        return
    settings = get_settings()
    for job in scheduler.get_jobs():
        if job.id.startswith("sync_account:"):
            scheduler.remove_job(job.id)
    db = SessionLocal()
    try:
        sync_settings = db.scalars(select(SyncSetting).where(SyncSetting.enabled == True)).all()
        for index, item in enumerate(sync_settings):
            _schedule_account_once(item.platform, item.account_id, index * settings.order_sync_startup_stagger_seconds)
        for job_id in (
            "purge_api_request_logs",
            "status_sync_all",
            "oauth_token_maintenance",
            "scheduled_task_due_retries",
            POST_PRINT_MONITOR_JOB_ID,
            TRAFFIC_ANALYTICS_SYNC_JOB_ID,
            TRAFFIC_ANALYTICS_RETRY_JOB_ID,
            PLATFORM_PRODUCT_CATALOG_SYNC_JOB_ID,
            PLATFORM_PRODUCT_CATALOG_INCREMENTAL_SYNC_JOB_ID,
        ):
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
        for job in scheduler.get_jobs():
            if job.id.startswith("exchange_rate_sync_from_provider:"):
                scheduler.remove_job(job.id)
        for job in scheduler.get_jobs():
            if job.id.startswith("scheduled_task:"):
                scheduler.remove_job(job.id)
        tasks = db.scalars(select(ScheduledTask).where(ScheduledTask.enabled == True).order_by(ScheduledTask.id)).all()
        for item in tasks:
            if item.task_type == TASK_TYPE_AUTO_ORDER_PIPELINE and _task_schedule_mode(item) == "interval":
                _schedule_custom_task_once(item.id, max(10, _task_poll_interval_seconds(item)))
            else:
                scheduler.add_job(
                    _run_custom_task,
                    cron_trigger_from_expr(item.cron_expr),
                    args=[item.id],
                    id=_scheduled_task_job_id(item.id),
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
    finally:
        db.close()

    scheduler.add_job(
        lambda: purge_old_logs(30),
        "cron",
        hour=0,
        minute=30,
        id="purge_api_request_logs",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_scheduler_heartbeat,
        "interval",
        seconds=max(1, settings.scheduler_heartbeat_interval_seconds),
        id="scheduler_heartbeat",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_sync_watchdog,
        "interval",
        seconds=max(1, settings.scheduler_watchdog_interval_seconds),
        id="sync_watchdog",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_oauth_token_maintenance,
        "interval",
        seconds=max(1, settings.oauth_token_maintenance_interval_seconds),
        id="oauth_token_maintenance",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_due_task_retries,
        "interval",
        seconds=max(1, settings.scheduled_task_retry_scan_interval_seconds),
        id="scheduled_task_due_retries",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_post_print_monitors,
        "interval",
        seconds=POST_PRINT_MONITOR_INTERVAL_SECONDS,
        id=POST_PRINT_MONITOR_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_traffic_analytics_sync,
        "cron",
        hour=6,
        minute=0,
        id=TRAFFIC_ANALYTICS_SYNC_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_traffic_analytics_retry,
        "cron",
        hour="7-11",
        minute=30,
        id=TRAFFIC_ANALYTICS_RETRY_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_platform_product_catalog_sync,
        "cron",
        hour=4,
        minute=0,
        args=[CATALOG_SYNC_MODE_FULL],
        id=PLATFORM_PRODUCT_CATALOG_SYNC_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_platform_product_catalog_sync,
        "cron",
        minute=30,
        args=[CATALOG_SYNC_MODE_INCREMENTAL],
        id=PLATFORM_PRODUCT_CATALOG_INCREMENTAL_SYNC_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    for index, cron_expr in enumerate(settings.exchange_rate_sync_cron_exprs):
        scheduler.add_job(
            _run_exchange_rate_sync,
            cron_trigger_from_expr(cron_expr),
            id=f"exchange_rate_sync_from_provider:{index}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )


def _recent_cron_fire_times(cron_expr: str, *, now: datetime, lookback: timedelta) -> list[datetime]:
    trigger = cron_trigger_from_expr(cron_expr)
    window_start = now - lookback
    fire_times: list[datetime] = []
    fire_time = trigger.get_next_fire_time(None, window_start)
    while fire_time is not None and fire_time <= now:
        if fire_time >= window_start:
            fire_times.append(fire_time)
        fire_time = trigger.get_next_fire_time(fire_time, fire_time)
    return fire_times


def _scheduled_task_has_run_since(db, task_id: int, scheduled_at: datetime, now: datetime) -> bool:
    scheduled_at_utc = scheduled_at.astimezone(timezone.utc).replace(tzinfo=None)
    now_utc = now.astimezone(timezone.utc).replace(tzinfo=None)
    row = db.scalar(
        select(ScheduledTaskRun.id)
        .where(
            ScheduledTaskRun.scheduled_task_id == task_id,
            ScheduledTaskRun.created_at >= scheduled_at_utc,
            ScheduledTaskRun.created_at <= now_utc,
        )
        .limit(1)
    )
    return row is not None


def _schedule_recent_missed_cron_tasks(*, now: datetime | None = None) -> int:
    if not _scheduler_is_leader or not scheduler.running:
        return 0

    current = now or datetime.now(scheduler.timezone)
    lookback = timedelta(minutes=SCHEDULED_TASK_CATCHUP_LOOKBACK_MINUTES)
    scheduled_count = 0
    db = SessionLocal()
    try:
        tasks = db.scalars(select(ScheduledTask).where(ScheduledTask.enabled == True).order_by(ScheduledTask.id)).all()
        for task in tasks:
            if _task_schedule_mode(task) != "cron":
                continue
            for fire_time in _recent_cron_fire_times(task.cron_expr, now=current, lookback=lookback):
                if _scheduled_task_has_run_since(db, task.id, fire_time, current):
                    continue
                job_id = f"scheduled_task_catchup:{task.id}:{fire_time.strftime('%Y%m%d%H%M%S')}"
                scheduler.add_job(
                    _run_catchup_task,
                    "date",
                    run_date=current + timedelta(seconds=1),
                    args=[task.id],
                    id=job_id,
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
                audit_sync_event(
                    db,
                    "scheduled_task_catchup_scheduled",
                    job_type="scheduler",
                    status="scheduled",
                    message=f"scheduled catch-up for task {task.id} at {fire_time.isoformat()}",
                    owner_id=runtime_owner_id(),
                    extra={"task_id": task.id, "scheduled_at": fire_time.isoformat()},
                )
                scheduled_count += 1
        db.commit()
    finally:
        db.close()
    return scheduled_count


def _schedule_leader_election_job() -> None:
    settings = get_settings()
    scheduler.add_job(
        _run_scheduler_leader_election,
        "interval",
        seconds=max(1, min(10, settings.scheduler_heartbeat_interval_seconds)),
        id=SCHEDULER_LEADER_ELECTION_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def _start_scheduler_loop() -> None:
    _schedule_leader_election_job()
    if not scheduler.running:
        scheduler.start()


def start_scheduler() -> None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled by configuration")
        return
    _start_scheduler_loop()
    _try_become_scheduler_leader(event_type="scheduler_startup", audit_standby=True)


def stop_scheduler() -> None:
    global _scheduler_is_leader
    if scheduler.running:
        scheduler.shutdown(wait=False)
    db = SessionLocal()
    try:
        if _scheduler_is_leader:
            audit_sync_event(
                db,
                "scheduler_shutdown",
                job_type="scheduler",
                status="stopped",
                message="scheduler shutdown",
                owner_id=runtime_owner_id(),
            )
        write_scheduler_heartbeat(db, is_leader=False, message="stopped")
        db.commit()
        release_scheduler_leader(db)
    finally:
        _scheduler_is_leader = False
        db.close()
