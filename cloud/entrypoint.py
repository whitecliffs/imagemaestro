"""Prepare persistent user data and start the authenticated GPU studio."""
import os
from pathlib import Path
import pwd
import shutil
import sys

ROOT = Path('/opt/imagemaestro')
APP = ROOT / 'app'
DATA = Path('/workspace/imagemaestro')
if len(os.environ.get('IMAGEMAESTRO_CLOUD_TOKEN', '')) < 32:
    raise SystemExit('Refusing cloud startup: missing strong session authentication.')
if DATA.is_symlink():
    raise SystemExit('Refusing to use a symlink as the persistent application directory.')
DATA.mkdir(parents=True, exist_ok=True)
if os.getuid() == 0:
    account = pwd.getpwnam('maestro')
    # New application data is created after dropping privileges. Never recursively
    # change ownership on an existing/shared network volume.
    os.chown(DATA, account.pw_uid, account.pw_gid, follow_symlinks=False)
    os.initgroups(account.pw_name, account.pw_gid)
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    os.environ['HOME'] = account.pw_dir
# Every writable app file, including imported model definitions, is retained on the
# volume. Source files are refreshed from the image without deleting user-only files.
workspace_app = DATA / 'app'
shutil.copytree(APP, workspace_app, dirs_exist_ok=True)
cache = DATA / 'cache'
cache.mkdir(exist_ok=True)
os.environ['HF_HOME'] = str(cache / 'huggingface')
os.environ['XDG_CACHE_HOME'] = str(cache)
os.environ['IMAGEMAESTRO_CLOUD_REQUIRED'] = '1'
os.environ['SERVER_NAME'] = '0.0.0.0'
os.environ['SERVER_PORT'] = '8080'
# UI path is resolved relative to app/, just like a local installation.
ui_link = DATA / 'ui'
if not ui_link.exists():
    ui_link.symlink_to(ROOT / 'ui', target_is_directory=True)
os.chdir(workspace_app)
os.execv(sys.executable, [sys.executable, 'launch.py'])
