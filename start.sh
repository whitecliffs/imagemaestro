#!/usr/bin/env bash
# ImageMaestro Standalone Shell Launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ -d "$SCRIPT_DIR/venv" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv/bin/python"
else
    # Fallback to system Python if no venv yet
    for cmd in python3 python3.11 python3.12 python3.10 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            PYTHON_CMD="$cmd"
            break
        fi
    done
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "[!] Error: Python not found."
    exit 1
fi

exec "$PYTHON_CMD" "$SCRIPT_DIR/run.py" "$@"
