import asyncio
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import _verify_shop_credentials, seed_default_platform_settings, v1_platforms
from app.models import PlatformSetting


def test_seed_default_platform_settings_preserves_enabled_state():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[PlatformSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        assert seed_default_platform_settings(db) > 0
        db.commit()

        ozon = db.scalar(select(PlatformSetting).where(PlatformSetting.platform == "ozon"))
        assert ozon is not None
        ozon.enabled = False
        ozon.updated_at = datetime(2026, 6, 1, 8, 0, 0)
        db.commit()

        seed_default_platform_settings(db)
        db.commit()

        rows = db.scalars(select(PlatformSetting).order_by(PlatformSetting.sort_order.asc())).all()

    assert rows[0].platform == "ozon"
    assert rows[0].platform_name == "Ozon"
    assert rows[0].enabled is False
    assert any(row.platform == "wildberries" and row.platform_name == "Wildberries" for row in rows)
    assert any(row.platform == "dmsmatrix" and row.platform_name == "DMSMatrix" for row in rows)


def test_platforms_dict_returns_enabled_platforms_only():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[PlatformSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        seed_default_platform_settings(db)
        db.commit()
        ozon = db.scalar(select(PlatformSetting).where(PlatformSetting.platform == "ozon"))
        assert ozon is not None
        ozon.enabled = False
        db.commit()

        rows = asyncio.run(v1_platforms(True, object(), db))

    platforms = {row["platform"] for row in rows}
    assert "ozon" not in platforms
    assert "wildberries" in platforms
    assert "dmsmatrix" in platforms
    assert all(row["enabled"] is True for row in rows)


def test_platforms_use_local_catalog_and_enabled_settings():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[PlatformSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        seed_default_platform_settings(db)
        db.commit()
        ozon = db.scalar(select(PlatformSetting).where(PlatformSetting.platform == "ozon"))
        assert ozon is not None
        ozon.enabled = False
        db.commit()

        rows = asyncio.run(v1_platforms(True, object(), db))

    platforms = {row["platform"] for row in rows}
    assert "ozon" not in platforms
    assert "wildberries" in platforms
    assert "dmsmatrix" in platforms
    assert all(row["enabled"] is True for row in rows)


def test_dmsmatrix_credentials_require_dms_fields():
    valid, missing, message = _verify_shop_credentials(
        "dmsmatrix",
        {
            "client_name": "demo-client",
            "client_id": "demo-id",
            "client_secret": "demo-secret",
            "channel_code": "demo-channel",
        },
    )

    assert valid is True
    assert missing == []
    assert message == "Token 授权成功"

    valid, missing, message = _verify_shop_credentials("dmsmatrix", {"client_name": "demo-client"})

    assert valid is False
    assert missing == ["client_id", "client_secret", "channel_code"]
    assert message == "令牌无效，请检查"
