#!/usr/bin/env bash
# Build React/Vite UI for ImageMaestro
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/ui"

if ! command -v npm >/dev/null 2>&1; then
    echo "[!] Error: npm is not installed. Please install Node.js (v18+) and npm."
    exit 1
fi

echo "[*] Installing UI dependencies..."
npm install

echo "[*] Compiling TypeScript & Building Vite production bundle..."
npm run build

echo "[✓] UI built successfully! Assets are ready in ui/dist/."
