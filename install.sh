#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Installing Bookish Academic Automation Engine ==="

if ! command -v python3 &>/dev/null; then
    echo "Error: Python 3 is required but not installed." >&2
    exit 1
fi

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "[1/4] Creating virtual environment in .venv..."
    python3 -m venv "$SCRIPT_DIR/.venv"
else
    echo "[1/4] Virtual environment .venv already exists."
fi

echo "[2/4] Installing Python dependencies..."
"$SCRIPT_DIR/.venv/bin/pip" install -q --upgrade pip
"$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

echo "[3/4] Installing Playwright Chromium browser..."
"$SCRIPT_DIR/.venv/bin/playwright" install chromium

echo "[4/4] Setting up executable symlink..."
chmod +x "$SCRIPT_DIR/bookish"

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
ln -sf "$SCRIPT_DIR/bookish" "$BIN_DIR/bookish"

echo ""
echo "=== Installation Successful ==="
echo "You can now run 'bookish' from anywhere in your terminal."
