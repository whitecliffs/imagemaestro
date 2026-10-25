"""Local-only Runpod control plane. No ML imports or provider SDK required."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.runpod.io/v2'
ACTIVE = {'PROVISIONING', 'STARTING', 'RUNNING', 'RESTARTING'}


class CloudError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def private_json(path: Path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + secrets.token_hex(6))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


class RunpodClient:
    def __init__(self, key):
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, method, path, body=None):
        request = urllib.request.Request(API + path, method=method,
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'},
            data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read(8 * 1024 * 1024)
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            # Never reflect provider payloads: responses can contain credentials/env values.
            messages = {401: 'Runpod rejected this API key.', 403: 'The API key lacks permission for this action.',
                        404: 'The Runpod resource no longer exists.', 409: 'GPU capacity or resource state changed. Refresh and retry.',
                        422: 'Runpod rejected this deployment configuration.', 429: 'Runpod rate limit reached. Wait before retrying.'}
            raise CloudError(messages.get(error.code, f'Runpod returned HTTP {error.code}. Check the Runpod console.'), error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise CloudError('Runpod could not be reached. Check the console before repeating a deployment.', 502) from None


class CloudManager:
    def __init__(self, root: Path, state_dir=None, client_factory=RunpodClient, clock=time.time):
        self.root = Path(root)
        self.directory = Path(state_dir or os.environ.get('IMAGEMAESTRO_CLOUD_STATE', Path.home() / '.config/imagemaestro/cloud'))
        self.config = read_json(self.root / 'cloud/config.json', {})
        self.state = read_json(self.directory / 'session.json', {})
        self.key = read_json(self.directory / 'credentials.json', {}).get('api_key', '')
        self.client_factory, self.clock = client_factory, clock
        self.lock = threading.RLock()
        self.quotes = {}
        self.last_error = ''

    def client(self):
        if not self.key:
            raise CloudError('Connect your Runpod account first.', 401)
        return self.client_factory(self.key)

    def save(self):
        private_json(self.directory / 'session.json', self.state)

    def settings(self):
        return {'connected': bool(self.key), 'signup_url': self.config.get('signup_url', 'https://runpod.io'),
                'referral': bool(urllib.parse.urlsplit(self.config.get('signup_url', '')).query),
                'image': os.environ.get('IMAGEMAESTRO_RUNPOD_IMAGE', self.config.get('image', '')),
                'default_gpu': self.config.get('default_gpu', 'NVIDIA RTX A6000')}

    def connect(self, key):
        if not isinstance(key, str) or not 12 <= len(key) <= 512 or any(c.isspace() for c in key):
            raise CloudError('Enter a valid Runpod API key.')
        with self.lock:
            if self.state.get('pod_id') or self.state.get('creation_unknown'):
                raise CloudError('Keep this account connected while its cloud session is tracked.', 409)
            self.client_factory(key).call('GET', '/pods?limit=1')
            private_json(self.directory / 'credentials.json', {'api_key': key})
            self.key = key
        return self.settings()

    def disconnect(self):
        with self.lock:
            if self.state.get('pod_id') or self.state.get('creation_unknown'):
                raise CloudError('Finish and release the tracked Pod before disconnecting.', 409)
            (self.directory / 'credentials.json').unlink(missing_ok=True)
            self.key = ''
        return self.settings()

    def catalog(self, cloud='SECURE'):
        if cloud not in {'SECURE', 'COMMUNITY'}:
            raise CloudError('Choose Secure or Community Cloud.')
        result = self.client().call('GET', '/catalog/gpus?' + urllib.parse.urlencode({'include': 'AVAILABILITY', 'product': 'POD', 'cloud': cloud}))
        items = []
        for gpu in result.get('gpus', []):
            if gpu.get('manufacturer', 'NVIDIA').upper() != 'NVIDIA' or not gpu.get(cloud.lower()):
                continue
            rate = gpu.get('price', {}).get(cloud.lower())
            if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
                continue
            quote = secrets.token_urlsafe(24)
            item = {'id': gpu['id'], 'name': gpu['name'], 'memory': gpu.get('memory'), 'hourly': rate,
                    'availability': gpu.get('availability', 'UNKNOWN'), 'quote': quote}
            self.quotes[quote] = {**item, 'cloud': cloud, 'expires': self.clock() + 300}
            items.append(item)
        self.quotes = {k: v for k, v in self.quotes.items() if v['expires'] > self.clock()}
        return {'gpus': sorted(items, key=lambda x: (x['id'] != self.settings()['default_gpu'], x['hourly'])), 'cloud': cloud}

    def volumes(self):
        volumes, cursor = [], ''
        for _ in range(100):
            query = '?' + urllib.parse.urlencode({'cursor': cursor}) if cursor else ''
            response = self.client().call('GET', '/network-volumes' + query)
            volumes.extend({k: v.get(k) for k in ('id', 'name', 'size', 'dataCenter')} for v in response.get('networkVolumes', []))
            pagination = response.get('pagination', {})
            if not pagination.get('hasNextPage'):
                return {'volumes': volumes}
            cursor = pagination.get('nextCursor')
            if not cursor:
                break
        raise CloudError('Could not finish listing storage volumes.', 502)

    def start(self, body):
        with self.lock:
            if self.state.get('pod_id') or self.state.get('creation_unknown'):
                raise CloudError('A session is already tracked. Release it before creating another.', 409)
            quote = self.quotes.get(body.get('quote'))
            if not quote or quote['expires'] < self.clock():
                raise CloudError('Pricing has expired. Refresh GPU prices before starting.', 409)
            if quote['availability'] == 'NONE':
                raise CloudError('This GPU is out of stock. Choose another GPU.', 409)
            if body.get('accept_charges') is not True:
                raise CloudError('Confirm the displayed usage charges before starting.')
            hours, idle = body.get('max_hours', 2), body.get('idle_minutes', 30)
            if type(hours) not in (float, int) or not math.isfinite(hours) or not 0.25 <= hours <= 24:
                raise CloudError('Session limit must be between 0.25 and 24 hours.')
            if type(idle) is not int or not 5 <= idle <= 120:
                raise CloudError('Idle shutdown must be between 5 and 120 minutes.')
            image = self.settings()['image']
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/:@-]{2,255}', image):
                raise CloudError('The publisher must configure the tested Runpod image before cloud deployment.', 409)
            volume_id = body.get('volume_id', '')
            if volume_id:
                volume = next((v for v in self.volumes()['volumes'] if v['id'] == volume_id), None)
                if not volume or quote['cloud'] != 'SECURE':
                    raise CloudError('Choose an existing network volume with Secure Cloud.')
                mounts = {'network': [{'volumeId': volume_id, 'path': '/workspace'}]}
            else:
                volume = None
                mounts = {'persistent': {'size': 100, 'path': '/workspace'}}
            token = secrets.token_urlsafe(48)
            name = 'imagemaestro-' + secrets.token_hex(8)
            payload = {'name': name, 'image': image, 'cloud': quote['cloud'],
                       'gpu': {'id': quote['id'], 'count': 1, 'minCudaVersion': '12.8'}, 'disk': 30, 'mounts': mounts,
                       'ports': ['8080/http'], 'startSsh': False, 'startJupyter': False,
                       'env': {'IMAGEMAESTRO_CLOUD_TOKEN': token, 'SERVER_NAME': '0.0.0.0', 'SERVER_PORT': '8080'}}
            if volume:
                payload['dataCenterIds'] = [volume['dataCenter']]
            # Write intent before POST. Never retry a possibly successful billable create.
            self.state = {'name': name, 'creation_unknown': True, 'token': token, 'started': self.clock(),
                          'deadline': self.clock() + hours * 3600, 'idle_seconds': idle * 60,
                          'quoted_hourly': quote['hourly'], 'network_volume': bool(volume), 'status': 'CREATING'}
            self.save()
            try:
                pod = self.client().call('POST', '/pods', payload)
            except CloudError as error:
                if error.status < 500 and error.status != 429:
                    self.state = {}
                    self.save()
                raise
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', str(pod.get('id', ''))):
                raise CloudError('Runpod returned an unexpected Pod ID. Check the console before continuing.', 502)
            self.state.update(pod_id=pod['id'], creation_unknown=False, status=pod.get('status', 'PROVISIONING'))
            self.save()
            return self.status(refresh=False)

    def remote(self, path):
        pod_id = self.state['pod_id']
        url = f'https://{pod_id}-8080.proxy.runpod.net' + path
        request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + self.state['token']})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=8) as response:
                return json.loads(response.read(1024 * 1024))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None

    def status(self, refresh=True):
        with self.lock:
            if refresh and self.state.get('pod_id'):
                try:
                    pod = self.client().call('GET', '/pods/' + self.state['pod_id'])
                except CloudError as error:
                    if error.status != 404:
                        raise
                    self.state.update(status='MISSING', ready=False)
                else:
                    self.state['status'] = pod.get('status', 'UNKNOWN')
                    if self.state['status'] in {'STOPPED', 'EXITED'}:
                        self.state.setdefault('stopped_at', self.clock())
                    rate = pod.get('cost')
                    if isinstance(rate, (int, float)) and math.isfinite(rate) and rate >= 0:
                        self.state['hourly'] = rate
                    if self.state['status'] == 'RUNNING':
                        runtime = self.remote('/cloud-runtime')
                        self.state['ready'] = bool(runtime and runtime.get('ready'))
                        if runtime:
                            self.state['busy'] = runtime.get('busy', True)
                            self.state['idle_for'] = runtime.get('idle_for', 0)
                    else:
                        self.state['ready'] = False
                self.save()
            public = {k: v for k, v in self.state.items() if k not in {'token', 'name'}}
            if self.state:
                elapsed = max(0, self.state.get('stopped_at', self.clock()) - self.state['started'])
                public['elapsed_seconds'] = elapsed
                public['estimated_compute_cost'] = round(elapsed / 3600 * self.state.get('hourly', self.state.get('quoted_hourly', 0)), 4)
            public['monitor_error'] = self.last_error
            return public

    def open_url(self):
        with self.lock:
            if not self.state.get('pod_id') or not self.state.get('ready') or self.state.get('status') != 'RUNNING':
                raise CloudError('Wait until the studio is ready.', 409)
            return {'url': f"https://{self.state['pod_id']}-8080.proxy.runpod.net/cloud-login#" + self.state['token']}

    def stop(self):
        with self.lock:
            if not self.state.get('pod_id'):
                raise CloudError('No tracked Pod to stop.', 409)
            if self.state.get('status') == 'MISSING':
                return self.status(refresh=False)
            self.client().call('POST', '/pods/' + self.state['pod_id'] + '/action', {'action': 'stop'})
            self.state.update(status='STOPPING', ready=False, stop_requested=self.clock())
            self.save()
            return self.status(refresh=False)

    def release(self, confirmed=False):
        with self.lock:
            if not confirmed:
                raise CloudError('Confirm that your outputs have been downloaded before releasing the Pod.')
            if not self.state.get('pod_id'):
                raise CloudError('No tracked Pod. For an uncertain create, reconcile it in the Runpod console.', 409)
            if self.state.get('status') not in {'STOPPED', 'EXITED', 'MISSING'}:
                raise CloudError('Stop the GPU and wait for Runpod to confirm it before releasing.', 409)
            if self.state.get('status') != 'MISSING':
                self.client().call('DELETE', '/pods/' + self.state['pod_id'])
            self.state = {}
            self.save()
            return {}

    def reconcile(self):
        with self.lock:
            if not self.state.get('creation_unknown'):
                return self.status()
            cursor = ''
            for _ in range(100):
                query = '?' + urllib.parse.urlencode({'cursor': cursor}) if cursor else ''
                result = self.client().call('GET', '/pods' + query)
                matches = [p for p in result.get('pods', []) if p.get('name') == self.state.get('name')]
                if matches:
                    if len(matches) != 1 or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', str(matches[0].get('id', ''))):
                        raise CloudError('Ambiguous deployment. Resolve it in the Runpod console.', 409)
                    self.state.update(pod_id=matches[0]['id'], creation_unknown=False, status=matches[0].get('status', 'UNKNOWN'))
                    self.save()
                    return self.status()
                page = result.get('pagination', {})
                if not page.get('hasNextPage'):
                    break
                cursor = page.get('nextCursor')
                if not cursor:
                    break
            raise CloudError('No matching Pod found yet. Check the Runpod console; do not repeat creation while its outcome is uncertain.', 409)

    def download_outputs(self):
        with self.lock:
            if not self.state.get('pod_id') or not self.state.get('ready'):
                raise CloudError('Open a running studio before downloading outputs.', 409)
            runtime = self.remote('/cloud-runtime')
            if not runtime or runtime.get('busy', True):
                raise CloudError('Wait until generation and downloads have finished before saving outputs.', 409)
            listing = self.remote('/api/v1/outputs?workspace=__all__&limit=0')
            if not listing or not isinstance(listing.get('outputs'), list):
                raise CloudError('Could not read the output gallery.', 502)
            pod_id, token = self.state['pod_id'], self.state['token']
        directory = Path.home() / 'Downloads' / 'ImageMaestro' / pod_id
        directory.mkdir(parents=True, exist_ok=True)
        count = 0
        for item in listing['outputs']:
            url = item.get('url', '')
            if not isinstance(url, str) or not url.startswith('/api/v1/file/') or urllib.parse.urlsplit(url).netloc:
                raise CloudError('Unexpected output URL. No files outside the gallery can be downloaded.', 502)
            name = Path(str(item.get('name', 'output'))).name
            name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)[:160].strip('.') or 'output'
            destination = directory / (hashlib.sha256(url.encode()).hexdigest()[:12] + '-' + name)
            if destination.exists():
                continue  # Completed downloads are never overwritten.
            temporary = destination.with_name(destination.name + '.' + secrets.token_hex(6) + '.partial')
            request = urllib.request.Request(f'https://{pod_id}-8080.proxy.runpod.net' + url, headers={'Authorization': 'Bearer ' + token})
            try:
                with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response, temporary.open('xb') as stream:
                    length = response.headers.get('Content-Length')
                    length = int(length) if length is not None else None
                    written = 0
                    while chunk := response.read(1024 * 1024):
                        written += len(chunk)
                        if written > 100 * 1024**3:
                            raise CloudError('An output exceeds the 100 GB download limit.')
                        stream.write(chunk)
                    if length is not None and written != length:
                        raise CloudError('An output download was incomplete. Retry before releasing the Pod.', 502)
                os.replace(temporary, destination)
                count += 1
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                raise CloudError('Output download failed. Existing completed files were preserved; retry before releasing.', 502) from None
            finally:
                temporary.unlink(missing_ok=True)
        return {'downloaded': count, 'directory': str(directory), 'total': len(listing['outputs'])}

    def tick(self):
        with self.lock:
            if not self.state.get('pod_id') or self.state.get('status') in {'STOPPING', 'STOPPED', 'EXITED', 'MISSING'}:
                return
            # Deadline must work even if the studio's health endpoint is unreachable.
            if self.clock() >= self.state['deadline']:
                self.stop()
                return
            status = self.status()
            if status.get('ready') and status.get('busy') is False and status.get('idle_for', 0) >= self.state['idle_seconds']:
                self.stop()

    def monitor(self, stopped):
        while not stopped.wait(15):
            try:
                self.tick()
                self.last_error = ''
            except Exception:
                self.last_error = 'Automatic shutdown could not reach Runpod. Check the console; charges may continue.'

    def dispatch(self, method, path, body=None):
        body = body or {}
        if method == 'GET' and path == '/api/cloud/settings': return self.settings()
        if method == 'POST' and path == '/api/cloud/connect': return self.connect(body.get('api_key'))
        if method == 'POST' and path == '/api/cloud/disconnect': return self.disconnect()
        if method == 'GET' and path.startswith('/api/cloud/catalog'):
            return self.catalog(urllib.parse.parse_qs(urllib.parse.urlsplit(path).query).get('cloud', ['SECURE'])[0])
        if method == 'GET' and path == '/api/cloud/volumes': return self.volumes()
        if method == 'GET' and path == '/api/cloud/session': return self.status()
        if method == 'POST' and path == '/api/cloud/start': return self.start(body)
        if method == 'POST' and path == '/api/cloud/reconcile': return self.reconcile()
        if method == 'POST' and path == '/api/cloud/download': return self.download_outputs()
        if method == 'POST' and path == '/api/cloud/open': return self.open_url()
        if method == 'POST' and path == '/api/cloud/stop': return self.stop()
        if method == 'POST' and path == '/api/cloud/release': return self.release(body.get('confirmed') is True)
        raise CloudError('Cloud endpoint not found.', 404)
