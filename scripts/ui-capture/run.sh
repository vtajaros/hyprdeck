#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

export HKS_ROOT="$ROOT"
export HKS_BACKUP_DIR="$TMP_DIR/backups"
export HKS_SIDECAR_PATH="$TMP_DIR/sidecar.json"
export HKS_EDIT_DRYRUN_ONLY=1
export HKS_CAPTURE_DIR="$ROOT/scripts/ui-capture"
export QT_QPA_PLATFORM=offscreen

mkdir -p "$HKS_BACKUP_DIR"
cd "$ROOT"
quickshell -p "$ROOT/scripts/ui-capture/capture.qml"
