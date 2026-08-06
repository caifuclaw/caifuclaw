# Database Operations

CaifuClaw ERP uses one PostgreSQL business database configured by `caifuclaw_business_app/config.toml`.

## Initialize

```powershell
python scripts\init_databases.py
```

The business service creates missing tables and indexes during startup.

## Install Bundled Demo Database

After copying `caifuclaw_business_app/config.template.toml` to `config.toml` and setting its PostgreSQL connection values, run:

```powershell
.\deploy\database\install_demo_database.cmd
```

The bundled fixture creates the configured database, imports the schema and sanitized demo data, and verifies the imported row counts. Use `-Replace` only when deliberately rebuilding an existing database. The test login is `testadmin` / `TestPass123!`.

## Back Up

Create and verify a PostgreSQL custom-format dump:

```powershell
python deploy\database\backup_postgres.py --config caifuclaw_business_app\config.toml
```

For a full snapshot containing PostgreSQL, labels, listing files and runtime configuration:

```powershell
python deploy\database\backup_all.py --config caifuclaw_business_app\config.toml --business-config caifuclaw_business_app\config.toml
```

## Export SQL

```powershell
python deploy\database\export_database.py
```

This writes the PostgreSQL creation script, schema/data SQL and `manifest.json` under `deploy/database/sql`.

## Restore SQL

```powershell
python deploy\database\upgrade_database.py
```

Use `--replace` only when the target PostgreSQL database may be dropped and recreated. Use `--skip-existing` to leave a populated target unchanged.

## Sanitized Fixture

```powershell
python deploy\database\export_test_fixture.py --output-dir outputs\test-fixture
```

The fixture contains a sanitized PostgreSQL schema and small test data set. It excludes production credentials, tokens, request payloads and personal data.
