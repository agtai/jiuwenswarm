"""Controlled container startup with first-use model setup and durable isolation.

Private Speech/runtime values are mounted at /run/secrets/runtime.json, never
baked into the image. Existing instance configuration is preserved on restart.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone


DATA = Path('/data')
PROJECT = Path('/projects/livevoice-test')
MARKER = DATA / 'deployment-instance.json'
REQUIRED_FLAGS = (
    'JIUWENSWARM_LIVE_VOICE_P3_ENABLED',
    'JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED',
    'JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED',
    'JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED',
    'JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED',
    'JIUWENSWARM_LIVE_VOICE_CRITICAL_INPUT_ENABLED',
    'JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED',
    'JIUWENSWARM_LIVE_VOICE_END_OF_TURN_ENABLED',
    'JIUWENSWARM_LIVE_VOICE_WEB_ALPHA_CREDENTIAL_ENABLED',
    'LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED',
    'LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED',
)
SPEECH_KEYS = (
    'LIVE_VOICE_SPEECH_API_KEY', 'LIVE_VOICE_SPEECH_API_BASE',
    'LIVE_VOICE_SPEECH_STT_MODEL', 'LIVE_VOICE_SPEECH_TTS_MODEL',
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def load_runtime(path: Path = Path('/run/secrets/runtime.json')) -> dict:
    runtime = json.loads(path.read_text())
    if not re.fullmatch(r'lv(?:0[1-9]|10)', runtime.get('instance', '')):
        raise ValueError('invalid_instance')
    hostname = runtime.get('hostname', '')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,240}[a-z0-9]', hostname):
        raise ValueError('invalid_hostname')
    if not hostname.startswith(runtime['instance'] + '.'):
        raise ValueError('hostname_instance_mismatch')
    if set(runtime['speech']) != set(SPEECH_KEYS):
        raise ValueError('invalid_speech_keys')
    if any(not isinstance(v, str) or not v or '\n' in v or '\r' in v for v in runtime['speech'].values()):
        raise ValueError('invalid_speech_value')
    if runtime['speech']['LIVE_VOICE_SPEECH_API_BASE'].rstrip('/') != 'https://api.openai.com/v1':
        raise ValueError('unexpected_speech_provider')
    expiry = datetime.fromisoformat(runtime['auth_expires_at'].replace('Z', '+00:00'))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError('authorization_expired')
    if not isinstance(runtime.get('auth_token'), str) or len(runtime['auth_token']) < 32:
        raise ValueError('invalid_auth_token')
    return runtime


def initialize(runtime: dict) -> dict:
    if MARKER.exists():
        marker = json.loads(MARKER.read_text())
        if marker['instance'] != runtime['instance'] or marker['project_dir'] != str(PROJECT):
            raise ValueError('existing_instance_mismatch')
        if not (DATA / 'config/config.yaml').is_file() or not (PROJECT / '.git').is_dir():
            raise ValueError('existing_instance_incomplete')
        return marker
    if any(DATA.iterdir()) or any(PROJECT.parent.iterdir()):
        raise ValueError('refusing_to_overwrite_unidentified_data')
    (DATA / 'config').mkdir(parents=True)
    from jiuwenswarm.common.utils import prepare_workspace
    prepare_workspace(overwrite=False, workspace_dir=DATA)
    import yaml
    config_path = DATA / 'config/config.yaml'
    config = yaml.safe_load(config_path.read_text())
    config['models'] = {'defaults': []}
    config['setup_guide'] = {'enabled': True}
    config['preferred_language'] = 'zh'
    config['auto_recap'] = {'enabled': False}
    config['auto_memory_enabled'] = False
    for name, channel in config.get('channels', {}).items():
        if name != 'web' and isinstance(channel, dict):
            channel['enabled'] = False
            for app in channel.get('apps') or []:
                app['enabled'] = False
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    # No development Agent API key, model or provider is inherited.
    (DATA / 'config/.env').write_text('API_KEY=\nAPI_BASE=\nMODEL_NAME=\nMODEL_PROVIDER=\n')
    PROJECT.mkdir(parents=True)
    (PROJECT / 'README.md').write_text(
        '# Live Voice 测试项目\n\n'
        '这是当前测试者的独立项目。先在 Web 设置中填写自己的 Agent 模型和 API 配置，'
        '再将左侧 Work 切换为 Code，选择本项目开启 Live Voice。Realtime 语音服务已由服务器配置。\n\n'
        '可先让 Agent 读取 inventory.csv，再要求它在本项目创建一份简短汇总，'
        '核对文件、任务结果和语音播报是否一致。\n', encoding='utf-8')
    (PROJECT / 'inventory.csv').write_text('item,quantity\nnotebooks,12\npens,30\nfolders,8\n')
    for args in (
        ['init', '-b', 'main'], ['config', 'user.name', 'Live Voice Tester'],
        ['config', 'user.email', 'livevoice@localhost'], ['add', 'README.md', 'inventory.csv'],
        ['commit', '-m', 'Initialize isolated Live Voice test project'],
    ):
        subprocess.run(['git', '-C', str(PROJECT), *args], check=True, capture_output=True)
    from jiuwenswarm.server.runtime.session.project_store import create_or_restore_project
    project, _ = create_or_restore_project('Live Voice Test', str(PROJECT), work_mode='code')
    from jiuwenswarm.server.runtime.session.project_git import get_project_git_service
    get_project_git_service().ensure_on_project_create(project)
    marker = {'instance': runtime['instance'], 'project_id': project.project_id,
              'project_dir': str(PROJECT), 'created_at': datetime.now(timezone.utc).isoformat()}
    write_json(MARKER, marker)
    return marker


def configure(runtime: dict, marker: dict) -> None:
    os.environ.update({name: '1' for name in REQUIRED_FLAGS})
    os.environ.update(runtime['speech'])
    os.environ.update({
        'JIUWENSWARM_LIVE_VOICE_RUNTIME_PROFILE': 'formal-web-validation',
        'JIUWENSWARM_ENABLE_ORIGIN_CHECK': '1',
        # Gateway->AgentServer uses a loopback Origin inside this container.
        'JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS': runtime['hostname'] + ',127.0.0.1',
        'JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN': runtime['auth_token'],
        'JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID': runtime['instance'],
        'JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS': marker['project_id'],
        'JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT': runtime['auth_expires_at'],
        'JIUWENSWARM_LIVE_VOICE_P3_DATABASE': str(DATA / 'live_voice/p3alpha/formal_tasks.sqlite3'),
        'JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE': 'live-voice.direct-project-code.d2.v2',
        'LIVE_VOICE_SPEECH_PROVIDER': 'openai',
        'LIVE_VOICE_SPEECH_TTS_VOICE': 'marin',
        'LIVE_VOICE_INTERACTION_ENGINE': 'openai-realtime-native',
        'LIVE_VOICE_NATIVE_REALTIME_MODEL': 'gpt-realtime-2',
    })
    (DATA / 'live_voice/p3alpha').mkdir(parents=True, exist_ok=True)
    from jiuwenswarm.server.runtime.session.project_store import get_project_by_id
    project = get_project_by_id(marker['project_id'])
    if project is None or project.project_dir != str(PROJECT) or project.work_mode != 'code':
        raise ValueError('registered_project_mismatch')


async def speech_preflight() -> dict:
    sys.path.insert(0, '/app')
    from scripts.live_voice.formal_web_runtime_probe import run_probe
    from jiuwenswarm.server.live_voice.batch_speech import create_environment_batch_speech_provider
    result = await run_probe(create_environment_batch_speech_provider())
    import websockets
    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-realtime-2',
        additional_headers={'Authorization': 'Bearer ' + os.environ['LIVE_VOICE_SPEECH_API_KEY']},
        open_timeout=20, max_size=2**22,
    ) as ws:
        event = json.loads(await asyncio.wait_for(ws.recv(), 20))
        if event.get('type') != 'session.created' or event.get('session', {}).get('model') != 'gpt-realtime-2':
            raise ValueError('native_session_not_confirmed')
    return {**result, 'native_session': 'passed', 'native_model': 'gpt-realtime-2'}


def main() -> None:
    os.umask(0o077)
    # The image and secrets never provide Agent model environment variables.
    for name in ('API_KEY', 'API_BASE', 'MODEL_NAME', 'MODEL_PROVIDER', 'MODEL_ALIAS', 'OPENAI_API_KEY'):
        os.environ.pop(name, None)
    runtime = load_runtime()
    marker = initialize(runtime)
    # The SDK's default log files are relative to cwd; the source image is
    # deliberately root-owned. Keep runtime writes in this instance's volume.
    os.chdir(DATA)
    configure(runtime, marker)
    if '--init-only' in sys.argv:
        print(json.dumps({'initialized': runtime['instance'], 'project_id': marker['project_id']}))
        return
    result = asyncio.run(speech_preflight())
    assets = Path('/app/jiuwenswarm/channels/web/frontend/dist')
    manifest = {str(p.relative_to(assets)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in assets.rglob('*') if p.is_file()}
    write_json(DATA / 'logs/live_voice_container_contract.json', {
        'source_commit': Path('/app/DEPLOYED_COMMIT').read_text().strip(),
        'instance': runtime['instance'], 'hostname': runtime['hostname'],
        'project_id': marker['project_id'], 'preflight': result,
        'flags': {name: os.environ[name] for name in REQUIRED_FLAGS},
        'assets': manifest, 'auth_expires_at': runtime['auth_expires_at'],
        'agent_model_policy': 'user_configured',
        'physical_acceptance': 'not_run',
    })
    print(json.dumps({'preflight': 'passed', 'instance': runtime['instance']}), flush=True)
    os.execv(sys.executable, [sys.executable, '-m', 'jiuwenswarm.start_services', 'all'])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Error bodies from Providers and YAML may contain private values.
        import traceback
        frames = [{'file': frame.filename, 'line': frame.lineno, 'function': frame.name}
                  for frame in traceback.extract_tb(error.__traceback__)]
        print(json.dumps({'startup': 'failed', 'error_type': type(error).__name__,
                          'frames': frames}), flush=True)
        raise SystemExit(1) from None
