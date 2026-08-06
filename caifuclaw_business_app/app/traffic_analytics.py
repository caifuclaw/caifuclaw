# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import Float, String, and_, case, cast, desc, exists, func, literal, or_, select, true, union_all
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .connector_client import ConnectorRuntimeError
from .database import SessionLocal
from .models import Order, OrderItem, PlatformAccount, TrafficMetric, TrafficSyncRun
from .product_models import Product, ProductShopMapping
from .sync_engine import _connector_for_account


logger = logging.getLogger(__name__)


SUPPORTED_TRAFFIC_PLATFORMS = {
    "ozon": {
        "label": "Ozon",
        "scope": "自然流量",
        "grain": "日",
        "metrics": ["impressions", "clicks", "add_to_cart", "orders", "buyers", "units_sold", "negative_reviews", "revenue"],
        "note": "搜索曝光、商品页访问、加购、下单和评价；买家数和评价来自平台/本地补充",
    },
    "joom_logistics": {
        "label": "Joom",
        "scope": "平台全量商品流量",
        "grain": "最近7/14/28天",
        "metrics": ["impressions", "clicks", "add_to_cart", "orders", "buyers", "units_sold", "negative_reviews", "revenue"],
        "note": "商品曝光、打开、加购、购买和销量来自 Joom Product Ranking，评价来自平台；买家数和成交额由本地订单补充",
    },
    "mercadolibre": {
        "label": "MercadoLibre",
        "scope": "自然流量",
        "grain": "选定周期 / 地区",
        "metrics": ["clicks", "orders", "buyers", "units_sold", "revenue", "negative_reviews"],
        "note": "按当地商品和站点时区合并访问、订单、买家、销量、成交额与评价",
    },
    "allegro": {
        "label": "Allegro",
        "scope": "自然流量",
        "grain": "滚动30天 + 自然订单日数据",
        "metrics": ["clicks", "orders", "buyers", "units_sold", "negative_reviews", "revenue"],
        "note": "商品访问和评价来自平台滚动30天统计；订单数、买家数、售出件数和成交额由本地订单补充",
    },
    "wildberries": {
        "label": "Wildberries",
        "scope": "自然流量",
        "grain": "选定周期",
        "metrics": ["clicks", "add_to_cart", "orders", "buyers", "units_sold", "negative_reviews", "revenue"],
        "note": "商品卡访问、加购、下单和评价；买家数和销量由本地订单补充",
    },
}

METRIC_FIELDS = (
    "impressions",
    "clicks",
    "add_to_cart",
    "orders",
    "buyers",
    "units_sold",
    "negative_reviews",
    "revenue",
)
TRAFFIC_QUERY_FIELDS = (
    "platform_account_id",
    "platform",
    "account_id",
    "shop_name",
    "source",
    "grain",
    "stat_date",
    "period_start",
    "period_end",
    "region",
    "entity_type",
    "entity_id",
    "sku",
    "product_name",
    *METRIC_FIELDS,
    "currency",
    "raw_data",
    "synced_at",
)
SUMMARY_GROUP_FIELDS = (
    "platform",
    "platform_account_id",
    "account_id",
    "shop_name",
    "source",
    "grain",
    "region",
)
DAILY_NEGATIVE_REVIEW_GROUP_FIELDS = (*SUMMARY_GROUP_FIELDS, "stat_date")
RANKING_GROUP_FIELDS = (
    "platform",
    "platform_account_id",
    "account_id",
    "shop_name",
    "source",
    "grain",
    "region",
    "entity_type",
    "entity_id",
    "sku",
)
COMPARISON_GROUP_FIELDS = (
    "platform",
    "platform_account_id",
    "account_id",
    "shop_name",
    "source",
    "region",
    "entity_type",
    "entity_id",
    "sku",
)
CATEGORY_GROUP_FIELDS = (
    *SUMMARY_GROUP_FIELDS,
    "platform_category_id",
)
CATEGORY_SKU_COMPARISON_GROUP_FIELDS = (
    *SUMMARY_GROUP_FIELDS,
    "entity_type",
    "entity_id",
    "sku",
)
COMPARISON_DIMENSIONS = {"sku", "category"}
COMPARISON_SORTS = {
    "delta_abs",
    "rate_desc",
    "rate_asc",
    "current_desc",
    "current_asc",
    "previous_desc",
    "previous_asc",
    "delta_desc",
    "delta_asc",
}
COMPARISON_CHANGE_DIRECTIONS = {"all", "up", "down", "flat"}
RANKING_METRICS = {"impressions", "clicks", "add_to_cart", "orders", "ctr", "cvr"}
RANKING_SORT_ORDERS = {"asc", "desc"}
CANCELLED_MARKERS = ("cancel", "void", "closed_by_buyer", "closed_by_seller")
MAX_DATE_RANGE_FALLBACK_LAG_DAYS = 7
MAX_SCHEDULED_TRAFFIC_ATTEMPTS_PER_PERIOD = 4
MERCADO_CBT_REGIONS = {"CBT", "CBT_MERCADOLIBRE", "GLOBAL", "GLOBAL_SELLING"}
MERCADO_COUNTRY_REGIONS = {
    "AR": "MLA",
    "BR": "MLB",
    "CL": "MLC",
    "CO": "MCO",
    "EC": "MEC",
    "MX": "MLM",
    "PE": "MPE",
    "UY": "MLU",
}
MERCADO_REGION_TIMEZONES = {
    "MLA": "America/Argentina/Buenos_Aires",
    "MLB": "America/Sao_Paulo",
    "MLC": "America/Santiago",
    "MCO": "America/Bogota",
    "MEC": "America/Guayaquil",
    "MLM": "America/Mexico_City",
    "MPE": "America/Lima",
    "MLU": "America/Montevideo",
}


class TrafficSyncRequest(BaseModel):
    platform_account_ids: list[int] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None


def default_period() -> tuple[date, date]:
    period_end = date.today() - timedelta(days=1)
    return period_end - timedelta(days=6), period_end


def validate_period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    default_from, default_to = default_period()
    start = date_from or default_from
    end = date_to or default_to
    if end >= date.today():
        raise ValueError("流量分析只能选择已结束的完整日期")
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    return start, end


def validate_sync_period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    start, end = validate_period(date_from, date_to)
    if (end - start).days > 30:
        raise ValueError("单次流量同步最多支持31天")
    return start, end


def previous_period(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=days - 1), previous_end


def _utc_iso(value: datetime | None) -> str | None:
    if not value:
        return None
    suffix = "Z" if value.tzinfo is None else ""
    return f"{value.isoformat()}{suffix}"


def _run_dto(row: TrafficSyncRun | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.id,
        "platform_account_id": row.platform_account_id,
        "platform": row.platform,
        "account_id": row.account_id,
        "shop_name": row.shop_name,
        "status": row.status,
        "date_from": row.date_from.isoformat(),
        "date_to": row.date_to.isoformat(),
        "rows_written": row.rows_written,
        "error_message": row.error_message or "",
        "triggered_by": row.triggered_by or "",
        "started_at": _utc_iso(row.started_at),
        "finished_at": _utc_iso(row.finished_at),
        "created_at": _utc_iso(row.created_at),
    }


def list_traffic_accounts(db: Session) -> list[dict]:
    accounts = db.scalars(
        select(PlatformAccount)
        .where(PlatformAccount.platform.in_(SUPPORTED_TRAFFIC_PLATFORMS))
        .order_by(PlatformAccount.platform, PlatformAccount.display_name, PlatformAccount.id)
    ).all()
    result: list[dict] = []
    for account in accounts:
        latest_run = db.scalar(
            select(TrafficSyncRun)
            .where(TrafficSyncRun.platform_account_id == account.id)
            .order_by(desc(TrafficSyncRun.id))
            .limit(1)
        )
        latest_metric = db.execute(
            select(TrafficMetric.period_start, TrafficMetric.period_end, TrafficMetric.synced_at)
            .where(TrafficMetric.platform_account_id == account.id)
            .order_by(desc(TrafficMetric.period_end), desc(TrafficMetric.synced_at))
            .limit(1)
        ).first()
        latest_period_start = latest_metric[0] if latest_metric else None
        latest_period_end = latest_metric[1] if latest_metric else None
        latest_metric_at = latest_metric[2] if latest_metric else None
        expected_period_end = date.today() - timedelta(days=1)
        if not latest_period_end:
            data_freshness = "missing"
        elif latest_period_end < expected_period_end:
            data_freshness = "stale"
        else:
            data_freshness = "fresh"
        result.append(
            {
                "id": account.id,
                "platform": account.platform,
                "account_id": account.account_id,
                "display_name": account.display_name or account.account_id,
                "enabled": bool(account.enabled),
                "authorization_status": account.authorization_status or "",
                "capability": SUPPORTED_TRAFFIC_PLATFORMS[account.platform],
                "latest_run": _run_dto(latest_run),
                "latest_metric_at": _utc_iso(latest_metric_at),
                "latest_period_start": latest_period_start.isoformat() if latest_period_start else None,
                "latest_period_end": latest_period_end.isoformat() if latest_period_end else None,
                "data_freshness": data_freshness,
            }
        )
    return result


def mark_interrupted_traffic_runs(db: Session) -> int:
    rows = db.scalars(
        select(TrafficSyncRun).where(TrafficSyncRun.status.in_(("pending", "running")))
    ).all()
    now = datetime.utcnow()
    for row in rows:
        row.status = "failed"
        row.error_message = "服务重启，同步任务已中断，请重新同步"
        row.finished_at = now
    return len(rows)


def create_traffic_sync_runs(
    db: Session,
    request: TrafficSyncRequest,
    triggered_by: str,
    *,
    skip_successful_period: bool = False,
    scheduled_attempt_limit: int | None = None,
) -> tuple[list[dict], list[int]]:
    period_start, period_end = validate_sync_period(request.date_from, request.date_to)
    stmt = select(PlatformAccount).where(
        PlatformAccount.platform.in_(SUPPORTED_TRAFFIC_PLATFORMS),
        PlatformAccount.enabled.is_(True),
        PlatformAccount.encrypted_credentials.is_not(None),
    )
    if request.platform_account_ids:
        stmt = stmt.where(PlatformAccount.id.in_(request.platform_account_ids))
    accounts = db.scalars(stmt.order_by(PlatformAccount.id)).all()
    if not accounts:
        raise ValueError("未找到可同步的流量分析店铺")

    runs: list[TrafficSyncRun] = []
    created_ids: list[int] = []
    for account in accounts:
        active = db.scalar(
            select(TrafficSyncRun)
            .where(
                TrafficSyncRun.platform_account_id == account.id,
                TrafficSyncRun.status.in_(("pending", "running")),
            )
            .order_by(desc(TrafficSyncRun.id))
            .limit(1)
        )
        if active:
            runs.append(active)
            continue
        if skip_successful_period:
            latest_period_run = db.scalar(
                select(TrafficSyncRun)
                .where(
                    TrafficSyncRun.platform_account_id == account.id,
                    TrafficSyncRun.date_from == period_start,
                    TrafficSyncRun.date_to == period_end,
                )
                .order_by(desc(TrafficSyncRun.id))
                .limit(1)
            )
            if latest_period_run and latest_period_run.status == "success":
                runs.append(latest_period_run)
                continue
        if scheduled_attempt_limit is not None:
            attempt_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(TrafficSyncRun)
                    .where(
                        TrafficSyncRun.platform_account_id == account.id,
                        TrafficSyncRun.date_from == period_start,
                        TrafficSyncRun.date_to == period_end,
                        TrafficSyncRun.triggered_by.like("scheduler:%"),
                    )
                )
                or 0
            )
            if attempt_count >= max(1, scheduled_attempt_limit):
                logger.error(
                    "Traffic sync retry limit reached: platform=%s account=%s period=%s..%s attempts=%s",
                    account.platform,
                    account.account_id,
                    period_start,
                    period_end,
                    attempt_count,
                )
                continue
        row = TrafficSyncRun(
            platform_account_id=account.id,
            platform=account.platform,
            account_id=account.account_id,
            shop_name=account.display_name or account.account_id,
            status="pending",
            date_from=period_start,
            date_to=period_end,
            triggered_by=triggered_by,
        )
        db.add(row)
        db.flush()
        runs.append(row)
        created_ids.append(row.id)
    db.commit()
    return [_run_dto(row) for row in runs if row], created_ids


