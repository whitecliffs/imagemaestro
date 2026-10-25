#!/usr/bin/env python3
"""Launch the cloud control panel using only Python's standard library."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'app'))
from services.runpod_cloud import CloudError, CloudManager


class CloudHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Never log query strings, secrets or session links.

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def reply(self, status, data, content_type='application/json'):
        body = json.dumps(data).encode() if content_type == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-ImageMaestro-Cloud', '1')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def handle_request(self):
        authority = self.headers.get('Host', '')
        try:
            expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if authority not in expected or (self.headers.get('Origin') and self.headers['Origin'] != 'http://' + authority):
                raise CloudError('Untrusted browser origin or host.', 403)
            path = self.path
            if path == '/':
                self.send_response(302)
                self.send_header('Location', '/cloud')
                self.end_headers()
                return
            if path.startswith('/api/cloud/'):
                body = None
                if self.command == 'POST':
                    if self.headers.get('X-ImageMaestro-Cloud') != '1':
                        raise CloudError('Missing cloud request header.', 403)
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 4096:
                        raise CloudError('Invalid request size.', 413)
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict):
                        raise CloudError('Expected a JSON object.')
                return self.reply(200, self.server.manager.dispatch(self.command, path, body))
            if self.command != 'GET':
                raise CloudError('Method not allowed.', 405)
            dist = ROOT / 'ui/dist'
            relative = 'index.html' if urlsplit(path).path in {'/', '/cloud', '/cloud/'} else urlsplit(path).path.lstrip('/')
            target = (dist / relative).resolve()
            if not target.is_relative_to(dist.resolve()) or not target.is_file():
                raise CloudError('File not found.', 404)
            return self.reply(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        except CloudError as error:
            self.reply(error.status, {'error': str(error)})
        except (ValueError, TypeError):
            self.reply(400, {'error': 'Invalid JSON request.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply(500, {'error': 'Cloud control failed. Your Pod may still be running; check the Runpod console.'})


def make_server(port=7870, manager=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), CloudHandler)
    server.manager = manager or CloudManager(ROOT)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='ImageMaestro Cloud GPU launcher (no local ML dependencies)')
    parser.add_argument('--port', type=int, default=7870)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = make_server(args.port)
    except OSError:
        import urllib.request
        try:
            url = f'http://127.0.0.1:{args.port}'
            with urllib.request.urlopen(url + '/api/cloud/settings', timeout=2) as response:
                if response.headers.get('X-ImageMaestro-Cloud') != '1':
                    raise ValueError('Another application owns this port')
            print('Cloud control is already running: ' + url + '/cloud')
            if not args.no_browser:
                webbrowser.open(url + '/cloud')
            return
        except Exception:
            raise SystemExit('The cloud launcher port is occupied. Choose another --port.')
    # One control plane owns the persisted session, even across multiple local windows.
    import fcntl
    server.manager.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (server.manager.directory / 'launcher.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Cloud control is already running. Reopen its existing browser tab.')
    stopped = threading.Event()
    threading.Thread(target=server.manager.monitor, args=(stopped,), daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/cloud'
    print(f'ImageMaestro Cloud: {url}\nKeep this process and machine online for automatic shutdown. Closing it does not stop a billed Pod.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        server.server_close()
        if server.manager.state.get('pod_id'):
            print('A Pod is still tracked. Verify it is stopped in https://console.runpod.io/pods before leaving.')


if __name__ == '__main__':
    main()
