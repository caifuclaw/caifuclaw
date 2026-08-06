# CaifuClaw AI

CaifuClaw AI is an open-source multi-marketplace ERP and order-fulfillment
system. It
combines two Python services:

- `caifuclaw_business_app`: business API and React frontend for shop credentials,
  OAuth authorization, order sync, purchasing, printing, exchange rates, and
  logistics callbacks.
- `connector_runtime`: private connector service for marketplace API adapters,
  normalized order data, fulfillment, and labels.

The system uses PostgreSQL. Copy
`caifuclaw_business_app/config.template.toml` to `config.toml`; never commit
marketplace credentials, provider keys, customer data, logs, or exports.

## Quick Start

Prerequisites: Python 3.11+, Node.js 20+, and PostgreSQL 14+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r caifuclaw_business_app\requirements.txt
pip install -r connector_runtime\requirements.txt
Push-Location caifuclaw_business_app\frontend
npm ci
Pop-Location
Copy-Item caifuclaw_business_app\config.template.toml caifuclaw_business_app\config.toml
.\deploy\database\install_demo_database.cmd
.\build_caifuclaw_erp.cmd
.\start_caifuclaw_erp.cmd -Restart
```

Set the PostgreSQL connection values in the copied configuration before running the demo installer. It creates the configured database with sanitized demo data and a `testadmin` / `TestPass123!` login. Use `python scripts\init_databases.py` instead when you need an empty database. Replace every placeholder in the copied configuration before production use.
Production must set `CAIFUCLAW_AI_ENV=production` and keep connector port `8100`
private. The legacy `CAIFUCLAW_ERP_*` environment variables and `*_erp` command
wrappers remain supported for deployment compatibility. See
[deployment](docs/deployment.md) for HTTPS, backups, and service configuration.

## Development

```powershell
.\build_caifuclaw_erp.cmd
.\start_caifuclaw_erp.cmd -Restart
```

- Business app: `http://127.0.0.1:9999`
- Connector health: `http://127.0.0.1:8100/health`

Run frontend tests with `npm test -- --run`, business tests with
`python -m pytest -q` from `caifuclaw_business_app`, and connector tests from
`connector_runtime`.

## Project Policies

- [Security policy](SECURITY.md)
- [Contributing guide](CONTRIBUTING.md)
- [Open-source release checklist](docs/open-source-release.md)
- [Asset sources and licenses](ASSETS.md)
- [Third-party dependency licenses](THIRD_PARTY_LICENSES.md)
- [Changelog](CHANGELOG.md)

Licensed under [Apache-2.0](LICENSE). Product marks remain protected; see
[TRADEMARKS.md](TRADEMARKS.md).
