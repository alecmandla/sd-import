#!/usr/bin/env bash
#
# Uninstall mac-sd-photo-import.
#
#   ./uninstall.sh
#
# Leaves config and logs in place so reinstalling preserves your settings
# and history. Paths are printed at the end if you want to delete them.

set -euo pipefail

LABEL="${SD_IMPORT_LABEL:-com.user.sdimport}"
BIN_DIR="${SD_IMPORT_BIN:-$HOME/.local/bin}"
SCRIPT_PATH="$BIN_DIR/sd-import"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
CONFIG_FILE="$HOME/.config/sd-photo-import/config.toml"
LOG_FILE="$HOME/Library/Logs/sd-import.log"

if [[ -e "$PLIST_PATH" ]]; then
    echo "==> Unloading launchd agent"
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    echo "==> Removing $PLIST_PATH"
    rm -f "$PLIST_PATH"
else
    echo "    (no launchd agent at $PLIST_PATH)"
fi

if [[ -e "$SCRIPT_PATH" ]]; then
    echo "==> Removing $SCRIPT_PATH"
    rm -f "$SCRIPT_PATH"
else
    echo "    (no script at $SCRIPT_PATH)"
fi

cat <<EOF

Uninstalled.

Left in place (delete manually if you want):
  Config: $CONFIG_FILE
  Logs:   $LOG_FILE (and sd-import.stdout.log / sd-import.stderr.log)

Python packages Pillow and exifread were left installed — they were
installed via pip --user and may be used by other tools.
EOF
