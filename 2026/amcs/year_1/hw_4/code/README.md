# Веб-сервер и очередь заданий

Набор сервисов на Python 3.10+: простой HTTP-сервер, API приёма заданий, обработчик очереди и генератор нагрузки.

## Простой веб-сервер

Файл: `simple_web/server.py`. Работает без сторонних библиотек.

| Запрос | Ответ |
| --- | --- |
| `GET /` | Приветствие и имя ВМ |
| `GET /health` | HTTP `200` и статус `ok` |

Запуск:

```bash
python3 simple_web/server.py
```

По умолчанию слушает `0.0.0.0:8080`. Имя берётся из hostname. Его можно переопределить:

```bash
INSTANCE_NAME=vm-1 PORT=8080 python3 simple_web/server.py
```

## API заданий

Файл: `queue_demo/api.py`.

Принимает HTTP-запросы, отправляет задания в Yandex Message Queue и читает готовые результаты из Object Storage.

| Запрос | Назначение |
| --- | --- |
| `GET /` | Название сервиса и hostname |
| `GET /health` | Проверка работы HTTP-сервера |
| `POST /tasks` | Создание задания; HTTP `202` и `task_id` |
| `GET /tasks/<task_id>` | Готовый результат; HTTP `200` |

Пример создания задания:

```bash
curl -X POST http://localhost:8080/tasks \
  -H 'Content-Type: application/json' \
  --data '{"text":"Привет, облако!","delay_seconds":20}'
```

`text` — строка длиной 1–2000 символов. `delay_seconds` — время обработки от 0 до 300 секунд, по умолчанию 20.

Ответ:

```json
{"task_id":"2e3b4b83e72f408697bf91659eaa2197","status":"accepted"}
```

Чтобы получить результат, используйте `task_id` из ответа:

```bash
curl http://localhost:8080/tasks/2e3b4b83e72f408697bf91659eaa2197
```

До появления результата API возвращает HTTP `404` со статусом `not_ready_or_unknown`: задание ещё не готово либо такой идентификатор неизвестен. При недоступности очереди или хранилища соответствующий запрос возвращает HTTP `503`.

## Воркер

Файл: `queue_demo/worker.py`.

Получает задания из Message Queue и последовательно выполняет их:

1. Проверяет, не сохранён ли уже результат для `task_id`.
2. Ждёт `delay_seconds` и переводит `text` в верхний регистр.
3. Сохраняет JSON в Object Storage по ключу `results/<task_id>.json`.
4. Удаляет сообщение из очереди после сохранения результата.

Результат содержит `task_id`, исходный текст, преобразованную строку, `worker_id` и время начала/окончания обработки. По умолчанию `worker_id` равен hostname.

Условная запись `If-None-Match: *` предотвращает перезапись готового результата при одновременной повторной доставке. При ошибке сохранения сообщение не подтверждается. Если результат уже существует, воркер удаляет повторно доставленное сообщение без повторного ожидания.

При SIGTERM незавершённое сообщение возвращается в очередь сразу. При резком завершении процесса оно становится доступным после таймаута видимости: `max(60, delay_seconds + 60)` секунд.

## Генератор нагрузки

Файл: `queue_demo/load.py`. Работает без сторонних библиотек и облачных ключей.

Отправляет задания через HTTP API и сохраняет их идентификаторы в JSON-файл:

```bash
python3 queue_demo/load.py http://localhost:8080 \
  --count 100 --delay 20 --parallel 4 --output submitted.json
```

| Параметр | Назначение | По умолчанию |
| --- | --- | --- |
| `--count` | Количество заданий | `100` |
| `--delay` | Время обработки одного задания, секунды | `20` |
| `--parallel` | Число параллельных HTTP-запросов | `4` |
| `--timeout` | Таймаут HTTP-запроса, секунды | `15` |
| `--output` | Файл с принятыми заданиями и ошибками | `submitted.json` |

## Настройки API и воркера

| Переменная | Назначение |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | Идентификатор статического ключа сервисного аккаунта |
| `AWS_SECRET_ACCESS_KEY` | Секретная часть ключа |
| `AWS_DEFAULT_REGION` | Регион; по умолчанию `ru-central1` |
| `QUEUE_URL` | Полный URL существующей очереди |
| `RESULT_BUCKET` | Имя бакета результатов |
| `RESULT_PREFIX` | Префикс объектов; по умолчанию `results/` |
| `SQS_ENDPOINT_URL` | Endpoint очереди; по умолчанию Yandex Message Queue |
| `S3_ENDPOINT_URL` | Endpoint хранилища; по умолчанию Yandex Object Storage |
| `HOST`, `PORT` | Адрес и порт HTTP-сервера; `0.0.0.0:8080` |
| `WORKER_ID` | Необязательное имя воркера вместо hostname |

API и воркеры используют одну очередь, бакет и префикс результатов. API нужны права отправки сообщений и чтения результатов; воркеру — получения/удаления сообщений, изменения их видимости и чтения/записи результатов.

## Установка и запуск

Команды выполняются из корня распакованного архива. Для API и воркера:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r queue_demo/requirements.txt
cp queue_demo/env.example .env
chmod 600 .env
```

Заполните `.env`, затем загрузите настройки в текущий терминал:

```bash
set -a
. ./.env
set +a
```

Запустите нужный сервис:

```bash
# API
.venv/bin/python queue_demo/api.py

# Воркер — в отдельном терминале с загруженными настройками или на другой ВМ
.venv/bin/python queue_demo/worker.py
```

Простой веб-сервер и API по умолчанию используют один порт. Для одновременного запуска на одной машине задайте им разные значения `PORT`.

### Веб-сервер

```bash
docker run --rm --name hw4-web \
  -p 8080:8080 -e INSTANCE_NAME=vm-1 \
  cloud-hw4-web:ubuntu24.04
```

Проверка: `curl http://localhost:8080/health`.

### API

Скопируйте `queue_demo/env.example` в `.env` и заполните настройки. Передайте файл контейнеру при запуске:

```bash
docker run --rm --name hw4-api \
  --env-file .env -p 8080:8080 \
  cloud-hw4-api:ubuntu24.04
```

### Воркер

```bash
docker run -d --name hw4-worker \
  --restart unless-stopped --stop-timeout 25 \
  --env-file .env \
  cloud-hw4-worker:ubuntu24.04
```

При необходимости задайте уникальное имя через `-e WORKER_ID=worker-vm-1`. По умолчанию используется hostname контейнера. Остановка — `docker stop hw4-worker`, логи — `docker logs -f hw4-worker`.

### Генератор нагрузки

В Linux/macOS, заменив URL на адрес своего API или балансировщика:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/output" \
  cloud-hw4-load:ubuntu24.04 http://203.0.113.10 \
  --count 100 --delay 20 --parallel 4 --output /output/submitted.json
```
