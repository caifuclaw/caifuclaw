from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from .country_mapping import country_name_cn, country_name_to_code
from .models import LogisticsMatchRule, Order
from .order_types import order_is_joom_standard_online_fulfillment, order_is_overseas_warehouse

LOGISTICS_MATCH_STATUS_MATCHED = "matched"
LOGISTICS_MATCH_STATUS_UNMATCHED = "unmatched"
LOGISTICS_MATCH_STATUS_MANUAL = "manual"
MANUAL_LOGISTICS_RULE_NAME = "人工指定"

PLATFORM_ALIASES = {
    "joom": "joom_logistics",
    "joomlogistics": "joom_logistics",
    "mercado": "mercadolibre",
    "mercado_global": "mercadolibre",
    "mercadoglobal": "mercadolibre",
    "mercado_libre": "mercadolibre",
    "tiktok": "tiktok_shop",
    "tiktokshop": "tiktok_shop",
    "ali_express": "aliexpress",
    "shopify_admin": "shopify",
    "ebay_sell": "ebay",
    "walmart_marketplace": "walmart",
    "shein_open": "shein",
    "coupang_openapi": "coupang",
    "wayfair_partner": "wayfair",
}


@dataclass(frozen=True)
class LogisticsMatchResult:
    status: str
    logistics_channel: str = ""
    carrier_code: str = ""
    rule_id: int | None = None
    rule_name: str = ""
    reason: str = ""


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def normalize_platform_code(value: object) -> str:
    text = _clean_text(value).lower()
    return PLATFORM_ALIASES.get(text, text)


def normalize_carrier_code(value: object) -> str:
    return _clean_text(value).lower()


