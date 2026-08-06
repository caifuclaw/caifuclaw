from app.logistics_rules import (
    LOGISTICS_MATCH_STATUS_MANUAL,
    apply_logistics_rules,
    apply_manual_logistics_channel,
    match_logistics_rule,
    order_matches_logistics_carrier_rule,
    split_logistics_rule_eligible_orders,
)
from app.models import LogisticsMatchRule, Order


def _order(**kwargs):
    base = {
        "tenant_id": "default",
        "platform": "wildberries",
        "account_id": "WB DEMO SHOP CN",
        "shop_id": "WB DEMO SHOP CN",
        "shop_name": "WB DEMO SHOP CN",
        "platform_order_id": "DEMO-ORDER-0015",
        "posting_number": "",
        "platform_status": "new",
        "local_status": "new",
        "country_code": "CN",
    }
    base.update(kwargs)
    return Order(**base)


def test_logistics_rule_matches_shop_and_country():
    order = _order()
    rule = LogisticsMatchRule(
        id=1,
        name="WB DEMO SHOP 中国订单",
        platform="wildberries",
        priority=1,
        enabled=True,
        shop_names=["WB DEMO SHOP CN"],
        country_codes=["CN"],
        logistics_channel="WB 中国专线",
        carrier_code="wanbang_suda_new",
    )

    result = match_logistics_rule(order, [rule])

    assert result.status == "matched"
    assert result.logistics_channel == "WB 中国专线"
    assert result.carrier_code == "wanbang_suda_new"
    assert result.rule_name == "WB DEMO SHOP 中国订单"
    assert "WB DEMO SHOP CN" in result.reason
    assert "CN" in result.reason

    assert apply_logistics_rules(order, [rule]) is True
    assert order.logistics_carrier_code == "wanbang_suda_new"


def test_manual_logistics_channel_is_not_overwritten_by_auto_match():
    order = _order()
    rule = LogisticsMatchRule(
        id=1,
        name="WB DEMO SHOP 中国订单",
        platform="wildberries",
        priority=1,
        enabled=True,
        shop_names=["WB DEMO SHOP CN"],
        country_codes=["CN"],
        logistics_channel="WB 中国专线",
    )

    apply_manual_logistics_channel(order, "人工渠道", carrier_code="bsi_overseas")
    changed = apply_logistics_rules(order, [rule])

    assert changed is False
    assert order.logistics_match_status == LOGISTICS_MATCH_STATUS_MANUAL
    assert order.logistics_channel == "人工渠道"
    assert order.logistics_carrier_code == "bsi_overseas"


def test_logistics_rule_does_not_match_other_platform():
    order = _order(platform="ozon")
    rule = LogisticsMatchRule(
        id=1,
        name="WB DEMO SHOP 中国订单",
        platform="wildberries",
        priority=1,
        enabled=True,
        shop_names=["WB DEMO SHOP CN"],
        country_codes=["CN"],
        logistics_channel="WB 中国专线",
    )

    result = match_logistics_rule(order, [rule])

    assert result.status == "unmatched"
    assert result.logistics_channel == ""


def test_logistics_rule_matches_overseas_warehouse_condition():
    overseas_order = _order(is_overseas_warehouse=True)
    non_overseas_order = _order(is_overseas_warehouse=False)
    rule = LogisticsMatchRule(
        id=1,
        name="WB 海外仓",
        platform="wildberries",
        priority=1,
        enabled=True,
        is_overseas_warehouse=True,
        logistics_channel="WB 海外仓渠道",
    )

    assert match_logistics_rule(overseas_order, [rule]).status == "matched"
    assert match_logistics_rule(non_overseas_order, [rule]).status == "unmatched"

    non_overseas_rule = LogisticsMatchRule(
        id=2,
        name="WB 非海外仓",
        platform="wildberries",
        priority=1,
        enabled=True,
        is_overseas_warehouse=False,
        logistics_channel="WB 自发货渠道",
    )
    assert match_logistics_rule(non_overseas_order, [non_overseas_rule]).status == "matched"
    assert match_logistics_rule(overseas_order, [non_overseas_rule]).status == "unmatched"


