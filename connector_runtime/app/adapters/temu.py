from datetime import datetime, timezone

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    compact_json,
    deep_get,
    extract_items,
    first_value,
    hmac_sha256_hex,
    label_from_platform_response,
    product_payload,
    response_data,
    unix_seconds,
)


class TemuConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "temu"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.app_key = str(first_value(self.credentials.get("app_key"), self.credentials.get("client_id")) or "")
        self.app_secret = str(first_value(self.credentials.get("app_secret"), self.credentials.get("client_secret")) or "")
        self.access_token = str(self.credentials.get("access_token") or "")
        self.refresh_token = str(self.credentials.get("refresh_token") or "")
        self.seller_id = str(self.credentials.get("seller_id") or self.settings.get("seller_id") or "")
        self.mall_id = str(self.credentials.get("mall_id") or self.settings.get("mall_id") or self.settings.get("account_id") or "")
        self.base_url = str(self.settings.get("base_url") or "https://openapi-b-us.temu.com").rstrip("/")
        self.region = str(self.settings.get("region") or "US")
        self.account_id = str(self.settings.get("account_id") or self.mall_id or self.seller_id)

    def _required_path(self, key: str) -> str:
        path = str(self.settings.get(key) or "")
        if not path:
            raise ValueError(f"Temu settings.{key} is required; confirm the path in Partner Platform before enabling sync")
        return path

    def _signed_params(self, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        query = {
            str(self.settings.get("app_key_param") or "app_key"): self.app_key,
            str(self.settings.get("timestamp_param") or "timestamp"): unix_seconds(),
            **dict(params or {}),
        }
        if self.access_token:
            query.setdefault(str(self.settings.get("access_token_param") or "access_token"), self.access_token)
        if self.mall_id:
            query.setdefault(str(self.settings.get("mall_id_param") or "mall_id"), self.mall_id)
        if self.region:
            query.setdefault(str(self.settings.get("region_param") or "region"), self.region)
        sign_source = ""
        if bool(self.settings.get("sign_include_path", False)):
            sign_source += path
        sign_source += "".join(f"{key}{query[key]}" for key in sorted(k for k in query if k != "sign"))
        if body is not None and bool(self.settings.get("sign_include_body", True)):
            sign_source += compact_json(body)
        secret_wrapped = bool(self.settings.get("sign_secret_wrap", True))
        if secret_wrapped:
            sign_source = f"{self.app_secret}{sign_source}{self.app_secret}"
        query[str(self.settings.get("sign_param") or "sign")] = hmac_sha256_hex(self.app_secret, sign_source).upper()
        return query

    @property
    def headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        token_header = str(self.settings.get("access_token_header") or "")
        if token_header and self.access_token:
            headers[token_header] = self.access_token
        return headers

    async def _api(self, method: str, path: str, *, params: dict | None = None, payload: dict | None = None, binary: bool = False):
        http_method = method.upper()
        return await self._request(
            http_method,
            f"{self.base_url}{path}",
            headers=self.headers,
            params=self._signed_params(path, params, payload),
            json_body=payload if http_method in {"POST", "PUT", "PATCH"} else None,
            binary=binary,
            timeout=90,
        )

    @staticmethod
    def _order_items(order: dict) -> list[dict]:
        return extract_items(order, "items", "order_items", "goods_list", "sku_list", "products", "package.items")

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("order_id"), order.get("parent_order_sn"), order.get("order_sn"), order.get("id")) or "")
        if not order_id:
            return None
        package = first_value(order.get("package"), order.get("shipment"), order.get("fulfillment"), {})
        package = package if isinstance(package, dict) else {}
        shipping = first_value(order.get("shipping"), order.get("shipping_info"), order.get("receiver"), {})
        shipping = shipping if isinstance(shipping, dict) else {}
        products = [
            product_payload(
                item,
                sku_keys=("seller_sku", "goods_sku", "product_sku", "sku", "sku_id"),
                name_keys=("goods_name", "product_name", "title", "name"),
                quantity_keys=("quantity", "qty", "item_quantity", "goods_quantity"),
                price_keys=("paid_price.amount", "item_price.amount", "price.amount", "paid_price", "item_price", "price"),
                currency_keys=("paid_price.currency", "item_price.currency", "price.currency", "currency"),
            )
            for item in self._order_items(order)
        ]
        tracking = first_value(
            order.get("tracking_number"),
            order.get("waybill_number"),
            package.get("tracking_number"),
            package.get("waybill_number"),
            deep_get(order, "shipping.tracking_number"),
        )
        status = str(first_value(order.get("order_status"), order.get("package_status"), order.get("status"), package.get("status")) or "")
        fulfillment_type = str(first_value(order.get("fulfillment_type"), package.get("fulfillment_type"), order.get("shipping_type"), "FBS"))
        raw_payload = {
            **order,
            "id": order_id,
            "order_number": first_value(order.get("order_sn"), order.get("parent_order_sn"), order_id),
            "package_id": first_value(package.get("package_id"), order.get("package_id"), order.get("fulfillment_id"), order_id),
            "site": self.region,
            "created_at": first_value(order.get("create_time"), order.get("created_at"), order.get("created_time")),
            "order_date": first_value(order.get("pay_time"), order.get("paid_at"), order.get("create_time")),
            "payment_at": first_value(order.get("pay_time"), order.get("paid_at"), order.get("payment_time")),
            "shipping_deadline_at": first_value(order.get("latest_ship_time"), order.get("ship_by_time"), order.get("delivery_sla"), package.get("latest_ship_time")),
            "buyer_selected_logistics": first_value(order.get("shipping_service"), order.get("logistics_channel"), package.get("logistics_channel")),
            "shipment_tracking_number": tracking,
            "tracking_number": tracking,
            "country_code": first_value(shipping.get("country_code"), shipping.get("region_code"), order.get("country_code")),
            "buyer_name": first_value(shipping.get("name"), shipping.get("receiver_name"), order.get("buyer_name")),
            "order_amount": first_value(deep_get(order, "paid_amount.amount"), order.get("paid_amount"), order.get("total_amount")),
            "currency_code": first_value(deep_get(order, "paid_amount.currency"), order.get("currency"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": fulfillment_type,
        }
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=str(first_value(order.get("order_sn"), order.get("parent_order_sn"), order_id)),
            posting_number=str(first_value(raw_payload["package_id"], order_id)),
            platform_status=status,
            fulfillment_type=fulfillment_type,
            is_overseas_warehouse=fulfillment_type.upper() not in {"FBS", "SELLER", "SELLER_SHIPPING"},
            raw_payload=raw_payload,
        )

    def _order_list_payload(self, since: datetime | None = None, cursor: str = "") -> dict:
        payload = dict(self.settings.get("order_list_payload_template") or {})
        statuses = self.settings.get("pull_statuses") or ["pending_shipment", "awaiting_shipping"]
        payload.setdefault(str(self.settings.get("status_field") or "status"), statuses)
        payload.setdefault(str(self.settings.get("page_size_field") or "page_size"), int(self.settings.get("page_size") or 50))
        if cursor:
            payload.setdefault(str(self.settings.get("cursor_field") or "cursor"), cursor)
        if since:
            value = int(since.replace(tzinfo=timezone.utc).timestamp()) if since.tzinfo is None else int(since.timestamp())
            payload.setdefault(str(self.settings.get("since_field") or "updated_after"), value)
        return payload

    async def _fetch_order_detail(self, order_id: str) -> dict:
        path = self._required_path("order_detail_path")
        method = str(self.settings.get("order_detail_method") or "POST")
        payload = dict(self.settings.get("order_detail_payload_template") or {})
        payload.setdefault(str(self.settings.get("order_id_field") or "order_id"), order_id)
        data = await self._api(method, path.format(order_id=order_id), payload=payload)
        payload_data = response_data(data)
        if isinstance(payload_data, dict):
            detail = first_value(payload_data.get("order"), payload_data.get("order_detail"), payload_data)
            return detail if isinstance(detail, dict) else payload_data
        return {}

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        path = self._required_path("order_list_path")
        method = str(self.settings.get("order_list_method") or "POST")
        cursor = ""
        orders: list[NormalizedOrder] = []
        while True:
            data = await self._api(method, path, payload=self._order_list_payload(since, cursor))
            payload = response_data(data)
            rows = extract_items(payload if isinstance(payload, dict) else {}, "orders", "order_list", "items", "list", "data")
            for row in rows:
                order_id = str(first_value(row.get("order_id"), row.get("order_sn"), row.get("id")) or "")
                detail = await self._fetch_order_detail(order_id) if bool(self.settings.get("fetch_order_details", True)) and order_id and self.settings.get("order_detail_path") else row
                normalized = self._normalize_order({**row, **detail})
                if normalized:
                    orders.append(normalized)
            cursor = str(first_value(deep_get(payload, "pagination.next_cursor") if isinstance(payload, dict) else None, payload.get("next_cursor") if isinstance(payload, dict) else None, payload.get("cursor") if isinstance(payload, dict) else None) or "")
            if not cursor:
                break
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for order_id in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            detail = await self._fetch_order_detail(order_id)
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
        tracking_number = str(first_value(order.raw_payload.get("tracking_number"), order.raw_payload.get("shipment_tracking_number"), self.settings.get("tracking_number"), order.posting_number) or "")
        carrier = str(first_value(self.settings.get("carrier_name"), self.settings.get("carrier_code"), order.raw_payload.get("buyer_selected_logistics"), "Temu"))
        if self._dry_run():
            return ShipmentResult(order.posting_number or order.platform_order_id, tracking_number, carrier, "dry_run_created", order.raw_payload)
        path = self._required_path("ship_path")
        method = str(self.settings.get("ship_method") or "POST")
        payload = dict(self.settings.get("ship_payload_template") or {})
        payload.setdefault(str(self.settings.get("order_id_field") or "order_id"), order.platform_order_id)
        payload.setdefault(str(self.settings.get("package_id_field") or "package_id"), order.posting_number or order.platform_order_id)
        payload.setdefault(str(self.settings.get("tracking_number_field") or "tracking_number"), tracking_number)
        payload.setdefault(str(self.settings.get("carrier_field") or "carrier"), carrier)
        data = await self._api(method, path.format(order_id=order.platform_order_id, package_id=order.posting_number), payload=payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("package_id"), raw.get("fulfillment_id"), order.posting_number, order.platform_order_id)),
            tracking_number=str(first_value(raw.get("tracking_number"), raw.get("waybill_number"), tracking_number)),
            carrier=str(first_value(raw.get("carrier"), raw.get("logistics_channel"), carrier)),
            status=str(first_value(raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("Temu Label Preview", shipment, order)
        if str(self.settings.get("label_mode") or "requires_partner_portal_confirmation").lower() in {"unsupported", "requires_partner_portal_confirmation"} and not self.settings.get("label_path"):
            raise NotImplementedError("Temu label download requires Partner Platform-confirmed settings.label_path")
        path = self._required_path("label_path")
        method = str(self.settings.get("label_method") or "POST")
        payload = dict(self.settings.get("label_payload_template") or {})
        payload.setdefault(str(self.settings.get("order_id_field") or "order_id"), order.platform_order_id)
        payload.setdefault(str(self.settings.get("package_id_field") or "package_id"), shipment.platform_shipment_id or order.posting_number)
        data = await self._api(method, path.format(order_id=order.platform_order_id, package_id=shipment.platform_shipment_id or order.posting_number), payload=payload, binary=bool(self.settings.get("label_binary_response", False)))
        return label_from_platform_response(data)
