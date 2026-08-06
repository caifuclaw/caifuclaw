# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.main as main_module
from app.database import Base
from app.models import Role, RoleMenuPermission


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Role.__table__, RoleMenuPermission.__table__])
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_backend_menu_definitions_include_all_managed_menus():
    menu_codes = [item["code"] for item in main_module.MENU_DEFINITIONS]

    assert "order-outbound" not in menu_codes
    assert main_module.ADMIN_MENU_CODES == menu_codes
    assert {
        "dashboard",
        "operations-daily-report",
        "traffic-analytics",
        "platform-product-catalog",
        "ai-image-processing",
        "text-translation",
        "traffic-sync-status",
        "orders",
        "order-summary",
        "purchase-orders",
        "purchase-details",
        "scan-outbound",
        "outbound-scans",
        "inventory",
        "shops",
        "products",
        "logistics-rules",
        "logistics-authorizations",
        "users",
        "permissions",
        "system-settings",
        "exchange-rates",
        "scheduled-task-logs",
        "sync-api-logs",
    }.issubset(set(menu_codes))


def test_backend_menu_definitions_match_frontend_leaf_menu_codes():
    frontend_menus = (ROOT / "caifuclaw_business_app" / "frontend" / "src" / "menus.tsx").read_text(encoding="utf-8")
    frontend_codes = set(re.findall(r"\bcode:\s*'([^']+)'", frontend_menus))
    frontend_leaf_codes = {code for code in frontend_codes if not code.startswith("group-")}

    assert {item["code"] for item in main_module.MENU_DEFINITIONS} == frontend_leaf_codes


def test_set_role_menus_keeps_real_menus_and_normalizes_legacy_alias():
    session_factory = _session_factory()
    with session_factory() as db:
        role = Role(code="ops", name="Ops")
        db.add(role)
        db.flush()

        main_module._set_role_menus(
            role,
            [
                "dashboard",
                "users",
                "permissions",
                "outbound-scans",
                "order-outbound",
                "not-real",
            ],
            db,
        )
        db.flush()

        saved = set(db.scalars(select(RoleMenuPermission.menu_code)).all())

        assert saved == {"dashboard", "users", "permissions", "outbound-scans"}
        assert main_module._role_menu_codes(role, db) == [
            "dashboard",
            "outbound-scans",
            "users",
            "permissions",
        ]


def test_sync_role_menu_permissions_migrates_order_outbound_alias():
    session_factory = _session_factory()
    with session_factory() as db:
        role = Role(code="sales", name="Sales")
        db.add(role)
        db.flush()
        db.add(RoleMenuPermission(role_id=role.id, menu_code="order-outbound"))
        db.flush()

        main_module._sync_role_menu_permissions(role, db)
        db.flush()
        saved = set(db.scalars(select(RoleMenuPermission.menu_code)).all())

        assert "order-outbound" not in saved
        assert "outbound-scans" in saved


def test_sync_role_menu_permissions_carries_traffic_access_to_status_menu():
    session_factory = _session_factory()
    with session_factory() as db:
        role = Role(code="ops", name="Ops")
        db.add(role)
        db.flush()
        db.add(RoleMenuPermission(role_id=role.id, menu_code="traffic-analytics"))
        db.flush()

        main_module._sync_role_menu_permissions(role, db)
        db.flush()
        saved = set(db.scalars(select(RoleMenuPermission.menu_code)).all())

        assert {"traffic-analytics", "traffic-sync-status"}.issubset(saved)


def test_sync_sales_role_menu_permissions_adds_operations_analysis_menus():
    session_factory = _session_factory()
    with session_factory() as db:
        role = Role(code="sales", name="Sales")
        db.add(role)
        db.flush()
        db.add(RoleMenuPermission(role_id=role.id, menu_code="orders"))
        db.flush()

        main_module._sync_role_menu_permissions(role, db)
        db.flush()

        saved = set(db.scalars(select(RoleMenuPermission.menu_code)).all())
        assert {"operations-daily-report", "platform-product-catalog"}.issubset(saved)


def test_traffic_analytics_api_requires_traffic_menu():
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/traffic-analytics/summary"), method="GET")

    assert main_module._required_menus_for_request(request) == {"traffic-analytics"}


def test_platform_product_catalog_api_requires_catalog_menu():
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/platform-product-catalog/rules"), method="GET")

    assert main_module._required_menus_for_request(request) == {"platform-product-catalog"}


def test_ai_image_api_requires_image_processing_menu():
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/ai-image/process"), method="POST")

    assert main_module._required_menus_for_request(request) == {"ai-image-processing"}


def test_ai_translation_api_requires_text_translation_menu():
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/ai-translation/translate"), method="POST")

    assert main_module._required_menus_for_request(request) == {"text-translation"}


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/v1/traffic-analytics/accounts", "GET"),
        ("/api/v1/traffic-analytics/sync", "POST"),
    ],
)
def test_traffic_sync_status_endpoints_accept_either_traffic_menu(path: str, method: str):
    request = SimpleNamespace(url=SimpleNamespace(path=path), method=method)

    assert main_module._required_menus_for_request(request) == {
        "traffic-analytics",
        "traffic-sync-status",
    }


def test_normalize_wecom_mobile_accepts_blank_and_mainland_mobile_only():
    assert main_module._normalize_wecom_mobile("") == ""
    assert main_module._normalize_wecom_mobile(" 13800000000 ") == "13800000000"

    with pytest.raises(main_module.HTTPException) as exc_info:
        main_module._normalize_wecom_mobile("12800138000")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "企微手机号格式不正确"
