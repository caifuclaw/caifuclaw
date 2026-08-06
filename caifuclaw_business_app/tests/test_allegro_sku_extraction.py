# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

from app import main, sync_engine


ALLEGRO_ITEM = {
    "offer_id": "DEMO-OFFER-0001",
    "quantity": 1,
    "raw_payload": {
        "offer": {
            "id": "13800000000",
            "external": {"id": "Book_Colour Matching Brochure_Brown"},
        }
    },
}


def test_allegro_seller_sku_precedes_offer_id_in_both_normalizers() -> None:
    expected = "Book_Colour Matching Brochure_Brown"

    assert sync_engine._item_sku(ALLEGRO_ITEM, "allegro") == expected
    assert main._item_sku(ALLEGRO_ITEM, "allegro") == expected
    assert sync_engine._normalized_order_item_payloads({"products": [ALLEGRO_ITEM]}, platform="allegro")[0]["sku"] == expected
    assert main._normalized_order_item_payloads({"products": [ALLEGRO_ITEM]}, platform="allegro")[0]["sku"] == expected


def test_non_allegro_sku_precedence_is_unchanged() -> None:
    assert sync_engine._item_sku(ALLEGRO_ITEM, "joom_logistics") == "DEMO-OFFER-0001"
    assert main._item_sku(ALLEGRO_ITEM, "joom_logistics") == "DEMO-OFFER-0001"
