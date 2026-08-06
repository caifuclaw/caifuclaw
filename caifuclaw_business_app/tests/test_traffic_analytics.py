# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

import app.traffic_analytics as traffic_module
from app.connector_client import ConnectorRuntimeError
from app.models import TrafficMetric, TrafficSyncRun
from app.traffic_analytics import previous_period, validate_period, validate_sync_period


def test_joom_transaction_id_is_used_for_local_order_stats() -> None:
    account = SimpleNamespace(platform="joom_logistics", account_id="JOOM-DEMO-001")
    order = SimpleNamespace(
        id=1,
        platform_order_id="DEMO-ORDER-0130",
        raw_payload={"transactionId": "transaction-1"},
    )

    assert traffic_module._local_order_stat_key(account, order) == "transaction:transaction-1"


def test_non_joom_local_order_stats_keep_platform_order_id() -> None:
    account = SimpleNamespace(platform="ozon", account_id="OZON-1")
    order = SimpleNamespace(id=1, platform_order_id="DEMO-ORDER-0017", raw_payload={})

    assert traffic_module._local_order_stat_key(account, order) == "DEMO-ORDER-0017"


@pytest.fixture
def traffic_db():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE traffic_metrics (
                platform_account_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                account_id TEXT NOT NULL,
                shop_name TEXT NOT NULL,
                source TEXT NOT NULL,
                grain TEXT NOT NULL,
                stat_date DATE NOT NULL,
                period_start DATE NOT NULL,
                period_end DATE NOT NULL,
                region TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                product_name TEXT NOT NULL,
                impressions BIGINT,
                clicks BIGINT,
                add_to_cart BIGINT,
                orders BIGINT,
                buyers BIGINT,
                units_sold BIGINT,
                negative_reviews BIGINT,
                revenue NUMERIC,
                currency TEXT NOT NULL,
                raw_data JSON NOT NULL,
                synced_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, internal_name TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE product_shop_mappings (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL,
                shop_id INTEGER NOT NULL,
                shop_sku TEXT NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    with Session(engine) as session:
        yield session


def insert_traffic_rows(db: Session, rows: list[dict]) -> None:
    defaults = {
        "shop_name": "Test shop",
        "source": "organic",
        "grain": "daily",
        "stat_date": "2026-07-07",
        "period_start": "2026-07-07",
        "period_end": "2026-07-07",
        "region": "",
        "entity_type": "sku",
        "product_name": "",
        "impressions": None,
        "clicks": None,
        "add_to_cart": None,
        "orders": None,
        "buyers": None,
        "units_sold": None,
        "negative_reviews": None,
        "revenue": None,
        "currency": "",
        "raw_data": {},
        "synced_at": "2026-07-14 00:00:00",
    }
    values = [{**defaults, **row} for row in rows]
    for value in values:
        if isinstance(value.get("revenue"), Decimal):
            value["revenue"] = float(value["revenue"])
        value["raw_data"] = json.dumps(value.get("raw_data") or {})
    db.execute(
        text(
            """
            INSERT INTO traffic_metrics (
                platform_account_id, platform, account_id, shop_name, source, grain,
                stat_date, period_start, period_end, region, entity_type, entity_id,
                sku, product_name, impressions, clicks, add_to_cart, orders, buyers,
                units_sold, negative_reviews, revenue, currency, raw_data, synced_at
            ) VALUES (
                :platform_account_id, :platform, :account_id, :shop_name, :source, :grain,
                :stat_date, :period_start, :period_end, :region, :entity_type, :entity_id,
                :sku, :product_name, :impressions, :clicks, :add_to_cart, :orders, :buyers,
                :units_sold, :negative_reviews, :revenue, :currency, :raw_data, :synced_at
            )
            """
        ),
        values,
    )
    db.commit()


def test_previous_period_uses_same_number_of_complete_days():
    assert previous_period(date(2026, 7, 6), date(2026, 7, 12)) == (
        date(2026, 6, 29),
        date(2026, 7, 5),
    )


def test_traffic_timestamps_identify_naive_database_values_as_utc():
    assert traffic_module._utc_iso(datetime(2026, 7, 13, 19, 32)) == "2026-07-13T19:32:00Z"
    aware = datetime(2026, 7, 13, 19, 32, tzinfo=timezone.utc)
    assert traffic_module._utc_iso(aware) == "2026-07-13T19:32:00+00:00"


def test_traffic_accounts_report_latest_period_freshness():
    expected_end = date.today() - timedelta(days=1)
    expected_start = expected_end - timedelta(days=29)
    account = SimpleNamespace(
        id=4,
        platform="mercadolibre",
        account_id="mercado-demo",
        display_name="Mercado shop",
        enabled=True,
        authorization_status="authorized",
    )

    class FakeDb:
        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [account])

        def scalar(self, _statement):
            return None

        def execute(self, _statement):
            return SimpleNamespace(
                first=lambda: (expected_start, expected_end, datetime(2026, 7, 28, 10, 0))
            )

    result = traffic_module.list_traffic_accounts(FakeDb())

    assert result[0]["latest_period_start"] == expected_start.isoformat()
    assert result[0]["latest_period_end"] == expected_end.isoformat()
    assert result[0]["data_freshness"] == "fresh"


def test_mercado_partial_sync_message_lists_only_incomplete_current_sites():
    rows = [
        {
            "period_start": "2026-07-21",
            "period_end": "2026-07-27",
            "region": "MLB",
            "raw_data": {
                "traffic_sync_status": "partial",
                "traffic_expected_items": 20,
                "traffic_received_items": 18,
                "traffic_missing_items": 2,
            },
        },
        {
            "period_start": "2026-07-21",
            "period_end": "2026-07-27",
            "region": "MLM",
            "raw_data": {
                "traffic_sync_status": "full",
                "traffic_expected_items": 10,
                "traffic_received_items": 10,
                "traffic_missing_items": 0,
            },
        },
        {
            "period_start": "2026-07-14",
            "period_end": "2026-07-20",
            "region": "MLC",
            "raw_data": {
                "traffic_sync_status": "partial",
                "traffic_expected_items": 5,
                "traffic_received_items": 4,
                "traffic_missing_items": 1,
            },
        },
    ]

    message = traffic_module._mercado_partial_sync_message(
        rows,
        date(2026, 7, 21),
        date(2026, 7, 27),
    )

    assert message == (
        "美客多访问量部分成功：MLB 本期已获取 18/20，缺少 2；"
        "MLC 上期已获取 4/5，缺少 1"
    )
    assert traffic_module._mercado_partial_period_regions(rows) == {
        (date(2026, 7, 21), date(2026, 7, 27), "MLB"),
        (date(2026, 7, 14), date(2026, 7, 20), "MLC"),
    }


def test_partial_mercado_replace_preserves_existing_incomplete_site(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "mercadolibre",
                "platform_account_id": 4,
                "account_id": "mercado-demo",
                "grain": "date_range",
                "stat_date": "2026-07-27",
                "period_start": "2026-07-21",
                "period_end": "2026-07-27",
                "region": "MLB",
                "entity_id": "MLB-1",
                "sku": "DEMO-SKU-0025",
                "clicks": 120,
            },
            {
                "platform": "mercadolibre",
                "platform_account_id": 4,
                "account_id": "mercado-demo",
                "grain": "date_range",
                "stat_date": "2026-07-27",
                "period_start": "2026-07-21",
                "period_end": "2026-07-27",
                "region": "MLM",
                "entity_id": "MLM-1",
                "sku": "DEMO-SKU-0026",
                "clicks": 80,
            },
        ],
    )
    account = SimpleNamespace(id=4)

    traffic_module._replace_period_metrics(
        traffic_db,
        account,
        [],
        date(2026, 7, 14),
        date(2026, 7, 27),
        preserve_period_regions={(date(2026, 7, 21), date(2026, 7, 27), "MLB")},
    )
    traffic_db.commit()

    remaining = traffic_db.execute(
        text("SELECT region, clicks FROM traffic_metrics ORDER BY region")
    ).all()
    assert remaining == [("MLB", 120)]


