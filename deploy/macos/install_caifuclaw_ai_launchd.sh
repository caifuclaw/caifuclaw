#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LABEL="com.caifuclaw-ai.watchdog"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
WATCHDOG="${ROOT}/deploy/macos/caifuclaw_ai_watchdog.sh"
UID_VALUE="$(id -u)"
LEGACY_LABELS=(
  "com.caifuclaw-erp.watchdog"
  "com.caifuclaw-erp.connector-runtime-api"
  "com.caifuclaw-erp.caifuclaw-business-api"
  "com.caifuclaw-erp.caifuclaw-business-frontend"
)

mkdir -p "${HOME}/Library/LaunchAgents" "${ROOT}/logs/watchdog"
chmod +x "$WATCHDOG"

for legacy_label in "${LEGACY_LABELS[@]}"; do
  launchctl bootout "gui/${UID_VALUE}/${legacy_label}" >/dev/null 2>&1 || true
  launchctl remove "$legacy_label" >/dev/null 2>&1 || true
  rm -f "${HOME}/Library/LaunchAgents/${legacy_label}.plist"
done

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
    <string>${WATCHDOG}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${ROOT}/logs/watchdog/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/logs/watchdog/launchd.err.log</string>
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

launchctl bootout "gui/${UID_VALUE}" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST"
launchctl kickstart -k "gui/${UID_VALUE}/${LABEL}"

echo "Installed ${LABEL}"
echo "Plist: ${PLIST}"
echo "Status: launchctl print gui/${UID_VALUE}/${LABEL}"
echo "Logs: ${ROOT}/logs/watchdog/watchdog.log"
