from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DashboardPlatformSetting


OTHER_DASHBOARD_PLATFORM = "other"
DEFAULT_DASHBOARD_RECEIPT_RATES = {
    "ozon": Decimal("0.69"),
    "wildberries": Decimal("0.75"),
    "mercadolibre": Decimal("1"),
    "dmsmatrix": Decimal("1"),
    "allegro": Decimal("1"),
    "joom_logistics": Decimal("1"),
    OTHER_DASHBOARD_PLATFORM: Decimal("1"),
}

DASHBOARD_PLATFORM_ALIASES = {
    "joom": "joom_logistics",
    "joomlogistics": "joom_logistics",
    "mercado": "mercadolibre",
    "mercado_libre": "mercadolibre",
    "dms_matrix": "dmsmatrix",
    "dms-matrix": "dmsmatrix",
}


def canonical_dashboard_platform(platform: str | None) -> str:
    normalized = (platform or "").strip().lower()
    return DASHBOARD_PLATFORM_ALIASES.get(normalized, normalized)


def seed_default_dashboard_platform_settings(db: Session) -> None:
    existing = {
        row.platform: row
        for row in db.scalars(select(DashboardPlatformSetting)).all()
    }
    now = datetime.utcnow()
    for platform, receipt_rate in DEFAULT_DASHBOARD_RECEIPT_RATES.items():
        if platform in existing:
            continue
        db.add(
            DashboardPlatformSetting(
                platform=platform,
                receipt_rate=receipt_rate,
                created_at=now,
                updated_at=now,
            )
        )


def load_dashboard_receipt_rates(db: Session) -> dict[str, Decimal]:
    seed_default_dashboard_platform_settings(db)
    db.flush()
    return {
        row.platform: Decimal(row.receipt_rate or 0)
        for row in db.scalars(select(DashboardPlatformSetting)).all()
    }


def dashboard_receipt_rate_for(rates: dict[str, Decimal], platform: str | None) -> Decimal:
    canonical = canonical_dashboard_platform(platform)
    return rates.get(canonical, rates.get(OTHER_DASHBOARD_PLATFORM, Decimal("1")))