def test_validate_period_rejects_today_but_allows_longer_queries():
    with pytest.raises(ValueError, match="完整日期"):
        validate_period(date.today(), date.today())

    assert validate_period(date(2026, 5, 1), date(2026, 6, 1)) == (
        date(2026, 5, 1),
        date(2026, 6, 1),
    )


def test_validate_sync_period_rejects_ranges_over_31_days():
    with pytest.raises(ValueError, match="最多支持31天"):
        validate_sync_period(date(2026, 5, 1), date(2026, 6, 1))


def test_joom_capability_uses_product_ranking_metrics():
    capability = traffic_module.SUPPORTED_TRAFFIC_PLATFORMS["joom_logistics"]

    assert capability["scope"] == "平台全量商品流量"
    assert capability["grain"] == "最近7/14/28天"
    assert "units_sold" in capability["metrics"]
    assert "revenue" in capability["metrics"]
    assert "Product Ranking" in capability["note"]


def test_all_traffic_capabilities_include_buyer_and_units_metrics():
    for capability in traffic_module.SUPPORTED_TRAFFIC_PLATFORMS.values():
        assert "buyers" in capability["metrics"]
        assert "units_sold" in capability["metrics"]
        assert "negative_reviews" in capability["metrics"]


def test_local_order_metrics_fill_missing_values_and_preserve_platform_units(monkeypatch):
    monkeypatch.setattr(
        traffic_module,
        "_local_order_groups",
        lambda *_args, **_kwargs: {
            (date(2026, 7, 8), "", "sku-1"): {
                "buyer_ids": {"BUYER-1"},
                "units_sold": 2,
                "revenue": Decimal("20"),
                "has_revenue": True,
                "currencies": {"USD"},
            },
            (date(2026, 7, 9), "", "sku-1"): {
                "buyer_ids": {"BUYER-1", "order:ORDER-2"},
                "units_sold": 3,
                "revenue": Decimal("35"),
                "has_revenue": True,
                "currencies": {"USD"},
            },
        },
    )
    rows = [
        {
            "entity_type": "sku",
            "sku": "SKU-1",
            "period_start": "2026-07-08",
            "period_end": "2026-07-14",
            "buyers": None,
            "units_sold": None,
            "revenue": None,
            "currency": "",
            "raw_data": {},
        },
        {
            "entity_type": "sku",
            "sku": "sku-1",
            "period_start": "2026-07-08",
            "period_end": "2026-07-14",
            "buyers": None,
            "units_sold": 8,
            "revenue": Decimal("80"),
            "currency": "USD",
            "raw_data": {"metric_source": "platform_report"},
        },
        {
            "entity_type": "sku",
            "sku": "DEMO-SKU-0027",
            "period_start": "2026-07-08",
            "period_end": "2026-07-14",
            "buyers": None,
            "units_sold": None,
            "orders": 0,
            "revenue": None,
            "currency": "",
            "raw_data": {},
        },
        {
            "entity_type": "shop",
            "sku": "",
            "period_start": "2026-07-08",
            "period_end": "2026-07-14",
            "buyers": None,
            "units_sold": None,
            "raw_data": {},
        },
    ]

    result = traffic_module._merge_local_order_metrics(
        None,
        SimpleNamespace(platform="ozon", account_id="ozon-demo"),
        rows,
        date(2026, 7, 8),
        date(2026, 7, 14),
    )

    assert result[0]["buyers"] == 2
    assert result[0]["units_sold"] == 5
    assert result[0]["revenue"] == Decimal("55")
    assert result[0]["currency"] == "USD"
    assert result[0]["raw_data"]["units_sold_source"] == "local_orders"
    assert result[0]["raw_data"]["revenue_source"] == "local_orders"
    assert result[1]["buyers"] == 2
    assert result[1]["units_sold"] == 8
    assert result[1]["revenue"] == Decimal("80")
    assert result[1]["raw_data"] == {
        "metric_source": "platform_report",
        "orders_source": "platform",
        "buyers_source": "local_orders",
        "units_sold_source": "platform",
        "revenue_source": "platform",
    }
    assert result[2]["buyers"] == 0
    assert result[2]["units_sold"] == 0
    assert result[2]["revenue"] == Decimal("0")
    assert result[2]["currency"] == "USD"
    assert result[2]["raw_data"]["revenue_source"] == "no_sales"
    assert result[3]["buyers"] == 0
    assert result[3]["units_sold"] == 0
    assert result[3]["raw_data"]["buyers_source"] == "not_applicable"


def test_joom_local_order_match_uses_parent_product_id():
    item = SimpleNamespace(
        sku="DEMO-SKU-0028",
        raw_payload={
            "product_id": "PRODUCT-1",
            "raw_payload": {"id": "PRODUCT-1", "sku": "DEMO-SKU-0029"},
        },
    )

    assert traffic_module._local_order_product_id(item) == "PRODUCT-1"
    assert traffic_module._local_order_match_key(
        SimpleNamespace(platform="joom_logistics"), item
    ) == "product-1"
    assert traffic_module._local_order_match_key(
        SimpleNamespace(platform="ozon"), item
    ) == "demo-sku-0028"


def test_allegro_local_order_match_uses_offer_id():
    item = SimpleNamespace(
        sku="DEMO-SKU-0030",
        raw_payload={
            "offer_id": "OFFER-1",
            "raw_payload": {"offer": {"id": "OFFER-1"}},
        },
    )

    assert traffic_module._local_order_offer_id(item) == "OFFER-1"
    assert traffic_module._local_order_match_key(
        SimpleNamespace(platform="allegro"), item
    ) == "offer-1"


def test_allegro_local_revenue_is_scoped_to_marketplace(monkeypatch):
    monkeypatch.setattr(
        traffic_module,
        "_local_order_groups",
        lambda *_args, **_kwargs: {
            (date(2026, 7, 8), "ALLEGRO-PL", "offer-1"): {
                "order_ids": {"ORDER-1"},
                "buyer_ids": {"BUYER-1"},
                "units_sold": 1,
                "revenue": Decimal("99.50"),
                "has_revenue": True,
                "currencies": {"PLN"},
            },
        },
    )
    rows = [
        {
            "entity_type": "sku",
            "entity_id": "OFFER-1",
            "sku": "DEMO-SKU-0030",
            "region": "allegro-pl",
            "period_start": "2026-07-08",
            "period_end": "2026-07-14",
            "orders": 1,
            "buyers": None,
            "units_sold": 1,
            "revenue": None,
            "currency": "",
            "raw_data": {},
        },
        {
            "entity_type": "sku",
            "entity_id": "OFFER-1",
            "sku": "DEMO-SKU-0030",
            "region": "allegro-cz",
            "period_start": "2026-07-08",
            "period_end": "2026-07-14",
            "orders": 0,
            "buyers": None,
            "units_sold": 0,
            "revenue": None,
            "currency": "",
            "raw_data": {},
        },
    ]

    result = traffic_module._merge_local_order_metrics(
        None,
        SimpleNamespace(platform="allegro", account_id="allegro-demo"),
        rows,
        date(2026, 7, 8),
        date(2026, 7, 14),
    )

    assert result[0]["buyers"] == 1
    assert result[0]["orders"] == 1
    assert result[0]["units_sold"] == 1
    assert result[0]["revenue"] == Decimal("99.50")
    assert result[0]["currency"] == "PLN"
    assert result[0]["raw_data"]["revenue_source"] == "local_orders"
    assert result[0]["raw_data"]["orders_source"] == "local_orders"
    assert result[1]["buyers"] == 0
    assert result[1]["revenue"] == Decimal("0")
    assert result[1]["currency"] == "PLN"
    assert result[1]["raw_data"]["revenue_source"] == "no_sales"


