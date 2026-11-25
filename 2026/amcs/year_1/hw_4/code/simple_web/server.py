#!/usr/bin/env python3
"""Простейший HTTP-сервер для уровней на 6 и 8. Только стандартная библиотека."""

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        name = os.getenv("INSTANCE_NAME") or socket.gethostname()
        if path == "/":
            status, data = 200, {"message": f"Hello from {name}", "hostname": name}
        elif path == "/health":
            status, data = 200, {"status": "ok", "hostname": name}
        else:
            status, data = 404, {"error": "not_found"}

        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    address = (os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8080")))
    server = ThreadingHTTPServer(address, Handler)
    print(f"Listening on {address[0]}:{address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
