# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import re

import pytest
import respx
from httpx import Response

from app.adapters.aliexpress import AliExpressConnector
from app.adapters.amazon import AmazonConnector
from app.adapters.base import ShipmentResult
from app.adapters.lazada import LazadaConnector
from app.adapters.shopee import ShopeeConnector
from app.adapters.tiktok_shop import TikTokShopConnector
from app.factory import canonical_platform, connector_for


def test_new_platforms_registered_in_factory():
    assert canonical_platform("tiktokshop") == "tiktok_shop"
    assert canonical_platform("ali_express") == "aliexpress"
    assert connector_for("amazon", {"access_token": "x", "aws_access_key_id": "ak", "aws_secret_access_key": "sk"}, {"base_url": "https://sellingpartnerapi-na.amazon.com", "marketplace_ids": ["ATVPDKIKX0DER"]}).platform == "amazon"
    assert connector_for("shopee", {"partner_id": "1", "partner_key": "k", "shop_id": "2", "access_token": "t"}, {"base_url": "https://partner.shopeemobile.com"}).platform == "shopee"
    assert connector_for("tiktok_shop", {"app_key": "k", "app_secret": "s", "shop_cipher": "c", "access_token": "t"}, {"base_url": "https://open-api.tiktokglobalshop.com"}).platform == "tiktok_shop"
    assert connector_for("aliexpress", {"app_key": "k", "app_secret": "s", "access_token": "t"}, {"base_url": "https://api-sg.aliexpress.com/sync"}).platform == "aliexpress"
    assert connector_for("lazada", {"app_key": "k", "app_secret": "s", "access_token": "t"}, {"base_url": "https://api.lazada.com/rest"}).platform == "lazada"


