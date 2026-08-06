# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from typing import Any

from pydantic import BaseModel, Field


class ConnectorError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    raw: Any = None


class ConnectorResponse(BaseModel):
    ok: bool
    platform: str
    adapter_version: str = "1.0.0"
    data: Any = None
    error: ConnectorError | None = None


class ConnectorRequest(BaseModel):
    credentials: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)
    account_id: str = ""


class FetchOrdersRequest(ConnectorRequest):
    since: str | None = None


class SearchOrdersRequest(ConnectorRequest):
    start: str
    end: str | None = None
    date_field: str = "lineItems.boughtAt"
    status: str = ""
    fulfillment_status: str = ""
    limit: int = 100
    max_pages: int = 0


class TrafficRequest(ConnectorRequest):
    start: str
    end: str
    timeout_seconds: float | None = None


class ProductInfoRequest(ConnectorRequest):
    offer_ids: list[str] = Field(default_factory=list)


class PlatformProductCatalogRequest(ConnectorRequest):
    since: str | None = None


class StatusUpdatesRequest(ConnectorRequest):
    posting_numbers: list[str] = Field(default_factory=list)


class ShipmentRequest(ConnectorRequest):
    order: dict


class TrackingRegistrationRequest(ConnectorRequest):
    order: dict
    tracking_number: str
    carrier: str = ""


class LabelRequest(ConnectorRequest):
    shipment: dict
    order: dict


class LabelBatchRequest(ConnectorRequest):
    orders: list[dict] = Field(default_factory=list)
