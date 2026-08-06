# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import LocalUser, SyncSetting
from ...schemas import SyncSettingDto
from ...sync_runtime import audit_sync_event, sync_health_snapshot


@dataclass(frozen=True)
class SyncSettingsRouteServices:
    canonical_platform: Callable[[str], str]
    platform_lookup_codes: Callable[[str], set[str]]
    reload_jobs: Callable[[], Any]


def create_sync_settings_router(
    *,
    current_user_dependency: Callable[..., Any],
    services: SyncSettingsRouteServices,
) -> APIRouter:
    router = APIRouter(tags=["sync-settings"])

    @router.get("/api/v1/sync-health")
    def get_sync_health(
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        return sync_health_snapshot(db)

    @router.get("/api/sync-settings", response_model=list[SyncSettingDto])
    @router.get("/api/v1/sync-settings", response_model=list[SyncSettingDto])
    def list_sync_settings(
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> list[SyncSettingDto]:
        rows = db.scalars(select(SyncSetting)).all()
        return [
            SyncSettingDto(
                platform=services.canonical_platform(row.platform),
                account_id=row.account_id,
                enabled=row.enabled,
                interval_seconds=row.interval_seconds,
                dry_run_fulfillment=row.dry_run_fulfillment,
            )
            for row in rows
        ]

    @router.put("/api/sync-settings/{platform}/{account_id}", response_model=SyncSettingDto)
    @router.put("/api/v1/sync-settings/{platform}/{account_id}", response_model=SyncSettingDto)
    def update_sync_setting(
        platform: str,
        account_id: str,
        payload: SyncSettingDto,
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> SyncSettingDto:
        platform = services.canonical_platform(platform)
        row = db.scalar(
            select(SyncSetting).where(
                SyncSetting.platform.in_(services.platform_lookup_codes(platform)),
                SyncSetting.account_id == account_id,
            )
        )
        before = {
            "enabled": row.enabled if row else None,
            "interval_seconds": row.interval_seconds if row else None,
            "dry_run_fulfillment": row.dry_run_fulfillment if row else None,
        }
        if not row:
            row = SyncSetting(platform=platform, account_id=account_id)
            db.add(row)
        row.enabled = payload.enabled
        row.interval_seconds = payload.interval_seconds
        row.dry_run_fulfillment = payload.dry_run_fulfillment
        audit_sync_event(
            db,
            "sync_setting_changed",
            platform=platform,
            account_id=account_id,
            job_type="sync_orders",
            status="updated",
            message="sync setting updated",
            extra={
                "before": before,
                "after": {
                    "enabled": payload.enabled,
                    "interval_seconds": payload.interval_seconds,
                    "dry_run_fulfillment": payload.dry_run_fulfillment,
                },
            },
        )
        db.commit()
        services.reload_jobs()
        return payload

    return router