@pytest.mark.asyncio
@respx.mock
async def test_shopee_fetch_orders_and_preview_label():
    list_route = respx.get("https://partner.shopeemobile.com/api/v2/order/get_order_list").mock(
        return_value=Response(200, json={"response": {"order_list": [{"order_sn": "SP-1"}], "more": False}})
    )
    detail_route = respx.get("https://partner.shopeemobile.com/api/v2/order/get_order_detail").mock(
        return_value=Response(
            200,
            json={
                "response": {
                    "order_list": [
                        {
                            "order_sn": "SP-1",
                            "order_status": "READY_TO_SHIP",
                            "currency": "SGD",
                            "pay_time": 1760000000,
                            "package_list": [{"package_number": "PKG-1"}],
                            "item_list": [
                                {
                                    "item_sku": "SKU-1",
                                    "item_name": "Shopee Item",
                                    "model_quantity_purchased": 2,
                                    "model_discounted_price": "12.50",
                                }
                            ],
                        }
                    ]
                }
            },
        )
    )
    connector = ShopeeConnector(
        {"partner_id": "100", "partner_key": "secret", "shop_id": "200", "access_token": "token"},
        {"base_url": "https://partner.shopeemobile.com", "dry_run_fulfillment": True, "pull_order_statuses": ["READY_TO_SHIP"]},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("PKG-1", "PKG-1"), orders[0])

    assert list_route.called
    assert detail_route.called
    assert orders[0].platform_order_id == "SP-1"
    assert orders[0].posting_number == "PKG-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "SKU-1"
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_tiktok_fetch_orders_and_preview_label():
    search_route = respx.post("https://open-api.tiktokglobalshop.com/order/202309/orders/search").mock(
        return_value=Response(200, json={"data": {"orders": [{"order_id": "TT-1"}]}})
    )
    detail_route = respx.get("https://open-api.tiktokglobalshop.com/order/202309/orders").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "orders": [
                        {
                            "order_id": "TT-1",
                            "order_status": "AWAITING_SHIPMENT",
                            "packages": [{"package_id": "TT-PKG-1"}],
                            "line_items": [{"seller_sku": "DEMO-SKU-0036", "product_name": "TikTok Item", "quantity": 1}],
                        }
                    ]
                }
            },
        )
    )
    connector = TikTokShopConnector(
        {"app_key": "app", "app_secret": "secret", "shop_cipher": "cipher", "access_token": "token"},
        {"base_url": "https://open-api.tiktokglobalshop.com", "dry_run_fulfillment": True, "pull_order_statuses": ["AWAITING_SHIPMENT"]},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("TT-PKG-1", "TT-PKG-1"), orders[0])

    assert search_route.called
    assert detail_route.called
    assert orders[0].platform_order_id == "TT-1"
    assert orders[0].posting_number == "TT-PKG-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0036"
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_aliexpress_fetch_orders_and_preview_label():
    route = respx.post("https://api-sg.aliexpress.com/sync").mock(
        side_effect=[
            Response(200, json={"result": {"order_list": [{"order_id": "AE-1"}]}}),
            Response(
                200,
                json={
                    "result": {
                        "order_id": "AE-1",
                        "order_status": "WAIT_SELLER_SEND_GOODS",
                        "child_order_list": [{"sku_code": "SKU-AE", "product_name": "Ali Item", "product_count": 3}],
                    }
                },
            ),
        ]
    )
    connector = AliExpressConnector(
        {"app_key": "app", "app_secret": "secret", "access_token": "token"},
        {"base_url": "https://api-sg.aliexpress.com/sync", "dry_run_fulfillment": True, "pull_order_statuses": ["WAIT_SELLER_SEND_GOODS"]},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("AE-1", "AE-1"), orders[0])

    assert route.call_count == 2
    assert orders[0].platform_order_id == "AE-1"
    assert orders[0].platform_status == "WAIT_SELLER_SEND_GOODS"
    assert orders[0].raw_payload["products"][0]["sku"] == "SKU-AE"
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_lazada_fetch_orders_and_preview_label():
    respx.post(url__regex=re.compile(r"https://api\.lazada\.com/rest/.*")).mock(
        side_effect=[
            Response(200, json={"data": {"orders": [{"order_id": "LZ-1", "order_number": "LZ-NO-1"}]}}),
            Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "order_item_id": "ITEM-1",
                                "package_id": "PKG-LZ-1",
                                "seller_sku": "DEMO-SKU-0037",
                                "name": "Lazada Item",
                                "paid_price": "9.90",
                                "currency": "SGD",
                                "status": "ready_to_ship",
                            }
                        ]
                    }
                },
            ),
        ]
    )
    connector = LazadaConnector(
        {"app_key": "app", "app_secret": "secret", "access_token": "token"},
        {"base_url": "https://api.lazada.com/rest", "dry_run_fulfillment": True, "pull_order_statuses": ["ready_to_ship"]},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("PKG-LZ-1", "PKG-LZ-1"), orders[0])

    assert orders[0].platform_order_id == "LZ-1"
    assert orders[0].platform_order_no == "LZ-NO-1"
    assert orders[0].posting_number == "PKG-LZ-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0037"
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_amazon_fetch_orders_and_preview_label():
    orders_route = respx.get("https://sellingpartnerapi-na.amazon.com/orders/v0/orders").mock(
        return_value=Response(
            200,
            json={
                "payload": {
                    "Orders": [
                        {
                            "AmazonOrderId": "AMZ-1",
                            "OrderStatus": "Unshipped",
                            "PurchaseDate": "2026-06-01T00:00:00Z",
                            "LatestShipDate": "2026-06-03T00:00:00Z",
                            "OrderTotal": {"Amount": "20.00", "CurrencyCode": "USD"},
                        }
                    ]
                }
            },
        )
    )
    items_route = respx.get("https://sellingpartnerapi-na.amazon.com/orders/v0/orders/AMZ-1/orderItems").mock(
        return_value=Response(
            200,
            json={"payload": {"OrderItems": [{"SellerSKU": "DEMO-SKU-0038", "Title": "Amazon Item", "QuantityOrdered": 1, "ItemPrice": {"Amount": "20.00", "CurrencyCode": "USD"}}]}},
        )
    )
    connector = AmazonConnector(
        {"access_token": "lwa-token", "aws_access_key_id": "AKIA_TEST", "aws_secret_access_key": "secret", "seller_id": "seller"},
        {"base_url": "https://sellingpartnerapi-na.amazon.com", "dry_run_fulfillment": True, "marketplace_ids": ["ATVPDKIKX0DER"]},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("AMZ-1", "AMZ-1"), orders[0])

    assert orders_route.called
    assert items_route.called
    assert "Authorization" in orders_route.calls[0].request.headers
    assert orders[0].platform_order_id == "AMZ-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0038"
    assert label.content.startswith(b"%PDF")
