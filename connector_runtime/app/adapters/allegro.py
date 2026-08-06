import asyncio
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from uuid import UUID

import httpx

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .pdf_preview import build_preview_pdf


class AllegroConnector(MarketplaceConnector):
    platform = "allegro"
    ORDER_STATUSES = {
        "BOUGHT",
        "FILLED_IN",
        "READY_FOR_PROCESSING",
        "CANCELLED",
        "BUYER_CANCELLED",
        "FULFILLMENT_STATUS_CHANGED",
        "AUTO_CANCELLED",
    }
    FULFILLMENT_STATUSES = {
        "NEW",
        "PROCESSING",
        "READY_FOR_SHIPMENT",
        "READY_FOR_PICKUP",
        "SENT",
        "PICKED_UP",
        "CANCELLED",
        "SUSPENDED",
        "RETURNED",
    }

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.access_token = credentials.get("access_token", "")
        self.settings = settings or {}
        self.base_url = self.settings["base_url"]

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.allegro.public.v1+json",
            "Content-Type": "application/vnd.allegro.public.v1+json",
        }

    async def _fetch_negative_ratings(
        self,
        client: httpx.AsyncClient,
        start: date,
        end: date,
    ) -> dict[tuple[str, str], int] | None:
        counts: dict[tuple[str, str], int] = {}
        offset = 0
        limit = 100
        for _ in range(200):
            try:
                response = await client.get(
                    f"{self.base_url}/sale/user-ratings",
                    headers=self.headers,
                    params={
                        "recommended": "false",
                        "lastChangedAt.gte": f"{start.isoformat()}T00:00:00Z",
                        "lastChangedAt.lte": f"{end.isoformat()}T23:59:59Z",
                        "limit": limit,
                        "offset": offset,
                    },
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                return None
            ratings = payload.get("ratings") if isinstance(payload, dict) else []
            ratings = ratings if isinstance(ratings, list) else []
            for rating in ratings:
                if not isinstance(rating, dict) or rating.get("recommended") is not False:
                    continue
                if rating.get("excludedFromAverageRates") is True:
                    continue
                created_at = str(rating.get("createdAt") or rating.get("lastChangedAt") or "")[:10]
                if created_at and not (start.isoformat() <= created_at <= end.isoformat()):
                    continue
                order = rating.get("order") if isinstance(rating.get("order"), dict) else {}
                offers = order.get("offers") if isinstance(order.get("offers"), list) else []
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    offer_id = str(offer.get("id") or "").strip()
                    if offer_id:
                        key = (offer_id, created_at or end.isoformat())
                        counts[key] = counts.get(key, 0) + 1
            if len(ratings) < limit:
                break
            offset += limit
        return counts

    async def fetch_traffic(self, start: datetime, end: datetime) -> list[dict]:
        offers: list[dict] = []
        offset = 0
        limit = 1000
        async with httpx.AsyncClient(timeout=90) as client:
            while True:
                response = await client.get(
                    f"{self.base_url}/sale/offers",
                    headers=self.headers,
                    params={"publication.status": "ACTIVE", "limit": limit, "offset": offset},
                )
                response.raise_for_status()
                payload = response.json()
                page = payload.get("offers") if isinstance(payload, dict) else []
                page = page if isinstance(page, list) else []
                offers.extend(item for item in page if isinstance(item, dict))
                total = int(payload.get("totalCount") or len(offers)) if isinstance(payload, dict) else len(offers)
                if len(page) < limit or len(offers) >= total:
                    break
                offset += limit

            negative_reviews = await self._fetch_negative_ratings(
                client,
                end.date() - timedelta(days=29),
                end.date(),
            )

        stat_date = end.date().isoformat()
        period_start_date = end.date() - timedelta(days=29)
        period_end_date = end.date()
        period_start = period_start_date.isoformat()
        rows: list[dict] = []

        def append_marketplace(offer: dict, marketplace: str, stats: dict, stock: dict) -> None:
            offer_id = str(offer.get("id") or "")
            external = offer.get("external") if isinstance(offer.get("external"), dict) else {}
            category = offer.get("category") if isinstance(offer.get("category"), dict) else {}
            platform_category_id = str(category.get("id") or "")
            rows.append(
                {
                    "source": "organic",
                    "grain": "rolling_30d",
                    "stat_date": stat_date,
                    "period_start": period_start,
                    "period_end": stat_date,
                    "region": marketplace,
                    "entity_type": "sku",
                    "entity_id": offer_id,
                    "sku": str(external.get("id") or offer_id),
                    "product_name": str(offer.get("name") or ""),
                    "impressions": None,
                    "clicks": int(stats.get("visitsCount") or 0),
                    "add_to_cart": None,
                    "orders": int(stock.get("sold") or 0),
                    "units_sold": int(stock.get("sold") or 0),
                    "negative_reviews": (
                        sum(
                            negative_reviews.get((offer_id, review_day), 0)
                            for review_day in (
                                (period_start_date + timedelta(days=offset)).isoformat()
                                for offset in range((period_end_date - period_start_date).days + 1)
                            )
                        )
                        if negative_reviews is not None
                        else None
                    ),
                    "revenue": None,
                    "currency": "",
                    "raw_data": {
                        "watchers_count": int(stats.get("watchersCount") or 0),
                        "negative_reviews_source": "allegro_user_ratings" if negative_reviews is not None else "unavailable",
                        "negative_reviews_daily": (
                            {
                                review_day: count
                                for review_day, count in (
                                    (
                                        (period_start_date + timedelta(days=offset)).isoformat(),
                                        negative_reviews.get((offer_id, (period_start_date + timedelta(days=offset)).isoformat()), 0),
                                    )
                                    for offset in range((period_end_date - period_start_date).days + 1)
                                )
                                if count
                            }
                            if negative_reviews is not None
                            else {}
                        ),
                        "platform_category_id": platform_category_id,
                        "platform_category_name": str(category.get("name") or ""),
                        "platform_category_path": "",
                    },
                }
            )

        for offer in offers:
            publication = offer.get("publication") if isinstance(offer.get("publication"), dict) else {}
            marketplaces = publication.get("marketplaces") if isinstance(publication.get("marketplaces"), dict) else {}
            base = marketplaces.get("base") if isinstance(marketplaces.get("base"), dict) else {}
            append_marketplace(
                offer,
                str(base.get("id") or "allegro-pl"),
                offer.get("stats") if isinstance(offer.get("stats"), dict) else {},
                offer.get("stock") if isinstance(offer.get("stock"), dict) else {},
            )
            additional = offer.get("additionalMarketplaces")
            if isinstance(additional, dict):
                additional_items = [(marketplace, value) for marketplace, value in additional.items()]
            elif isinstance(additional, list):
                additional_items = [
                    (
                        str((value.get("marketplace") or {}).get("id") or value.get("id") or ""),
                        value,
                    )
                    for value in additional
                    if isinstance(value, dict)
                ]
            else:
                additional_items = []
            for marketplace, value in additional_items:
                if not isinstance(value, dict):
                    continue
                append_marketplace(
                    offer,
                    str(marketplace),
                    value.get("stats") if isinstance(value.get("stats"), dict) else {},
                    value.get("stock") if isinstance(value.get("stock"), dict) else {},
                )
        return rows

    async def fetch_platform_products(self, since: datetime | None = None) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        limit = 1000
        async with httpx.AsyncClient(timeout=90) as client:
            while True:
                response = await client.get(
                    f"{self.base_url}/sale/offers",
                    headers=self.headers,
                    params={"publication.status": "ACTIVE", "limit": limit, "offset": offset},
                )
                response.raise_for_status()
                payload = response.json()
                page = payload.get("offers") if isinstance(payload, dict) else []
                page = [item for item in page if isinstance(item, dict)] if isinstance(page, list) else []
                rows.extend(page)
                try:
                    total = int(payload.get("totalCount") or len(rows)) if isinstance(payload, dict) else len(rows)
                except (TypeError, ValueError):
                    total = len(rows)
                if not page or len(page) < limit or len(rows) >= total:
                    break
                offset += limit
                await asyncio.sleep(0.1)
            normalized: list[dict] = []
            for offer in rows:
                offer_id = str(offer.get("id") or "").strip()
                external = offer.get("external") if isinstance(offer.get("external"), dict) else {}
                publication = offer.get("publication") if isinstance(offer.get("publication"), dict) else {}
                marketplaces = publication.get("marketplaces") if isinstance(publication.get("marketplaces"), dict) else {}
                base_marketplace = marketplaces.get("base") if isinstance(marketplaces.get("base"), dict) else {}
                selling_mode = offer.get("sellingMode") if isinstance(offer.get("sellingMode"), dict) else {}
                price = selling_mode.get("price") if isinstance(selling_mode.get("price"), dict) else {}
                offer_price = offer.get("price") if isinstance(offer.get("price"), dict) else {}
                stock = offer.get("stock") if isinstance(offer.get("stock"), dict) else {}
                sku = str(self._first(external.get("id"), offer.get("sellerSku"), offer.get("sku"), offer_id) or "").strip()
                if not offer_id and not sku:
                    continue
                normalized.append(
                    {
                        "platform_product_id": offer_id or sku,
                        "platform_sku": sku or offer_id,
                        "product_name": str(offer.get("name") or ""),
                        "listing_status": str(self._first(publication.get("status"), offer.get("status")) or ""),
                        "warehouse_code": "",
                        "warehouse_name": "",
                        "fulfillment_type": "",
                        "logistics_type": "",
                        "available_stock": self._first(
                            stock.get("available"),
                            stock.get("availableQuantity"),
                            stock.get("quantity"),
                            0,
                        ),
                        "reserved_stock": self._first(stock.get("reserved"), stock.get("reservedQuantity")),
                        "price_amount": self._first(price.get("amount"), offer_price.get("amount"), offer.get("price")),
                        "price_currency": str(self._first(price.get("currency"), offer_price.get("currency"), offer.get("currency"), "PLN") or "PLN"),
                        "raw_payload": {
                            "offer": offer,
                            "marketplace_id": str(base_marketplace.get("id") or ""),
                            "marketplace_name": str(base_marketplace.get("name") or ""),
                        },
                    }
                )
        return normalized

    def _download_platform_package_orders(self) -> bool:
        return bool(self.settings.get("download_platform_package_orders", True))

    def _is_platform_package_order(self, event: dict) -> bool:
        order = event.get("order") or {}
        checkout_form = order.get("checkoutForm") or {}
        fulfillment = checkout_form.get("fulfillment") or {}
        provider = fulfillment.get("provider") or {}
        candidates = [
            order.get("platformPackage"),
            order.get("platform_package"),
            checkout_form.get("platformPackage"),
            checkout_form.get("platform_package"),
            fulfillment.get("type"),
            fulfillment.get("name"),
            provider.get("id"),
            provider.get("name"),
            (checkout_form.get("delivery") or {}).get("provider"),
            ((checkout_form.get("delivery") or {}).get("method") or {}).get("name"),
        ]
        text = " ".join(str(item) for item in candidates if item is not None).lower()
        markers = ("platform_package", "platform package", "allegro fulfillment", "one fulfillment", "allegro one")
        return any(marker in text for marker in markers)

    def _is_platform_fulfillment_form(self, form: dict) -> bool:
        return self._is_platform_package_order({"order": {"checkoutForm": form}})

    @staticmethod
    def _iso_utc(value: datetime) -> str:
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(microsecond=0).isoformat() + "Z"

    @staticmethod
    def _first(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _shipment_tracking_number(shipments: list[dict]) -> str:
        values: list[str] = []
        for shipment in shipments:
            if not isinstance(shipment, dict):
                continue
            value = AllegroConnector._first(
                shipment.get("waybill"),
                shipment.get("trackingNumber"),
                shipment.get("tracking_number"),
            )
            if value:
                text = str(value).strip()
                if text and text not in values:
                    values.append(text)
        return ", ".join(values)

    def _form_tracking_number(self, form: dict) -> str:
        delivery = form.get("delivery") if isinstance(form.get("delivery"), dict) else {}
        shipments = form.get("_shipments") if isinstance(form.get("_shipments"), list) else []
        return str(
            self._first(
                form.get("shipment_tracking_number"),
                form.get("tracking_number"),
                delivery.get("trackingNumber"),
                delivery.get("tracking_number"),
                self._shipment_tracking_number(shipments),
            )
            or ""
        ).strip()

    @staticmethod
    def _checkout_form_lookup_id(value: str) -> str:
        text = str(value or "").strip()
        if "-" in text or len(text) != 32:
            return text
        try:
            return str(UUID(text))
        except ValueError:
            return text

    @staticmethod
    def _line_item_ids(order: NormalizedOrder) -> list[str]:
        payload = order.raw_payload if isinstance(order.raw_payload, dict) else {}
        candidates = [
            payload.get("lineItems"),
            payload.get("line_items"),
            payload.get("items"),
        ]
        values: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, list):
                continue
            for item in candidate:
                value = ""
                if isinstance(item, dict):
                    value = str(item.get("id") or item.get("lineItemId") or item.get("line_item_id") or "").strip()
                else:
                    value = str(item or "").strip()
                if value and value not in values:
                    values.append(value)
        return values

    def _shipment_request_payload(self, order: NormalizedOrder) -> dict:
        template = dict(self.settings.get("shipment_payload_template") or {})
        carrier_id = str(
            template.pop("carrierId", "")
            or template.pop("carrier_id", "")
            or self.settings.get("allegro_carrier_id")
            or self.settings.get("carrierId")
            or self.settings.get("carrier_id")
            or ""
        ).strip()
        if not carrier_id:
            raise ValueError(
                "Allegro shipment carrierId is required. Configure allegro_carrier_id with an id from GET /order/carriers."
            )

        waybill = str(
            template.pop("waybill", "")
            or self.settings.get("allegro_waybill")
            or self.settings.get("waybill")
            or ""
        ).strip()
        payload = {"carrierId": carrier_id, "waybill": waybill, **template}

        line_items = payload.get("lineItems")
        if isinstance(line_items, dict):
            ids = line_items.get("id")
            if isinstance(ids, list):
                payload["lineItems"] = [{"id": str(item_id)} for item_id in ids if str(item_id or "").strip()]
            elif ids:
                payload["lineItems"] = [{"id": str(ids)}]
        elif isinstance(line_items, list):
            normalized_items = []
            for item in line_items:
                if isinstance(item, dict):
                    item_id = str(item.get("id") or "").strip()
                else:
                    item_id = str(item or "").strip()
                if item_id:
                    normalized_items.append({"id": item_id})
            payload["lineItems"] = normalized_items
        else:
            item_ids = self._line_item_ids(order)
            if item_ids:
                payload["lineItems"] = [{"id": item_id} for item_id in item_ids]

        return payload

    async def _fetch_order_shipments(self, client: httpx.AsyncClient, checkout_form_id: str) -> dict:
        if self.settings.get("fetch_order_shipments", True) is False:
            return {}
        lookup_id = self._checkout_form_lookup_id(checkout_form_id)
        response = await client.get(f"{self.base_url}/order/checkout-forms/{lookup_id}/shipments", headers=self.headers)
        if response.status_code in {403, 404}:
            return {}
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _apply_order_shipments(self, form: dict, shipments_payload: dict) -> None:
        shipments = shipments_payload.get("shipments") if isinstance(shipments_payload, dict) else None
        if not isinstance(shipments, list) or not shipments:
            return
        tracking_number = self._shipment_tracking_number(shipments)
        if not tracking_number:
            return
        form["_shipments_payload"] = shipments_payload
        form["_shipments"] = shipments
        form.setdefault("shipping", {})
        if isinstance(form["shipping"], dict):
            form["shipping"]["tracking_number"] = tracking_number
        form["tracking_number"] = tracking_number
        form["shipment_tracking_number"] = tracking_number

    def _normalize_checkout_form(self, form: dict, event_type: str = "") -> NormalizedOrder | None:
        order_id = form.get("id")
        if not order_id:
            return None
        delivery = form.get("delivery") or {}
        delivery_method = delivery.get("method") or {}
        delivery_address = delivery.get("address") or {}
        buyer = form.get("buyer") or {}
        summary = form.get("summary") or {}
        total = summary.get("totalToPay") or summary.get("totalPaid") or {}
        fulfillment = form.get("fulfillment") or {}
        provider = fulfillment.get("provider") or {}
        line_items = form.get("lineItems") or []
        shipments = form.get("_shipments") if isinstance(form.get("_shipments"), list) else []
        tracking_number = self._form_tracking_number(form)
        products = []
        for item in line_items:
            offer = item.get("offer") or {}
            price = item.get("price") or {}
            products.append(
                {
                    "offer_id": self._first(offer.get("id"), item.get("offerId"), item.get("id")),
                    "name": self._first(offer.get("name"), item.get("name")),
                    "quantity": item.get("quantity") or 1,
                    "price": price.get("amount") if isinstance(price, dict) else price,
                    "currency_code": price.get("currency") if isinstance(price, dict) else None,
                    "raw_payload": item,
                }
            )
        is_platform_fulfillment = self._is_platform_fulfillment_form(form)
        fulfillment_type = "ALLEGRO_FULFILLMENT" if is_platform_fulfillment else str(provider.get("id") or fulfillment.get("status") or "FBS")
        raw_payload = {
            **form,
            "id": str(order_id),
            "order_date": self._first(form.get("updatedAt"), form.get("revision"), form.get("createdAt")),
            "created_at": self._first(*(item.get("boughtAt") for item in line_items if isinstance(item, dict)), form.get("updatedAt")),
            "buyer": {
                "id": buyer.get("id"),
                "name": self._first(buyer.get("login"), buyer.get("email"), buyer.get("firstName")),
                "email": buyer.get("email"),
            },
            "delivery_method": {"name": delivery_method.get("name"), **delivery_method},
            "shipping": {
                "receiver_address": {
                    "country_code": delivery_address.get("countryCode"),
                    "country": delivery_address.get("countryCode"),
                    "name": self._first(delivery_address.get("name"), delivery_address.get("company")),
                },
                "tracking_number": tracking_number,
                "shipping_mode": self._first(delivery_method.get("name"), provider.get("name"), provider.get("id")),
            },
            "shipments": shipments,
            "shipments_payload": form.get("_shipments_payload") if isinstance(form.get("_shipments_payload"), dict) else {},
            "shipment_tracking_number": tracking_number,
            "tracking_number": tracking_number,
            "order_amount": total.get("amount") if isinstance(total, dict) else total,
            "currency_code": total.get("currency") if isinstance(total, dict) else None,
            "products": products,
            "fulfillment_type": fulfillment_type,
            "is_overseas_warehouse": is_platform_fulfillment,
        }
        status_value = str(self._first(fulfillment.get("status"), event_type, form.get("status"), "READY_FOR_PROCESSING"))
        return NormalizedOrder(
            platform_order_id=str(order_id),
            platform_order_no=str(order_id),
            posting_number=str(order_id),
            platform_status=status_value,
            fulfillment_type=fulfillment_type,
            is_overseas_warehouse=is_platform_fulfillment,
            raw_payload=raw_payload,
        )

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        status_value = str(self.settings.get("allegro_order_status") or "READY_FOR_PROCESSING").strip().upper()
        fulfillment_status = str(self.settings.get("allegro_fulfillment_status") or "").strip().upper()
        if fulfillment_status and fulfillment_status not in self.FULFILLMENT_STATUSES:
            if fulfillment_status in self.ORDER_STATUSES:
                status_value = fulfillment_status
            fulfillment_status = ""
        params = {
            "status": status_value,
            "limit": int(self.settings.get("limit", 100)),
            "sort": self.settings.get("sort", "-updatedAt"),
        }
        if fulfillment_status:
            params["fulfillment.status"] = fulfillment_status
        if since:
            params["updatedAt.gte"] = self._iso_utc(since)
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(f"{self.base_url}/order/checkout-forms", headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            forms = data.get("checkoutForms") or data.get("orders") or []
            if not forms:
                event_params = {"type": status_value, "limit": int(self.settings.get("limit", 100))}
                response = await client.get(f"{self.base_url}/order/events", headers=self.headers, params=event_params)
                response.raise_for_status()
                forms = []
                for event in response.json().get("events", []):
                    checkout_form = event.get("order", {}).get("checkoutForm") or {}
                    checkout_id = checkout_form.get("id") or event.get("order", {}).get("id")
                    if not checkout_id:
                        continue
                    detail = await client.get(f"{self.base_url}/order/checkout-forms/{checkout_id}", headers=self.headers)
                    if detail.status_code < 400:
                        checkout_form = detail.json()
                    checkout_form["_event_type"] = event.get("type") or status_value
                    checkout_form["_event_payload"] = event
                    forms.append(checkout_form)
            for form in forms:
                event_payload = form.get("_event_payload") or {"order": {"checkoutForm": form}}
                if not self._download_platform_package_orders() and self._is_platform_package_order(event_payload):
                    continue
                if self._form_tracking_number(form):
                    continue
                checkout_id = form.get("id")
                if not checkout_id:
                    continue
                shipments_payload = await self._fetch_order_shipments(client, str(checkout_id))
                self._apply_order_shipments(form, shipments_payload)
        orders: list[NormalizedOrder] = []
        for form in forms:
            event_payload = form.get("_event_payload") or {"order": {"checkoutForm": form}}
            if not self._download_platform_package_orders() and self._is_platform_package_order(event_payload):
                continue
            normalized = self._normalize_checkout_form(form, str(form.get("_event_type") or status_value))
            if normalized:
                orders.append(normalized)
        return orders

    async def fetch_orders_by_date_range(
        self,
        start: datetime,
        end: datetime | None = None,
        *,
        date_field: str = "lineItems.boughtAt",
        status: str = "",
        fulfillment_status: str = "",
        limit: int = 100,
        max_pages: int = 0,
    ) -> list[NormalizedOrder]:
        field = date_field if date_field in {"lineItems.boughtAt", "updatedAt"} else "lineItems.boughtAt"
        limit = max(1, min(int(limit or 100), 100))
        normalized_status = str(status or "").strip().upper()
        normalized_fulfillment_status = str(fulfillment_status or "").strip().upper()
        if normalized_fulfillment_status and normalized_fulfillment_status not in self.FULFILLMENT_STATUSES:
            normalized_fulfillment_status = ""

        params = {
            f"{field}.gte": self._iso_utc(start),
            "limit": limit,
            "offset": 0,
            "sort": f"-{field}",
        }
        if end:
            params[f"{field}.lte"] = self._iso_utc(end)
        if normalized_status:
            params["status"] = normalized_status
        if normalized_fulfillment_status:
            params["fulfillment.status"] = normalized_fulfillment_status

        forms: list[dict] = []
        page_count = 0
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                response = await client.get(f"{self.base_url}/order/checkout-forms", headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                batch = data.get("checkoutForms") or data.get("orders") or []
                forms.extend(batch)
                page_count += 1

                total_count = int(data.get("totalCount") or len(forms))
                if not batch or len(forms) >= total_count:
                    break
                if max_pages and page_count >= max_pages:
                    break
                params["offset"] = int(params["offset"]) + limit
            for form in forms:
                event_payload = {"order": {"checkoutForm": form}}
                if not self._download_platform_package_orders() and self._is_platform_package_order(event_payload):
                    continue
                if self._form_tracking_number(form):
                    continue
                checkout_id = form.get("id")
                if not checkout_id:
                    continue
                shipments_payload = await self._fetch_order_shipments(client, str(checkout_id))
                self._apply_order_shipments(form, shipments_payload)

        orders: list[NormalizedOrder] = []
        for form in forms:
            event_payload = {"order": {"checkoutForm": form}}
            if not self._download_platform_package_orders() and self._is_platform_package_order(event_payload):
                continue
            normalized = self._normalize_checkout_form(form, "")
            if normalized:
                orders.append(normalized)
        return orders

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        if self.settings.get("dry_run_fulfillment", False):
            return ShipmentResult(
                platform_shipment_id=order.platform_order_id,
                tracking_number=order.platform_order_id,
                carrier="Allegro",
                status="dry_run_created",
                raw_payload=order.raw_payload,
            )
        checkout_form_id = self._checkout_form_lookup_id(order.platform_order_id or order.posting_number or order.platform_order_no)
        if not checkout_form_id:
            raise ValueError("Allegro checkoutFormId is required to create shipment.")
        payload = self._shipment_request_payload(order)
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/order/checkout-forms/{quote(checkout_form_id, safe='')}/shipments",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        shipment_id = str(data.get("id") or "").strip()
        if not shipment_id:
            raise RuntimeError(f"Allegro shipment creation response did not include shipment id: {data}")
        return ShipmentResult(
            platform_shipment_id=shipment_id,
            tracking_number=str(data.get("waybill") or payload.get("waybill") or ""),
            carrier=str(data.get("carrierName") or data.get("carrierId") or payload.get("carrierId") or "Allegro"),
            status="created",
            raw_payload=data,
        )

    async def register_tracking_number(
        self,
        order: NormalizedOrder,
        tracking_number: str,
        carrier: str = "",
    ) -> ShipmentResult:
        """Register a WanbExpress waybill without creating an Allegro label.

        Allegro uses the checkout-form shipment endpoint for external waybills
        too.  The initial lookup makes retries idempotent when a timeout occurs
        after Allegro accepted the POST.
        """
        tracking_number = str(tracking_number or "").strip()
        if not tracking_number:
            raise ValueError("Allegro external tracking number is required.")
        if len(tracking_number) > 64:
            raise ValueError("Allegro external tracking number cannot exceed 64 characters.")

        checkout_form_id = self._checkout_form_lookup_id(
            order.platform_order_id or order.posting_number or order.platform_order_no
        )
        if not checkout_form_id:
            raise ValueError("Allegro checkoutFormId is required to register external tracking.")

        carrier_id = str(
            self.settings.get("wanbang_allegro_carrier_id")
            or self.settings.get("external_tracking_carrier_id")
            or "OTHER"
        ).strip()
        carrier_name = str(
            self.settings.get("wanbang_allegro_carrier_name")
            or self.settings.get("external_tracking_carrier_name")
            or carrier
            or "WanbExpress"
        ).strip()
        if carrier_id == "OTHER":
            if not carrier_name:
                raise ValueError("Allegro carrierName is required when carrierId is OTHER.")
            if len(carrier_name) > 30:
                raise ValueError("Allegro external carrierName cannot exceed 30 characters.")

        payload = {"carrierId": carrier_id, "waybill": tracking_number}
        if carrier_id == "OTHER":
            payload["carrierName"] = carrier_name
        line_item_ids = self._line_item_ids(order)
        if line_item_ids:
            payload["lineItems"] = [{"id": item_id} for item_id in line_item_ids]

        if self.settings.get("dry_run_fulfillment", False):
            return ShipmentResult(
                platform_shipment_id=checkout_form_id,
                tracking_number=tracking_number,
                carrier=carrier_name or carrier_id,
                status="dry_run_registered",
                raw_payload={"registration": "dry_run", "payload": payload},
            )

        async with httpx.AsyncClient(timeout=60) as client:
            shipments_payload = await self._fetch_order_shipments(client, checkout_form_id)
            shipments = shipments_payload.get("shipments") if isinstance(shipments_payload, dict) else []
            for existing in shipments if isinstance(shipments, list) else []:
                if not isinstance(existing, dict):
                    continue
                if str(existing.get("waybill") or "").strip() != tracking_number:
                    continue
                return ShipmentResult(
                    platform_shipment_id=str(existing.get("id") or "").strip(),
                    tracking_number=tracking_number,
                    carrier=str(existing.get("carrierName") or existing.get("carrierId") or carrier_name or carrier_id),
                    status="existing",
                    raw_payload={"registration": "existing", "shipment": existing},
                )

            response = await client.post(
                f"{self.base_url}/order/checkout-forms/{quote(checkout_form_id, safe='')}/shipments",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        shipment_id = str(data.get("id") or "").strip() if isinstance(data, dict) else ""
        if not shipment_id:
            raise RuntimeError(f"Allegro external tracking response did not include shipment id: {data}")
        return ShipmentResult(
            platform_shipment_id=shipment_id,
            tracking_number=str(data.get("waybill") or tracking_number),
            carrier=str(data.get("carrierName") or data.get("carrierId") or carrier_name or carrier_id),
            status="registered",
            raw_payload={"registration": "created", "shipment": data},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self.settings.get("dry_run_fulfillment", False):
            return LabelResult(
                content=build_preview_pdf(
                    "Allegro Label Preview",
                    [f"Order: {order.platform_order_id}", f"Shipment: {shipment.platform_shipment_id}"],
                )
            )
        lookup_id = self._checkout_form_lookup_id(order.platform_order_id or order.posting_number or order.platform_order_no)
        shipment_id = str(shipment.platform_shipment_id or "").strip()
        if lookup_id and shipment_id:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/pdf",
            }
            checkout_part = quote(str(lookup_id), safe="")
            shipment_part = quote(shipment_id, safe="")
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(
                    f"{self.base_url}/order/checkout-forms/{checkout_part}/shipments/{shipment_part}/label",
                    headers=headers,
                )
                if response.status_code < 400:
                    return LabelResult(content=response.content, content_type=response.headers.get("content-type") or "application/pdf")
                response_text = response.text[:500]
                if response.status_code != 404:
                    raise RuntimeError(
                        "Allegro 订单 shipment 面单接口不可用："
                        f"HTTP {response.status_code} {response_text}"
                    )

        payload = {"shipmentIds": [shipment.platform_shipment_id]}
        headers = {
            **self.headers,
            "Accept": "application/octet-stream, application/pdf, */*",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.base_url}/shipment-management/label", headers=headers, json=payload)
            if response.status_code == 204:
                raise RuntimeError("Allegro 未返回面单：该 shipment 当前没有可下载标签。")
            if response.status_code == 404:
                raise RuntimeError(
                    "Allegro 未找到面单 shipmentId；只有通过 Ship with Allegro/WZA 创建的 shipment 才能下载面单。"
                )
            if response.status_code == 406:
                raise RuntimeError(
                    "Allegro WZA 面单接口返回 406 Not Acceptable；当前 shipment 没有可下载平台面单。"
                )
            response.raise_for_status()
            return LabelResult(content=response.content)

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        checkout_form_ids = [str(value).strip() for value in posting_numbers if str(value or "").strip()]
        if not checkout_form_ids:
            return []
        results: list[OrderStatusUpdate] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for checkout_form_id in checkout_form_ids:
                lookup_id = self._checkout_form_lookup_id(checkout_form_id)
                response = await client.get(f"{self.base_url}/order/checkout-forms/{lookup_id}", headers=self.headers)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                form = response.json()
                if not isinstance(form, dict):
                    continue
                normalized = self._normalize_checkout_form(form)
                if not normalized:
                    continue
                if not self._form_tracking_number(form):
                    shipments_payload = await self._fetch_order_shipments(client, lookup_id)
                    self._apply_order_shipments(form, shipments_payload)
                    normalized = self._normalize_checkout_form(form)
                    if not normalized:
                        continue
                delivery = form.get("delivery") if isinstance(form.get("delivery"), dict) else {}
                fulfillment = form.get("fulfillment") if isinstance(form.get("fulfillment"), dict) else {}
                tracking_number = self._first(
                    normalized.raw_payload.get("shipment_tracking_number"),
                    normalized.raw_payload.get("tracking_number"),
                    delivery.get("trackingNumber"),
                    delivery.get("tracking_number"),
                )
                results.append(
                    OrderStatusUpdate(
                        posting_number=checkout_form_id,
                        platform_order_id=normalized.platform_order_id,
                        platform_order_no=normalized.platform_order_no,
                        platform_status=str(self._first(fulfillment.get("status"), form.get("status"), normalized.platform_status) or ""),
                        shipment_tracking_number=str(tracking_number or ""),
                        raw_payload=normalized.raw_payload,
                    )
                )
        return results
