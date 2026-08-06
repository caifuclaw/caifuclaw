import json
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from httpx import AsyncClient, Response

from app.adapters.allegro import AllegroConnector
from app.adapters.joom import JoomLogisticsConnector
from app.adapters.mercado import MercadoGlobalConnector
from app.adapters.ozon import OzonConnector
from app.adapters.wildberries import WildberriesConnector


@pytest.mark.asyncio
async def test_ozon_traffic_request_retries_remote_protocol_disconnect(monkeypatch):
    connector = OzonConnector(
        {"client_id": "1", "api_key": "token"},
        {"base_url": "https://api-seller.ozon.ru"},
    )
    post = AsyncMock(
        side_effect=[
            httpx.RemoteProtocolError("Server disconnected without sending a response."),
            {"result": {}},
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(connector, "_post", post)
    monkeypatch.setattr("app.adapters.ozon.asyncio.sleep", sleep)

    response = await connector._traffic_post("/v1/analytics/data", {"limit": 1000})

    assert response == {"result": {}}
    assert post.await_count == 2
    sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
@respx.mock
async def test_ozon_traffic_maps_daily_funnel_metrics():
    respx.post("https://api-seller.ozon.ru/v1/analytics/data").mock(
        return_value=Response(
            200,
            json={
                "result": {
                    "data": [
                        {
                            "dimensions": [{"id": "2026-07-06"}, {"id": "1001", "name": "SKU-1"}],
                            "metrics": [100, 25, 3, 2, 4, 88.5],
                        }
                    ]
                }
            },
        )
    )
    product_route = respx.post("https://api-seller.ozon.ru/v3/product/info/list").mock(
        return_value=Response(
            200,
            json={
                "items": [
                    {
                        "id": 501,
                        "offer_id": "SELLER-SKU-1",
                        "sku": 1001,
                        "name": "SKU-1",
                        "description_category_id": 46590429,
                        "type_id": 392547272,
                    }
                ]
            },
        )
    )
    respx.post("https://api-seller.ozon.ru/v1/review/list").mock(
        return_value=Response(
            200,
            json={
                "reviews": [
                    {"sku": 1001, "rating": 1, "published_at": "2026-07-06T12:00:00Z"},
                    {"sku": 1001, "rating": 5, "published_at": "2026-07-06T13:00:00Z"},
                ],
                "has_next": False,
                "last_id": "",
            },
        )
    )
    connector = OzonConnector(
        {"client_id": "1", "api_key": "token"},
        {"base_url": "https://api-seller.ozon.ru"},
    )

    rows = await connector.fetch_traffic(datetime(2026, 7, 6), datetime(2026, 7, 12))

    assert product_route.called
    assert rows[0]["entity_id"] == "1001"
    assert rows[0]["sku"] == "SELLER-SKU-1"
    assert rows[0]["raw_data"]["ozon_sku"] == "1001"
    assert rows[0]["product_name"] == "SKU-1"
    assert rows[0]["impressions"] == 100
    assert rows[0]["clicks"] == 25
    assert rows[0]["add_to_cart"] == 5
    assert rows[0]["orders"] == 4
    assert rows[0]["units_sold"] == 4
    assert rows[0]["negative_reviews"] == 1
    assert rows[0]["raw_data"]["negative_reviews_source"] == "ozon_reviews"
    assert rows[0]["raw_data"]["platform_category_id"] == "46590429:392547272"


@pytest.mark.asyncio
@respx.mock
async def test_joom_traffic_maps_product_ranking_and_derives_previous_week():
    base_url = "https://api-merchant.joom.com/api/v3"
    store_id = "649e8e1148dcce63235fa6f6"
    respx.get(f"{base_url}/stores/all").mock(
        return_value=Response(200, json={"code": 0, "data": {"items": [{"id": store_id, "name": "Joom Demo Shop"}]}})
    )
    respx.post(f"{base_url}/products/multi").mock(
        return_value=Response(
            200,
            json={"code": 0, "data": {"items": [{"metrics": {"asOfDate": "2026-07-13"}}]}},
        )
    )

    def create_download(request):
        body = json.loads(request.content)
        metrics_period = body["metricsPeriod"]
        return Response(
            200,
            json={"code": 0, "data": {"id": f"download-{metrics_period}", "status": "pending"}},
        )

    create_route = respx.post(f"{base_url}/products/periodMetrics/downloads/create").mock(
        side_effect=create_download
    )

    def download_status(request):
        download_id = request.url.params["id"]
        metrics_period = download_id.removeprefix("download-")
        return Response(
            200,
            json={
                "code": 0,
                "data": {
                    "id": download_id,
                    "status": "finished",
                    "csvFileUrl": f"https://api-merchant.joom.com/reports/{metrics_period}.csv",
                },
            },
        )

    respx.get(f"{base_url}/downloads").mock(side_effect=download_status)
    header = (
        "Product ID,SKU,Name,Category,Category ID,Store ID,Impressions,Opens,Cart,Favourites,"
        "Purchases,Sales,\"CTR, %\",\"Open to Cart, %\",\"Open to Favourites, %\",\"CR, %\"\n"
    )
    current_csv = header + (
        "698ea6c4948afe01defb7f2f,KPOP_A_LNGSHOT_MORE VISION_STANDARD,"
        "LNGSHOT - [SHOT CALLERS] EP Album STANDARD Version,Music Albums,category-1,"
        f"{store_id},13077,897,192,0,25,25,6.86,21.40,0.00,2.79\n"
    )
    wider_csv = header + (
        "698ea6c4948afe01defb7f2f,KPOP_A_LNGSHOT_MORE VISION_STANDARD,"
        "LNGSHOT - [SHOT CALLERS] EP Album STANDARD Version,Music Albums,category-1,"
        f"{store_id},20000,1200,250,1,40,42,6.00,20.83,0.08,3.33\n"
        "previous-only,OLD-SKU,Previous product,Music Albums,category-1,"
        f"{store_id},50,5,1,0,1,2,10.00,20.00,0.00,20.00\n"
    )
    respx.get("https://api-merchant.joom.com/reports/1w.csv").mock(
        return_value=Response(200, content=current_csv.encode("utf-8"), headers={"Content-Type": "text/csv"})
    )
    respx.get("https://api-merchant.joom.com/reports/2w.csv").mock(
        return_value=Response(200, content=wider_csv.encode("utf-8"), headers={"Content-Type": "text/csv"})
    )
    respx.get(f"{base_url}/reviews/multi").mock(
        return_value=Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "productId": "698ea6c4948afe01defb7f2f",
                            "reviewTimestamp": "2026-07-07T12:00:00Z",
                            "starRating": 1,
                        },
                        {
                            "productId": "698ea6c4948afe01defb7f2f",
                            "reviewTimestamp": "2026-07-07T13:00:00Z",
                            "starRating": 5,
                        },
                    ]
                },
            },
        )
    )
    connector = JoomLogisticsConnector(
        {"access_token": "token"},
        {
            "base_url": base_url,
            "display_name": "Joom Demo Shop",
            "joom_traffic_poll_interval_seconds": 0,
        },
    )

    rows = await connector.fetch_traffic(datetime(2026, 7, 8), datetime(2026, 7, 14))

    assert create_route.call_count == 2
    request_bodies = [json.loads(call.request.content) for call in create_route.calls]
    assert {body["metricsPeriod"] for body in request_bodies} == {"1w", "2w"}
    assert {body["storeId"] for body in request_bodies} == {store_id}

    current = next(row for row in rows if row["period_start"] == "2026-07-07")
    assert current["source"] == "platform"
    assert current["grain"] == "date_range"
    assert current["entity_type"] == "sku"
    assert current["entity_id"] == "698ea6c4948afe01defb7f2f"
    assert current["sku"] == "KPOP_A_LNGSHOT_MORE VISION_STANDARD"
    assert current["impressions"] == 13077
    assert current["clicks"] == 897
    assert current["add_to_cart"] == 192
    assert current["orders"] == 25
    assert current["units_sold"] == 25
    assert current["negative_reviews"] == 1
    assert current["raw_data"]["store_id"] == store_id
    assert current["raw_data"]["platform_category_id"] == "category-1"
    assert current["raw_data"]["platform_category_name"] == "Music Albums"
    assert current["raw_data"]["negative_reviews_source"] == "joom_reviews"
    assert current["raw_data"]["negative_reviews_daily"] == {"2026-07-07": 1}

    previous = next(
        row
        for row in rows
        if row["entity_id"] == "698ea6c4948afe01defb7f2f" and row["period_start"] == "2026-06-30"
    )
    assert previous["period_end"] == "2026-07-06"
    assert previous["impressions"] == 6923
    assert previous["clicks"] == 303
    assert previous["add_to_cart"] == 58
    assert previous["orders"] == 15
    assert previous["units_sold"] == 17
    assert previous["raw_data"]["derived_previous"] is True
    assert any(row["entity_id"] == "previous-only" for row in rows)