def test_traffic_query_indexes_match_read_and_sync_filters():
    metric_indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in TrafficMetric.__table__.indexes
    }
    sync_run_indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in TrafficSyncRun.__table__.indexes
    }

    assert metric_indexes["ix_traffic_metrics_grain_stat_date"] == ("grain", "stat_date")
    assert metric_indexes["ix_traffic_metrics_account_grain_stat_date"] == (
        "platform_account_id",
        "grain",
        "stat_date",
    )
    assert metric_indexes["ix_traffic_metrics_grain_period_account"] == (
        "grain",
        "period_start",
        "period_end",
        "platform_account_id",
    )
    assert sync_run_indexes["ix_traffic_sync_runs_account_latest"] == (
        "platform_account_id",
        "id",
    )
    assert {"buyers", "units_sold", "negative_reviews"}.issubset(TrafficMetric.__table__.columns.keys())


def test_mercado_order_dimensions_use_local_item_region_and_timezone():
    order = SimpleNamespace(site="CBT", country_code="BR")
    item = SimpleNamespace(
        raw_payload={"raw_payload": {"item": {"id": "MLB0000000001", "parent_item_id": "CBT0000000001"}}}
    )

    assert traffic_module._mercado_order_region(order) == "MLB"
    assert traffic_module._mercado_local_item_id(item) == "MLB0000000001"
    assert traffic_module._mercado_local_date(datetime(2026, 7, 7, 2, 30), "MLB") == date(2026, 7, 6)


def test_mercado_orders_merge_by_local_item_id_and_keep_distinct_metrics(monkeypatch):
    monkeypatch.setattr(
        traffic_module,
        "_mercado_order_groups",
        lambda *_args, **_kwargs: {
            (date(2026, 7, 7), "MLB", "MLB1"): {
                "order_ids": {"ORDER-1", "ORDER-2"},
                "buyer_ids": {"BUYER-1"},
                "skus": {"SELLER-SKU-1"},
                "units_sold": 3,
                "revenue": Decimal("119.97"),
                "has_revenue": True,
                "currencies": {"USD"},
                "product_name": "Localized product",
            }
        },
    )
    rows = [
        {
            "period_start": "2026-07-07",
            "period_end": "2026-07-13",
            "stat_date": "2026-07-13",
            "region": "MLB",
            "entity_id": "MLB1",
            "entity_type": "sku",
            "sku": "DEMO-SKU-0031",
            "product_name": "Parent product",
            "source": "organic",
            "grain": "date_range",
            "clicks": 100,
            "negative_reviews": 2,
            "raw_data": {"parent_item_id": "CBT1"},
        },
        {
            "period_start": "2026-07-07",
            "period_end": "2026-07-13",
            "stat_date": "2026-07-13",
            "region": "MLB",
            "entity_id": "MLB2",
            "entity_type": "sku",
            "sku": "SELLER-SKU-2",
            "product_name": "No sales",
            "source": "organic",
            "grain": "date_range",
            "clicks": 20,
            "negative_reviews": 0,
            "raw_data": {},
        },
    ]

    result = traffic_module._merge_mercado_orders(
        None,
        SimpleNamespace(platform="mercadolibre", account_id="mercado-demo"),
        rows,
        date(2026, 7, 7),
        date(2026, 7, 13),
    )

    assert len(result) == 2
    assert result[0]["sku"] == "SELLER-SKU-1"
    assert result[0]["orders"] == 2
    assert result[0]["buyers"] == 1
    assert result[0]["units_sold"] == 3
    assert result[0]["revenue"] == Decimal("119.97")
    assert result[0]["currency"] == "USD"
    assert result[0]["negative_reviews"] == 2
    assert result[1]["orders"] == 0
    assert result[1]["buyers"] == 0
    assert result[1]["units_sold"] == 0
    assert result[1]["revenue"] == Decimal("0")


def test_traffic_records_support_multiple_platform_shop_and_region_filters():
    rows = traffic_module._filtered_metric_rows(
        date(2026, 7, 7),
        date(2026, 7, 13),
        include_rolling=True,
        platform=["OZON", "wildberries", "ozon"],
        platform_account_id=[2, 1, 2],
        region=["ru", "MLB", "RU"],
    )

    bound_values = list(select(rows).compile().params.values())
    assert ["ozon", "wildberries"] in bound_values
    assert [1, 2] in bound_values
    assert ["MLB", "RU"] in bound_values


def test_daily_negative_review_materialization_and_query_ignore_period_rows(traffic_db):
    period_row = {
        "platform": "joom_logistics",
        "platform_account_id": 3,
        "account_id": "joom-demo",
        "shop_name": "Joom shop",
        "source": "platform",
        "grain": "date_range",
        "stat_date": "2026-07-13",
        "period_start": "2026-07-07",
        "period_end": "2026-07-13",
        "region": "",
        "entity_type": "sku",
        "entity_id": "JOOM-1",
        "sku": "SKU-1",
        "product_name": "Product",
        "negative_reviews": 3,
        "raw_data": {
            "negative_reviews_source": "joom_reviews",
            "negative_reviews_daily": {"2026-07-07": 1, "2026-07-09": 2},
        },
    }
    daily_rows = traffic_module._materialize_daily_negative_review_rows([period_row])

    assert len(daily_rows) == 3
    assert [row["stat_date"] for row in daily_rows[1:]] == ["2026-07-07", "2026-07-09"]
    assert [row["negative_reviews"] for row in daily_rows[1:]] == [1, 2]
    assert daily_rows[1]["raw_data"]["derivation_method"] == "review_date"

    insert_traffic_rows(
        traffic_db,
        [
            period_row,
            *[
                {
                    **row,
                    "platform_account_id": 3,
                    "platform": "joom_logistics",
                    "account_id": "joom-demo",
                    "shop_name": "Joom shop",
                }
                for row in daily_rows[1:]
            ],
        ],
    )
    result = traffic_module.query_negative_reviews_daily(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 7),
        platform="joom_logistics",
    )

    assert result["grain"] == "daily"
    assert result["fallback_periods"] == []
    assert len(result["items"]) == 1
    assert result["items"][0]["negative_reviews"] == 1
    assert result["items"][0]["grain"] == "daily"


