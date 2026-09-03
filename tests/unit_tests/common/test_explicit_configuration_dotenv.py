from jiuwenswarm.dotenv_early import load_dotenv_runtime


def test_explicit_configuration_cannot_replace_instance_policy(tmp_path, monkeypatch):
    source = tmp_path / ".env"
    source.write_text("JIUWENSWARM_ENABLE_ORIGIN_CHECK=0\nWEB_PORT=19000\nAUDIO_TEST_MISSING=provided\n", encoding="utf-8")
    original = source.read_bytes()
    monkeypatch.setenv("JIUWENSWARM_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "1")
    monkeypatch.setenv("WEB_PORT", "19100")
    monkeypatch.delenv("AUDIO_TEST_MISSING", raising=False)
    import os
    assert load_dotenv_runtime(source, override=True)
    assert os.environ["JIUWENSWARM_ENABLE_ORIGIN_CHECK"] == "1"
    assert os.environ["WEB_PORT"] == "19100"
    assert os.environ["AUDIO_TEST_MISSING"] == "provided"
    assert source.read_bytes() == original
    monkeypatch.delenv("AUDIO_TEST_MISSING")


def test_unselected_legacy_dotenv_keeps_override_contract(tmp_path, monkeypatch):
    source = tmp_path / ".env"
    source.write_text("AUDIO_TEST_VALUE=from_file\n", encoding="utf-8")
    monkeypatch.delenv("JIUWENSWARM_CONFIG_DIR", raising=False)
    monkeypatch.setenv("AUDIO_TEST_VALUE", "process")
    import os
    assert load_dotenv_runtime(source, override=True)
    assert os.environ["AUDIO_TEST_VALUE"] == "from_file"