@pytest.mark.asyncio
async def test_joom_traffic_rejects_unsupported_period_before_requesting_reports():
    connector = JoomLogisticsConnector(
        {"access_token": "token"},
        {"base_url": "https://api-merchant.joom.com/api/v3"},
    )

    with pytest.raises(ValueError, match="latest 7, 14, or 28 complete days"):
        await connector.fetch_traffic(datetime(2026, 7, 8), datetime(2026, 7, 13))


@pytest.mark.asyncio
@respx.mock
async def test_mercado_traffic_preserves_local_marketplace_region():
    respx.get("https://api.mercadolibre.com/users/1/items/search").mock(
        return_value=Response(200, json={"scroll_id": "scroll", "results": ["CBT1"]})
    )
    respx.get("https://api.mercadolibre.com/items").mock(
        side_effect=[
            Response(
                200,
                json=[
                    {
                        "code": 200,
                        "body": {"id": "CBT1", "title": "Product", "category_id": "CBT100"},
                    }
                ],
            ),
            Response(
                200,
                json=[
                    {
                        "code": 200,
                        "body": {
                            "id": "MLM1",
                            "title": "Mexico Product",
                            "seller_sku": "DEMO-SKU-0026",
                            "category_id": "MLM100",
                        },
                    },
                    {
                        "code": 200,
                        "body": {
                            "id": "MLB2",
                            "title": "Brazil Product",
                            "seller_sku": "DEMO-SKU-0025",
                            "category_id": "MLB200",
                        },
                    },
                ],
            ),
        ]
    )
    respx.get("https://api.mercadolibre.com/items/CBT1/marketplace_items").mock(
        return_value=Response(
            200,
            json={
                "marketplace_items": [
                    {"item_id": "MLM1", "site_id": "MLM"},
                    {"item_id": "MLB2", "site_id": "MLB"},
                ]
            },
        )
    )
    respx.get("https://api.mercadolibre.com/categories/MLM100").mock(
        return_value=Response(
            200,
            json={
                "id": "MLM100",
                "name": "Collectibles",
                "path_from_root": [
                    {"id": "MLM1", "name": "Hobbies"},
                    {"id": "MLM100", "name": "Collectibles"},
                ],
            },
        )
    )
    respx.get("https://api.mercadolibre.com/categories/MLB200").mock(
        return_value=Response(
            200,
            json={
                "id": "MLB200",
                "name": "Toys",
                "path_from_root": [{"id": "MLB200", "name": "Toys"}],
            },
        )
    )
    visits_route = respx.get("https://api.mercadolibre.com/items/visits/time_window").mock(
        return_value=Response(
            200,
            json=[
                {"item_id": "MLM1", "total_visits": 17},
                {"item_id": "MLB2", "total_visits": 9},
            ],
        )
    )
    mlm_review_route = respx.get("https://api.mercadolibre.com/reviews/item/MLM1").mock(
        side_effect=[
            Response(
                200,
                json={
                    "paging": {"total": 7, "limit": 2, "offset": 0, "total_pageable": 3},
                    "rating_average": 3.8,
                    "rating_levels": {
                        "one_star": 1,
                        "two_star": 2,
                        "three_star": 1,
                        "four_star": 1,
                        "five_star": 2,
                    },
                    "reviews": [
                        {"id": 1, "rate": 1, "reviewable_object": {"id": "MLM1"}},
                        {"id": 2, "rate": 2, "reviewable_object": {"id": "MLM-OTHER"}},
                    ],
                },
            ),
            Response(
                200,
                json={
                    "paging": {"total": 7, "limit": 2, "offset": 2, "total_pageable": 3},
                    "reviews": [
                        {"id": 3, "rate": 2, "reviewable_object": {"id": "MLM1"}},
                    ],
                },
            ),
        ]
    )
    respx.get("https://api.mercadolibre.com/reviews/item/MLB2").mock(
        return_value=Response(
            200,
            json={"paging": {"total": 0, "limit": 100, "offset": 0, "total_pageable": 0}, "rating_levels": {}, "reviews": []},
        )
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "1"},
        {"base_url": "https://api.mercadolibre.com", "mercado_site": "CBT", "mercado_store_type": "cbt"},
    )

    rows = await connector.fetch_traffic(datetime(2026, 7, 6), datetime(2026, 7, 12))

    assert len(rows) == 4
    assert visits_route.call_count == 4
    assert all("," not in call.request.url.params["ids"] for call in visits_route.calls)
    assert rows[0]["region"] == "MLM"
    assert rows[0]["entity_id"] == "MLM1"
    assert rows[0]["sku"] == "DEMO-SKU-0026"
    assert rows[0]["product_name"] == "Mexico Product"
    assert rows[0]["clicks"] == 17
    assert rows[0]["impressions"] is None
    assert rows[0]["negative_reviews"] == 2
    assert rows[1]["negative_reviews"] == 0
    assert rows[0]["raw_data"]["review_total"] == 7
    assert rows[0]["raw_data"]["catalog_negative_reviews"] == 3
    assert rows[0]["raw_data"]["negative_reviews_pageable"] == 3
    assert rows[0]["raw_data"]["negative_reviews_scope"] == "local_item"
    assert mlm_review_route.call_count == 2
    assert mlm_review_route.calls[0].request.url.params["rating"] == "negative"
    assert mlm_review_route.calls[0].request.url.params["limit"] == "100"
    assert mlm_review_route.calls[0].request.url.params["offset"] == "0"
    assert mlm_review_route.calls[1].request.url.params["offset"] == "2"
    assert rows[0]["raw_data"]["platform_category_id"] == "MLM100"
    assert rows[0]["raw_data"]["platform_category_name"] == "Collectibles"
    assert rows[0]["raw_data"]["platform_category_path"] == "Hobbies / Collectibles"
    assert rows[0]["raw_data"]["traffic_sync_status"] == "full"
    assert rows[0]["raw_data"]["traffic_expected_items"] == 1
    assert rows[0]["raw_data"]["traffic_received_items"] == 1
    assert rows[0]["raw_data"]["traffic_missing_items"] == 0
    assert rows[2]["period_end"] == "2026-07-05"


