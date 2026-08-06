from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...dashboard_settings import canonical_dashboard_platform, seed_default_dashboard_platform_settings
from ...database import get_db
from ...deadline_settings import (
    BASE_DATE_PAYMENT_AT,
    backfill_order_dispatch_deadlines,
    canonical_deadline_platform,
    seed_default_shipping_deadline_settings,
)
from ...models import DashboardPlatformSetting, LocalUser, ShippingDeadlineSetting
from ...schemas import (
    DashboardAnalyticsResponse,
    DashboardOverviewResponse,
    DashboardRiskResponse,
    DashboardSalesResponse,
    DashboardSettingsResponse,
    DashboardSettingsUpdateRequest,
    DashboardSettingsUpdateResponse,
    DashboardSkuResponse,
    OperationsDailyReportResponse,
)


@dataclass(frozen=True)
class DashboardRouteServices:
    platform_setting_items: Callable[..., Any]
    is_admin_user: Callable[..., bool]
    shop_scope: Callable[..., Any]
    context: Callable[..., Any]
    text_datetime: Callable[..., str | None]
    int_value: Callable[..., int]
    text_date: Callable[..., str | None]
    mtd_comparison: Callable[..., Any]
    last_order_date: Callable[..., date]
    period: Callable[..., Any]
    comparison_period: Callable[..., Any]
    monthly_sales: Callable[..., Any]
    daily_sales: Callable[..., Any]
    shop_sales: Callable[..., Any]
    risk_buckets: Callable[..., Any]
    risk_shops: Callable[..., Any]
    operations_daily_report: Callable[..., Any]
    risk_skus: Callable[..., Any]
    hot_skus: Callable[..., Any]
    local_now: Callable[[], datetime]


