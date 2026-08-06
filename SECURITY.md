# Security Policy

## Supported Versions

Security fixes are provided for the latest release on the default branch. Older
versions may not receive fixes.

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub private
vulnerability reporting or contact the repository maintainers through the
private security channel configured for the public repository. Include the
affected version, reproduction steps, impact, and any logs with credentials
removed.

Please do not include customer data, marketplace tokens, database dumps, or
unencrypted configuration files in a report. We will acknowledge reports and
coordinate disclosure after a fix is available.

## Deployment Requirements

Keep `8100` private and protect all internal service calls with
`X-Internal-Service-Token`. Set `CAIFUCLAW_AI_ENV=production` or
`CAIFUCLAW_AI_REQUIRE_SECURE_CONFIG=1`, use HTTPS, and replace every template
secret before exposing the business service. The legacy `CAIFUCLAW_ERP_*`
aliases remain supported for existing deployments.
