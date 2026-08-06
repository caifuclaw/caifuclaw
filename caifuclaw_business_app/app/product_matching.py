from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from .models import OrderItem, PlatformAccount
from .product_models import Product, ProductShopMapping


def normalized_shop_sku(expr):
    return func.lower(func.trim(func.coalesce(expr, "")))


def mapping_choice_for_order_item(shop_id_expr=PlatformAccount.id):
    exact_mapping = aliased(ProductShopMapping)
    insensitive_mapping = aliased(ProductShopMapping)
    exact_product = aliased(Product)
    insensitive_product = aliased(Product)
    other_mapping_time = func.coalesce(ProductShopMapping.updated_at, ProductShopMapping.created_at)
    exact_mapping_time = func.coalesce(exact_mapping.updated_at, exact_mapping.created_at)
    insensitive_mapping_time = func.coalesce(insensitive_mapping.updated_at, insensitive_mapping.created_at)

    duplicate_exact_mapping_ids = (
        select(ProductShopMapping.id)
        .where(
            ProductShopMapping.shop_id == exact_mapping.shop_id,
            ProductShopMapping.shop_sku == exact_mapping.shop_sku,
            or_(
                other_mapping_time > exact_mapping_time,
                (other_mapping_time == exact_mapping_time) & (ProductShopMapping.id > exact_mapping.id),
            ),
        )
        .correlate(exact_mapping)
    )
    duplicate_insensitive_mapping_ids = (
        select(ProductShopMapping.id)
        .where(
            ProductShopMapping.shop_id == insensitive_mapping.shop_id,
            normalized_shop_sku(ProductShopMapping.shop_sku) == normalized_shop_sku(insensitive_mapping.shop_sku),
            or_(
                other_mapping_time > insensitive_mapping_time,
                (other_mapping_time == insensitive_mapping_time) & (ProductShopMapping.id > insensitive_mapping.id),
            ),
        )
        .correlate(insensitive_mapping)
    )

    exact_condition = (
        (exact_mapping.shop_id == shop_id_expr)
        & (exact_mapping.shop_sku == OrderItem.sku)
        & ~exact_mapping.id.in_(duplicate_exact_mapping_ids)
    )
    insensitive_condition = (
        (insensitive_mapping.shop_id == shop_id_expr)
        & (normalized_shop_sku(insensitive_mapping.shop_sku) == normalized_shop_sku(OrderItem.sku))
        & ~insensitive_mapping.id.in_(duplicate_insensitive_mapping_ids)
    )

    return {
        "exact_mapping": exact_mapping,
        "insensitive_mapping": insensitive_mapping,
        "exact_product": exact_product,
        "insensitive_product": insensitive_product,
        "exact_condition": exact_condition,
        "insensitive_condition": insensitive_condition,
    }
