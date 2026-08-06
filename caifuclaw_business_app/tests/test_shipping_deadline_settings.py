from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.deadline_settings import (
    BASE_DATE_PAYMENT_AT,
    BASE_DATE_PLATFORM_CREATED,
    BASE_DATE_SHIPPING_DEADLINE,
    calculate_dispatch_deadline,
    canonical_deadline_platform,
    seed_default_shipping_deadline_settings,
)
from app.models import ShippingDeadlineSetting


class Rule:
    def __init__(self, base_date_field: str, offset_days: int):
        self.base_date_field = base_date_field
        self.offset_days = offset_days


class Order:
    def __init__(self, platform: str, created_at: datetime | None, shipping_deadline_at: datetime | None, payment_at: datetime | None = None):
        self.platform = platform
        self.platform_created_at = created_at
        self.shipping_deadline_at = shipping_deadline_at
        self.payment_at = payment_at or created_at


def test_shipping_deadline_uses_platform_rule_base_date_and_offset():
    settings = {
        "joom_logistics": Rule(BASE_DATE_PLATFORM_CREATED, 2),
        "ozon": Rule(BASE_DATE_SHIPPING_DEADLINE, -1),
        "other": Rule(BASE_DATE_PLATFORM_CREATED, 3),
    }

    joom = Order("joom", datetime(2026, 5, 1, 8, 0, 0), datetime(2026, 5, 10, 8, 0, 0))
    ozon = Order("ozon", datetime(2026, 5, 1, 8, 0, 0), datetime(2026, 5, 10, 8, 0, 0))
    unknown = Order("unknown", datetime(2026, 5, 1, 8, 0, 0), None)

    assert canonical_deadline_platform("Joom") == "joom_logistics"
    assert calculate_dispatch_deadline(joom, settings) == datetime(2026, 5, 3, 8, 0, 0)
    assert calculate_dispatch_deadline(ozon, settings) == datetime(2026, 5, 9, 8, 0, 0)
    assert calculate_dispatch_deadline(unknown, settings) == datetime(2026, 5, 4, 8, 0, 0)


def test_shipping_deadline_returns_none_when_base_date_missing():
    settings = {"ozon": Rule(BASE_DATE_SHIPPING_DEADLINE, -1), "other": Rule(BASE_DATE_PLATFORM_CREATED, 3)}
    order = Order("ozon", datetime(2026, 5, 1, 8, 0, 0), None)

    assert calculate_dispatch_deadline(order, settings) is None


def test_shipping_deadline_returns_none_for_unknown_platform_without_other_rule():
    settings = {"ozon": Rule(BASE_DATE_SHIPPING_DEADLINE, -1)}
    order = Order("unknown", datetime(2026, 5, 1, 8, 0, 0), datetime(2026, 5, 10, 8, 0, 0))

    assert calculate_dispatch_deadline(order, settings) is None


def test_seed_default_shipping_deadline_settings_assigns_payment_based_platform_defaults():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ShippingDeadlineSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        seed_default_shipping_deadline_settings(db)
        db.commit()
        rows = db.scalars(
            select(ShippingDeadlineSetting).order_by(ShippingDeadlineSetting.sort_order.asc())
        ).all()

    assert [(row.platform, row.sort_order) for row in rows] == [
        ("ozon", 0),
        ("wildberries", 1),
        ("mercadolibre", 2),
        ("dmsmatrix", 3),
        ("allegro", 4),
        ("joom_logistics", 5),
        ("other", 6),
    ]
    assert all(row.base_date_field == BASE_DATE_PAYMENT_AT for row in rows)
    assert {row.platform: row.offset_days for row in rows} == {
        "ozon": 5,
        "wildberries": 2,
        "mercadolibre": 2,
        "dmsmatrix": 2,
        "allegro": 3,
        "joom_logistics": 3,
        "other": 3,
    }


def test_seed_migrates_legacy_defaults_once_and_preserves_custom_values():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ShippingDeadlineSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        db.add_all(
            [
                ShippingDeadlineSetting(platform="joom_logistics", base_date_field=BASE_DATE_PLATFORM_CREATED, offset_days=2, sort_order=0),
                ShippingDeadlineSetting(platform="ozon", base_date_field=BASE_DATE_SHIPPING_DEADLINE, offset_days=-1, sort_order=1),
            ]
        )
        db.commit()
        seed_default_shipping_deadline_settings(db)
        db.commit()
        ozon = db.scalar(select(ShippingDeadlineSetting).where(ShippingDeadlineSetting.platform == "ozon"))
        assert (ozon.base_date_field, ozon.offset_days) == (BASE_DATE_PAYMENT_AT, 5)

        ozon.offset_days = 7
        db.commit()
        seed_default_shipping_deadline_settings(db)
        db.commit()
        assert ozon.offset_days == 7
