#!/usr/bin/env python3
"""Один процесс последовательно обрабатывает задания из Yandex Message Queue."""

import json
import logging
import math
import os
import signal
import socket
import threading

from botocore.exceptions import BotoCoreError, ClientError

from common import create_clients, log, missing_object, now, parse_task, settings_from_env


def release_message(sqs, settings, receipt):
    """Вернуть незавершённое сообщение в очередь при штатном выключении."""
    sqs.change_message_visibility(QueueUrl=settings.queue_url, ReceiptHandle=receipt, VisibilityTimeout=0)


def process_message(message, settings, sqs, s3, stop, worker_id):
    receipt = message["ReceiptHandle"]
    if stop.is_set():
        release_message(sqs, settings, receipt)
        return False

    task = parse_task(message["Body"])
    task_id = task["task_id"]
    key = settings.result_key(task_id)

    # После сбоя между PutObject и DeleteMessage результат уже может существовать.
    try:
        s3.head_object(Bucket=settings.result_bucket, Key=key)
    except ClientError as error:
        if not missing_object(error):
            raise
    else:
        sqs.delete_message(QueueUrl=settings.queue_url, ReceiptHandle=receipt)
        log("already_done", task_id=task_id, worker_id=worker_id)
        return True

    # Задача ограничена 300 секундами. Добавляем запас на запись результата.
    visibility = max(60, math.ceil(task["delay_seconds"]) + 60)
    sqs.change_message_visibility(
        QueueUrl=settings.queue_url, ReceiptHandle=receipt, VisibilityTimeout=visibility
    )
    started_at = now()
    log("started", task_id=task_id, worker_id=worker_id,
        attempt=message.get("Attributes", {}).get("ApproximateReceiveCount", "?"),
        delay_seconds=task["delay_seconds"], visibility_timeout=visibility)

    # Здесь могла бы быть настоящая работа. Event позволяет прервать ожидание по SIGTERM.
    if stop.wait(task["delay_seconds"]):
        release_message(sqs, settings, receipt)
        log("interrupted", task_id=task_id, worker_id=worker_id)
        return False

    result = {
        "task_id": task_id,
        "text": task["text"],
        "result": task["text"].upper(),
        "worker_id": worker_id,
        "started_at": started_at,
        "finished_at": now(),
    }
    try:
        # Условная запись атомарно защищает от двух результатов при повторной доставке.
        s3.put_object(
            Bucket=settings.result_bucket,
            Key=key,
            Body=json.dumps(result, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
            IfNoneMatch="*",
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in {"PreconditionFailed", "412"}:
            raise
        log("result_already_saved", task_id=task_id, worker_id=worker_id)

    # Если запись не удалась, до этого места не дойдём: сообщение останется в очереди.
    sqs.delete_message(QueueUrl=settings.queue_url, ReceiptHandle=receipt)
    log("completed", task_id=task_id, worker_id=worker_id)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = settings_from_env()
    sqs, s3 = create_clients()
    worker_id = os.getenv("WORKER_ID") or socket.gethostname()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    log("worker_started", worker_id=worker_id)

    while not stop.is_set():
        try:
            response = sqs.receive_message(
                QueueUrl=settings.queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
                VisibilityTimeout=60,
                AttributeNames=["ApproximateReceiveCount"],
            )
            for message in response.get("Messages", []):
                process_message(message, settings, sqs, s3, stop, worker_id)
        except (BotoCoreError, ClientError, ValueError, TypeError, KeyError) as error:
            # Не подтверждаем сообщение при ошибке: оно вернётся после visibility timeout.
            log("processing_failed", worker_id=worker_id, error=str(error))
            stop.wait(3)
    log("worker_stopped", worker_id=worker_id)


if __name__ == "__main__":
    main()
