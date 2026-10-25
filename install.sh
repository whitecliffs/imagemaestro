#!/usr/bin/env bash
# ImageMaestro Standalone Shell Installer
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check Python availability
PYTHON_CMD=""
for cmd in python3 python3.11 python3.12 python3.10 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[!] Error: Python 3 is required but not found in PATH."
    echo "    Please install Python 3.10, 3.11, or 3.12."
    exit 1
fi

echo "[*] Using Python: $($PYTHON_CMD --version)"
exec "$PYTHON_CMD" "$SCRIPT_DIR/install.py" "$@"
