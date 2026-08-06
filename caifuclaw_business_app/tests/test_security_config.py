from types import SimpleNamespace

import pytest

from app.settings import validate_security_settings


def _safe_settings():
    return SimpleNamespace(
        postgres_password="safe-postgres-password",
        sync_secret_key="safe-sync-secret-value-with-32-chars",
        admin_password="safe-admin-password",
        internal_service_token="safe-internal-service-token-value-32",
        fernet_key="safe-fernet-key",
    )


def test_secure_config_validation_allows_non_placeholder_values(monkeypatch):
    monkeypatch.setenv("CAIFUCLAW_AI_REQUIRE_SECURE_CONFIG", "1")

    validate_security_settings(_safe_settings())


def test_secure_config_validation_rejects_placeholder_values(monkeypatch):
    monkeypatch.setenv("CAIFUCLAW_AI_REQUIRE_SECURE_CONFIG", "true")
    settings = _safe_settings()
    settings.admin_password = "123456"

    with pytest.raises(RuntimeError, match="sync_admin.password"):
        validate_security_settings(settings)
