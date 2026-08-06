# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import LocalUser
from ...traffic_analytics import (
    TrafficSyncRequest,
    create_traffic_sync_runs,
    list_traffic_accounts,
    query_categories,
    query_category_sku_comparison,
    query_category_sku_focus_analysis,
    query_comparison,
    query_negative_reviews_daily,
    query_rankings,
    query_summary,
    run_traffic_sync_runs,
    validate_period,
)


def create_traffic_analytics_router(
    *,
    current_user_dependency: Callable[..., Any],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/traffic-analytics", tags=["traffic-analytics"])

    @router.get("/accounts")
    def traffic_analytics_accounts(
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        return {"items": list_traffic_accounts(db)}

    @router.post("/sync")
    def sync_traffic_analytics(
        payload: TrafficSyncRequest,
        background_tasks: BackgroundTasks,
        user: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            runs, pending_ids = create_traffic_sync_runs(db, payload, user.username)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if pending_ids:
            background_tasks.add_task(run_traffic_sync_runs, pending_ids)
        return {"items": runs}

    @router.get("/summary")
    def traffic_analytics_summary(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        platform: list[str] | None = Query(None),
        platform_account_id: list[int] | None = Query(None),
        source: str = Query(""),
        region: list[str] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            start, end = validate_period(date_from, date_to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return query_summary(
            db,
            start,
            end,
            platform=platform or [],
            platform_account_id=platform_account_id,
            source=source.strip().lower(),
            region=region or [],
        )

    @router.get("/negative-reviews")
    def traffic_analytics_negative_reviews(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        platform: list[str] | None = Query(None),
        platform_account_id: list[int] | None = Query(None),
        source: str = Query(""),
        region: list[str] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            start, end = validate_period(date_from, date_to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return query_negative_reviews_daily(
            db,
            start,
            end,
            platform=platform or [],
            platform_account_id=platform_account_id,
            source=source.strip().lower(),
            region=region or [],
        )

    @router.get("/rankings")
    def traffic_analytics_rankings(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        metric: str = Query("impressions"),
        sort_order: str = Query("desc"),
        limit: int = Query(20, ge=1, le=100),
        platform: list[str] | None = Query(None),
        platform_account_id: list[int] | None = Query(None),
        source: str = Query(""),
        region: list[str] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            start, end = validate_period(date_from, date_to)
            return query_rankings(
                db,
                start,
                end,
                metric=metric,
                sort_order=sort_order,
                limit=limit,
                platform=platform or [],
                platform_account_id=platform_account_id,
                source=source.strip().lower(),
                region=region or [],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/categories")
    def traffic_analytics_categories(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        platform: list[str] | None = Query(None),
        platform_account_id: list[int] | None = Query(None),
        source: str = Query(""),
        region: list[str] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            start, end = validate_period(date_from, date_to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return query_categories(
            db,
            start,
            end,
            platform=platform or [],
            platform_account_id=platform_account_id,
            source=source.strip().lower(),
            region=region or [],
        )

    @router.get("/comparison")
    def traffic_analytics_comparison(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        metric: str = Query("clicks"),
        dimension: str = Query("sku"),
        sort_by: str = Query("delta_abs"),
        limit: int = Query(20, ge=1, le=100),
        platform: list[str] | None = Query(None),
        platform_account_id: list[int] | None = Query(None),
        source: str = Query(""),
        region: list[str] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            start, end = validate_period(date_from, date_to)
            return query_comparison(
                db,
                start,
                end,
                metric=metric,
                dimension=dimension,
                sort_by=sort_by,
                limit=limit,
                platform=platform or [],
                platform_account_id=platform_account_id,
                source=source.strip().lower(),
                region=region or [],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/comparison/category-skus")
    def traffic_analytics_category_sku_comparison(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        metric: str = Query("clicks"),
        sort_by: str = Query("delta_abs"),
        limit: int = Query(20, ge=1, le=100),
        platform: str = Query(""),
        platform_account_id: int = Query(0),
        source: str = Query(""),
        grain: str = Query(""),
        region: str = Query(""),
        platform_category_id: str = Query(""),
        keyword: str = Query(""),
        change_direction: str = Query("all"),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            start, end = validate_period(date_from, date_to)
            return query_category_sku_comparison(
                db,
                start,
                end,
                metric=metric,
                sort_by=sort_by,
                limit=limit,
                platform=platform,
                platform_account_id=platform_account_id,
                source=source,
                grain=grain,
                region=region,
                platform_category_id=platform_category_id,
                keyword=keyword,
                change_direction=change_direction,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/analysis/category-skus")
    def traffic_analytics_category_sku_focus_analysis(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        top_n: int = Query(20, ge=1, le=100),
        platform: str = Query(""),
        platform_account_id: int = Query(0),
        source: str = Query(""),
        grain: str = Query(""),
        region: str = Query(""),
        platform_category_id: str = Query(""),
        keyword: str = Query(""),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            start, end = validate_period(date_from, date_to)
            return query_category_sku_focus_analysis(
                db,
                start,
                end,
                top_n=top_n,
                platform=platform,
                platform_account_id=platform_account_id,
                source=source,
                grain=grain,
                region=region,
                platform_category_id=platform_category_id,
                keyword=keyword,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