def _date_time(value: date, *, end: bool = False) -> datetime:
    return datetime.combine(value, time.max if end else time.min)


def _order_is_cancelled(order: Order) -> bool:
    if str(order.biz_status or "").strip() == "已作废":
        return True
    status = str(order.platform_status or "").strip().lower()
    return any(marker in status for marker in CANCELLED_MARKERS)


def _normalize_region(value) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or value.get("site_id") or value.get("site") or "").strip().upper()
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("{"):
        try:
            parsed = json.loads(text.replace("'", '"'))
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return _normalize_region(parsed)
        matched = re.search(r"[\"']?(?:id|site_id|site)[\"']?\s*:\s*[\"']([^\"']+)", text, re.I)
        if matched:
            return matched.group(1).strip().upper()
    return text.upper()


def _local_order_product_id(item: OrderItem) -> str:
    payload = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    nested_payload = payload.get("raw_payload") if isinstance(payload.get("raw_payload"), dict) else {}
    candidates = (
        payload.get("product_id"),
        payload.get("productId"),
        nested_payload.get("id"),
        nested_payload.get("product_id"),
        nested_payload.get("productId"),
    )
    return next((str(value).strip() for value in candidates if str(value or "").strip()), "")


def _local_order_offer_id(item: OrderItem) -> str:
    payload = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    nested_payload = payload.get("raw_payload") if isinstance(payload.get("raw_payload"), dict) else {}
    offer = nested_payload.get("offer") if isinstance(nested_payload.get("offer"), dict) else {}
    candidates = (
        payload.get("offer_id"),
        payload.get("offerId"),
        nested_payload.get("offer_id"),
        nested_payload.get("offerId"),
        offer.get("id"),
    )
    return next((str(value).strip() for value in candidates if str(value or "").strip()), "")


def _local_order_match_key(account: PlatformAccount, item: OrderItem) -> str:
    if account.platform == "joom_logistics":
        product_id = _local_order_product_id(item)
        if product_id:
            return product_id.casefold()
    if account.platform == "allegro":
        offer_id = _local_order_offer_id(item)
        if offer_id:
            return offer_id.casefold()
    return str(item.sku or "").strip().casefold()


def _local_order_stat_key(account: PlatformAccount, order: Order) -> str:
    if account.platform == "joom_logistics":
        payload = order.raw_payload if isinstance(order.raw_payload, dict) else {}
        transaction_id = str(payload.get("transactionId") or payload.get("transaction_id") or "").strip()
        if transaction_id:
            return f"transaction:{transaction_id}"
    return str(order.platform_order_id or order.id)


def _local_order_groups(
    db: Session,
    account: PlatformAccount,
    start: date,
    end: date,
) -> dict[tuple[date, str, str], dict]:
    rows = db.execute(
        select(Order, OrderItem)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(
            Order.platform == account.platform,
            Order.account_id == account.account_id,
            or_(
                and_(Order.payment_at >= _date_time(start), Order.payment_at <= _date_time(end, end=True)),
                and_(
                    Order.payment_at.is_(None),
                    Order.platform_created_at >= _date_time(start),
                    Order.platform_created_at <= _date_time(end, end=True),
                ),
            ),
        )
    ).all()
    grouped: dict[tuple[date, str, str], dict] = {}
    for order, item in rows:
        if _order_is_cancelled(order):
            continue
        occurred_at = order.payment_at or order.platform_created_at
        if not occurred_at:
            continue
        sku = str(item.sku or "").strip()
        match_key = _local_order_match_key(account, item)
        if not match_key:
            continue
        region = _normalize_region(order.site or order.country_code)
        key = (occurred_at.date(), region, match_key)
        value = grouped.setdefault(
            key,
            {
                "orders": 0,
                "order_ids": set(),
                "buyer_ids": set(),
                "units_sold": 0,
                "sku": sku,
                "product_name": item.platform_product_name or "",
                "revenue": Decimal("0"),
                "has_revenue": False,
                "currencies": set(),
            },
        )
        order_id = _local_order_stat_key(account, order)
        buyer_id = str(order.buyer_id or "").strip() or f"order:{order_id}"
        quantity = int(item.quantity or 1)
        value["order_ids"].add(order_id)
        value["orders"] = len(value["order_ids"])
        value["buyer_ids"].add(buyer_id)
        value["units_sold"] += quantity
        unit_price = _decimal_or_none(item.unit_price)
        if unit_price is not None:
            value["revenue"] += unit_price * quantity
            value["has_revenue"] = True
        currency = str(item.currency or order.currency or "").strip().upper()
        if currency:
            value["currencies"].add(currency)
        if not value["product_name"] and item.platform_product_name:
            value["product_name"] = item.platform_product_name
    return grouped


def _local_daily_order_rows(
    db: Session,
    account: PlatformAccount,
    start: date,
    end: date,
) -> list[dict]:
    rows: list[dict] = []
    for (day, region, _sku_key), values in _local_order_groups(db, account, start, end).items():
        sku = values["sku"]
        currencies = sorted(values["currencies"])
        rows.append(
            {
                "source": "organic",
                "grain": "daily",
                "stat_date": day.isoformat(),
                "period_start": day.isoformat(),
                "period_end": day.isoformat(),
                "region": region,
                "entity_type": "sku",
                "entity_id": f"local-order:{sku}",
                "sku": sku,
                "product_name": values["product_name"],
                "impressions": None,
                "clicks": None,
                "add_to_cart": None,
                "orders": len(values["order_ids"]),
                "buyers": len(values["buyer_ids"]),
                "units_sold": values["units_sold"],
                "negative_reviews": None,
                "revenue": values["revenue"] if values["has_revenue"] else None,
                "currency": currencies[0] if len(currencies) == 1 else "MIXED" if currencies else "",
                "raw_data": {
                    "metric_source": "local_orders",
                    "revenue_source": "local_orders" if values["has_revenue"] else "unavailable",
                },
            }
        )
    return rows


def _merge_local_order_metrics(
    db: Session,
    account: PlatformAccount,
    traffic_rows: list[dict],
    start: date,
    end: date,
) -> list[dict]:
    row_periods: list[tuple[dict, str, str, date, date]] = []
    for row in traffic_rows:
        if str(row.get("entity_type") or "sku") != "sku":
            continue
        if account.platform in {"joom_logistics", "allegro"}:
            match_key = str(row.get("entity_id") or row.get("sku") or "").strip().casefold()
        else:
            match_key = str(row.get("sku") or "").strip().casefold()
        if not match_key:
            continue
        try:
            period_start = date.fromisoformat(str(row.get("period_start") or "")[:10])
            period_end = date.fromisoformat(str(row.get("period_end") or "")[:10])
        except ValueError:
            continue
        region_key = _normalize_region(row.get("region")) if account.platform == "allegro" else ""
        row_periods.append((row, region_key, match_key, period_start, period_end))

    query_start = min((period_start for _, _, _, period_start, _ in row_periods), default=start)
    query_end = max((period_end for _, _, _, _, period_end in row_periods), default=end)
    daily_by_dimension: dict[tuple[str, str], list[tuple[date, dict]]] = defaultdict(list)
    for (day, region_key, match_key), values in _local_order_groups(db, account, query_start, query_end).items():
        merge_region = region_key if account.platform == "allegro" else ""
        daily_by_dimension[(merge_region, match_key)].append((day, values))

    period_cache: dict[tuple[date, date, str, str], tuple[int, int, int, Decimal, bool, set[str]]] = {}
    period_currency_cache: dict[tuple[date, date], set[str]] = {}
    for row, region_key, match_key, period_start, period_end in row_periods:
        cache_key = (period_start, period_end, region_key, match_key)
        metrics = period_cache.get(cache_key)
        if metrics is None:
            order_ids: set[str] = set()
            buyer_ids: set[str] = set()
            units_sold = 0
            revenue = Decimal("0")
            has_revenue = False
            currencies: set[str] = set()
            for day, values in daily_by_dimension.get((region_key, match_key), []):
                if period_start <= day <= period_end:
                    order_ids.update(values.get("order_ids") or set())
                    buyer_ids.update(values["buyer_ids"])
                    units_sold += int(values["units_sold"] or 0)
                    revenue += values.get("revenue") or Decimal("0")
                    has_revenue = has_revenue or bool(values.get("has_revenue"))
                    currencies.update(values.get("currencies") or set())
            metrics = (len(order_ids), len(buyer_ids), units_sold, revenue, has_revenue, currencies)
            period_cache[cache_key] = metrics

        local_orders, buyers, local_units_sold, local_revenue, has_local_revenue, currencies = metrics
        row["buyers"] = buyers
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        units_source = str(raw_data.get("units_sold_source") or "")
        orders_source = str(raw_data.get("orders_source") or "")
        if account.platform == "allegro" and local_orders:
            row["orders"] = local_orders
            row["units_sold"] = local_units_sold
            orders_source = "local_orders"
            units_source = "local_orders"
        elif row.get("units_sold") is None:
            if account.platform in {"ozon", "allegro"} and row.get("orders") is not None:
                row["units_sold"] = int(row.get("orders") or 0)
                units_source = "platform"
            else:
                row["units_sold"] = local_units_sold
                units_source = "local_orders"
        if not units_source:
            units_source = "platform"
        if not orders_source:
            orders_source = "platform"
        revenue_source = str(raw_data.get("revenue_source") or "")
        if row.get("revenue") is None:
            if has_local_revenue:
                row["revenue"] = local_revenue
                revenue_source = "local_orders"
            elif int(row.get("orders") or 0) == 0:
                row["revenue"] = Decimal("0")
                revenue_source = "no_sales"
            else:
                revenue_source = "unavailable"
        elif not revenue_source:
            revenue_source = "platform"
        if not row.get("currency"):
            row_currencies = currencies
            if not row_currencies and row.get("revenue") == 0:
                period_key = (period_start, period_end)
                if period_key not in period_currency_cache:
                    period_currency_cache[period_key] = {
                        currency
                        for daily_rows in daily_by_dimension.values()
                        for day, values in daily_rows
                        if period_start <= day <= period_end
                        for currency in values.get("currencies") or set()
                    }
                row_currencies = period_currency_cache[period_key]
            if len(row_currencies) == 1:
                row["currency"] = next(iter(row_currencies))
            elif len(row_currencies) > 1:
                row["currency"] = "MIXED"
        row["raw_data"] = {
            **raw_data,
            "orders_source": orders_source,
            "buyers_source": "local_orders",
            "units_sold_source": units_source,
            "revenue_source": revenue_source,
        }
    for row in traffic_rows:
        if str(row.get("entity_type") or "sku") == "sku" and str(row.get("sku") or "").strip():
            continue
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        if row.get("buyers") is None:
            row["buyers"] = 0
        if row.get("units_sold") is None:
            row["units_sold"] = 0
        row["raw_data"] = {
            **raw_data,
            "orders_source": raw_data.get("orders_source") or "not_applicable",
            "buyers_source": "not_applicable",
            "units_sold_source": "not_applicable",
            "revenue_source": raw_data.get("revenue_source") or "not_applicable",
        }
    return traffic_rows


