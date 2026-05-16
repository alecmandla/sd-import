#!/usr/bin/env bash
#
# Install mac-sd-photo-import on macOS.
#
#   ./install.sh
#
# Environment variables (optional):
#   SD_IMPORT_LABEL   launchd Label (default: com.user.sdimport)
#   SD_IMPORT_BIN     install dir for the script (default: ~/.local/bin)

set -euo pipefail

if [[ "${OSTYPE:-}" != darwin* ]]; then
    echo "Error: this tool is macOS-only (OSTYPE=$OSTYPE)" >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="${SD_IMPORT_LABEL:-com.user.sdimport}"
BIN_DIR="${SD_IMPORT_BIN:-$HOME/.local/bin}"
SCRIPT_PATH="$BIN_DIR/sd-import"
CONFIG_DIR="$HOME/.config/sd-photo-import"
CONFIG_FILE="$CONFIG_DIR/config.toml"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"

PYTHON=""
for candidate in /usr/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "Error: python3 not found. Install the Xcode Command Line Tools:" >&2
    echo "  xcode-select --install" >&2
    exit 1
fi

PY_VERSION="$($PYTHON -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"
if (( PY_MAJOR < 3 )) || { (( PY_MAJOR == 3 )) && (( PY_MINOR < 9 )); }; then
    echo "Error: need Python 3.9+, found $PY_VERSION at $PYTHON" >&2
    exit 1
fi

echo "==> Using $PYTHON ($PY_VERSION)"

echo "==> Installing Python dependencies (Pillow, exifread)"
if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
    "$PYTHON" -m ensurepip --user >/dev/null
fi
DEPS=(Pillow exifread)
if (( PY_MAJOR == 3 )) && (( PY_MINOR < 11 )); then
    DEPS+=(tomli)
fi
"$PYTHON" -m pip install --user --upgrade "${DEPS[@]}"

echo "==> Installing script to $SCRIPT_PATH"
mkdir -p "$BIN_DIR" "$LOG_DIR"
cp "$REPO_DIR/sd_import.py" "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"

echo "==> Setting up config at $CONFIG_FILE"
mkdir -p "$CONFIG_DIR"
if [[ -e "$CONFIG_FILE" ]]; then
    echo "    (config already exists, leaving it alone)"
else
    cp "$REPO_DIR/config.example.toml" "$CONFIG_FILE"
    echo "    (copied from config.example.toml)"
fi

echo "==> Writing launchd agent to $PLIST_PATH"
mkdir -p "$PLIST_DIR"
sed \
    -e "s|{{LABEL}}|$LABEL|g" \
    -e "s|{{HOME}}|$HOME|g" \
    -e "s|{{SCRIPT_PATH}}|$SCRIPT_PATH|g" \
    "$REPO_DIR/com.user.sdimport.plist.template" > "$PLIST_PATH"

echo "==> Loading launchd agent"
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

PATH_HINT=""
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) PATH_HINT="
Note: $BIN_DIR is not on your PATH. Add this to your shell rc file:
    export PATH=\"$BIN_DIR:\$PATH\"
You can still run the script directly: $SCRIPT_PATH" ;;
esac

cat <<EOF

Installed successfully.

  Script:  $SCRIPT_PATH
  Config:  $CONFIG_FILE
  Agent:   $PLIST_PATH
  Logs:    $LOG_DIR/sd-import.log

Try it: insert an SD card, then run
  $SCRIPT_PATH --dry-run

To uninstall: ./uninstall.sh
$PATH_HINT
EOF
