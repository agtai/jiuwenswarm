"""Bootstrap acceptance: empty models, restart preservation, and fail-closed data."""
from pathlib import Path
import json
import os
import subprocess
import sys

import yaml
import pytest


ROOT = Path(__file__).resolve().parents[2]
CHILD = '''
import importlib.util, json, os
from pathlib import Path
spec=importlib.util.spec_from_file_location('deployment_launch', os.environ['LAUNCH_PATH'])
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.DATA=Path(os.environ['TEST_DATA'])
module.PROJECT=Path(os.environ['TEST_PROJECT'])/'livevoice-test'
module.MARKER=module.DATA/'deployment-instance.json'
try:
    value=module.initialize({'instance':os.environ['TEST_INSTANCE']})
    print(json.dumps({'result':'ok','project_id':value['project_id']}))
except Exception as error:
    print(json.dumps({'result':'rejected','reason':str(error)}))
    raise SystemExit(1)
'''


def invoke(tmp_path, instance='lv01'):
    data, projects = tmp_path / 'data', tmp_path / 'projects'
    data.mkdir(exist_ok=True)
    projects.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('JIUWENSWARM_', 'LIVE_VOICE_', 'MODEL_'))
           and k not in ('API_KEY', 'API_BASE', 'OPENAI_API_KEY')}
    env.update(LAUNCH_PATH=str(Path(__file__).with_name('launch.py')),
               TEST_DATA=str(data), TEST_PROJECT=str(projects), TEST_INSTANCE=instance,
               JIUWENSWARM_DATA_DIR=str(data), JIUWENSWARM_CONFIG_DIR=str(data / 'config'),
               PYTHONUTF8='1', PYTHONPATH=str(ROOT))
    return subprocess.run([sys.executable, '-c', CHILD], env=env, cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8', timeout=90)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_first_use_has_no_agent_credentials_and_registered_code_project(tmp_path):
    result = invoke(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    config = yaml.safe_load((tmp_path / 'data/config/config.yaml').read_text(encoding='utf-8'))
    assert config['models'] == {'defaults': []}
    assert config['setup_guide']['enabled'] is True
    assert (tmp_path / 'data/config/.env').read_text() == 'API_KEY=\nAPI_BASE=\nMODEL_NAME=\nMODEL_PROVIDER=\n'
    projects = json.loads((tmp_path / 'data/agent/projects.json').read_text())['projects']
    assert len(projects) == 1 and projects[0]['work_mode'] == 'code'
    assert projects[0]['git']['enabled'] is True
    assert projects[0]['git']['status'] == 'ready'
    marker = json.loads((tmp_path / 'data/deployment-instance.json').read_text())
    assert marker['project_id'] == projects[0]['project_id']
    assert Path(projects[0]['project_dir']).resolve() == (tmp_path / 'projects/livevoice-test').resolve()


def test_restart_preserves_user_model_project_and_private_settings(tmp_path):
    assert invoke(tmp_path).returncode == 0
    config_path = tmp_path / 'data/config/config.yaml'
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    config['models'] = {'defaults': [{'model_client_config': {'model_name': 'user-selected-model'}}]}
    config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
    (tmp_path / 'data/config/.env').write_text('API_KEY=user-supplied-test-placeholder\n')
    (tmp_path / 'projects/livevoice-test/user-result.md').write_text('preserve this result')
    before = snapshot(tmp_path)
    result = invoke(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(tmp_path) == before


def test_foreign_instance_is_rejected_without_writes(tmp_path):
    assert invoke(tmp_path).returncode == 0
    before = snapshot(tmp_path)
    result = invoke(tmp_path, 'lv02')
    assert result.returncode != 0 and 'existing_instance_mismatch' in result.stdout
    assert snapshot(tmp_path) == before


def test_unidentified_data_is_preserved_and_rejected(tmp_path):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/existing-user-data.txt').write_text('must survive')
    before = snapshot(tmp_path)
    result = invoke(tmp_path)
    assert result.returncode != 0 and 'refusing_to_overwrite_unidentified_data' in result.stdout
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('invalid', ['expired', 'other_hostname', 'agent_key_in_speech'])
def test_invalid_runtime_authority_is_rejected_before_bootstrap_without_writes(tmp_path, invalid):
    import importlib.util
    from datetime import datetime, timedelta, timezone
    spec = importlib.util.spec_from_file_location('runtime_validation', Path(__file__).with_name('launch.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime = {'instance': 'lv01', 'hostname': 'lv01.test.example',
               'auth_token': 'test-token-' * 5,
               'auth_expires_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
               'speech': dict(zip(module.SPEECH_KEYS, ['test-key', 'https://api.openai.com/v1', 'stt', 'tts']))}
    if invalid == 'expired':
        runtime['auth_expires_at'] = '2000-01-01T00:00:00+00:00'
    elif invalid == 'other_hostname':
        runtime['hostname'] = 'lv02.test.example'
    else:
        runtime['speech']['API_KEY'] = 'forbidden-agent-placeholder'
    path = tmp_path / 'runtime.json'
    path.write_text(json.dumps(runtime))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        module.load_runtime(path)
    assert snapshot(tmp_path) == before