def _materialize_daily_negative_review_rows(traffic_rows: list[dict]) -> list[dict]:
    """Persist dated review counts alongside period metrics without inventing a split."""
    materialized = list(traffic_rows)
    for row in traffic_rows:
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        daily_counts = raw_data.get("negative_reviews_daily")
        if not isinstance(daily_counts, dict):
            continue
        try:
            period_start = date.fromisoformat(str(row.get("period_start") or "")[:10])
            period_end = date.fromisoformat(str(row.get("period_end") or "")[:10])
        except ValueError:
            continue
        source = str(row.get("source") or "organic")
        review_source = str(raw_data.get("negative_reviews_source") or "unavailable")
        for day_text, count in daily_counts.items():
            try:
                review_day = date.fromisoformat(str(day_text)[:10])
                review_count = int(count)
            except (TypeError, ValueError):
                continue
            if review_count <= 0 or not (period_start <= review_day <= period_end):
                continue
            materialized.append(
                {
                    "source": source,
                    "grain": "daily",
                    "stat_date": review_day.isoformat(),
                    "period_start": review_day.isoformat(),
                    "period_end": review_day.isoformat(),
                    "region": str(row.get("region") or ""),
                    "entity_type": str(row.get("entity_type") or "sku"),
                    "entity_id": str(row.get("entity_id") or ""),
                    "sku": str(row.get("sku") or ""),
                    "product_name": str(row.get("product_name") or ""),
                    "impressions": None,
                    "clicks": None,
                    "add_to_cart": None,
                    "orders": None,
                    "buyers": None,
                    "units_sold": None,
                    "negative_reviews": review_count,
                    "revenue": None,
                    "currency": "",
                    "raw_data": {
                        "metric_source": "negative_reviews_daily",
                        "negative_reviews_source": review_source,
                        "derived": True,
                        "derivation_method": "review_date",
                        "source_period_start": period_start.isoformat(),
                        "source_period_end": period_end.isoformat(),
                    },
                }
            )
    return materialized


def _mercado_order_region(order: Order) -> str:
    site = _normalize_region(order.site)
    country = str(order.country_code or "").strip().upper()
    if site and site not in MERCADO_CBT_REGIONS:
        return site
    return MERCADO_COUNTRY_REGIONS.get(country, site or country)


def _mercado_local_date(value: datetime, region: str) -> date:
    timezone_name = MERCADO_REGION_TIMEZONES.get(region)
    if not timezone_name:
        return value.date()
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.astimezone(ZoneInfo(timezone_name)).date()


def _nested_dict(value, *keys: str) -> dict:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _mercado_local_item_id(item: OrderItem) -> str:
    payload = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    candidates = (
        _nested_dict(payload, "raw_payload", "item").get("id"),
        _nested_dict(payload, "item").get("id"),
        payload.get("item_id"),
        payload.get("local_item_id"),
        _nested_dict(payload, "raw_payload").get("item_id"),
    )
    for candidate in candidates:
        text = str(candidate or "").strip().upper()
        if text and not text.startswith("CBT"):
            return text
    return ""


def _mercado_order_groups(
    db: Session,
    account: PlatformAccount,
    start: date,
    end: date,
) -> dict[tuple[date, str, str], dict]:
    query_start = _date_time(start - timedelta(days=1))
    query_end = _date_time(end + timedelta(days=1), end=True)
    rows = db.execute(
        select(Order, OrderItem)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(
            Order.platform == account.platform,
            Order.account_id == account.account_id,
            or_(
                and_(Order.payment_at >= query_start, Order.payment_at <= query_end),
                and_(
                    Order.payment_at.is_(None),
                    Order.platform_created_at >= query_start,
                    Order.platform_created_at <= query_end,
                ),
            ),
        )
    ).all()
    grouped: dict[tuple[date, str, str], dict] = {}
    for order, item in rows:
        if _order_is_cancelled(order):
            continue
        occurred_at = order.payment_at or order.platform_created_at
        region = _mercado_order_region(order)
        local_item_id = _mercado_local_item_id(item)
        if not occurred_at or not region or not local_item_id:
            continue
        occurred_on = _mercado_local_date(occurred_at, region)
        if occurred_on < start or occurred_on > end:
            continue
        key = (occurred_on, region, local_item_id)
        value = grouped.setdefault(
            key,
            {
                "order_ids": set(),
                "buyer_ids": set(),
                "skus": set(),
                "units_sold": 0,
                "revenue": Decimal("0"),
                "has_revenue": False,
                "currencies": set(),
                "product_name": item.platform_product_name or "",
            },
        )
        value["order_ids"].add(str(order.platform_order_id or order.id))
        buyer_id = str(order.buyer_id or "").strip() or f"order:{order.platform_order_id or order.id}"
        value["buyer_ids"].add(buyer_id)
        if str(item.sku or "").strip():
            value["skus"].add(str(item.sku).strip())
        quantity = int(item.quantity or 1)
        value["units_sold"] += quantity
        unit_price = _decimal_or_none(item.unit_price)
        if unit_price is not None:
            value["revenue"] += unit_price * quantity
            value["has_revenue"] = True
        currency = str(item.currency or order.currency or "").strip().upper()
        if currency:
            value["currencies"].add(currency)
        if not value["product_name"] and item.platform_product_name:
            value["product_name"] = item.platform_product_name
    return grouped


def _merge_mercado_orders(
    db: Session,
    account: PlatformAccount,
    traffic_rows: list[dict],
    start: date,
    end: date,
) -> list[dict]:
    grouped = _mercado_order_groups(db, account, start, end)
    periods = sorted(
        {
            (str(row.get("period_start") or ""), str(row.get("period_end") or ""))
            for row in traffic_rows
            if row.get("period_start") and row.get("period_end")
        }
    )
    period_orders: dict[tuple[str, str, str, str], dict] = {}
    for (day, region, local_item_id), values in grouped.items():
        day_text = day.isoformat()
        period = next(((period_start, period_end) for period_start, period_end in periods if period_start <= day_text <= period_end), None)
        if not period:
            continue
        key = (*period, region, local_item_id)
        target = period_orders.setdefault(
            key,
            {
                "order_ids": set(),
                "buyer_ids": set(),
                "skus": set(),
                "units_sold": 0,
                "revenue": Decimal("0"),
                "has_revenue": False,
                "currencies": set(),
                "product_name": values["product_name"],
            },
        )
        target["order_ids"].update(values["order_ids"])
        target["buyer_ids"].update(values["buyer_ids"])
        target["skus"].update(values["skus"])
        target["units_sold"] += values["units_sold"]
        target["revenue"] += values["revenue"]
        target["has_revenue"] = target["has_revenue"] or values["has_revenue"]
        target["currencies"].update(values["currencies"])
        if not target["product_name"] and values["product_name"]:
            target["product_name"] = values["product_name"]

    unmatched = dict(period_orders)
    period_currencies: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for (period_start, period_end, region, _local_item_id), values in period_orders.items():
        period_currencies[(period_start, period_end, region)].update(values["currencies"])
    for row in traffic_rows:
        key = (
            str(row.get("period_start") or ""),
            str(row.get("period_end") or ""),
            str(row.get("region") or "").upper(),
            str(row.get("entity_id") or "").upper(),
        )
        values = unmatched.pop(key, None)
        row["orders"] = len(values["order_ids"]) if values else 0
        row["buyers"] = len(values["buyer_ids"]) if values else 0
        row["units_sold"] = values["units_sold"] if values else 0
        row["revenue"] = values["revenue"] if values and values["has_revenue"] else Decimal("0")
        region_currencies = sorted(period_currencies.get(key[:3], set()))
        if not row.get("currency") and region_currencies:
            row["currency"] = region_currencies[0] if len(region_currencies) == 1 else "MIXED"
        if not values:
            continue
        seller_skus = sorted(values["skus"])
        if seller_skus:
            row["sku"] = seller_skus[0]
        if values["product_name"]:
            row["product_name"] = values["product_name"]
        currencies = sorted(values["currencies"])
        row["currency"] = currencies[0] if len(currencies) == 1 else "MIXED" if currencies else row.get("currency", "")
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        row["raw_data"] = {**raw_data, "metric_source": "mercado_visits_and_local_orders", "seller_skus": seller_skus}

    for (period_start, period_end, region, local_item_id), values in unmatched.items():
        seller_skus = sorted(values["skus"])
        currencies = sorted(values["currencies"])
        traffic_rows.append(
            {
                "source": "organic",
                "grain": "date_range",
                "stat_date": period_end,
                "period_start": period_start,
                "period_end": period_end,
                "region": region,
                "entity_type": "sku",
                "entity_id": local_item_id,
                "sku": seller_skus[0] if seller_skus else local_item_id,
                "product_name": values["product_name"],
                "impressions": None,
                "clicks": None,
                "add_to_cart": None,
                "orders": len(values["order_ids"]),
                "buyers": len(values["buyer_ids"]),
                "units_sold": values["units_sold"],
                "negative_reviews": None,
                "revenue": values["revenue"] if values["has_revenue"] else None,
                "currency": currencies[0] if len(currencies) == 1 else "MIXED" if currencies else "",
                "raw_data": {"metric_source": "local_orders", "seller_skus": seller_skus},
            }
        )
    return traffic_rows


def _decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _metric_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_values(account: PlatformAccount, row: dict, synced_at: datetime) -> dict:
    stat_date = date.fromisoformat(str(row.get("stat_date"))[:10])
    period_start = date.fromisoformat(str(row.get("period_start"))[:10])
    period_end = date.fromisoformat(str(row.get("period_end"))[:10])
    dimensions = [
        account.platform,
        account.account_id,
        str(row.get("source") or "organic"),
        str(row.get("grain") or "daily"),
        stat_date.isoformat(),
        period_start.isoformat(),
        period_end.isoformat(),
        str(row.get("region") or ""),
        str(row.get("entity_type") or "sku"),
        str(row.get("entity_id") or ""),
        str(row.get("sku") or ""),
    ]
    return {
        "record_key": hashlib.sha256("\x1f".join(dimensions).encode("utf-8")).hexdigest(),
        "platform_account_id": account.id,
        "platform": account.platform,
        "account_id": account.account_id,
        "shop_name": account.display_name or account.account_id,
        "source": dimensions[2],
        "grain": dimensions[3],
        "stat_date": stat_date,
        "period_start": period_start,
        "period_end": period_end,
        "region": dimensions[7],
        "entity_type": dimensions[8],
        "entity_id": dimensions[9],
        "sku": dimensions[10],
        "product_name": str(row.get("product_name") or ""),
        "impressions": _metric_int(row.get("impressions")),
        "clicks": _metric_int(row.get("clicks")),
        "add_to_cart": _metric_int(row.get("add_to_cart")),
        "orders": _metric_int(row.get("orders")),
        "buyers": _metric_int(row.get("buyers")),
        "units_sold": _metric_int(row.get("units_sold")),
        "negative_reviews": _metric_int(row.get("negative_reviews")),
        "revenue": _decimal_or_none(row.get("revenue")),
        "currency": str(row.get("currency") or ""),
        "raw_data": row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {},
        "synced_at": synced_at,
        "created_at": synced_at,
        "updated_at": synced_at,
    }


