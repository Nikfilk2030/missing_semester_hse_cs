"""Общие настройки, клиенты Yandex Cloud и формат задания."""

import json
import logging
import math
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import boto3
from botocore.config import Config


MAX_TEXT_LENGTH = 2000
MAX_DELAY_SECONDS = 300


@dataclass(frozen=True)
class Settings:
    queue_url: str
    result_bucket: str
    result_prefix: str = "results/"

    def result_key(self, task_id):
        prefix = self.result_prefix.strip("/")
        return f"{prefix + '/' if prefix else ''}{task_id}.json"


def settings_from_env():
    for name in ("QUEUE_URL", "RESULT_BUCKET"):
        if not os.getenv(name) or "CHANGE_ME" in os.environ[name]:
            raise ValueError(f"Задайте {name} в переменных окружения")
    return Settings(
        os.environ["QUEUE_URL"],
        os.environ["RESULT_BUCKET"],
        os.getenv("RESULT_PREFIX", "results/"),
    )


def create_clients():
    # Используем статические ключи / AWS profile, а не AWS EC2 metadata.
    os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
    region = os.getenv("AWS_DEFAULT_REGION", "ru-central1")
    options = dict(
        connect_timeout=5,
        read_timeout=30,  # Дольше 20-секундного long polling очереди.
        retries={"mode": "standard", "total_max_attempts": 3},
    )
    session = boto3.session.Session()
    sqs = session.client(
        "sqs",
        region_name=region,
        endpoint_url=os.getenv("SQS_ENDPOINT_URL", "https://message-queue.api.cloud.yandex.net"),
        config=Config(**options),
    )
    s3 = session.client(
        "s3",
        region_name=region,
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "https://storage.yandexcloud.net"),
        config=Config(
            **options,
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    return sqs, s3


def validate_input(data):
    if not isinstance(data, dict):
        raise ValueError("Ожидается JSON-объект")
    text = data.get("text")
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT_LENGTH:
        raise ValueError(f"text должен быть строкой длиной 1–{MAX_TEXT_LENGTH}")
    delay = data.get("delay_seconds", 20)
    if type(delay) not in (int, float) or not math.isfinite(delay) or not 0 <= delay <= MAX_DELAY_SECONDS:
        raise ValueError(f"delay_seconds должен быть числом от 0 до {MAX_DELAY_SECONDS}")
    return text, delay


def parse_task(body):
    task = json.loads(body)
    text, delay = validate_input(task)
    task_id = task.get("task_id")
    if not isinstance(task_id, str) or uuid.UUID(task_id).hex != task_id:
        raise ValueError("task_id должен быть UUID без дефисов")
    return {"task_id": task_id, "text": text, "delay_seconds": delay}


def now():
    return datetime.now(timezone.utc).isoformat()


def log(event, **fields):
    logging.info(json.dumps({"time": now(), "event": event, **fields}, ensure_ascii=False))


def missing_object(error):
    return error.response.get("Error", {}).get("Code") in {"NoSuchKey", "NotFound", "404"}
