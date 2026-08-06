# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import asyncio
import hashlib
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ExchangeRate, PlatformAccount, SyncCursor
from app.platform_product_catalog import (
    CATALOG_MAIN_IMAGE_FILE_KEY,
    CATALOG_MAIN_IMAGE_LOCAL_URL_KEY,
    CATALOG_MAIN_IMAGE_SOURCE_URL_KEY,
    CATALOG_MAIN_IMAGE_URL_PREFIX,
    CATALOG_MAIN_IMAGE_DIR_NAME,
    CATALOG_SYNC_CURSOR_KEY_FULL,
    CATALOG_SYNC_MODE_FULL,
    CATALOG_SYNC_MODE_INCREMENTAL,
    CATALOG_SUPPORTED_PLATFORMS,
    PlatformProductCatalogItem,
    _normalize_platform,
    calculate_suggested_price,
    cache_catalog_main_image,
    catalog_main_image_display_url,
    catalog_main_image_url_from_payload,
    recalculate_catalog_item,
    synchronize_platform_catalog,
    upsert_catalog_item,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kw):
    return "JSON"


def test_calculate_suggested_price_includes_shipping_commission_and_target_margin():
    shipping, suggested = calculate_suggested_price(
        cost_cny=Decimal("30"),
        weight_kg=Decimal("0.2"),
        commission_rate=Decimal("0.12"),
        base_shipping_fee_cny=Decimal("11"),
        shipping_fee_per_kg_cny=Decimal("0.04"),
        target_margin_rate=Decimal("0.20"),
        price_increment_cny=Decimal("0.01"),
    )

    assert shipping == Decimal("11.008")
    assert suggested == Decimal("60.31")


def test_calculate_suggested_price_rejects_non_positive_price_denominator():
    with pytest.raises(ValueError, match="小于 100%"):
        calculate_suggested_price(
            cost_cny=Decimal("10"),
            weight_kg=Decimal("0"),
            commission_rate=Decimal("0.60"),
            base_shipping_fee_cny=Decimal("0"),
            shipping_fee_per_kg_cny=Decimal("0"),
            target_margin_rate=Decimal("0.40"),
            price_increment_cny=Decimal("0.01"),
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("allegro", "allegro"),
        ("dmsmatrix", "dmsmatrix"),
        ("wb", "wildberries"),
        ("JOOM", "joom_logistics"),
        ("mkd", "mercadolibre"),
        ("ozon", "ozon"),
    ],
)
def test_catalog_platform_aliases_are_normalized(value, expected):
    assert _normalize_platform(value) == expected


def test_catalog_sync_platforms_match_implemented_connectors():
    assert CATALOG_SUPPORTED_PLATFORMS == {"ozon", "wildberries", "mercadolibre", "joom_logistics", "allegro", "dmsmatrix"}


def test_catalog_main_image_url_extracts_common_payload_shapes():
    assert catalog_main_image_url_from_payload({"mainImageUrl": "https://example.test/main.jpg"}) == "https://example.test/main.jpg"
    assert catalog_main_image_url_from_payload({"pictures": [{"source": "https://example.test/picture.jpg"}]}) == "https://example.test/picture.jpg"
    assert catalog_main_image_url_from_payload({"raw_payload": {"images": ["https://example.test/image.jpg"]}}) == "https://example.test/image.jpg"
    assert catalog_main_image_url_from_payload({"info": {"primary_image": ["https://example.test/ozon.jpg"]}}) == "https://example.test/ozon.jpg"
    assert catalog_main_image_url_from_payload({"product": {"mainImage": {"origUrl": "https://example.test/joom.jpg"}}}) == "https://example.test/joom.jpg"
    assert catalog_main_image_url_from_payload({"card": {"photos": [{"big": "https://example.test/wb.webp"}]}}) == "https://example.test/wb.webp"
    assert catalog_main_image_url_from_payload({"raw_payload": {"ItemImage": "https://example.test/dms.jpg"}}) == "https://example.test/dms.jpg"
    assert catalog_main_image_url_from_payload({"image": "not-a-renderable-image-id"}) == ""


def test_cache_catalog_main_image_downloads_to_local_storage(monkeypatch, tmp_path):
    payload = {"main_image_url": "https://cdn.example.test/products/main.png"}

    monkeypatch.setattr("app.platform_product_catalog.get_settings", lambda: SimpleNamespace(label_storage_path=tmp_path))
    monkeypatch.setattr(
        "app.platform_product_catalog.download_network_image",
        lambda url: (b"image-bytes", "image/png", url),
    )

    changed = cache_catalog_main_image(payload)

    assert changed is True
    assert payload[CATALOG_MAIN_IMAGE_SOURCE_URL_KEY] == "https://cdn.example.test/products/main.png"
    assert payload[CATALOG_MAIN_IMAGE_LOCAL_URL_KEY].startswith(CATALOG_MAIN_IMAGE_URL_PREFIX)
    assert catalog_main_image_display_url(payload) == payload[CATALOG_MAIN_IMAGE_LOCAL_URL_KEY]
    image_path = tmp_path / CATALOG_MAIN_IMAGE_DIR_NAME / payload[CATALOG_MAIN_IMAGE_FILE_KEY]
    assert image_path.read_bytes() == b"image-bytes"