@pytest.mark.asyncio
@respx.mock
async def test_mercado_traffic_isolates_missing_visits_by_site():
    respx.get("https://api.mercadolibre.com/users/1/items/search").mock(
        return_value=Response(200, json={"results": ["CBT1"]})
    )
    respx.get("https://api.mercadolibre.com/items").mock(
        side_effect=[
            Response(
                200,
                json=[
                    {
                        "code": 200,
                        "body": {"id": "CBT1", "title": "Product", "category_id": "CBT100"},
                    }
                ],
            ),
            Response(
                200,
                json=[
                    {"code": 200, "body": {"id": "MLM1", "title": "Mexico", "seller_sku": "DEMO-SKU-0026"}},
                    {"code": 200, "body": {"id": "MLB2", "title": "Brazil", "seller_sku": "DEMO-SKU-0025"}},
                ],
            ),
        ]
    )
    respx.get("https://api.mercadolibre.com/items/CBT1/marketplace_items").mock(
        return_value=Response(
            200,
            json={
                "marketplace_items": [
                    {"item_id": "MLM1", "site_id": "MLM"},
                    {"item_id": "MLB2", "site_id": "MLB"},
                ]
            },
        )
    )
    respx.get("https://api.mercadolibre.com/categories/CBT100").mock(
        return_value=Response(
            200,
            json={"id": "CBT100", "name": "Collectibles", "path_from_root": []},
        )
    )

    def visit_response(request):
        child_id = request.url.params["ids"]
        if child_id == "MLB2":
            return Response(404, json={"message": "not available"})
        return Response(200, json=[{"item_id": child_id, "total_visits": 17}])

    respx.get("https://api.mercadolibre.com/items/visits/time_window").mock(
        side_effect=visit_response
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "1"},
        {
            "base_url": "https://api.mercadolibre.com",
            "mercado_site": "CBT",
            "fetch_traffic_reviews": False,
            "traffic_request_interval_seconds": 0.1,
        },
    )

    rows = await connector.fetch_traffic(datetime(2026, 7, 6), datetime(2026, 7, 12))
    current = {row["region"]: row for row in rows if row["period_end"] == "2026-07-12"}

    assert current["MLM"]["clicks"] == 17
    assert current["MLM"]["raw_data"]["traffic_sync_status"] == "full"
    assert current["MLB"]["clicks"] is None
    assert current["MLB"]["raw_data"]["traffic_sync_status"] == "partial"
    assert current["MLB"]["raw_data"]["traffic_expected_items"] == 1
    assert current["MLB"]["raw_data"]["traffic_received_items"] == 0
    assert current["MLB"]["raw_data"]["traffic_missing_items"] == 1
    assert "HTTP 404" in current["MLB"]["raw_data"]["traffic_error_samples"][0]


