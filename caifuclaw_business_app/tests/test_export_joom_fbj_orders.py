from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Order, OrderFollowUpExportItem, OrderFollowUpExportJob, OrderItem, OrderOperationLog
from scripts.reconcile_joom_bsi_orders import reconcile_joom_bsi_orders
from scripts.export_joom_fbj_orders import reconcile_joom_fbj_orders


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Order.__table__,
            OrderItem.__table__,
            OrderFollowUpExportJob.__table__,
            OrderFollowUpExportItem.__table__,
            OrderOperationLog.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _fbj_order(order_id: int = 1) -> Order:
    return Order(
        id=order_id,
        tenant_id="default",
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        shop_id="JOOM-DEMO-001",
        shop_name="Joom Demo Shop",
        platform_order_id="FBJ-ORDER-1",
        platform_order_no="FBJ-ORDER-1",
        platform_status="fulfilledOnline",
        biz_status="待处理",
        local_status="shipment_created",
        fulfillment_type="FBJ",
        shipment_tracking_number="DEMO-TRACKING-0002",
        payment_at=datetime(2026, 7, 29, 1, 2, 3),
        shipping_deadline_at=datetime(2026, 7, 30, 1, 2, 3),
        error_message="面单同步失败",
        raw_payload={
            "fulfillmentType": "FBJ",
            "shippingOption": {"warehouseName": "Joom Logistics CN Warehouse", "warehouseType": "fulfillment"},
            "shippingAddress": {
                "name": "Jane Doe",
                "country": "PL",
                "state": "Mazowieckie",
                "city": "Warsaw",
                "streetAddress1": "Main Street 1",
                "zipCode": "00-001",
                "phoneNumber": "+48123456789",
                "email": "demo@example.invalid",
            },
        },
        last_api_payload={},
    )


def _bsi_order(order_id: int = 3) -> Order:
    return Order(
        id=order_id,
        tenant_id="default",
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        shop_id="JOOM-DEMO-001",
        shop_name="Joom Demo Shop",
        platform_order_id="BSI-ORDER-1",
        platform_order_no="BSI-ORDER-1",
        platform_status="approved",
        biz_status="待处理",
        local_status="new",
        fulfillment_type="PHYSICAL",
        is_overseas_warehouse=True,
        bsi_order_no="BSI-DRAFT-1",
        payment_at=datetime(2026, 7, 29, 1, 2, 3),
        shipping_deadline_at=datetime(2026, 7, 30, 1, 2, 3),
        error_message="previous error",
        raw_payload={
            "fulfillmentType": "PHYSICAL",
            "shippingOption": {"warehouseName": "BSI-PL", "warehouseType": "physical"},
        },
        last_api_payload={},
    )


def test_reconcile_fbj_orders_marks_only_confirmed_follow_up_rows_shipped():
    session_factory = _session_factory()
    with session_factory() as db:
        fbj = _fbj_order()
        normal = _fbj_order(order_id=2)
        normal.platform = "ozon"
        normal.platform_order_id = "DEMO-ORDER-0009"
        normal.platform_order_no = "DEMO-ORDER-0009"
        db.add_all(
            [
                fbj,
                normal,
                OrderItem(id=101, order_id=1, sku="SKU-1", platform_product_name="Product 1", quantity=2),
                OrderFollowUpExportJob(id=11, scheduled_task_run_id=1, status="success"),
                OrderFollowUpExportItem(
                    id=201,
                    job_id=11,
                    order_id=1,
                    order_item_id=101,
                    action="append",
                    status="success",
                    worksheet_row=100,
                    snapshot_json={},
                ),
            ]
        )
        db.commit()

        result = reconcile_joom_fbj_orders(db, apply=True)
        db.commit()

        assert result.candidate_count == 1
        assert result.ready_to_ship_count == 1
        assert result.shipped_order_ids == [1]
        assert fbj.biz_status == "已发货"
        assert fbj.local_status == "shipped"
        assert fbj.error_message == ""
        assert fbj.label_printed_at is None
        assert fbj.shipped_at is not None
        assert fbj.marked_shipped_at is not None
        assert normal.biz_status == "待处理"
        assert db.query(OrderOperationLog).filter_by(operation_type="fbj_follow_up_export_shipped").count() == 1


def test_reconcile_fbj_orders_dry_run_does_not_change_unregistered_order():
    session_factory = _session_factory()
    with session_factory() as db:
        order = _fbj_order()
        order.biz_status = "待处理"
        db.add(order)
        db.commit()

        result = reconcile_joom_fbj_orders(db, apply=False)

        assert result.candidate_count == 1
        assert result.ready_to_ship_count == 0
        assert result.shipped_order_ids == []
        assert order.biz_status == "待处理"


def test_reconcile_bsi_orders_marks_only_registered_drafts_shipped():
    session_factory = _session_factory()
    with session_factory() as db:
        bsi = _bsi_order()
        unregistered = _bsi_order(order_id=4)
        unregistered.platform_order_id = "BSI-ORDER-2"
        unregistered.platform_order_no = "BSI-ORDER-2"
        unregistered.bsi_order_no = "BSI-DRAFT-2"
        db.add_all(
            [
                bsi,
                unregistered,
                OrderItem(id=103, order_id=3, sku="SKU-BSI-1", platform_product_name="Product 1", quantity=1),
                OrderItem(id=104, order_id=4, sku="SKU-BSI-2", platform_product_name="Product 2", quantity=1),
                OrderFollowUpExportJob(id=12, scheduled_task_run_id=2, status="success"),
                OrderFollowUpExportItem(
                    id=203,
                    job_id=12,
                    order_id=3,
                    order_item_id=103,
                    action="append",
                    status="success",
                    worksheet_row=101,
                    snapshot_json={},
                ),
            ]
        )
        db.commit()

        result = reconcile_joom_bsi_orders(db, apply=True)
        db.commit()

        assert result.candidate_count == 2
        assert result.ready_to_ship_count == 1
        assert result.shipped_order_ids == [3]
        assert bsi.biz_status == "已发货"
        assert bsi.local_status == "shipped"
        assert bsi.error_message == ""
        assert bsi.label_printed_at is None
        assert bsi.shipped_at is not None
        assert bsi.marked_shipped_at is not None
        assert unregistered.biz_status == "待处理"
        assert db.query(OrderOperationLog).filter_by(operation_type="bsi_follow_up_export_shipped").count() == 1
