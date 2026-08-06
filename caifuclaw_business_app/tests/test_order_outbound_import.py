from datetime import datetime

from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Order, OrderOperationLog, Shipment
from app.order_outbound_import import read_outbound_entries, run_order_outbound_import


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _workbook(path, rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "订单出库"
    worksheet.append(["物流单号", "发货日期"])
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
    workbook.close()


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Order.__table__, Shipment.__table__, OrderOperationLog.__table__],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _order(order_id, tracking_number, status="配货中"):
    return Order(
        id=order_id,
        tenant_id="default",
        platform="ozon",
        account_id="A",
        shop_id="S",
        platform_order_id=f"ORDER-{order_id}",
        posting_number=f"POST-{order_id}",
        shipment_tracking_number=tracking_number,
        biz_status=status,
        local_status="picking" if status == "配货中" else "shipped",
        raw_payload={},
        last_api_payload={},
    )


def test_read_outbound_entries_parses_serial_dates_and_rejects_conflicts(tmp_path):
    path = tmp_path / "orders.xlsx"
    _workbook(
        path,
        [
            [" TRACK-1 ", 46024],
            ["TRACK-1", 46024],
            ["TRACK-2", "2026-01-03"],
            ["TRACK-2", "2026-01-04"],
            ["TRACK-3", "bad-date"],
        ],
    )

    entries, issues, rows_seen = read_outbound_entries(path)

    assert rows_seen == 5
    assert [(entry.tracking_number, entry.shipped_at) for entry in entries] == [
        ("TRACK-1", datetime(2026, 1, 1, 16, 0, 0))
    ]
    assert {(issue.tracking_number, issue.reason) for issue in issues} == {
        ("TRACK-2", "shipped_date_conflict"),
        ("TRACK-3", "invalid_shipped_date"),
    }


def test_run_order_outbound_import_updates_only_picking_orders(tmp_path):
    path = tmp_path / "orders.xlsx"
    log_path = tmp_path / "outbound.csv"
    _workbook(
        path,
        [
            ["TRACK-DIRECT", "2026-07-20"],
            ["TRACK-SHIPMENT", "2026-07-21"],
            ["TRACK-SHIPPED", "2026-07-22"],
            ["TRACK-MISSING", "2026-07-23"],
        ],
    )
    factory = _session_factory()
    with factory() as db:
        db.add_all(
            [
                _order(1, "TRACK-DIRECT"),
                _order(2, ""),
                _order(3, "TRACK-SHIPPED", status="已发货"),
                Shipment(order_id=2, tracking_number="TRACK-SHIPMENT"),
            ]
        )
        db.commit()

    stats = run_order_outbound_import(path, apply=True, log_path=log_path, session_factory=factory)

    assert stats.rows_seen == 4
    assert stats.updated_orders == 2
    assert stats.would_update_orders == 2
    assert stats.skipped_not_picking == 1
    assert stats.skipped_not_found == 1
    with factory() as db:
        direct = db.get(Order, 1)
        shipment = db.get(Order, 2)
        already_shipped = db.get(Order, 3)
        assert (direct.biz_status, direct.local_status, direct.shipped_at, direct.marked_shipped_at) == (
            "已发货",
            "shipped",
            datetime(2026, 7, 19, 16, 0, 0),
            datetime(2026, 7, 19, 16, 0, 0),
        )
        assert shipment.biz_status == "已发货"
        assert shipment.shipped_at == datetime(2026, 7, 20, 16, 0, 0)
        assert already_shipped.shipped_at is None
        assert db.scalar(select(func.count(OrderOperationLog.id))) == 2
    assert "summary,updated_orders,2" in log_path.read_text(encoding="utf-8-sig")


def test_run_order_outbound_import_dry_run_does_not_change_orders(tmp_path):
    path = tmp_path / "orders.xlsx"
    log_path = tmp_path / "outbound.csv"
    _workbook(path, [["TRACK-1", "2026-07-20"]])
    factory = _session_factory()
    with factory() as db:
        db.add(_order(1, "TRACK-1"))
        db.commit()

    stats = run_order_outbound_import(path, apply=False, log_path=log_path, session_factory=factory)

    assert stats.updated_orders == 0
    assert stats.would_update_orders == 1
    with factory() as db:
        assert db.get(Order, 1).biz_status == "配货中"
        assert db.scalar(select(func.count(OrderOperationLog.id))) == 0
