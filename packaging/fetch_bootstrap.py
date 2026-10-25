"""Fetch pinned micromamba executables and verify their recorded SHA-256."""
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request


def ensure_bootstraps():
    root = Path(__file__).resolve().parents[1]
    expected = {}
    for line in (root / 'packaging/bootstrap/SHA256SUMS').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        expected[Path(name).name] = digest
    for target, platform in [('linux-x86_64', 'linux-64'), ('macos-arm64', 'osx-arm64')]:
        binary = root / 'packaging/bootstrap' / ('micromamba-' + target)
        if not binary.exists():
            url = f'https://micro.mamba.pm/api/micromamba/{platform}/2.8.1'
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:bz2') as archive:
                executable = archive.extractfile('bin/micromamba').read()
            if hashlib.sha256(executable).hexdigest() != expected[binary.name]:
                raise RuntimeError('Bootstrap checksum mismatch: ' + target)
            binary.write_bytes(executable)
            binary.chmod(0o755)
        if hashlib.sha256(binary.read_bytes()).hexdigest() != expected[binary.name]:
            raise RuntimeError('Bootstrap checksum mismatch: ' + target)


if __name__ == '__main__':
    ensure_bootstraps()
