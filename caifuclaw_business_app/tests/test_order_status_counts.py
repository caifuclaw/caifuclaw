import base64
import io
from datetime import date, datetime
from types import SimpleNamespace

import pytest
import app.chinese_label_pdf as label_pdf
import app.main as main_module
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from reportlab.pdfbase import pdfmetrics
from app.chinese_label_pdf import (
    FONT_NAME,
    FONT_SIZE_PT,
    LABEL_HEIGHT,
    LINE_HEIGHT_PT,
    PROJECT_FONT_NAME,
    PROJECT_FONT_PATH,
    ChineseLabelRow,
    _label_block_start_y,
    generate_chinese_label_pdf,
    register_chinese_label_font,
    resolve_chinese_label_deadline,
)
from app.main import (
    ORDER_STATUS_AWAITING_PICKUP,
    ORDER_STATUS_DELIVERED,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_PICKING,
    ORDER_STATUS_SHIPPED,
    ORDER_STATUS_VOIDED,
    ORDER_STATUS_WAITING_PRINT,
    ORDER_STATUS_WAITING_PURCHASE,
    _query_order_summary,
    _query_orders,
    _normalize_batch_order_numbers,
    _order_dto,
    _order_item_detail_rows,
    _summary_warning,
    batch_confirm_printed,
    batch_print_chinese_label,
    batch_to_picking,
    batch_to_printing,
    delete_purchase_order,
    order_status_counts,
)
from app.database import Base
from app.models import (
    LabelFile,
    LocalUser,
    LogisticsMatchRule,
    Order,
    OrderItem,
    OrderOperationLog,
    OutboundScanRecord,
    PlatformAccount,
    PlatformPrintSetting,
    Shipment,
    ShippingDeadlineSetting,
)
from app.product_models import (
    Product,
    ProductShopMapping,
    PurchaseOrder,
    PurchaseOrderEditLock,
    PurchaseOrderItem,
    PurchaseOrderLog,
    PurchaseOrderSource,
)
from app.schemas import OrderBatchRequest


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def test_legacy_fbj_export_statuses_fall_back_to_pending():
    assert main_module._status_key_for_label("FBJ待导出") == "pending"
    assert main_module._status_key_for_label("FBJ已导出") == "pending"
    assert main_module._should_show_remaining_shipping("FBJ待导出")
    assert main_module._should_show_remaining_shipping("FBJ已导出")


def test_startup_normalizes_legacy_fbj_export_orders(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Order.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as db:
        db.add_all(
            [
                Order(
                    id=801,
                    tenant_id="default",
                    platform="joom_logistics",
                    account_id="JOOM-DEMO-001",
                    shop_id="JOOM-DEMO-001",
                    shop_name="Joom Demo Shop",
                    platform_order_id="DEMO-ORDER-0046",
                    platform_order_no="DEMO-ORDER-0046",
                    biz_status="FBJ待导出",
                    local_status="fbj_export_pending",
                    error_message="old export state",
                ),
                Order(
                    id=802,
                    tenant_id="default",
                    platform="joom_logistics",
                    account_id="JOOM-DEMO-001",
                    shop_id="JOOM-DEMO-001",
                    shop_name="Joom Demo Shop",
                    platform_order_id="DEMO-ORDER-0047",
                    platform_order_no="DEMO-ORDER-0047",
                    biz_status="FBJ已导出",
                    local_status="fbj_export_pending",
                ),
            ]
        )
        db.commit()

    monkeypatch.setattr(main_module, "SessionLocal", session_factory)
    main_module._normalize_legacy_fbj_export_statuses()

    with session_factory() as db:
        for order_id in (801, 802):
            row = db.get(Order, order_id)
            assert row.biz_status == ORDER_STATUS_PENDING
            assert row.local_status == "new"
            assert row.error_message == ""


class _ExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows, platform_status_rows=None):
        self.rows = rows
        self.platform_status_rows = platform_status_rows or []
        self.statements = []

    def execute(self, stmt):
        self.statements.append(stmt)
        if len(self.statements) == 2:
            return _ExecuteResult(self.platform_status_rows)
        return _ExecuteResult(self.rows)


class _FakeBatchSession:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    def scalars(self, stmt):
        return _ExecuteResult(self.rows)

    def scalar(self, stmt):
        return None

    def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def _default_no_logistics_rules(monkeypatch):
    monkeypatch.setattr(main_module, "load_enabled_logistics_rules", lambda db: [])


def test_order_status_counts_uses_all_current_statuses():
    db = _FakeSession(
        [
            (ORDER_STATUS_PENDING, "new", False, False, 2),
            (ORDER_STATUS_WAITING_PRINT, "new", False, False, 6),
            (ORDER_STATUS_WAITING_PURCHASE, "label_saved", True, False, 7),
            (ORDER_STATUS_WAITING_PURCHASE, "label_saved", False, False, 9),
            (ORDER_STATUS_WAITING_PURCHASE, "label_saved", True, True, 8),
            (ORDER_STATUS_PICKING, "picking", False, False, 3),
            (None, "label_saved", False, False, 4),
            (ORDER_STATUS_SHIPPED, "shipped", False, False, 5),
        ],
        [
            ("awaiting_packaging", 3),
            ("awaiting_packaging", 2),
            ("delivered", 4),
            ("", 1),
            (None, 1),
            ("None", 1),
        ],
    )

    counts = order_status_counts(db=db)

    assert counts["pending"] == 2
    assert counts["waiting_print"] == 6
    assert counts["waiting_purchase"] == 7
    assert counts["picking"] == 7
    assert counts["shipped"] == 5
    assert counts["platform_status_counts"] == {
        "awaiting_packaging": 5,
        "delivered": 4,
        "未记录": 3,
    }
    assert len(db.statements) == 2


def test_cancelled_platform_status_counts_as_voided_even_if_biz_status_is_pending():
    db = _FakeSession(
        [
            (ORDER_STATUS_PENDING, "new", "awaiting_packaging", 2),
            (ORDER_STATUS_PENDING, "new", "cancelled", 1),
            (ORDER_STATUS_WAITING_PRINT, "new", "cancelled_by_seller", 3),
        ]
    )

    counts = order_status_counts(db=db)

    assert counts["pending"] == 2
    assert counts["waiting_print"] == 0
    assert counts["voided"] == 4


