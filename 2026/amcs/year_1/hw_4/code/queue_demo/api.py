#!/usr/bin/env python3
"""HTTP API за балансировщиком: принять задание и прочитать готовый результат."""

import json
import logging
import os
import socket
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from botocore.exceptions import BotoCoreError, ClientError

from common import create_clients, log, missing_object, now, settings_from_env, validate_input


MAX_BODY_BYTES = 16 * 1024


def make_handler(settings, sqs, s3):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                return self.reply(200, {"status": "ok", "hostname": socket.gethostname()})
            if path == "/":
                return self.reply(200, {"service": "hw4-api", "hostname": socket.gethostname()})
            if not path.startswith("/tasks/"):
                return self.reply(404, {"error": "not_found"})
            try:
                task_id = uuid.UUID(path.removeprefix("/tasks/")).hex
            except ValueError:
                return self.reply(400, {"error": "invalid_task_id"})
            try:
                response = s3.get_object(Bucket=settings.result_bucket, Key=settings.result_key(task_id))
                with response["Body"] as stream:
                    result = json.loads(stream.read())
            except ClientError as error:
                if missing_object(error):
                    # Без отдельного реестра нельзя отличить ожидание от неизвестного ID.
                    return self.reply(404, {"task_id": task_id, "status": "not_ready_or_unknown"})
                log("result_read_failed", task_id=task_id, error=str(error))
                return self.reply(503, {"error": "storage_unavailable"})
            except (BotoCoreError, ValueError) as error:
                log("result_read_failed", task_id=task_id, error=str(error))
                return self.reply(503, {"error": "storage_unavailable"})
            self.reply(200, result)

        def do_POST(self):
            if urlsplit(self.path).path != "/tasks":
                return self.reply(404, {"error": "not_found"})
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Используйте Content-Length без Transfer-Encoding")
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    raise ValueError("Ожидается непустой JSON с Content-Length")
                if length > MAX_BODY_BYTES:
                    return self.reply(413, {"error": "request_too_large"})
                payload = json.loads(self.rfile.read(length))
                text, delay = validate_input(payload)
            except (ValueError, UnicodeDecodeError) as error:
                return self.reply(400, {"error": str(error)})
            except TimeoutError:
                return self.reply(408, {"error": "request_timeout"})

            task = {"task_id": uuid.uuid4().hex, "text": text, "delay_seconds": delay, "created_at": now()}
            try:
                sqs.send_message(QueueUrl=settings.queue_url, MessageBody=json.dumps(task, ensure_ascii=False))
            except (BotoCoreError, ClientError) as error:
                log("enqueue_failed", error=str(error))
                return self.reply(503, {"error": "queue_unavailable"})
            log("accepted", task_id=task["task_id"])
            self.reply(202, {"task_id": task["task_id"], "status": "accepted"})

        def log_message(self, message, *args):
            logging.info("%s %s", self.address_string(), message % args)

    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = settings_from_env()
    sqs, s3 = create_clients()
    address = (os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8080")))
    server = ThreadingHTTPServer(address, make_handler(settings, sqs, s3))
    log("api_started", host=address[0], port=address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