@pytest.mark.asyncio
@respx.mock
async def test_mercado_traffic_retries_item_server_errors():
    respx.get("https://api.mercadolibre.com/users/1/items/search").mock(
        return_value=Response(200, json={"results": ["CBT1"]})
    )
    respx.get("https://api.mercadolibre.com/items").mock(
        side_effect=[
            Response(
                200,
                json=[
                    {
                        "code": 200,
                        "body": {
                            "id": "CBT1",
                            "title": "Product",
                            "category_id": "CBT100",
                        },
                    }
                ],
            ),
            Response(
                200,
                json=[
                    {
                        "code": 403,
                        "body": {
                            "id": "MLM1",
                            "status": 403,
                            "error": "forbidden",
                        },
                    }
                ],
            ),
        ]
    )
    respx.get("https://api.mercadolibre.com/items/CBT1/marketplace_items").mock(
        return_value=Response(200, json={"marketplace_items": [{"item_id": "MLM1", "site_id": "MLM"}]})
    )
    respx.get("https://api.mercadolibre.com/reviews/item/MLM1").mock(
        return_value=Response(200, json={"paging": {"total": 0}, "rating_levels": {}})
    )
    respx.get("https://api.mercadolibre.com/categories/CBT100").mock(
        return_value=Response(
            200,
            json={
                "id": "CBT100",
                "name": "Cross-border Collectibles",
                "path_from_root": [
                    {"id": "CBT1", "name": "Collectibles"},
                    {"id": "CBT100", "name": "Cross-border Collectibles"},
                ],
            },
        )
    )
    visits_route = respx.get("https://api.mercadolibre.com/items/visits/time_window").mock(
        side_effect=[
            httpx.ConnectError("temporary network failure"),
            Response(500, json={"message": "temporary"}),
            Response(200, json=[{"item_id": "MLM1", "total_visits": 17}]),
            Response(200, json=[{"item_id": "MLM1", "total_visits": 8}]),
        ]
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "1"},
        {
            "base_url": "https://api.mercadolibre.com",
            "mercado_site": "CBT",
            "traffic_request_interval_seconds": 0.1,
        },
    )

    rows = await connector.fetch_traffic(datetime(2026, 7, 6), datetime(2026, 7, 12))

    assert visits_route.call_count == 4
    assert [row["clicks"] for row in rows] == [17, 8]
    assert rows[0]["sku"] == ""
    assert rows[0]["raw_data"]["platform_category_id"] == "CBT100"
    assert rows[0]["raw_data"]["platform_category_name"] == "Cross-border Collectibles"
    assert rows[0]["raw_data"]["platform_category_path"] == "Collectibles / Cross-border Collectibles"


