# Contributing

## Before You Start

Please read `SECURITY.md` before reporting security issues. Do not commit
customer records, marketplace credentials, local configuration files, logs,
generated exports, or production screenshots.

## Development Setup

1. Copy `caifuclaw_business_app/config.template.toml` to
   `caifuclaw_business_app/config.toml` and fill local-only values.
2. Install Python dependencies from `requirements.txt` and
   `connector_runtime/requirements.txt`.
3. Run `npm ci` in `caifuclaw_business_app/frontend`.
4. Use the build and start commands in `docs/deployment.md`.

## Validation

Run the frontend type check and tests, both Python test suites, and
`build_caifuclaw_erp.cmd` before opening a pull request. Changes that affect
authentication, credentials, configuration, or connectors must include tests.

Use English commit messages that describe one focused change. Keep pull
requests small enough to review and explain any migration or deployment impact.
