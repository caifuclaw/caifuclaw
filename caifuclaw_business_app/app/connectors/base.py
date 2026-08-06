# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NormalizedOrder:
    platform_order_id: str
    platform_status: str
    raw_payload: dict
    platform_order_no: str = ""
    posting_number: str = ""
    fulfillment_type: str = "FBS"  # FBS / FBP / FBO / SDS / Crossborder
    is_overseas_warehouse: bool = False


@dataclass
class OrderStatusUpdate:
    """Lightweight structure for status-only updates from platform."""
    posting_number: str
    platform_order_id: str
    platform_status: str
    platform_order_no: str = ""
    shipment_tracking_number: str = ""
    handover_at: str = ""
    raw_payload: dict = field(default_factory=dict)


@dataclass
class ShipmentResult:
    platform_shipment_id: str = ""
    tracking_number: str = ""
    carrier: str = ""
    status: str = "created"
    raw_payload: dict = field(default_factory=dict)


@dataclass
class LabelResult:
    content: bytes
    content_type: str = "application/pdf"
    file_extension: str = ".pdf"
    raw_payload: dict = field(default_factory=dict)


class MarketplaceConnector:
    platform = ""

    async def fetch_unprocessed_orders(self, since: Optional[datetime] = None) -> list[NormalizedOrder]:
        """获取未处理的订单
        
        Args:
            since: 增量同步的起始时间。如果为 None，则进行全量同步
        
        Returns:
            标准化订单列表
        """
        raise NotImplementedError

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        raise NotImplementedError

    async def register_tracking_number(
        self,
        order: NormalizedOrder,
        tracking_number: str,
        carrier: str = "",
    ) -> ShipmentResult:
        return ShipmentResult(
            tracking_number=str(tracking_number or "").strip(),
            carrier=str(carrier or "").strip(),
            status="unsupported",
            raw_payload={"reason": "external tracking registration is not supported by this connector"},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        raise NotImplementedError

    async def fetch_label_batch(self, orders: list[NormalizedOrder]) -> LabelResult:
        """批量拉取真实面单（不走 dry-run）。返回合并后的单个 PDF。
        默认实现：由子类自行实现平台批量接口。"""
        raise NotImplementedError

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list["OrderStatusUpdate"]:
        """Fetch latest platform status for given posting_numbers.
        Default implementation returns empty list (platform does not support status refresh)."""
        return []
