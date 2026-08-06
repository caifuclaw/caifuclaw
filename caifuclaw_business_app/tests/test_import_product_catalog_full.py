# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from types import SimpleNamespace

from scripts.import_product_catalog_full import (
    ImportStats,
    MappingValue,
    ProductGroup,
    apply_latest_sku_owner,
    build_buyer_lookup,
    selected_field_value,
)


def test_apply_latest_sku_owner_keeps_later_product_for_cross_product_sku():
    groups = {
        "old name": ProductGroup(name="old name", first_row=10),
        "new name": ProductGroup(name="new name", first_row=11),
    }
    stats = ImportStats()
    events = []

    apply_latest_sku_owner(
        groups,
        [
            MappingValue(row_no=10, sequence=1, product_name="old name", shop_id=1, shop_name="Shop", sku="SKU-1"),
            MappingValue(row_no=11, sequence=2, product_name="new name", shop_id=1, shop_name="Shop", sku="SKU-1"),
        ],
        stats,
        events,
    )

    assert groups["old name"].mappings == {}
    assert groups["new name"].mappings == {1: ["SKU-1"]}
    assert stats.source_mapping_ignored_by_later_row == 1
    assert events[0]["type"] == "source_mapping_ignored_by_later_row"
    assert events[0]["row"] == 10


def test_apply_latest_sku_owner_keeps_multiple_skus_for_same_product_shop():
    groups = {"product": ProductGroup(name="product", first_row=20)}
    stats = ImportStats()

    apply_latest_sku_owner(
        groups,
        [
            MappingValue(row_no=20, sequence=1, product_name="product", shop_id=1, shop_name="Shop", sku="DEMO-SKU-0006"),
            MappingValue(row_no=21, sequence=2, product_name="product", shop_id=1, shop_name="Shop", sku="DEMO-SKU-0007"),
        ],
        stats,
        [],
    )

    assert groups["product"].mappings == {1: ["DEMO-SKU-0006", "DEMO-SKU-0007"]}
    assert stats.source_mapping_ignored_by_later_row == 0


def test_selected_field_value_latest_uses_last_row_value():
    values = [
        SimpleNamespace(row_no=1, value="first"),
        SimpleNamespace(row_no=2, value="last"),
    ]

    assert selected_field_value(values, "latest") == "last"
    assert selected_field_value(values, "first") == "first"


def test_build_buyer_lookup_supports_catalog_aliases():
    db = SimpleNamespace(
        scalars=lambda _: SimpleNamespace(
            all=lambda: [
                SimpleNamespace(username="tony", display_name="tony", enabled=True),
                SimpleNamespace(username="cangku", display_name="仓库", enabled=True),
            ]
        )
    )

    lookup = build_buyer_lookup(db)

    assert lookup["Tony"].username == "tony"
    assert lookup["库存"].username == "cangku"
