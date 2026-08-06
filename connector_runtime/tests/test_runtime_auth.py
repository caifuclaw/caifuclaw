# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.security import _internal_service_token


def test_connector_routes_require_internal_service_token(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[security]\ninternal_service_token = "test-internal-token"\n', encoding="utf-8")
    monkeypatch.setenv("CAIFUCLAW_AI_CONFIG_FILE", str(config))
    _internal_service_token.cache_clear()
    client = TestClient(app)

    missing = client.post("/api/v1/connectors/ozon/orders/unprocessed", json={})
    invalid = client.post(
        "/api/v1/connectors/ozon/orders/unprocessed",
        json={},
        headers={"X-Internal-Service-Token": "wrong"},
    )
    accepted = client.post(
        "/api/v1/connectors/ozon/orders/unprocessed",
        json={},
        headers={"X-Internal-Service-Token": "test-internal-token"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert accepted.status_code == 200


def test_health_check_remains_public() -> None:
    assert TestClient(app).get("/health").status_code == 200