def test_logistics_rule_without_overseas_warehouse_condition_matches_all_orders():
    overseas_order = _order(is_overseas_warehouse=True)
    rule = LogisticsMatchRule(
        id=1,
        name="WB 全部",
        platform="wildberries",
        priority=1,
        enabled=True,
        is_overseas_warehouse=None,
        logistics_channel="WB 通用渠道",
    )

    assert match_logistics_rule(overseas_order, [rule]).status == "matched"


def test_bsi_draft_eligibility_uses_the_matching_rule_carrier_code():
    order = _order(platform="allegro", account_id="allegro0001", shop_id="allegro0001", shop_name="Allegro Demo Shop")
    bsi_rule = LogisticsMatchRule(
        id=1,
        name="Allegro BSI",
        platform="allegro",
        priority=10,
        enabled=True,
        shop_names=["Allegro Demo Shop"],
        logistics_channel="BSI海外仓 / DEMO-CARRIER-3",
        carrier_code="bsi_overseas",
    )
    other_rule = LogisticsMatchRule(
        id=2,
        name="Allegro normal",
        platform="allegro",
        priority=20,
        enabled=True,
        logistics_channel="普通渠道",
        carrier_code="wanbang_suda_new",
    )

    assert order_matches_logistics_carrier_rule(order, [bsi_rule, other_rule], "bsi_overseas") is True
    assert order_matches_logistics_carrier_rule(order, [bsi_rule, other_rule], "wanbang_suda_new") is False

    apply_manual_logistics_channel(order, "人工渠道")
    assert order_matches_logistics_carrier_rule(order, [bsi_rule, other_rule], "bsi_overseas") is False


def test_split_logistics_rule_eligible_orders_requires_match_when_platform_has_rules():
    matched = _order(id=1, shop_id="WB DEMO SHOP CN", shop_name="WB DEMO SHOP CN", country_code="CN")
    unmatched = _order(id=2, shop_id="OTHER", shop_name="OTHER", country_code="US")
    unrestricted = _order(id=3, platform="ozon", shop_id="OZON", shop_name="OZON", country_code="US")
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

    eligible, skipped = split_logistics_rule_eligible_orders([matched, unmatched, unrestricted], [rule])

    assert [row.id for row in eligible] == [1, 3]
    assert [row.id for row in skipped] == [2]
    assert matched.logistics_match_status == "matched"
    assert unmatched.logistics_match_status == "unmatched"


def test_split_logistics_rule_eligible_orders_allows_all_when_no_enabled_platform_rule():
    order = _order(id=1, platform="ozon", shop_id="OZON", shop_name="OZON", country_code="US")
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

    eligible, skipped = split_logistics_rule_eligible_orders([order], [rule])

    assert eligible == [order]
    assert skipped == []


def test_split_logistics_rule_eligible_orders_keeps_regular_joom_online_orders_out_of_bsi_rule_gate():
    order = _order(
        id=1,
        platform="joom_logistics",
        fulfillment_type="DEFAULT",
        country_code="NL",
        logistics_match_status="unmatched",
        raw_payload={"shippingOption": {"warehouseType": "default"}},
    )
    bsi_rule = LogisticsMatchRule(
        id=1,
        name="Joom BSI warehouse",
        platform="joom_logistics",
        priority=1,
        enabled=True,
        is_overseas_warehouse=True,
        logistics_channel="BSI warehouse",
        carrier_code="bsi_overseas",
    )

    eligible, skipped = split_logistics_rule_eligible_orders([order], [bsi_rule])

    assert eligible == [order]
    assert skipped == []
    assert order.logistics_match_status == "unmatched"
