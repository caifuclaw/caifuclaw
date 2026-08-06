from datetime import date, datetime
from decimal import Decimal

import pytest

import app.main as main_module
from app.main import ORDER_STATUS_PENDING, dashboard_analytics


class _ExecuteResult:
    def __init__(self, row_or_rows):
        self._rows = row_or_rows if isinstance(row_or_rows, list) else [row_or_rows]

    def one(self):
        return self._rows[0]

    def all(self):
        return self._rows


class _Row:
    def __init__(self, **values):
        self.__dict__.update(values)


class _DashboardSession:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, stmt, params=None):
        compiled = str(stmt)
        self.statements.append(compiled)
        if "COUNT(*) AS total_orders" in compiled:
            return _ExecuteResult(
                _Row(
                    total_orders=3,
                    first_order_date=date(2026, 5, 1),
                    last_order_date=date(2026, 5, 26),
                    blank_currency_orders=0,
                )
            )
        if "current_period" in (params or {}):
            pass
        if "SELECT COUNT(DISTINCT order_count_key) AS orders" in compiled and "FROM receipted" in compiled and "GROUP BY" not in compiled:
            start_at = params["start_at"]
            amount = Decimal("1712") if start_at.date() == date(2026, 5, 1) else Decimal("856")
            receipt = Decimal("1181.28") if start_at.date() == date(2026, 5, 1) else Decimal("590.64")
            return _ExecuteResult(_Row(orders=2, raw_amount=amount, expected_receipt=receipt, pending=1, voided=0))
        if "TO_CHAR(DATE_TRUNC('month', order_date), 'YYYY-MM')" in compiled:
            return _ExecuteResult(
                _Row(
                    month="2026-05",
                    orders=2,
                    avg_daily_orders=1,
                    raw_amount=Decimal("1712"),
                    raw_aov=Decimal("856"),
                    expected_receipt=Decimal("1181.28"),
                    pending=1,
                    picking=0,
                    shipped=0,
                    delivered=0,
                    voided=0,
                    voided_rate=0,
                    blank_currency_orders=0,
                )
            )
        if "order_count_key" in compiled and "AS raw_aov" in compiled and "GROUP BY platform, shop" in compiled:
            return _ExecuteResult(
                _Row(
                    platform="ozon",
                    shop="demo",
                    orders=2,
                    raw_amount=Decimal("1712"),
                    raw_aov=Decimal("856"),
                    expected_receipt=Decimal("1181.28"),
                    receipt_rate_pct=Decimal("69"),
                    voided=0,
                    blank_currency_orders=0,
                )
            )
        if "GROUP BY order_date" in compiled:
            return _ExecuteResult(
                _Row(
                    order_date=date(2026, 5, 26),
                    orders=2,
                    raw_amount=Decimal("1712"),
                    expected_receipt=Decimal("1181.28"),
                    pending=1,
                    voided=0,
                )
            )
        if "GROUP BY risk_key" in compiled:
            return _ExecuteResult(
                _Row(
                    risk_key="due_24",
                    orders=1,
                    raw_amount=Decimal("856"),
                    earliest_deadline=datetime(2026, 5, 26, 18, 0),
                    latest_deadline=datetime(2026, 5, 26, 18, 0),
                )
            )
        if "GROUP BY platform, shop" in compiled:
            return _ExecuteResult(
                _Row(
                    platform="ozon",
                    shop="demo",
                    pending_orders=1,
                    pending_units=2,
                    overdue_orders=0,
                    due_24h=1,
                    due_48h=0,
                    due_later=0,
                    raw_amount=Decimal("856"),
                    min_hours_to_deadline=4,
                    earliest_deadline=datetime(2026, 5, 26, 18, 0),
                )
            )
        if "GROUP BY oi.sku" in compiled:
            return _ExecuteResult(
                _Row(
                    sku="SKU-1",
                    product_name="产品中文名称",
                    pending_orders=1,
                    pending_units=2,
                    shops=1,
                    overdue_orders=0,
                    earliest_deadline=datetime(2026, 5, 26, 18, 0),
                )
            )
        if "ORDER BY ts.units_7d DESC" in compiled:
            return _ExecuteResult(
                _Row(
                    sku="SKU-1",
                    product_name="产品中文名称",
                    units_all=2,
                    orders_all=1,
                    units_7d=2,
                    units_prev_7d=0,
                    units_7d_delta=2,
                    shops=1,
                    platforms="ozon",
                    pending_orders=1,
                )
            )
        raise AssertionError(f"Unexpected dashboard query:\n{compiled}")


class _ShopScopeSession:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, _stmt):
        rows = self.rows

        class _Rows:
            def all(self):
                return rows

        return _Rows()


