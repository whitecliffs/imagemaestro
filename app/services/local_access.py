"""Protect the unauthenticated desktop server from hostile browser origins."""
import os
from urllib.parse import urlsplit


class LocalAccessMiddleware:
    def __init__(self, app):
        self.app = app
        host = os.environ.get("SERVER_NAME", "127.0.0.1").lower()
        self.hosts = {"localhost", "127.0.0.1", "::1"}
        if host not in {"0.0.0.0", "::"}:
            self.hosts.add(host)
        self.lan = host in {"0.0.0.0", "::"}

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        authority = headers.get(b"host", b"").decode("latin1").lower()
        try:
            hostname = urlsplit("//" + authority).hostname
            origin = headers.get(b"origin", b"").decode("latin1")
            parsed_origin = urlsplit(origin)
            trusted = (self.lan or hostname in self.hosts) and (
                not origin or (parsed_origin.scheme in {"http", "https"} and parsed_origin.netloc.lower() == authority)
            )
        except ValueError:
            trusted = False
        if not trusted:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                body = b"Untrusted host or browser origin"
                await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
