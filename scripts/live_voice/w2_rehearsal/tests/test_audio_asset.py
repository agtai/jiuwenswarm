from __future__ import annotations

import hashlib
import json
from pathlib import Path
import wave


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "voice-command-48k-mono-pcm16.wav"
MANIFEST = ROOT / "assets" / "manifest.json"


def test_prepared_wav_matches_portable_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    content = ASSET.read_bytes()
    assert len(content) == manifest["bytes"]
    assert hashlib.sha256(content).hexdigest() == manifest["sha256"]
    with wave.open(str(ASSET)) as wav:
        assert wav.getnchannels() == manifest["channels"]
        assert wav.getframerate() == manifest["sample_rate_hz"]
        assert wav.getsampwidth() == manifest["sample_width_bytes"]
        assert wav.getnframes() == manifest["frame_count"]


def test_prepared_wav_is_explicitly_diagnostic_only() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["gate_credit"] is False
    assert manifest["spoken_command"] == "请回复：语音联调成功。"
