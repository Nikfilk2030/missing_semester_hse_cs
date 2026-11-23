"""Показать настоящий обмен с Microsoft Learn: python3 mcp_demo.py
Для разбора полных JSON-RPC ответов: python3 mcp_demo.py --raw
Нужны Python 3, curl и сеть. Здесь нет LLM, ключей или операций записи в сервис.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

URL = 'https://learn.microsoft.com/api/mcp'
VERSION = '2025-06-18'
QUERY = 'What is Azure Functions?'
SEARCH = 'microsoft_docs_search'


def main(directory, *, raw=False):
    # Шаг 1. В этой редакции MCP клиент сначала предлагает версию протокола.
    # Это служебный обмен: ни каталога, ни статей мы пока не запрашивали.
    print('1. Согласуем версию с Microsoft Learn')
    init, session = exchange(directory, {
        'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': VERSION, 'capabilities': {},
                   'clientInfo': {'name': 'seminar-readonly', 'version': '1'}}
    }, raw=raw)
    print('  Версия:', init.get('protocolVersion'))
    if init.get('protocolVersion') != VERSION:
        raise ValueError('сервер не согласовал учебную версию ' + VERSION)

    # У уведомления нет id. Сервер подтверждает получение на уровне HTTP,
    # но у notifications/initialized нет парного JSON-RPC ответа.
    _, session = exchange(directory, {
        'jsonrpc': '2.0', 'method': 'notifications/initialized'
    }, session, raw=raw)

    # Шаг 2. В tools/list нет поискового запроса: ответ описывает инструменты,
    # а inputSchema.properties сообщает, какие поля принимает каждый из них.
    print('\n2. Читаем каталог инструментов (статью еще не искали)')
    catalog, session = exchange(directory, {
        'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}
    }, session, raw=raw)
    tools = catalog['tools']
    for tool in tools:
        fields = ', '.join(tool['inputSchema'].get('properties', {}))
        print(f"  {tool['name']}({fields})")
    if not any(tool['name'] == SEARCH for tool in tools):
        raise ValueError('поиск не объявлен в полученном каталоге')

    # Шаг 3. Только теперь просим выполнить поиск. tools/call — метод MCP,
    # name — выбранный инструмент, arguments — его вход. В демо выбор задан
    # в коде; в агенте этот же вызов могла бы предложить модель.
    print('\n3. Вызываем ' + SEARCH + ': ' + QUERY)
    result, _ = exchange(directory, {
        'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
        'params': {'name': SEARCH, 'arguments': {'query': QUERY}}
    }, session, raw=raw)
    show_search_result(result)


def show_search_result(result):
    # HTTP 200 означает доставку, а не успешный поиск. Смотрим на isError и
    # на содержимое результата. У Microsoft Learn выдача — JSON внутри текста.
    text = next((item['text'] for item in result.get('content', [])
                 if item.get('type') == 'text' and item.get('text', '').strip()), '')
    if result.get('isError'):
        raise ValueError('ошибка инструмента: ' + text[:240])
    if not text:
        raise ValueError('инструмент вернул пустой текст')
    try:
        rows = json.loads(text)['results']
    except (json.JSONDecodeError, TypeError, KeyError):
        print('  Фрагмент ответа:', text[:240])
        return
    if not rows:
        raise ValueError('в результате поиска нет документов')
    first = rows[0]
    print('  Первый результат:', first['title'])
    print('  Источник:', first.get('contentUrl') or '(ссылки нет)')
    # Для проектора пропускаем Markdown-заголовок: полезное отличие от запроса — текст статьи.
    lines = first.get('content', '').splitlines()
    if lines and lines[0].lstrip().startswith('#'):
        lines = lines[1:]
    snippet = textwrap.shorten(' '.join(lines), width=220, placeholder='…')
    if snippet:
        print('  Фрагмент статьи:')
        print(textwrap.fill(snippet, width=82, initial_indent='    ', subsequent_indent='    '))


def exchange(directory, packet, session=None, *, raw=False):
    """Один HTTP POST. Показываем то же тело, которое передаем curl."""
    headers = Path(directory) / 'headers'
    body = Path(directory) / 'body'
    cmd = ['curl', '-q', '--silent', '--show-error', '--max-time', '15',
           '--header', 'Content-Type: application/json',
           '--header', 'Accept: application/json, text/event-stream',
           '--dump-header', str(headers), '--output', str(body), '--write-out', '%{http_code}']
    if packet['method'] != 'initialize':
        cmd += ['--header', 'MCP-Protocol-Version: ' + VERSION]
    if session:
        cmd += ['--header', 'Mcp-Session-Id: ' + session]
    cmd += ['--data-binary', '@-', URL]

    payload = json.dumps(packet, ensure_ascii=False)
    print('Клиент → Microsoft Learn |', 'запрос' if 'id' in packet else 'уведомление')
    print(payload, flush=True)
    response = subprocess.run(cmd, input=payload.encode('utf-8'), stdout=subprocess.PIPE, check=True)
    status = int(response.stdout)
    print(f"Microsoft Learn → клиент | {packet['method']}: HTTP {status}")
    if not 200 <= status < 300:
        raise ValueError('сервер вернул HTTP ' + str(status))
    for line in headers.read_text(encoding='latin-1').splitlines():
        if line.lower().startswith('mcp-session-id:'):
            session = line.split(':', 1)[1].strip()
    if 'id' not in packet:
        print('  Уведомление принято. JSON-RPC ответа не ожидаем')
        return {}, session

    # Ответ бывает обычным JSON или событием SSE с тем же JSON в строке data:.
    # Сопоставляем запрос и ответ по id, а не по очередности сообщений.
    data = body.read_text(encoding='utf-8')
    if data.lstrip().startswith('{'):
        candidates = [json.loads(data)]
    else:
        candidates = [json.loads(line[5:].strip()) for line in data.splitlines()
                      if line.startswith('data:') and line[5:].strip().startswith('{')]
    reply = next((msg for msg in candidates if msg.get('id') == packet['id']), None)
    if not reply or reply.get('jsonrpc') != '2.0':
        raise ValueError(f"нет ответа JSON-RPC с id={packet['id']}")
    if raw:
        print(json.dumps(reply, ensure_ascii=False, indent=2))
    if 'error' in reply:
        raise ValueError(f"JSON-RPC id={reply['id']}: {reply['error']}")
    print(f"  Ответ id={reply['id']} (выбранные поля):")
    return reply['result'], session


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Учебный MCP-клиент Microsoft Learn')
    parser.add_argument('--raw', action='store_true', help='печатать также полные JSON-RPC ответы')
    args = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory() as directory:
            main(directory, raw=args.raw)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('Демо остановлено:', error, file=sys.stderr)
        sys.exit(1)
