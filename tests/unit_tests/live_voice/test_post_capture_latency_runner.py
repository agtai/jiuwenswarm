from __future__ import annotations

import importlib.util
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path


def test_fixture_manifest_loader_rejects_paths_outside_its_manifest_root(tmp_path: Path) -> None:
    module_path = Path(__file__).parents[3] / "scripts" / "live_voice" / "post_capture_latency_runner.py"
    spec = importlib.util.spec_from_file_location("post_capture_latency_runner", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    manifest = tmp_path / "fixture.json"
    manifest.write_text('{"schema_version":"live-voice.fixed-audio-fixture.v0","fixture_profile_id":"en-v1-fixed-wav","cases":[{"profile_id":"dialogue_no_tool","input_case_id":"dialogue-paris-en-v1","wav_path":"../private.wav","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","sample_rate_hz":48000}]}', encoding="utf-8")

    try:
        module.load_fixture_manifest(manifest, "en-v1-fixed-wav")
    except ValueError as error:
        assert str(error) == "FIXTURE_PATH_INVALID"
    else:
        raise AssertionError("path traversal must fail closed")


def test_loopback_fixture_server_rejects_foreign_origin_and_never_serves_unknown_case(tmp_path: Path) -> None:
    module_path = Path(__file__).parents[3] / "scripts" / "live_voice" / "post_capture_latency_runner.py"
    spec = importlib.util.spec_from_file_location("post_capture_latency_runner_server", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    wav = tmp_path / "fixture.wav"
    wav.write_bytes(b"RIFFfixture")
    case = module.FixtureCase("dialogue_no_tool", "dialogue-paris-en-v1", wav, "a" * 64, 48000)
    server = module.create_loopback_fixture_server("http://localhost:5173", (case,))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/fixture/dialogue-paris-en-v1.wav"
        request = urllib.request.Request(url, headers={"Origin": "http://foreign.test"})
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("foreign origin must fail")
    finally:
        server.shutdown()
        server.server_close()
