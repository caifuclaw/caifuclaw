from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import (
    ORDER_STATUS_PENDING,
    ORDER_STATUS_PICKING,
    ORDER_STATUS_SHIPPED,
    ORDER_STATUS_WAITING_PRINT,
    ORDER_STATUS_WAITING_PURCHASE,
    _query_orders,
    batch_update_order_risk_handling,
)
from app.models import LabelFile, Order, OrderItem, OrderOperationLog, OrderRiskHandling, OutboundScanRecord, Shipment
from app.schemas import OrderRiskHandlingRequest


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _order(order_id: int, status: str, deadline: datetime | None, *, shop: str = "shop-a") -> Order:
    return Order(
        id=order_id,
        tenant_id="default",
        platform="ozon",
        account_id=shop,
        shop_id=shop,
        shop_name=shop,
        platform_order_id=f"ORDER-{order_id}",
        platform_order_no=f"ORDER-{order_id}",
        posting_number=f"POST-{order_id}",
        biz_status=status,
        local_status="new",
        dispatch_deadline_at=deadline,
        payment_at=datetime(2026, 7, 1),
        raw_payload={},
        last_api_payload={},
        created_at=datetime(2026, 7, 1),
        updated_at=datetime(2026, 7, 1),
    )


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Order.__table__,
            OrderRiskHandling.__table__,
            OrderOperationLog.__table__,
            OrderItem.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OutboundScanRecord.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_order_risk_query_isolated_from_standard_status_filter():
    session_factory = _session_factory()
    now = datetime.utcnow()
    with session_factory() as db:
        db.add_all(
            [
                _order(1, ORDER_STATUS_PENDING, now - timedelta(hours=2)),
                _order(2, ORDER_STATUS_WAITING_PRINT, now + timedelta(hours=2)),
                _order(3, ORDER_STATUS_WAITING_PURCHASE, now + timedelta(hours=23)),
                _order(4, ORDER_STATUS_PICKING, now + timedelta(hours=25)),
                _order(5, ORDER_STATUS_SHIPPED, now - timedelta(hours=1)),
                _order(6, ORDER_STATUS_PENDING, None),
                _order(7, ORDER_STATUS_PICKING, now + timedelta(hours=1)),
                _order(8, ORDER_STATUS_PENDING, now - timedelta(hours=4), shop="shop-b"),
            ]
        )
        db.add(OrderRiskHandling(order_id=7, handled_at=now, handled_by="admin"))
        db.commit()

        standard = _query_orders(db, ORDER_STATUS_PENDING, None, None, None, None, None, page=1, page_size=50)
        unhandled = _query_orders(
            db, None, None, None, None, None, None, page=1, page_size=50, risk_filter="unhandled"
        )
        handled = _query_orders(
            db, None, None, None, None, None, None, page=1, page_size=50, risk_filter="handled"
        )
        shop_b = _query_orders(
            db, None, None, None, None, None, None, page=1, page_size=50, risk_filter="all", shop="shop-b"
        )
        scoped = _query_orders(
            db,
            None,
            None,
            None,
            None,
            None,
            None,
            page=1,
            page_size=50,
            risk_filter="all",
            risk_shop_keys=[("ozon", "shop-b")],
        )
        standard_scoped = _query_orders(
            db,
            ORDER_STATUS_PENDING,
            None,
            None,
            None,
            None,
            None,
            page=1,
            page_size=50,
            shop_keys=[("ozon", "shop-b")],
        )

    assert {item.id for item in standard.items} == {1, 6, 8}
    assert [item.id for item in unhandled.items] == [8, 1, 2, 3]
    assert unhandled.items[0].risk_bucket.startswith("overdue")
    assert unhandled.items[2].risk_bucket == "due_24"
    assert handled.total == 1
    assert handled.items[0].id == 7
    assert handled.items[0].risk_handled is True
    assert handled.items[0].risk_handled_by == "admin"
    assert [item.id for item in shop_b.items] == [8]
    assert [item.id for item in scoped.items] == [8]
    assert [item.id for item in standard_scoped.items] == [8]


def test_order_risk_query_compares_deadlines_in_utc():
    session_factory = _session_factory()
    now = datetime.utcnow()
    with session_factory() as db:
        db.add(_order(11, ORDER_STATUS_PENDING, now + timedelta(hours=31)))
        db.commit()

        result = _query_orders(
            db, None, None, None, None, None, None, page=1, page_size=50, risk_filter="unhandled"
        )

    assert result.items == []


def test_risk_handling_uses_separate_state_and_writes_operation_log():
    session_factory = _session_factory()
    now = datetime.utcnow()
    original_updated_at = datetime(2026, 7, 1)
    with session_factory() as db:
        db.add(_order(21, ORDER_STATUS_PENDING, now + timedelta(hours=3)))
        db.commit()
        user = SimpleNamespace(username="admin", display_name="管理员")

        response = batch_update_order_risk_handling(
            OrderRiskHandlingRequest(order_ids=[21], handled=True, note="已安排优先打包"),
            user=user,
            db=db,
        )
        handling = db.scalar(select(OrderRiskHandling).where(OrderRiskHandling.order_id == 21))
        order = db.get(Order, 21)
        log = db.scalar(select(OrderOperationLog).where(OrderOperationLog.order_id == 21))

        assert response.updated == 1
        assert handling is not None
        assert handling.handled_by == "管理员"
        assert handling.note == "已安排优先打包"
        assert order.updated_at == original_updated_at
        assert log.operation_type == "risk_handled"

        batch_update_order_risk_handling(
            OrderRiskHandlingRequest(order_ids=[21], handled=False),
            user=user,
            db=db,
        )
        assert db.scalar(select(OrderRiskHandling).where(OrderRiskHandling.order_id == 21)) is None
