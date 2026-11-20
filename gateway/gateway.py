import hmac
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


API_KEY = os.environ["API_KEY"]
BALANCER_URL = os.environ.get("BALANCER_URL", "http://load-balancer").rstrip("/")


def positive_int_env(name, default):
    value = os.environ.get(name, str(default))
    try:
        parsed = int(value)
    except ValueError:
        raise RuntimeError(f"{name} must be a positive integer")
    if parsed <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return parsed


if not API_KEY:
    raise RuntimeError("API_KEY must not be empty")

RATE_LIMIT_REQUESTS = positive_int_env("RATE_LIMIT_REQUESTS", 300)
RATE_LIMIT_WINDOW_SECONDS = positive_int_env("RATE_LIMIT_WINDOW_SECONDS", 60)
MAX_BODY_BYTES = positive_int_env("GATEWAY_MAX_BODY_BYTES", 1_048_576)
UPSTREAM_TIMEOUT_SECONDS = positive_int_env("GATEWAY_UPSTREAM_TIMEOUT_SECONDS", 8)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
RESPONSE_HEADERS_TO_SKIP = HOP_BY_HOP_HEADERS | {"server", "date"}


class RateLimiter:
    def __init__(self, maximum, window_seconds):
        self.maximum = maximum
        self.window_seconds = window_seconds
        self.requests = {}
        self.lock = threading.Lock()

    def check(self, client_ip):
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self.lock:
            for ip, timestamps in list(self.requests.items()):
                while timestamps and timestamps[0] <= cutoff:
                    timestamps.popleft()
                if not timestamps:
                    del self.requests[ip]

            timestamps = self.requests.setdefault(client_ip, deque())
            if len(timestamps) >= self.maximum:
                retry_after = max(1, math.ceil(timestamps[0] + self.window_seconds - now))
                return False, retry_after
            timestamps.append(now)
            return True, None


RATE_LIMITER = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)


class GatewayHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, str(value))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "11")
            self.end_headers()
            self.wfile.write(b"gateway-ok\n")
            return
        self.handle_protected_request()

    def do_POST(self):
        self.handle_protected_request()

    def do_HEAD(self):
        self.send_method_not_allowed()

    def do_DELETE(self):
        self.send_method_not_allowed()

    def do_PATCH(self):
        self.send_method_not_allowed()

    def do_PUT(self):
        self.send_method_not_allowed()

    def do_OPTIONS(self):
        self.send_method_not_allowed()

    def send_method_not_allowed(self):
        self.send_json(
            405,
            {"error": "Metodo HTTP no permitido"},
            {"Allow": "GET, POST"},
        )

    def handle_protected_request(self):
        if not hmac.compare_digest(self.headers.get("X-API-Key", ""), API_KEY):
            self.send_json(401, {"error": "API Key ausente o invalida"})
            return

        allowed, retry_after = RATE_LIMITER.check(self.client_address[0])
        if not allowed:
            self.send_json(
                429,
                {"error": "Limite de solicitudes excedido"},
                {"Retry-After": retry_after},
            )
            return

        try:
            body = self.read_request_body()
        except GatewayRequestError as error:
            self.send_json(error.status, {"error": error.message})
            return

        headers = {}
        for header_name in ("Accept", "Content-Type"):
            header_value = self.headers.get(header_name)
            if header_value:
                headers[header_name] = header_value
        if body is not None:
            headers["Content-Length"] = str(len(body))
        request = urllib.request.Request(
            f"{BALANCER_URL}{self.path}",
            data=body if self.command == "POST" else None,
            headers=headers,
            method=self.command,
        )
        try:
            with urllib.request.urlopen(request, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
                self.relay_response(response)
        except urllib.error.HTTPError as error:
            self.relay_response(error)
        except (urllib.error.URLError, TimeoutError):
            self.send_json(502, {"error": "Balanceador no disponible"})

    def read_request_body(self):
        content_length = self.headers.get("Content-Length")
        if self.command != "POST":
            return None
        if self.headers.get("Transfer-Encoding"):
            raise GatewayRequestError(400, "Transfer-Encoding no soportado")
        if content_length is None:
            raise GatewayRequestError(400, "Content-Length es obligatorio")
        try:
            length = int(content_length)
        except ValueError:
            raise GatewayRequestError(400, "Content-Length invalido")
        if length < 0:
            raise GatewayRequestError(400, "Content-Length invalido")
        if length > MAX_BODY_BYTES:
            raise GatewayRequestError(413, "El cuerpo de la solicitud es demasiado grande")
        body = self.rfile.read(length)
        if len(body) != length:
            raise GatewayRequestError(400, "Cuerpo de solicitud incompleto")
        return body

    def relay_response(self, response):
        body = response.read()
        self.send_response(response.status)
        connection_headers = set()
        for value in response.headers.get_all("Connection", []):
            connection_headers.update(
                token.strip().lower()
                for token in value.split(",")
                if token.strip()
            )
        headers_to_skip = RESPONSE_HEADERS_TO_SKIP | connection_headers
        for name, value in response.headers.items():
            if name.lower() not in headers_to_skip:
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class GatewayRequestError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


ThreadingHTTPServer(("0.0.0.0", 8080), GatewayHandler).serve_forever()
