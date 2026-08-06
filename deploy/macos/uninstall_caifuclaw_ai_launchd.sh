#!/usr/bin/env bash
# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

set -euo pipefail

LABELS=("com.caifuclaw-ai.watchdog" "com.caifuclaw-erp.watchdog")
UID_VALUE="$(id -u)"

for label in "${LABELS[@]}"; do
  plist="${HOME}/Library/LaunchAgents/${label}.plist"
  launchctl bootout "gui/${UID_VALUE}" "$plist" >/dev/null 2>&1 || true
  launchctl remove "$label" >/dev/null 2>&1 || true
  rm -f "$plist"
  echo "Uninstalled ${label}"
done