def test_rankings_return_global_top_rows_across_platforms(traffic_db):
    rows = []
    for platform in ("ozon", "allegro"):
        for value in range(1, 5):
            rows.append(
                {
                    "platform": platform,
                    "platform_account_id": 1 if platform == "ozon" else 2,
                    "account_id": platform,
                    "shop_name": platform,
                    "entity_id": f"{platform}-{value}",
                    "sku": f"SKU-{value}",
                    "product_name": f"Product {value}",
                    "impressions": value,
                    "clicks": value * 2 if platform == "ozon" else value * 2 - 1,
                    "add_to_cart": 5 - value,
                    "orders": value,
                }
            )
    insert_traffic_rows(traffic_db, rows)
    traffic_db.execute(text("INSERT INTO products (id, internal_name) VALUES (1, '中文商品名称')"))
    traffic_db.execute(
        text(
            """
            INSERT INTO product_shop_mappings (
                id, product_id, shop_id, shop_sku, created_at, updated_at
            ) VALUES (1, 1, 1, 'sku-4', '2026-07-01 00:00:00', '2026-07-02 00:00:00')
            """
        )
    )
    traffic_db.commit()

    result = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="clicks",
        limit=2,
    )

    assert result["rank_scope"] == "global"
    assert [(item["platform"], item["rank"]) for item in result["items"]] == [
        ("ozon", 1),
        ("allegro", 2),
    ]
    assert [item["clicks"] for item in result["items"]] == [8, 7]
    assert result["items"][0]["product_name"] == "中文商品名称"
    assert result["items"][1]["product_name"] == "Product 4"

    cart_result = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="add_to_cart",
        limit=1,
    )

    assert [item["add_to_cart"] for item in cart_result["items"]] == [4]
    assert [item["platform"] for item in cart_result["items"]] == ["allegro"]
    assert [item["sku"] for item in cart_result["items"]] == ["SKU-1"]


def test_rankings_sort_rates_across_all_matching_skus_before_limiting(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "ozon",
                "entity_id": f"ozon-{sku}",
                "sku": sku,
                "impressions": impressions,
                "clicks": clicks,
                "orders": orders,
            }
            for sku, impressions, clicks, orders in (
                ("MOST-CLICKS", 1000, 100, 5),
                ("BEST-CTR", 100, 90, 9),
                ("SECOND-CTR", 100, 80, 40),
                ("NO-RATE", 100, None, None),
            )
        ],
    )

    ctr_desc = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="ctr",
        sort_order="desc",
        limit=2,
    )
    ctr_asc = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="ctr",
        sort_order="asc",
        limit=2,
    )
    cvr_desc = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="cvr",
        sort_order="desc",
        limit=2,
    )
    cvr_asc = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="cvr",
        sort_order="asc",
        limit=4,
    )

    assert ctr_desc["sort_order"] == "desc"
    assert [item["sku"] for item in ctr_desc["items"]] == ["BEST-CTR", "SECOND-CTR"]
    assert [item["rank"] for item in ctr_desc["items"]] == [1, 2]
    assert [item["sku"] for item in ctr_asc["items"]] == ["MOST-CLICKS", "SECOND-CTR"]
    assert [item["sku"] for item in cvr_desc["items"]] == ["SECOND-CTR", "BEST-CTR"]
    assert [item["sku"] for item in cvr_asc["items"]] == [
        "MOST-CLICKS",
        "BEST-CTR",
        "SECOND-CTR",
        "NO-RATE",
    ]


@pytest.mark.parametrize(
    ("metric", "sort_order", "message"),
    (("unknown", "desc", "排行指标不受支持"), ("ctr", "sideways", "排行排序方向不受支持")),
)
def test_rankings_reject_unsupported_metric_or_sort_order(traffic_db, metric, sort_order, message):
    with pytest.raises(ValueError, match=message):
        traffic_module.query_rankings(
            traffic_db,
            date(2026, 7, 7),
            date(2026, 7, 13),
            metric=metric,
            sort_order=sort_order,
            limit=20,
        )


def test_rankings_calculate_sales_share_within_shop_region(traffic_db):
    rows = [
        {
            "platform": "mercadolibre",
            "platform_account_id": 4,
            "account_id": "mercado-demo",
            "shop_name": "Mercado shop",
            "grain": "date_range",
            "region": "MLB",
            "entity_id": f"MLB-{index}",
            "sku": f"SKU-{index}",
            "product_name": f"Product {index}",
            "clicks": clicks,
            "orders": orders,
            "buyers": orders,
            "units_sold": orders,
            "negative_reviews": 0,
            "revenue": revenue,
            "currency": "USD",
            "stat_date": "2026-07-13",
            "period_start": "2026-07-07",
            "period_end": "2026-07-13",
        }
        for index, clicks, orders, revenue in (
            (1, 100, 3, Decimal("75")),
            (2, 50, 1, Decimal("25")),
            (3, 25, 0, Decimal("0")),
        )
    ]
    insert_traffic_rows(traffic_db, rows)

    result = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="clicks",
        limit=20,
    )

    assert [item["sales_share"] for item in result["items"]] == [0.75, 0.25, 0.0]


