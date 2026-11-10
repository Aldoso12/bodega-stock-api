import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


API_KEY = os.environ["API_KEY"]
BALANCER_URL = os.environ.get("BALANCER_URL", "http://load-balancer").rstrip("/")
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


class GatewayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"gateway-ok\n")
            return

        if self.headers.get("X-API-Key") != API_KEY:
            self.send_error(401, "Invalid or missing API key")
            return

        request = urllib.request.Request(
            f"{BALANCER_URL}{self.path}",
            headers={"Accept": self.headers.get("Accept", "*/*")},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read()
                self.send_response(response.status)
                for name, value in response.headers.items():
                    if name.lower() not in HOP_BY_HOP_HEADERS:
                        self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as error:
            self.send_error(error.code, error.reason)
        except urllib.error.URLError:
            self.send_error(502, "Load balancer unavailable")

    def log_message(self, format, *args):
        return


ThreadingHTTPServer(("0.0.0.0", 8080), GatewayHandler).serve_forever()