def test_cache_catalog_main_image_reuses_existing_file_for_source(monkeypatch, tmp_path):
    source_url = "https://cdn.example.test/products/reused.jpg"
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:20]
    image_dir = tmp_path / CATALOG_MAIN_IMAGE_DIR_NAME
    image_dir.mkdir(parents=True)
    existing_path = image_dir / f"{digest}_reused.jpg"
    existing_path.write_bytes(b"cached")

    monkeypatch.setattr("app.platform_product_catalog.get_settings", lambda: SimpleNamespace(label_storage_path=tmp_path))
    monkeypatch.setattr(
        "app.platform_product_catalog.download_network_image",
        lambda _url: (_ for _ in ()).throw(AssertionError("existing cache should be reused")),
    )
    payload = {"main_image_url": source_url}

    changed = cache_catalog_main_image(payload)

    assert changed is True
    assert payload[CATALOG_MAIN_IMAGE_FILE_KEY] == existing_path.name
    assert payload[CATALOG_MAIN_IMAGE_LOCAL_URL_KEY] == f"{CATALOG_MAIN_IMAGE_URL_PREFIX}{existing_path.name}"


def test_catalog_main_image_display_url_recovers_existing_cache_without_metadata(monkeypatch, tmp_path):
    source_url = "https://cdn.example.test/products/recovered.jpg"
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:20]
    image_dir = tmp_path / CATALOG_MAIN_IMAGE_DIR_NAME
    image_dir.mkdir(parents=True)
    existing_path = image_dir / f"{digest}_recovered.jpg"
    existing_path.write_bytes(b"cached")

    monkeypatch.setattr("app.platform_product_catalog.get_settings", lambda: SimpleNamespace(label_storage_path=tmp_path))

    assert catalog_main_image_display_url({"main_image_url": source_url}) == (
        f"{CATALOG_MAIN_IMAGE_URL_PREFIX}{existing_path.name}"
    )


