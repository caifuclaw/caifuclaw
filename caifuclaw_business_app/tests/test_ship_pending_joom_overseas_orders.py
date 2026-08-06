# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import LogisticsMatchRule, Order, OrderOperationLog
from scripts.ship_pending_joom_overseas_orders import process_pending_joom_overseas_orders


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[LogisticsMatchRule.__table__, Order.__table__, OrderOperationLog.__table__],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _order(
    *,
    order_id: int,
    order_no: str,
    warehouse_type: str,
    status: str = "待处理",
    warehouse_name: str | None = None,
) -> Order:
    return Order(
        id=order_id,
        tenant_id="default",
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        shop_id="JOOM-DEMO-001",
        shop_name="Joom Demo Shop",
        platform_order_id=order_no,
        platform_order_no=order_no,
        biz_status=status,
        local_status="new",
        fulfillment_type="FBJ" if warehouse_type == "fulfillment" else "DEFAULT",
        is_overseas_warehouse=warehouse_type == "fulfillment",
        raw_payload={
            "shippingOption": {
                "warehouseName": warehouse_name or ("Joom Logistics CN Warehouse" if warehouse_type == "fulfillment" else "Default warehouse"),
                "warehouseType": warehouse_type,
            }
        },
        last_api_payload={},
    )


def test_legacy_shipping_script_does_not_select_fbj_orders():
    session_factory = _session_factory()
    with session_factory() as db:
        target = _order(order_id=1, order_no="JOOM-FBJ-1", warehouse_type="fulfillment")
        normal = _order(order_id=2, order_no="JOOM-DEFAULT-1", warehouse_type="default")
        db.add_all([target, normal])
        db.commit()

        result = process_pending_joom_overseas_orders(db, apply=False)

        assert result.candidate_count == 0
        assert db.get(Order, 1).biz_status == "待处理"
        assert db.scalar(select(OrderOperationLog.id)) is None


def test_legacy_shipping_script_never_marks_fbj_orders_shipped():
    session_factory = _session_factory()
    with session_factory() as db:
        target = _order(order_id=1, order_no="JOOM-FBJ-1", warehouse_type="fulfillment")
        normal = _order(order_id=2, order_no="JOOM-DEFAULT-1", warehouse_type="default")
        db.add_all([target, normal])
        db.commit()

        result = process_pending_joom_overseas_orders(db, apply=True)
        db.commit()

        assert result.candidate_count == 0
        target = db.get(Order, 1)
        assert target.biz_status == "待处理"
        assert target.local_status == "new"
        assert target.label_printed_at is None
        assert target.shipped_at is None
        assert target.marked_shipped_at is None
        assert db.get(Order, 2).biz_status == "待处理"

        logs = db.scalars(select(OrderOperationLog).where(OrderOperationLog.order_id == 1)).all()
        assert logs == []


def test_script_excludes_orders_matched_to_bsi_rule():
    session_factory = _session_factory()
    with session_factory() as db:
        bsi = _order(
            order_id=1,
            order_no="JOOM-BSI-1",
            warehouse_type="physical",
            warehouse_name="BSI-PL",
        )
        bsi_rule = LogisticsMatchRule(
            id=1,
            name="Joom BSI",
            platform="joom_logistics",
            priority=10,
            enabled=True,
            is_overseas_warehouse=True,
            logistics_channel="BSI海外仓 / DEMO-CARRIER-3",
            carrier_code="bsi_overseas",
        )
        db.add_all([bsi, bsi_rule])
        db.commit()

        result = process_pending_joom_overseas_orders(db, apply=True)

        assert result.candidate_count == 0
        assert db.get(Order, 1).biz_status == "待处理"
