from datetime import datetime, timezone

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    deep_get,
    first_value,
    label_from_platform_response,
    product_payload,
    response_data,
)


ORDER_FRAGMENT = """
fragment ConnectorOrderFields on Order {
  id
  name
  createdAt
  processedAt
  cancelledAt
  closed
  displayFinancialStatus
  displayFulfillmentStatus
  totalPriceSet { shopMoney { amount currencyCode } }
  shippingLine { title code }
  shippingAddress { name countryCodeV2 countryCode }
  fulfillments(first: 10) {
    id
    status
    trackingInfo { number company url }
  }
  fulfillmentOrders(first: 10) {
    nodes {
      id
      status
      requestStatus
      fulfillAt
      fulfillBy
      deliveryMethod { methodType serviceCode }
      lineItems(first: 50) {
        nodes {
          id
          remainingQuantity
          totalQuantity
          lineItem {
            id
            sku
            title
            variantTitle
            quantity
            currentQuantity
            originalUnitPriceSet { shopMoney { amount currencyCode } }
          }
        }
      }
    }
  }
  lineItems(first: 50) {
    nodes {
      id
      sku
      title
      variantTitle
      quantity
      currentQuantity
      originalUnitPriceSet { shopMoney { amount currencyCode } }
    }
  }
}
"""


class ShopifyConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "shopify"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.shop_domain = str(
            first_value(
                self.credentials.get("shop_domain"),
                self.credentials.get("shop"),
                self.settings.get("shop_domain"),
                self.settings.get("account_id"),
            )
            or ""
        ).replace("https://", "").replace("http://", "").strip("/")
        self.access_token = str(first_value(self.credentials.get("access_token"), self.credentials.get("admin_access_token")) or "")
        self.api_version = str(self.settings.get("api_version") or "2026-04")
        self.base_url = str(self.settings.get("base_url") or "").rstrip("/")
        self.account_id = str(self.settings.get("account_id") or self.shop_domain)

    def _graphql_url(self) -> str:
        if self.base_url:
            base_url = self.base_url.format(shop_domain=self.shop_domain)
            if base_url.endswith("/graphql.json"):
                return base_url
            if "/admin/api/" in base_url:
                return f"{base_url.rstrip('/')}/graphql.json"
            return f"{base_url}/admin/api/{self.api_version}/graphql.json"
        if not self.shop_domain:
            raise ValueError("Shopify shop_domain is required")
        return f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"

    @property
    def headers(self) -> dict:
        if not self.access_token:
            raise ValueError("Shopify access_token is required")
        return {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token,
        }

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        data = await self._request(
            "POST",
            self._graphql_url(),
            headers=self.headers,
            json_body={"query": query, "variables": variables or {}},
            timeout=90,
        )
        payload = data if isinstance(data, dict) else {}
        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"Shopify GraphQL errors: {errors}")
        return payload

    @staticmethod
    def _nodes(value) -> list[dict]:
        if isinstance(value, dict):
            if isinstance(value.get("nodes"), list):
                return [item for item in value["nodes"] if isinstance(item, dict)]
            if isinstance(value.get("edges"), list):
                return [edge.get("node") for edge in value["edges"] if isinstance(edge, dict) and isinstance(edge.get("node"), dict)]
        return []

    def _order_items(self, order: dict) -> list[dict]:
        fulfillment_items: list[dict] = []
        for fulfillment_order in self._nodes(order.get("fulfillmentOrders")):
            fulfillment_order_id = fulfillment_order.get("id")
            for row in self._nodes(fulfillment_order.get("lineItems")):
                line = row.get("lineItem") if isinstance(row.get("lineItem"), dict) else row
                if isinstance(line, dict):
                    fulfillment_items.append(
                        {
                            **line,
                            "fulfillment_order_id": fulfillment_order_id,
                            "fulfillment_order_line_item_id": row.get("id"),
                            "remainingQuantity": row.get("remainingQuantity"),
                            "totalQuantity": row.get("totalQuantity"),
                        }
                    )
        return fulfillment_items or self._nodes(order.get("lineItems"))

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("id"), order.get("legacyResourceId"), order.get("order_id")) or "")
        if not order_id:
            return None
        fulfillment_orders = self._nodes(order.get("fulfillmentOrders"))
        first_fulfillment_order = fulfillment_orders[0] if fulfillment_orders else {}
        shipping = order.get("shippingLine") if isinstance(order.get("shippingLine"), dict) else {}
        address = order.get("shippingAddress") if isinstance(order.get("shippingAddress"), dict) else {}
        fulfillments = as_list(order.get("fulfillments"))
        tracking_info = {}
        if fulfillments and isinstance(fulfillments[0], dict):
            tracking_rows = as_list(fulfillments[0].get("trackingInfo"))
            tracking_info = tracking_rows[0] if tracking_rows and isinstance(tracking_rows[0], dict) else {}
        products = [
            product_payload(
                item,
                sku_keys=("sku", "seller_sku", "variant.sku"),
                name_keys=("title", "variantTitle", "name"),
                quantity_keys=("currentQuantity", "quantity", "remainingQuantity", "totalQuantity"),
                price_keys=("originalUnitPriceSet.shopMoney.amount", "price.amount", "price"),
                currency_keys=("originalUnitPriceSet.shopMoney.currencyCode", "price.currency", "currency"),
            )
            for item in self._order_items(order)
        ]
        status = str(
            first_value(
                "CANCELLED" if order.get("cancelledAt") else None,
                order.get("displayFulfillmentStatus"),
                first_fulfillment_order.get("status"),
                order.get("displayFinancialStatus"),
            )
            or ""
        )
        fulfillment_type = str(first_value(first_fulfillment_order.get("deliveryMethod", {}).get("methodType") if isinstance(first_fulfillment_order.get("deliveryMethod"), dict) else None, "FBS"))
        raw_payload = {
            **order,
            "id": order_id,
            "order_number": first_value(order.get("name"), order_id),
            "fulfillment_order_id": first_value(first_fulfillment_order.get("id"), order_id),
            "fulfillment_order_line_items": [
                {
                    "id": row.get("fulfillment_order_line_item_id"),
                    "quantity": first_value(row.get("remainingQuantity"), row.get("currentQuantity"), row.get("quantity"), 1),
                }
                for row in self._order_items(order)
                if row.get("fulfillment_order_line_item_id")
            ],
            "site": self.shop_domain or "shopify",
            "created_at": order.get("createdAt"),
            "order_date": first_value(order.get("processedAt"), order.get("createdAt")),
            "payment_at": order.get("processedAt"),
            "shipping_deadline_at": first_value(first_fulfillment_order.get("fulfillBy"), first_fulfillment_order.get("fulfillAt")),
            "buyer_selected_logistics": first_value(shipping.get("title"), shipping.get("code")),
            "shipment_tracking_number": tracking_info.get("number"),
            "tracking_number": tracking_info.get("number"),
            "country_code": first_value(address.get("countryCodeV2"), address.get("countryCode")),
            "buyer_name": address.get("name"),
            "order_amount": deep_get(order, "totalPriceSet.shopMoney.amount"),
            "currency_code": first_value(deep_get(order, "totalPriceSet.shopMoney.currencyCode"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": fulfillment_type,
        }
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=str(first_value(order.get("name"), order_id)),
            posting_number=str(first_value(first_fulfillment_order.get("id"), order_id)),
            platform_status=status,
            fulfillment_type=fulfillment_type,
            is_overseas_warehouse=fulfillment_type.upper() not in {"FBS", "MANUAL", "SHIPPING"},
            raw_payload=raw_payload,
        )

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        query_text = str(self.settings.get("pull_query") or "fulfillment_status:unfulfilled OR fulfillment_status:partial")
        if since:
            value = since.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if since.tzinfo else since.replace(microsecond=0).isoformat() + "Z"
            query_text = f"({query_text}) updated_at:>={value}"
        query = str(
            self.settings.get("orders_graphql_query")
            or f"""
query ConnectorOrders($first: Int!, $after: String, $query: String) {{
  orders(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {{
    nodes {{ ...ConnectorOrderFields }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
{ORDER_FRAGMENT}
"""
        )
        page_size = int(self.settings.get("page_size") or 50)
        cursor = None
        orders: list[NormalizedOrder] = []
        while True:
            payload = await self._graphql(query, {"first": page_size, "after": cursor, "query": query_text})
            orders_payload = deep_get(payload, "data.orders") or {}
            for row in self._nodes(orders_payload):
                normalized = self._normalize_order(row)
                if normalized:
                    orders.append(normalized)
            page_info = orders_payload.get("pageInfo") if isinstance(orders_payload, dict) else {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        query = str(
            self.settings.get("status_graphql_query")
            or f"""
query ConnectorOrderStatus($id: ID!) {{
  node(id: $id) {{
    __typename
    ...ConnectorOrderFields
    ... on FulfillmentOrder {{
      id
      status
      order {{ ...ConnectorOrderFields }}
    }}
  }}
}}
{ORDER_FRAGMENT}
"""
        )
        updates: list[OrderStatusUpdate] = []
        for node_id in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            payload = await self._graphql(query, {"id": node_id})
            node = deep_get(payload, "data.node")
            if not isinstance(node, dict):
                continue
            order = node.get("order") if isinstance(node.get("order"), dict) else node
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
        tracking_number = str(first_value(order.raw_payload.get("tracking_number"), order.raw_payload.get("shipment_tracking_number"), self.settings.get("tracking_number"), order.posting_number) or "")
        carrier = str(first_value(self.settings.get("carrier_name"), order.raw_payload.get("buyer_selected_logistics"), "Shopify"))
        if self._dry_run():
            return ShipmentResult(order.posting_number or order.platform_order_id, tracking_number, carrier, "dry_run_created", order.raw_payload)
        mutation = str(
            self.settings.get("fulfillment_create_mutation")
            or """
mutation ConnectorFulfillmentCreate($fulfillment: FulfillmentInput!, $message: String) {
  fulfillmentCreate(fulfillment: $fulfillment, message: $message) {
    fulfillment { id status trackingInfo { number company url } }
    userErrors { field message }
  }
}
"""
        )
        fulfillment_order_id = str(first_value(order.raw_payload.get("fulfillment_order_id"), order.posting_number, order.platform_order_id))
        line_items = [
            {"id": item.get("id"), "quantity": int(item.get("quantity") or 1)}
            for item in as_list(order.raw_payload.get("fulfillment_order_line_items"))
            if isinstance(item, dict) and item.get("id")
        ]
        line_item_group: dict = {"fulfillmentOrderId": fulfillment_order_id}
        if line_items:
            line_item_group["fulfillmentOrderLineItems"] = line_items
        payload = dict(self.settings.get("fulfillment_payload_template") or {})
        payload.setdefault("lineItemsByFulfillmentOrder", [line_item_group])
        payload.setdefault(
            "trackingInfo",
            {
                "company": carrier,
                "number": tracking_number,
                **({"url": self.settings.get("tracking_url")} if self.settings.get("tracking_url") else {}),
            },
        )
        response = await self._graphql(mutation, {"fulfillment": payload, "message": self.settings.get("fulfillment_message")})
        raw = deep_get(response, "data.fulfillmentCreate") or {}
        errors = raw.get("userErrors") if isinstance(raw, dict) else None
        if errors:
            raise RuntimeError(f"Shopify fulfillmentCreate user errors: {errors}")
        fulfillment = raw.get("fulfillment") if isinstance(raw, dict) and isinstance(raw.get("fulfillment"), dict) else {}
        tracking_rows = as_list(fulfillment.get("trackingInfo"))
        tracking = tracking_rows[0] if tracking_rows and isinstance(tracking_rows[0], dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(fulfillment.get("id"), fulfillment_order_id)),
            tracking_number=str(first_value(tracking.get("number"), tracking_number, fulfillment_order_id)),
            carrier=str(first_value(tracking.get("company"), carrier)),
            status=str(first_value(fulfillment.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("Shopify Label Preview", shipment, order)
        if str(self.settings.get("label_mode") or "unsupported").lower() == "unsupported":
            raise NotImplementedError("Shopify Admin API does not provide marketplace label download by default")
        path = str(self.settings.get("label_path") or "")
        if not path:
            raise ValueError("Shopify label_path is required when label_mode is not unsupported")
        data = await self._request(
            "GET",
            path.format(shipment_id=shipment.platform_shipment_id, order_id=order.platform_order_id),
            headers=self.headers,
            binary=True,
        )
        return label_from_platform_response(data)
