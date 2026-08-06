# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime

from app.main import _extract_order_fields, _iso, _payment_range_bounds, _platform_import_time


def test_platform_import_time_normalizes_source_timezone_to_utc():
    raw_payload = {
        "payment_at": "2026-05-12T08:16:36-08:00",
        "shipping_deadline_at": "2026-05-13T08:07:08+08:00",
        "shipment_date": "2026-05-14T09:00:00Z",
    }

    extracted = _extract_order_fields(raw_payload)

    assert extracted["payment_at"] == datetime(2026, 5, 12, 16, 16, 36)
    assert extracted["shipping_deadline_at"] == datetime(2026, 5, 13, 0, 7, 8)
    assert extracted["platform_handover_deadline"] == datetime(2026, 5, 14, 9, 0, 0)
    assert _platform_import_time(raw_payload, "payment_at", extracted["payment_at"]) == "2026-05-12T16:16:36Z"


def test_mercado_shipping_deadline_prefers_order_expiration_date_over_pay_before():
    raw_payload = {
        "marketplace": "mercadolibre",
        "orders": [
            {
                "expiration_date": "2026-09-02T22:26:41.000-04:00",
                "payments": [{"date_approved": "2026-05-25T22:26:41.000-04:00"}],
            }
        ],
        "shipping": {
            "lead_time": {
                "estimated_delivery_time": {
                    "pay_before": "2026-05-26T12:59:00.000-03:00",
                }
            }
        },
    }

    extracted = _extract_order_fields(raw_payload)

    assert extracted["payment_at"] == datetime(2026, 5, 26, 2, 26, 41)
    assert extracted["shipping_deadline_at"] == datetime(2026, 9, 3, 2, 26, 41)
    assert _platform_import_time(raw_payload, "shipping_deadline_at", extracted["shipping_deadline_at"]) == "2026-09-03T02:26:41Z"


def test_system_time_iso_keeps_existing_utc_contract():
    assert _iso(datetime(2026, 5, 12, 0, 16, 36)) == "2026-05-12T00:16:36Z"


def test_payment_range_uses_platform_display_day_bounds():
    assert _payment_range_bounds(payment_start="2026-05-12", payment_end="2026-05-12") == (
        datetime(2026, 5, 11, 16, 0, 0),
        datetime(2026, 5, 12, 16, 0, 0),
    )
