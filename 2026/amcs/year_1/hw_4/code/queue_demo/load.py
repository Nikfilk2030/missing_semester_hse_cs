#!/usr/bin/env python3
"""Генератор нагрузки: работает на ноутбуке без boto3 и облачных ключей."""

import argparse
import concurrent.futures
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path


def submit(base_url, number, delay, timeout):
    payload = {"text": f"task-{number}", "delay_seconds": delay}
    request = urllib.request.Request(
        base_url.rstrip("/") + "/tasks",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 202:
            raise ValueError(f"Ожидался HTTP 202, получен {response.status}")
        result = json.load(response)
    return {**payload, "task_id": result["task_id"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Адрес балансировщика, например http://203.0.113.10")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--delay", type=float, default=20, help="Длительность одного задания, 0–300 секунд")
    parser.add_argument("--parallel", type=int, default=4, help="Число параллельных HTTP-запросов")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--output", type=Path, default=Path("submitted.json"))
    args = parser.parse_args()
    if args.count < 1 or args.parallel < 1 or not math.isfinite(args.delay) or not 0 <= args.delay <= 300:
        parser.error("count и parallel должны быть положительными; delay — от 0 до 300")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout должен быть положительным конечным числом")

    accepted, failed = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {
            executor.submit(submit, args.base_url, number, args.delay, args.timeout): number
            for number in range(1, args.count + 1)
        }
        for future in concurrent.futures.as_completed(futures):
            number = futures[future]
            try:
                task = future.result()
                accepted.append(task)
                print(f"Accepted {len(accepted)}/{args.count}: {task['task_id']}", flush=True)
            except (OSError, ValueError, KeyError) as error:
                failed.append({"number": number, "error": str(error)})
                print(f"Failed {number}: {error}", file=sys.stderr)

    args.output.write_text(json.dumps({"api_url": args.base_url, "accepted": accepted, "failed": failed},
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Accepted: {len(accepted)}; failed: {len(failed)}; saved: {args.output}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
