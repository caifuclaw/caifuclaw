# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from deploy.database.export_test_fixture import (
    CONFIG_SECRET_VALUE,
    FixtureContext,
    PASSWORD_CONTEXT,
    TEST_ADMIN_PASSWORD,
    TEST_ADMIN_USERNAME,
    normalize_postgres_schema_for_driver,
    sanitize_config_template,
    sanitize_row,
    write_manifest,
    write_readme,
)


class ExportTestFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = FixtureContext(
            generated_at=datetime(2026, 8, 1),
            user_id=7,
            role_id=1,
            password_hash="test-password-hash",
            account_aliases={("ozon", "production-account"): "test-ozon-3"},
            fallback_accounts={"ozon": "test-ozon-3"},
            sku_aliases={"PRODUCTION-SKU": "TEST-SKU-9"},
        )

    def test_platform_account_drops_all_authorization_data(self) -> None:
        sanitized = sanitize_row(
            "platform_accounts",
            {
                "id": 3,
                "platform": "ozon",
                "account_id": "production-account",
                "encrypted_credentials": b"secret",
                "settings": {"api_key": "secret"},
                "authorization_status": "authorized",
                "token_message": "production token",
            },
            self.context,
        )

        self.assertEqual(sanitized["account_id"], "test-ozon-3")
        self.assertIsNone(sanitized["encrypted_credentials"])
        self.assertEqual(sanitized["settings"], {})
        self.assertEqual(sanitized["authorization_status"], "unauthorized")
        self.assertIsNone(sanitized["token_message"])

    def test_order_drops_buyer_identifiers_and_raw_payloads(self) -> None:
        sanitized = sanitize_row(
            "orders",
            {
                "id": 42,
                "platform": "ozon",
                "account_id": "production-account",
                "buyer_id": "buyer-123",
                "buyer_name": "Production Buyer",
                "raw_payload": {"address": "production address"},
                "last_api_payload": {"token": "secret"},
            },
            self.context,
        )

        self.assertEqual(sanitized["account_id"], "test-ozon-3")
        self.assertEqual(sanitized["buyer_id"], "TEST-BUYER-42")
        self.assertEqual(sanitized["buyer_name"], "Test Buyer")
        self.assertEqual(sanitized["raw_payload"], {})
        self.assertEqual(sanitized["last_api_payload"], {})

    def test_order_item_uses_test_sku_and_price(self) -> None:
        sanitized = sanitize_row(
            "order_items",
            {"id": 8, "sku": "PRODUCTION-SKU", "raw_payload": {"private": "data"}},
            self.context,
        )

        self.assertEqual(sanitized["sku"], "TEST-SKU-9")
        self.assertEqual(sanitized["unit_price"], "10.00")
        self.assertEqual(sanitized["raw_payload"], {})

    def test_product_mapping_uses_test_sku_and_keeps_numeric_relation_key(self) -> None:
        mapping = sanitize_row(
            "product_shop_mappings",
            {"id": 8, "shop_id": 42, "shop_sku": "PRODUCTION-SKU"},
            self.context,
        )

        self.assertEqual(mapping["shop_id"], 42)
        self.assertEqual(mapping["shop_sku"], "TEST-SKU-9")

    def test_config_template_replaces_secret_values_but_keeps_urls(self) -> None:
        sanitized = sanitize_config_template(
            'password = "production-password"\n'
            'sync_secret_key = "production-secret"\n'
            'token_url = "https://provider.example/token"\n'
            'credentials = { api_key = "production-api-key", access_token = "production-token" }\n'
        )

        self.assertIn(f'password = "{CONFIG_SECRET_VALUE}"', sanitized)
        self.assertIn(f'sync_secret_key = "{CONFIG_SECRET_VALUE}"', sanitized)
        self.assertIn('token_url = "https://provider.example/token"', sanitized)
        self.assertNotIn('production-api-key', sanitized)
        self.assertNotIn('production-token', sanitized)

    def test_schema_normalization_removes_psql_restrict_guards(self) -> None:
        normalized = normalize_postgres_schema_for_driver(
            "\\restrict generated-key\n"
            "SET transaction_timeout = 0;\n"
            "CREATE TABLE example (id integer);\n"
            "\\unrestrict generated-key\n"
        )

        self.assertEqual(normalized, "CREATE TABLE example (id integer);\n")

    def test_exported_fixture_advertises_default_admin_login(self) -> None:
        self.assertEqual(TEST_ADMIN_USERNAME, "admin")
        self.assertEqual(TEST_ADMIN_PASSWORD, "123456")

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_readme(output_dir)
            write_manifest(output_dir, {})

            readme = (output_dir / "README.md").read_text(encoding="utf-8")
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("- Username: `admin`", readme)
            self.assertIn("- Password: `123456`", readme)
            self.assertEqual(manifest["test_login"], {"username": "admin", "password": "123456"})

    def test_bundled_fixture_uses_default_admin_login(self) -> None:
        fixture_dir = Path(__file__).with_name("demo_fixture")
        seed = (fixture_dir / "postgres_seed.sql").read_text(encoding="utf-8")
        login = re.search(r'local_users.*VALUES \(1, \'([^\']+)\', \'([^\']+)\'', seed)

        self.assertIsNotNone(login)
        assert login is not None
        self.assertEqual(login.group(1), TEST_ADMIN_USERNAME)
        self.assertTrue(PASSWORD_CONTEXT.verify(TEST_ADMIN_PASSWORD, login.group(2)))

        readme = (fixture_dir / "README.md").read_text(encoding="utf-8")
        manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn(f"- Username: `{TEST_ADMIN_USERNAME}`", readme)
        self.assertIn(f"- Password: `{TEST_ADMIN_PASSWORD}`", readme)
        self.assertEqual(
            manifest["test_login"],
            {"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )


if __name__ == "__main__":
    unittest.main()