@pytest.mark.asyncio
@respx.mock
async def test_mercado_traffic_metadata_retries_rate_limit(monkeypatch):
    item_route = respx.get("https://api.mercadolibre.com/items").mock(
        side_effect=[
            Response(429, headers={"Retry-After": "3"}, json={"message": "too many requests"}),
            Response(200, json=[{"code": 200, "body": {"id": "CBT1", "title": "Product"}}]),
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr("app.adapters.mercado.asyncio.sleep", sleep)
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "1"},
        {
            "base_url": "https://api.mercadolibre.com",
            "traffic_metadata_request_interval_seconds": 0,
        },
    )

    async with AsyncClient() as client:
        response = await connector._traffic_get(client, "/items", params={"ids": "CBT1"})

    assert response.status_code == 200
    assert item_route.call_count == 2
    assert sleep.await_count == 1
    assert 2.9 <= sleep.await_args.args[0] <= 3.0


@pytest.mark.asyncio
@respx.mock
async def test_allegro_traffic_uses_rolling_30_day_offer_stats():
    respx.get("https://api.allegro.pl/sale/offers").mock(
        return_value=Response(
            200,
            json={
                "offers": [
                    {
                        "id": "offer-1",
                        "name": "Product",
                        "category": {"id": "257110"},
                        "external": {"id": "SKU-1"},
                        "publication": {"marketplaces": {"base": {"id": "allegro-pl"}}},
                        "stats": {"visitsCount": 32, "watchersCount": 2},
                        "stock": {"sold": 4},
                    }
                ],
                "totalCount": 1,
            },
        )
    )
    respx.get("https://api.allegro.pl/sale/user-ratings").mock(
        return_value=Response(
            200,
            json={
                "ratings": [
                    {
                        "recommended": False,
                        "excludedFromAverageRates": False,
                        "createdAt": "2026-07-06T12:00:00Z",
                        "order": {"offers": [{"id": "offer-1"}]},
                    }
                ]
            },
        )
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"base_url": "https://api.allegro.pl"},
    )

    rows = await connector.fetch_traffic(datetime(2026, 7, 6), datetime(2026, 7, 12))

    assert rows[0]["grain"] == "rolling_30d"
    assert rows[0]["region"] == "allegro-pl"
    assert rows[0]["clicks"] == 32
    assert rows[0]["orders"] == 4
    assert rows[0]["units_sold"] == 4
    assert rows[0]["negative_reviews"] == 1
    assert rows[0]["raw_data"]["negative_reviews_source"] == "allegro_user_ratings"
    assert rows[0]["raw_data"]["negative_reviews_daily"] == {"2026-07-06": 1}
    assert rows[0]["raw_data"]["platform_category_id"] == "257110"
    assert rows[0]["impressions"] is None


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_traffic_returns_selected_and_previous_periods():
    respx.post("https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "products": [
                        {
                            "product": {
                                "nmId": 10,
                                "vendorCode": "SKU-1",
                                "title": "Product",
                                "subjectId": 8416,
                                "subjectName": "Inflatable pools",
                            },
                            "statistic": {
                                "selected": {"openCardCount": 50, "addToCartCount": 7, "ordersCount": 2, "ordersSumRub": 1000},
                                "past": {"openCardCount": 40, "addToCartCount": 5, "ordersCount": 1, "ordersSumRub": 500},
                            },
                        }
                    ],
                    "isNextPage": False,
                }
            },
        )
    )
    respx.get("https://feedbacks-api.wildberries.ru/api/v1/feedbacks").mock(
        side_effect=[
            Response(
                200,
                json={
                    "data": {
                        "feedbacks": [
                            {
                                "createdDate": "2026-07-06T12:00:00Z",
                                "productValuation": 1,
                                "productDetails": {"nmId": 10, "supplierArticle": "SKU-1"},
                            }
                        ]
                    }
                },
            ),
            Response(200, json={"data": {"feedbacks": []}}),
        ]
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {"base_url": "https://marketplace-api.wildberries.ru"},
    )

    rows = await connector.fetch_traffic(datetime(2026, 7, 6), datetime(2026, 7, 12))

    assert len(rows) == 2
    assert rows[0]["period_start"] == "2026-07-06"
    assert rows[0]["clicks"] == 50
    assert rows[1]["period_end"] == "2026-07-05"
    assert rows[1]["orders"] == 1
    assert rows[0]["negative_reviews"] == 1
    assert rows[1]["negative_reviews"] == 0
    assert rows[0]["raw_data"]["negative_reviews_daily"] == {"2026-07-06": 1}
    assert rows[0]["raw_data"]["platform_category_id"] == "8416"
    assert rows[0]["raw_data"]["platform_category_name"] == "Inflatable pools"
