"""Read-only public ingress/ten-connection check; never output login secrets.

Run with the private tester-access.json path, using Python with websockets 15.
This deliberately does not call Agent, Tool, speech or task mutation methods.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import json
import http.client
import secrets
from pathlib import Path
import urllib.error
from urllib.parse import urlparse
import urllib.request

import websockets

PHASE = 'input'


def authorization(entry):
    return 'Basic ' + base64.b64encode(
        (entry['username'] + ':' + entry['password']).encode()).decode()


def http_status(url, entry=None):
    request = urllib.request.Request(url)
    if entry:
        request.add_header('Authorization', authorization(entry))
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def connect(entry, origin=None):
    return websockets.connect(entry['url'].replace('https:', 'wss:') + 'ws',
        origin=origin or entry['url'].rstrip('/'),
        additional_headers={'Authorization': authorization(entry)},
        open_timeout=20, close_timeout=5)


def rejected_upgrade_status(entry, origin):
    # Inspect the rejection's HTTP status directly. Python's WebSocket client
    # cannot parse every truncated HTTP error body forwarded by a proxy.
    connection = http.client.HTTPSConnection(urlparse(entry['url']).hostname, timeout=20)
    try:
        connection.request('GET', '/ws', headers={
            'Authorization': authorization(entry), 'Origin': origin,
            'Upgrade': 'websocket', 'Connection': 'Upgrade',
            'Sec-WebSocket-Version': '13',
            'Sec-WebSocket-Key': base64.b64encode(secrets.token_bytes(16)).decode()})
        response = connection.getresponse()
        return response.status
    finally:
        connection.close()


async def rpc(ws, method, params=None):
    request_id = 'deployment-probe-' + method
    await ws.send(json.dumps({'type': 'req', 'id': request_id,
                             'method': method, 'params': params or {}}))
    async with asyncio.timeout(20):
        while True:
            message = json.loads(await ws.recv())
            if message.get('id') == request_id:
                if not message.get('ok'):
                    raise ValueError('rpc_rejected_' + method)
                return message['payload']


async def check_connection(ws):
    ack = json.loads(await asyncio.wait_for(ws.recv(), 20))
    if ack.get('event') != 'connection.ack':
        raise ValueError('missing_connection_ack')
    config = await rpc(ws, 'config.get')
    if any(config.get(key) for key in ('model', 'model_provider', 'api_base', 'api_key')):
        raise ValueError('agent_model_not_empty')
    if any('LIVE_VOICE_SPEECH' in key for key in config):
        raise ValueError('private_speech_configuration_exposed')
    payload = await rpc(ws, 'project.list', {'filter': 'all', 'work_mode': 'code'})
    projects = [p for p in payload['projects'] if not p.get('is_default')]
    if len(projects) != 1 or projects[0]['project_dir'] != '/projects/livevoice-test':
        raise ValueError('unexpected_project_scope')
    if projects[0].get('git', {}).get('status') != 'ready':
        raise ValueError('project_git_not_ready')
    return projects[0]['project_id']


async def run(entries):
    global PHASE
    if len(entries) != 10 or {e['instance'] for e in entries} != {f'lv{i:02d}' for i in range(1, 11)}:
        raise ValueError('ten_unique_access_records_required')
    evidence = {'observed_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'public_https_wss_and_empty_model_readiness',
                'agent_tool_calls': 0, 'speech_calls': 0, 'negative': [], 'waves': []}
    for index, entry in enumerate(entries):
        PHASE = entry['instance'] + '_http_auth'
        for path in ('', 'ws', 'ws/live-voice/media'):
            if await asyncio.to_thread(http_status, entry['url'] + path) != 401:
                raise ValueError('unauthenticated_route_not_rejected')
        other = entries[(index + 1) % 10]
        if await asyncio.to_thread(http_status, entry['url'], other) != 401:
            raise ValueError('cross_account_access_not_rejected')
        if await asyncio.to_thread(http_status, entry['url'], entry) != 200:
            raise ValueError('authenticated_ui_unavailable')
        PHASE = entry['instance'] + '_origin'
        if await asyncio.to_thread(rejected_upgrade_status, entry, other['url'].rstrip('/')) != 403:
            raise ValueError('cross_instance_origin_not_rejected')
        evidence['negative'].append({'instance': entry['instance'],
            'unauthenticated_routes': '401', 'other_account': '401', 'other_origin': '403'})
    for count in (1, 3, 10):
        PHASE = f'connections_{count}'
        async with AsyncExitStack() as stack:
            sockets = await asyncio.gather(*(stack.enter_async_context(connect(e)) for e in entries[:count]))
            projects = await asyncio.gather(*(check_connection(ws) for ws in sockets))
            if len(set(projects)) != count:
                raise ValueError('project_identity_not_isolated')
            # Hold every real socket together and verify responsive transport.
            waiters = await asyncio.gather(*(ws.ping() for ws in sockets))
            await asyncio.wait_for(asyncio.gather(*waiters), 15)
            evidence['waves'].append({'connections': count, 'ready_acks': count,
                'empty_agent_models': count, 'unique_projects': count, 'pongs': count})
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('access_file', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = asyncio.run(run(json.loads(args.access_file.read_text(encoding='utf-8-sig'))))
        args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(evidence))
    except Exception as error:
        # Provider/transport exceptions can carry request headers. No exception
        # body, traceback, access record or configuration is logged.
        print(json.dumps({'result': 'failed', 'phase': PHASE, 'error_type': type(error).__name__,
                          'check': str(error) if type(error) is ValueError else None}))
        raise SystemExit(1) from None
