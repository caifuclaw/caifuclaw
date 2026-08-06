# Open-Source Release Checklist

This repository must pass the following gates before it is made public:

- [ ] Publish only the clean public branch created from the reviewed source tree;
      never push the existing private `master` history.
- [x] Rotate the application secrets and administrator password in the local
      runtime configuration used for release verification.
- [x] Exclude `config.toml`, `.env`, certificates, logs, exports, backups,
      screenshots, internal diagnostics, and generated runtime data.
- [ ] Run Gitleaks against the complete clean public branch in CI.
- [x] Run npm and Python vulnerability audits and review direct dependency
      licenses.
- [x] Record logo, image, and font provenance in `NOTICE` and `ASSETS.md`.
- [x] Remove frontend `dist` directories from source control; build them locally
      or in CI.
- [x] Run frontend tests/build and all Python test suites from a clean checkout.
- [x] Document supported platforms, known limitations, migrations, and
      backup/restore procedures in the changelog and deployment guide.
- [x] Tag the clean public commit locally as `v1.0.0`.
- [ ] Publish the clean public branch and `v1.0.0` tag through the configured
      public remote.

Production deployment remains a separate gate: set `CAIFUCLAW_AI_ENV=production`,
replace every template value, keep connector port `8100` private, and configure
the internal service token before exposing the business service.

The private `master` branch is retained only as a local backup. Configure the
public remote after creating and validating the clean release branch, then push
only that branch.
