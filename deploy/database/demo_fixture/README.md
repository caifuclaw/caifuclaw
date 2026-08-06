# CaifuClaw AI Test Database Fixture

This fixture contains the current PostgreSQL schema plus a small, sanitized data set. It has no production credentials, tokens, buyer identities, addresses, request logs, audit logs, or raw API payloads.

## Quick Install

1. Copy `config_templates/caifuclaw_business_app.config.toml.example` to `caifuclaw_business_app/config.toml`.
2. Set the PostgreSQL connection values in that file.
3. From the repository root, run `.\deploy\database\install_demo_database.cmd`.

The installer creates the configured database, imports `postgres_schema.sql` and `postgres_seed.sql`, then verifies row counts. Use `-Replace` only when intentionally replacing an existing database.

## Manual PostgreSQL Install

1. Create a fresh database with `00_create_caifuclaw_ai_test.sql`.
2. Import `postgres_schema.sql`.
3. Import `postgres_seed.sql`.

## Test Login

- Username: `testadmin`
- Password: `TestPass123!`
Copy the files in `config_templates/` for the new environment and replace all placeholder secrets, URLs, and database connection values. Keep platform accounts disabled until test credentials are configured.