def create_dashboard_router(
    *,
    current_user_dependency: Callable[..., Any],
    require_admin_dependency: Callable[..., Any],
    services: DashboardRouteServices,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

    @router.get("/settings", response_model=DashboardSettingsResponse)
    def dashboard_settings(
        user: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> DashboardSettingsResponse:
        items = services.platform_setting_items(db)
        db.commit()
        return DashboardSettingsResponse(items=items, can_manage=services.is_admin_user(user, db))

    @router.put("/settings", response_model=DashboardSettingsUpdateResponse)
    def update_dashboard_settings(
        payload: DashboardSettingsUpdateRequest,
        _: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> DashboardSettingsUpdateResponse:
        seed_default_dashboard_platform_settings(db)
        seed_default_shipping_deadline_settings(db)
        db.flush()
        receipt_rows = {
            row.platform: row
            for row in db.scalars(select(DashboardPlatformSetting)).all()
        }
        deadline_rows = {
            row.platform: row
            for row in db.scalars(select(ShippingDeadlineSetting)).all()
        }
        now = datetime.utcnow()
        seen: set[str] = set()
        for index, item in enumerate(payload.items):
            platform = canonical_dashboard_platform(item.platform)
            if not platform or platform in seen:
                raise HTTPException(status_code=400, detail="平台不能为空或重复")
            seen.add(platform)

            receipt_row = receipt_rows.get(platform)
            if not receipt_row:
                receipt_row = DashboardPlatformSetting(platform=platform, created_at=now)
                db.add(receipt_row)
                receipt_rows[platform] = receipt_row
            receipt_row.receipt_rate = Decimal(str(item.receipt_rate_pct)) / Decimal("100")
            receipt_row.updated_at = now

            deadline_platform = canonical_deadline_platform(platform)
            deadline_row = deadline_rows.get(deadline_platform)
            if not deadline_row:
                deadline_row = ShippingDeadlineSetting(platform=deadline_platform, created_at=now)
                db.add(deadline_row)
                deadline_rows[deadline_platform] = deadline_row
            deadline_row.base_date_field = BASE_DATE_PAYMENT_AT
            deadline_row.offset_days = int(item.fulfillment_days)
            deadline_row.sort_order = index
            deadline_row.enabled = True
            deadline_row.updated_at = now

        backfilled = backfill_order_dispatch_deadlines(db)
        db.commit()
        return DashboardSettingsUpdateResponse(
            items=services.platform_setting_items(db),
            can_manage=True,
            backfilled=backfilled,
        )

    @router.get("/overview", response_model=DashboardOverviewResponse)
    def dashboard_overview(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        compare_from: date | None = Query(None),
        compare_to: date | None = Query(None),
        shop_ids: list[int] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> DashboardOverviewResponse:
        scope = services.shop_scope(db, shop_ids)
        summary, start_day, end_day, previous_start, previous_end = services.context(
            db, date_from, date_to, compare_from, compare_to, scope
        )
        return DashboardOverviewResponse(
            generated_at=services.text_datetime(services.local_now()) or "",
            total_orders=services.int_value(summary.total_orders),
            first_order_date=services.text_date(summary.first_order_date),
            last_order_date=services.text_date(summary.last_order_date),
            blank_currency_orders=services.int_value(summary.blank_currency_orders),
            mtd_comparison=services.mtd_comparison(
                db, start_day, end_day, previous_start, previous_end, scope
            ),
        )

    @router.get("/sales", response_model=DashboardSalesResponse)
    def dashboard_sales(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        compare_from: date | None = Query(None),
        compare_to: date | None = Query(None),
        shop_ids: list[int] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> DashboardSalesResponse:
        scope = services.shop_scope(db, shop_ids)
        fallback_end = services.last_order_date(db, scope)
        start_day, end_day, comparison_start, comparison_end = services.period(
            fallback_end, date_from, date_to
        )
        comparison_start, comparison_end = services.comparison_period(
            start_day,
            end_day,
            comparison_start,
            comparison_end,
            compare_from,
            compare_to,
        )
        return DashboardSalesResponse(
            monthly_sales=services.monthly_sales(db, start_day, end_day, scope),
            daily_sales=services.daily_sales(db, start_day, end_day, scope),
            comparison_daily_sales=services.daily_sales(
                db, comparison_start, comparison_end, scope
            ),
            shop_sales=services.shop_sales(db, start_day, end_day, scope),
            current_label=f"{start_day.isoformat()}~{end_day.isoformat()}",
            comparison_label=f"{comparison_start.isoformat()}~{comparison_end.isoformat()}",
        )

    @router.get("/risk", response_model=DashboardRiskResponse)
    def dashboard_risk(
        shop_ids: list[int] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> DashboardRiskResponse:
        scope = services.shop_scope(db, shop_ids)
        return DashboardRiskResponse(
            risk_buckets=services.risk_buckets(db, scope),
            risk_shops=services.risk_shops(db, scope),
        )

    @router.get("/operations", response_model=OperationsDailyReportResponse)
    def dashboard_operations(
        days: int = Query(7, ge=7, le=7),
        report_date: date | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> OperationsDailyReportResponse:
        return services.operations_daily_report(db, days=days, report_date=report_date)

    @router.get("/skus", response_model=DashboardSkuResponse)
    def dashboard_skus(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        compare_from: date | None = Query(None),
        compare_to: date | None = Query(None),
        shop_ids: list[int] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> DashboardSkuResponse:
        scope = services.shop_scope(db, shop_ids)
        fallback_end = services.last_order_date(db, scope)
        start_day, end_day, previous_start, previous_end = services.period(
            fallback_end, date_from, date_to
        )
        previous_start, previous_end = services.comparison_period(
            start_day,
            end_day,
            previous_start,
            previous_end,
            compare_from,
            compare_to,
        )
        return DashboardSkuResponse(
            risk_skus=services.risk_skus(db, scope),
            hot_skus=services.hot_skus(
                db, start_day, end_day, previous_start, previous_end, scope
            ),
            current_label=f"{start_day.isoformat()}~{end_day.isoformat()}",
            previous_label=f"{previous_start.isoformat()}~{previous_end.isoformat()}",
        )

    @router.get("/analytics", response_model=DashboardAnalyticsResponse)
    def dashboard_analytics(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        compare_from: date | None = Query(None),
        compare_to: date | None = Query(None),
        shop_ids: list[int] | None = Query(None),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> DashboardAnalyticsResponse:
        scope = services.shop_scope(db, shop_ids)
        summary, start_day, end_day, previous_start, previous_end = services.context(
            db, date_from, date_to, compare_from, compare_to, scope
        )
        return DashboardAnalyticsResponse(
            generated_at=services.text_datetime(services.local_now()) or "",
            total_orders=services.int_value(summary.total_orders),
            first_order_date=services.text_date(summary.first_order_date),
            last_order_date=services.text_date(summary.last_order_date),
            blank_currency_orders=services.int_value(summary.blank_currency_orders),
            monthly_sales=services.monthly_sales(db, start_day, end_day, scope),
            daily_sales=services.daily_sales(db, start_day, end_day, scope),
            comparison_daily_sales=services.daily_sales(
                db, previous_start, previous_end, scope
            ),
            shop_sales=services.shop_sales(db, start_day, end_day, scope),
            current_label=f"{start_day.isoformat()}~{end_day.isoformat()}",
            comparison_label=f"{previous_start.isoformat()}~{previous_end.isoformat()}",
            mtd_comparison=services.mtd_comparison(
                db, start_day, end_day, previous_start, previous_end, scope
            ),
            risk_buckets=services.risk_buckets(db, scope),
            risk_shops=services.risk_shops(db, scope),
            risk_skus=services.risk_skus(db, scope),
            hot_skus=services.hot_skus(
                db, start_day, end_day, previous_start, previous_end, scope
            ),
        )

    return router