def test_categories_aggregate_platform_categories_and_report_sku_coverage(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "wildberries",
                "platform_account_id": 1,
                "account_id": "wb-demo",
                "shop_name": "WB shop",
                "entity_id": "WB-1",
                "sku": "SKU-1",
                "impressions": 100,
                "clicks": 20,
                "add_to_cart": 4,
                "orders": 2,
                "revenue": Decimal("40"),
                "currency": "RUB",
                "raw_data": {
                    "platform_category_id": "8416",
                    "platform_category_name": "Бассейны надувные",
                    "platform_category_path": "Спорт / Бассейны надувные",
                },
            },
            {
                "platform": "wildberries",
                "platform_account_id": 1,
                "account_id": "wb-demo",
                "shop_name": "WB shop",
                "stat_date": "2026-07-08",
                "period_start": "2026-07-08",
                "period_end": "2026-07-08",
                "entity_id": "WB-1",
                "sku": "SKU-1",
                "impressions": 50,
                "clicks": 10,
                "add_to_cart": 2,
                "orders": 1,
                "revenue": Decimal("20"),
                "currency": "RUB",
                "raw_data": {
                    "platform_category_id": "8416",
                    "platform_category_name": "Бассейны надувные",
                    "platform_category_path": "Спорт / Бассейны надувные",
                },
            },
            {
                "platform": "joom_logistics",
                "platform_account_id": 2,
                "account_id": "joom-demo",
                "shop_name": "Joom shop",
                "source": "platform",
                "grain": "date_range",
                "stat_date": "2026-07-13",
                "period_start": "2026-07-07",
                "period_end": "2026-07-13",
                "entity_id": "JOOM-1",
                "sku": "SKU-2",
                "impressions": 80,
                "clicks": 8,
                "orders": 1,
                "raw_data": {"category_id": "joom-music", "category": "Music Albums"},
            },
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "ozon-demo",
                "shop_name": "Ozon shop",
                "entity_id": "OZON-2",
                "sku": "SKU-3",
                "impressions": 10,
                "clicks": 1,
                "raw_data": {},
            },
        ],
    )

    result = traffic_module.query_categories(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
    )
    by_category = {
        (item["platform"], item["platform_category_id"]): item
        for item in result["items"]
    }

    wildberries = by_category[("wildberries", "8416")]
    assert wildberries["platform_category_name"] == "Бассейны надувные"
    assert wildberries["platform_category_path"] == "Спорт / Бассейны надувные"
    assert wildberries["sku_count"] == 1
    assert wildberries["impressions"] == 150
    assert wildberries["clicks"] == 30
    assert wildberries["ctr"] == pytest.approx(0.2)
    assert wildberries["sales_share"] == pytest.approx(1.0)
    raw_data = json.loads(
        traffic_db.execute(
            text("SELECT raw_data FROM traffic_metrics WHERE entity_id = 'WB-1' LIMIT 1")
        ).scalar_one()
    )
    assert raw_data["platform_category_name"] == "Бассейны надувные"
    assert raw_data["platform_category_path"] == "Спорт / Бассейны надувные"
    assert by_category[("joom_logistics", "joom-music")]["platform_category_name"] == "Music Albums"
    assert by_category[("ozon", "")]["platform_category_name"] == "未归类"
    assert result["total_sku_count"] == 3
    assert result["categorized_sku_count"] == 2
    assert result["uncategorized_sku_count"] == 1
    assert result["classification_rate"] == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    ("platform", "platform_account_id", "region"),
    (("mercadolibre", 4, "MLB"), ("wildberries", 5, "RU")),
)
def test_date_range_platforms_fallback_to_latest_matching_period(
    traffic_db,
    platform,
    platform_account_id,
    region,
):
    common = {
        "platform": platform,
        "platform_account_id": platform_account_id,
        "account_id": f"{platform}-demo",
        "shop_name": f"{platform} shop",
        "source": "organic",
        "grain": "date_range",
        "region": region,
        "entity_id": f"{platform}-1",
        "sku": "SKU-1",
        "raw_data": {
            "platform_category_id": "category-1",
            "platform_category_name": "Category 1",
        },
    }
    insert_traffic_rows(
        traffic_db,
        [
            {
                **common,
                "stat_date": "2026-07-15",
                "period_start": "2026-07-09",
                "period_end": "2026-07-15",
                "clicks": 20,
                "orders": 4,
            },
            {
                **common,
                "stat_date": "2026-07-08",
                "period_start": "2026-07-02",
                "period_end": "2026-07-08",
                "clicks": 10,
                "orders": 2,
            },
        ],
    )

    requested_start = date(2026, 7, 10)
    requested_end = date(2026, 7, 16)
    categories = traffic_module.query_categories(
        traffic_db,
        requested_start,
        requested_end,
        platform=[platform],
    )
    rankings = traffic_module.query_rankings(
        traffic_db,
        requested_start,
        requested_end,
        metric="clicks",
        limit=20,
        platform=[platform],
    )
    comparison = traffic_module.query_comparison(
        traffic_db,
        requested_start,
        requested_end,
        metric="orders",
        limit=20,
        platform=[platform],
    )

    assert categories["items"][0]["clicks"] == 20
    assert categories["total_sku_count"] == 1
    assert len(rankings["items"]) == 1
    assert comparison["items"][0]["current_orders"] == 4
    assert comparison["items"][0]["previous_orders"] == 2
    assert comparison["items"][0]["delta_orders"] == 2
    assert categories["fallback_periods"] == [
        {
            "platform": platform,
            "platform_account_id": platform_account_id,
            "scope": "current",
            "requested_date_from": "2026-07-10",
            "requested_date_to": "2026-07-16",
            "actual_date_from": "2026-07-09",
            "actual_date_to": "2026-07-15",
        }
    ]
    assert {item["scope"] for item in comparison["fallback_periods"]} == {"current", "previous"}

    exact = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 9),
        date(2026, 7, 15),
        metric="clicks",
        limit=20,
        platform=[platform],
    )
    assert exact["fallback_periods"] == []


def test_mercado_views_show_latest_available_period_when_requested_duration_is_missing(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "mercadolibre",
                "platform_account_id": 4,
                "account_id": "mercado-demo",
                "shop_name": "Mercado shop",
                "source": "organic",
                "grain": "date_range",
                "stat_date": "2026-07-27",
                "period_start": "2026-06-28",
                "period_end": "2026-07-27",
                "region": "MLB",
                "entity_id": "MLB-1",
                "sku": "SKU-1",
                "clicks": 120,
                "orders": 6,
                "raw_data": {
                    "platform_category_id": "category-1",
                    "platform_category_name": "Category 1",
                },
            }
        ],
    )

    requested_start = date(2026, 7, 21)
    requested_end = date(2026, 7, 27)
    summary = traffic_module.query_summary(
        traffic_db,
        requested_start,
        requested_end,
        platform="mercadolibre",
    )
    categories = traffic_module.query_categories(
        traffic_db,
        requested_start,
        requested_end,
        platform="mercadolibre",
    )
    rankings = traffic_module.query_rankings(
        traffic_db,
        requested_start,
        requested_end,
        platform="mercadolibre",
        metric="clicks",
        limit=20,
    )
    comparison = traffic_module.query_comparison(
        traffic_db,
        requested_start,
        requested_end,
        platform="mercadolibre",
        metric="clicks",
        limit=20,
    )

    assert summary["items"][0]["clicks"] == 120
    assert summary["items"][0]["period_start"] == "2026-06-28"
    assert categories["items"][0]["clicks"] == 120
    assert rankings["items"][0]["clicks"] == 120
    assert summary["fallback_periods"] == [
        {
            "platform": "mercadolibre",
            "platform_account_id": 4,
            "scope": "current",
            "requested_date_from": "2026-07-21",
            "requested_date_to": "2026-07-27",
            "actual_date_from": "2026-06-28",
            "actual_date_to": "2026-07-27",
        }
    ]
    assert comparison["items"] == []


def test_summary_aggregates_in_sql_and_keeps_latest_rolling_snapshot(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "ozon-demo",
                "entity_id": "OZON-1",
                "sku": "SKU-1",
                "impressions": 10,
                "clicks": 2,
            },
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "ozon-demo",
                "entity_id": "OZON-2",
                "sku": "SKU-2",
                "impressions": None,
                "clicks": 3,
            },
            {
                "platform": "allegro",
                "platform_account_id": 2,
                "account_id": "allegro-demo",
                "grain": "rolling_30d",
                "stat_date": "2026-07-12",
                "period_start": "2026-06-13",
                "period_end": "2026-07-12",
                "entity_id": "ALLEGRO-1",
                "sku": "DEMO-SKU-0006",
                "clicks": 10,
            },
            {
                "platform": "allegro",
                "platform_account_id": 2,
                "account_id": "allegro-demo",
                "grain": "rolling_30d",
                "stat_date": "2026-07-13",
                "period_start": "2026-06-14",
                "period_end": "2026-07-13",
                "entity_id": "ALLEGRO-1",
                "sku": "DEMO-SKU-0006",
                "clicks": 20,
            },
        ],
    )

    result = traffic_module.query_summary(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
    )
    by_platform = {item["platform"]: item for item in result["items"]}

    assert by_platform["ozon"]["impressions"] == 10
    assert by_platform["ozon"]["clicks"] == 5
    assert by_platform["ozon"]["coverage"]["impressions"] == "partial"
    assert by_platform["allegro"]["clicks"] == 20
    assert by_platform["allegro"]["period_start"] == "2026-06-14"