def test_catalog_upsert_keeps_zero_sellable_stock_and_zero_price(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []

        def scalar(self, _statement):
            return None

        def add(self, value):
            self.added.append(value)

    monkeypatch.setattr("app.platform_product_catalog.recalculate_catalog_item", lambda *_args, **_kwargs: None)
    db = FakeSession()
    item = upsert_catalog_item(
        db,
        SimpleNamespace(id=1, platform="ozon"),
        {
            "platform_product_id": "1001",
            "platform_sku": "SKU-1001",
            "available_stock": 0,
            "stock": 99,
            "price_amount": 0,
            "price": 99,
            "price_currency": "RUB",
        },
        synced_at=datetime(2026, 7, 30, 12, 0, 0),
    )

    assert item.available_stock == 0
    assert item.price_amount == Decimal("0")
    assert item.price_currency == "RUB"


def test_catalog_upsert_preserves_normalized_main_image_with_nested_raw_payload(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []

        def scalar(self, _statement):
            return None

        def add(self, value):
            self.added.append(value)

    monkeypatch.setattr("app.platform_product_catalog.recalculate_catalog_item", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.platform_product_catalog.cache_catalog_main_image",
        lambda payload, source_url=None: payload.update(
            {
                CATALOG_MAIN_IMAGE_FILE_KEY: "cached-main.jpg",
                CATALOG_MAIN_IMAGE_LOCAL_URL_KEY: f"{CATALOG_MAIN_IMAGE_URL_PREFIX}cached-main.jpg",
            }
        )
        is None,
    )
    item = upsert_catalog_item(
        FakeSession(),
        SimpleNamespace(id=1, platform="ozon"),
        {
            "platform_product_id": "1001",
            "platform_sku": "SKU-1001",
            "main_image_url": "https://example.test/main.jpg",
            "raw_payload": {"id": "1001", "name": "Raw product"},
        },
        synced_at=datetime(2026, 7, 30, 12, 0, 0),
    )

    assert item.raw_payload["main_image_url"] == "https://example.test/main.jpg"
    assert item.raw_payload[CATALOG_MAIN_IMAGE_LOCAL_URL_KEY] == f"{CATALOG_MAIN_IMAGE_URL_PREFIX}cached-main.jpg"


def test_catalog_upsert_reuses_pending_item_for_duplicate_identity(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []

        def scalar(self, _statement):
            return None

        def add(self, value):
            self.added.append(value)

    monkeypatch.setattr("app.platform_product_catalog.recalculate_catalog_item", lambda *_args, **_kwargs: None)
    db = FakeSession()
    cache = {}
    shop = SimpleNamespace(id=1, platform="ozon")

    first = upsert_catalog_item(
        db,
        shop,
        {
            "platform_product_id": "1001",
            "platform_sku": "SKU-1001",
            "warehouse_code": "",
            "available_stock": 1,
            "price_amount": 100,
            "price_currency": "RUB",
        },
        synced_at=datetime(2026, 7, 30, 12, 0, 0),
        cache=cache,
    )
    second = upsert_catalog_item(
        db,
        shop,
        {
            "platform_product_id": "1001",
            "platform_sku": "SKU-1001",
            "warehouse_code": "",
            "available_stock": 7,
            "price_amount": 101,
            "price_currency": "RUB",
        },
        synced_at=datetime(2026, 7, 30, 12, 5, 0),
        cache=cache,
    )

    assert first is second
    assert len(db.added) == 1
    assert second.available_stock == 7
    assert second.price_amount == Decimal("101")


def test_catalog_incremental_sync_preserves_missing_rows_and_uses_cursor(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformAccount.__table__,
            PlatformProductCatalogItem.__table__,
            SyncCursor.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    class FakeConnector:
        def __init__(self):
            self.calls = []

        async def fetch_platform_products(self, since=None):
            self.calls.append(since)
            return [
                {
                    "platform_product_id": "P-1",
                    "platform_sku": "SKU-1",
                    "product_name": "Product 1",
                    "available_stock": 5,
                    "price_amount": "10.00",
                    "price_currency": "CNY",
                }
            ]

    connector = FakeConnector()
    monkeypatch.setattr("app.platform_product_catalog._product_mapping", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.platform_product_catalog.recalculate_catalog_item", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.sync_engine._connector_for_account", lambda *_args, **_kwargs: connector)

    with session_factory() as db:
        shop = PlatformAccount(
            platform="ozon",
            account_id="shop-1",
            display_name="Ozon Shop",
            enabled=True,
            encrypted_credentials=b"token",
        )
        db.add(shop)
        db.commit()

        first_result = asyncio.run(synchronize_platform_catalog(db, mode=CATALOG_SYNC_MODE_FULL))
        assert first_result["success"] == 1
        assert connector.calls == [None]

        stale_item = PlatformProductCatalogItem(
            shop_id=shop.id,
            platform="ozon",
            platform_product_id="STALE",
            platform_sku="DEMO-SKU-0023",
            product_name="Stale Product",
            last_seen_at=datetime(2026, 7, 1, 0, 0, 0),
            is_active=True,
        )
        db.add(stale_item)
        db.commit()

        second_result = asyncio.run(synchronize_platform_catalog(db, mode=CATALOG_SYNC_MODE_FULL))
        assert second_result["success"] == 1
        db.expire_all()
        stale_after_full = db.scalar(
            select(PlatformProductCatalogItem).where(PlatformProductCatalogItem.platform_product_id == "STALE")
        )
        assert stale_after_full is not None
        assert stale_after_full.is_active is False

        stale_after_full.is_active = True
        db.commit()
        full_cursor = db.scalar(
            select(SyncCursor).where(
                SyncCursor.platform == "ozon",
                SyncCursor.account_id == "shop-1",
                SyncCursor.cursor_key == CATALOG_SYNC_CURSOR_KEY_FULL,
            )
        )
        assert full_cursor is not None
        expected_since = datetime.fromisoformat(full_cursor.cursor_value)

        incremental_result = asyncio.run(synchronize_platform_catalog(db, mode=CATALOG_SYNC_MODE_INCREMENTAL))
        assert incremental_result["success"] == 1
        assert connector.calls[-1] == expected_since
        db.expire_all()
        stale_after_incremental = db.scalar(
            select(PlatformProductCatalogItem).where(PlatformProductCatalogItem.platform_product_id == "STALE")
        )
        assert stale_after_incremental is not None
        assert stale_after_incremental.is_active is True


def test_catalog_recalculate_uses_latest_system_exchange_rate_when_today_is_missing():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ExchangeRate.__table__,
            PlatformProductCatalogItem.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        db.add_all(
            [
                ExchangeRate(
                    rate_date=datetime(2026, 7, 30, 0, 0, 0).date(),
                    currency_code="USD",
                    currency_name="美元",
                    rate=Decimal("6.80"),
                    synced_at=datetime(2026, 7, 30, 3, 0, 0),
                    updated_at=datetime(2026, 7, 30, 3, 0, 0),
                ),
                PlatformProductCatalogItem(
                    shop_id=1,
                    platform="ozon",
                    platform_product_id="P-1",
                    platform_sku="SKU-1",
                    product_name="Product 1",
                    price_currency="USD",
                    price_amount=Decimal("10.00"),
                ),
            ]
        )
        db.commit()

        item = db.scalar(select(PlatformProductCatalogItem).where(PlatformProductCatalogItem.platform_product_id == "P-1"))
        assert item is not None
        recalculate_catalog_item(db, item, today=datetime(2026, 7, 31, 0, 0, 0).date())

        assert item.exchange_rate == Decimal("6.80")
        assert item.exchange_rate_date == datetime(2026, 7, 30, 0, 0, 0).date()
        assert item.calculation_status == "missing_mapping"
