from types import SimpleNamespace

from scripts.update_allegro_internal_order_no_from_excel import (
    ExcelRow,
    build_update_plan,
)


class FakeDb:
    def __init__(self):
        self.queries = []

    def scalar(self, statement):
        self.queries.append(("scalar", statement))
        return None

    def scalars(self, statement):
        self.queries.append(("scalars", statement))
        return SimpleNamespace(all=lambda: [])


def test_build_update_plan_skips_empty_internal_number_before_database_lookup():
    db = FakeDb()
    plan = build_update_plan(
        db,
        [
            ExcelRow(
                row_number=2,
                order_no="DEMO-ORDER-0131",
                transaction_no="DEMO-TXN-0001",
                internal_order_no="",
                tracking_no="",
            )
        ],
    )

    assert plan[0].status == "skipped_empty_internal_no"
    assert db.queries == []


def test_build_update_plan_uses_exact_transaction_number_matching(monkeypatch):
    matched_order = SimpleNamespace(id=16850, internal_order_no="DEMO-ORDER-0109")
    db = FakeDb()

    monkeypatch.setattr(
        "scripts.update_allegro_internal_order_no_from_excel._orders_by_transaction",
        lambda _db, transaction_no: [matched_order]
        if transaction_no == "DEMO-TXN-0001"
        else [],
    )

    plan = build_update_plan(
        db,
        [
            ExcelRow(
                row_number=2,
                order_no="DEMO-ORDER-0131",
                transaction_no="DEMO-TXN-0001",
                internal_order_no="DEMO-ORDER-0132",
                tracking_no="DEMO-TRACKING-0032",
            )
        ],
    )

    assert plan[0].status == "update"
    assert plan[0].order_id == 16850
    assert plan[0].current_internal_order_no == "DEMO-ORDER-0109"


def test_build_update_plan_skips_multiple_exact_matches(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(
        "scripts.update_allegro_internal_order_no_from_excel._orders_by_transaction",
        lambda _db, _transaction_no: [
            SimpleNamespace(id=1, internal_order_no="DEMO-ORDER-0133"),
            SimpleNamespace(id=2, internal_order_no="DEMO-ORDER-0134"),
        ],
    )

    plan = build_update_plan(
        db,
        [
            ExcelRow(
                row_number=45,
                order_no="DEMO-ORDER-0135",
                transaction_no="DEMO-TXN-0002",
                internal_order_no="DEMO-ORDER-0136",
                tracking_no="DEMO-TRACKING-0033",
            )
        ],
    )

    assert plan[0].status == "skipped_multiple_matches"
