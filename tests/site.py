"""A tiny in-process web site served with http.server, for offline tests."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Tuple


class Site:
    """Routes map a path to ``(status, content_type, body[, extra_headers])``."""

    def __init__(self, routes: Dict[str, tuple], latency: float = 0.0):
        self.routes = routes
        self.latency = latency
        self.requests: List[Tuple[str, float, str]] = []  # (path, monotonic time, user agent)
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0
        site = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):  # keep test output quiet
                pass

            def do_GET(self):
                with site._lock:
                    site.requests.append((self.path, time.monotonic(), self.headers.get("User-Agent", "")))
                    site._in_flight += 1
                    site.max_in_flight = max(site.max_in_flight, site._in_flight)
                try:
                    if site.latency:
                        time.sleep(site.latency)
                    route = site.routes.get(self.path)
                    if route is None:
                        status, ctype, body, headers = 404, "text/html", "<h1>not found</h1>", {}
                    else:
                        status, ctype, body = route[:3]
                        headers = route[3] if len(route) > 3 else {}
                    data = body.encode() if isinstance(body, str) else body
                    self.send_response(status)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(data)
                finally:
                    with site._lock:
                        site._in_flight -= 1

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    @property
    def netloc(self) -> str:
        return f"127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self) -> "Site":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def paths(self) -> List[str]:
        return [p for p, _, _ in self.requests]

    def count(self, path: str) -> int:
        return self.paths().count(path)


def html(*links: str, title: str = "page", extra: str = "") -> tuple:
    anchors = "".join(f'<a href="{href}">link</a>' for href in links)
    return 200, "text/html; charset=utf-8", f"<html><head><title>{title}</title></head><body>{extra}{anchors}</body></html>"
