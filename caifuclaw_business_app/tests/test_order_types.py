from types import SimpleNamespace

from app.order_types import (
    infer_is_overseas_warehouse,
    order_has_bsi_draft,
    order_is_joom_bsi_draft,
    order_is_joom_fbj_warehouse,
    order_is_joom_overseas_warehouse,
    order_is_joom_standard_online_fulfillment,
    order_is_overseas_warehouse,
)


def test_joom_physical_warehouse_is_overseas() -> None:
    payload = {
        "shippingOption": {
            "warehouseName": "Poland warehouse",
            "warehouseType": "physical",
        }
    }

    assert infer_is_overseas_warehouse("joom_logistics", "PHYSICAL", payload) is True


def test_joom_default_warehouse_is_not_overseas() -> None:
    payload = {
        "shippingOption": {
            "warehouseName": "Default warehouse",
            "warehouseType": "default",
        }
    }

    assert infer_is_overseas_warehouse("joom_logistics", "DEFAULT", payload) is False


def test_joom_default_order_uses_standard_online_fulfillment() -> None:
    order = SimpleNamespace(
        platform="joom_logistics",
        fulfillment_type="DEFAULT",
        raw_payload={"shippingOption": {"warehouseType": "default"}},
    )

    assert order_is_joom_standard_online_fulfillment(order) is True


def test_joom_special_fulfillment_orders_do_not_use_standard_online_flow() -> None:
    physical = SimpleNamespace(
        platform="joom_logistics",
        fulfillment_type="PHYSICAL",
        raw_payload={"shippingOption": {"warehouseType": "physical"}},
    )
    fbj = SimpleNamespace(
        platform="joom_logistics",
        fulfillment_type="FBJ",
        raw_payload={"fulfillmentType": "FBJ"},
    )
    offline = SimpleNamespace(
        platform="joom_logistics",
        fulfillment_type="DEFAULT",
        raw_payload={"onlineShippingRequired": False, "shippingMethod": "manual"},
    )

    assert order_is_joom_standard_online_fulfillment(physical) is False
    assert order_is_joom_standard_online_fulfillment(fbj) is False
    assert order_is_joom_standard_online_fulfillment(offline) is False


def test_joom_physical_warehouse_overrides_stale_database_flag() -> None:
    order = SimpleNamespace(
        platform="joom_logistics",
        fulfillment_type="PHYSICAL",
        is_overseas_warehouse=False,
        raw_payload={
            "shippingOption": {
                "warehouseName": "Poland warehouse",
                "warehouseType": "physical",
            }
        },
    )

    assert order_is_overseas_warehouse(order) is True
    assert order_is_joom_overseas_warehouse(order) is True
    assert order_is_joom_bsi_draft(order) is False


def test_non_joom_overseas_warehouse_keeps_existing_workflow() -> None:
    order = SimpleNamespace(
        platform="wildberries",
        fulfillment_type="FBO",
        is_overseas_warehouse=True,
        raw_payload={},
    )

    assert order_is_overseas_warehouse(order) is True
    assert order_is_joom_overseas_warehouse(order) is False
    assert order_is_joom_bsi_draft(order) is False


def test_joom_cn_warehouse_is_not_overseas() -> None:
    order = SimpleNamespace(
        platform="joom_logistics",
        raw_payload={
            "shippingOption": {
                "warehouseName": "Joom Logistics CN Warehouse",
                "warehouseType": "fulfillment",
            }
        },
    )

    assert order_is_joom_fbj_warehouse(order) is True
    assert order_is_overseas_warehouse(order) is False


def test_joom_fbj_fulfillment_type_uses_follow_up_export_even_without_warehouse_name() -> None:
    order = SimpleNamespace(
        platform="joom_logistics",
        fulfillment_type="FBJ",
        raw_payload={"fulfillmentType": "FBJ"},
    )

    assert order_is_joom_fbj_warehouse(order) is True
    assert order_is_joom_bsi_draft(order) is False


def test_joom_cn_warehouse_is_not_overseas_even_with_legacy_flag() -> None:
    order = SimpleNamespace(
        platform="joom_logistics",
        fulfillment_type="FULFILLMENT",
        is_overseas_warehouse=True,
        raw_payload={
            "shippingOption": {
                "warehouseName": "Joom Logistics CN Warehouse",
                "warehouseType": "fulfillment",
            }
        },
    )

    assert infer_is_overseas_warehouse(order.platform, order.fulfillment_type, order.raw_payload) is False
    assert order_is_overseas_warehouse(order) is False
    assert order_is_joom_bsi_draft(order) is False


def test_allegro_account_id_no_longer_implies_bsi_or_overseas_warehouse() -> None:
    order = SimpleNamespace(
        platform="allegro",
        account_id="allegro0001",
        fulfillment_type="SELLER",
        is_overseas_warehouse=False,
        raw_payload={},
    )

    assert order_is_overseas_warehouse(order) is False


def test_bsi_draft_state_is_recorded_on_the_order() -> None:
    order = SimpleNamespace(
        platform="joom_logistics",
        bsi_order_no="BSI-JOOM-201",
    )

    assert order_has_bsi_draft(order) is True
    assert order_is_joom_bsi_draft(order) is True
