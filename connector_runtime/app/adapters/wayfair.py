import base64
from datetime import datetime, timedelta, timezone

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    deep_get,
    first_value,
    label_from_platform_response,
    product_payload,
)


DROPSHIP_ORDER_QUERY = """
query ConnectorDropshipPurchaseOrders($limit: Int!, $hasResponse: Boolean, $sortOrder: SortOrder) {
  getDropshipPurchaseOrders(limit: $limit, hasResponse: $hasResponse, sortOrder: $sortOrder) {
    poNumber
    poDate
    estimatedShipDate
    customerName
    customerAddress1
    customerAddress2
    customerCity
    customerState
    customerPostalCode
    customerCountry
    orderType
    packingSlipUrl
    shippingInfo { shipSpeed carrierCode }
    warehouse { id name }
    products { partNumber quantity price name }
  }
}
"""


REGISTER_MUTATION = """
mutation ConnectorRegister($params: RegistrationInput!) {
  purchaseOrders {
    register(registrationInput: $params) {
      eventDate
      pickupDate
      consolidatedShippingLabel { url }
      shippingLabelInfo { carrier }
      purchaseOrder {
        poNumber
        shippingInfo { carrierCode }
      }
    }
  }
}
"""


class WayfairConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "wayfair"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.client_id = str(self.credentials.get("client_id") or "")
        self.client_secret = str(self.credentials.get("client_secret") or "")
        self.access_token = str(self.credentials.get("access_token") or "")
        self.supplier_id = str(first_value(self.credentials.get("supplier_id"), self.credentials.get("supplierId"), self.settings.get("supplier_id"), self.settings.get("account_id")) or "")
        self.graphql_url = str(self.settings.get("graphql_url") or self.settings.get("base_url") or "https://api.wayfair.com/v1/graphql")
        self.token_url = str(self.settings.get("token_url") or "https://sso.auth.wayfair.com/oauth/token")
        self.account_id = str(self.settings.get("account_id") or self.supplier_id or self.client_id)

    async def _ensure_access_token(self) -> str:
        if self.access_token:
            return self.access_token
        if not (self.client_id and self.client_secret):
            raise ValueError("Wayfair client_id/client_secret or access_token is required")
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        data = await self._request(
            "POST",
            self.token_url,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        if not isinstance(data, dict) or not data.get("access_token"):
            raise RuntimeError(f"Wayfair token response did not include access_token: {data}")
        self.access_token = str(data["access_token"])
        return self.access_token

    async def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {await self._ensure_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        data = await self._request("POST", self.graphql_url, headers=await self._headers(), json_body={"query": query, "variables": variables or {}}, timeout=90)
        payload = data if isinstance(data, dict) else {}
        if payload.get("errors"):
            raise RuntimeError(f"Wayfair GraphQL errors: {payload.get('errors')}")
        return payload

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        po_number = str(first_value(order.get("poNumber"), order.get("po_number"), order.get("id")) or "")
        if not po_number:
            return None
        shipping = order.get("shippingInfo") if isinstance(order.get("shippingInfo"), dict) else {}
        warehouse = order.get("warehouse") if isinstance(order.get("warehouse"), dict) else {}
        products = [
            product_payload(
                item,
                sku_keys=("partNumber", "part_number", "sku", "supplierPartNumber"),
                name_keys=("name", "productName", "product_name", "partNumber"),
                quantity_keys=("quantity", "qty"),
                price_keys=("price.amount", "price", "unitPrice"),
                currency_keys=("price.currency", "currency", "currencyCode"),
            )
            for item in as_list(order.get("products"))
            if isinstance(item, dict)
        ]
        status = str(first_value(order.get("status"), "NO_RESPONSE" if order.get("hasResponse") is False else "", order.get("orderType")) or "")
        raw_payload = {
            **order,
            "id": po_number,
            "order_number": po_number,
            "site": first_value(self.settings.get("region"), order.get("country"), "wayfair"),
            "created_at": order.get("poDate"),
            "order_date": order.get("poDate"),
            "payment_at": order.get("poDate"),
            "shipping_deadline_at": order.get("estimatedShipDate"),
            "buyer_selected_logistics": first_value(shipping.get("shipSpeed"), shipping.get("carrierCode")),
            "shipment_tracking_number": first_value(order.get("trackingNumber"), order.get("tracking_number")),
            "tracking_number": first_value(order.get("trackingNumber"), order.get("tracking_number")),
            "country_code": first_value(order.get("customerCountry"), order.get("countryCode"), self.settings.get("region")),
            "buyer_name": order.get("customerName"),
            "warehouse_id": first_value(warehouse.get("id"), self.settings.get("warehouse_id")),
            "order_amount": first_value(order.get("orderAmount"), *(item.get("price") for item in products)),
            "currency_code": first_value(order.get("currency"), *(item.get("currency_code") for item in products), self.settings.get("currency", "USD")),
            "products": products,
            "items": products,
            "fulfillment_type": first_value(order.get("orderType"), "DROPSHIP"),
        }
        return NormalizedOrder(
            platform_order_id=po_number,
            platform_order_no=po_number,
            posting_number=po_number,
            platform_status=status,
            fulfillment_type=str(raw_payload["fulfillment_type"]),
            is_overseas_warehouse=str(raw_payload["fulfillment_type"]).upper() in {"CASTLEGATE", "CG"},
            raw_payload=raw_payload,
        )

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        query = str(self.settings.get("orders_query") or DROPSHIP_ORDER_QUERY)
        variables = dict(self.settings.get("orders_query_variables") or {})
        variables.setdefault("limit", int(self.settings.get("limit") or self.settings.get("page_size") or 50))
        variables.setdefault("hasResponse", bool(self.settings.get("has_response", False)))
        variables.setdefault("sortOrder", str(self.settings.get("sort_order") or "DESC"))
        if since:
            variables.setdefault("fromDate", since.replace(microsecond=0).isoformat())
        data = await self._graphql(query, variables)
        rows = deep_get(data, "data.getDropshipPurchaseOrders")
        if not isinstance(rows, list):
            rows = deep_get(data, "data.purchaseOrders") if isinstance(deep_get(data, "data.purchaseOrders"), list) else []
        return [normalized for row in rows if isinstance(row, dict) for normalized in [self._normalize_order(row)] if normalized]

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        query = str(self.settings.get("status_query") or self.settings.get("orders_query") or DROPSHIP_ORDER_QUERY)
        updates: list[OrderStatusUpdate] = []
        for po_number in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            variables = dict(self.settings.get("status_query_variables") or {})
            variables.setdefault("poNumber", po_number)
            variables.setdefault("limit", 1)
            variables.setdefault("hasResponse", None)
            variables.setdefault("sortOrder", "DESC")
            data = await self._graphql(query, variables)
            rows = deep_get(data, "data.getDropshipPurchaseOrders")
            row = next((item for item in as_list(rows) if isinstance(item, dict) and str(first_value(item.get("poNumber"), item.get("po_number"))) == po_number), None)
            if not row and isinstance(rows, list) and rows:
                row = rows[0] if isinstance(rows[0], dict) else None
            if not row:
                continue
            normalized = self._normalize_order(row)
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
        carrier = str(first_value(self.settings.get("carrier_code"), order.raw_payload.get("buyer_selected_logistics"), "Wayfair"))
        tracking_number = str(first_value(order.raw_payload.get("tracking_number"), order.raw_payload.get("shipment_tracking_number"), self.settings.get("tracking_number"), order.platform_order_id) or "")
        if self._dry_run():
            return ShipmentResult(order.platform_order_id, tracking_number, carrier, "dry_run_registered", order.raw_payload)
        query = str(self.settings.get("register_mutation") or REGISTER_MUTATION)
        params = dict(self.settings.get("registration_payload_template") or {})
        params.setdefault("poNumber", order.platform_order_id)
        if self.settings.get("warehouse_id") or order.raw_payload.get("warehouse_id"):
            params.setdefault("warehouseId", str(first_value(self.settings.get("warehouse_id"), order.raw_payload.get("warehouse_id"))))
        params.setdefault("requestForPickupDate", datetime.now(timezone.utc).replace(microsecond=0).isoformat())
        data = await self._graphql(query, {"params": params})
        raw = deep_get(data, "data.purchaseOrders.register")
        raw = raw if isinstance(raw, dict) else {}
        label = deep_get(raw, "consolidatedShippingLabel.url")
        carrier = str(first_value(deep_get(raw, "shippingLabelInfo.carrier"), deep_get(raw, "purchaseOrder.shippingInfo.carrierCode"), carrier))
        return ShipmentResult(
            platform_shipment_id=order.platform_order_id,
            tracking_number=tracking_number or order.platform_order_id,
            carrier=carrier,
            status=str(first_value(raw.get("eventDate"), "registered")),
            raw_payload={**raw, **({"label_url": label} if label else {})},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("Wayfair Label Preview", shipment, order)
        label_url = first_value(shipment.raw_payload.get("label_url"), deep_get(shipment.raw_payload, "consolidatedShippingLabel.url"), order.raw_payload.get("label_url"))
        if label_url:
            data = await self._request("GET", str(label_url), headers=await self._headers(), binary=True, timeout=90)
            return label_from_platform_response(data)
        label_query = self.settings.get("label_query")
        if label_query:
            variables = dict(self.settings.get("label_query_variables") or {})
            variables.setdefault("poNumber", order.platform_order_id)
            data = await self._graphql(str(label_query), variables)
            return label_from_platform_response(data)
        raise NotImplementedError("Wayfair label download requires a label URL from registration or configured settings.label_query")
