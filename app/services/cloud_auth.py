"""Whole-application authentication for a cloud Pod, including mounted UIs."""
import hashlib
import hmac
from http.cookies import SimpleCookie
import json
import time
from urllib.parse import urlsplit

LOGIN_HTML = b'''<!doctype html><html><head><meta name="referrer" content="no-referrer"><title>Connect ImageMaestro</title></head><body style="background:#131313;color:#eee;font:18px system-ui;padding:40px"><h1>ImageMaestro Cloud</h1><p id="status">Connecting securely...</p><script>
(async()=>{const token=location.hash.slice(1);history.replaceState(null,'','/cloud-login');if(!token){document.getElementById('status').textContent='Open this studio from your local ImageMaestro Cloud panel.';return;}try{const r=await fetch('/cloud-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});if(!r.ok)throw Error();location.replace('/');}catch{document.getElementById('status').textContent='Connection failed. Reopen from your local Cloud panel.';}})();
</script></body></html>'''


class CloudAuthMiddleware:
    def __init__(self, app, token, runtime=None):
        if len(token) < 32:
            raise RuntimeError('Cloud mode requires a strong per-session token.')
        self.app, self.token, self.runtime = app, token, runtime
        self.cookie = hmac.new(token.encode(), b'imagemaestro-browser-session', hashlib.sha256).hexdigest()
        self.last_activity = time.monotonic()

    async def reply(self, send, status, data, headers=None):
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            content_type = b'application/json'
        else:
            content_type = b'text/html; charset=utf-8'
        await send({'type': 'http.response.start', 'status': status, 'headers': [(b'content-type', content_type), (b'cache-control', b'no-store'), (b'referrer-policy', b'no-referrer'), (b'x-frame-options', b'DENY'), (b'x-content-type-options', b'nosniff')] + (headers or [])})
        await send({'type': 'http.response.body', 'body': data})

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        origin = headers.get(b'origin', b'').decode('latin1')
        host = headers.get(b'host', b'').decode('latin1')
        try:
            trusted = not origin or (urlsplit(origin).scheme in {'http', 'https'} and urlsplit(origin).netloc == host)
        except ValueError:
            trusted = False
        if not trusted:
            if scope['type'] == 'websocket':
                return await send({'type': 'websocket.close', 'code': 1008})
            return await self.reply(send, 403, {'error': 'Untrusted browser origin.'})
        path = scope['path']
        if scope['type'] == 'http' and path == '/cloud-login':
            if scope['method'] == 'GET':
                return await self.reply(send, 200, LOGIN_HTML)
            if scope['method'] == 'POST':
                body = b''
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    body += message.get('body', b'')
                    if len(body) > 4096:
                        return await self.reply(send, 413, {'error': 'Request too large.'})
                    if not message.get('more_body'):
                        break
                try:
                    candidate = json.loads(body).get('token', '')
                    valid = isinstance(candidate, str) and hmac.compare_digest(candidate.encode(), self.token.encode())
                except (ValueError, AttributeError):
                    valid = False
                if not valid:
                    return await self.reply(send, 401, {'error': 'Invalid session.'})
                self.last_activity = time.monotonic()
                cookie = f'__Host-imagemaestro={self.cookie}; Path=/; Secure; HttpOnly; SameSite=Strict'
                return await self.reply(send, 200, {'connected': True}, [(b'set-cookie', cookie.encode()), (b'set-cookie', b'imagemaestro-cloud-ui=1; Path=/; Secure; SameSite=Strict')])
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get(b'cookie', b'').decode('latin1'))
        except Exception:
            pass
        cookie = cookies.get('__Host-imagemaestro')
        bearer = headers.get(b'authorization', b'').decode('latin1')
        authenticated = hmac.compare_digest(bearer.encode(), ('Bearer ' + self.token).encode()) or (cookie is not None and hmac.compare_digest(cookie.value.encode(), self.cookie.encode()))
        if not authenticated:
            if scope['type'] == 'websocket':
                return await send({'type': 'websocket.close', 'code': 1008})
            return await self.reply(send, 401, {'error': 'Open this studio from your local Cloud GPU panel.'})
        if path == '/cloud-activity' and scope.get('method') == 'POST':
            self.last_activity = time.monotonic()
            return await self.reply(send, 200, {'active': True})
        if path == '/cloud-runtime' and scope['type'] == 'http':
            try:
                busy = self.runtime() if self.runtime else True
            except Exception:
                busy = True
            if busy:
                self.last_activity = time.monotonic()
            return await self.reply(send, 200, {'ready': True, 'busy': bool(busy), 'idle_for': max(0, time.monotonic() - self.last_activity)})
        if scope.get('method') in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            self.last_activity = time.monotonic()
        await self.app(scope, receive, send)
