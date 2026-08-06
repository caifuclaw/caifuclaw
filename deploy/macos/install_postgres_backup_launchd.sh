#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LABEL="com.caifuclaw-ai.postgres-backup"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LEGACY_LABEL="com.caifuclaw-erp.postgres-backup"
PYTHON="${CAIFUCLAW_AI_PYTHON:-${CAIFUCLAW_ERP_PYTHON:-}}"
BACKUP_DIR="${CAIFUCLAW_AI_BACKUP_DIR:-${CAIFUCLAW_AI_POSTGRES_BACKUP_DIR:-${CAIFUCLAW_ERP_BACKUP_DIR:-${CAIFUCLAW_ERP_POSTGRES_BACKUP_DIR:-${HOME}/caifuclaw_ai_backups/full}}}}"
RETENTION_DAYS="${CAIFUCLAW_AI_BACKUP_RETENTION_DAYS:-${CAIFUCLAW_AI_POSTGRES_BACKUP_RETENTION_DAYS:-${CAIFUCLAW_ERP_BACKUP_RETENTION_DAYS:-${CAIFUCLAW_ERP_POSTGRES_BACKUP_RETENTION_DAYS:-14}}}}"
HOUR="${CAIFUCLAW_AI_POSTGRES_BACKUP_HOUR:-${CAIFUCLAW_ERP_POSTGRES_BACKUP_HOUR:-1}}"
MINUTE="${CAIFUCLAW_AI_POSTGRES_BACKUP_MINUTE:-${CAIFUCLAW_ERP_POSTGRES_BACKUP_MINUTE:-0}}"
LOG_DIR="${CAIFUCLAW_AI_BACKUP_LOG_DIR:-${CAIFUCLAW_ERP_BACKUP_LOG_DIR:-${ROOT}/logs/backup}}"
UID_VALUE="$(id -u)"

if [ -z "$PYTHON" ]; then
  if [ -x "${ROOT}/.venv312/bin/python" ]; then
    PYTHON="${ROOT}/.venv312/bin/python"
  elif [ -x "${ROOT}/.venv/bin/python" ]; then
    PYTHON="${ROOT}/.venv/bin/python"
  else
    PYTHON="$(command -v python3 || true)"
  fi
fi

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
  echo "Python executable not found. Set CAIFUCLAW_AI_PYTHON." >&2
  exit 1
fi

mkdir -p "${HOME}/Library/LaunchAgents" "$LOG_DIR" "$BACKUP_DIR"
chmod +x "${ROOT}/deploy/database/backup_postgres.py"

cat >"$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${ROOT}/deploy/database/backup_postgres.py</string>
    <string>--config</string>
    <string>${ROOT}/caifuclaw_business_app/config.toml</string>
    <string>--backup-dir</string>
    <string>${BACKUP_DIR}</string>
    <string>--log-dir</string>
    <string>${LOG_DIR}</string>
    <string>--retention-days</string>
    <string>${RETENTION_DAYS}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>${HOUR}</integer>
    <key>Minute</key>
    <integer>${MINUTE}</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>CAIFUCLAW_AI_ROOT</key>
    <string>${ROOT}</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
PLIST

legacy_plist="${HOME}/Library/LaunchAgents/${LEGACY_LABEL}.plist"
launchctl bootout "gui/${UID_VALUE}" "$legacy_plist" >/dev/null 2>&1 || true
launchctl remove "$LEGACY_LABEL" >/dev/null 2>&1 || true
rm -f "$legacy_plist"
launchctl bootout "gui/${UID_VALUE}" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST"

echo "Installed ${LABEL}"
echo "Schedule: daily at ${HOUR}:$(printf '%02d' "$MINUTE")"
echo "Plist: ${PLIST}"
echo "Backups: ${BACKUP_DIR}"
echo "Logs: ${LOG_DIR}"
echo "Status: launchctl print gui/${UID_VALUE}/${LABEL}"