class _OperationsSession:
    def __init__(self, issue_day: date = date(2026, 7, 29)):
        self.statements: list[str] = []
        self.issue_day = issue_day
        self.shops = [
            _Row(platform="ozon", account_id="seller-a", display_name="Ozon 店铺"),
            _Row(platform="mercadolibre", account_id="seller-b", display_name="Mercado 店铺"),
        ]

    def scalars(self, _stmt):
        rows = self.shops

        class _Rows:
            def all(self):
                return rows

        return _Rows()

    def execute(self, stmt, _params=None):
        compiled = str(stmt)
        self.statements.append(compiled)
        if "GROUP BY platform, account_id, order_date" in compiled:
            return _ExecuteResult(
                _Row(
                    platform="ozon",
                    account_id="seller-a",
                    order_date=date(2026, 7, 28),
                    orders=4,
                    revenue_cny=Decimal("680.50"),
                )
            )
        if "due_soon_orders" in compiled:
            return _ExecuteResult(_Row(platform="ozon", overdue_orders=2, due_soon_orders=3))
        if "traffic_metrics tm" in compiled and "negative_reviews" in compiled and "tm.stat_date = :issue_day" in compiled:
            assert _params == {"issue_day": self.issue_day}
            return _ExecuteResult(
                _Row(
                    platform="ozon",
                    platform_account_id=1,
                    account_id="seller-a",
                    shop="Ozon 店铺",
                    negative_review_count=4,
                    latest_issue_at=self.issue_day,
                )
            )
        raise AssertionError(f"Unexpected operations report query:\n{compiled}")


def test_dashboard_analytics_converts_amounts_with_nearest_exchange_rate(monkeypatch):
    monkeypatch.setattr(main_module, "_local_now", lambda: datetime(2026, 5, 26, 12, 0, 0))

    db = _DashboardSession()
    response = dashboard_analytics(db=db)

    assert response.mtd_comparison.current_amount == 1712
    assert response.mtd_comparison.current_receipt == 1181.28
    assert response.shop_sales[0].raw_amount == 1712
    assert response.shop_sales[0].expected_receipt == 1181.28
    assert response.shop_sales[0].receipt_rate_pct == 69
    assert response.daily_sales[0].raw_amount == 1712
    assert response.comparison_daily_sales[0].expected_receipt == 1181.28
    assert response.current_label == "2026-05-01~2026-05-26"
    assert response.comparison_label == "2026-04-05~2026-04-30"
    assert response.risk_skus[0].product_name == "产品中文名称"
    assert response.hot_skus[0].product_name == "产品中文名称"
    sku_mapping_queries = [statement for statement in db.statements if "product_shop_mappings" in statement]
    assert len(sku_mapping_queries) == 2
    assert all("JOIN products p" in statement for statement in sku_mapping_queries)
    assert all("platform_product_name" not in statement for statement in sku_mapping_queries)
    amount_queries = [
        statement
        for statement in db.statements
        if "FROM exchange_rates er" in statement
    ]
    assert len(amount_queries) == 8
    assert all("ABS(er.rate_date - base.order_date)" in statement for statement in amount_queries)
    assert all("base.currency_code IN ('CNY', 'RMB')" in statement for statement in amount_queries)
    receipt_queries = [statement for statement in db.statements if "dashboard_platform_settings exact_rate" in statement]
    assert len(receipt_queries) == 6
    sales_queries = [statement for statement in db.statements if "order_count_key" in statement]
    assert len(sales_queries) == 10
    assert all("transactionId" in statement for statement in sales_queries)
    assert all("COUNT(DISTINCT" in statement for statement in sales_queries)


def test_dashboard_period_uses_selected_range_and_equal_previous_period():
    start, end, previous_start, previous_end = main_module._dashboard_period(
        date(2026, 7, 14),
        date(2026, 7, 1),
        date(2026, 7, 14),
    )

    assert (start, end) == (date(2026, 7, 1), date(2026, 7, 14))
    assert (previous_start, previous_end) == (date(2026, 6, 17), date(2026, 6, 30))


def test_dashboard_comparison_period_accepts_equal_custom_range():
    comparison = main_module._dashboard_comparison_period(
        date(2026, 7, 1),
        date(2026, 7, 14),
        date(2026, 6, 17),
        date(2026, 6, 30),
        date(2025, 7, 1),
        date(2025, 7, 14),
    )

    assert comparison == (date(2025, 7, 1), date(2025, 7, 14))


def test_dashboard_comparison_period_rejects_different_length():
    with pytest.raises(main_module.HTTPException):
        main_module._dashboard_comparison_period(
            date(2026, 7, 1),
            date(2026, 7, 14),
            date(2026, 6, 17),
            date(2026, 6, 30),
            date(2025, 7, 1),
            date(2025, 7, 10),
        )


def test_dashboard_shop_scope_preserves_platform_account_pairs():
    scope = main_module.DashboardShopScope(
        shop_ids=(7, 12),
        keys=(("mercadolibre", "shared-account"), ("ozon", "shared-account")),
    )

    params = scope.params()
    scope_sql = main_module._dashboard_shop_scope_sql("o")

    assert params["dashboard_shop_scope"] == (
        '[{"platform": "mercadolibre", "account_id": "shared-account"}, '
        '{"platform": "ozon", "account_id": "shared-account"}]'
    )
    assert "jsonb_to_recordset" in scope_sql
    assert "selected_shop.platform" in scope_sql
    assert "o.account_id" in scope_sql
    assert "o.shop_id" in scope_sql


