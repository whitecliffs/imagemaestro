"""Create a user-owned desktop launcher after installation succeeds."""
import os
from pathlib import Path
import shlex
import sys

root = Path(sys.argv[1]).resolve()
if '--cloud-only' not in sys.argv:
    launcher = root / 'ImageMaestro.command'
    launcher.write_text('#!/bin/bash\nset -e\nexport PATH=' + shlex.quote(str(root / 'runtime/bin')) + ':"$PATH"\nexec ' + shlex.quote(str(root / 'venv/bin/python')) + ' ' + shlex.quote(str(root / 'run.py')) + ' "$@"\n')
    launcher.chmod(0o755)
    if sys.platform == 'darwin':
        app = Path.home() / 'Applications/ImageMaestro.app/Contents'
        (app / 'MacOS').mkdir(parents=True, exist_ok=True)
        import plistlib
        (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleName': 'ImageMaestro', 'CFBundleIdentifier': 'local.imagemaestro.studio', 'CFBundleExecutable': 'ImageMaestro', 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '3.2.5'}))
        script = app / 'MacOS/ImageMaestro'
        script.write_text('#!/bin/bash\nexec /usr/bin/open -a Terminal ' + shlex.quote(str(launcher)) + '\n')
        script.chmod(0o755)
    else:
        target = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications/imagemaestro.desktop'
        target.parent.mkdir(parents=True, exist_ok=True)
        # Desktop entry quoting is not shell quoting; escape its reserved characters.
        escaped = str(launcher).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
        target.write_text('[Desktop Entry]\nType=Application\nName=ImageMaestro\nComment=Local AI creative studio\nExec="' + escaped + '"\nTerminal=true\nCategories=Graphics;AudioVideo;\n')
        target.chmod(0o755)

# Cloud mode deliberately uses the small runtime, never the ML virtual environment.
cloud_python = root / 'runtime/bin/python'
if not cloud_python.exists():
    cloud_python = Path(sys.executable)
cloud_launcher = root / 'ImageMaestro Cloud.command'
cloud_launcher.write_text('#!/bin/bash\nexec ' + shlex.quote(str(cloud_python)) + ' ' + shlex.quote(str(root / 'cloud_launcher.py')) + ' "$@"\n')
cloud_launcher.chmod(0o755)
if sys.platform == 'darwin':
    cloud_app = Path.home() / 'Applications/ImageMaestro Cloud.app/Contents'
    (cloud_app / 'MacOS').mkdir(parents=True, exist_ok=True)
    import plistlib
    (cloud_app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleName': 'ImageMaestro Cloud', 'CFBundleIdentifier': 'local.imagemaestro.cloud', 'CFBundleExecutable': 'ImageMaestroCloud', 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '3.2.5'}))
    script = cloud_app / 'MacOS/ImageMaestroCloud'
    script.write_text('#!/bin/bash\nexec /usr/bin/open -a Terminal ' + shlex.quote(str(cloud_launcher)) + '\n')
    script.chmod(0o755)
else:
    target = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications/imagemaestro-cloud.desktop'
    target.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(cloud_launcher).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    target.write_text('[Desktop Entry]\nType=Application\nName=ImageMaestro Cloud\nComment=Run ImageMaestro on a rented GPU\nExec="' + escaped + '"\nTerminal=true\nCategories=Graphics;AudioVideo;\n')
    target.chmod(0o755)