def normalize_shop_names(values: Iterable[object] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = _clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def normalize_country_codes(values: Iterable[object] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = _clean_text(value)
        if not text:
            continue
        code = text.upper() if len(text) == 2 and text.isalpha() else country_name_to_code(text).upper()
        if not code:
            code = text.upper()
        if code in seen:
            continue
        seen.add(code)
        result.append(code)
    return result


def order_shop_candidates(order: Order) -> list[str]:
    values = [
        getattr(order, "shop_id", None),
        getattr(order, "shop_name", None),
        getattr(order, "account_id", None),
    ]
    return normalize_shop_names(values)


def order_country_code(order: Order) -> str:
    code = _clean_text(getattr(order, "country_code", None)).upper()
    if code:
        return code
    return country_name_to_code(_clean_text(getattr(order, "country_name_cn", None))).upper()


def logistics_rule_matches(order: Order, rule: LogisticsMatchRule) -> bool:
    rule_platform = normalize_platform_code(getattr(rule, "platform", ""))
    order_platform = normalize_platform_code(getattr(order, "platform", ""))
    if not rule_platform or rule_platform != order_platform:
        return False

    rule_shops = {item.casefold() for item in normalize_shop_names(getattr(rule, "shop_names", None))}
    rule_countries = set(normalize_country_codes(getattr(rule, "country_codes", None)))

    if rule_shops:
        candidates = {item.casefold() for item in order_shop_candidates(order)}
        if not candidates.intersection(rule_shops):
            return False

    rule_is_overseas_warehouse = getattr(rule, "is_overseas_warehouse", None)
    if rule_is_overseas_warehouse is not None and order_is_overseas_warehouse(order) != rule_is_overseas_warehouse:
        return False

    if rule_countries:
        code = order_country_code(order)
        if code not in rule_countries:
            return False

    return True


def logistics_match_reason(order: Order, rule: LogisticsMatchRule) -> str:
    parts: list[str] = []
    rule_shops = normalize_shop_names(getattr(rule, "shop_names", None))
    rule_countries = normalize_country_codes(getattr(rule, "country_codes", None))
    rule_platform = normalize_platform_code(getattr(rule, "platform", ""))
    shop_text = _clean_text(getattr(order, "shop_name", None)) or _clean_text(getattr(order, "shop_id", None)) or _clean_text(getattr(order, "account_id", None))
    country_code = order_country_code(order)
    country_label = country_name_cn(country_code) if country_code else ""

    if rule_platform:
        parts.append(f"平台 {rule_platform}")
    if rule_shops:
        parts.append(f"店铺 {shop_text or '-'}")
    rule_is_overseas_warehouse = getattr(rule, "is_overseas_warehouse", None)
    if rule_is_overseas_warehouse is not None:
        parts.append(f"海外仓 {'是' if rule_is_overseas_warehouse else '否'}")
    if rule_countries:
        parts.append(f"目的国家 {country_label or country_code or '-'}({country_code or '-'})")
    if not parts:
        parts.append("默认规则")
    return "，".join(parts)


def load_enabled_logistics_rules(db: Session) -> list[LogisticsMatchRule]:
    return db.scalars(
        select(LogisticsMatchRule)
        .where(LogisticsMatchRule.enabled == True)
        .order_by(asc(LogisticsMatchRule.priority), asc(LogisticsMatchRule.id))
    ).all()


def match_logistics_rule(order: Order, rules: list[LogisticsMatchRule]) -> LogisticsMatchResult:
    for rule in rules:
        logistics_channel = _clean_text(getattr(rule, "logistics_channel", ""))
        if not logistics_channel:
            continue
        if logistics_rule_matches(order, rule):
            return LogisticsMatchResult(
                status=LOGISTICS_MATCH_STATUS_MATCHED,
                logistics_channel=logistics_channel,
                carrier_code=normalize_carrier_code(getattr(rule, "carrier_code", "")),
                rule_id=getattr(rule, "id", None),
                rule_name=_clean_text(getattr(rule, "name", "")),
                reason=logistics_match_reason(order, rule),
            )
    return LogisticsMatchResult(
        status=LOGISTICS_MATCH_STATUS_UNMATCHED,
        reason="未命中启用的物流规则",
    )


def apply_logistics_match_result(order: Order, result: LogisticsMatchResult, *, matched_at: datetime | None = None) -> bool:
    now = matched_at or datetime.utcnow()
    changes = {
        "logistics_channel": result.logistics_channel,
        "logistics_carrier_code": result.carrier_code,
        "logistics_match_rule_id": result.rule_id,
        "logistics_match_rule_name": result.rule_name,
        "logistics_match_status": result.status,
        "logistics_match_reason": result.reason,
        "logistics_matched_at": now,
    }
    changed = False
    for key, value in changes.items():
        if getattr(order, key, None) != value:
            setattr(order, key, value)
            changed = True
    if changed:
        order.updated_at = now
    return changed


def apply_manual_logistics_channel(
    order: Order,
    logistics_channel: str,
    *,
    carrier_code: str = "",
    matched_at: datetime | None = None,
) -> bool:
    channel = _clean_text(logistics_channel)
    result = LogisticsMatchResult(
        status=LOGISTICS_MATCH_STATUS_MANUAL if channel else LOGISTICS_MATCH_STATUS_UNMATCHED,
        logistics_channel=channel,
        carrier_code=normalize_carrier_code(carrier_code),
        rule_id=None,
        rule_name=MANUAL_LOGISTICS_RULE_NAME if channel else "",
        reason="人工指定物流渠道" if channel else "清空人工指定物流渠道",
    )
    return apply_logistics_match_result(order, result, matched_at=matched_at)


def order_matches_logistics_carrier_rule(
    order: Order,
    rules: list[LogisticsMatchRule],
    carrier_code: str,
) -> bool:
    """Return whether the current enabled rules route an order to a carrier."""
    if _clean_text(getattr(order, "logistics_match_status", "")).lower() == LOGISTICS_MATCH_STATUS_MANUAL:
        return False
    result = match_logistics_rule(order, rules)
    return result.status == LOGISTICS_MATCH_STATUS_MATCHED and result.carrier_code == normalize_carrier_code(carrier_code)


def apply_logistics_rules(order: Order, rules: list[LogisticsMatchRule], *, override_manual: bool = False, matched_at: datetime | None = None) -> bool:
    if not override_manual and getattr(order, "logistics_match_status", "") == LOGISTICS_MATCH_STATUS_MANUAL:
        return False
    return apply_logistics_match_result(order, match_logistics_rule(order, rules), matched_at=matched_at)


def logistics_rule_platforms(rules: list[LogisticsMatchRule]) -> set[str]:
    platforms: set[str] = set()
    for rule in rules or []:
        platform = normalize_platform_code(getattr(rule, "platform", ""))
        if platform and _clean_text(getattr(rule, "logistics_channel", "")):
            platforms.add(platform)
    return platforms


def order_has_active_logistics_match(order: Order) -> bool:
    status = _clean_text(getattr(order, "logistics_match_status", "")).lower()
    if status not in {LOGISTICS_MATCH_STATUS_MATCHED, LOGISTICS_MATCH_STATUS_MANUAL}:
        return False
    return bool(_clean_text(getattr(order, "logistics_channel", "")))


def split_logistics_rule_eligible_orders(
    orders: list[Order],
    rules: list[LogisticsMatchRule],
    *,
    matched_at: datetime | None = None,
) -> tuple[list[Order], list[Order]]:
    rule_platforms = logistics_rule_platforms(rules)
    if not rule_platforms:
        return list(orders or []), []

    eligible: list[Order] = []
    unmatched: list[Order] = []
    for order in orders or []:
        platform = normalize_platform_code(getattr(order, "platform", ""))
        # Joom's regular seller-fulfilled orders must call fulfillOnline and
        # obtain Joom's platform label.  A BSI rule for Joom physical-warehouse
        # orders must not turn the regular online flow into an unmatched skip.
        if order_is_joom_standard_online_fulfillment(order):
            eligible.append(order)
            continue
        if not platform or platform not in rule_platforms:
            eligible.append(order)
            continue
        apply_logistics_rules(order, rules, matched_at=matched_at)
        if order_has_active_logistics_match(order):
            eligible.append(order)
        else:
            unmatched.append(order)
    return eligible, unmatched
