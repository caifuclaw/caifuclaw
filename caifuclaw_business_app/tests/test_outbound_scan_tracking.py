from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.main import (
    _find_order_by_tracking_number,
    _has_successful_outbound_scan,
    _outbound_scan_number_search_condition,
    _tracking_number_lookup_key,
)
from app.models import Order


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RecordingDb:
    def __init__(self, scalar_values=None, raw_order_id=None, get_result=None):
        self.scalar_values = list(scalar_values or [])
        self.raw_order_id = raw_order_id
        self.get_result = get_result
        self.scalar_statements = []
        self.executions = []
        self.gets = []

    def scalar(self, stmt):
        compiled = stmt.compile(dialect=postgresql.dialect())
        self.scalar_statements.append((str(compiled), compiled.params))
        return self.scalar_values.pop(0) if self.scalar_values else None

    def execute(self, stmt, params=None):
        self.executions.append((str(stmt), params))
        return _ScalarOneOrNoneResult(self.raw_order_id)

    def get(self, model, value):
        self.gets.append((model, value))
        return self.get_result


def _param_values(params):
    return set(params.values())


def test_tracking_lookup_key_removes_whitespace_and_lowercases():
    assert _tracking_number_lookup_key(" SE 000000000 ZZ \n") == "se000000000zz"


def test_find_order_by_tracking_number_matches_order_column_case_insensitively():
    order = object()
    db = _RecordingDb([order])

    assert _find_order_by_tracking_number(db, "se000000000zz") is order

    sql, params = db.scalar_statements[0]
    assert "lower(btrim(orders.shipment_tracking_number))" in sql.lower()
    assert "se000000000zz" in _param_values(params)
    assert not db.executions


def test_find_order_by_tracking_number_matches_shipment_column_case_insensitively():
    order = object()
    shipment = SimpleNamespace(order_id=42)
    db = _RecordingDb([None, shipment, order])

    assert _find_order_by_tracking_number(db, "Se000000000Zz") is order

    sql, params = db.scalar_statements[1]
    assert "lower(btrim(shipments.tracking_number))" in sql.lower()
    assert "se000000000zz" in _param_values(params)


def test_find_order_by_tracking_number_matches_raw_payload_case_insensitively():
    order = object()
    db = _RecordingDb([None, None], raw_order_id=42, get_result=order)

    assert _find_order_by_tracking_number(db, " SE000000000ZZ ") is order

    sql, params = db.executions[0]
    assert "LOWER(BTRIM(raw_payload->>'tracking_number'))" in sql
    assert params == {"tracking_lookup_key": "se000000000zz"}
    assert db.gets == [(Order, 42)]


def test_successful_outbound_scan_duplicate_check_is_case_insensitive():
    db = _RecordingDb([1])

    assert _has_successful_outbound_scan(db, "SE000000000ZZ") is True

    sql, params = db.scalar_statements[0]
    assert "lower(btrim(outbound_scan_records.tracking_number))" in sql.lower()
    assert "se000000000zz" in _param_values(params)
    assert "success" in _param_values(params)


def test_outbound_scan_number_search_excludes_posting_number():
    condition = _outbound_scan_number_search_condition("ORDER-100")
    compiled = condition.compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()

    assert "outbound_scan_records.tracking_number" in sql
    assert "outbound_scan_records.platform_order_no" in sql
    assert "orders.platform_order_no" in sql
    assert "orders.platform_order_id" in sql
    assert "shipments.tracking_number" in sql
    assert "posting_number" not in sql
