from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app, current_user
from app.models import UserTablePreference


class FakeSession:
    def __init__(self, row: UserTablePreference | None = None):
        self.row = row
        self.added: list[UserTablePreference] = []
        self.deleted: list[UserTablePreference] = []
        self.commits = 0

    def scalar(self, _statement):
        return self.row

    def add(self, row: UserTablePreference) -> None:
        self.added.append(row)
        self.row = row

    def delete(self, row: UserTablePreference) -> None:
        self.deleted.append(row)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, row: UserTablePreference) -> None:
        row.id = row.id or 42


def _client_for(session: FakeSession) -> TestClient:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_get_missing_table_preference_returns_empty_contract() -> None:
    response = _client_for(FakeSession()).get("/api/v1/table-preferences/orders/main")

    assert response.status_code == 200
    assert response.json() == {
        "id": None,
        "table_key": "orders/main",
        "config_json": None,
        "created_at": None,
        "updated_at": None,
    }


def test_upsert_table_preference_creates_row() -> None:
    session = FakeSession()
    response = _client_for(session).put(
        "/api/v1/table-preferences/orders/main",
        json={"config_json": {"columns": ["status", "amount"]}},
    )

    assert response.status_code == 200
    assert response.json()["config_json"] == {"columns": ["status", "amount"]}
    assert session.row is not None
    assert session.row.user_id == 7
    assert session.row.table_key == "orders/main"
    assert session.commits == 1


def test_delete_table_preference_is_idempotent() -> None:
    row = UserTablePreference(
        id=9,
        user_id=7,
        table_key="orders/main",
        config_json={},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session = FakeSession(row)

    response = _client_for(session).delete("/api/v1/table-preferences/orders/main")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert session.deleted == [row]
    assert session.commits == 1