def _replace_period_metrics(
    db: Session,
    account: PlatformAccount,
    values: list[dict],
    delete_start: date,
    delete_end: date,
    *,
    preserve_period_regions: set[tuple[date, date, str]] | None = None,
) -> int:
    delete_conditions = [
        and_(
            TrafficMetric.grain.in_(("daily", "date_range")),
            TrafficMetric.period_start >= delete_start,
            TrafficMetric.period_end <= delete_end,
        ),
        and_(TrafficMetric.grain == "rolling_30d", TrafficMetric.stat_date == delete_end),
    ]
    negative_review_periods: set[tuple[date, date]] = set()
    for value in values:
        raw_data = value.get("raw_data") if isinstance(value.get("raw_data"), dict) else {}
        if "negative_reviews_daily" not in raw_data:
            continue
        try:
            period_start = date.fromisoformat(str(value.get("period_start") or "")[:10])
            period_end = date.fromisoformat(str(value.get("period_end") or "")[:10])
        except ValueError:
            continue
        negative_review_periods.add((period_start, period_end))
    for period_start, period_end in negative_review_periods:
        delete_conditions.append(
            and_(
                TrafficMetric.grain == "daily",
                TrafficMetric.stat_date >= period_start,
                TrafficMetric.stat_date <= period_end,
                TrafficMetric.raw_data["metric_source"].as_string() == "negative_reviews_daily",
            )
        )
    delete_query = db.query(TrafficMetric).filter(
        TrafficMetric.platform_account_id == account.id,
        or_(*delete_conditions),
    )
    for period_start, period_end, region in preserve_period_regions or set():
        delete_query = delete_query.filter(
            ~and_(
                TrafficMetric.period_start == period_start,
                TrafficMetric.period_end == period_end,
                TrafficMetric.region == region,
            )
        )
    delete_query.delete(synchronize_session=False)
    if not values:
        return 0

    if db.bind and db.bind.dialect.name == "postgresql":
        update_columns = {
            column.name: getattr(pg_insert(TrafficMetric).excluded, column.name)
            for column in TrafficMetric.__table__.columns
            if column.name not in {"id", "record_key"}
        }
        for index in range(0, len(values), 500):
            statement = pg_insert(TrafficMetric).values(values[index : index + 500])
            db.execute(
                statement.on_conflict_do_update(
                    index_elements=[TrafficMetric.record_key],
                    set_=update_columns,
                )
            )
    else:
        for value in values:
            current = db.scalar(select(TrafficMetric).where(TrafficMetric.record_key == value["record_key"]))
            if current:
                for key, item in value.items():
                    if key not in {"record_key", "created_at"}:
                        setattr(current, key, item)
            else:
                db.add(TrafficMetric(**value))
    return len(values)


def _row_period_region(row: dict) -> tuple[date, date, str] | None:
    try:
        period_start = date.fromisoformat(str(row.get("period_start") or "")[:10])
        period_end = date.fromisoformat(str(row.get("period_end") or "")[:10])
    except ValueError:
        return None
    return period_start, period_end, str(row.get("region") or "").strip().upper()


def _mercado_partial_period_regions(rows: list[dict]) -> set[tuple[date, date, str]]:
    result: set[tuple[date, date, str]] = set()
    for row in rows:
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        period_region = _row_period_region(row)
        if raw_data.get("traffic_sync_status") == "partial" and period_region:
            result.add(period_region)
    return result


def _mercado_partial_sync_message(rows: list[dict], start: date, end: date) -> str:
    previous_start, previous_end = previous_period(start, end)
    period_scopes = {
        (start, end): "本期",
        (previous_start, previous_end): "上期",
    }
    site_health: dict[tuple[str, str], tuple[int, int, int]] = {}
    site_errors: dict[tuple[str, str], str] = {}
    for row in rows:
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        if raw_data.get("traffic_sync_status") != "partial":
            continue
        period_region = _row_period_region(row)
        if not period_region or period_region[:2] not in period_scopes:
            continue
        scope = period_scopes[period_region[:2]]
        region = str(row.get("region") or "未知站点").strip().upper() or "未知站点"
        expected = int(raw_data.get("traffic_expected_items") or 0)
        received = int(raw_data.get("traffic_received_items") or 0)
        missing = int(raw_data.get("traffic_missing_items") or max(0, expected - received))
        key = (scope, region)
        current = site_health.get(key, (0, 0, 0))
        site_health[key] = (
            max(current[0], expected),
            max(current[1], received),
            max(current[2], missing),
        )
        error_samples = raw_data.get("traffic_error_samples")
        if isinstance(error_samples, list) and error_samples:
            site_errors.setdefault(key, str(error_samples[0])[:160])
    if not site_health:
        return ""
    details = "；".join(
        (
            f"{region} {scope}已获取 {received}/{expected}，缺少 {missing}"
            + (f"（{site_errors[(scope, region)]}）" if (scope, region) in site_errors else "")
        )
        for (scope, region), (expected, received, missing) in sorted(
            site_health.items(),
            key=lambda item: (0 if item[0][0] == "本期" else 1, item[0][1]),
        )
    )
    return f"美客多访问量部分成功：{details}"


def _traffic_failure_status(exc: Exception) -> str:
    if isinstance(exc, ConnectorRuntimeError) and exc.code == "TRAFFIC_SYNC_TIMEOUT":
        return "timed_out"
    return "failed"


