#!/usr/bin/env python3
"""Boot the published image on CPU and verify the authenticated app boundary."""
import argparse
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('image')
args = parser.parse_args()
token = secrets.token_urlsafe(48)
env = {**os.environ, 'IMAGEMAESTRO_CLOUD_TOKEN': token}
container = subprocess.check_output(['docker', 'run', '-d', '-e', 'IMAGEMAESTRO_CLOUD_TOKEN', '-p', '127.0.0.1::8080', args.image], env=env, text=True).strip()
try:
    port = subprocess.check_output(['docker', 'port', container, '8080'], text=True).strip().rsplit(':', 1)[1]
    base = 'http://127.0.0.1:' + port
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Running}}', container], text=True).strip() != 'true':
            raise RuntimeError('Container exited during startup')
        try:
            with urllib.request.urlopen(urllib.request.Request(base + '/cloud-runtime', headers={'Authorization': 'Bearer ' + token}), timeout=5) as response:
                if json.load(response).get('ready'):
                    break
        except (OSError, ValueError):
            time.sleep(2)
    else:
        raise RuntimeError('Container did not become ready within five minutes')
    for path in ['/', '/api/v1/models', '/classic/']:
        try:
            urllib.request.urlopen(base + path, timeout=5)
            raise AssertionError('Unauthenticated access was allowed: ' + path)
        except urllib.error.HTTPError as error:
            assert error.code == 401, (path, error.code)
        with urllib.request.urlopen(urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + token}), timeout=10) as response:
            assert response.status == 200, (path, response.status)
    request = urllib.request.Request(base + '/cloud-login', data=json.dumps({'token': token}).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        cookie = response.headers.get('Set-Cookie', '')
        assert all(flag in cookie for flag in ['__Host-', 'Secure', 'HttpOnly', 'SameSite=Strict'])
    print('PASS: image starts, UI/API/classic reject anonymous requests, bearer access works, secure login cookie is issued.')
except Exception:
    # The container never receives provider credentials; its logs contain no account key.
    subprocess.run(['docker', 'logs', '--tail', '100', container], check=False)
    raise
finally:
    subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, check=False)
