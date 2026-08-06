"""Platform listing catalog storage, pricing calculation, and synchronization.

The catalog is deliberately separate from the internal product master.  One
internal product can have several store listings and every listing can have
separate platform warehouses, inventory, price, and fulfillment data.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, asc, or_, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from .database import Base, SessionLocal
from .image_storage import IMAGE_MIME_TO_SUFFIX, ImageStorageError, download_network_image, split_image_urls
from .models import ExchangeRate, PlatformAccount, SyncCursor
from .product_models import Product, ProductShopMapping
from .settings import get_settings


CATALOG_SYNC_JOB_TYPE = "platform_product_catalog"
CATALOG_STATUS_READY = "ready"
CATALOG_STATUS_MISSING_MAPPING = "missing_mapping"
CATALOG_STATUS_MISSING_RULE = "missing_rule"
CATALOG_STATUS_MISSING_COST = "missing_cost"
CATALOG_STATUS_MISSING_RATE = "missing_exchange_rate"
CATALOG_STATUS_INVALID_RULE = "invalid_rule"
CATALOG_SUPPORTED_PLATFORMS = {"ozon", "wildberries", "mercadolibre", "joom_logistics", "allegro", "dmsmatrix"}
CATALOG_SYNC_MODE_FULL = "full"
CATALOG_SYNC_MODE_INCREMENTAL = "incremental"
CATALOG_SYNC_CURSOR_KEY_FULL = "platform_product_catalog:last_full_sync_at"
CATALOG_SYNC_CURSOR_KEY_INCREMENTAL = "platform_product_catalog:last_incremental_sync_at"
CATALOG_MAIN_IMAGE_DIR_NAME = "platform_product_catalog_images"
CATALOG_MAIN_IMAGE_URL_PREFIX = "/api/v1/platform-product-catalog/images/"
CATALOG_MAIN_IMAGE_SOURCE_URL_KEY = "catalog_main_image_source_url"
CATALOG_MAIN_IMAGE_FINAL_URL_KEY = "catalog_main_image_final_url"
CATALOG_MAIN_IMAGE_FILE_KEY = "catalog_main_image_file"
CATALOG_MAIN_IMAGE_LOCAL_URL_KEY = "catalog_main_image_local_url"
CATALOG_MAIN_IMAGE_ERROR_KEY = "catalog_main_image_download_error"
CATALOG_MAIN_IMAGE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}
CATALOG_MAIN_IMAGE_KEYS = (
    "main_image_url",
    "mainImageUrl",
    "MainImageUrl",
    "MainImageURL",
    "main_image",
    "mainImage",
    "MainImage",
    "primary_image_url",
    "primaryImageUrl",
    "PrimaryImageUrl",
    "primary_image",
    "primaryImage",
    "PrimaryImage",
    "image_url",
    "imageUrl",
    "ImageUrl",
    "ImageURL",
    "image",
    "Image",
    "item_image_url",
    "itemImageUrl",
    "ItemImageUrl",
    "ItemImageURL",
    "item_image",
    "itemImage",
    "ItemImage",
    "product_image_url",
    "productImageUrl",
    "ProductImageUrl",
    "ProductImageURL",
    "product_image",
    "productImage",
    "ProductImage",
    "thumbnail_url",
    "thumbnailUrl",
    "ThumbnailUrl",
    "thumbnail",
    "Thumbnail",
    "picture_url",
    "pictureUrl",
    "PictureUrl",
    "PictureURL",
    "photo_url",
    "photoUrl",
    "PhotoUrl",
    "PhotoURL",
    "cover_url",
    "coverUrl",
    "CoverUrl",
    "cover",
    "Cover",
)
CATALOG_IMAGE_LIST_KEYS = (
    "images",
    "Images",
    "image_urls",
    "imageUrls",
    "ImageUrls",
    "pictures",
    "Pictures",
    "photos",
    "Photos",
    "mediaFiles",
    "media_files",
    "media",
    "Media",
    "gallery_image_urls",
    "galleryImageUrls",
    "GalleryImageUrls",
    "gallery_images",
    "galleryImages",
    "GalleryImages",
    "extraImages",
)
CATALOG_IMAGE_VALUE_KEYS = (
    "url",
    "Url",
    "URL",
    "src",
    "Src",
    "source",
    "Source",
    "href",
    "Href",
    "link",
    "Link",
    "origUrl",
    "orig_url",
    "original",
    "original_url",
    "originalUrl",
    "OriginalUrl",
    "large",
    "large_url",
    "largeUrl",
    "LargeUrl",
    "big",
    "Big",
    "full",
    "full_url",
    "fullUrl",
    "preview",
    "preview_url",
    "previewUrl",
    "medium",
    "small",
)
CATALOG_IMAGE_CONTAINER_KEYS = (
    "info",
    "card",
    "product",
    "product_info",
    "productInfo",
    "product_detail",
    "productDetail",
    "item",
    "offer",
    "listing",
    "variant",
    "variants",
    "details",
    "data",
    "result",
    "payload",
    "raw_payload",
)


class PlatformProductCatalogItem(Base):
    __tablename__ = "platform_product_catalog_items"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "platform_product_id",
            "platform_sku",
            "warehouse_code",
            name="uq_platform_product_catalog_listing_warehouse",
        ),
        Index("ix_platform_product_catalog_platform_shop", "platform", "shop_id"),
        Index("ix_platform_product_catalog_product", "product_id"),
        Index("ix_platform_product_catalog_sync", "last_synced_at"),
        Index("ix_platform_product_catalog_calculation", "calculation_status"),
        {"comment": "平台商品目录，按店铺、平台 SKU 与平台仓库保存可售库存"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("platform_accounts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    pricing_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("platform_product_pricing_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(40), index=True)
    platform_product_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    platform_sku: Mapped[str] = mapped_column(String(255), default="", index=True)
    product_name: Mapped[str] = mapped_column(String(500), default="")
    listing_status: Mapped[str] = mapped_column(String(80), default="")
    warehouse_code: Mapped[str] = mapped_column(String(160), default="")
    warehouse_name: Mapped[str] = mapped_column(String(255), default="")
    fulfillment_type: Mapped[str] = mapped_column(String(80), default="")
    logistics_type: Mapped[str] = mapped_column(String(160), default="")
    available_stock: Mapped[int] = mapped_column(Integer, default=0)
    reserved_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    price_currency: Mapped[str] = mapped_column(String(12), default="CNY")
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    exchange_rate_date: Mapped[date | None] = mapped_column(nullable=True)
    current_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    cost_cny: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    shipping_fee_cny: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    target_margin_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    current_profit_cny: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    current_margin_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    suggested_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    calculation_status: Mapped[str] = mapped_column(String(80), default=CATALOG_STATUS_MISSING_MAPPING, index=True)
    calculation_message: Mapped[str] = mapped_column(Text, default="")
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mapped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mapped_by: Mapped[str] = mapped_column(String(80), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop: Mapped[PlatformAccount] = relationship()
    product: Mapped[Product | None] = relationship()
    pricing_rule: Mapped["PlatformProductPricingRule | None"] = relationship()


class PlatformProductPricingRule(Base):
    __tablename__ = "platform_product_pricing_rules"
    __table_args__ = (
        Index("ix_platform_product_pricing_rules_match", "platform", "shop_id", "enabled", "priority"),
        Index("ix_platform_product_pricing_rules_product", "product_id"),
        {"comment": "平台商品佣金、运费与建议价规则"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("platform_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True)
    warehouse_code: Mapped[str] = mapped_column(String(160), default="")
    logistics_type: Mapped[str] = mapped_column(String(160), default="")
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    base_shipping_fee_cny: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    shipping_fee_per_kg_cny: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    target_margin_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    price_increment_cny: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0.01"))
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop: Mapped[PlatformAccount | None] = relationship()
    product: Mapped[Product | None] = relationship()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _catalog_image_url_from_value(value: Any, depth: int = 0) -> str:
    if value in (None, "") or depth > 3:
        return ""
    if isinstance(value, str):
        urls = split_image_urls(value)
        if not urls:
            return ""
        image_url = urls[0]
        normalized = image_url.lower()
        if normalized.startswith(("http://", "https://", "//", "/api/", "data:image/")):
            return image_url
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            image_url = _catalog_image_url_from_value(item, depth + 1)
            if image_url:
                return image_url
        return ""
    if isinstance(value, dict):
        for key in CATALOG_IMAGE_VALUE_KEYS:
            image_url = _catalog_image_url_from_value(value.get(key), depth + 1)
            if image_url:
                return image_url
        return ""
    return ""


def catalog_main_image_url_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in CATALOG_MAIN_IMAGE_KEYS:
        image_url = _catalog_image_url_from_value(payload.get(key))
        if image_url:
            return image_url
    for key in CATALOG_IMAGE_LIST_KEYS:
        image_url = _catalog_image_url_from_value(payload.get(key))
        if image_url:
            return image_url
    for key in CATALOG_IMAGE_CONTAINER_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            image_url = catalog_main_image_url_from_payload(nested)
            if image_url:
                return image_url
        elif isinstance(nested, (list, tuple, set)):
            for item in nested:
                if isinstance(item, dict):
                    image_url = catalog_main_image_url_from_payload(item)
                else:
                    image_url = _catalog_image_url_from_value(item)
                if image_url:
                    return image_url
    return ""


def _catalog_main_image_root() -> Path:
    return (get_settings().label_storage_path / CATALOG_MAIN_IMAGE_DIR_NAME).resolve()


def _path_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def catalog_main_image_file_path(filename: str) -> Path:
    root = _catalog_main_image_root()
    safe_filename = Path(filename or "").name
    path = (root / safe_filename).resolve()
    if not safe_filename or not _path_relative_to(path, root):
        raise ValueError("invalid catalog image filename")
    return path


def catalog_main_image_local_url(filename: str) -> str:
    return f"{CATALOG_MAIN_IMAGE_URL_PREFIX}{quote(Path(filename or '').name, safe='')}"


def catalog_main_image_display_url(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    local_url = _text(payload.get(CATALOG_MAIN_IMAGE_LOCAL_URL_KEY))
    if local_url.startswith(CATALOG_MAIN_IMAGE_URL_PREFIX):
        return local_url
    source_url = catalog_main_image_url_from_payload(payload)
    remote_url = _catalog_remote_main_image_url(payload, source_url)
    if remote_url:
        existing_path = _existing_catalog_image_path_for_source(remote_url)
        if existing_path is not None:
            return catalog_main_image_local_url(existing_path.name)
    return source_url


def _catalog_remote_main_image_url(payload: dict, source_url: str | None = None) -> str:
    image_url = _text(source_url) or catalog_main_image_url_from_payload(payload)
    if image_url.startswith("//"):
        image_url = f"https:{image_url}"
    normalized = image_url.lower()
    if not normalized.startswith(("http://", "https://")):
        return ""
    return image_url


def _safe_catalog_image_stem(value: str) -> str:
    parsed_path = unquote(urlparse(value or "").path)
    stem = Path(parsed_path).stem or "catalog-main-image"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return (stem or "catalog-main-image")[:80]


def _catalog_image_filename(source_url: str, final_url: str, mime_type: str) -> str:
    digest = hashlib.sha256(_text(source_url).encode("utf-8")).hexdigest()
    suffix = IMAGE_MIME_TO_SUFFIX.get((mime_type or "").lower(), ".jpg")
    return f"{digest[:20]}_{_safe_catalog_image_stem(final_url or source_url)}{suffix}"


def _existing_catalog_image_path_for_source(source_url: str) -> Path | None:
    root = _catalog_main_image_root()
    digest = hashlib.sha256(_text(source_url).encode("utf-8")).hexdigest()[:20]
    for path in root.glob(f"{digest}_*"):
        if path.is_file() and path.suffix.lower() in CATALOG_MAIN_IMAGE_CONTENT_TYPES:
            return path
    return None


def cache_catalog_main_image(payload: dict, source_url: str | None = None) -> bool:
    if not isinstance(payload, dict):
        return False
    remote_url = _catalog_remote_main_image_url(payload, source_url)
    if not remote_url:
        return False

    changed = False
    existing_filename = _text(payload.get(CATALOG_MAIN_IMAGE_FILE_KEY))
    if existing_filename:
        try:
            existing_path = catalog_main_image_file_path(existing_filename)
        except ValueError:
            existing_path = None
        if existing_path is not None and existing_path.is_file():
            local_url = catalog_main_image_local_url(existing_path.name)
            if payload.get(CATALOG_MAIN_IMAGE_LOCAL_URL_KEY) != local_url:
                payload[CATALOG_MAIN_IMAGE_LOCAL_URL_KEY] = local_url
                changed = True
            if payload.get(CATALOG_MAIN_IMAGE_SOURCE_URL_KEY) != remote_url:
                payload[CATALOG_MAIN_IMAGE_SOURCE_URL_KEY] = remote_url
                changed = True
            if payload.pop(CATALOG_MAIN_IMAGE_ERROR_KEY, None) is not None:
                changed = True
            return changed

    existing_path = _existing_catalog_image_path_for_source(remote_url)
    if existing_path is not None:
        local_url = catalog_main_image_local_url(existing_path.name)
        for key, value in (
            (CATALOG_MAIN_IMAGE_SOURCE_URL_KEY, remote_url),
            (CATALOG_MAIN_IMAGE_FILE_KEY, existing_path.name),
            (CATALOG_MAIN_IMAGE_LOCAL_URL_KEY, local_url),
        ):
            if payload.get(key) != value:
                payload[key] = value
                changed = True
        if payload.pop(CATALOG_MAIN_IMAGE_ERROR_KEY, None) is not None:
            changed = True
        return changed

    try:
        content, mime_type, final_url = download_network_image(remote_url)
    except ImageStorageError as exc:
        error = str(exc)[:500]
        if payload.get(CATALOG_MAIN_IMAGE_ERROR_KEY) != error:
            payload[CATALOG_MAIN_IMAGE_ERROR_KEY] = error
            changed = True
        if payload.get(CATALOG_MAIN_IMAGE_SOURCE_URL_KEY) != remote_url:
            payload[CATALOG_MAIN_IMAGE_SOURCE_URL_KEY] = remote_url
            changed = True
        return changed

    filename = _catalog_image_filename(remote_url, final_url, mime_type)
    path = catalog_main_image_file_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_bytes(content)
    local_url = catalog_main_image_local_url(filename)
    for key, value in (
        (CATALOG_MAIN_IMAGE_SOURCE_URL_KEY, remote_url),
        (CATALOG_MAIN_IMAGE_FINAL_URL_KEY, final_url),
        (CATALOG_MAIN_IMAGE_FILE_KEY, filename),
        (CATALOG_MAIN_IMAGE_LOCAL_URL_KEY, local_url),
    ):
        if payload.get(key) != value:
            payload[key] = value
            changed = True
    if payload.pop(CATALOG_MAIN_IMAGE_ERROR_KEY, None) is not None:
        changed = True
    return changed


def _catalog_raw_payload(payload: dict) -> dict:
    nested_raw_payload = payload.get("raw_payload")
    if isinstance(nested_raw_payload, dict):
        raw_payload = dict(nested_raw_payload)
        for key in (*CATALOG_MAIN_IMAGE_KEYS, *CATALOG_IMAGE_LIST_KEYS):
            if key in payload and key not in raw_payload:
                raw_payload[key] = payload[key]
        return raw_payload
    return dict(payload)


def _stock(value: Any) -> int:
    try:
        return max(0, int(Decimal(str(value or 0))))
    except (InvalidOperation, ValueError, TypeError):
        return 0


def _normalize_platform(value: str) -> str:
    aliases = {
        "wb": "wildberries",
        "wildberrie": "wildberries",
        "joom": "joom_logistics",
        "joomlogistics": "joom_logistics",
        "mkd": "mercadolibre",
        "mercado": "mercadolibre",
    }
    normalized = _text(value).lower()
    return aliases.get(normalized, normalized)


def _parse_sync_cursor(value: str | None) -> datetime | None:
    text_value = _text(value)
    if not text_value:
        return None
    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        return None


def _catalog_sync_cursor_key(mode: str) -> str:
    return (
        CATALOG_SYNC_CURSOR_KEY_INCREMENTAL
        if _text(mode).lower() == CATALOG_SYNC_MODE_INCREMENTAL
        else CATALOG_SYNC_CURSOR_KEY_FULL
    )


def _load_catalog_sync_cursor(db: Session, shop: PlatformAccount, mode: str) -> datetime | None:
    key = _catalog_sync_cursor_key(mode)
    row = db.scalar(
        select(SyncCursor).where(
            SyncCursor.platform == shop.platform,
            SyncCursor.account_id == shop.account_id,
            SyncCursor.cursor_key == key,
        )
    )
    return _parse_sync_cursor(row.cursor_value if row else None)


def _load_latest_catalog_sync_cursor(db: Session, shop: PlatformAccount) -> datetime | None:
    candidates = [
        value
        for value in (
            _load_catalog_sync_cursor(db, shop, CATALOG_SYNC_MODE_FULL),
            _load_catalog_sync_cursor(db, shop, CATALOG_SYNC_MODE_INCREMENTAL),
        )
        if value
    ]
    if not candidates:
        return None
    return max(candidates)


def _save_catalog_sync_cursor(db: Session, shop: PlatformAccount, mode: str, synced_at: datetime) -> None:
    key = _catalog_sync_cursor_key(mode)
    row = db.scalar(
        select(SyncCursor).where(
            SyncCursor.platform == shop.platform,
            SyncCursor.account_id == shop.account_id,
            SyncCursor.cursor_key == key,
        )
    )
    if not row:
        row = SyncCursor(platform=shop.platform, account_id=shop.account_id, cursor_key=key)
        db.add(row)
    row.cursor_value = synced_at.isoformat()
    row.updated_at = synced_at


def _currency_rate(db: Session, currency: str, today: date) -> tuple[Decimal | None, date | None]:
    normalized = _text(currency).upper() or "CNY"
    if normalized == "CNY":
        return Decimal("1"), today
    row = db.scalar(
        select(ExchangeRate)
        .where(ExchangeRate.rate_date <= today, ExchangeRate.currency_code == normalized)
        .order_by(ExchangeRate.rate_date.desc(), ExchangeRate.updated_at.desc(), ExchangeRate.id.desc())
        .limit(1)
    )
    if not row:
        return None, None
    return row.rate, row.rate_date


def _rule_specificity(rule: PlatformProductPricingRule) -> int:
    return sum(
        1
        for value in (rule.shop_id, rule.product_id, rule.warehouse_code, rule.logistics_type)
        if value not in (None, "")
    )


def find_pricing_rule(db: Session, item: PlatformProductCatalogItem, product: Product | None) -> PlatformProductPricingRule | None:
    rules = db.scalars(
        select(PlatformProductPricingRule)
        .where(
            PlatformProductPricingRule.platform == _normalize_platform(item.platform),
            PlatformProductPricingRule.enabled == True,
            or_(PlatformProductPricingRule.shop_id.is_(None), PlatformProductPricingRule.shop_id == item.shop_id),
        )
        .order_by(asc(PlatformProductPricingRule.priority), asc(PlatformProductPricingRule.id))
    ).all()
    matched = [
        rule
        for rule in rules
        if (rule.product_id is None or rule.product_id == item.product_id)
        and (not rule.warehouse_code or rule.warehouse_code == item.warehouse_code)
        and (not rule.logistics_type or rule.logistics_type == item.logistics_type)
    ]
    if not matched:
        return None
    return sorted(matched, key=lambda rule: (rule.priority, -_rule_specificity(rule), rule.id))[0]


def calculate_suggested_price(
    *,
    cost_cny: Decimal,
    weight_kg: Decimal,
    commission_rate: Decimal,
    base_shipping_fee_cny: Decimal,
    shipping_fee_per_kg_cny: Decimal,
    target_margin_rate: Decimal,
    price_increment_cny: Decimal,
) -> tuple[Decimal, Decimal]:
    """Return the shipping fee and suggested CNY price for one listing."""
    shipping_fee = base_shipping_fee_cny + weight_kg * shipping_fee_per_kg_cny
    denominator = Decimal("1") - commission_rate - target_margin_rate
    if denominator <= 0:
        raise ValueError("佣金率与目标利润率之和必须小于 100%")
    raw_price = (cost_cny + shipping_fee) / denominator
    increment = price_increment_cny if price_increment_cny > 0 else Decimal("0.01")
    suggested = (raw_price / increment).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * increment
    return shipping_fee, suggested


def recalculate_catalog_item(db: Session, item: PlatformProductCatalogItem, *, today: date | None = None) -> None:
    current_day = today or date.today()
    item.calculated_at = datetime.utcnow()
    item.pricing_rule_id = None
    item.commission_rate = None
    item.shipping_fee_cny = None
    item.target_margin_rate = None
    item.current_profit_cny = None
    item.current_margin_rate = None
    item.suggested_price_cny = None
    item.cost_cny = None

    currency = _text(item.price_currency).upper() or "CNY"
    price = _decimal(item.price_amount)
    rate, rate_date = _currency_rate(db, currency, current_day)
    item.exchange_rate = rate
    item.exchange_rate_date = rate_date
    item.current_price_cny = price * rate if price is not None and rate is not None else None
    if price is not None and rate is None:
        item.calculation_status = CATALOG_STATUS_MISSING_RATE
        item.calculation_message = f"系统汇率表缺少 {currency} 在 {current_day.isoformat()} 或之前的汇率"
        return

    product = db.get(Product, item.product_id) if item.product_id else None
    if not product:
        item.calculation_status = CATALOG_STATUS_MISSING_MAPPING
        item.calculation_message = "请先映射内部产品"
        return
    cost = _decimal(product.cost)
    if cost is None:
        item.calculation_status = CATALOG_STATUS_MISSING_COST
        item.calculation_message = "内部产品未维护成本"
        return
    item.cost_cny = cost

    rule = find_pricing_rule(db, item, product)
    if not rule:
        item.calculation_status = CATALOG_STATUS_MISSING_RULE
        item.calculation_message = "未匹配到佣金和运费规则"
        return

    commission = _decimal(rule.commission_rate) or Decimal("0")
    target = _decimal(rule.target_margin_rate) or Decimal("0")
    base_shipping = _decimal(rule.base_shipping_fee_cny) or Decimal("0")
    per_kg = _decimal(rule.shipping_fee_per_kg_cny) or Decimal("0")
    weight = _decimal(product.gross_weight) or _decimal(product.weight) or Decimal("0")
    increment = _decimal(rule.price_increment_cny) or Decimal("0.01")
    try:
        shipping, suggested = calculate_suggested_price(
            cost_cny=cost,
            weight_kg=weight,
            commission_rate=commission,
            base_shipping_fee_cny=base_shipping,
            shipping_fee_per_kg_cny=per_kg,
            target_margin_rate=target,
            price_increment_cny=increment,
        )
    except ValueError as exc:
        item.calculation_status = CATALOG_STATUS_INVALID_RULE
        item.calculation_message = str(exc)
        return

    item.pricing_rule_id = rule.id
    item.commission_rate = commission
    item.shipping_fee_cny = shipping
    item.target_margin_rate = target
    item.suggested_price_cny = suggested
    if item.current_price_cny is not None:
        current_profit = item.current_price_cny * (Decimal("1") - commission) - cost - shipping
        item.current_profit_cny = current_profit
        item.current_margin_rate = current_profit / item.current_price_cny if item.current_price_cny else None
    item.calculation_status = CATALOG_STATUS_READY
    item.calculation_message = ""


def _catalog_identity(payload: dict) -> tuple[str, str, str]:
    product_id = _text(payload.get("platform_product_id") or payload.get("product_id") or payload.get("id"))
    sku = _text(payload.get("platform_sku") or payload.get("sku") or payload.get("offer_id") or payload.get("vendor_code"))
    warehouse = _text(payload.get("warehouse_code") or payload.get("warehouse_id") or payload.get("warehouse_name"))
    if not product_id and not sku:
        raise ValueError("平台返回的商品缺少 product id 与 SKU")
    return product_id, sku, warehouse


def _product_mapping(db: Session, shop_id: int, sku: str) -> Product | None:
    if not sku:
        return None
    return db.scalar(
        select(Product)
        .join(ProductShopMapping, ProductShopMapping.product_id == Product.id)
        .where(ProductShopMapping.shop_id == shop_id, ProductShopMapping.shop_sku == sku)
        .limit(1)
    )


def upsert_catalog_item(
    db: Session,
    shop: PlatformAccount,
    payload: dict,
    *,
    synced_at: datetime,
    cache: dict[tuple[int, str, str, str], PlatformProductCatalogItem] | None = None,
) -> PlatformProductCatalogItem:
    external_id, sku, warehouse_code = _catalog_identity(payload)
    cache_key = (shop.id, external_id, sku, warehouse_code)
    if cache is not None and cache_key in cache:
        item = cache[cache_key]
    else:
        item = db.scalar(
            select(PlatformProductCatalogItem).where(
                PlatformProductCatalogItem.shop_id == shop.id,
                PlatformProductCatalogItem.platform_product_id == external_id,
                PlatformProductCatalogItem.platform_sku == sku,
                PlatformProductCatalogItem.warehouse_code == warehouse_code,
            )
        )
        if cache is not None and item is not None:
            cache[cache_key] = item
    if not item:
        item = PlatformProductCatalogItem(
            shop_id=shop.id,
            platform=_normalize_platform(shop.platform),
            platform_product_id=external_id,
            platform_sku=sku,
            warehouse_code=warehouse_code,
        )
        db.add(item)
        if cache is not None:
            cache[cache_key] = item

    item.product_name = _text(payload.get("product_name") or payload.get("name") or payload.get("title"))
    item.listing_status = _text(payload.get("listing_status") or payload.get("status"))
    item.warehouse_code = warehouse_code
    item.warehouse_name = _text(payload.get("warehouse_name") or payload.get("warehouse"))
    item.fulfillment_type = _text(payload.get("fulfillment_type"))
    item.logistics_type = _text(payload.get("logistics_type") or payload.get("shipping_method"))
    available_stock = payload.get("available_stock")
    if available_stock is None:
        available_stock = payload.get("stock")
    if available_stock is None:
        available_stock = payload.get("quantity")
    item.available_stock = _stock(available_stock)
    reserved = payload.get("reserved_stock")
    item.reserved_stock = _stock(reserved) if reserved not in (None, "") else None
    price_amount = payload.get("price_amount")
    if price_amount is None:
        price_amount = payload.get("price")
    item.price_amount = _decimal(price_amount)
    item.price_currency = _text(payload.get("price_currency") or payload.get("currency") or "CNY").upper()
    raw_payload = _catalog_raw_payload(payload)
    cache_catalog_main_image(raw_payload)
    item.raw_payload = raw_payload
    item.last_synced_at = synced_at
    item.last_seen_at = synced_at
    item.is_active = True
    if item.product_id is None:
        product = _product_mapping(db, shop.id, sku)
        if product:
            item.product_id = product.id
            item.mapped_at = synced_at
            item.mapped_by = "shop_sku_mapping"
    recalculate_catalog_item(db, item, today=synced_at.date())
    return item


async def synchronize_platform_catalog(
    db: Session,
    *,
    shop_ids: list[int] | None = None,
    mode: str = CATALOG_SYNC_MODE_FULL,
) -> dict:
    """Synchronize every selected shop and return per-shop, auditable results."""
    normalized_mode = _text(mode).lower() or CATALOG_SYNC_MODE_FULL
    if normalized_mode not in {CATALOG_SYNC_MODE_FULL, CATALOG_SYNC_MODE_INCREMENTAL}:
        raise ValueError("unsupported catalog sync mode")
    stmt = select(PlatformAccount).where(
        PlatformAccount.enabled == True,
        PlatformAccount.encrypted_credentials.is_not(None),
        PlatformAccount.platform.in_(CATALOG_SUPPORTED_PLATFORMS),
    )
    if shop_ids:
        stmt = stmt.where(PlatformAccount.id.in_(shop_ids))
    shops = db.scalars(stmt.order_by(asc(PlatformAccount.id))).all()
    results: list[dict] = []
    for shop in shops:
        started_at = datetime.utcnow()
        item_cache: dict[tuple[int, str, str, str], PlatformProductCatalogItem] = {}
        try:
            # Imported lazily to keep model registration independent from the sync engine.
            from .sync_engine import _connector_for_account

            connector = _connector_for_account(db, shop.platform, shop.account_id)
            since = _load_latest_catalog_sync_cursor(db, shop) if normalized_mode == CATALOG_SYNC_MODE_INCREMENTAL else None
            rows = await connector.fetch_platform_products(since=since)
            synced = 0
            for payload in rows:
                if not isinstance(payload, dict):
                    continue
                upsert_catalog_item(db, shop, payload, synced_at=started_at, cache=item_cache)
                synced += 1
            db.flush()
            if normalized_mode == CATALOG_SYNC_MODE_FULL:
                db.query(PlatformProductCatalogItem).filter(
                    PlatformProductCatalogItem.shop_id == shop.id,
                    PlatformProductCatalogItem.last_seen_at.is_not(None),
                    PlatformProductCatalogItem.last_seen_at < started_at,
                ).update({PlatformProductCatalogItem.is_active: False}, synchronize_session=False)
            _save_catalog_sync_cursor(db, shop, normalized_mode, started_at)
            db.commit()
            results.append(
                {
                    "shop_id": shop.id,
                    "shop_name": shop.display_name or shop.account_id,
                    "status": "success",
                    "synced": synced,
                    "mode": normalized_mode,
                    "since": since.isoformat() if since else None,
                }
            )
        except Exception as exc:
            db.rollback()
            results.append(
                {
                    "shop_id": shop.id,
                    "shop_name": shop.display_name or shop.account_id,
                    "status": "failed",
                    "synced": 0,
                    "mode": normalized_mode,
                    "message": str(exc)[:1000],
                }
            )
    return {
        "shops": results,
        "success": sum(1 for item in results if item["status"] == "success"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "synced": sum(int(item["synced"] or 0) for item in results),
    }


def synchronize_platform_catalog_sync(
    *,
    mode: str = CATALOG_SYNC_MODE_FULL,
    shop_ids: list[int] | None = None,
) -> dict:
    db = SessionLocal()
    try:
        return asyncio.run(synchronize_platform_catalog(db, shop_ids=shop_ids, mode=mode))
    finally:
        db.close()


def recalculate_catalog(db: Session, *, item_ids: list[int] | None = None) -> int:
    stmt = select(PlatformProductCatalogItem)
    if item_ids:
        stmt = stmt.where(PlatformProductCatalogItem.id.in_(item_ids))
    rows = db.scalars(stmt).all()
    for item in rows:
        recalculate_catalog_item(db, item)
    db.commit()
    return len(rows)


def map_catalog_item(db: Session, item: PlatformProductCatalogItem, product_id: int | None, *, username: str) -> PlatformProductCatalogItem:
    if product_id is None:
        item.product_id = None
        item.mapped_at = datetime.utcnow()
        item.mapped_by = username
        recalculate_catalog_item(db, item)
        db.commit()
        return item
    product = db.get(Product, product_id)
    if not product:
        raise ValueError("内部产品不存在")
    if item.platform_sku:
        existing = db.scalar(
            select(ProductShopMapping).where(
                ProductShopMapping.shop_id == item.shop_id,
                ProductShopMapping.shop_sku == item.platform_sku,
            )
        )
        if existing and existing.product_id != product.id:
            raise ValueError("该店铺 SKU 已映射到其他内部产品，请先在产品管理中处理映射")
        if not existing:
            db.add(ProductShopMapping(product_id=product.id, shop_id=item.shop_id, shop_sku=item.platform_sku))
    item.product_id = product.id
    item.mapped_at = datetime.utcnow()
    item.mapped_by = username
    recalculate_catalog_item(db, item)
    db.commit()
    return item