async def _sync_one_run(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(TrafficSyncRun, run_id)
        if not run:
            return
        run.status = "running"
        run.started_at = datetime.utcnow()
        run.error_message = ""
        db.commit()

        account = db.get(PlatformAccount, run.platform_account_id)
        if not account or not account.enabled:
            raise RuntimeError("店铺不存在或已停用")
        current_start, current_end = run.date_from, run.date_to
        compare_start, compare_end = previous_period(current_start, current_end)
        connector = _connector_for_account(db, account.platform, account.account_id)

        if account.platform == "mercadolibre":
            rows = await connector.fetch_traffic(_date_time(current_start), _date_time(current_end, end=True))
            rows = _merge_mercado_orders(db, account, rows, compare_start, current_end)
        elif account.platform == "wildberries":
            rows = await connector.fetch_traffic(_date_time(current_start), _date_time(current_end, end=True))
        elif account.platform == "joom_logistics":
            rows = await connector.fetch_traffic(_date_time(current_start), _date_time(current_end, end=True))
        else:
            rows = await connector.fetch_traffic(_date_time(compare_start), _date_time(current_end, end=True))
            if account.platform == "allegro":
                rows.extend(_local_daily_order_rows(db, account, compare_start, current_end))

        if account.platform != "mercadolibre":
            rows = _merge_local_order_metrics(db, account, rows, compare_start, current_end)
        rows = _materialize_daily_negative_review_rows(rows)

        partial_period_regions = (
            _mercado_partial_period_regions(rows)
            if account.platform == "mercadolibre"
            else set()
        )
        complete_rows = [
            row
            for row in rows
            if _row_period_region(row) not in partial_period_regions
        ]
        synced_at = datetime.utcnow()
        values = [_record_values(account, row, synced_at) for row in complete_rows]
        written = _replace_period_metrics(
            db,
            account,
            values,
            compare_start,
            current_end,
            preserve_period_regions=partial_period_regions,
        )
        run = db.get(TrafficSyncRun, run_id)
        partial_message = (
            _mercado_partial_sync_message(rows, current_start, current_end)
            if account.platform == "mercadolibre"
            else ""
        )
        run.status = "partial_success" if partial_message else "success"
        run.rows_written = written
        run.error_message = partial_message
        run.finished_at = datetime.utcnow()
        db.commit()
        if partial_message:
            logger.warning(
                "Traffic sync partially completed: run_id=%s account=%s detail=%s",
                run_id,
                account.account_id,
                partial_message,
            )
    except Exception as exc:
        logger.exception("Traffic sync run failed: run_id=%s", run_id)
        db.rollback()
        run = db.get(TrafficSyncRun, run_id)
        if run:
            run.status = _traffic_failure_status(exc)
            run.error_message = (str(exc) or type(exc).__name__)[:4000]
            run.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


async def _run_traffic_sync_runs(run_ids: Iterable[int]) -> None:
    normalized_ids = [int(run_id) for run_id in run_ids]
    db = SessionLocal()
    try:
        rows = db.execute(
            select(TrafficSyncRun.id, TrafficSyncRun.platform)
            .where(TrafficSyncRun.id.in_(normalized_ids))
            .order_by(TrafficSyncRun.id)
        ).all()
    finally:
        db.close()
    grouped: dict[str, list[int]] = defaultdict(list)
    for run_id, platform in rows:
        grouped[str(platform)].append(int(run_id))

    async def run_platform(platform: str, platform_run_ids: list[int]) -> None:
        for run_id in platform_run_ids:
            try:
                await _sync_one_run(run_id)
            except Exception:
                logger.exception(
                    "Unexpected traffic sync runner failure; continuing platform queue: platform=%s run_id=%s",
                    platform,
                    run_id,
                )

    await asyncio.gather(
        *(run_platform(platform, platform_run_ids) for platform, platform_run_ids in grouped.items())
    )


def run_traffic_sync_runs(run_ids: Iterable[int]) -> None:
    asyncio.run(_run_traffic_sync_runs(run_ids))


def audit_traffic_data_freshness(db: Session, *, today: date | None = None) -> int:
    expected_period_end = (today or date.today()) - timedelta(days=1)
    rows = db.execute(
        select(
            PlatformAccount.platform,
            PlatformAccount.account_id,
            func.max(TrafficMetric.period_end),
        )
        .outerjoin(TrafficMetric, TrafficMetric.platform_account_id == PlatformAccount.id)
        .where(
            PlatformAccount.platform.in_(SUPPORTED_TRAFFIC_PLATFORMS),
            PlatformAccount.enabled.is_(True),
        )
        .group_by(PlatformAccount.id, PlatformAccount.platform, PlatformAccount.account_id)
    ).all()
    stale_count = 0
    for platform, account_id, latest_period_end in rows:
        if latest_period_end is not None and latest_period_end >= expected_period_end:
            continue
        stale_count += 1
        lag_text = (
            f"{(expected_period_end - latest_period_end).days} days"
            if latest_period_end
            else "no data"
        )
        logger.error(
            "Traffic data freshness alert: platform=%s account=%s expected_period_end=%s "
            "latest_period_end=%s lag=%s",
            platform,
            account_id,
            expected_period_end,
            latest_period_end,
            lag_text,
        )
    return stale_count


def run_scheduled_traffic_sync(
    *,
    triggered_by: str = "scheduler:daily-06:00",
    attempt_limit: int = MAX_SCHEDULED_TRAFFIC_ATTEMPTS_PER_PERIOD,
) -> int:
    db = SessionLocal()
    try:
        _, pending_ids = create_traffic_sync_runs(
            db,
            TrafficSyncRequest(),
            triggered_by=triggered_by,
            skip_successful_period=True,
            scheduled_attempt_limit=attempt_limit,
        )
    finally:
        db.close()
    if pending_ids:
        run_traffic_sync_runs(pending_ids)
    audit_db = SessionLocal()
    try:
        audit_traffic_data_freshness(audit_db)
    except Exception:
        logger.exception("Traffic data freshness audit failed")
    finally:
        audit_db.close()
    return len(pending_ids)


def _traffic_filter_conditions(
    *,
    platform: str | Iterable[str] = "",
    platform_account_id: int | Iterable[int] | None = None,
    source: str = "",
    region: str | Iterable[str] = "",
) -> list:
    platform_values = sorted(
        {
            value.strip().lower()
            for value in ([platform] if isinstance(platform, str) else platform or [])
            if value.strip()
        }
    )
    account_values = sorted(
        {
            int(value)
            for value in (
                [platform_account_id]
                if isinstance(platform_account_id, int)
                else platform_account_id or []
            )
        }
    )
    region_values = sorted(
        {
            value.strip().upper()
            for value in ([region] if isinstance(region, str) else region or [])
            if value.strip()
        }
    )
    conditions = []
    if platform_values:
        conditions.append(TrafficMetric.platform.in_(platform_values))
    if account_values:
        conditions.append(TrafficMetric.platform_account_id.in_(account_values))
    if source:
        conditions.append(TrafficMetric.source == source)
    if region_values:
        conditions.append(TrafficMetric.region.in_(region_values))
    return conditions


def _effective_date_range_periods(
    db: Session,
    start: date,
    end: date,
    *,
    allow_mercado_period_mismatch: bool = False,
    **filters,
) -> dict[int, tuple[str, date, date]]:
    period_days = (end - start).days + 1
    if period_days < 1 or period_days > 31:
        return {}
    filter_conditions = _traffic_filter_conditions(**filters)
    statement = (
        select(
            TrafficMetric.platform,
            TrafficMetric.platform_account_id,
            TrafficMetric.period_start,
            TrafficMetric.period_end,
        )
        .distinct()
        .where(
            TrafficMetric.grain == "date_range",
            TrafficMetric.period_end <= end,
            TrafficMetric.period_end >= end - timedelta(days=MAX_DATE_RANGE_FALLBACK_LAG_DAYS),
            *filter_conditions,
        )
        .order_by(
            TrafficMetric.platform_account_id,
            TrafficMetric.period_end.desc(),
            TrafficMetric.period_start.desc(),
        )
    )

    result: dict[int, tuple[str, date, date]] = {}
    mercado_fallbacks: dict[int, tuple[str, date, date]] = {}
    for platform, account_id, period_start, period_end in db.execute(statement).all():
        account_id = int(account_id)
        if account_id in result:
            continue
        period = (str(platform), period_start, period_end)
        if (period_end - period_start).days + 1 == period_days:
            result[account_id] = period
        elif allow_mercado_period_mismatch and platform == "mercadolibre":
            mercado_fallbacks.setdefault(account_id, period)
    for account_id, period in mercado_fallbacks.items():
        result.setdefault(account_id, period)
    return result


def _period_fallback_items(
    periods: dict[int, tuple[str, date, date]],
    requested_start: date,
    requested_end: date,
    *,
    scope: str = "current",
) -> list[dict]:
    return [
        {
            "platform": platform,
            "platform_account_id": account_id,
            "scope": scope,
            "requested_date_from": requested_start.isoformat(),
            "requested_date_to": requested_end.isoformat(),
            "actual_date_from": actual_start.isoformat(),
            "actual_date_to": actual_end.isoformat(),
        }
        for account_id, (platform, actual_start, actual_end) in sorted(periods.items())
        if (actual_start, actual_end) != (requested_start, requested_end)
    ]


def _filtered_metric_rows(
    start: date,
    end: date,
    *,
    include_rolling: bool,
    date_range_periods: dict[int, tuple[str, date, date]] | None = None,
    **filters,
):
    columns = [getattr(TrafficMetric, field) for field in TRAFFIC_QUERY_FIELDS]
    filter_conditions = _traffic_filter_conditions(**filters)
    date_range_condition = and_(
        TrafficMetric.grain == "date_range",
        TrafficMetric.period_start == start,
        TrafficMetric.period_end == end,
    )
    if date_range_periods is not None:
        effective_period_conditions = [
            and_(
                TrafficMetric.platform == platform,
                TrafficMetric.platform_account_id == account_id,
                TrafficMetric.period_start == period_start,
                TrafficMetric.period_end == period_end,
            )
            for account_id, (platform, period_start, period_end) in date_range_periods.items()
        ]
        if effective_period_conditions:
            date_range_condition = and_(
                TrafficMetric.grain == "date_range",
                or_(*effective_period_conditions),
            )
    period_rows = select(*columns).where(
        or_(
            and_(
                TrafficMetric.grain == "daily",
                TrafficMetric.stat_date >= start,
                TrafficMetric.stat_date <= end,
            ),
            date_range_condition,
        ),
        *filter_conditions,
    )
    if not include_rolling:
        return period_rows.subquery("traffic_period_rows")

    rolling_rank = func.row_number().over(
        partition_by=(
            TrafficMetric.platform_account_id,
            TrafficMetric.source,
            TrafficMetric.region,
            TrafficMetric.entity_type,
            TrafficMetric.entity_id,
            TrafficMetric.sku,
        ),
        order_by=TrafficMetric.stat_date.desc(),
    ).label("snapshot_rank")
    ranked_rolling = (
        select(*columns, rolling_rank)
        .where(
            TrafficMetric.grain == "rolling_30d",
            TrafficMetric.stat_date <= end,
            *filter_conditions,
        )
        .subquery("ranked_traffic_snapshots")
    )
    latest_rolling = select(
        *(ranked_rolling.c[field] for field in TRAFFIC_QUERY_FIELDS)
    ).where(ranked_rolling.c.snapshot_rank == 1)
    return union_all(period_rows, latest_rolling).subquery("filtered_traffic_metrics")


def _rate(numerator, denominator):
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def _normalize_traffic_sku(value: str | None) -> str:
    return (value or "").strip().lower()


def _mapping_timestamp(updated_at: datetime | None, created_at: datetime | None) -> datetime:
    return updated_at or created_at or datetime.min


def _row_value(row, field: str):
    if isinstance(row, dict):
        return row.get(field)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping.get(field)
    return getattr(row, field, None)


def _traffic_product_name_lookup(
    db: Session,
    rows: list,
) -> dict[tuple[int, str], str]:
    traffic_keys = {
        (
            int(_row_value(row, "platform_account_id")),
            str(_row_value(row, "sku") or "").strip(),
            _normalize_traffic_sku(_row_value(row, "sku")),
        )
        for row in rows
        if _row_value(row, "platform_account_id") and str(_row_value(row, "sku") or "").strip()
    }
    if not traffic_keys:
        return {}

    shop_ids = sorted({shop_id for shop_id, _sku, _normalized_sku in traffic_keys})
    exact_skus = sorted({sku for _shop_id, sku, _normalized_sku in traffic_keys})
    normalized_skus = sorted({normalized_sku for _shop_id, _sku, normalized_sku in traffic_keys})
    normalized_mapping_sku = func.lower(func.trim(func.coalesce(ProductShopMapping.shop_sku, "")))
    mapping_rows = db.execute(
        select(
            ProductShopMapping.id,
            ProductShopMapping.shop_id,
            ProductShopMapping.shop_sku,
            ProductShopMapping.created_at,
            ProductShopMapping.updated_at,
            Product.internal_name,
        )
        .join(Product, Product.id == ProductShopMapping.product_id)
        .where(
            ProductShopMapping.shop_id.in_(shop_ids),
            or_(ProductShopMapping.shop_sku.in_(exact_skus), normalized_mapping_sku.in_(normalized_skus)),
        )
    ).all()

    exact_candidates: dict[tuple[int, str], tuple[datetime, int, str]] = {}
    insensitive_candidates: dict[tuple[int, str], tuple[datetime, int, str]] = {}
    for mapping_id, shop_id, shop_sku, created_at, updated_at, product_name in mapping_rows:
        display_name = (product_name or "").strip()
        if not display_name:
            continue
        rank = (_mapping_timestamp(updated_at, created_at), int(mapping_id or 0), display_name)
        exact_key = (int(shop_id), (shop_sku or "").strip())
        if exact_key not in exact_candidates or rank[:2] > exact_candidates[exact_key][:2]:
            exact_candidates[exact_key] = rank
        insensitive_key = (int(shop_id), _normalize_traffic_sku(shop_sku))
        if insensitive_key not in insensitive_candidates or rank[:2] > insensitive_candidates[insensitive_key][:2]:
            insensitive_candidates[insensitive_key] = rank

    result: dict[tuple[int, str], str] = {}
    for shop_id, sku, normalized_sku in traffic_keys:
        candidate = exact_candidates.get((shop_id, sku)) or insensitive_candidates.get((shop_id, normalized_sku))
        if candidate:
            result[(shop_id, sku)] = candidate[2]
    return result


def _metric_aggregate_statement(
    rows,
    group_fields: tuple[str, ...],
    *,
    include_product_name: bool,
):
    group_columns = [rows.c[field] for field in group_fields]
    selections = list(group_columns)
    if include_product_name:
        selections.append(func.max(func.nullif(rows.c.product_name, "")).label("product_name"))
    selections.extend(func.sum(rows.c[field]).label(field) for field in METRIC_FIELDS)

    currency_value = func.nullif(rows.c.currency, "")
    currency_count = func.count(func.distinct(currency_value))
    selections.extend(
        (
            case(
                (currency_count == 0, ""),
                (currency_count == 1, func.max(currency_value)),
                else_="MIXED",
            ).label("currency"),
            func.min(rows.c.period_start).label("period_start"),
            func.max(rows.c.period_end).label("period_end"),
            func.max(rows.c.synced_at).label("synced_at"),
        )
    )
    total_count = func.count()
    for field in METRIC_FIELDS:
        available_count = func.count(rows.c[field])
        selections.append(
            case(
                (available_count == 0, "unavailable"),
                (available_count == total_count, "full"),
                else_="partial",
            ).label(f"coverage_{field}")
        )
    return select(*selections).group_by(*group_columns)


def _metric_item(row) -> dict:
    item = dict(row)
    for field in METRIC_FIELDS:
        value = item.get(field)
        if value is not None:
            item[field] = float(value) if field == "revenue" else int(value)
    if "product_name" in item:
        item["product_name"] = str(item.get("product_name") or "")
    item["currency"] = str(item.get("currency") or "")
    item["period_start"] = item["period_start"].isoformat()
    item["period_end"] = item["period_end"].isoformat()
    item["synced_at"] = _utc_iso(item["synced_at"])
    item["coverage"] = {
        field: item.pop(f"coverage_{field}")
        for field in METRIC_FIELDS
    }
    item["ctr"] = _rate(item["clicks"], item["impressions"])
    item["cart_rate"] = _rate(item["add_to_cart"], item["clicks"])
    item["cvr"] = _rate(item["orders"], item["clicks"])
    item["cart_conversion"] = _rate(item["orders"], item["add_to_cart"])
    if item.get("sales_share") is not None:
        item["sales_share"] = float(item["sales_share"])
    if item.get("rank") is not None:
        item["rank"] = int(item["rank"])
    return item


def _apply_product_names(db: Session, items: list[dict]) -> None:
    product_names = _traffic_product_name_lookup(db, items)
    for item in items:
        key = (int(item.get("platform_account_id") or 0), str(item.get("sku") or "").strip())
        if key in product_names:
            item["product_name"] = product_names[key]


def _json_text(column, key: str):
    return func.nullif(func.trim(cast(column[key].as_string(), String)), "")


def _categorized_metric_rows(rows, *, cte_name: str = "categorized_traffic_metrics"):
    raw_data = rows.c.raw_data
    legacy_joom_category_id = case(
        (rows.c.platform == "joom_logistics", _json_text(raw_data, "category_id")),
        else_=None,
    )
    legacy_joom_category_name = case(
        (rows.c.platform == "joom_logistics", _json_text(raw_data, "category")),
        else_=None,
    )
    platform_category_id = func.coalesce(
        _json_text(raw_data, "platform_category_id"),
        legacy_joom_category_id,
        "",
    ).label("platform_category_id")
    platform_category_name = func.coalesce(
        _json_text(raw_data, "platform_category_name"),
        legacy_joom_category_name,
        "",
    ).label("platform_category_name")
    platform_category_path = func.coalesce(
        _json_text(raw_data, "platform_category_path"),
        legacy_joom_category_name,
        "",
    ).label("platform_category_path")
    category_fields = tuple(field for field in TRAFFIC_QUERY_FIELDS if field != "raw_data")
    return (
        select(
            *(rows.c[field] for field in category_fields),
            platform_category_id,
            platform_category_name,
            platform_category_path,
        )
        .where(
            rows.c.entity_type == "sku",
            or_(rows.c.sku != "", rows.c.entity_id != ""),
        )
        .cte(cte_name)
    )


def _apply_platform_category_metadata(db: Session, items: list[dict]) -> None:
    for item in items:
        category_id = str(item.get("platform_category_id") or "")
        if not category_id:
            item["platform_category_name"] = "未归类"
            item["platform_category_path"] = ""
            item["categorized"] = False
            continue
        item["platform_category_name"] = str(
            item.get("platform_category_name") or category_id
        )
        item["platform_category_path"] = str(
            item.get("platform_category_path") or item["platform_category_name"]
        )
        item["categorized"] = True


def query_categories(
    db: Session,
    start: date,
    end: date,
    **filters,
) -> dict:
    effective_periods = _effective_date_range_periods(
        db,
        start,
        end,
        allow_mercado_period_mismatch=True,
        **filters,
    )
    rows = _filtered_metric_rows(
        start,
        end,
        include_rolling=True,
        date_range_periods=effective_periods,
        **filters,
    )
    category_rows = _categorized_metric_rows(rows)
    sku_value = func.coalesce(func.nullif(category_rows.c.sku, ""), category_rows.c.entity_id)
    sku_key = (
        cast(category_rows.c.platform_account_id, String)
        + literal("\x1f")
        + sku_value
    )
    aggregate_statement = _metric_aggregate_statement(
        category_rows,
        CATEGORY_GROUP_FIELDS,
        include_product_name=False,
    ).add_columns(
        func.max(func.nullif(category_rows.c.platform_category_name, "")).label("platform_category_name"),
        func.max(func.nullif(category_rows.c.platform_category_path, "")).label("platform_category_path"),
        func.count(func.distinct(sku_value)).label("sku_count"),
    )
    aggregates = aggregate_statement.subquery("aggregated_category_traffic")
    revenue_partition = (
        aggregates.c.platform_account_id,
        aggregates.c.source,
        aggregates.c.grain,
        aggregates.c.region,
        aggregates.c.currency,
    )
    with_revenue_totals = select(
        *aggregates.c,
        func.sum(aggregates.c.revenue)
        .over(partition_by=revenue_partition)
        .label("revenue_total"),
    ).subquery("category_traffic_with_revenue_totals")
    sales_share = case(
        (with_revenue_totals.c.currency == "MIXED", None),
        (with_revenue_totals.c.revenue == 0, 0.0),
        (
            and_(
                with_revenue_totals.c.revenue.is_not(None),
                with_revenue_totals.c.revenue_total > 0,
            ),
            cast(with_revenue_totals.c.revenue, Float)
            / cast(with_revenue_totals.c.revenue_total, Float),
        ),
        else_=None,
    ).label("sales_share")
    coverage_counts = select(
        func.count(func.distinct(sku_key)).label("total_sku_count"),
        func.count(
            func.distinct(
                case(
                    (category_rows.c.platform_category_id != "", sku_key),
                    else_=None,
                )
            )
        ).label("categorized_sku_count"),
    ).cte("category_coverage_counts")
    statement = (
        select(
            *with_revenue_totals.c,
            sales_share,
            coverage_counts.c.total_sku_count,
            coverage_counts.c.categorized_sku_count,
        )
        .select_from(with_revenue_totals.join(coverage_counts, true()))
        .order_by(
            with_revenue_totals.c.platform,
            with_revenue_totals.c.shop_name,
            with_revenue_totals.c.region,
            with_revenue_totals.c.platform_category_name,
            with_revenue_totals.c.platform_category_id,
        )
    )
    raw_items = db.execute(statement).mappings().all()
    total_sku_count = int(raw_items[0].get("total_sku_count") or 0) if raw_items else 0
    categorized_sku_count = int(raw_items[0].get("categorized_sku_count") or 0) if raw_items else 0
    items = [_metric_item(row) for row in raw_items]
    for item in items:
        item["platform_category_id"] = str(item.get("platform_category_id") or "")
        item["platform_category_name"] = str(item.get("platform_category_name") or "")
        item["platform_category_path"] = str(item.get("platform_category_path") or "")
        item["sku_count"] = int(item.get("sku_count") or 0)
        item.pop("revenue_total", None)
        item.pop("total_sku_count", None)
        item.pop("categorized_sku_count", None)
        if item.get("currency") == "MIXED":
            item["revenue"] = None
            item["sales_share"] = None
    _apply_platform_category_metadata(db, items)
    return {
        "items": items,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "total_sku_count": total_sku_count,
        "categorized_sku_count": categorized_sku_count,
        "uncategorized_sku_count": max(0, total_sku_count - categorized_sku_count),
        "classification_rate": (
            float(categorized_sku_count) / float(total_sku_count)
            if total_sku_count
            else 0.0
        ),
        "fallback_periods": _period_fallback_items(effective_periods, start, end),
    }


def query_summary(
    db: Session,
    start: date,
    end: date,
    **filters,
) -> dict:
    effective_periods = _effective_date_range_periods(
        db,
        start,
        end,
        allow_mercado_period_mismatch=True,
        **filters,
    )
    rows = _filtered_metric_rows(
        start,
        end,
        include_rolling=True,
        date_range_periods=effective_periods,
        **filters,
    )
    statement = _metric_aggregate_statement(
        rows,
        SUMMARY_GROUP_FIELDS,
        include_product_name=False,
    )
    items = [_metric_item(row) for row in db.execute(statement).mappings().all()]
    items.sort(key=lambda item: (item["platform"], item["shop_name"], item["source"], item["grain"], item["region"]))
    return {
        "items": items,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "fallback_periods": _period_fallback_items(effective_periods, start, end),
    }


def query_negative_reviews_daily(
    db: Session,
    start: date,
    end: date,
    **filters,
) -> dict:
    """Return only persisted daily negative-review rows, never period fallbacks."""
    columns = [getattr(TrafficMetric, field) for field in TRAFFIC_QUERY_FIELDS]
    filter_conditions = _traffic_filter_conditions(**filters)
    rows = (
        select(*columns)
        .where(
            TrafficMetric.grain == "daily",
            TrafficMetric.stat_date >= start,
            TrafficMetric.stat_date <= end,
            *filter_conditions,
        )
        .subquery("daily_negative_review_metrics")
    )
    statement = _metric_aggregate_statement(
        rows,
        DAILY_NEGATIVE_REVIEW_GROUP_FIELDS,
        include_product_name=False,
    )
    items = [_metric_item(row) for row in db.execute(statement).mappings().all()]
    items.sort(
        key=lambda item: (
            item["stat_date"],
            item["platform"],
            item["shop_name"],
            item["source"],
            item["region"],
        )
    )
    return {
        "items": items,
        "metric": "negative_reviews",
        "grain": "daily",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "fallback_periods": [],
    }


def query_rankings(
    db: Session,
    start: date,
    end: date,
    *,
    metric: str,
    limit: int,
    sort_order: str = "desc",
    **filters,
) -> dict:
    if metric not in RANKING_METRICS:
        raise ValueError("排行指标不受支持")
    if sort_order not in RANKING_SORT_ORDERS:
        raise ValueError("排行排序方向不受支持")
    result_limit = max(1, min(limit, 100))
    effective_periods = _effective_date_range_periods(
        db,
        start,
        end,
        allow_mercado_period_mismatch=True,
        **filters,
    )
    rows = _filtered_metric_rows(
        start,
        end,
        include_rolling=True,
        date_range_periods=effective_periods,
        **filters,
    )
    sku_rows = select(*(rows.c[field] for field in TRAFFIC_QUERY_FIELDS)).where(
        rows.c.entity_type == "sku",
        or_(rows.c.sku != "", rows.c.entity_id != ""),
    ).subquery("sku_traffic_metrics")
    aggregates = _metric_aggregate_statement(
        sku_rows,
        RANKING_GROUP_FIELDS,
        include_product_name=True,
    ).subquery("aggregated_sku_traffic")
    revenue_partition = (
        aggregates.c.platform_account_id,
        aggregates.c.source,
        aggregates.c.grain,
        aggregates.c.region,
        aggregates.c.currency,
    )
    with_revenue_totals = select(
        *aggregates.c,
        func.sum(aggregates.c.revenue)
        .over(partition_by=revenue_partition)
        .label("revenue_total"),
    ).subquery("sku_traffic_with_revenue_totals")
    sales_share = case(
        (with_revenue_totals.c.revenue == 0, 0.0),
        (
            and_(
                with_revenue_totals.c.revenue.is_not(None),
                with_revenue_totals.c.revenue_total > 0,
            ),
            cast(with_revenue_totals.c.revenue, Float)
            / cast(with_revenue_totals.c.revenue_total, Float),
        ),
        else_=None,
    ).label("sales_share")
    if metric == "ctr":
        numerator = with_revenue_totals.c.clicks
        denominator = with_revenue_totals.c.impressions
    elif metric == "cvr":
        numerator = with_revenue_totals.c.orders
        denominator = with_revenue_totals.c.clicks
    else:
        numerator = None
        denominator = None

    if numerator is not None and denominator is not None:
        ranking_value = case(
            (or_(numerator.is_(None), denominator.is_(None)), None),
            (denominator == 0, 0.0),
            else_=cast(numerator, Float) / cast(denominator, Float),
        )
    else:
        ranking_value = with_revenue_totals.c[metric]
    ranking_order = ranking_value.asc() if sort_order == "asc" else ranking_value.desc()
    ranking_null_order = case((ranking_value.is_(None), 1), else_=0)
    global_rank = func.row_number().over(
        order_by=(
            ranking_null_order,
            ranking_order,
            func.coalesce(with_revenue_totals.c.orders, 0).desc(),
            with_revenue_totals.c.platform,
            with_revenue_totals.c.platform_account_id,
            with_revenue_totals.c.entity_id,
            with_revenue_totals.c.sku,
        ),
    ).label("rank")
    ranked_statement = select(
        *(with_revenue_totals.c[field] for field in aggregates.c.keys()),
        sales_share,
        global_rank,
    )
    if metric not in {"ctr", "cvr"}:
        ranked_statement = ranked_statement.where(ranking_value.is_not(None))
    ranked = ranked_statement.subquery("ranked_sku_traffic")
    statement = (
        select(ranked)
        .where(ranked.c.rank <= result_limit)
        .order_by(ranked.c.rank)
    )
    ranked_items = [_metric_item(row) for row in db.execute(statement).mappings().all()]
    _apply_product_names(db, ranked_items)
    return {
        "items": ranked_items,
        "metric": metric,
        "sort_order": sort_order,
        "rank_scope": "global",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "fallback_periods": _period_fallback_items(effective_periods, start, end),
    }


def _resolved_category_comparison_rows(
    current_rows,
    previous_rows,
    *,
    cte_name_prefix: str = "",
):
    current_category_rows = _categorized_metric_rows(
        current_rows,
        cte_name=f"{cte_name_prefix}current_categorized_traffic_metrics",
    )
    previous_category_rows = _categorized_metric_rows(
        previous_rows,
        cte_name=f"{cte_name_prefix}previous_categorized_traffic_metrics",
    )
    category_query_fields = tuple(field for field in TRAFFIC_QUERY_FIELDS if field != "raw_data")
    unresolved_period_rows = union_all(
        select(
            *(current_category_rows.c[field] for field in category_query_fields),
            current_category_rows.c.platform_category_id,
            current_category_rows.c.platform_category_name,
            current_category_rows.c.platform_category_path,
            literal("current").label("comparison_period"),
        ),
        select(
            *(previous_category_rows.c[field] for field in category_query_fields),
            previous_category_rows.c.platform_category_id,
            previous_category_rows.c.platform_category_name,
            previous_category_rows.c.platform_category_path,
            literal("previous").label("comparison_period"),
        ),
    ).subquery(f"{cte_name_prefix}unresolved_category_comparison_rows")
    category_partition = (
        unresolved_period_rows.c.platform_account_id,
        unresolved_period_rows.c.source,
        unresolved_period_rows.c.grain,
        unresolved_period_rows.c.region,
        unresolved_period_rows.c.entity_type,
        unresolved_period_rows.c.entity_id,
        unresolved_period_rows.c.sku,
    )
    known_category_id = func.max(
        func.nullif(unresolved_period_rows.c.platform_category_id, "")
    ).over(partition_by=category_partition)
    known_category_name = func.max(
        func.nullif(unresolved_period_rows.c.platform_category_name, "")
    ).over(partition_by=category_partition)
    known_category_path = func.max(
        func.nullif(unresolved_period_rows.c.platform_category_path, "")
    ).over(partition_by=category_partition)
    return select(
        *(unresolved_period_rows.c[field] for field in category_query_fields),
        func.coalesce(
            func.nullif(unresolved_period_rows.c.platform_category_id, ""),
            known_category_id,
            "",
        ).label("platform_category_id"),
        func.coalesce(
            func.nullif(unresolved_period_rows.c.platform_category_name, ""),
            known_category_name,
            "",
        ).label("platform_category_name"),
        func.coalesce(
            func.nullif(unresolved_period_rows.c.platform_category_path, ""),
            known_category_path,
            "",
        ).label("platform_category_path"),
        unresolved_period_rows.c.comparison_period,
    ).subquery(f"{cte_name_prefix}resolved_category_comparison_rows")


def query_comparison(
    db: Session,
    start: date,
    end: date,
    *,
    metric: str,
    limit: int,
    dimension: str = "sku",
    sort_by: str = "delta_abs",
    **filters,
) -> dict:
    if metric not in {"impressions", "clicks", "add_to_cart", "orders"}:
        raise ValueError("变化指标不受支持")
    if dimension not in COMPARISON_DIMENSIONS:
        raise ValueError("环比分析维度不受支持")
    if sort_by not in COMPARISON_SORTS:
        raise ValueError("环比排序方式不受支持")
    previous_start, previous_end = previous_period(start, end)
    result_limit = max(1, min(limit, 100))
    current_periods = _effective_date_range_periods(db, start, end, **filters)
    previous_periods = _effective_date_range_periods(db, previous_start, previous_end, **filters)
    current_rows = _filtered_metric_rows(
        start,
        end,
        include_rolling=False,
        date_range_periods=current_periods,
        **filters,
    )
    previous_rows = _filtered_metric_rows(
        previous_start,
        previous_end,
        include_rolling=False,
        date_range_periods=previous_periods,
        **filters,
    )
    if dimension == "category":
        period_rows = _resolved_category_comparison_rows(current_rows, previous_rows)
        group_fields = CATEGORY_GROUP_FIELDS
    else:
        period_rows = union_all(
            select(
                *(current_rows.c[field] for field in TRAFFIC_QUERY_FIELDS),
                literal("current").label("comparison_period"),
            ),
            select(
                *(previous_rows.c[field] for field in TRAFFIC_QUERY_FIELDS),
                literal("previous").label("comparison_period"),
            ),
        ).subquery("comparison_traffic_metrics")
        group_fields = COMPARISON_GROUP_FIELDS

    group_columns = [period_rows.c[field] for field in group_fields]
    selections = [*group_columns]
    if dimension == "sku":
        current_name = func.max(
            case(
                (
                    period_rows.c.comparison_period == "current",
                    func.nullif(period_rows.c.product_name, ""),
                ),
                else_=None,
            )
        )
        previous_name = func.max(
            case(
                (
                    period_rows.c.comparison_period == "previous",
                    func.nullif(period_rows.c.product_name, ""),
                ),
                else_=None,
            )
        )
        selections.append(func.coalesce(current_name, previous_name, "").label("product_name"))
    else:
        selections.extend(
            (
                func.max(func.nullif(period_rows.c.platform_category_name, "")).label("platform_category_name"),
                func.max(func.nullif(period_rows.c.platform_category_path, "")).label("platform_category_path"),
            )
        )
    for field in METRIC_FIELDS:
        selections.extend(
            (
                func.sum(
                    case(
                        (period_rows.c.comparison_period == "current", period_rows.c[field]),
                        else_=None,
                    )
                ).label(f"current_{field}"),
                func.sum(
                    case(
                        (period_rows.c.comparison_period == "previous", period_rows.c[field]),
                        else_=None,
                    )
                ).label(f"previous_{field}"),
            )
        )
    aggregates = select(*selections).group_by(*group_columns).subquery("aggregated_traffic_comparison")
    current_metric = aggregates.c[f"current_{metric}"]
    previous_metric = aggregates.c[f"previous_{metric}"]
    selected_delta = func.coalesce(current_metric, 0) - func.coalesce(previous_metric, 0)
    selected_rate = case(
        (func.coalesce(previous_metric, 0) == 0, 0.0),
        else_=cast(selected_delta, Float) / cast(previous_metric, Float),
    )
    if sort_by == "rate_desc":
        order_by = [selected_rate.desc(), func.abs(selected_delta).desc()]
    elif sort_by == "rate_asc":
        order_by = [selected_rate.asc(), func.abs(selected_delta).desc()]
    elif sort_by == "current_desc":
        order_by = [func.coalesce(current_metric, 0).desc(), func.abs(selected_delta).desc()]
    elif sort_by == "current_asc":
        order_by = [func.coalesce(current_metric, 0).asc(), func.abs(selected_delta).desc()]
    elif sort_by == "previous_desc":
        order_by = [func.coalesce(previous_metric, 0).desc(), func.abs(selected_delta).desc()]
    elif sort_by == "previous_asc":
        order_by = [func.coalesce(previous_metric, 0).asc(), func.abs(selected_delta).desc()]
    elif sort_by == "delta_desc":
        order_by = [selected_delta.desc(), func.abs(selected_delta).desc()]
    elif sort_by == "delta_asc":
        order_by = [selected_delta.asc(), func.abs(selected_delta).desc()]
    else:
        order_by = [func.abs(selected_delta).desc()]
    order_by.extend((aggregates.c.platform, aggregates.c.platform_account_id))
    if dimension == "category":
        order_by.extend((aggregates.c.region, aggregates.c.platform_category_id))
    else:
        order_by.extend((aggregates.c.entity_id, aggregates.c.sku))
    statement = (
        select(aggregates)
        .where(or_(current_metric.is_not(None), previous_metric.is_not(None)))
        .order_by(*order_by)
        .limit(result_limit)
    )
    items = []
    item_fields = [*group_fields]
    if dimension == "sku":
        item_fields.append("product_name")
    else:
        item_fields.extend(("platform_category_name", "platform_category_path"))
    for index, row in enumerate(db.execute(statement).mappings().all(), 1):
        values = dict(row)
        item = {
            field: values.get(field)
            for field in item_fields
        }
        if dimension == "sku":
            item["product_name"] = str(item.get("product_name") or "")
        else:
            item["platform_category_id"] = str(item.get("platform_category_id") or "")
            item["platform_category_name"] = str(item.get("platform_category_name") or "")
            item["platform_category_path"] = str(item.get("platform_category_path") or "")
        for field in METRIC_FIELDS:
            current_value = values.get(f"current_{field}")
            previous_value = values.get(f"previous_{field}")
            if current_value is not None or previous_value is not None:
                current_value = current_value or 0
                previous_value = previous_value or 0
            if field == "revenue":
                current_value = float(current_value) if current_value is not None else None
                previous_value = float(previous_value) if previous_value is not None else None
            else:
                current_value = int(current_value) if current_value is not None else None
                previous_value = int(previous_value) if previous_value is not None else None
            delta = (
                current_value - previous_value
                if current_value is not None and previous_value is not None
                else None
            )
            item[f"current_{field}"] = current_value
            item[f"previous_{field}"] = previous_value
            item[f"delta_{field}"] = delta
            item[f"delta_rate_{field}"] = _rate(delta, previous_value)
        item["rank"] = index
        items.append(item)
    if dimension == "sku":
        _apply_product_names(db, items)
    else:
        _apply_platform_category_metadata(db, items)
    return {
        "items": items,
        "metric": metric,
        "dimension": dimension,
        "sort_by": sort_by,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "previous_date_from": previous_start.isoformat(),
        "previous_date_to": previous_end.isoformat(),
        "fallback_periods": [
            *_period_fallback_items(current_periods, start, end, scope="current"),
            *_period_fallback_items(previous_periods, previous_start, previous_end, scope="previous"),
        ],
    }


def _category_sku_aggregates(
    db: Session,
    start: date,
    end: date,
    *,
    platform: str,
    platform_account_id: int,
    source: str,
    grain: str,
    region: str,
    platform_category_id: str,
    keyword: str = "",
):
    platform_value = str(platform or "").strip().lower()
    source_value = str(source or "").strip().lower()
    grain_value = str(grain or "").strip().lower()
    region_value = str(region or "").strip().upper()
    category_id_value = str(platform_category_id or "").strip()
    account_id_value = int(platform_account_id or 0)
    if not platform_value or not account_id_value or not grain_value:
        raise ValueError("品类明细上下文不完整")

    previous_start, previous_end = previous_period(start, end)
    base_filters = {
        "platform": [platform_value],
        "platform_account_id": [account_id_value],
        "source": source_value,
        "region": [region_value] if region_value else [],
    }
    current_periods = _effective_date_range_periods(db, start, end, **base_filters)
    previous_periods = _effective_date_range_periods(db, previous_start, previous_end, **base_filters)
    current_rows = _filtered_metric_rows(
        start,
        end,
        include_rolling=False,
        date_range_periods=current_periods,
        **base_filters,
    )
    previous_rows = _filtered_metric_rows(
        previous_start,
        previous_end,
        include_rolling=False,
        date_range_periods=previous_periods,
        **base_filters,
    )
    period_rows = _resolved_category_comparison_rows(
        current_rows,
        previous_rows,
        cte_name_prefix="category_sku_",
    )
    target_rows = select(period_rows).where(
        period_rows.c.platform == platform_value,
        period_rows.c.platform_account_id == account_id_value,
        period_rows.c.source == source_value,
        period_rows.c.grain == grain_value,
        period_rows.c.region == region_value,
        period_rows.c.platform_category_id == category_id_value,
        period_rows.c.entity_type == "sku",
        or_(period_rows.c.sku != "", period_rows.c.entity_id != ""),
    ).subquery("target_category_sku_rows")

    group_fields = CATEGORY_SKU_COMPARISON_GROUP_FIELDS
    group_columns = [target_rows.c[field] for field in group_fields]
    current_name = func.max(
        case(
            (
                target_rows.c.comparison_period == "current",
                func.nullif(target_rows.c.product_name, ""),
            ),
            else_=None,
        )
    )
    previous_name = func.max(
        case(
            (
                target_rows.c.comparison_period == "previous",
                func.nullif(target_rows.c.product_name, ""),
            ),
            else_=None,
        )
    )
    selections = [
        *group_columns,
        func.coalesce(current_name, previous_name, "").label("product_name"),
    ]
    for field in METRIC_FIELDS:
        selections.extend(
            (
                func.sum(
                    case(
                        (target_rows.c.comparison_period == "current", target_rows.c[field]),
                        else_=None,
                    )
                ).label(f"current_{field}"),
                func.sum(
                    case(
                        (target_rows.c.comparison_period == "previous", target_rows.c[field]),
                        else_=None,
                    )
                ).label(f"previous_{field}"),
            )
        )
    aggregates = select(*selections).group_by(*group_columns).subquery("aggregated_category_sku")

    keyword_value = str(keyword or "").strip().lower()
    if keyword_value:
        keyword_pattern = f"%{keyword_value}%"
        aggregates = select(aggregates).where(
            or_(
                func.lower(func.coalesce(aggregates.c.sku, "")).like(keyword_pattern),
                func.lower(func.coalesce(aggregates.c.entity_id, "")).like(keyword_pattern),
                func.lower(func.coalesce(aggregates.c.product_name, "")).like(keyword_pattern),
                exists(
                    select(1)
                    .select_from(ProductShopMapping)
                    .join(Product, Product.id == ProductShopMapping.product_id)
                    .where(
                        ProductShopMapping.shop_id == aggregates.c.platform_account_id,
                        func.lower(func.trim(ProductShopMapping.shop_sku))
                        == func.lower(func.trim(aggregates.c.sku)),
                        func.lower(func.coalesce(Product.internal_name, "")).like(keyword_pattern),
                    )
                ),
            )
        ).subquery("filtered_aggregated_category_sku")

    return aggregates, previous_start, previous_end, current_periods, previous_periods


def query_category_sku_comparison(
    db: Session,
    start: date,
    end: date,
    *,
    metric: str,
    limit: int,
    platform: str,
    platform_account_id: int,
    source: str,
    grain: str,
    region: str,
    platform_category_id: str,
    sort_by: str = "delta_abs",
    keyword: str = "",
    change_direction: str = "all",
) -> dict:
    if metric not in {"impressions", "clicks", "add_to_cart", "orders"}:
        raise ValueError("变化指标不受支持")
    if sort_by not in COMPARISON_SORTS:
        raise ValueError("环比排序方式不受支持")
    if change_direction not in COMPARISON_CHANGE_DIRECTIONS:
        raise ValueError("环比变化方向不受支持")
    result_limit = max(1, min(limit, 100))
    aggregates, previous_start, previous_end, current_periods, previous_periods = _category_sku_aggregates(
        db,
        start,
        end,
        platform=platform,
        platform_account_id=platform_account_id,
        source=source,
        grain=grain,
        region=region,
        platform_category_id=platform_category_id,
        keyword=keyword,
    )
    group_fields = CATEGORY_SKU_COMPARISON_GROUP_FIELDS
    current_metric = aggregates.c[f"current_{metric}"]
    previous_metric = aggregates.c[f"previous_{metric}"]
    selected_delta = func.coalesce(current_metric, 0) - func.coalesce(previous_metric, 0)
    selected_rate = case(
        (func.coalesce(previous_metric, 0) == 0, 0.0),
        else_=cast(selected_delta, Float) / cast(previous_metric, Float),
    )
    if sort_by == "rate_desc":
        order_by = [selected_rate.desc(), func.abs(selected_delta).desc()]
    elif sort_by == "rate_asc":
        order_by = [selected_rate.asc(), func.abs(selected_delta).desc()]
    elif sort_by == "current_desc":
        order_by = [func.coalesce(current_metric, 0).desc(), func.abs(selected_delta).desc()]
    elif sort_by == "current_asc":
        order_by = [func.coalesce(current_metric, 0).asc(), func.abs(selected_delta).desc()]
    elif sort_by == "previous_desc":
        order_by = [func.coalesce(previous_metric, 0).desc(), func.abs(selected_delta).desc()]
    elif sort_by == "previous_asc":
        order_by = [func.coalesce(previous_metric, 0).asc(), func.abs(selected_delta).desc()]
    elif sort_by == "delta_desc":
        order_by = [selected_delta.desc(), func.abs(selected_delta).desc()]
    elif sort_by == "delta_asc":
        order_by = [selected_delta.asc(), func.abs(selected_delta).desc()]
    else:
        order_by = [func.abs(selected_delta).desc()]
    direction_conditions = {
        "up": selected_delta > 0,
        "down": selected_delta < 0,
        "flat": selected_delta == 0,
    }
    result_conditions = [or_(current_metric.is_not(None), previous_metric.is_not(None))]
    if change_direction in direction_conditions:
        result_conditions.append(direction_conditions[change_direction])
    order_by.extend((aggregates.c.entity_id, aggregates.c.sku))
    statement = (
        select(aggregates)
        .where(*result_conditions)
        .order_by(*order_by)
        .limit(result_limit)
    )

    items = []
    item_fields = [*group_fields, "product_name"]
    for index, row in enumerate(db.execute(statement).mappings().all(), 1):
        values = dict(row)
        item = {field: values.get(field) for field in item_fields}
        item["product_name"] = str(item.get("product_name") or "")
        for field in METRIC_FIELDS:
            current_value = values.get(f"current_{field}")
            previous_value = values.get(f"previous_{field}")
            if current_value is not None or previous_value is not None:
                current_value = current_value or 0
                previous_value = previous_value or 0
            if field == "revenue":
                current_value = float(current_value) if current_value is not None else None
                previous_value = float(previous_value) if previous_value is not None else None
            else:
                current_value = int(current_value) if current_value is not None else None
                previous_value = int(previous_value) if previous_value is not None else None
            delta = (
                current_value - previous_value
                if current_value is not None and previous_value is not None
                else None
            )
            item[f"current_{field}"] = current_value
            item[f"previous_{field}"] = previous_value
            item[f"delta_{field}"] = delta
            item[f"delta_rate_{field}"] = _rate(delta, previous_value)
        item["rank"] = index
        items.append(item)
    _apply_product_names(db, items)
    return {
        "items": items,
        "metric": metric,
        "dimension": "sku",
        "sort_by": sort_by,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "previous_date_from": previous_start.isoformat(),
        "previous_date_to": previous_end.isoformat(),
        "fallback_periods": [
            *_period_fallback_items(current_periods, start, end, scope="current"),
            *_period_fallback_items(previous_periods, previous_start, previous_end, scope="previous"),
        ],
    }


def query_category_sku_focus_analysis(
    db: Session,
    start: date,
    end: date,
    *,
    top_n: int,
    platform: str,
    platform_account_id: int,
    source: str,
    grain: str,
    region: str,
    platform_category_id: str,
    keyword: str = "",
) -> dict:
    result_top_n = max(1, min(top_n, 100))
    aggregates, _, _, current_periods, _ = _category_sku_aggregates(
        db,
        start,
        end,
        platform=platform,
        platform_account_id=platform_account_id,
        source=source,
        grain=grain,
        region=region,
        platform_category_id=platform_category_id,
    )
    focus_metrics = ("impressions", "clicks", "add_to_cart", "orders")
    statement = select(aggregates).where(
        or_(*(aggregates.c[f"current_{metric}"].is_not(None) for metric in focus_metrics))
    )
    item_fields = [*CATEGORY_SKU_COMPARISON_GROUP_FIELDS, "product_name"]
    items = []
    for row in db.execute(statement).mappings().all():
        values = dict(row)
        item = {field: values.get(field) for field in item_fields}
        item["product_name"] = str(item.get("product_name") or "")
        for metric in focus_metrics:
            value = values.get(f"current_{metric}")
            item[metric] = int(value) if value is not None else None
            item[f"{metric}_rank"] = None
        items.append(item)
    _apply_product_names(db, items)

    supported_metrics = [
        metric
        for metric in focus_metrics
        if any(item[metric] is not None for item in items)
    ]
    supported_metric_set = set(supported_metrics)
    for metric in supported_metrics:
        ranked_items = [item for item in items if item[metric] is not None]
        ranked_items.sort(
            key=lambda item: (
                -int(item[metric] or 0),
                str(item.get("entity_id") or ""),
                str(item.get("sku") or ""),
            )
        )
        for metric_rank, item in enumerate(ranked_items, 1):
            item[f"{metric}_rank"] = metric_rank

    def is_top(item: dict, metric: str) -> bool:
        metric_rank = item.get(f"{metric}_rank")
        return metric_rank is not None and metric_rank <= result_top_n

    def is_outside_top(item: dict, metric: str) -> bool:
        metric_rank = item.get(f"{metric}_rank")
        return metric_rank is None or metric_rank > result_top_n

    focus_items = []
    for item in items:
        reasons = []
        if (
            {"impressions", "orders"}.issubset(supported_metric_set)
            and is_top(item, "impressions")
            and int(item.get("orders") or 0) == 0
        ):
            reasons.append("high_impressions_no_orders")
        if (
            "clicks" in supported_metric_set
            and is_top(item, "clicks")
            and (
                ("impressions" in supported_metric_set and is_outside_top(item, "impressions"))
                or ("add_to_cart" in supported_metric_set and is_outside_top(item, "add_to_cart"))
            )
        ):
            reasons.append("high_clicks_missing_impressions_or_cart")
        if (
            {"add_to_cart", "orders"}.issubset(supported_metric_set)
            and is_top(item, "add_to_cart")
            and is_outside_top(item, "orders")
        ):
            reasons.append("high_cart_missing_orders")
        if (
            {"orders", "impressions"}.issubset(supported_metric_set)
            and is_top(item, "orders")
            and is_outside_top(item, "impressions")
        ):
            reasons.append("high_orders_missing_impressions")
        if reasons:
            item["focus_reasons"] = reasons
            focus_items.append(item)

    keyword_value = str(keyword or "").strip().lower()
    if keyword_value:
        focus_items = [
            item
            for item in focus_items
            if keyword_value in str(item.get("sku") or "").lower()
            or keyword_value in str(item.get("entity_id") or "").lower()
            or keyword_value in str(item.get("product_name") or "").lower()
        ]

    reason_priority = {
        "high_impressions_no_orders": 1,
        "high_clicks_missing_impressions_or_cart": 2,
        "high_cart_missing_orders": 3,
        "high_orders_missing_impressions": 4,
    }
    focus_items.sort(
        key=lambda item: (
            -len(item["focus_reasons"]),
            min(reason_priority[reason] for reason in item["focus_reasons"]),
            min(
                item[f"{metric}_rank"]
                for metric in focus_metrics
                if item[f"{metric}_rank"] is not None
            ),
            str(item.get("sku") or item.get("entity_id") or ""),
        )
    )
    for index, item in enumerate(focus_items, 1):
        item["rank"] = index

    return {
        "items": focus_items,
        "top_n": result_top_n,
        "supported_metrics": supported_metrics,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "fallback_periods": _period_fallback_items(current_periods, start, end),
    }
