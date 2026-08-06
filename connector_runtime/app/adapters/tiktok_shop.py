from datetime import datetime

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    compact_json,
    deep_get,
    first_value,
    hmac_sha256_hex,
    label_from_platform_response,
    product_payload,
    response_data,
    unix_seconds,
)


class TikTokShopConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "tiktok_shop"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.app_key = str(self.credentials.get("app_key") or self.credentials.get("client_id") or "")
        self.app_secret = str(self.credentials.get("app_secret") or self.credentials.get("client_secret") or "")
        self.access_token = str(self.credentials.get("access_token") or "")
        self.shop_cipher = str(self.credentials.get("shop_cipher") or self.settings.get("shop_cipher") or self.settings.get("account_id") or "")
        self.base_url = str(self.settings.get("base_url") or "https://open-api.tiktokglobalshop.com").rstrip("/")
        self.account_id = str(self.settings.get("account_id") or self.shop_cipher)

    def _signed_params(self, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        query = {
            "app_key": self.app_key,
            "timestamp": unix_seconds(),
            **(params or {}),
        }
        if self.shop_cipher:
            query.setdefault("shop_cipher", self.shop_cipher)
        sign_source = path
        for key in sorted(k for k in query if k not in {"sign", "access_token"}):
            sign_source += f"{key}{query[key]}"
        if body:
            sign_source += compact_json(body)
        sign_source = f"{self.app_secret}{sign_source}{self.app_secret}"
        query["sign"] = hmac_sha256_hex(self.app_secret, sign_source)
        return query

    @property
    def headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-tts-access-token": self.access_token,
        }

    async def _get(self, path: str, params: dict | None = None, *, binary: bool = False):
        return await self._request("GET", f"{self.base_url}{path}", headers=self.headers, params=self._signed_params(path, params), binary=binary)

    async def _post(self, path: str, payload: dict, params: dict | None = None, *, binary: bool = False):
        return await self._request(
            "POST",
            f"{self.base_url}{path}",
            headers=self.headers,
            params=self._signed_params(path, params, payload),
            json_body=payload,
            binary=binary,
        )

    @staticmethod
    def _order_items(order: dict) -> list[dict]:
        items: list[dict] = []
        for key in ("line_items", "lineItems", "items", "order_items", "skus", "products"):
            items.extend(item for item in as_list(order.get(key)) if isinstance(item, dict))
        for package in as_list(order.get("packages")):
            if isinstance(package, dict):
                items.extend(item for item in as_list(package.get("items")) if isinstance(item, dict))
        return items

    @staticmethod
    def _first_package(order: dict) -> dict:
        return next((item for item in as_list(order.get("packages")) if isinstance(item, dict)), {})

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("order_id"), order.get("id"), order.get("orderId")) or "")
        if not order_id:
            return None
        package = self._first_package(order)
        package_id = str(first_value(package.get("package_id"), package.get("id"), order.get("package_id"), order.get("fulfillment_id"), order_id) or "")
        recipient = first_value(order.get("recipient_address"), order.get("shipping_address"), order.get("delivery_address"), {})
        recipient = recipient if isinstance(recipient, dict) else {}
        products = [
            product_payload(
                item,
                sku_keys=("seller_sku", "sku_id", "sku", "product_sku", "inventory_item_id"),
                name_keys=("product_name", "product_title", "name", "title"),
                quantity_keys=("quantity", "qty", "item_quantity"),
                price_keys=("sale_price.amount", "sale_price", "original_price.amount", "price.amount", "price"),
                currency_keys=("sale_price.currency", "original_price.currency", "price.currency", "currency"),
            )
            for item in self._order_items(order)
        ]
        shipment = first_value(order.get("shipping"), order.get("shipment"), package.get("shipping"), {})
        shipment = shipment if isinstance(shipment, dict) else {}
        tracking = first_value(
            order.get("tracking_number"),
            package.get("tracking_number"),
            shipment.get("tracking_number"),
            shipment.get("trackingNumber"),
        )
        status = str(first_value(order.get("order_status"), order.get("status"), package.get("fulfillment_status"), package.get("status")) or "")
        fulfillment_type = str(first_value(order.get("fulfillment_type"), package.get("fulfillment_type"), shipment.get("shipping_type"), "FBS"))
        raw_payload = {
            **order,
            "id": order_id,
            "site": first_value(self.settings.get("region"), order.get("region"), "tiktok_shop"),
            "created_at": first_value(order.get("create_time"), order.get("created_time"), order.get("created_at")),
            "order_date": first_value(order.get("paid_time"), order.get("create_time"), order.get("created_at")),
            "payment_at": first_value(order.get("paid_time"), order.get("payment_time")),
            "shipping_deadline_at": first_value(order.get("shipping_due_time"), order.get("dispatch_by_time"), package.get("shipping_due_time")),
            "buyer_selected_logistics": first_value(order.get("shipping_provider"), order.get("delivery_option"), shipment.get("provider")),
            "shipment_tracking_number": tracking,
            "tracking_number": tracking,
            "country_code": first_value(recipient.get("country_code"), recipient.get("region_code"), order.get("country_code")),
            "order_amount": first_value(deep_get(order, "payment.total_amount"), deep_get(order, "total_amount.amount"), order.get("total_amount")),
            "currency_code": first_value(deep_get(order, "payment.currency"), deep_get(order, "total_amount.currency"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": fulfillment_type,
        }
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=str(first_value(order.get("order_number"), order.get("display_order_id"), order_id)),
            posting_number=package_id,
            platform_status=status,
            fulfillment_type=fulfillment_type,
            is_overseas_warehouse=fulfillment_type.upper() in {"FBT", "FBO", "FULFILLMENT"},
            raw_payload=raw_payload,
        )

    def _detail_path(self) -> str:
        return str(self.settings.get("order_detail_path") or "/order/202309/orders")

    async def _fetch_order_details(self, order_ids: list[str]) -> list[dict]:
        if not order_ids:
            return []
        detail_path = self._detail_path()
        data = await self._get(detail_path, {"ids": ",".join(order_ids)})
        payload = response_data(data)
        if isinstance(payload, dict):
            for key in ("orders", "order_list", "items", "list"):
                if isinstance(payload.get(key), list):
                    return [item for item in payload[key] if isinstance(item, dict)]
        return []

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        search_path = str(self.settings.get("order_search_path") or "/order/202309/orders/search")
        statuses = list(self.settings.get("pull_order_statuses") or ["AWAITING_SHIPMENT", "AWAITING_COLLECTION", "IN_TRANSIT"])
        page_size = int(self.settings.get("page_size") or 50)
        body = {"page_size": page_size, "order_status": statuses}
        if since:
            body["create_time_ge"] = int(since.timestamp())
        cursor = ""
        orders: list[NormalizedOrder] = []
        while True:
            payload = dict(body)
            if cursor:
                payload["cursor"] = cursor
            data = await self._post(search_path, payload)
            response = response_data(data)
            rows = []
            if isinstance(response, dict):
                rows = [item for item in as_list(first_value(response.get("orders"), response.get("order_list"), response.get("items"), response.get("list"))) if isinstance(item, dict)]
            order_ids = [str(first_value(row.get("order_id"), row.get("id")) or "") for row in rows]
            detail_rows = await self._fetch_order_details([item for item in order_ids if item]) if bool(self.settings.get("fetch_order_details", True)) else []
            for order in detail_rows or rows:
                normalized = self._normalize_order(order)
                if normalized:
                    orders.append(normalized)
            cursor = str(first_value(response.get("next_cursor"), response.get("cursor")) or "") if isinstance(response, dict) else ""
            if not cursor:
                break
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        detail_rows = await self._fetch_order_details([str(item).strip() for item in posting_numbers if str(item or "").strip()])
        updates: list[OrderStatusUpdate] = []
        for order in detail_rows:
            normalized = self._normalize_order(order)
            if not normalized:
                continue
            updates.append(
                OrderStatusUpdate(
                    posting_number=normalized.posting_number,
                    platform_order_id=normalized.platform_order_id,
                    platform_order_no=normalized.platform_order_no,
                    platform_status=normalized.platform_status,
                    shipment_tracking_number=str(normalized.raw_payload.get("shipment_tracking_number") or ""),
                    raw_payload=normalized.raw_payload,
                )
            )
        return updates

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        if self._dry_run():
            return ShipmentResult(order.posting_number or order.platform_order_id, str(order.raw_payload.get("tracking_number") or order.posting_number or order.platform_order_id), "TikTok Shop", "dry_run_created", order.raw_payload)
        path_template = str(self.settings.get("ship_package_path") or "/fulfillment/202309/packages/{package_id}/ship")
        package_id = order.posting_number or order.platform_order_id
        payload = dict(self.settings.get("ship_package_payload_template") or {})
        payload.setdefault("tracking_number", first_value(order.raw_payload.get("tracking_number"), order.raw_payload.get("shipment_tracking_number"), ""))
        payload.setdefault("shipping_provider_id", self.settings.get("shipping_provider_id", ""))
        data = await self._post(path_template.format(package_id=package_id, order_id=order.platform_order_id), payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("package_id"), package_id)),
            tracking_number=str(first_value(raw.get("tracking_number"), payload.get("tracking_number"), package_id)),
            carrier=str(first_value(raw.get("shipping_provider"), payload.get("shipping_provider_id"), "TikTok Shop")),
            status=str(first_value(raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("TikTok Shop Label Preview", shipment, order)
        path_template = str(self.settings.get("shipping_document_path") or "/fulfillment/202309/packages/{package_id}/shipping_documents")
        path = path_template.format(package_id=shipment.platform_shipment_id or order.posting_number or order.platform_order_id, order_id=order.platform_order_id)
        data = await self._get(path, binary=True)
        return label_from_platform_response(data)
