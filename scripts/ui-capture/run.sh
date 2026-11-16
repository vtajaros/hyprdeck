#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

source "$ROOT/scripts/lib-hyprdeck-env.sh"

hyprdeck_env_export_pair ROOT "$ROOT"
hyprdeck_env_export_pair BACKUP_DIR "$TMP_DIR/backups"
hyprdeck_env_export_pair SIDECAR_PATH "$TMP_DIR/sidecar.json"
hyprdeck_env_export_pair EDIT_DRYRUN_ONLY "1"
hyprdeck_env_export_pair CAPTURE_DIR "$ROOT/scripts/ui-capture"
export QT_QPA_PLATFORM=offscreen

mkdir -p "$HYPRDECK_BACKUP_DIR"
cd "$ROOT"
quickshell -p "$ROOT/scripts/ui-capture/capture.qml"
