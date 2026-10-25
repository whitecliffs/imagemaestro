import asyncio
import copy
from http.client import HTTPConnection
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'app')]
from services.runpod_cloud import CloudError, CloudManager
from services.cloud_auth import CloudAuthMiddleware
from cloud_launcher import make_server


class FakeRunpod:
    def __init__(self):
        self.calls = []
        self.pod = None
        self.fail_create = False
    def __call__(self, key):
        self.key = key
        return self
    def call(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path.startswith('/catalog/gpus'):
            return {'gpus': [{'id': 'NVIDIA RTX A6000', 'name': 'RTX A6000', 'manufacturer': 'NVIDIA', 'memory': 48, 'secure': True, 'community': True, 'price': {'secure': .59, 'community': .33}, 'availability': 'HIGH'}]}
        if path == '/network-volumes':
            return {'networkVolumes': [{'id': 'vol123', 'name': 'Models', 'size': 200, 'dataCenter': 'EU-1'}]}
        if path.startswith('/pods?') or (path == '/pods' and method == 'GET'):
            return {'pods': [self.pod] if self.pod else []}
        if method == 'POST' and path == '/pods':
            self.pod = {'id': 'pod123', 'name': body['name'], 'status': 'RUNNING', 'cost': .59}
            if self.fail_create:
                raise CloudError('Request timed out', 502)
            return self.pod
        if method == 'POST' and path.endswith('/action'):
            self.pod['status'] = 'EXITED'
            return self.pod
        if method == 'DELETE':
            self.pod = None
            return {}
        if path == '/pods/pod123':
            return self.pod
        raise AssertionError((method, path, body))


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'cloud').mkdir()
        (self.root / 'cloud/config.json').write_text(json.dumps({'image': 'ghcr.io/example/imagemaestro@sha256:' + 'a'*64, 'signup_url': 'https://runpod.io?ref=test'}))
        self.provider = FakeRunpod()
        self.now = 1000
        self.manager = CloudManager(self.root, self.root / 'state', self.provider, lambda: self.now)
        self.manager.connect('test-key-for-local-mocked-provider')
        self.manager.remote = lambda path: {'ready': True, 'busy': False, 'idle_for': 0}
    def tearDown(self):
        self.temp.cleanup()
    def start(self, **extra):
        quote = self.manager.catalog()['gpus'][0]['quote']
        return self.manager.start({'quote': quote, 'accept_charges': True, **extra})
    def test_credentials_private_and_never_returned(self):
        self.assertEqual(os.stat(self.root / 'state/credentials.json').st_mode & 0o777, 0o600)
        self.assertNotIn('test-key', json.dumps(self.manager.settings()))
    def test_create_is_authenticated_and_does_not_send_account_key(self):
        result = self.start(volume_id='vol123')
        body = next(c[2] for c in self.provider.calls if c[:2] == ('POST', '/pods'))
        self.assertEqual(body['gpu'], {'id': 'NVIDIA RTX A6000', 'count': 1, 'minCudaVersion': '12.8'})
        self.assertEqual(body['dataCenterIds'], ['EU-1'])
        self.assertEqual(body['ports'], ['8080/http'])
        self.assertNotIn('RUNPOD_API_KEY', body['env'])
        self.assertGreaterEqual(len(body['env']['IMAGEMAESTRO_CLOUD_TOKEN']), 32)
        self.assertNotIn('token', result)
        self.assertNotIn(self.provider.key, json.dumps(body))
    def test_double_start_cannot_create_duplicate_pod(self):
        self.start()
        with self.assertRaises(CloudError): self.start()
        self.assertEqual(sum(c[:2] == ('POST', '/pods') for c in self.provider.calls), 1)
    def test_expired_quote_rejected(self):
        quote = self.manager.catalog()['gpus'][0]['quote']
        self.now += 301
        with self.assertRaises(CloudError): self.manager.start({'quote': quote, 'accept_charges': True})
    def test_charge_confirmation_required(self):
        quote = self.manager.catalog()['gpus'][0]['quote']
        with self.assertRaises(CloudError): self.manager.start({'quote': quote})
    def test_timeout_intent_survives_restart_and_is_reconciled(self):
        self.provider.fail_create = True
        with self.assertRaises(CloudError): self.start()
        restarted = CloudManager(self.root, self.root / 'state', self.provider, lambda: self.now)
        restarted.remote = self.manager.remote
        with self.assertRaises(CloudError): restarted.start({})
        self.assertEqual(restarted.reconcile()['pod_id'], 'pod123')
        self.assertFalse(restarted.state['creation_unknown'])
    def test_stop_preserves_disk_and_release_requires_confirmation(self):
        self.start()
        self.manager.stop()
        self.manager.status()
        self.assertFalse(any(c[0] == 'DELETE' for c in self.provider.calls))
        with self.assertRaises(CloudError): self.manager.release()
        self.manager.release(True)
        self.assertEqual(self.manager.state, {})
    def test_session_deadline_stops_even_when_health_unreachable(self):
        self.start(max_hours=.25)
        self.manager.remote = lambda _: None
        self.now += 901
        self.manager.tick()
        self.assertEqual(self.manager.state['status'], 'STOPPING')
    def test_idle_shutdown_respects_busy_jobs(self):
        self.start()
        self.manager.remote = lambda _: {'ready': True, 'busy': True, 'idle_for': 99999}
        self.manager.tick()
        self.assertEqual(self.manager.state['status'], 'RUNNING')
        self.manager.remote = lambda _: {'ready': True, 'busy': False, 'idle_for': 99999}
        self.manager.tick()
        self.assertEqual(self.manager.state['status'], 'STOPPING')
    def test_unknown_health_does_not_trigger_idle_stop(self):
        self.start()
        self.manager.remote = lambda _: None
        self.manager.tick()
        self.assertEqual(self.manager.state['status'], 'RUNNING')
    def test_cannot_disconnect_account_with_tracked_pod(self):
        self.start()
        with self.assertRaises(CloudError): self.manager.disconnect()
    def test_missing_image_blocks_deployment(self):
        self.manager.config['image'] = ''
        with self.assertRaises(CloudError): self.start()
        self.assertFalse(any(c[:2] == ('POST', '/pods') for c in self.provider.calls))
    def test_download_rejects_external_urls(self):
        self.start(); self.manager.status()
        self.manager.remote = lambda path: ({'ready': True, 'busy': False} if path == '/cloud-runtime' else {'outputs': [{'url': 'https://evil.example/file', 'name': '../secret'}]})
        with patch.dict(os.environ, {'HOME': str(self.root)}):
            with self.assertRaises(CloudError): self.manager.download_outputs()
    def test_download_is_atomic_and_sanitizes_names(self):
        self.start(); self.manager.status()
        self.manager.remote = lambda path: ({'ready': True, 'busy': False} if path == '/cloud-runtime' else {'outputs': [{'url': '/api/v1/file/video.mp4', 'name': '../../video.mp4'}]})
        stream = io.BytesIO(b'video'); stream.headers = {'Content-Length': '5'}
        opener = unittest.mock.Mock(); opener.open.return_value = stream
        with patch.dict(os.environ, {'HOME': str(self.root)}), patch('urllib.request.build_opener', return_value=opener):
            result = self.manager.download_outputs()
        files = list((self.root / 'Downloads/ImageMaestro/pod123').iterdir())
        self.assertEqual(result['downloaded'], 1)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), b'video')
        self.assertNotIn('..', files[0].name)
    def test_truncated_output_leaves_no_completed_file(self):
        self.start(); self.manager.status()
        self.manager.remote = lambda path: ({'ready': True, 'busy': False} if path == '/cloud-runtime' else {'outputs': [{'url': '/api/v1/file/video.mp4', 'name': 'video.mp4'}]})
        stream = io.BytesIO(b'short'); stream.headers = {'Content-Length': '100'}
        opener = unittest.mock.Mock(); opener.open.return_value = stream
        with patch.dict(os.environ, {'HOME': str(self.root)}), patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaises(CloudError): self.manager.download_outputs()
        self.assertEqual(list((self.root / 'Downloads/ImageMaestro/pod123').iterdir()), [])

    def test_stopped_cost_does_not_keep_growing(self):
        self.start(); self.now += 3600; self.manager.stop(); self.manager.status()
        first = self.manager.status(False)['estimated_compute_cost']
        self.now += 3600
        self.assertEqual(self.manager.status(False)['estimated_compute_cost'], first)


