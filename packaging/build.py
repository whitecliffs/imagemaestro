#!/usr/bin/env python3
"""Build self-extracting Linux and Apple Silicon online installers from source."""
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import zipfile
from fetch_bootstrap import ensure_bootstraps

ensure_bootstraps()

root = Path(__file__).resolve().parents[1]
out = root / 'dist-installers'
out.mkdir(exist_ok=True)
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
extra = ['cloud_launcher.py', '.dockerignore', 'app/services/runpod_cloud.py', 'app/services/cloud_auth.py', 'tests/test_runpod_cloud.py', 'docs/RUNPOD_CLOUD.md', 'constraints.txt', 'app/services/local_access.py', 'packaging/desktop.py', 'packaging/build.py', 'packaging/fetch_bootstrap.py', 'packaging/bootstrap/install.command', 'packaging/bootstrap/SHA256SUMS', 'tests/test_standalone_setup.py', 'docs/STANDALONE_REVIEW.md', 'docs/backend-advisories.json']
files = sorted({p for p in tracked + extra if p and (root / p).is_file() and not p.startswith(('legacy_pinokio/', '.github/'))})
files += [str(p.relative_to(root)) for directory in ['cloud', 'ui/dist', 'packaging/bootstrap/licenses'] for p in (root / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
for platform, binary in [('linux-x86_64', 'micromamba-linux-x86_64'), ('macos-arm64', 'micromamba-macos-arm64')]:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as archive:
        for name in sorted(set(files + ['packaging/bootstrap/' + binary])):
            archive.add(root / name, arcname='ImageMaestro/' + name, recursive=False)
    payload = buf.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    header = '''#!/bin/bash
set -euo pipefail
SELF="$0"
if [ "${1:-}" = "--verify" ]; then VERIFY_ONLY=1; shift; else VERIFY_ONLY=0; fi
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/imagemaestro.XXXXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
LINE=$(awk '/^__IMAGEMAESTRO_PAYLOAD__$/ {print NR + 1; exit}' "$SELF")
tail -n +"$LINE" "$SELF" > "$TMP_DIR/payload.tar.gz"
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL=$(sha256sum "$TMP_DIR/payload.tar.gz" | cut -d ' ' -f 1)
else
  ACTUAL=$(shasum -a 256 "$TMP_DIR/payload.tar.gz" | cut -d ' ' -f 1)
fi
[ "$ACTUAL" = "DIGEST" ] || { echo 'Installer checksum failed'; exit 1; }
if [ "$VERIFY_ONLY" = 1 ]; then echo 'Installer payload verified'; exit 0; fi
tar -xzf "$TMP_DIR/payload.tar.gz" -C "$TMP_DIR"
"$TMP_DIR/ImageMaestro/packaging/bootstrap/install.command" "$@"
exit 0
__IMAGEMAESTRO_PAYLOAD__
'''.replace('DIGEST', digest)
    suffix = '.run' if platform.startswith('linux') else '.command'
    for cloud_only in (False, True):
        name = 'ImageMaestro-Cloud' if cloud_only else 'ImageMaestro'
        artifact = out / (name + '-3.2.5-' + platform + suffix)
        edition_header = header.replace('install.command" "$@"', 'install.command" --cloud-only "$@"') if cloud_only else header
        artifact.write_bytes(edition_header.encode() + payload)
        artifact.chmod(0o755)
        if platform.startswith('macos'):
            with zipfile.ZipFile(str(artifact) + '.zip', 'w', zipfile.ZIP_STORED) as z:
                z.write(artifact, artifact.name)
        print(artifact)
artifacts = sorted(p for p in out.iterdir() if p.is_file() and p.name != 'SHA256SUMS')
(out / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in artifacts))
