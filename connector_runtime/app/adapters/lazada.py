from datetime import datetime
from urllib.parse import urlencode

from .alibaba_common import AlibabaTopConnector
from .base import LabelResult, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    as_list,
    deep_get,
    extract_items,
    first_value,
    label_from_platform_response,
    product_payload,
    response_data,
)


class LazadaConnector(AlibabaTopConnector):
    platform = "lazada"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        super().__init__(credentials, settings)
        if not self.base_url:
            self.base_url = "https://api.lazada.com/rest"

    def _common_params(self, method: str, extra: dict | None = None) -> dict:
        params = super()._common_params(method, extra)
        if self.access_token:
            params.pop("session", None)
            params["access_token"] = self.access_token
        return params

    def _sign(self, params: dict) -> str:
        import hashlib
        import hmac

        api_path = str(params.get("api_path") or "")
        source = api_path + "".join(f"{key}{params[key]}" for key in sorted(params) if key not in {"sign", "api_path"})
        return hmac.new(self.app_secret.encode("utf-8"), source.encode("utf-8"), hashlib.sha256).hexdigest().upper()

    async def _top_post(self, method: str, params: dict | None = None, *, binary: bool = False):
        url = f"{self.base_url}{method}" if method.startswith("/") else self.base_url
        if method.startswith("/"):
            all_params = {
                "app_key": self.app_key,
                "sign_method": self.sign_method,
                "timestamp": self._format_time(),
                "format": "json",
                "v": str(self.settings.get("api_version") or "2.0"),
                **(params or {}),
            }
            if self.access_token:
                all_params["access_token"] = self.access_token
            all_params["sign"] = self._sign({**all_params, "api_path": method})
            query = urlencode(sorted(all_params.items()), doseq=True)
            url = f"{url}?{query}" if query else url
            return await self._request(
                "POST",
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
                data={},
                binary=binary,
            )
        all_params = self._common_params(method, params)
        return await super()._top_post(method, params, binary=binary)

    @staticmethod
    def _item_rows(order: dict) -> list[dict]:
        rows = []
        for key in ("items", "order_items", "order_items_list", "products"):
            rows.extend(item for item in as_list(order.get(key)) if isinstance(item, dict))
        return rows

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("order_id"), order.get("id")) or "")
        if not order_id:
            return None
        items = self._item_rows(order)
        first_item = items[0] if items else {}
        package_id = str(
            first_value(
                first_item.get("package_id"),
                first_item.get("order_item_id"),
                order.get("package_id"),
                order.get("order_item_id"),
                deep_get(order, "packages.0.package_id"),
                order_id,
            )
            or ""
        )
        products = [
            product_payload(
                item,
                sku_keys=("seller_sku", "sku", "Sku", "shop_sku", "item_sku"),
                name_keys=("name", "item_name", "product_name", "title"),
                quantity_keys=("quantity", "qty", "item_quantity"),
                price_keys=("paid_price", "item_price", "price", "unit_price"),
                currency_keys=("currency", "currency_code", "price.currency"),
            )
            for item in items
        ]
        address = first_value(order.get("address_shipping"), order.get("shipping_address"), order.get("recipient_address"), {})
        address = address if isinstance(address, dict) else {}
        tracking = first_value(
            first_item.get("tracking_code"),
            first_item.get("tracking_number"),
            order.get("tracking_code"),
            order.get("tracking_number"),
        )
        raw_payload = {
            **order,
            "id": order_id,
            "site": first_value(self.settings.get("region"), order.get("country"), "lazada"),
            "created_at": first_value(order.get("created_at"), order.get("create_time")),
            "order_date": first_value(order.get("created_at"), order.get("payment_time"), order.get("updated_at")),
            "payment_at": first_value(order.get("payment_time"), order.get("created_at")),
            "shipping_deadline_at": first_value(first_item.get("ship_before"), order.get("ship_before"), order.get("sla_time_stamp")),
            "buyer_selected_logistics": first_value(first_item.get("shipment_provider"), order.get("shipment_provider"), order.get("shipping_type")),
            "shipment_tracking_number": tracking,
            "tracking_number": tracking,
            "country_code": first_value(address.get("country_code"), order.get("country_code"), self.settings.get("region")),
            "order_amount": first_value(order.get("price"), order.get("total_price"), order.get("paid_price")),
            "currency_code": first_value(order.get("currency"), order.get("currency_code"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": first_value(first_item.get("warehouse_code"), order.get("fulfillment_type"), "FBS"),
        }
        status = str(first_value(first_item.get("status"), order.get("statuses"), order.get("status")) or "")
        if isinstance(order.get("statuses"), list):
            status = str(first_value(*order.get("statuses")) or status)
        fulfillment_type = str(raw_payload["fulfillment_type"])
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=str(first_value(order.get("order_number"), order_id)),
            posting_number=package_id,
            platform_status=status,
            fulfillment_type=fulfillment_type,
            is_overseas_warehouse=fulfillment_type.upper() in {"FBL", "FULFILLMENT", "LAZADA_FULFILLMENT"},
            raw_payload=raw_payload,
        )

    async def _fetch_order_items(self, order_id: str) -> list[dict]:
        method = str(self.settings.get("order_items_method") or "/order/items/get")
        data = await self._top_post(method, {"order_id": order_id})
        payload = response_data(data)
        rows = extract_items(payload if isinstance(payload, dict) else {}, "items", "data", "order_items")
        return rows

    async def _fetch_order(self, order_id: str) -> dict:
        method = str(self.settings.get("order_detail_method") or "/order/get")
        data = await self._top_post(method, {"order_id": order_id})
        payload = response_data(data)
        return payload if isinstance(payload, dict) else {}

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        method = str(self.settings.get("order_list_method") or "/orders/get")
        statuses = list(self.settings.get("pull_order_statuses") or ["pending", "ready_to_ship", "packed"])
        page_size = int(self.settings.get("page_size") or 50)
        orders: list[NormalizedOrder] = []
        for status in statuses:
            offset = 0
            while True:
                params = {
                    "status": status,
                    "limit": page_size,
                    "offset": offset,
                    **self._timestamp_filter(since, "created_after", "created_before"),
                }
                data = await self._top_post(method, params)
                payload = response_data(data)
                rows = extract_items(payload if isinstance(payload, dict) else {}, "orders", "data.orders", "items")
                if not rows:
                    break
                for row in rows:
                    order_id = str(first_value(row.get("order_id"), row.get("id")) or "")
                    detail = await self._fetch_order(order_id) if bool(self.settings.get("fetch_order_details", False)) and order_id else {}
                    items = await self._fetch_order_items(order_id) if bool(self.settings.get("fetch_order_items", True)) and order_id else []
                    merged = {**row, **detail}
                    if items:
                        merged["items"] = items
                    normalized = self._normalize_order(merged)
                    if normalized:
                        orders.append(normalized)
                if len(rows) < page_size:
                    break
                offset += page_size
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for order_id in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            detail = await self._fetch_order(order_id)
            items = await self._fetch_order_items(order_id) if bool(self.settings.get("fetch_order_items", True)) else []
            if items:
                detail["items"] = items
            normalized = self._normalize_order(detail)
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
            return ShipmentResult(order.posting_number or order.platform_order_id, str(order.raw_payload.get("tracking_number") or order.posting_number or order.platform_order_id), "Lazada", "dry_run_created", order.raw_payload)
        method = str(self.settings.get("ready_to_ship_method") or "/order/rts")
        payload = {
            "order_item_ids": self.settings.get("order_item_ids") or order.raw_payload.get("order_item_ids") or order.posting_number,
            "delivery_type": self.settings.get("delivery_type", "dropship"),
            "shipping_provider": self.settings.get("shipping_provider", ""),
            **dict(self.settings.get("shipment_payload_template") or {}),
        }
        data = await self._top_post(method, payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("package_id"), raw.get("tracking_code"), order.posting_number, order.platform_order_id)),
            tracking_number=str(first_value(raw.get("tracking_code"), raw.get("tracking_number"), order.raw_payload.get("tracking_number"), order.posting_number)),
            carrier=str(first_value(raw.get("shipment_provider"), payload.get("shipping_provider"), "Lazada")),
            status=str(first_value(raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("Lazada Label Preview", shipment, order)
        method = str(self.settings.get("label_method") or "/order/document/get")
        params = {
            "doc_type": self.settings.get("doc_type", "shippingLabel"),
            "order_item_ids": self.settings.get("order_item_ids") or order.raw_payload.get("order_item_ids") or order.posting_number,
            **dict(self.settings.get("label_payload_template") or {}),
        }
        data = await self._top_post(method, params, binary=bool(self.settings.get("label_binary_response", False)))
        return label_from_platform_response(data)
