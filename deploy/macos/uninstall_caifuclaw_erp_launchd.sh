#!/usr/bin/env bash
# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/uninstall_caifuclaw_ai_launchd.sh" "$@"
