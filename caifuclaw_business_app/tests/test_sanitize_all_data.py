from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sanitize_all_data import ColumnInfo, _is_safe_runtime_path, _sanitize_config_text, _synthetic_expression


def test_runtime_config_sanitizes_external_credentials_and_demo_login() -> None:
    source = """\
[postgres]
password = "keep-local-database-password"

[oauth.allegro]
client_id = "production-client"
client_secret = "production-secret"
token_url = "https://example.invalid/token"

[exchange_rates]
enabled = true

[exchange_rates.tencent_cloud_market]
secret_id = "production-id"
secret_key = "production-key"

[security]
sync_secret_key = "production-sync-secret"
fernet_key = "production-fernet-key"

[sync_admin]
username = "production-admin"
password = "production-password"
"""

    sanitized, changed = _sanitize_config_text(source)

    assert 'password = "keep-local-database-password"' in sanitized
    assert 'client_id = ""' in sanitized
    assert 'client_secret = ""' in sanitized
    assert 'enabled = false' in sanitized
    assert 'secret_id = ""' in sanitized
    assert 'secret_key = ""' in sanitized
    assert 'sync_secret_key = "REPLACE_WITH_AT_LEAST_32_RANDOM_CHARACTERS"' in sanitized
    assert 'fernet_key = ""' in sanitized
    assert 'username = "admin"' in sanitized
    assert 'password = "123456"' in sanitized
    assert len(changed) == 9


def test_template_config_uses_explicit_password_placeholders() -> None:
    source = """\
[postgres]
password = "legacy-password"

[sync_admin]
username = "legacy-admin"
password = "legacy-admin-password"
"""

    sanitized, changed = _sanitize_config_text(source, template=True)

    assert sanitized.count('password = "change-me"') == 1
    assert 'username = "admin"' in sanitized
    assert 'password = "REPLACE_WITH_AT_LEAST_12_RANDOM_CHARACTERS"' in sanitized
    assert changed == ["postgres.password", "sync_admin.username", "sync_admin.password"]


def test_synthetic_expression_clears_nested_payloads() -> None:
    column = ColumnInfo("raw_payload", "jsonb", True, None)

    expression = _synthetic_expression("orders", column)

    assert expression == 'CASE WHEN "raw_payload" IS NULL THEN NULL ELSE \'{}\'::jsonb END'


def test_synthetic_expression_preserves_structural_platform() -> None:
    column = ColumnInfo("platform", "character varying", False, 50)

    assert _synthetic_expression("orders", column) is None


def test_synthetic_expression_replaces_business_identifier() -> None:
    column = ColumnInfo("platform_order_no", "character varying", False, 64)

    expression = _synthetic_expression("orders", column)

    assert expression is not None
    assert "DEMO-" in expression
    assert "id::text" in expression


def test_runtime_path_guard_rejects_repository_root() -> None:
    assert not _is_safe_runtime_path(ROOT)
    assert _is_safe_runtime_path(ROOT / "output")
