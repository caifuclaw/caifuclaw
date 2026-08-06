from datetime import datetime

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    deep_get,
    first_value,
    hmac_sha256_hex,
    label_from_platform_response,
    product_payload,
    response_data,
    unix_seconds,
)


class ShopeeConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "shopee"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.partner_id = str(self.credentials.get("partner_id") or self.settings.get("partner_id") or "")
        self.partner_key = str(self.credentials.get("partner_key") or "")
        self.shop_id = str(self.credentials.get("shop_id") or self.settings.get("shop_id") or self.settings.get("account_id") or "")
        self.access_token = str(self.credentials.get("access_token") or "")
        self.base_url = str(self.settings.get("base_url") or "https://partner.shopeemobile.com").rstrip("/")
        self.account_id = str(self.settings.get("account_id") or self.shop_id)

    def _signed_params(self, path: str, *, public: bool = False) -> dict:
        timestamp = unix_seconds()
        base = f"{self.partner_id}{path}{timestamp}"
        params = {"partner_id": int(self.partner_id) if self.partner_id.isdigit() else self.partner_id, "timestamp": timestamp}
        if not public:
            base += f"{self.access_token}{self.shop_id}"
            params.update({"access_token": self.access_token, "shop_id": int(self.shop_id) if self.shop_id.isdigit() else self.shop_id})
        params["sign"] = hmac_sha256_hex(self.partner_key, base)
        return params

    async def _get(self, path: str, params: dict | None = None, *, public: bool = False, binary: bool = False):
        signed = self._signed_params(path, public=public)
        if params:
            signed.update(params)
        return await self._request("GET", f"{self.base_url}{path}", params=signed, binary=binary)

    async def _post(self, path: str, payload: dict, *, public: bool = False, binary: bool = False):
        return await self._request(
            "POST",
            f"{self.base_url}{path}",
            params=self._signed_params(path, public=public),
            json_body=payload,
            binary=binary,
        )

    @staticmethod
    def _items(order: dict) -> list[dict]:
        items = []
        for key in ("item_list", "items", "order_items", "products"):
            items.extend(item for item in as_list(order.get(key)) if isinstance(item, dict))
        return items

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_sn = str(first_value(order.get("order_sn"), order.get("ordersn"), order.get("order_id")) or "")
        if not order_sn:
            return None
        package = first_value(
            deep_get(order, "package_list.0.package_number"),
            deep_get(order, "package_list.0.package_sn"),
            order.get("package_number"),
            order.get("package_sn"),
            order_sn,
        )
        shipping = order.get("shipping") if isinstance(order.get("shipping"), dict) else {}
        products = [
            product_payload(
                item,
                sku_keys=("model_sku", "item_sku", "seller_sku", "sku", "model.model_sku", "item.item_sku"),
                name_keys=("item_name", "model_name", "name", "item.item_name", "model.model_name"),
                quantity_keys=("model_quantity_purchased", "quantity", "item_quantity", "amount"),
                price_keys=("model_discounted_price", "model_original_price", "price", "item_price"),
                currency_keys=("currency", "price.currency", "model_discounted_price.currency"),
            )
            for item in self._items(order)
        ]
        tracking = first_value(
            order.get("tracking_number"),
            order.get("tracking_no"),
            shipping.get("tracking_number"),
            shipping.get("tracking_no"),
            deep_get(order, "package_list.0.logistics_status"),
        )
        currency = first_value(order.get("currency"), *(item.get("currency_code") for item in products))
        raw_payload = {
            **order,
            "id": order_sn,
            "site": first_value(self.settings.get("region"), order.get("region"), "shopee"),
            "created_at": first_value(order.get("create_time"), order.get("update_time")),
            "order_date": first_value(order.get("pay_time"), order.get("create_time")),
            "payment_at": order.get("pay_time"),
            "shipping_deadline_at": first_value(order.get("ship_by_date"), order.get("days_to_ship")),
            "buyer_selected_logistics": first_value(order.get("shipping_carrier"), order.get("logistics_channel_id")),
            "tracking_number": tracking,
            "shipment_tracking_number": tracking,
            "country_code": first_value(order.get("recipient_address", {}).get("region") if isinstance(order.get("recipient_address"), dict) else None, self.settings.get("region")),
            "currency_code": currency,
            "order_amount": first_value(order.get("total_amount"), order.get("estimated_shipping_fee"), order.get("actual_shipping_fee")),
            "products": products,
            "items": products,
            "fulfillment_type": first_value(order.get("fulfillment_type"), "FBS"),
        }
        return NormalizedOrder(
            platform_order_id=order_sn,
            platform_order_no=order_sn,
            posting_number=str(package or order_sn),
            platform_status=str(first_value(order.get("order_status"), order.get("status")) or ""),
            fulfillment_type=str(raw_payload["fulfillment_type"]),
            is_overseas_warehouse=False,
            raw_payload=raw_payload,
        )

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        path = str(self.settings.get("order_list_path") or "/api/v2/order/get_order_list")
        detail_path = str(self.settings.get("order_detail_path") or "/api/v2/order/get_order_detail")
        statuses = list(self.settings.get("pull_order_statuses") or ["READY_TO_SHIP", "PROCESSED"])
        page_size = int(self.settings.get("page_size") or 50)
        time_field = str(self.settings.get("time_field") or "update_time")
        detail_fields = str(
            self.settings.get("response_optional_fields")
            or "buyer_user_id,buyer_username,recipient_address,item_list,package_list,shipping_carrier,pay_time,ship_by_date,total_amount,currency"
        )
        orders: list[NormalizedOrder] = []
        for status in statuses:
            cursor = ""
            while True:
                params = {"page_size": page_size, "order_status": status, "time_range_field": time_field}
                if since:
                    params["time_from"] = int(since.timestamp())
                    params["time_to"] = unix_seconds()
                if cursor:
                    params["cursor"] = cursor
                data = await self._get(path, params)
                payload = response_data(data)
                order_list = payload.get("order_list") if isinstance(payload, dict) else []
                order_sns = [str(item.get("order_sn") or item.get("ordersn") or item.get("order_id") or "") for item in as_list(order_list)]
                order_sns = [item for item in order_sns if item]
                if order_sns:
                    detail = await self._get(detail_path, {"order_sn_list": ",".join(order_sns), "response_optional_fields": detail_fields})
                    detail_payload = response_data(detail)
                    detail_orders = detail_payload.get("order_list") if isinstance(detail_payload, dict) else []
                    for order in as_list(detail_orders):
                        if isinstance(order, dict):
                            normalized = self._normalize_order(order)
                            if normalized:
                                orders.append(normalized)
                cursor = str(payload.get("next_cursor") or "") if isinstance(payload, dict) else ""
                if not cursor or not bool(payload.get("more")):
                    break
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        order_sns = [str(value).strip() for value in posting_numbers if str(value or "").strip()]
        if not order_sns:
            return []
        detail_path = str(self.settings.get("order_detail_path") or "/api/v2/order/get_order_detail")
        data = await self._get(detail_path, {"order_sn_list": ",".join(order_sns), "response_optional_fields": "package_list,shipping_carrier"})
        payload = response_data(data)
        updates: list[OrderStatusUpdate] = []
        for order in as_list(payload.get("order_list") if isinstance(payload, dict) else []):
            if not isinstance(order, dict):
                continue
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
        order_sn = order.platform_order_id
        if self._dry_run():
            return ShipmentResult(order_sn, str(order.raw_payload.get("tracking_number") or order.posting_number or order_sn), "Shopee", "dry_run_created", order.raw_payload)
        path = str(self.settings.get("ship_order_path") or "/api/v2/logistics/ship_order")
        payload = dict(self.settings.get("ship_order_payload_template") or {})
        payload.setdefault("order_sn", order_sn)
        if order.posting_number and order.posting_number != order_sn:
            payload.setdefault("package_number", order.posting_number)
        data = await self._post(path, payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("package_number"), raw.get("order_sn"), order.posting_number, order_sn)),
            tracking_number=str(first_value(raw.get("tracking_number"), order.raw_payload.get("tracking_number"), order.posting_number, order_sn)),
            carrier=str(first_value(raw.get("shipping_carrier"), order.raw_payload.get("buyer_selected_logistics"), "Shopee")),
            status=str(first_value(raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("Shopee Label Preview", shipment, order)
        create_path = str(self.settings.get("create_shipping_document_path") or "/api/v2/logistics/create_shipping_document")
        result_path = str(self.settings.get("shipping_document_result_path") or "/api/v2/logistics/get_shipping_document_result")
        download_path = str(self.settings.get("download_shipping_document_path") or "/api/v2/logistics/download_shipping_document")
        package_number = order.posting_number if order.posting_number and order.posting_number != order.platform_order_id else ""
        doc_type = str(self.settings.get("shipping_document_type") or "THERMAL_AIR_WAYBILL")
        order_payload = {"order_sn": order.platform_order_id}
        if package_number:
            order_payload["package_number"] = package_number
        await self._post(create_path, {"shipping_document_type": doc_type, "order_list": [order_payload]})
        attempts = int(self.settings.get("shipping_document_poll_attempts") or 3)
        last_result = {}
        for _ in range(max(1, attempts)):
            result = await self._post(result_path, {"shipping_document_type": doc_type, "order_list": [order_payload]})
            last_result = response_data(result) if isinstance(result, dict) else {}
            entries = as_list(last_result.get("result_list") if isinstance(last_result, dict) else [])
            if not entries or str(first_value(entries[0].get("status"), entries[0].get("result")) or "").upper() in {"READY", "SUCCESS"}:
                break
        content = await self._post(download_path, {"shipping_document_type": doc_type, "order_list": [order_payload]}, binary=True)
        try:
            return label_from_platform_response(content)
        except RuntimeError as exc:
            raise RuntimeError(f"Shopee shipping document is not ready: {last_result}") from exc
