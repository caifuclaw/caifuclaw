# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ShippingDeadlineSetting


BASE_DATE_PLATFORM_CREATED = "platform_created_at"
BASE_DATE_SHIPPING_DEADLINE = "shipping_deadline_at"
BASE_DATE_PAYMENT_AT = "payment_at"
OTHER_PLATFORM = "other"

VALID_BASE_DATE_FIELDS = {BASE_DATE_PLATFORM_CREATED, BASE_DATE_SHIPPING_DEADLINE, BASE_DATE_PAYMENT_AT}

DEFAULT_SHIPPING_DEADLINE_RULES = [
    {
        "platform": "ozon",
        "base_date_field": BASE_DATE_PAYMENT_AT,
        "offset_days": 5,
    },
    {
        "platform": "wildberries",
        "base_date_field": BASE_DATE_PAYMENT_AT,
        "offset_days": 2,
    },
    {
        "platform": "mercadolibre",
        "base_date_field": BASE_DATE_PAYMENT_AT,
        "offset_days": 2,
    },
    {
        "platform": "dmsmatrix",
        "base_date_field": BASE_DATE_PAYMENT_AT,
        "offset_days": 2,
    },
    {
        "platform": "allegro",
        "base_date_field": BASE_DATE_PAYMENT_AT,
        "offset_days": 3,
    },
    {
        "platform": "joom_logistics",
        "base_date_field": BASE_DATE_PAYMENT_AT,
        "offset_days": 3,
    },
    {
        "platform": OTHER_PLATFORM,
        "base_date_field": BASE_DATE_PAYMENT_AT,
        "offset_days": 3,
    },
]

PLATFORM_ALIASES = {
    "joom": "joom_logistics",
    "joomlogistics": "joom_logistics",
    "其他": OTHER_PLATFORM,
    "others": OTHER_PLATFORM,
}


class DeadlineOrderLike(Protocol):
    platform: str | None
    platform_created_at: datetime | None
    shipping_deadline_at: datetime | None
    payment_at: datetime | None


def canonical_deadline_platform(platform: str | None) -> str:
    normalized = (platform or "").strip().lower()
    return PLATFORM_ALIASES.get(normalized, normalized)


def normalize_base_date_field(value: str | None) -> str:
    field = (value or BASE_DATE_PLATFORM_CREATED).strip()
    if field not in VALID_BASE_DATE_FIELDS:
        raise ValueError("基准日期无效")
    return field


def seed_default_shipping_deadline_settings(db: Session) -> None:
    existing = {
        row.platform: row
        for row in db.scalars(select(ShippingDeadlineSetting)).all()
    }
    now = datetime.utcnow()
    legacy_joom = existing.get("joom_logistics")
    legacy_ozon = existing.get("ozon")
    should_migrate_legacy_defaults = bool(
        legacy_joom
        and legacy_ozon
        and legacy_joom.base_date_field == BASE_DATE_PLATFORM_CREATED
        and int(legacy_joom.offset_days or 0) == 2
        and legacy_ozon.base_date_field == BASE_DATE_SHIPPING_DEADLINE
        and int(legacy_ozon.offset_days or 0) == -1
        and not any(platform in existing for platform in {"wildberries", "mercadolibre", "dmsmatrix", "allegro"})
    )

    for index, item in enumerate(DEFAULT_SHIPPING_DEADLINE_RULES):
        platform = item["platform"]
        row = existing.get(platform)
        if row and not should_migrate_legacy_defaults:
            continue
        if not row:
            row = ShippingDeadlineSetting(
                platform=platform,
                created_at=now,
            )
            db.add(row)
            existing[platform] = row
        row.base_date_field = item["base_date_field"]
        row.offset_days = int(item["offset_days"])
        row.sort_order = index
        row.enabled = True
        row.updated_at = now

    rows = db.scalars(
        select(ShippingDeadlineSetting).order_by(
            ShippingDeadlineSetting.sort_order.asc(),
            ShippingDeadlineSetting.platform.asc(),
        )
    ).all()
    seen_orders: set[int] = set()
    should_reindex = False
    for row in rows:
        sort_order = int(row.sort_order or 0)
        if sort_order in seen_orders:
            should_reindex = True
            break
        seen_orders.add(sort_order)
    if should_reindex:
        for index, row in enumerate(rows):
            row.sort_order = index
            row.updated_at = now


def load_shipping_deadline_settings(db: Session) -> dict[str, ShippingDeadlineSetting]:
    seed_default_shipping_deadline_settings(db)
    db.flush()
    return {
        row.platform: row
        for row in db.scalars(
            select(ShippingDeadlineSetting)
            .where(ShippingDeadlineSetting.enabled == True)
            .order_by(ShippingDeadlineSetting.sort_order.asc(), ShippingDeadlineSetting.platform.asc())
        ).all()
    }


def shipping_deadline_rule_for(
    settings: dict[str, ShippingDeadlineSetting],
    platform: str | None,
) -> ShippingDeadlineSetting | None:
    canonical = canonical_deadline_platform(platform)
    return settings.get(canonical) or settings.get(OTHER_PLATFORM)


def calculate_dispatch_deadline(
    order: DeadlineOrderLike,
    settings: dict[str, ShippingDeadlineSetting],
) -> datetime | None:
    rule = shipping_deadline_rule_for(settings, order.platform)
    if not rule:
        return None
    base_date = getattr(order, rule.base_date_field, None)
    if not base_date:
        return None
    return base_date + timedelta(days=int(rule.offset_days or 0))


def update_order_dispatch_deadline(
    order: DeadlineOrderLike,
    settings: dict[str, ShippingDeadlineSetting],
) -> datetime | None:
    deadline = calculate_dispatch_deadline(order, settings)
    setattr(order, "dispatch_deadline_at", deadline)
    return deadline


def backfill_order_dispatch_deadlines(db: Session) -> int:
    from .models import Order

    settings = load_shipping_deadline_settings(db)
    rows = db.scalars(select(Order)).all()
    changed = 0
    for row in rows:
        next_value = calculate_dispatch_deadline(row, settings)
        if row.dispatch_deadline_at != next_value:
            row.dispatch_deadline_at = next_value
            row.updated_at = datetime.utcnow()
            changed += 1
    return changed
