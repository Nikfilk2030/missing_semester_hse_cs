"""Учебный HTTP-сервис. Дорогой студент, не меняй, пожалуйста, этот файл. Мы проверим."""

import json
import logging
import os
from pathlib import Path
import socket
import sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class SQLiteCounter:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS counter "
                "(id INTEGER PRIMARY KEY CHECK (id = 1), value INTEGER NOT NULL)"
            )
            connection.execute("INSERT OR IGNORE INTO counter VALUES (1, 0)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=3)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def read(self):
        with self.connect() as connection:
            return connection.execute(
                "SELECT value FROM counter WHERE id = 1"
            ).fetchone()[0]

    def increment(self):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE counter SET value = value + 1 WHERE id = 1")
            return connection.execute(
                "SELECT value FROM counter WHERE id = 1"
            ).fetchone()[0]

    def ready(self):
        self.read()


class RedisCounter:
    def __init__(self, url):
        import redis

        self.client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False,
            health_check_interval=5,
        )

    def read(self):
        return int(self.client.get("docker-hw:counter") or 0)

    def increment(self):
        return int(self.client.incr("docker-hw:counter"))

    def ready(self):
        self.client.ping()


def make_handler(counter, storage, greeting):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def snapshot(self, value):
            return {
                "greeting": greeting,
                "count": value,
                "hostname": socket.gethostname(),
                "storage": storage,
            }

        def unavailable(self, exc):
            logging.warning("storage_unavailable: %s", type(exc).__name__)
            self.send_json(503, {"error": "storage_unavailable"})

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/healthz":
                self.send_json(200, {"status": "alive"})
                return
            if path not in ("/", "/readyz"):
                self.send_json(404, {"error": "not_found"})
                return
            try:
                if path == "/readyz":
                    counter.ready()
                    self.send_json(200, {"status": "ready", "storage": storage})
                else:
                    value = counter.read()
                    self.send_json(200, self.snapshot(value))
            except (sqlite3.Error, OSError, ValueError) as exc:
                self.unavailable(exc)
            except Exception as exc:
                # Redis exception classes импортируются только в режиме redis.
                if storage == "redis":
                    import redis

                    if isinstance(exc, redis.exceptions.RedisError):
                        self.unavailable(exc)
                        return
                raise

        def do_POST(self):
            if urlsplit(self.path).path != "/increment":
                self.send_json(404, {"error": "not_found"})
                return
            try:
                value = counter.increment()
                self.send_json(200, self.snapshot(value))
            except (sqlite3.Error, OSError, ValueError) as exc:
                self.unavailable(exc)
            except Exception as exc:
                if storage == "redis":
                    import redis

                    if isinstance(exc, redis.exceptions.RedisError):
                        self.unavailable(exc)
                        return
                raise

        def log_message(self, message, *args):
            logging.info("http %s %s", self.client_address[0], message % args)

    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    storage = os.getenv("STORAGE", "sqlite")
    if storage == "sqlite":
        counter = SQLiteCounter(os.getenv("DATA_FILE", "/data/counter.db"))
    elif storage == "redis":
        counter = RedisCounter(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    else:
        raise SystemExit("STORAGE must be sqlite or redis")
    port = int(os.getenv("PORT", "8000"))
    handler = make_handler(counter, storage, os.getenv("GREETING", "Hello, Docker!"))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    logging.info("listening port=%s storage=%s", port, storage)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