def test_joom_queries_use_latest_available_complete_period(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "joom_logistics",
                "platform_account_id": 3,
                "account_id": "joom-demo",
                "shop_name": "Joom shop",
                "source": "platform",
                "grain": "date_range",
                "stat_date": "2026-07-13",
                "period_start": "2026-07-07",
                "period_end": "2026-07-13",
                "entity_id": "JOOM-1",
                "sku": "SKU-1",
                "impressions": 100,
                "clicks": 10,
                "add_to_cart": 2,
                "orders": 1,
            },
            {
                "platform": "joom_logistics",
                "platform_account_id": 3,
                "account_id": "joom-demo",
                "shop_name": "Joom shop",
                "source": "platform",
                "grain": "date_range",
                "stat_date": "2026-07-06",
                "period_start": "2026-06-30",
                "period_end": "2026-07-06",
                "entity_id": "JOOM-1",
                "sku": "SKU-1",
                "impressions": 80,
                "clicks": 8,
                "add_to_cart": 1,
                "orders": 1,
            },
        ],
    )

    summary = traffic_module.query_summary(
        traffic_db,
        date(2026, 7, 8),
        date(2026, 7, 14),
        platform="joom_logistics",
    )
    rankings = traffic_module.query_rankings(
        traffic_db,
        date(2026, 7, 8),
        date(2026, 7, 14),
        platform="joom_logistics",
        metric="impressions",
        limit=20,
    )
    comparison = traffic_module.query_comparison(
        traffic_db,
        date(2026, 7, 8),
        date(2026, 7, 14),
        platform="joom_logistics",
        metric="impressions",
        limit=20,
    )

    assert len(summary["items"]) == 1
    assert summary["items"][0]["impressions"] == 100
    assert summary["items"][0]["period_start"] == "2026-07-07"
    assert summary["items"][0]["period_end"] == "2026-07-13"
    assert len(rankings["items"]) == 1
    assert rankings["items"][0]["impressions"] == 100
    assert len(comparison["items"]) == 1
    assert comparison["items"][0]["current_impressions"] == 100
    assert comparison["items"][0]["previous_impressions"] == 80


def test_comparison_aggregates_periods_and_calculates_deltas(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "ozon-demo",
                "entity_id": "OZON-1",
                "sku": "SKU-1",
                "stat_date": "2026-07-08",
                "period_start": "2026-07-08",
                "period_end": "2026-07-08",
                "clicks": 100,
                "orders": 5,
            },
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "ozon-demo",
                "entity_id": "OZON-1",
                "sku": "SKU-1",
                "stat_date": "2026-07-01",
                "period_start": "2026-07-01",
                "period_end": "2026-07-01",
                "clicks": 40,
                "orders": 2,
            },
        ],
    )

    result = traffic_module.query_comparison(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="clicks",
        limit=20,
    )

    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["current_clicks"] == 100
    assert item["previous_clicks"] == 40
    assert item["delta_clicks"] == 60
    assert item["delta_rate_clicks"] == 1.5
    assert item["delta_orders"] == 3


def test_comparison_category_dimension_aggregates_by_shop_and_category_globally(traffic_db):
    rows = []
    for shop_id, shop_name, category_id, sku, current, previous, previous_has_category in (
        (1, "Shop A", "cat-a", "SKU-A1", 60, 20, False),
        (1, "Shop A", "cat-a", "SKU-A2", 20, 10, True),
        (2, "Shop B", "cat-b", "SKU-B1", 90, 70, True),
    ):
        common = {
            "platform": "ozon",
            "platform_account_id": shop_id,
            "account_id": f"shop-{shop_id}",
            "shop_name": shop_name,
            "entity_id": sku,
            "sku": sku,
        }
        category = {
            "platform_category_id": category_id,
            "platform_category_name": category_id.upper(),
        }
        rows.extend(
            (
                {
                    **common,
                    "stat_date": "2026-07-08",
                    "period_start": "2026-07-08",
                    "period_end": "2026-07-08",
                    "clicks": current,
                    "raw_data": category,
                },
                {
                    **common,
                    "stat_date": "2026-07-01",
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-01",
                    "clicks": previous,
                    "raw_data": category if previous_has_category else {},
                },
            )
        )
    insert_traffic_rows(traffic_db, rows)

    result = traffic_module.query_comparison(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="clicks",
        dimension="category",
        limit=1,
    )

    assert result["dimension"] == "category"
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["shop_name"] == "Shop A"
    assert item["platform_category_id"] == "cat-a"
    assert item["platform_category_name"] == "CAT-A"
    assert item["current_clicks"] == 80
    assert item["previous_clicks"] == 30
    assert item["delta_clicks"] == 50
    assert "sku" not in item
    assert "product_name" not in item


def test_category_sku_comparison_returns_top_skus_for_selected_category_metric(traffic_db):
    rows = []
    for sku, category_id, current_clicks, previous_clicks, previous_has_category in (
        ("SKU-A1", "cat-a", 90, 10, False),
        ("SKU-A2", "cat-a", 35, 20, True),
        ("SKU-A3", "cat-a", 12, 80, True),
        ("SKU-B1", "cat-b", 200, 1, True),
    ):
        common = {
            "platform": "ozon",
            "platform_account_id": 1,
            "account_id": "shop-1",
            "shop_name": "Shop A",
            "entity_id": sku,
            "sku": sku,
            "product_name": f"Product {sku}",
            "source": "organic",
            "grain": "daily",
            "region": "",
        }
        category = {
            "platform_category_id": category_id,
            "platform_category_name": category_id.upper(),
        }
        rows.extend(
            (
                {
                    **common,
                    "stat_date": "2026-07-08",
                    "period_start": "2026-07-08",
                    "period_end": "2026-07-08",
                    "clicks": current_clicks,
                    "orders": current_clicks // 10,
                    "raw_data": category,
                },
                {
                    **common,
                    "stat_date": "2026-07-01",
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-01",
                    "clicks": previous_clicks,
                    "orders": previous_clicks // 10,
                    "raw_data": category if previous_has_category else {},
                },
            )
        )
    insert_traffic_rows(traffic_db, rows)

    result = traffic_module.query_category_sku_comparison(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="clicks",
        sort_by="delta_abs",
        limit=2,
        platform="ozon",
        platform_account_id=1,
        source="organic",
        grain="daily",
        region="",
        platform_category_id="cat-a",
    )

    assert result["dimension"] == "sku"
    assert [item["sku"] for item in result["items"]] == ["SKU-A1", "SKU-A3"]
    assert result["items"][0]["current_clicks"] == 90
    assert result["items"][0]["previous_clicks"] == 10
    assert result["items"][0]["delta_clicks"] == 80
    assert result["items"][0]["delta_rate_clicks"] == 8.0

    filtered = traffic_module.query_category_sku_comparison(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="clicks",
        sort_by="current_desc",
        change_direction="up",
        keyword="SKU-A",
        limit=20,
        platform="ozon",
        platform_account_id=1,
        source="organic",
        grain="daily",
        region="",
        platform_category_id="cat-a",
    )

    assert filtered["sort_by"] == "current_desc"
    assert [item["sku"] for item in filtered["items"]] == ["SKU-A1", "SKU-A2"]


def test_category_sku_comparison_rejects_unknown_change_direction(traffic_db):
    with pytest.raises(ValueError, match="环比变化方向不受支持"):
        traffic_module.query_category_sku_comparison(
            traffic_db,
            date(2026, 7, 7),
            date(2026, 7, 13),
            metric="clicks",
            sort_by="delta_abs",
            change_direction="sideways",
            limit=20,
            platform="ozon",
            platform_account_id=1,
            source="organic",
            grain="daily",
            region="",
            platform_category_id="cat-a",
        )


