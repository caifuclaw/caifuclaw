from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.dashboard_settings import (
    dashboard_receipt_rate_for,
    load_dashboard_receipt_rates,
    seed_default_dashboard_platform_settings,
)
from app.database import Base
from app.models import DashboardPlatformSetting


def test_dashboard_receipt_rate_defaults_and_fallback():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[DashboardPlatformSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        seed_default_dashboard_platform_settings(db)
        db.commit()
        rows = db.scalars(select(DashboardPlatformSetting)).all()
        rates = load_dashboard_receipt_rates(db)

    assert len(rows) == 7
    assert dashboard_receipt_rate_for(rates, "ozon") == Decimal("0.690000")
    assert dashboard_receipt_rate_for(rates, "wildberries") == Decimal("0.750000")
    assert dashboard_receipt_rate_for(rates, "mercado") == Decimal("1.000000")
    assert dashboard_receipt_rate_for(rates, "unlisted") == Decimal("1.000000")


def test_dashboard_receipt_rate_seed_preserves_saved_value():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[DashboardPlatformSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        seed_default_dashboard_platform_settings(db)
        db.commit()
        ozon = db.scalar(select(DashboardPlatformSetting).where(DashboardPlatformSetting.platform == "ozon"))
        ozon.receipt_rate = Decimal("0.71")
        db.commit()
        seed_default_dashboard_platform_settings(db)
        db.commit()

        assert ozon.receipt_rate == Decimal("0.710000")