def test_dashboard_empty_shop_scope_keeps_all_shops():
    scope = main_module.DashboardShopScope()

    assert scope.is_filtered is False
    assert scope.params() == {"dashboard_shop_scope": None}


def test_dashboard_risk_queries_compare_deadlines_in_utc():
    session = _DashboardSession()

    main_module._dashboard_risk_buckets(session)
    main_module._dashboard_risk_shops(session)
    main_module._dashboard_risk_skus(session)

    risk_queries = [statement for statement in session.statements if "order_risk_handlings" in statement]
    assert len(risk_queries) == 3
    assert all("timezone('UTC', NOW())" in statement for statement in risk_queries)


def test_operations_daily_report_fills_enabled_shops_and_risk_zeros(monkeypatch):
    monkeypatch.setattr(main_module, "_local_now", lambda: datetime(2026, 7, 30, 10, 15, 0))
    session = _OperationsSession()

    report = main_module._operations_daily_report(session, report_date=date(2026, 7, 29))

    assert report.date_from == "2026-07-23"
    assert report.date_to == "2026-07-29"
    assert report.generated_at == "2026-07-30T10:15:00+08:00"
    assert len(report.shop_daily_orders) == 2
    assert [point.date for point in report.shop_daily_orders[0].days] == [
        "2026-07-23",
        "2026-07-24",
        "2026-07-25",
        "2026-07-26",
        "2026-07-27",
        "2026-07-28",
        "2026-07-29",
    ]
    assert [point.orders for point in report.shop_daily_orders[0].days] == [0, 0, 0, 0, 0, 4, 0]
    assert [point.revenue_cny for point in report.shop_daily_orders[0].days] == [0, 0, 0, 0, 0, 680.5, 0]
    assert report.shop_daily_orders[0].total_revenue_cny == 680.5
    assert report.shop_daily_orders[1].total_orders == 0
    assert report.shop_daily_orders[1].total_revenue_cny == 0
    assert [(item.platform, item.overdue_orders, item.due_soon_orders) for item in report.fulfillment_risk] == [
        ("mercadolibre", 0, 0),
        ("ozon", 2, 3),
    ]
    assert [(item.platform, item.shop, item.count, item.latest_issue_at) for item in report.customer_complaints] == [
        ("ozon", "Ozon 店铺", 4, "2026-07-29"),
    ]
    assert report.customer_complaints_data_status == "negative_reviews"

    daily_query = next(statement for statement in session.statements if "GROUP BY platform, account_id, order_date" in statement)
    risk_query = next(statement for statement in session.statements if "due_soon_orders" in statement)
    complaint_query = next(statement for statement in session.statements if "traffic_metrics tm" in statement)
    assert "INTERVAL '8 hours'" in daily_query
    assert "SUM(cny_amount)" in daily_query
    assert "FROM exchange_rates er" in daily_query
    assert "o.biz_status IN (:pending, :picking)" in risk_query
    assert "timezone('UTC', NOW())" in risk_query
    assert "tm.grain = 'daily'" in complaint_query
    assert "tm.stat_date = :issue_day" in complaint_query
    assert "date_range" not in complaint_query
    assert "rolling_30d" not in complaint_query
    assert "JOIN active_accounts aa ON aa.platform_account_id = tm.platform_account_id" in complaint_query
    assert "COALESCE(tm.negative_reviews, 0) > 0" in complaint_query
    assert "GROUP BY aa.platform, aa.platform_account_id, aa.account_id, aa.shop" in complaint_query


def test_operations_daily_report_defaults_to_yesterday(monkeypatch):
    monkeypatch.setattr(main_module, "_local_now", lambda: datetime(2026, 7, 30, 10, 15, 0))
    session = _OperationsSession(issue_day=date(2026, 7, 29))

    report = main_module._operations_daily_report(session)

    assert report.date_from == "2026-07-23"
    assert report.date_to == "2026-07-29"
    assert report.customer_complaints[0].latest_issue_at == "2026-07-29"


@pytest.mark.parametrize("report_date", [date(2026, 7, 30), date(2026, 7, 31)])
def test_operations_daily_report_rejects_incomplete_date(monkeypatch, report_date):
    monkeypatch.setattr(main_module, "_local_now", lambda: datetime(2026, 7, 30, 10, 15, 0))

    with pytest.raises(main_module.HTTPException, match="统计日期不能晚于昨天") as exc_info:
        main_module._operations_daily_report(_OperationsSession(), report_date=report_date)

    assert exc_info.value.status_code == 422


def test_dashboard_shop_scope_resolves_and_canonicalizes_selected_accounts():
    db = _ShopScopeSession([_Row(id=12, platform="joom", account_id="seller-12")])

    scope = main_module._dashboard_shop_scope(db, [12, 12])

    assert scope.shop_ids == (12,)
    assert scope.keys == (("joom_logistics", "seller-12"),)


def test_dashboard_shop_scope_rejects_missing_accounts():
    with pytest.raises(main_module.HTTPException, match="所选店铺不存在"):
        main_module._dashboard_shop_scope(_ShopScopeSession([]), [404])