class AuthTests(unittest.TestCase):
    def request(self, path='/', method='GET', headers=None, body=None, kind='http'):
        async def run():
            async def app(scope, receive, send):
                await send({'type': 'http.response.start', 'status': 200, 'headers': []})
                await send({'type': 'http.response.body', 'body': b'protected'})
            messages = []
            async def send(message): messages.append(message)
            async def receive(): return {'type': 'http.request', 'body': json.dumps(body or {}).encode()}
            middleware = CloudAuthMiddleware(app, 't'*48, runtime=lambda: False)
            await middleware({'type': kind, 'method': method, 'path': path, 'headers': [(b'host', b'pod.proxy.runpod.net')] + (headers or [])}, receive, send)
            return messages
        return asyncio.run(run())
    def test_entire_app_and_classic_protected(self):
        for path in ['/', '/classic/', '/api/v1/models', '/assets/app.js']:
            self.assertEqual(self.request(path)[0]['status'], 401)
    def test_login_cookie_secure_httponly_samesite(self):
        response = self.request('/cloud-login', 'POST', body={'token': 't'*48})[0]
        self.assertEqual(response['status'], 200)
        cookie = next(v for k,v in response['headers'] if k == b'set-cookie')
        for flag in [b'__Host-', b'Secure', b'HttpOnly', b'SameSite=Strict']: self.assertIn(flag, cookie)
    def test_wrong_password_and_cross_origin_rejected(self):
        self.assertEqual(self.request('/cloud-login', 'POST', body={'token':'bad'})[0]['status'], 401)
        self.assertEqual(self.request('/cloud-login', 'POST', [(b'origin', b'https://evil.example')], {'token':'t'*48})[0]['status'], 403)
    def test_bearer_runtime_and_websocket_auth(self):
        self.assertEqual(self.request('/cloud-runtime', headers=[(b'authorization', b'Bearer '+ b't'*48)])[0]['status'], 200)
        self.assertEqual(self.request(kind='websocket')[0]['code'], 1008)


class LocalHTTPTests(unittest.TestCase):
    def test_real_http_origin_and_csrf_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = CloudManager(ROOT, folder)
            server = make_server(0, manager)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                connection = HTTPConnection('127.0.0.1', server.server_port)
                connection.request('GET', '/api/cloud/settings')
                response = connection.getresponse(); self.assertEqual(response.status, 200); response.read()
                connection.request('POST', '/api/cloud/connect', '{}', {'Content-Type':'application/json'})
                response=connection.getresponse(); self.assertEqual(response.status,403); response.read()
                connection.request('GET', '/api/cloud/settings', headers={'Host':'evil.example'})
                response=connection.getresponse(); self.assertEqual(response.status,403); response.read()
                connection.close()
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