def test_category_sku_comparison_allows_uncategorized_category(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "shop-1",
                "shop_name": "Shop A",
                "entity_id": "SKU-EMPTY",
                "sku": "DEMO-SKU-0032",
                "stat_date": "2026-07-08",
                "period_start": "2026-07-08",
                "period_end": "2026-07-08",
                "orders": 9,
                "raw_data": {},
            },
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "shop-1",
                "shop_name": "Shop A",
                "entity_id": "SKU-EMPTY",
                "sku": "DEMO-SKU-0032",
                "stat_date": "2026-07-01",
                "period_start": "2026-07-01",
                "period_end": "2026-07-01",
                "orders": 3,
                "raw_data": {},
            },
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "shop-1",
                "shop_name": "Shop A",
                "entity_id": "SKU-CAT",
                "sku": "DEMO-SKU-0033",
                "stat_date": "2026-07-08",
                "period_start": "2026-07-08",
                "period_end": "2026-07-08",
                "orders": 20,
                "raw_data": {"platform_category_id": "cat-a"},
            },
        ],
    )

    result = traffic_module.query_category_sku_comparison(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="orders",
        sort_by="delta_abs",
        limit=20,
        platform="ozon",
        platform_account_id=1,
        source="organic",
        grain="daily",
        region="",
        platform_category_id="",
    )

    assert [item["sku"] for item in result["items"]] == ["DEMO-SKU-0032"]
    assert result["items"][0]["delta_orders"] == 6


def test_category_sku_focus_analysis_matches_any_rule_and_preserves_global_ranks(traffic_db):
    rows = []
    for sku, impressions, clicks, add_to_cart, orders in (
        ("RULE-1", 100, 10, 10, 0),
        ("RULE-2-IMPRESSION", 10, 100, 100, 100),
        ("RULE-2-CART", 90, 90, 5, 90),
        ("RULE-3", 80, 80, 90, 1),
    ):
        rows.append(
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "shop-1",
                "shop_name": "Shop A",
                "entity_id": sku,
                "sku": sku,
                "product_name": f"Product {sku}",
                "source": "organic",
                "grain": "daily",
                "region": "",
                "stat_date": "2026-07-08",
                "period_start": "2026-07-08",
                "period_end": "2026-07-08",
                "impressions": impressions,
                "clicks": clicks,
                "add_to_cart": add_to_cart,
                "orders": orders,
                "raw_data": {
                    "platform_category_id": "cat-a",
                    "platform_category_name": "Category A",
                },
            }
        )
    insert_traffic_rows(traffic_db, rows)

    result = traffic_module.query_category_sku_focus_analysis(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        top_n=2,
        platform="ozon",
        platform_account_id=1,
        source="organic",
        grain="daily",
        region="",
        platform_category_id="cat-a",
    )

    assert result["top_n"] == 2
    assert result["supported_metrics"] == ["impressions", "clicks", "add_to_cart", "orders"]
    items_by_sku = {item["sku"]: item for item in result["items"]}
    assert items_by_sku["RULE-1"]["focus_reasons"] == ["high_impressions_no_orders"]
    assert items_by_sku["RULE-2-IMPRESSION"]["focus_reasons"] == [
        "high_clicks_missing_impressions_or_cart",
        "high_orders_missing_impressions",
    ]
    assert items_by_sku["RULE-2-CART"]["focus_reasons"] == [
        "high_clicks_missing_impressions_or_cart"
    ]
    assert items_by_sku["RULE-3"]["focus_reasons"] == ["high_cart_missing_orders"]
    assert items_by_sku["RULE-2-CART"]["impressions_rank"] == 2
    assert items_by_sku["RULE-2-CART"]["add_to_cart_rank"] == 4

    filtered = traffic_module.query_category_sku_focus_analysis(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        top_n=2,
        platform="ozon",
        platform_account_id=1,
        source="organic",
        grain="daily",
        region="",
        platform_category_id="cat-a",
        keyword="RULE-2-CART",
    )

    assert [item["sku"] for item in filtered["items"]] == ["RULE-2-CART"]
    assert filtered["items"][0]["impressions_rank"] == 2
    assert filtered["items"][0]["add_to_cart_rank"] == 4


def test_comparison_rejects_unknown_dimension(traffic_db):
    with pytest.raises(ValueError, match="环比分析维度不受支持"):
        traffic_module.query_comparison(
            traffic_db,
            date(2026, 7, 7),
            date(2026, 7, 13),
            metric="clicks",
            dimension="shop",
            limit=20,
        )


def test_comparison_sorts_top_results_by_change_rate(traffic_db):
    rows = []
    for sku, current, previous in (
        ("RATE-HIGH", 30, 10),
        ("RATE-LOW", 120, 100),
        ("NEW", 100, 0),
        ("LOSS", 0, 100),
    ):
        common = {
            "platform": "ozon",
            "platform_account_id": 1,
            "account_id": "ozon-demo",
            "entity_id": sku,
            "sku": sku,
        }
        rows.append(
            {
                **common,
                "stat_date": "2026-07-08",
                "period_start": "2026-07-08",
                "period_end": "2026-07-08",
                "impressions": current,
            }
        )
        if previous:
            rows.append(
                {
                    **common,
                    "stat_date": "2026-07-01",
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-01",
                    "impressions": previous,
                }
            )
    insert_traffic_rows(traffic_db, rows)

    descending = traffic_module.query_comparison(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="impressions",
        sort_by="rate_desc",
        limit=2,
    )
    ascending = traffic_module.query_comparison(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="impressions",
        sort_by="rate_asc",
        limit=2,
    )

    assert descending["sort_by"] == "rate_desc"
    assert [item["sku"] for item in descending["items"]] == ["RATE-HIGH", "RATE-LOW"]
    assert [item["sku"] for item in ascending["items"]] == ["LOSS", "NEW"]


def test_comparison_rejects_unknown_sort(traffic_db):
    with pytest.raises(ValueError, match="环比排序方式不受支持"):
        traffic_module.query_comparison(
            traffic_db,
            date(2026, 7, 7),
            date(2026, 7, 13),
            metric="impressions",
            sort_by="rate_abs",
            limit=20,
        )


def test_comparison_includes_skus_present_in_only_one_period(traffic_db):
    insert_traffic_rows(
        traffic_db,
        [
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "ozon-demo",
                "entity_id": "CURRENT-ONLY",
                "sku": "DEMO-SKU-0034",
                "stat_date": "2026-07-08",
                "period_start": "2026-07-08",
                "period_end": "2026-07-08",
                "orders": 10,
            },
            {
                "platform": "ozon",
                "platform_account_id": 1,
                "account_id": "ozon-demo",
                "entity_id": "PREVIOUS-ONLY",
                "sku": "DEMO-SKU-0035",
                "stat_date": "2026-07-01",
                "period_start": "2026-07-01",
                "period_end": "2026-07-01",
                "orders": 7,
            },
        ],
    )

    result = traffic_module.query_comparison(
        traffic_db,
        date(2026, 7, 7),
        date(2026, 7, 13),
        metric="orders",
        limit=20,
    )

    by_sku = {item["sku"]: item for item in result["items"]}
    assert by_sku["DEMO-SKU-0034"]["current_orders"] == 10
    assert by_sku["DEMO-SKU-0034"]["previous_orders"] == 0
    assert by_sku["DEMO-SKU-0034"]["delta_orders"] == 10
    assert by_sku["DEMO-SKU-0035"]["current_orders"] == 0
    assert by_sku["DEMO-SKU-0035"]["previous_orders"] == 7
    assert by_sku["DEMO-SKU-0035"]["delta_orders"] == -7


