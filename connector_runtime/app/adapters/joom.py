import asyncio
import csv
import io
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .pdf_preview import build_preview_pdf


class JoomLogisticsConnector(MarketplaceConnector):
    platform = "joom_logistics"
    _TRAFFIC_PERIODS = {7: "1w", 14: "2w", 28: "4w"}
    _TRAFFIC_METRIC_FIELDS = (
        "impressions",
        "clicks",
        "add_to_cart",
        "orders",
        "units_sold",
        "favourites",
    )

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.access_token = credentials.get("access_token") or ("" if credentials.get("client_secret") else credentials.get("api_key", ""))
        self.settings = settings or {}
        self.base_url = self.settings["base_url"]

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def fetch_traffic(self, start: datetime, end: datetime) -> list[dict]:
        period_days = (end.date() - start.date()).days + 1
        metrics_period = self._TRAFFIC_PERIODS.get(period_days)
        if not metrics_period:
            raise ValueError("Joom Product Ranking supports only the latest 7, 14, or 28 complete days")

        period_end = end.date()

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            store_id = await self._traffic_store_id(client)
            as_of_date = await self._traffic_as_of_date(client, store_id)
            if as_of_date and period_end < as_of_date:
                raise ValueError(
                    f"Joom Product Ranking is available only through {as_of_date.isoformat()}, "
                    f"not {period_end.isoformat()}"
                )
            if as_of_date:
                period_end = as_of_date

            period_start = period_end - timedelta(days=period_days - 1)
            previous_end = period_start - timedelta(days=1)
            previous_start = previous_end - timedelta(days=period_days - 1)

            wider_period = {7: "2w", 14: "4w"}.get(period_days)
            reports = [await self._download_product_ranking(client, store_id, metrics_period, period_end)]
            if wider_period:
                reports.append(await self._download_product_ranking(client, store_id, wider_period, period_end))
            negative_reviews = await self._fetch_negative_reviews(
                client,
                store_id,
                previous_start if wider_period else period_start,
                period_end,
            )

        rows = self._traffic_rows_from_report(
            reports[0],
            period_start=period_start,
            period_end=period_end,
            metrics_period=metrics_period,
            negative_reviews=negative_reviews,
        )
        if wider_period:
            previous_report = self._subtract_traffic_reports(reports[1], reports[0])
            rows.extend(
                self._traffic_rows_from_report(
                    previous_report,
                    period_start=previous_start,
                    period_end=previous_end,
                    metrics_period=wider_period,
                    derived_previous=True,
                    negative_reviews=negative_reviews,
                )
            )
        return rows

    async def _fetch_negative_reviews(
        self,
        client: httpx.AsyncClient,
        store_id: str,
        start: date,
        end: date,
    ) -> dict[tuple[str, str], int] | None:
        counts: dict[tuple[str, str], int] = {}
        offset = 0
        limit = 100
        for _ in range(500):
            try:
                response = await client.get(
                    f"{self.base_url.rstrip('/')}/reviews/multi",
                    headers=self.headers,
                    params={"limit": limit, "offset": offset, "storeId": store_id},
                )
                data = self._response_data(response)
            except (httpx.HTTPError, RuntimeError):
                return None
            items = data.get("items") if isinstance(data, dict) else []
            items = items if isinstance(items, list) else []
            oldest_date = ""
            for item in items:
                if not isinstance(item, dict):
                    continue
                review_date = str(item.get("reviewTimestamp") or "")[:10]
                if not review_date:
                    continue
                oldest_date = min(oldest_date or review_date, review_date)
                if review_date < start.isoformat() or review_date > end.isoformat():
                    continue
                try:
                    rating = int(item.get("starRating") or 0)
                except (TypeError, ValueError):
                    continue
                if 0 < rating <= 2:
                    product_id = str(item.get("productId") or "").strip()
                    if product_id:
                        key = (product_id, review_date)
                        counts[key] = counts.get(key, 0) + 1
            if len(items) < limit or (oldest_date and oldest_date < start.isoformat()):
                break
            offset += limit
        return counts

    @staticmethod
    def _response_data(response: httpx.Response):
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Joom returned an invalid response")
        if payload.get("code") not in (None, 0):
            raise RuntimeError(str(payload.get("message") or "Joom request failed"))
        return payload.get("data")

    async def _traffic_store_id(self, client: httpx.AsyncClient) -> str:
        response = await client.get(f"{self.base_url.rstrip('/')}/stores/all", headers=self.headers)
        data = self._response_data(response)
        items = data.get("items") if isinstance(data, dict) else data
        stores = [item for item in items or [] if isinstance(item, dict) and item.get("id")]
        configured_id = str(self.settings.get("joom_store_id") or self.settings.get("store_id") or "").strip()
        if configured_id:
            if any(str(item.get("id")) == configured_id for item in stores):
                return configured_id
            raise ValueError(f"Configured Joom store was not found: {configured_id}")

        configured_name = str(
            self.settings.get("joom_store_name")
            or self.settings.get("display_name")
            or ""
        ).strip().casefold()
        if configured_name:
            matched = [item for item in stores if str(item.get("name") or "").strip().casefold() == configured_name]
            if len(matched) == 1:
                return str(matched[0]["id"])
        if len(stores) == 1:
            return str(stores[0]["id"])
        raise ValueError("Unable to resolve a unique Joom store for Product Ranking")

    async def _traffic_as_of_date(self, client: httpx.AsyncClient, store_id: str) -> date | None:
        response = await client.post(
            f"{self.base_url.rstrip('/')}/products/multi",
            headers=self.headers,
            json={"offset": 0, "limit": 1, "storeId": store_id},
        )
        data = self._response_data(response)
        items = data.get("items") if isinstance(data, dict) else []
        if not items or not isinstance(items[0], dict):
            return None
        metrics = items[0].get("metrics") if isinstance(items[0].get("metrics"), dict) else {}
        raw_date = str(metrics.get("asOfDate") or "")[:10]
        if not raw_date:
            return None
        try:
            return datetime.fromisoformat(raw_date).date()
        except ValueError:
            return None

    async def _download_product_ranking(
        self,
        client: httpx.AsyncClient,
        store_id: str,
        metrics_period: str,
        period_end: date,
    ) -> dict[str, dict]:
        response = await client.post(
            f"{self.base_url.rstrip('/')}/products/periodMetrics/downloads/create",
            headers=self.headers,
            json={
                "metricsPeriod": metrics_period,
                "storeId": store_id,
                "sendEmail": False,
                "fileName": f"traffic-{store_id}-{metrics_period}-{period_end.isoformat()}",
            },
        )
        data = self._response_data(response)
        download_id = str(data.get("id") or "") if isinstance(data, dict) else ""
        if not download_id:
            raise RuntimeError("Joom Product Ranking download did not return an id")

        try:
            poll_interval = max(0.0, float(self.settings.get("joom_traffic_poll_interval_seconds", 1)))
        except (TypeError, ValueError):
            poll_interval = 1.0
        try:
            timeout = max(10.0, float(self.settings.get("joom_traffic_report_timeout_seconds", 600)))
        except (TypeError, ValueError):
            timeout = 600.0
        deadline = asyncio.get_running_loop().time() + timeout
        download_url = ""
        while True:
            status_response = await client.get(
                f"{self.base_url.rstrip('/')}/downloads",
                headers=self.headers,
                params={"id": download_id},
            )
            status_data = self._response_data(status_response)
            status = str(status_data.get("status") or "") if isinstance(status_data, dict) else ""
            if status in {"finished", "finishedWithErrors"}:
                download_url = str(status_data.get("csvFileUrl") or status_data.get("fileUrl") or "")
                if download_url:
                    break
                raise RuntimeError("Joom Product Ranking download finished without a file URL")
            if status in {"failed", "validationFailed", "expired"}:
                errors = status_data.get("validationErrors") if isinstance(status_data, dict) else None
                raise RuntimeError(f"Joom Product Ranking download failed: {errors or status}")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Joom Product Ranking download timed out")
            await asyncio.sleep(poll_interval)

        parsed_url = urlparse(download_url)
        base_host = urlparse(self.base_url).hostname or ""
        download_host = parsed_url.hostname or ""
        if parsed_url.scheme != "https" or not (
            download_host == base_host or download_host.endswith(".amazonaws.com")
        ):
            raise ValueError("Joom Product Ranking returned an unexpected download URL")
        file_response = await client.get(download_url)
        file_response.raise_for_status()
        return self._parse_product_ranking_csv(file_response.content)

    @staticmethod
    def _metric_int(value) -> int:
        text = str(value or "0").strip().replace(",", "")
        try:
            return int(text or 0)
        except ValueError:
            return int(float(text or 0))

    @classmethod
    def _parse_product_ranking_csv(cls, content: bytes) -> dict[str, dict]:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        required = {
            "Product ID",
            "SKU",
            "Name",
            "Store ID",
            "Impressions",
            "Opens",
            "Cart",
            "Purchases",
            "Sales",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Joom Product Ranking CSV has unexpected columns")
        result: dict[str, dict] = {}
        for row in reader:
            product_id = str(row.get("Product ID") or "").strip()
            if not product_id:
                continue
            result[product_id] = {
                "product_id": product_id,
                "sku": str(row.get("SKU") or "").strip(),
                "product_name": str(row.get("Name") or "").strip(),
                "store_id": str(row.get("Store ID") or "").strip(),
                "category": str(row.get("Category") or "").strip(),
                "category_id": str(row.get("Category ID") or "").strip(),
                "metrics": {
                    "impressions": cls._metric_int(row.get("Impressions")),
                    "clicks": cls._metric_int(row.get("Opens")),
                    "add_to_cart": cls._metric_int(row.get("Cart")),
                    "orders": cls._metric_int(row.get("Purchases")),
                    "units_sold": cls._metric_int(row.get("Sales")),
                    "favourites": cls._metric_int(row.get("Favourites")),
                },
            }
        return result

    @classmethod
    def _subtract_traffic_reports(
        cls,
        wider: dict[str, dict],
        current: dict[str, dict],
    ) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for product_id, wider_item in wider.items():
            current_metrics = current.get(product_id, {}).get("metrics", {})
            metrics = {
                field: max(
                    0,
                    int(wider_item.get("metrics", {}).get(field) or 0)
                    - int(current_metrics.get(field) or 0),
                )
                for field in cls._TRAFFIC_METRIC_FIELDS
            }
            ranked_fields = ("impressions", "clicks", "add_to_cart", "orders", "units_sold")
            if not any(metrics[field] for field in ranked_fields):
                continue
            result[product_id] = {**wider_item, "metrics": metrics}
        return result

    @classmethod
    def _traffic_rows_from_report(
        cls,
        report: dict[str, dict],
        *,
        period_start: date,
        period_end: date,
        metrics_period: str,
        derived_previous: bool = False,
        negative_reviews: dict[tuple[str, str], int] | None = None,
    ) -> list[dict]:
        rows: list[dict] = []
        for product_id in sorted(report):
            item = report[product_id]
            metrics = item.get("metrics", {})
            negative_count = None
            if negative_reviews is not None:
                negative_count = sum(
                    negative_reviews.get((product_id, review_day), 0)
                    for review_day in (
                        (period_start + timedelta(days=offset)).isoformat()
                        for offset in range((period_end - period_start).days + 1)
                    )
                )
            rows.append(
                {
                    "source": "platform",
                    "grain": "date_range",
                    "stat_date": period_end.isoformat(),
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "region": "",
                    "entity_type": "sku",
                    "entity_id": product_id,
                    "sku": item.get("sku") or "",
                    "product_name": item.get("product_name") or "",
                    "impressions": metrics.get("impressions"),
                    "clicks": metrics.get("clicks"),
                    "add_to_cart": metrics.get("add_to_cart"),
                    "orders": metrics.get("orders"),
                    "buyers": None,
                    "units_sold": metrics.get("units_sold"),
                    "negative_reviews": negative_count,
                    "revenue": None,
                    "currency": "",
                    "raw_data": {
                        "metric_source": "joom_product_ranking",
                        "metrics_period": metrics_period,
                        "derived_previous": derived_previous,
                        "store_id": item.get("store_id") or "",
                        "category": item.get("category") or "",
                        "category_id": item.get("category_id") or "",
                        "platform_category_id": item.get("category_id") or "",
                        "platform_category_name": item.get("category") or "",
                        "platform_category_path": item.get("category") or "",
                        "favourites": metrics.get("favourites"),
                        "negative_reviews_source": "joom_reviews" if negative_reviews is not None else "unavailable",
                        "negative_reviews_daily": (
                            {
                                review_day: count
                                for offset in range((period_end - period_start).days + 1)
                                for review_day in [(period_start + timedelta(days=offset)).isoformat()]
                                for count in [negative_reviews.get((product_id, review_day), 0)]
                                if count
                            }
                            if negative_reviews is not None
                            else {}
                        ),
                    },
                }
            )
        return rows

    def _download_overseas_warehouse_orders(self) -> bool:
        return bool(self.settings.get("download_overseas_warehouse_orders", False))

    def _download_full_orders(self) -> bool:
        return bool(self.settings.get("full_refresh", False)) or bool(
            self.settings.get("joom_use_orders_multi_incremental", False)
        )

    def _order_limit(self) -> int:
        try:
            limit = int(self.settings.get("limit", 500 if self._download_full_orders() else 100))
        except (TypeError, ValueError):
            limit = 500 if self._download_full_orders() else 100
        return max(1, min(limit, 500))

    def _max_pages(self) -> int:
        try:
            value = int(self.settings.get("max_pages", 100))
        except (TypeError, ValueError):
            value = 100
        return max(1, value)

    @staticmethod
    def _warehouse_type_values(item: dict) -> list:
        shipping_option = item.get("shippingOption") if isinstance(item.get("shippingOption"), dict) else {}
        shipping_option_snake = item.get("shipping_option") if isinstance(item.get("shipping_option"), dict) else {}
        warehouse = item.get("warehouse") if isinstance(item.get("warehouse"), dict) else {}
        return [
            item.get("fulfillmentType"),
            item.get("fulfillment_type"),
            item.get("deliveryType"),
            item.get("delivery_type"),
            item.get("logisticsType"),
            item.get("logistics_type"),
            item.get("warehouseType"),
            item.get("warehouse_type"),
            shipping_option.get("warehouseType"),
            shipping_option.get("warehouse_type"),
            shipping_option_snake.get("warehouseType"),
            shipping_option_snake.get("warehouse_type"),
            warehouse.get("type"),
            warehouse.get("warehouseType"),
            warehouse.get("warehouse_type"),
        ]

    @classmethod
    def _is_physical_warehouse_order(cls, item: dict) -> bool:
        return any(
            str(value or "").strip().replace("_", "").replace("-", "").lower() == "physical"
            for value in cls._warehouse_type_values(item)
        )

    @classmethod
    def _is_overseas_warehouse_order(cls, item: dict) -> bool:
        shipping_option = item.get("shippingOption") if isinstance(item.get("shippingOption"), dict) else {}
        shipping_option_snake = item.get("shipping_option") if isinstance(item.get("shipping_option"), dict) else {}
        warehouse = item.get("warehouse") if isinstance(item.get("warehouse"), dict) else {}
        warehouse_type_values = cls._warehouse_type_values(item)
        type_text = " ".join(str(value) for value in warehouse_type_values if value is not None).lower()
        if cls._is_physical_warehouse_order(item) or any(
            marker in type_text for marker in ("fbj", "overseas", "fulfillment")
        ):
            return True

        values = [
            item.get("warehouse"),
            item.get("source"),
            shipping_option.get("warehouseName"),
            shipping_option.get("warehouse_name"),
            shipping_option_snake.get("warehouseName"),
            shipping_option_snake.get("warehouse_name"),
            warehouse.get("name"),
            warehouse.get("warehouseName"),
            warehouse.get("warehouse_name"),
        ]
        text = " ".join(str(value) for value in values if value is not None).lower()
        if any(marker in text for marker in ("fbj", "overseas", "fulfillment")):
            return True
        return "joom logistics" in text and "warehouse" in text

    @classmethod
    def _order_fulfillment_type(cls, item: dict, is_overseas_warehouse: bool) -> str:
        explicit_type = str(
            cls._first(item.get("fulfillmentType"), item.get("fulfillment_type"), "FBS") or "FBS"
        ).upper()
        if any(marker in explicit_type.lower() for marker in ("fbj", "overseas", "fulfillment")):
            return "FBJ"
        if cls._is_physical_warehouse_order(item):
            return "PHYSICAL"
        return "FBJ" if is_overseas_warehouse else explicit_type

    @staticmethod
    def _first(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _iso_utc(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _full_sync_updated_from(self) -> str | None:
        return (
            self.settings.get("joom_full_sync_updated_from")
            or self.settings.get("full_sync_updated_from")
            or self.settings.get("updated_from")
        )

    def _full_sync_created_from(self) -> str | None:
        return (
            self.settings.get("joom_full_sync_created_from")
            or self.settings.get("full_sync_created_from")
            or self.settings.get("order_created_from")
            or self.settings.get("created_from")
        )

    @staticmethod
    def _datetime_gte(value: datetime, cutoff: datetime) -> bool:
        if value.tzinfo is None and cutoff.tzinfo is not None:
            value = value.replace(tzinfo=timezone.utc)
        if value.tzinfo is not None and cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        return value >= cutoff

    def _include_order_item(self, item: dict) -> bool:
        if not self._download_full_orders():
            return True
        created_from = self._full_sync_created_from()
        if not created_from:
            return True
        cutoff = self._parse_iso_datetime(created_from)
        created_at = self._parse_iso_datetime(
            self._first(item.get("orderTimestamp"), item.get("createdAt"), item.get("created_at"))
        )
        if not cutoff or not created_at:
            return True
        return self._datetime_gte(created_at, cutoff)

    def _tracking_number(self, item: dict) -> str | None:
        shipment = item.get("shipment") if isinstance(item.get("shipment"), dict) else {}
        shipping = item.get("shipping") if isinstance(item.get("shipping"), dict) else {}
        logistics = item.get("logistics") if isinstance(item.get("logistics"), dict) else {}
        tracking = item.get("tracking") if isinstance(item.get("tracking"), dict) else {}
        return self._first(
            item.get("shipment_tracking_number"),
            item.get("trackingNumber"),
            item.get("tracking_number"),
            item.get("trackNumber"),
            item.get("track_number"),
            item.get("trackingNo"),
            item.get("tracking_no"),
            item.get("waybillNumber"),
            item.get("waybill_number"),
            shipment.get("trackingNumber"),
            shipment.get("tracking_number"),
            shipment.get("trackNumber"),
            shipment.get("track_number"),
            shipment.get("trackingNo"),
            shipment.get("tracking_no"),
            shipment.get("waybillNumber"),
            shipment.get("waybill_number"),
            shipping.get("trackingNumber"),
            shipping.get("tracking_number"),
            logistics.get("trackingNumber"),
            logistics.get("tracking_number"),
            tracking.get("trackingNumber"),
            tracking.get("tracking_number"),
            tracking.get("number"),
        )

    def _fulfillment_deadline(self, item: dict) -> str | None:
        base = self._parse_iso_datetime(
            self._first(item.get("approvedTimestamp"), item.get("orderTimestamp"), item.get("updateTimestamp"))
        )
        if base and (item.get("daysToFulfill") not in (None, "") or item.get("hoursToFulfill") not in (None, "")):
            try:
                deadline = base + timedelta(
                    days=int(item.get("daysToFulfill") or 0),
                    hours=int(item.get("hoursToFulfill") or 0),
                )
                return deadline.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            except (TypeError, ValueError):
                pass
        return item.get("fulfillmentAllowedTimestamp")

    def _normalize_order_payload(self, item: dict) -> dict:
        product = item.get("product") if isinstance(item.get("product"), dict) else {}
        variant = product.get("variant") if isinstance(product.get("variant"), dict) else {}
        price_info = item.get("priceInfo") if isinstance(item.get("priceInfo"), dict) else {}
        shipping_address = item.get("shippingAddress") if isinstance(item.get("shippingAddress"), dict) else {}
        shipping_option = item.get("shippingOption") if isinstance(item.get("shippingOption"), dict) else {}
        shipment = item.get("shipment") if isinstance(item.get("shipment"), dict) else {}
        currency = self._first(item.get("currency"), price_info.get("currency"))
        # orderPrice is the line/order total when quantity > 1; keep the
        # per-unit value for order_items and use orderPrice below for totals.
        unit_price = self._first(price_info.get("unitPrice"), price_info.get("orderPrice"), item.get("price"))
        fulfillment_deadline = self._fulfillment_deadline(item)
        tracking_number = self._tracking_number(item)
        is_overseas_warehouse = self._is_overseas_warehouse_order(item)
        fulfillment_type = self._order_fulfillment_type(item, is_overseas_warehouse)
        return {
            **item,
            "site": self._first(item.get("marketplace"), item.get("source"), "Joom"),
            "fulfillment_type": fulfillment_type,
            "is_overseas_warehouse": is_overseas_warehouse,
            "customer_id": item.get("customerId"),
            "buyer_id": item.get("customerId"),
            "country_code": shipping_address.get("country"),
            "order_amount": self._first(price_info.get("orderPrice"), price_info.get("origAmount"), item.get("amount")),
            "currency_code": currency,
            "payment_at": self._first(item.get("approvedTimestamp"), item.get("orderTimestamp")),
            "created_at": item.get("orderTimestamp"),
            "shipping_deadline_at": fulfillment_deadline,
            "platform_handover_deadline": fulfillment_deadline,
            "trackingNumber": tracking_number,
            "tracking_number": tracking_number,
            "shipment_tracking_number": tracking_number,
            "handover_at": self._first(
                shipment.get("fulfilledTimestamp"),
                shipment.get("shippedTimestamp"),
                shipment.get("timestamp"),
            ),
            "shipped_at": self._first(
                shipment.get("shippedTimestamp"),
                shipment.get("fulfilledTimestamp"),
                shipment.get("timestamp"),
            ),
            "buyer_selected_logistics": self._first(
                item.get("shippingMethod"),
                shipping_option.get("tierName"),
                shipping_option.get("tierType"),
            ),
            "products": [
                {
                    "sku": self._first(variant.get("sku"), product.get("sku"), product.get("id")),
                    "name": product.get("name"),
                    "product_id": product.get("id"),
                    "variant_id": variant.get("id"),
                    "quantity": item.get("quantity") or 1,
                    "price": unit_price,
                    "currency_code": currency,
                    "raw_payload": product,
                }
            ],
        }

    @staticmethod
    def _items_from_response(data: dict) -> list:
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        if isinstance(data.get("data"), list):
            return data["data"]
        if not isinstance(payload, dict):
            return []
        return payload.get("items") or payload.get("orders") or data.get("orders") or data.get("items") or []

    def _is_next_url_allowed(self, next_url: str) -> bool:
        parsed_base = urlparse(self.base_url)
        parsed_next = urlparse(next_url)
        return parsed_next.scheme == parsed_base.scheme and parsed_next.netloc == parsed_base.netloc

    def _orders_path_and_params(self, since: datetime | None) -> tuple[str, dict]:
        if self._download_full_orders():
            params = {"limit": self._order_limit()}
            updated_from = self._iso_utc(since) if since else self._full_sync_updated_from()
            if updated_from:
                params["updatedFrom"] = updated_from
            return "/orders/multi", params
        params = {"limit": self._order_limit()}
        if bool(self.settings.get("joom_unfulfilled_use_updated_from", False)):
            updated_from = self._iso_utc(since) if since else self._full_sync_updated_from()
            if updated_from:
                params["updatedFrom"] = updated_from
        return self.settings.get("orders_path", "/orders/unfulfilled"), params

    def _fulfill_online_payload(self, order: NormalizedOrder) -> dict:
        template = self.settings.get("fulfill_payload_template", {})
        payload = dict(template) if isinstance(template, dict) else {}
        payload["ids"] = payload.get("ids") or [order.platform_order_id]

        provider = self._first(self.settings.get("joom_shipping_provider"), self.settings.get("provider"))
        provider_id = self._first(self.settings.get("joom_shipping_provider_id"), self.settings.get("providerId"))
        if provider and provider_id:
            raise ValueError("Joom online shipping accepts either provider or providerId, not both")
        if provider:
            payload.setdefault("provider", provider)
        if provider_id:
            payload.setdefault("providerId", provider_id)

        pickup = self.settings.get("joom_pickup")
        if pickup is not None:
            payload.setdefault("pickup", bool(pickup))
        pickup_address_id = self._first(self.settings.get("joom_pickup_address_id"), self.settings.get("pickupAddressId"))
        if pickup_address_id:
            payload.setdefault("pickupAddressId", pickup_address_id)
        return payload

    async def fetch_platform_products(self, since: datetime | None = None) -> list[dict]:
        """Fetch Joom store products using the pageable merchant products API."""
        catalog_path = str(self.settings.get("catalog_products_path") or "/products/multi").strip()
        if not catalog_path.startswith("/"):
            catalog_path = f"/{catalog_path}"
        page_size = max(1, min(int(self.settings.get("catalog_page_size", 100) or 100), 500))
        rows: list[dict] = []
        next_url = ""
        async with httpx.AsyncClient(timeout=90) as client:
            store_id = str(self.settings.get("catalog_store_id") or "").strip()
            if not store_id:
                store_id = await self._traffic_store_id(client)
            params: dict[str, object] = {"limit": page_size}
            if store_id:
                params["storeId"] = store_id
            for _ in range(self._max_pages()):
                if next_url:
                    if not self._is_next_url_allowed(next_url):
                        raise ValueError("Joom catalog paging.next points to an unexpected host")
                    response = await client.get(next_url, headers=self.headers)
                else:
                    response = await client.get(f"{self.base_url}{catalog_path}", headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
                page = []
                if isinstance(payload, dict):
                    for key in ("products", "items", "results"):
                        if isinstance(payload.get(key), list):
                            page = [item for item in payload[key] if isinstance(item, dict)]
                            break
                elif isinstance(payload, list):
                    page = [item for item in payload if isinstance(item, dict)]
                rows.extend(page)
                paging = payload.get("paging") if isinstance(payload, dict) and isinstance(payload.get("paging"), dict) else {}
                next_url = str(paging.get("next") or "")
                if not next_url:
                    break
            else:
                raise RuntimeError("Joom product catalog pagination exceeded the safety limit")

        normalized: list[dict] = []
        for item in rows:
            product = item.get("product") if isinstance(item.get("product"), dict) else item
            variants = product.get("variants") if isinstance(product.get("variants"), list) else []
            variants = [value for value in variants if isinstance(value, dict)] or [{}]
            warehouse = item.get("warehouse") if isinstance(item.get("warehouse"), dict) else {}
            for variant in variants:
                inventory = variant.get("inventory") if isinstance(variant.get("inventory"), dict) else {}
                price = variant.get("price") if isinstance(variant.get("price"), dict) else {}
                product_id = str(variant.get("id") or product.get("id") or item.get("id") or "").strip()
                sku = str(variant.get("sku") or product.get("sku") or product_id).strip()
                if not product_id and not sku:
                    continue
                normalized.append(
                    {
                        "platform_product_id": product_id,
                        "platform_sku": sku,
                        "product_name": str(product.get("name") or product.get("title") or ""),
                        "listing_status": str(product.get("status") or item.get("status") or ""),
                        "warehouse_code": str(warehouse.get("id") or warehouse.get("code") or warehouse.get("name") or ""),
                        "warehouse_name": str(warehouse.get("name") or ""),
                        "fulfillment_type": str(product.get("fulfillmentType") or warehouse.get("type") or ""),
                        "logistics_type": str(product.get("shippingMethod") or item.get("shippingMethod") or ""),
                        "available_stock": inventory.get("available") or variant.get("availableQuantity") or variant.get("stock") or product.get("stock") or 0,
                        "reserved_stock": inventory.get("reserved"),
                        "price_amount": price.get("amount") or variant.get("price") or product.get("price"),
                        "price_currency": str(price.get("currency") or variant.get("currency") or product.get("currency") or "USD"),
                        "raw_payload": {"product": product, "variant": variant, "warehouse": warehouse},
                    }
                )
        return normalized

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        path, params = self._orders_path_and_params(since)
        if not self._download_full_orders() and self.settings.get("order_status"):
            params["status"] = self.settings.get("order_status")
        elif not self._download_full_orders():
            params["status"] = "approved"

        orders: list[NormalizedOrder] = []
        next_url = ""
        pages = 0
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                if next_url:
                    if not self._is_next_url_allowed(next_url):
                        raise ValueError("Joom paging.next points to an unexpected host")
                    response = await client.get(next_url, headers=self.headers)
                else:
                    response = await client.get(f"{self.base_url}{path}", headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                pages += 1
                for item in self._items_from_response(data):
                    if not self._include_order_item(item):
                        continue
                    order_id = item.get("id") or item.get("orderId")
                    status = str(item.get("status") or "")
                    is_overseas_warehouse = self._is_overseas_warehouse_order(item)
                    if not self._download_overseas_warehouse_orders() and is_overseas_warehouse:
                        continue
                    if order_id:
                        normalized_id = str(order_id)
                        fulfillment_type = self._order_fulfillment_type(item, is_overseas_warehouse)
                        orders.append(
                            NormalizedOrder(
                                normalized_id,
                                status,
                                self._normalize_order_payload(item),
                                platform_order_no=normalized_id,
                                fulfillment_type=fulfillment_type,
                                is_overseas_warehouse=is_overseas_warehouse,
                            )
                        )
                next_url = str((data.get("paging") or {}).get("next") or "")
                if not next_url or pages >= self._max_pages():
                    break
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        order_ids = [str(value).strip() for value in posting_numbers if str(value or "").strip()]
        if not order_ids:
            return []
        results: list[OrderStatusUpdate] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for order_id in order_ids:
                response = await client.get(
                    f"{self.base_url}/orders",
                    headers=self.headers,
                    params={"id": order_id},
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                payload = response.json()
                item = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_order_payload(item)
                shipment = item.get("shipment") if isinstance(item.get("shipment"), dict) else {}
                tracking_number = str(self._tracking_number(item) or "")
                handover_at = str(
                    self._first(
                        shipment.get("fulfilledTimestamp"),
                        shipment.get("shippedTimestamp"),
                        shipment.get("timestamp"),
                    )
                    or ""
                )
                results.append(
                    OrderStatusUpdate(
                        posting_number=order_id,
                        platform_order_id=str(item.get("id") or order_id),
                        platform_order_no=str(item.get("id") or order_id),
                        platform_status=str(item.get("status") or ""),
                        shipment_tracking_number=tracking_number,
                        handover_at=handover_at,
                        raw_payload=normalized,
                    )
                )
        return results

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        if self.settings.get("dry_run_fulfillment", True):
            return ShipmentResult(order.platform_order_id, order.platform_order_id, "Joom Logistics", "dry_run_created", order.raw_payload)
        payload = self._fulfill_online_payload(order)
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/orders/fulfillOnline",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        result = data.get("data") if isinstance(data.get("data"), dict) else data
        shipment_id = str(result.get("shippingOrderNumber") or result.get("shipmentId") or result.get("id") or order.platform_order_id)
        tracking_number = str(result.get("trackingNumber") or shipment_id)
        return ShipmentResult(
            platform_shipment_id=shipment_id,
            tracking_number=tracking_number,
            carrier=str(result.get("shipperName") or "Joom Logistics"),
            status=str(result.get("status") or "fulfilledOnline"),
            raw_payload=data,
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self.settings.get("dry_run_fulfillment", True):
            return LabelResult(
                content=build_preview_pdf(
                    "Joom Logistics Label Preview",
                    [f"Order: {order.platform_order_id}", f"Shipment: {shipment.platform_shipment_id}"],
                )
            )
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.base_url}/orders/shippingLabel",
                headers=self.headers,
                params={"id": order.platform_order_id},
            )
            response.raise_for_status()
            return LabelResult(content=response.content)
