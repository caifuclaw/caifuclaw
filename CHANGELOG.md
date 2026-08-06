# Changelog

## 1.0.0 - 2026-08-06

- Added service-to-service authentication for internal credential endpoints and
  connector runtime calls.
- Added HttpOnly session cookies, login throttling, and secure configuration
  validation.
- Added Apache-2.0 licensing and public contribution/security policies.
- Added a sanitized PostgreSQL demo fixture and documented Windows and macOS
  deployment workflows.
- Removed generated frontend bundles and internal diagnostics from the public
  source tree; builds now generate runtime assets locally or in CI.
- Replaced React Router with Wouter after upstream advisories left no published
  React Router release without a production dependency audit finding.
- Added reproducible frontend, Python dependency, and license audit guidance.

### Supported Platforms

- Windows 10/11 and Windows Server are the primary deployment targets.
- macOS is supported through the bundled `launchd` watchdog scripts.
- Linux can run the Python services but does not yet include a service installer.

### Upgrade and Backup Notes

- Back up PostgreSQL and runtime files before every upgrade.
- Review `deploy/database` migrations before replacing an existing database.
- Follow `docs/deployment.md` for backup, restore, HTTPS, and service restart
  procedures.