def test_product_name_lookup_is_scoped_by_shop_and_tolerates_sku_case():
    class FakeResult:
        def all(self):
            return [
                (
                    10,
                    1,
                    "sku-1",
                    datetime(2026, 7, 1),
                    datetime(2026, 7, 2),
                    "产品中文名称",
                )
            ]

    class FakeDb:
        def execute(self, _statement):
            return FakeResult()

    rows = [
        SimpleNamespace(platform_account_id=1, sku="SKU-1"),
        SimpleNamespace(platform_account_id=2, sku="SKU-1"),
        SimpleNamespace(platform_account_id=1, sku="SKU-2"),
    ]

    assert traffic_module._traffic_product_name_lookup(FakeDb(), rows) == {
        (1, "SKU-1"): "产品中文名称"
    }


def test_scheduled_sync_uses_default_period_and_runs_pending_accounts(monkeypatch):
    calls = []

    class FakeDb:
        def close(self):
            calls.append(("close",))

    def fake_create(db, request, triggered_by, **options):
        calls.append(("create", db, request.date_from, request.date_to, triggered_by, options))
        return [], [7, 9]

    monkeypatch.setattr(traffic_module, "SessionLocal", FakeDb)
    monkeypatch.setattr(traffic_module, "create_traffic_sync_runs", fake_create)
    monkeypatch.setattr(traffic_module, "run_traffic_sync_runs", lambda run_ids: calls.append(("run", run_ids)))

    assert traffic_module.run_scheduled_traffic_sync() == 2
    assert calls[0][2:5] == (None, None, "scheduler:daily-06:00")
    assert calls[0][5] == {
        "skip_successful_period": True,
        "scheduled_attempt_limit": traffic_module.MAX_SCHEDULED_TRAFFIC_ATTEMPTS_PER_PERIOD,
    }
    assert ("close",) in calls
    assert ("run", [7, 9]) in calls


def test_traffic_freshness_audit_logs_missing_and_stale_accounts(caplog):
    expected_end = date(2026, 7, 27)

    class FakeDb:
        def execute(self, _statement):
            return SimpleNamespace(
                all=lambda: [
                    ("mercadolibre", "mercado-demo", date(2026, 7, 25)),
                    ("ozon", "ozon-demo", expected_end),
                    ("joom_logistics", "joom-demo", None),
                ]
            )

    caplog.set_level("ERROR", logger="app.traffic_analytics")

    stale_count = traffic_module.audit_traffic_data_freshness(
        FakeDb(),
        today=date(2026, 7, 28),
    )

    assert stale_count == 2
    assert "account=mercado-demo" in caplog.text
    assert "lag=2 days" in caplog.text
    assert "account=joom-demo" in caplog.text
    assert "lag=no data" in caplog.text


def test_scheduled_sync_creation_skips_successful_period():
    account = SimpleNamespace(
        id=1,
        platform="ozon",
        account_id="ozon-demo",
        display_name="Ozon shop",
    )
    successful = SimpleNamespace(
        id=11,
        platform_account_id=1,
        platform="ozon",
        account_id="ozon-demo",
        shop_name="Ozon shop",
        status="success",
        date_from=date(2026, 7, 9),
        date_to=date(2026, 7, 15),
        rows_written=20,
        error_message="",
        triggered_by="scheduler:daily-06:00",
        started_at=None,
        finished_at=None,
        created_at=None,
    )

    class FakeDb:
        def __init__(self):
            self.scalar_results = [None, successful]
            self.added = []

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [account])

        def scalar(self, _statement):
            return self.scalar_results.pop(0)

        def add(self, row):
            self.added.append(row)

        def commit(self):
            return None

    db = FakeDb()
    runs, created_ids = traffic_module.create_traffic_sync_runs(
        db,
        traffic_module.TrafficSyncRequest(date_from=date(2026, 7, 9), date_to=date(2026, 7, 15)),
        "scheduler:retry",
        skip_successful_period=True,
        scheduled_attempt_limit=4,
    )

    assert runs[0]["id"] == 11
    assert created_ids == []
    assert db.added == []


def test_scheduled_sync_creation_stops_at_attempt_limit():
    account = SimpleNamespace(
        id=1,
        platform="mercadolibre",
        account_id="mercado-demo",
        display_name="Mercado shop",
    )

    class FakeDb:
        def __init__(self):
            self.scalar_results = [None, None, 4]
            self.added = []

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [account])

        def scalar(self, _statement):
            return self.scalar_results.pop(0)

        def add(self, row):
            self.added.append(row)

        def commit(self):
            return None

    db = FakeDb()
    runs, created_ids = traffic_module.create_traffic_sync_runs(
        db,
        traffic_module.TrafficSyncRequest(date_from=date(2026, 7, 9), date_to=date(2026, 7, 15)),
        "scheduler:retry",
        skip_successful_period=True,
        scheduled_attempt_limit=4,
    )

    assert runs == []
    assert created_ids == []
    assert db.added == []


def test_scheduled_sync_retries_when_latest_period_run_timed_out():
    account = SimpleNamespace(
        id=1,
        platform="wildberries",
        account_id="wb-demo",
        display_name="Wildberries shop",
    )
    timed_out = SimpleNamespace(status="timed_out")

    class FakeDb:
        def __init__(self):
            self.scalar_results = [None, timed_out, 1]
            self.added = []

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [account])

        def scalar(self, _statement):
            return self.scalar_results.pop(0)

        def add(self, row):
            self.added.append(row)

        def flush(self):
            self.added[-1].id = 12
            self.added[-1].rows_written = 0
            self.added[-1].created_at = None

        def commit(self):
            return None

    db = FakeDb()
    runs, created_ids = traffic_module.create_traffic_sync_runs(
        db,
        traffic_module.TrafficSyncRequest(date_from=date(2026, 7, 22), date_to=date(2026, 7, 28)),
        "scheduler:retry",
        skip_successful_period=True,
        scheduled_attempt_limit=4,
    )

    assert runs[0]["status"] == "pending"
    assert created_ids == [12]
    assert len(db.added) == 1


def test_traffic_timeout_has_distinct_terminal_status():
    timeout = ConnectorRuntimeError(
        "TRAFFIC_SYNC_TIMEOUT",
        "流量同步超过 30 分钟，已停止当前店铺任务",
        retryable=True,
    )

    assert traffic_module._traffic_failure_status(timeout) == "timed_out"
    assert traffic_module._traffic_failure_status(RuntimeError("HTTP 500")) == "failed"


@pytest.mark.asyncio
async def test_platform_queue_continues_after_unexpected_run_failure(monkeypatch):
    calls = []

    class FakeDb:
        def execute(self, _statement):
            return SimpleNamespace(all=lambda: [(1, "ozon"), (2, "ozon"), (3, "joom_logistics")])

        def close(self):
            return None

    async def fake_sync(run_id):
        calls.append(run_id)
        if run_id == 1:
            raise RuntimeError("unexpected failure")

    monkeypatch.setattr(traffic_module, "SessionLocal", FakeDb)
    monkeypatch.setattr(traffic_module, "_sync_one_run", fake_sync)

    await traffic_module._run_traffic_sync_runs([1, 2, 3])

    assert set(calls) == {1, 2, 3}
    assert calls.index(2) > calls.index(1)
