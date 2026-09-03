"""Configuration selection must never redirect mutable runtime ownership."""

import pytest

from jiuwenswarm.common import utils


@pytest.mark.parametrize("selection", [None, "", "  "])
def test_default_configuration_stays_compatible(tmp_path, monkeypatch, selection):
    runtime = tmp_path / "runtime-config"
    monkeypatch.setattr(utils, "get_config_dir", lambda: runtime)
    if selection is None:
        monkeypatch.delenv("JIUWENSWARM_CONFIG_DIR", raising=False)
    else:
        monkeypatch.setenv("JIUWENSWARM_CONFIG_DIR", selection)
    assert utils.get_config_file() == runtime / "config.yaml"
    assert utils.get_env_file() == runtime / ".env"
    assert utils.get_runtime_state_path("one") == runtime / "runtime_state" / "one.yaml"
    assert not runtime.exists()


def test_explicit_configuration_is_read_in_place_runtime_stays_isolated(tmp_path, monkeypatch):
    configuration = tmp_path / "private-config"
    configuration.mkdir()
    source = configuration / "config.yaml"
    source.write_text("models: {}\n", encoding="utf-8")
    original = source.read_bytes()
    runtime = tmp_path / "isolated-runtime" / "config"
    monkeypatch.setattr(utils, "get_config_dir", lambda: runtime)
    monkeypatch.setenv("JIUWENSWARM_CONFIG_DIR", str(configuration))
    assert utils.get_config_file() == source
    assert utils.get_env_file() == configuration / ".env"
    assert utils.get_config_dir() == runtime
    assert utils.get_runtime_state_path("one") == runtime / "runtime_state" / "one.yaml"
    assert source.read_bytes() == original
    assert sorted(path.name for path in configuration.iterdir()) == ["config.yaml"]
    assert not runtime.exists()


@pytest.mark.parametrize("kind", ["relative", "missing", "file"])
def test_invalid_explicit_selection_never_silently_falls_back(tmp_path, monkeypatch, kind):
    candidate = tmp_path / kind
    if kind == "file":
        candidate.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("JIUWENSWARM_CONFIG_DIR", "relative" if kind == "relative" else str(candidate))
    monkeypatch.setattr(utils, "get_config_dir", lambda: pytest.fail("unexpected fallback"))
    for reader in (utils.get_config_file, utils.get_env_file):
        with pytest.raises(ValueError, match="existing absolute directory"):
            reader()


def test_uninitialized_runtime_with_external_configuration_never_uses_resources(tmp_path, monkeypatch):
    configuration = tmp_path / "private-config"
    configuration.mkdir()
    (configuration / "config.yaml").write_text("models: {}\n", encoding="utf-8")
    runtime = tmp_path / "fresh-runtime"
    monkeypatch.setattr(utils, "_initialized", False)
    for cache in ("_config_dir", "_workspace_dir", "_root_dir"):
        monkeypatch.setattr(utils, cache, None)
    monkeypatch.setattr(utils, "get_user_workspace_dir", lambda: runtime)
    monkeypatch.setattr(utils, "_find_package_root", lambda: pytest.fail("package fallback forbidden"))
    monkeypatch.setattr(utils, "_find_source_root", lambda: pytest.fail("source fallback forbidden"))
    monkeypatch.setenv("JIUWENSWARM_CONFIG_DIR", str(configuration))
    assert utils.get_config_dir() == runtime / "config"
    assert utils.get_workspace_dir() == runtime / "agent" / "workspace"
    assert utils.get_root_dir() == runtime
    assert utils.get_runtime_state_path("isolated") == runtime / "config/runtime_state/isolated.yaml"
    assert utils.get_config_file() == configuration / "config.yaml"
    assert utils.get_env_file() == configuration / ".env"
    assert not runtime.exists()
    assert (configuration / "config.yaml").read_text(encoding="utf-8") == "models: {}\n"
