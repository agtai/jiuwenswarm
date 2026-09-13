"""Selected configuration is read-only, including normal/fallback launches."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from jiuwenswarm import start_services
from jiuwenswarm.dotenv_early import load_dotenv_runtime


@pytest.mark.parametrize("fallback", [False, True])
def test_selected_configuration_ports_inherit_without_shared_writes(tmp_path, monkeypatch, fallback):
    config = tmp_path / "shared"
    config.mkdir()
    source = config / ".env"
    source.write_text("GATEWAY_PORT=1\nWEB_PORT=2\nAGENT_SERVER_PORT=3\nFRONTEND_PORT=4\n", encoding="utf-8")
    before = source.read_bytes()
    monkeypatch.setenv("JIUWENSWARM_CONFIG_DIR", str(config))
    monkeypatch.setattr(start_services, "get_env_file", lambda: source)
    monkeypatch.setattr("jiuwenswarm.instance_manager.config._upsert_env_ports",
                        lambda *args: pytest.fail("shared configuration write forbidden"))
    ports = {"agent_server": 18092, "web": 19000, "gateway": 19001, "frontend": 5173}
    resolved = {key: value + 1000 for key, value in ports.items()} if fallback else ports
    command = SimpleNamespace(is_default=True, name="default", config=start_services.InstanceConfig(
        name="default", workspace=tmp_path / "runtime", ports=ports))
    if fallback:
        monkeypatch.setattr(start_services, "is_port_available", lambda *args: False)
        monkeypatch.setattr("jiuwenswarm.instance_manager.collect_all_ports", lambda **kwargs: [])
        monkeypatch.setattr(start_services, "find_available_ports", lambda **kwargs: (resolved, 1))
        assert start_services._resolve_ports_with_fallback(command) is None
    assert start_services._sync_default_env_ports(command.config.ports) is None
    captured = {}

    def popen(*args, **kwargs):
        captured.update(kwargs["env"])
        return MagicMock()

    monkeypatch.setattr(start_services.subprocess, "Popen", popen)
    start_services._start_process("app", ["python", "-m", "jiuwenswarm.app"], tmp_path,
                                  ports=command.config.ports)
    for key, value in captured.items():
        monkeypatch.setenv(key, value)
    load_dotenv_runtime(source, override=True)
    import os
    for key, variable in start_services.PORT_ENV_NAMES.items():
        assert os.environ[variable] == str(resolved[key])
    assert source.read_bytes() == before