def test_batch_to_printing_requires_tracking_unless_confirmed(monkeypatch):
    row = SimpleNamespace(
        id=1,
        platform_order_id="ORDER-1",
        platform_order_no="ORDER-1",
        posting_number="",
        shipment_tracking_number="",
        raw_payload={},
        biz_status=ORDER_STATUS_PENDING,
        local_status="new",
        updated_at=None,
    )
    db = _FakeBatchSession([row])
    user = SimpleNamespace(username="admin", display_name="admin")
    monkeypatch.setattr(main_module, "load_enabled_logistics_rules", lambda db: [])
    payload = OrderBatchRequest(order_ids=[1])
    monkeypatch.setattr(main_module, "add_order_operation_logs", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc:
        batch_to_printing(payload, user=user, db=db)

    assert exc.value.status_code == 400
    assert "没有货运单号" in exc.value.detail

    confirmed_payload = OrderBatchRequest(order_ids=[1], allow_missing_tracking=True)
    response = batch_to_printing(confirmed_payload, user=user, db=db)

    assert response.updated == 1
    assert row.biz_status == ORDER_STATUS_WAITING_PRINT
    assert db.commits == 1


def test_batch_to_printing_skips_overseas_warehouse_to_shipped(monkeypatch):
    row = SimpleNamespace(
        id=2,
        platform="wildberries",
        platform_order_id="WB-OVERSEAS-1",
        platform_order_no="WB-OVERSEAS-1",
        posting_number="",
        shipment_tracking_number="",
        raw_payload={},
        fulfillment_type="DBS",
        is_overseas_warehouse=True,
        biz_status=ORDER_STATUS_PENDING,
        local_status="new",
        label_printed_at=None,
        updated_at=None,
    )
    db = _FakeBatchSession([row])
    user = SimpleNamespace(username="admin", display_name="admin")
    monkeypatch.setattr(main_module, "load_enabled_logistics_rules", lambda db: [])
    monkeypatch.setattr(main_module, "add_order_operation_logs", lambda *args, **kwargs: None)

    response = batch_to_printing(OrderBatchRequest(order_ids=[2]), user=user, db=db)

    assert response.updated == 1
    assert row.biz_status == ORDER_STATUS_SHIPPED
    assert row.local_status == "shipped"
    assert row.label_printed_at is not None
    assert row.shipped_at is not None
    assert row.marked_shipped_at is not None
    assert "已发货" in response.message
    assert db.commits == 1


def test_batch_to_printing_rejects_joom_overseas_registration_only_order():
    row = SimpleNamespace(
        id=22,
        platform="joom_logistics",
        platform_order_id="JOOM-FBJ-1",
        platform_order_no="JOOM-FBJ-1",
        posting_number="",
        shipment_tracking_number="",
        raw_payload={"shippingOption": {"warehouseType": "physical"}},
        fulfillment_type="PHYSICAL",
        is_overseas_warehouse=True,
        biz_status=ORDER_STATUS_PENDING,
        local_status="new",
        label_printed_at=None,
        updated_at=None,
    )
    db = _FakeBatchSession([row])
    user = SimpleNamespace(username="admin", display_name="admin")

    with pytest.raises(HTTPException) as exc:
        batch_to_printing(OrderBatchRequest(order_ids=[22]), user=user, db=db)

    assert exc.value.status_code == 409
    assert "仅登记" in exc.value.detail
    assert row.biz_status == ORDER_STATUS_PENDING
    assert db.commits == 0


def _fbj_registration_only_row(*, order_id: int, status: str):
    return SimpleNamespace(
        id=order_id,
        platform="joom_logistics",
        account_id="JOOM-DEMO-001",
        shop_id="JOOM-DEMO-001",
        shop_name="Joom Demo Shop",
        platform_order_id=f"FBJ-{order_id}",
        platform_order_no=f"FBJ-{order_id}",
        posting_number="",
        shipment_tracking_number="",
        raw_payload={
            "fulfillmentType": "FBJ",
            "shippingOption": {"warehouseName": "Joom Logistics CN Warehouse", "warehouseType": "fulfillment"},
        },
        fulfillment_type="FBJ",
        is_overseas_warehouse=False,
        biz_status=status,
        local_status="fbj_follow_up_pending",
        label_printed_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        updated_at=None,
    )


def test_batch_to_printing_rejects_fbj_registration_only_order():
    row = _fbj_registration_only_row(order_id=23, status=ORDER_STATUS_PENDING)
    db = _FakeBatchSession([row])
    user = SimpleNamespace(username="admin", display_name="admin")

    with pytest.raises(HTTPException) as exc:
        batch_to_printing(OrderBatchRequest(order_ids=[23]), user=user, db=db)

    assert exc.value.status_code == 409
    assert "FBJ" in exc.value.detail
    assert row.biz_status == ORDER_STATUS_PENDING
    assert db.commits == 0


def test_batch_to_picking_rejects_fbj_registration_only_order():
    row = _fbj_registration_only_row(order_id=24, status=ORDER_STATUS_WAITING_PURCHASE)
    db = _FakeBatchSession([row])
    user = SimpleNamespace(username="admin", display_name="admin")

    with pytest.raises(HTTPException) as exc:
        batch_to_picking(OrderBatchRequest(order_ids=[24]), user=user, db=db)

    assert exc.value.status_code == 409
    assert "FBJ" in exc.value.detail
    assert row.biz_status == ORDER_STATUS_WAITING_PURCHASE
    assert db.commits == 0


def test_batch_to_printing_marks_logistics_rule_unmatched_as_shipped(monkeypatch):
    row = SimpleNamespace(
        id=3,
        platform="wildberries",
        account_id="WB-1",
        shop_id="OTHER",
        shop_name="OTHER",
        platform_order_id="WB-UNMATCHED-1",
        platform_order_no="WB-UNMATCHED-1",
        posting_number="",
        shipment_tracking_number="",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        logistics_match_status="unmatched",
        logistics_channel="",
        biz_status=ORDER_STATUS_PENDING,
        local_status="new",
        shipped_at=None,
        marked_shipped_at=None,
        updated_at=None,
    )
    rule = LogisticsMatchRule(
        id=1,
        name="WB DEMO SHOP",
        platform="wildberries",
        priority=1,
        enabled=True,
        shop_names=["WB DEMO SHOP CN"],
        country_codes=["CN"],
        logistics_channel="WB China",
    )
    db = _FakeBatchSession([row])
    user = SimpleNamespace(username="admin", display_name="admin")
    monkeypatch.setattr(main_module, "load_enabled_logistics_rules", lambda db: [rule])
    monkeypatch.setattr(main_module, "add_order_operation_logs", lambda *args, **kwargs: None)

    response = batch_to_printing(OrderBatchRequest(order_ids=[3]), user=user, db=db)

    assert response.updated == 1
    assert row.biz_status == ORDER_STATUS_SHIPPED
    assert row.local_status == "shipped"
    assert row.shipped_at is not None
    assert row.marked_shipped_at is not None
    assert "已发货" in response.message
    assert db.commits == 1


def test_batch_to_picking_marks_label_exempt_order_as_shipped_without_purchase(monkeypatch):
    row = SimpleNamespace(
        id=4,
        platform="wildberries",
        account_id="WB-1",
        shop_id="WB-1",
        shop_name="WB DEMO SHOP CN",
        platform_order_id="WB-RU-1",
        platform_order_no="WB-RU-1",
        posting_number="",
        shipment_tracking_number="",
        raw_payload={},
        fulfillment_type="FBS",
        is_overseas_warehouse=False,
        country_code="RU",
        country_name_cn="俄罗斯",
        biz_status=ORDER_STATUS_WAITING_PURCHASE,
        local_status="label_saved",
        label_printed_at=None,
        shipped_at=None,
        marked_shipped_at=None,
        updated_at=None,
    )
    db = _FakeBatchSession([row])
    user = SimpleNamespace(username="admin", display_name="admin")
    monkeypatch.setattr(main_module, "add_order_operation_logs", lambda *args, **kwargs: None)

    def fail_purchase_generation(*args, **kwargs):
        raise AssertionError("label-exempt orders should not generate purchase orders")

    monkeypatch.setattr(main_module, "_generate_purchase_order_for_orders", fail_purchase_generation)

    response = batch_to_picking(OrderBatchRequest(order_ids=[4]), user=user, db=db)

    assert response.updated == 1
    assert response.purchase_order_id is None
    assert response.purchase_no is None
    assert row.biz_status == ORDER_STATUS_SHIPPED
    assert row.local_status == "shipped"
    assert row.label_printed_at is not None
    assert row.shipped_at is not None
    assert row.marked_shipped_at is not None
    assert "跳过采购" in response.message
    assert db.commits == 1


@pytest.mark.asyncio
async def test_batch_print_label_skips_allegro_without_wza_shipment_id(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            Order.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OrderOperationLog.__table__,
            PlatformPrintSetting.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    user = LocalUser(id=1, username="admin", password_hash="x", display_name="管理员", enabled=True)
    order_id = "93f5ae72-7012-11f1-b243-c11dfac6217f"

    async def fake_fetch_labels(db, rows, load_bytes=True):
        for row in rows:
            row.error_message = "Allegro 订单 shipment 面单接口不可用：HTTP 404 Feature unavailable"
        return {}, 0, 0, 0

    monkeypatch.setattr(main_module, "_ensure_labels_cached", fake_fetch_labels)

    with session_factory() as db:
        order = Order(
            id=33,
            tenant_id="default",
            platform="allegro",
            account_id="allegro-demo",
            shop_id="allegro-demo",
            shop_name="Demo Shop",
            platform_order_id=order_id,
            platform_order_no=order_id,
            posting_number=order_id,
            platform_status="SENT",
            biz_status=ORDER_STATUS_SHIPPED,
            local_status="new",
            shipment_tracking_number="DEMO-TRACKING-0006",
            fulfillment_type="FBS",
            is_overseas_warehouse=False,
            error_message="面单同步失败：old",
            raw_payload={
                "id": order_id,
                "shipments": [
                    {
                        "id": "DEMO-SHIPMENT-001",
                        "waybill": "DEMO-WAYBILL-001",
                        "carrierId": "WANB_EXPRESS",
                    }
                ],
                "shipment_tracking_number": "DEMO-TRACKING-0006",
            },
        )
        db.add_all([user, order])
        db.add(
            Shipment(
                order_id=33,
                platform_shipment_id="DEMO-ORDER-0048",
                tracking_number="DEMO-TRACKING-0006",
                carrier="WANB_EXPRESS",
            )
        )
        db.commit()

        response = await main_module.batch_print_label(OrderBatchRequest(order_ids=[33]), user=user, db=db)
        refreshed = db.get(Order, 33)

    assert response["printed"] == 0
    assert response["skipped"] == 1
    assert response["failed"] == 0
    assert response["pdf_base64"] == ""
    assert refreshed.label_printed_at is not None
    assert refreshed.biz_status == ORDER_STATUS_SHIPPED
    assert refreshed.local_status == "shipped"
    assert refreshed.shipped_at is not None
    assert refreshed.marked_shipped_at is not None
    assert refreshed.error_message == ""


def test_batch_confirm_printed_moves_to_waiting_purchase_without_purchase_generation(monkeypatch):
    row = SimpleNamespace(
        id=3,
        platform_order_id="ORDER-3",
        platform_order_no="ORDER-3",
        posting_number="",
        biz_status=ORDER_STATUS_WAITING_PRINT,
        label_printed_at=None,
        updated_at=None,
    )
    db = _FakeBatchSession([row])
    user = SimpleNamespace(username="admin", display_name="admin")
    monkeypatch.setattr(main_module, "add_order_operation_logs", lambda *args, **kwargs: None)

    def fail_purchase_generation(*args, **kwargs):
        raise AssertionError("confirm printed should not generate purchase orders")

    monkeypatch.setattr(main_module, "_generate_purchase_order_for_orders", fail_purchase_generation)

    response = batch_confirm_printed(OrderBatchRequest(order_ids=[3]), user=user, db=db)

    assert response.updated == 1
    assert response.purchase_order_id is None
    assert response.purchase_no is None
    assert row.biz_status == ORDER_STATUS_WAITING_PURCHASE
    assert row.label_printed_at is not None
    assert db.commits == 1


def test_batch_to_picking_reuses_existing_purchase_order_for_repeated_request():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OutboundScanRecord.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderItem.__table__,
            PurchaseOrderSource.__table__,
            PurchaseOrderLog.__table__,
            OrderOperationLog.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    user = LocalUser(id=1, username="admin", password_hash="x", display_name="管理员", enabled=True)

    with session_factory() as db:
        account = PlatformAccount(id=101, platform="ozon", account_id="100001", display_name="Ozon")
        product = Product(id=201, product_code="DEMO-PRODUCT-0002", internal_name="产品A")
        order = Order(
            id=60,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id="DEMO-ORDER-0049",
            platform_order_no="DEMO-ORDER-0049",
            posting_number="DEMO-ORDER-0050",
            biz_status=ORDER_STATUS_WAITING_PURCHASE,
            local_status="label_saved",
            raw_payload={},
            last_api_payload={},
        )
        order_item = OrderItem(id=601, order_id=order.id, sku="DEMO-SKU-0006", quantity=1, raw_payload={})
        mapping = ProductShopMapping(product_id=product.id, shop_id=account.id, shop_sku="DEMO-SKU-0006")
        db.add_all([user, account, product, order, order_item, mapping])
        db.commit()

        first = batch_to_picking(OrderBatchRequest(order_ids=[order.id]), user=user, db=db)
        db.expire_all()
        second = batch_to_picking(OrderBatchRequest(order_ids=[order.id]), user=user, db=db)

        assert first.purchase_order_id == second.purchase_order_id
        assert first.purchase_no == second.purchase_no
        assert second.updated == 1
        assert "已在采购单" in second.message
        assert db.get(Order, order.id).biz_status == ORDER_STATUS_PICKING
        assert db.scalar(select(func.count(PurchaseOrder.id))) == 1
        assert db.scalar(select(func.count(PurchaseOrderSource.id))) == 1


def test_batch_to_picking_recovers_when_parallel_request_created_purchase(monkeypatch):
    row = SimpleNamespace(
        id=70,
        platform_order_id="DEMO-ORDER-0051",
        platform_order_no="DEMO-ORDER-0051",
        posting_number="DEMO-ORDER-0052",
        platform_status="",
        biz_status=ORDER_STATUS_WAITING_PURCHASE,
        local_status="label_saved",
    )
    purchase = SimpleNamespace(id=77, purchase_no="PO20260624-077")

    class ParallelSession:
        def __init__(self):
            self.scalar_calls = 0
            self.rollback_count = 0

        def scalars(self, _stmt):
            self.scalar_calls += 1
            if self.scalar_calls == 4:
                return _ExecuteResult([701])
            return _ExecuteResult([row])

        def execute(self, _stmt):
            return _ExecuteResult([(701, purchase.id)])

        def get(self, _model, item_id):
            return purchase if item_id == purchase.id else None

        def rollback(self):
            self.rollback_count += 1

    db = ParallelSession()
    user = SimpleNamespace(username="admin", display_name="admin")

    def raise_parallel_unique_conflict(*_args, **_kwargs):
        row.biz_status = ORDER_STATUS_PICKING
        row.local_status = "picking"
        raise main_module.IntegrityError("insert purchase source", {}, Exception("duplicate order_item_id"))

    monkeypatch.setattr(main_module, "_generate_purchase_order_for_orders", raise_parallel_unique_conflict)

    response = batch_to_picking(OrderBatchRequest(order_ids=[row.id]), user=user, db=db)

    assert response.purchase_order_id == purchase.id
    assert response.purchase_no == purchase.purchase_no
    assert "已在采购单" in response.message
    assert db.rollback_count == 1


def test_order_summary_resolves_product_names_with_batch_lookup():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OutboundScanRecord.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderSource.__table__,
            ShippingDeadlineSetting.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        account = PlatformAccount(id=101, platform="ozon", account_id="100001", display_name="Ozon")
        product = Product(id=201, product_code="DEMO-PRODUCT-0002", internal_name="产品A")
        order = Order(
            id=71,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id="DEMO-ORDER-0053",
            platform_order_no="DEMO-ORDER-0053",
            posting_number="DEMO-ORDER-0054",
            biz_status=ORDER_STATUS_WAITING_PURCHASE,
            local_status="label_saved",
            payment_at=datetime(2026, 6, 24, 8, 0, 0),
            raw_payload={},
            last_api_payload={},
        )
        item = OrderItem(id=711, order_id=order.id, sku="DEMO-SKU-0006", quantity=1, raw_payload={})
        mapping = ProductShopMapping(product_id=product.id, shop_id=account.id, shop_sku="DEMO-SKU-0006")
        db.add_all([account, product, order, item, mapping])
        db.commit()

        response = main_module._query_order_summary(
            db,
            status_filter=None,
            platform=None,
            transaction_id=None,
            tracking_number=None,
            number=None,
            payment_time_range=None,
            page=1,
            page_size=100,
            lazy=True,
        )
        scoped_response = main_module._query_order_summary(
            db,
            status_filter=None,
            platform=None,
            transaction_id=None,
            tracking_number=None,
            number=None,
            payment_time_range=None,
            page=1,
            page_size=100,
            lazy=True,
            shop_keys=[("ozon", "100001")],
        )
        excluded_response = main_module._query_order_summary(
            db,
            status_filter=None,
            platform=None,
            transaction_id=None,
            tracking_number=None,
            number=None,
            payment_time_range=None,
            page=1,
            page_size=100,
            lazy=True,
            shop_keys=[("ozon", "397007")],
        )

        assert response.items
        assert response.items[0].product_name == "产品A"
        assert response.items[0].sku == "DEMO-SKU-0006"
        assert [row.order_id for row in scoped_response.items] == [71]
        assert excluded_response.items == []


def test_order_detail_item_rows_resolve_products_without_wide_mapping_join():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        account = PlatformAccount(id=101, platform="ozon", account_id="100001", display_name="Ozon")
        exact_product = Product(id=201, product_code="DEMO-PRODUCT-0002", internal_name="精确产品", cost=12.5, weight=0.25)
        fallback_product = Product(id=202, product_code="DEMO-PRODUCT-0004", internal_name="忽略大小写产品", cost=8, weight=0.1)
        newer_product = Product(id=203, product_code="DEMO-PRODUCT-0005", internal_name="最新映射产品", cost=9, weight=0.2)
        order = Order(
            id=81,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id="DEMO-ORDER-0055",
            platform_order_no="DEMO-ORDER-0055",
            posting_number="DEMO-ORDER-0056",
            biz_status=ORDER_STATUS_PENDING,
            local_status="new",
            raw_payload={},
            last_api_payload={},
        )
        db.add_all([account, exact_product, fallback_product, newer_product, order])
        db.flush()
        db.add_all(
            [
                OrderItem(id=811, order_id=order.id, sku="DEMO-SKU-0006", quantity=2, unit_price="3.50", raw_payload={}),
                OrderItem(id=812, order_id=order.id, sku="DEMO-SKU-0007", quantity=1, unit_price="4.00", raw_payload={}),
                ProductShopMapping(
                    id=901,
                    product_id=exact_product.id,
                    shop_id=account.id,
                    shop_sku="DEMO-SKU-0006",
                    updated_at=datetime(2026, 6, 1),
                ),
                ProductShopMapping(
                    id=902,
                    product_id=fallback_product.id,
                    shop_id=account.id,
                    shop_sku="DEMO-SKU-UNUSED",
                    updated_at=datetime(2026, 6, 1),
                ),
                ProductShopMapping(
                    id=903,
                    product_id=newer_product.id,
                    shop_id=account.id,
                    shop_sku="DEMO-SKU-0007",
                    updated_at=datetime(2026, 6, 2),
                ),
            ]
        )
        db.commit()

        rows = _order_item_detail_rows(db, order)

    assert [row.product_code for row in rows] == ["DEMO-PRODUCT-0002", "DEMO-PRODUCT-0005"]
    assert [row.product_name for row in rows] == ["精确产品", "最新映射产品"]
    assert rows[0].quantity == 2
    assert rows[0].product_cost == 12.5
    assert rows[0].product_weight == 0.25


def test_generate_chinese_label_pdf_keeps_long_product_name_printable():
    longest_name = "演示商品-超长产品名称-测试换行与截断行为 0000000000000"

    pdf_bytes = generate_chinese_label_pdf(
        [
            ChineseLabelRow(
                tracking_number="DEMO-TRACKING-0011",
                deadline=datetime(2026, 6, 6, 12, 30, 0),
                product_name=longest_name,
            )
        ]
    )

    reader = PdfReader(io.BytesIO(pdf_bytes))
    page = reader.pages[0]
    text = page.extract_text()

    assert len(reader.pages) == 1
    assert FONT_SIZE_PT == 10.5
    assert round(float(page.mediabox.width)) == 283
    assert round(float(page.mediabox.height)) == 57
    assert "DEMO-TRACK\nING-0011" in text
    assert "2026-06-06" in text
    assert "".join(text.split()).find("".join(longest_name.split())) >= 0


@pytest.mark.parametrize(
    ("payment_at", "platform_created_at", "imported_at", "expected"),
    [
        (datetime(2026, 6, 1, 18, 30), datetime(2026, 5, 30), datetime(2026, 5, 31), date(2026, 6, 5)),
        (None, datetime(2026, 6, 2, 9, 0), datetime(2026, 6, 1), date(2026, 6, 5)),
        (None, None, datetime(2026, 6, 3, 23, 59), date(2026, 6, 7)),
    ],
)
def test_resolve_chinese_label_deadline_uses_mercado_date_priority(
    payment_at,
    platform_created_at,
    imported_at,
    expected,
):
    assert resolve_chinese_label_deadline(
        platform="mercadolibre",
        payment_at=payment_at,
        platform_created_at=platform_created_at,
        imported_at=imported_at,
        fallback=date(2026, 6, 30),
    ) == expected


def test_resolve_chinese_label_deadline_keeps_other_platform_fallback():
    fallback = datetime(2026, 6, 30, 8, 0)

    assert resolve_chinese_label_deadline(
        platform="ozon",
        payment_at=datetime(2026, 6, 1),
        platform_created_at=datetime(2026, 5, 30),
        imported_at=datetime(2026, 5, 31),
        fallback=fallback,
    ) is fallback


def test_chinese_label_shrinks_extreme_mixed_product_name_to_fit():
    product_name = (
        "拼装模型-万代-30MM系列-装甲核心6-Orbiter-CC2000 #5067438 / "
        "拼装模型-万代-30MM系列-装甲核心6-钢铁迷雾-Steel Haze-5067169"
    )
    product_column_x = (
        label_pdf.HORIZONTAL_PADDING
        + label_pdf.TRACKING_COLUMN_WIDTH
        + label_pdf.COLUMN_GAP
        + label_pdf.DEADLINE_COLUMN_WIDTH
        + label_pdf.COLUMN_GAP
    )
    product_column_width = label_pdf.LABEL_WIDTH - label_pdf.HORIZONTAL_PADDING - product_column_x

    block = label_pdf._product_text_block(product_name, product_column_width)
    pdf_bytes = generate_chinese_label_pdf(
        [
            ChineseLabelRow(
                tracking_number="DEMO-TRACKING-0012",
                deadline=date(2026, 6, 7),
                product_name=product_name,
            )
        ]
    )
    text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()

    assert block.font_size < FONT_SIZE_PT
    assert label_pdf._text_block_height(len(block.lines), block.font_size, block.line_height) <= LABEL_HEIGHT
    assert "".join(text.split()).find("".join(product_name.split())) >= 0


def test_chinese_label_truncates_unbounded_product_name_inside_minimum_size():
    product_name = (
        "极端中文标签中文名称" * 12
        + "-中间仍然很长很长很长很长很长很长很长"
        + "-尾部型号-ABC1234567890"
    )
    product_column_x = (
        label_pdf.HORIZONTAL_PADDING
        + label_pdf.TRACKING_COLUMN_WIDTH
        + label_pdf.COLUMN_GAP
        + label_pdf.DEADLINE_COLUMN_WIDTH
        + label_pdf.COLUMN_GAP
    )
    product_column_width = label_pdf.LABEL_WIDTH - label_pdf.HORIZONTAL_PADDING - product_column_x

    block = label_pdf._product_text_block(product_name, product_column_width)

    assert block.font_size == label_pdf.MIN_PRODUCT_FONT_SIZE_PT
    assert block.lines[-1].startswith(label_pdf.TRUNCATION_MARKER)
    assert block.lines[-1].endswith("ABC1234567890")
    assert label_pdf._text_block_height(len(block.lines), block.font_size, block.line_height) <= LABEL_HEIGHT


def test_chinese_label_uses_embedded_project_medium_font():
    assert PROJECT_FONT_PATH.exists()
    assert register_chinese_label_font() == PROJECT_FONT_NAME

    pdf_bytes = generate_chinese_label_pdf(
        [
            ChineseLabelRow(
                tracking_number="DEMO-TRACKING-0013",
                deadline=date(2026, 6, 7),
                product_name="拼装模型-万代-30 M M 系列-装甲核心6-#1黄昏NightFall-5067168",
            )
        ]
    )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    fonts = reader.pages[0].get("/Resources").get("/Font") or {}
    base_fonts = [str(ref.get_object().get("/BaseFont")) for ref in fonts.values()]

    assert any("NotoSansSC-Medium" in base_font for base_font in base_fonts)


def test_chinese_label_text_block_is_vertically_centered():
    register_chinese_label_font()
    line_count = 3
    start_y = _label_block_start_y(line_count)
    ascent = pdfmetrics.getAscent(FONT_NAME, FONT_SIZE_PT)
    descent = pdfmetrics.getDescent(FONT_NAME, FONT_SIZE_PT)

    top_blank = LABEL_HEIGHT - (start_y + ascent)
    bottom_blank = start_y - ((line_count - 1) * LINE_HEIGHT_PT) + descent

    assert abs(top_blank - bottom_blank) < 0.01


def test_batch_print_chinese_label_generates_one_page_per_order_with_product_mapping():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    user = LocalUser(id=1, username="admin", password_hash="x", display_name="管理员", enabled=True)
    longest_name = "演示商品-超长产品名称-测试换行与截断行为 0000000000000"

    with session_factory() as db:
        account = PlatformAccount(id=101, platform="ozon", account_id="100001", display_name="Ozon")
        order = Order(
            id=30,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id="DEMO-ORDER-0057",
            platform_order_no="DEMO-ORDER-0057",
            posting_number="DEMO-ORDER-0058",
            biz_status=ORDER_STATUS_PICKING,
            local_status="picking",
            shipment_tracking_number="DEMO-TRACKING-0011",
            shipping_deadline_at=datetime(2026, 6, 6, 8, 0, 0),
            raw_payload={},
            last_api_payload={},
        )
        product = Product(id=201, product_code="DEMO-PRODUCT-0002", internal_name=longest_name)
        db.add_all([user, account, order, product])
        db.flush()
        db.add(OrderItem(order_id=order.id, sku="DEMO-SKU-0011", quantity=1, raw_payload={}))
        db.add(ProductShopMapping(product_id=product.id, shop_id=account.id, shop_sku="DEMO-SKU-0011"))
        db.commit()

        response = batch_print_chinese_label(OrderBatchRequest(order_ids=[30]), user=user, db=db)

    pdf_bytes = base64.b64decode(response["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = reader.pages[0].extract_text()

    assert response["printed"] == 1
    assert response["total"] == 1
    assert len(reader.pages) == 1
    assert "2026-06-06" in text
    assert "".join(text.split()).find("".join(longest_name.split())) >= 0


def test_batch_print_chinese_label_allows_blank_product_name():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    user = LocalUser(id=1, username="admin", password_hash="x", display_name="管理员", enabled=True)

    with session_factory() as db:
        order = Order(
            id=31,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id="DEMO-ORDER-0059",
            platform_order_no="DEMO-ORDER-0059",
            posting_number="DEMO-ORDER-0060",
            biz_status=ORDER_STATUS_PICKING,
            local_status="picking",
            shipment_tracking_number="DEMO-TRACKING-0014",
            shipping_deadline_at=datetime(2026, 6, 6, 8, 0, 0),
            raw_payload={},
            last_api_payload={},
        )
        db.add_all([user, order])
        db.flush()
        db.add(OrderItem(order_id=order.id, sku="DEMO-SKU-0012", quantity=1, raw_payload={}))
        db.commit()

        response = batch_print_chinese_label(OrderBatchRequest(order_ids=[31]), user=user, db=db)

    pdf_bytes = base64.b64decode(response["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = reader.pages[0].extract_text()

    assert response["printed"] == 1
    assert len(reader.pages) == 1
    assert "DEMO-TRACK\nING-0014" in text
    assert "2026-06-06" in text


def test_batch_print_chinese_label_uses_mercado_payment_date_plus_three_days():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    user = LocalUser(id=1, username="admin", password_hash="x", display_name="管理员", enabled=True)

    with session_factory() as db:
        order = Order(
            id=32,
            tenant_id="default",
            platform="mercadolibre",
            account_id="mercado-1",
            shop_id="mercado-1",
            platform_order_id="DEMO-ORDER-0061",
            platform_order_no="DEMO-ORDER-0061",
            posting_number="DEMO-ORDER-0062",
            biz_status=ORDER_STATUS_PICKING,
            local_status="picking",
            shipment_tracking_number="MERCADO-TRACK-32",
            payment_at=datetime(2026, 6, 10, 23, 30),
            platform_created_at=datetime(2026, 6, 9, 8, 0),
            shipping_deadline_at=datetime(2026, 6, 30, 8, 0),
            raw_payload={},
            last_api_payload={},
        )
        db.add_all([user, order])
        db.flush()
        db.add(OrderItem(order_id=order.id, sku="DEMO-SKU-0013", quantity=1, raw_payload={}))
        db.commit()

        response = batch_print_chinese_label(OrderBatchRequest(order_ids=[32]), user=user, db=db)

    text = PdfReader(io.BytesIO(base64.b64decode(response["pdf_base64"]))).pages[0].extract_text()

    assert response["printed"] == 1
    assert "2026-06-14" in text
    assert "2026-06-30" not in text


def test_generate_purchase_order_items_sorted_by_product_name():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderItem.__table__,
            PurchaseOrderSource.__table__,
            PurchaseOrderLog.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        account = PlatformAccount(id=101, platform="ozon", account_id="100001", display_name="Ozon")
        order = Order(
            id=40,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id="DEMO-ORDER-0063",
            platform_order_no="DEMO-ORDER-0063",
            posting_number="DEMO-ORDER-0064",
            biz_status=ORDER_STATUS_WAITING_PURCHASE,
            local_status="label_saved",
            raw_payload={},
            last_api_payload={},
        )
        products = [
            Product(id=201, product_code="DEMO-PRODUCT-0002", internal_name="产品C"),
            Product(id=202, product_code="DEMO-PRODUCT-0004", internal_name="产品A"),
            Product(id=203, product_code="DEMO-PRODUCT-0005", internal_name="产品B"),
        ]
        db.add_all([account, order, *products])
        db.flush()
        items = [
            OrderItem(id=101, order_id=order.id, sku="DEMO-SKU-0014", quantity=1, raw_payload={}),
            OrderItem(id=102, order_id=order.id, sku="DEMO-SKU-0006", quantity=1, raw_payload={}),
            OrderItem(id=103, order_id=order.id, sku="DEMO-SKU-0007", quantity=1, raw_payload={}),
        ]
        mappings = [
            ProductShopMapping(product_id=201, shop_id=account.id, shop_sku="DEMO-SKU-0014"),
            ProductShopMapping(product_id=202, shop_id=account.id, shop_sku="DEMO-SKU-0006"),
            ProductShopMapping(product_id=203, shop_id=account.id, shop_sku="DEMO-SKU-0007"),
        ]
        db.add_all([*items, *mappings])
        db.flush()

        purchase, created = main_module._generate_or_append_purchase_order_for_item_ids(
            db,
            [item.id for item in items],
            "admin",
            "",
        )

        assert created is True
        assert purchase.item_count == 3
        purchase_items = db.scalars(
            select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == purchase.id).order_by(PurchaseOrderItem.id)
        ).all()
        assert [item.product_name for item in purchase_items] == ["产品A", "产品B", "产品C"]


def test_generate_purchase_order_merges_same_product_name_quantities():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderItem.__table__,
            PurchaseOrderSource.__table__,
            PurchaseOrderLog.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        account = PlatformAccount(id=101, platform="ozon", account_id="100001", display_name="Ozon")
        order = Order(
            id=41,
            tenant_id="default",
            platform="ozon",
            account_id="100001",
            shop_id="100001",
            platform_order_id="DEMO-ORDER-0065",
            platform_order_no="DEMO-ORDER-0065",
            posting_number="DEMO-ORDER-0066",
            biz_status=ORDER_STATUS_WAITING_PURCHASE,
            local_status="label_saved",
            raw_payload={},
            last_api_payload={},
        )
        product = Product(id=204, product_code="DEMO-PRODUCT-0009", internal_name="充电器-华为-手表快充底座二代-白色-CW05")
        db.add_all([account, order, product])
        db.flush()
        items = [
            OrderItem(id=104, order_id=order.id, sku="DEMO-SKU-0015", quantity=1, raw_payload={}),
            OrderItem(id=105, order_id=order.id, sku="DEMO-SKU-0016", quantity=2, raw_payload={}),
        ]
        mappings = [
            ProductShopMapping(product_id=product.id, shop_id=account.id, shop_sku="DEMO-SKU-0015"),
            ProductShopMapping(product_id=product.id, shop_id=account.id, shop_sku="DEMO-SKU-0016"),
        ]
        db.add_all([*items, *mappings])
        db.flush()

        purchase, created = main_module._generate_or_append_purchase_order_for_item_ids(
            db,
            [item.id for item in items],
            "admin",
            "",
        )

        assert created is True
        assert purchase.source_count == 2
        assert purchase.item_count == 1
        assert purchase.total_required_qty == 3
        purchase_items = db.scalars(
            select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == purchase.id)
        ).all()
        assert len(purchase_items) == 1
        assert purchase_items[0].product_name == "充电器-华为-手表快充底座二代-白色-CW05"
        assert purchase_items[0].required_qty == 3
        assert purchase_items[0].purchase_qty == 3
        purchase_sources = db.scalars(
            select(PurchaseOrderSource).where(PurchaseOrderSource.purchase_order_id == purchase.id)
        ).all()
        assert len(purchase_sources) == 2
        assert {source.purchase_order_item_id for source in purchase_sources} == {purchase_items[0].id}


def test_merge_duplicate_purchase_order_items_keeps_sources_and_totals():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            Product.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderItem.__table__,
            PurchaseOrderSource.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        purchase = PurchaseOrder(
            id=120,
            purchase_no="PO20260604-120",
            purchase_date=date(2026, 6, 4),
            source_count=2,
            item_count=2,
            total_required_qty=2,
            created_by="admin",
        )
        item_a = PurchaseOrderItem(
            id=1201,
            purchase_order_id=purchase.id,
            product_name="充电器-华为-手表快充底座二代-白色-CW05",
            required_qty=1,
            purchase_qty=1,
            purchase_channel="1688",
        )
        item_b = PurchaseOrderItem(
            id=1202,
            purchase_order_id=purchase.id,
            product_name="充电器-华为-手表快充底座二代-白色-CW05",
            required_qty=2,
            purchase_qty=2,
            purchase_channel="淘宝",
        )
        db.add_all([purchase, item_a, item_b])
        db.flush()
        db.add_all(
            [
                PurchaseOrderSource(
                    purchase_order_id=purchase.id,
                    purchase_order_item_id=item_a.id,
                    order_id=12001,
                    order_item_id=12001,
                    product_name=item_a.product_name,
                    quantity=1,
                ),
                PurchaseOrderSource(
                    purchase_order_id=purchase.id,
                    purchase_order_item_id=item_b.id,
                    order_id=12002,
                    order_item_id=12002,
                    product_name=item_b.product_name,
                    quantity=2,
                ),
            ]
        )
        db.flush()

        merged_count = main_module._merge_duplicate_purchase_order_items(db)

        assert merged_count == 1
        purchase_items = db.scalars(
            select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == purchase.id)
        ).all()
        assert len(purchase_items) == 1
        assert purchase_items[0].required_qty == 3
        assert purchase_items[0].purchase_qty == 3
        assert purchase_items[0].purchase_channel == "1688；淘宝"
        purchase_sources = db.scalars(
            select(PurchaseOrderSource).where(PurchaseOrderSource.purchase_order_id == purchase.id)
        ).all()
        assert len(purchase_sources) == 2
        assert {source.purchase_order_item_id for source in purchase_sources} == {purchase_items[0].id}
        assert purchase.source_count == 2
        assert purchase.item_count == 1
        assert purchase.total_required_qty == 3


def test_delete_purchase_order_rolls_back_recent_picking_orders_to_waiting_purchase(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LocalUser.__table__,
            Order.__table__,
            OrderItem.__table__,
            OrderOperationLog.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderEditLock.__table__,
            PurchaseOrderItem.__table__,
            PurchaseOrderSource.__table__,
            PurchaseOrderLog.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(main_module, "_local_date_start_utc", lambda value: datetime.combine(value, datetime.min.time()))
    user = LocalUser(id=1, username="admin", password_hash="x", display_name="管理员", enabled=True)

    with session_factory() as db:
        db.add(user)
        rows = [
            Order(
                id=10,
                tenant_id="default",
                platform="ozon",
                account_id="A",
                shop_id="S",
                platform_order_id="DEMO-ORDER-0067",
                posting_number="DEMO-ORDER-0068",
                biz_status=ORDER_STATUS_PICKING,
                local_status="picking",
                payment_at=datetime(2026, 6, 1),
                picking_at=datetime(2026, 6, 1, 2, 0, 0),
                label_printed_at=datetime(2026, 6, 1, 1, 0, 0),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=11,
                tenant_id="default",
                platform="ozon",
                account_id="A",
                shop_id="S",
                platform_order_id="DEMO-ORDER-0069",
                posting_number="DEMO-ORDER-0070",
                biz_status=ORDER_STATUS_PICKING,
                local_status="picking",
                payment_at=datetime(2026, 5, 31, 23, 59, 59),
                label_printed_at=datetime(2026, 6, 1, 1, 0, 0),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=12,
                tenant_id="default",
                platform="ozon",
                account_id="A",
                shop_id="S",
                platform_order_id="DEMO-ORDER-0071",
                posting_number="DEMO-ORDER-0072",
                biz_status=ORDER_STATUS_SHIPPED,
                local_status="shipped",
                payment_at=datetime(2026, 6, 2),
                label_printed_at=datetime(2026, 6, 2, 1, 0, 0),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=13,
                tenant_id="default",
                platform="ozon",
                account_id="A",
                shop_id="S",
                platform_order_id="DEMO-ORDER-0073",
                posting_number="DEMO-ORDER-0074",
                biz_status=ORDER_STATUS_PICKING,
                local_status="picking",
                payment_at=datetime(2026, 6, 2),
                label_printed_at=datetime(2026, 6, 2, 1, 0, 0),
                raw_payload={},
                last_api_payload={},
            ),
        ]
        db.add_all(rows)
        db.flush()
        for row in rows:
            db.add(OrderItem(id=row.id * 10, order_id=row.id, sku=f"SKU-{row.id}", raw_payload={}))
        db.add(OrderItem(id=131, order_id=13, sku="DEMO-SKU-0017", raw_payload={}))
        purchase = PurchaseOrder(id=100, purchase_no="PO20260602-001", purchase_date=date(2026, 6, 2), created_by="admin")
        other_purchase = PurchaseOrder(id=101, purchase_no="PO20260602-002", purchase_date=date(2026, 6, 2), created_by="admin")
        db.add_all([purchase, other_purchase])
        db.flush()
        db.add(
            PurchaseOrderEditLock(
                purchase_order_id=purchase.id,
                locked_by=user.username,
                expires_at=datetime(2099, 1, 1),
            )
        )
        for row in rows:
            item = PurchaseOrderItem(
                id=row.id * 100,
                purchase_order_id=purchase.id,
                product_name=f"产品{row.id}",
                required_qty=1,
                purchase_qty=1,
            )
            db.add(item)
            db.flush()
            db.add(
                PurchaseOrderSource(
                    purchase_order_id=purchase.id,
                    purchase_order_item_id=item.id,
                    order_id=row.id,
                    order_item_id=row.id * 10,
                    product_name=f"产品{row.id}",
                    quantity=1,
                )
            )
        other_item = PurchaseOrderItem(
            id=1301,
            purchase_order_id=other_purchase.id,
            product_name="产品13",
            required_qty=1,
            purchase_qty=1,
        )
        db.add(other_item)
        db.flush()
        db.add(
            PurchaseOrderSource(
                purchase_order_id=other_purchase.id,
                purchase_order_item_id=other_item.id,
                order_id=13,
                order_item_id=131,
                product_name="产品13",
                quantity=1,
            )
        )
        db.commit()

        response = delete_purchase_order(100, user=user, db=db)

        assert response["message"] == "已删除，已回到待采购 1 条"
        assert db.get(Order, 10).biz_status == ORDER_STATUS_WAITING_PURCHASE
        assert db.get(Order, 10).local_status == "label_saved"
        assert db.get(Order, 10).picking_at is None
        assert db.get(Order, 11).biz_status == ORDER_STATUS_PICKING
        assert db.get(Order, 12).biz_status == ORDER_STATUS_SHIPPED
        assert db.get(Order, 13).biz_status == ORDER_STATUS_PICKING
        logs = db.scalars(select(OrderOperationLog).where(OrderOperationLog.order_id == 10)).all()
        assert len(logs) == 1
        assert logs[0].operation_type == "purchase_order_deleted_rollback"
        assert logs[0].extra["purchase_no"] == "PO20260602-001"


def test_order_dto_uses_outbound_scan_as_handover_fallback():
    row = Order(
        id=2062,
        tenant_id="default",
        platform="ozon",
        account_id="100001",
        shop_id="100001",
        shop_name="OZON DEMO SHOP A",
        platform_order_id="DEMO-ORDER-0075",
        platform_order_no="DEMO-ORDER-0076",
        posting_number="DEMO-ORDER-0077",
        platform_status="awaiting_deliver",
        biz_status=ORDER_STATUS_SHIPPED,
        local_status="shipped",
        payment_at=datetime(2026, 5, 25, 7, 23, 59),
        shipment_tracking_number="DEMO-TRACKING-0015",
        raw_payload={
            "posting_number": "DEMO-ORDER-0077",
            "status": "awaiting_deliver",
            "delivering_date": None,
        },
        created_at=datetime(2026, 5, 25, 7, 24, 54),
        updated_at=datetime(2026, 5, 26, 3, 7, 9),
    )

    dto = _order_dto(row, outbound_scanned_at=datetime(2026, 5, 26, 1, 46, 0))

    assert dto.handover_at == "2026-05-26T01:46:00Z"


def test_order_dto_uses_raw_payload_tracking_when_order_column_is_empty():
    row = Order(
        id=2063,
        tenant_id="default",
        platform="joom_logistics",
        account_id="J001",
        shop_id="J001",
        shop_name="Joom Demo Shop",
        platform_order_id="DEMO-ORDER-0078",
        platform_order_no="DEMO-ORDER-0078",
        posting_number="DEMO-ORDER-0078",
        platform_status="approved",
        biz_status=ORDER_STATUS_PENDING,
        local_status="new",
        shipment_tracking_number=None,
        raw_payload={"trackingNumber": "DEMO-TRACKING-0004"},
        created_at=datetime(2026, 5, 25, 0, 5, 0),
        updated_at=datetime(2026, 5, 25, 0, 5, 0),
    )

    dto = _order_dto(row)

    assert dto.shipment_tracking_number == "DEMO-TRACKING-0004"
    assert dto.tracking_number == "DEMO-TRACKING-0004"


def test_order_dto_includes_overseas_warehouse_fields():
    row = Order(
        id=2064,
        tenant_id="default",
        platform="wildberries",
        account_id="WB001",
        shop_id="WB001",
        shop_name="WB",
        platform_order_id="DEMO-ORDER-0079",
        platform_order_no="DEMO-ORDER-0079",
        posting_number="DEMO-ORDER-0079",
        platform_status="new",
        fulfillment_type="DBS",
        is_overseas_warehouse=True,
        biz_status=ORDER_STATUS_WAITING_PURCHASE,
        local_status="new",
        raw_payload={},
        created_at=datetime(2026, 5, 25, 0, 5, 0),
        updated_at=datetime(2026, 5, 25, 0, 5, 0),
    )

    dto = _order_dto(row)

    assert dto.fulfillment_type == "DBS"
    assert dto.is_overseas_warehouse is True


def test_normalize_batch_order_numbers_trims_deduplicates_and_validates_limit():
    submitted, numbers = _normalize_batch_order_numbers([" ORDER-1 ", "", "ORDER-2", "ORDER-1"])

    assert submitted == 3
    assert numbers == ["ORDER-1", "ORDER-2"]

    with pytest.raises(HTTPException) as exc:
        _normalize_batch_order_numbers([f"ORDER-{index}" for index in range(101)])

    assert exc.value.status_code == 400
    assert "不能超过 100 个" in exc.value.detail


def test_order_list_batch_numbers_match_exact_fields_and_report_unmatched():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Order.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OutboundScanRecord.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        rows = [
            Order(
                id=4101,
                tenant_id="default",
                platform="ozon",
                account_id="A001",
                shop_id="A001",
                platform_order_id="DEMO-ORDER-0080",
                platform_order_no="ORDER-1",
                posting_number="DEMO-ORDER-0081",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=4102,
                tenant_id="default",
                platform="ozon",
                account_id="A001",
                shop_id="A001",
                platform_order_id="DEMO-ORDER-0082",
                platform_order_no="ORDER-2",
                posting_number="POST-2",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=4103,
                tenant_id="default",
                platform="ozon",
                account_id="A001",
                shop_id="A001",
                platform_order_id="DEMO-ORDER-0084",
                platform_order_no="ORDER-3",
                posting_number="DEMO-ORDER-0085",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=4104,
                tenant_id="default",
                platform="ozon",
                account_id="A001",
                shop_id="A001",
                platform_order_id="DEMO-ORDER-0086",
                platform_order_no="ORDER-100",
                posting_number="DEMO-ORDER-0087",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=4105,
                tenant_id="default",
                platform="ozon",
                account_id="A001",
                shop_id="A001",
                platform_order_id="DEMO-ORDER-0088",
                platform_order_no="ORDER-SHIPPED",
                posting_number="DEMO-ORDER-0090",
                biz_status=ORDER_STATUS_SHIPPED,
                local_status="shipped",
                raw_payload={},
                last_api_payload={},
            ),
        ]
        db.add_all(rows)
        db.flush()
        db.add(Shipment(order_id=4103, tracking_number="TRACK-3"))
        db.commit()

        response = _query_orders(
            db=db,
            status_filter=ORDER_STATUS_PENDING,
            platform="ozon",
            transaction_id=None,
            order_no=None,
            number=None,
            payment_time_range=None,
            page=1,
            page_size=50,
            numbers=["ORDER-1", "POST-2", "TRACK-3", "ORDER-SHIPPED", "MISSING"],
            submitted_number_count=6,
        )

        assert {row.id for row in response.items} == {4101, 4102, 4103}
        assert response.total == 3
        assert response.search_summary is not None
        assert response.search_summary.submitted == 6
        assert response.search_summary.unique == 5
        assert response.search_summary.matched == 3
        assert response.search_summary.unmatched_numbers == ["ORDER-SHIPPED", "MISSING"]


def test_order_list_product_keyword_matches_item_name_sku_or_chinese_name():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OutboundScanRecord.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        account = PlatformAccount(id=101, platform="ozon", account_id="100001", display_name="Ozon")
        product = Product(id=201, product_code="DEMO-PRODUCT-0002", internal_name="中文积木套装")
        orders = [
            Order(
                id=301,
                tenant_id="default",
                platform="ozon",
                account_id="100001",
                shop_id="100001",
                platform_order_id="DEMO-ORDER-0091",
                platform_order_no="DEMO-ORDER-0091",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                payment_at=datetime(2026, 6, 1),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=302,
                tenant_id="default",
                platform="ozon",
                account_id="100001",
                shop_id="100001",
                platform_order_id="DEMO-ORDER-0092",
                platform_order_no="DEMO-ORDER-0092",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                payment_at=datetime(2026, 6, 2),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=303,
                tenant_id="default",
                platform="ozon",
                account_id="100001",
                shop_id="100001",
                platform_order_id="DEMO-ORDER-0093",
                platform_order_no="DEMO-ORDER-0093",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                payment_at=datetime(2026, 6, 3),
                raw_payload={},
                last_api_payload={},
            ),
        ]
        db.add_all([account, product, *orders])
        db.flush()
        db.add_all(
            [
                OrderItem(order_id=301, sku="DEMO-SKU-0018", platform_product_name="Robot Building Set", raw_payload={}),
                OrderItem(order_id=302, sku="SKU-CN", platform_product_name="Plain Item", raw_payload={}),
                OrderItem(order_id=303, sku="DEMO-SKU-0020", platform_product_name="Unrelated Item", raw_payload={}),
                ProductShopMapping(product_id=product.id, shop_id=account.id, shop_sku="SKU-CN"),
            ]
        )
        db.commit()

        by_name = _query_orders(db, ORDER_STATUS_PENDING, None, None, None, None, None, None, None, 1, 50, "building")
        by_sku = _query_orders(db, ORDER_STATUS_PENDING, None, None, None, None, None, None, None, 1, 50, "sku-cn")
        by_chinese_name = _query_orders(db, ORDER_STATUS_PENDING, None, None, None, None, None, None, None, 1, 50, "积木")

    assert [item.id for item in by_name.items] == [301]
    assert [item.id for item in by_sku.items] == [302]
    assert [item.id for item in by_chinese_name.items] == [302]


def test_cancelled_platform_status_moves_from_pending_to_voided_list():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OutboundScanRecord.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        db.add_all(
            [
                Order(
                    id=501,
                    tenant_id="default",
                    platform="ozon",
                    account_id="100001",
                    shop_id="100001",
                    platform_order_id="DEMO-ORDER-0094",
                    platform_order_no="DEMO-ORDER-0094",
                    posting_number="DEMO-ORDER-0095",
                    biz_status=ORDER_STATUS_PENDING,
                    local_status="new",
                    platform_status="awaiting_packaging",
                    payment_at=datetime(2026, 6, 1),
                    raw_payload={},
                    last_api_payload={},
                ),
                Order(
                    id=502,
                    tenant_id="default",
                    platform="ozon",
                    account_id="100001",
                    shop_id="100001",
                    platform_order_id="DEMO-ORDER-0096",
                    platform_order_no="DEMO-ORDER-0096",
                    posting_number="DEMO-ORDER-0097",
                    biz_status=ORDER_STATUS_PENDING,
                    local_status="new",
                    platform_status="cancelled",
                    payment_at=datetime(2026, 6, 2),
                    raw_payload={},
                    last_api_payload={},
                ),
            ]
        )
        db.commit()

        pending = _query_orders(db, ORDER_STATUS_PENDING, None, None, None, None, None, None, None, 1, 50)
        voided = _query_orders(db, ORDER_STATUS_VOIDED, None, None, None, None, None, None, None, 1, 50)

    assert [item.id for item in pending.items] == [501]
    assert [item.id for item in voided.items] == [502]
    assert voided.items[0].status == ORDER_STATUS_VOIDED


def test_order_summary_product_keyword_filters_item_rows_by_or_fields():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OutboundScanRecord.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderSource.__table__,
            ShippingDeadlineSetting.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        account = PlatformAccount(id=102, platform="ozon", account_id="397007", display_name="Ozon")
        product = Product(id=202, product_code="DEMO-PRODUCT-0004", internal_name="中文水杯")
        order = Order(
            id=401,
            tenant_id="default",
            platform="ozon",
            account_id="397007",
            shop_id="397007",
            platform_order_id="DEMO-ORDER-0098",
            platform_order_no="DEMO-ORDER-0098",
            biz_status=ORDER_STATUS_PICKING,
            local_status="picking",
            payment_at=datetime(2026, 6, 1),
            picking_at=datetime(2026, 6, 1, 8, 0, 0),
            raw_payload={},
            last_api_payload={},
        )
        db.add_all([account, product, order])
        db.flush()
        db.add_all(
            [
                OrderItem(id=4011, order_id=order.id, sku="DEMO-SKU-0021", platform_product_name="Travel Mug", raw_payload={}),
                OrderItem(id=4012, order_id=order.id, sku="DEMO-SKU-0022", platform_product_name="Notebook", raw_payload={}),
                ProductShopMapping(product_id=product.id, shop_id=account.id, shop_sku="DEMO-SKU-0021"),
            ]
        )
        db.commit()

        by_name = _query_order_summary(db, ORDER_STATUS_PICKING, None, None, None, None, None, product_keyword="travel")
        by_sku = _query_order_summary(db, ORDER_STATUS_PICKING, None, None, None, None, None, product_keyword="book")
        by_chinese_name = _query_order_summary(db, ORDER_STATUS_PICKING, None, None, None, None, None, product_keyword="水杯")

    assert [item.item_id for item in by_name.items] == [4011]
    assert [item.item_id for item in by_sku.items] == [4012]
    assert [item.item_id for item in by_chinese_name.items] == [4011]


def test_order_summary_includes_downstream_statuses_without_picking_date():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformAccount.__table__,
            Order.__table__,
            OrderItem.__table__,
            Shipment.__table__,
            LabelFile.__table__,
            OutboundScanRecord.__table__,
            Product.__table__,
            ProductShopMapping.__table__,
            PurchaseOrder.__table__,
            PurchaseOrderSource.__table__,
            ShippingDeadlineSetting.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        db.add(PlatformAccount(id=103, platform="ozon", account_id="397007", display_name="Ozon"))
        rows = [
            Order(
                id=501,
                tenant_id="default",
                platform="ozon",
                account_id="397007",
                shop_id="397007",
                platform_order_id="DEMO-ORDER-0094",
                platform_order_no="DEMO-ORDER-0094",
                posting_number="DEMO-ORDER-0099",
                biz_status=ORDER_STATUS_SHIPPED,
                local_status="shipped",
                platform_status="delivering",
                payment_at=datetime(2026, 6, 3),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=502,
                tenant_id="default",
                platform="ozon",
                account_id="397007",
                shop_id="397007",
                platform_order_id="DEMO-ORDER-0096",
                platform_order_no="DEMO-ORDER-0096",
                posting_number="DEMO-ORDER-0100",
                biz_status=ORDER_STATUS_AWAITING_PICKUP,
                local_status="awaiting_pickup",
                platform_status="awaiting_deliver",
                payment_at=datetime(2026, 6, 2),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=503,
                tenant_id="default",
                platform="ozon",
                account_id="397007",
                shop_id="397007",
                platform_order_id="DEMO-ORDER-0101",
                platform_order_no="DEMO-ORDER-0101",
                posting_number="DEMO-ORDER-0102",
                biz_status=ORDER_STATUS_DELIVERED,
                local_status="delivered",
                platform_status="delivered",
                payment_at=datetime(2026, 6, 1),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=504,
                tenant_id="default",
                platform="ozon",
                account_id="397007",
                shop_id="397007",
                platform_order_id="DEMO-ORDER-0103",
                platform_order_no="DEMO-ORDER-0103",
                posting_number="DEMO-ORDER-0104",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                platform_status="awaiting_packaging",
                payment_at=datetime(2026, 6, 4),
                raw_payload={},
                last_api_payload={},
            ),
            Order(
                id=505,
                tenant_id="default",
                platform="ozon",
                account_id="397007",
                shop_id="397007",
                platform_order_id="DEMO-ORDER-0105",
                platform_order_no="DEMO-ORDER-0105",
                posting_number="DEMO-ORDER-0106",
                biz_status=ORDER_STATUS_PENDING,
                local_status="new",
                platform_status="awaiting_packaging",
                payment_at=datetime(2026, 6, 5),
                picking_at=datetime(2026, 6, 5, 8, 0, 0),
                raw_payload={},
                last_api_payload={},
            ),
        ]
        db.add_all(rows)
        db.flush()
        db.add_all([OrderItem(id=row.id * 10, order_id=row.id, sku=f"SKU-{row.id}", raw_payload={}) for row in rows])
        db.commit()

        response = _query_order_summary(db, None, None, None, None, None, None)
        awaiting_pickup_response = _query_order_summary(db, "awaiting_delivery", None, None, None, None, None)

    assert [item.order_id for item in response.items] == [501, 502, 503]
    assert [(item.status, item.platform_status) for item in response.items] == [
        (ORDER_STATUS_SHIPPED, "delivering"),
        (ORDER_STATUS_AWAITING_PICKUP, "awaiting_deliver"),
        (ORDER_STATUS_DELIVERED, "delivered"),
    ]
    assert [item.order_id for item in awaiting_pickup_response.items] == [502]


def test_order_summary_warning_matches_spreadsheet_formula(monkeypatch):
    monkeypatch.setattr(main_module, "_local_today", lambda: date(2026, 5, 26))
    monkeypatch.setattr(main_module, "_local_now", lambda: datetime(2026, 5, 26, 10, 0, 0))

    assert _summary_warning(True, "产品A", None, datetime(2026, 5, 27, 2, 0, 0)) == ""
    assert _summary_warning(False, "", None, datetime(2026, 5, 27, 2, 0, 0)) == ""
    assert _summary_warning(False, "产品A", datetime(2026, 5, 26, 9, 0, 0), datetime(2026, 5, 27, 2, 0, 0)) == "Delivered"
    assert _summary_warning(False, "产品A", None, datetime(2026, 5, 25, 2, 0, 0)) == "Delayed"
    assert _summary_warning(False, "产品A", None, datetime(2026, 5, 27, 2, 0, 0)) == "Urgent"
    assert _summary_warning(False, "产品A", None, datetime(2026, 5, 30, 2, 0, 0)) == "4天0小时0分"
