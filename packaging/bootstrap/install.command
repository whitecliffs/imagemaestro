#!/bin/bash
set -euo pipefail
CLOUD_ONLY=0
for argument in "$@"; do [ "$argument" != "--cloud-only" ] || CLOUD_ONLY=1; done
SOURCE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) TARGET=linux-x86_64; INSTALL_ROOT="${IMAGEMAESTRO_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/ImageMaestro}" ;;
  Darwin-arm64) TARGET=macos-arm64; INSTALL_ROOT="${IMAGEMAESTRO_INSTALL_DIR:-$HOME/Library/Application Support/ImageMaestro}" ;;
  *) echo 'Supported targets: Linux x86_64 and macOS Apple Silicon.'; exit 1 ;;
esac
if [ "$CLOUD_ONLY" = 1 ] && [ -z "${IMAGEMAESTRO_INSTALL_DIR:-}" ]; then INSTALL_ROOT="$INSTALL_ROOT-Cloud"; fi
if [ "$(id -u)" = 0 ]; then echo 'Run this installer as your normal user, not root.'; exit 1; fi
# Packaged installers include the source. Never overwrite an existing installation.
if [ "$SOURCE_DIR" != "$INSTALL_ROOT" ]; then
  if [ -e "$INSTALL_ROOT" ]; then
    echo "Installation already exists: $INSTALL_ROOT. Run its packaging/bootstrap/install.command to repair, or choose IMAGEMAESTRO_INSTALL_DIR."
    exit 1
  fi
  mkdir -p "$(dirname "$INSTALL_ROOT")"
  cp -R "$SOURCE_DIR" "$INSTALL_ROOT"
fi
cd "$INSTALL_ROOT"
export MAMBA_ROOT_PREFIX="$INSTALL_ROOT/.mamba"
MAMBA="$INSTALL_ROOT/packaging/bootstrap/micromamba-$TARGET"
chmod +x "$MAMBA"
PACKAGES=(python=3.11 pip)
if [ "$CLOUD_ONLY" = 0 ]; then PACKAGES+=(ffmpeg); fi
if [ ! -x "$INSTALL_ROOT/runtime/bin/python" ] || { [ "$CLOUD_ONLY" = 0 ] && [ ! -x "$INSTALL_ROOT/runtime/bin/ffprobe" ]; }; then
  "$MAMBA" create --yes --prefix "$INSTALL_ROOT/runtime" --override-channels --channel conda-forge "${PACKAGES[@]}"
fi
export PATH="$INSTALL_ROOT/runtime/bin:$PATH"
python "$INSTALL_ROOT/install.py" "$@"
if [ "$CLOUD_ONLY" = 0 ]; then python "$INSTALL_ROOT/packaging/desktop.py" "$INSTALL_ROOT"; fi
echo "Installation completed. Use the ImageMaestro desktop launcher."
