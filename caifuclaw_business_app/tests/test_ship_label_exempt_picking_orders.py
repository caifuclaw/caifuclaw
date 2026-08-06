# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import date, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import LocalUser, Order, OrderItem, OrderOperationLog
from app.product_models import Product, PurchaseOrder, PurchaseOrderItem, PurchaseOrderLog, PurchaseOrderSource
from scripts.ship_label_exempt_picking_orders import process_label_exempt_picking_orders


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            Product.__table__,
            Order.__table__,
            OrderItem.__table__,
            OrderOperationLog.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderItem.__table__,
            PurchaseOrderSource.__table__,
            PurchaseOrderLog.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _seed_mixed_purchase(db):
    target = Order(
        id=1,
        tenant_id="default",
        platform="wildberries",
        account_id="A",
        shop_id="S",
        shop_name="WB DEMO SHOP CN",
        platform_order_id="DEMO-ORDER-0015",
        posting_number="DEMO-ORDER-0015",
        country_code="RU",
        country_name_cn="俄罗斯",
        biz_status="配货中",
        local_status="picking",
        raw_payload={},
        last_api_payload={},
    )
    normal = Order(
        id=2,
        tenant_id="default",
        platform="ozon",
        account_id="A",
        shop_id="S",
        shop_name="OZON",
        platform_order_id="DEMO-ORDER-0125",
        posting_number="DEMO-ORDER-0125",
        country_code="RU",
        country_name_cn="俄罗斯",
        biz_status="配货中",
        local_status="picking",
        raw_payload={},
        last_api_payload={},
    )
    db.add_all([target, normal])
    db.flush()
    target_item = OrderItem(id=10, order_id=target.id, sku="SKU-1", quantity=1, raw_payload={})
    normal_item = OrderItem(id=20, order_id=normal.id, sku="SKU-2", quantity=1, raw_payload={})
    purchase = PurchaseOrder(
        id=100,
        purchase_no="PO20260706-001",
        purchase_date=date(2026, 7, 6),
        source_count=2,
        item_count=1,
        total_required_qty=2,
        created_by="admin",
    )
    purchase_item = PurchaseOrderItem(
        id=1000,
        purchase_order_id=purchase.id,
        product_name="测试产品",
        required_qty=2,
        purchase_qty=2,
    )
    db.add_all([target_item, normal_item, purchase, purchase_item])
    db.flush()
    db.add_all(
        [
            PurchaseOrderSource(
                id=10001,
                purchase_order_id=purchase.id,
                purchase_order_item_id=purchase_item.id,
                order_id=target.id,
                order_item_id=target_item.id,
                product_name=purchase_item.product_name,
                quantity=1,
            ),
            PurchaseOrderSource(
                id=10002,
                purchase_order_id=purchase.id,
                purchase_order_item_id=purchase_item.id,
                order_id=normal.id,
                order_item_id=normal_item.id,
                product_name=purchase_item.product_name,
                quantity=1,
            ),
        ]
    )
    db.commit()


def test_label_exempt_picking_cleanup_dry_run_does_not_change_rows():
    session_factory = _session_factory()
    with session_factory() as db:
        _seed_mixed_purchase(db)

        result = process_label_exempt_picking_orders(db, apply=False)

        assert result.candidate_count == 1
        assert result.purchase_source_count == 1
        assert db.get(Order, 1).biz_status == "配货中"
        assert db.scalar(select(func.count(PurchaseOrderSource.id))) == 2


def test_label_exempt_picking_cleanup_ships_order_and_removes_purchase_source():
    session_factory = _session_factory()
    with session_factory() as db:
        _seed_mixed_purchase(db)

        result = process_label_exempt_picking_orders(db, apply=True)
        db.commit()

        assert result.candidate_count == 1
        assert result.removed_source_ids == [10001]
        target = db.get(Order, 1)
        assert target.biz_status == "已发货"
        assert target.local_status == "shipped"
        assert isinstance(target.shipped_at, datetime)
        assert db.get(Order, 2).biz_status == "配货中"

        sources = db.scalars(select(PurchaseOrderSource).order_by(PurchaseOrderSource.id)).all()
        assert [source.id for source in sources] == [10002]
        purchase_item = db.get(PurchaseOrderItem, 1000)
        assert purchase_item.required_qty == 1
        assert purchase_item.purchase_qty == 1
        purchase = db.get(PurchaseOrder, 100)
        assert purchase.source_count == 1
        assert purchase.item_count == 1
        assert purchase.total_required_qty == 1

        order_logs = db.scalars(select(OrderOperationLog).where(OrderOperationLog.order_id == 1)).all()
        assert len(order_logs) == 1
        assert order_logs[0].operation_type == "label_exempt_picking_cleanup"
        purchase_logs = db.scalars(select(PurchaseOrderLog).where(PurchaseOrderLog.purchase_order_id == 100)).all()
        assert len(purchase_logs) == 1
        assert purchase_logs[0].snapshot["removed_order_ids"] == [1]
