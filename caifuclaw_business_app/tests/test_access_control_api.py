from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import MENU_DEFINITIONS, app, require_admin


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_admin_can_list_managed_menus() -> None:
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)

    response = TestClient(app).get("/api/v1/menus")

    assert response.status_code == 200
    assert response.json() == MENU_DEFINITIONS
