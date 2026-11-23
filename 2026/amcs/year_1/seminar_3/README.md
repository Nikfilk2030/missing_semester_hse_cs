# Семинар 3 · LLM-агенты, MCP и оценка качества

[Слайды (PDF)](lecture.pdf) · [Демо MCP на Python](mcp_demo.py)

Демо запрашивает у Microsoft Learn список инструментов (`tools/list`), затем вызывает поиск по документации (`tools/call`). Для запуска из папки семинара нужны Python 3, `curl` и доступ к сети

```bash
python3 mcp_demo.py
```

## Агенты и инструменты

- [Агент бронирования Алисы](https://alice.yandex.ru/agents/booking): поиск ресторана и бронирование столика
- [Плагины Алисы](https://alice.yandex.ru/plugins/)
- [Google: Agents (PDF)](https://storage.ghost.io/c/dc/a8/dca8ae32-7ed6-405a-b948-680b55c8f3dc/content/files/2025/01/Whitepaper-Agents---Google.pdf?utm_source=chatgpt.com): как устроен агент и зачем ему инструменты

## Спецификация Model Context Protocol (2026-07-28)

- [Базовый протокол](https://modelcontextprotocol.io/specification/2026-07-28/basic): формат сообщений
- [Core Components](https://modelcontextprotocol.io/specification/2026-07-28/architecture#core-components): за что отвечают хост, клиент и сервер
- [Message Flow](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#message-flow): как клиент получает список инструментов и вызывает один из них

## Оценка агентов

- [τ-bench (PDF)](https://arxiv.org/pdf/2406.12045v1): как проверить результат по состоянию базы и оценить надежность агента на повторных попытках
- [Sell More, Play Less: приложение B](https://arxiv.org/html/2604.07054v3#A2): как оценивали симулятор покупателя и замечали, что он начинал играть роль продавца
