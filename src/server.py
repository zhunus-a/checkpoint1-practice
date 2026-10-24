"""The notes service: a very small HTTP API that keeps the M1 contract."""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

NOTES = ["alpha", "beta", "gamma"]
HOST = "0.0.0.0"  # every interface, so the service can be reached from outside a container


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, "ok")
        elif self.path == "/":
            self._send(200, "notes service")
        elif self.path == "/notes":
            self._send(200, str(len(NOTES) - 1))
        elif self.path == "/notes/first":
            self._send(200, NOTES[0])
        elif self.path == "/notes/latest":
            self._send(200, NOTES[-1])
        else:
            self._send(404, "not found")

    def _send(self, code, text):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def make_server(port):
    return HTTPServer((HOST, port), Handler)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"notes service listening on {HOST}:{port}", flush=True)
    make_server(port).serve_forever()
