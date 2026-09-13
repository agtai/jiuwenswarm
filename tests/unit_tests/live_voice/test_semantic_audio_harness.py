"""Test-controller safety only, not proof of real audio or business execution."""

import hashlib
import pytest
from scripts.live_voice.semantic_audio_browser import (
    read_sample_audio,
    validate_target_url,
)


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:6173/chat/test", "http://localhost:6173", "http://[::1]:6173"],
)
def test_owned_browser_accepts_explicit_loopback(url):
    assert validate_target_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com:6173",
        "http://127.0.0.1",
        "http://user:secret@127.0.0.1:6173",
        "http://127.0.0.1:6173#secret",
        "file:///C:/Users/admin/private.txt",
        "http://127.0.0.1:99999",
    ],
)
def test_owned_browser_rejects_external_or_ambiguous_target(url):
    with pytest.raises(ValueError):
        validate_target_url(url)


def test_sample_digest_and_path_are_checked_before_browser_injection(tmp_path):
    root = tmp_path / "audio"
    root.mkdir()
    content = b"test-only WAV bytes, never injected"
    path = root / "sample.wav"
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    assert read_sample_audio(root, {"file": "sample.wav", "sha256": digest}) == content
    for relative in ("../outside.wav", str(path.resolve()), "sample.txt"):
        with pytest.raises(ValueError):
            read_sample_audio(root, {"file": relative, "sha256": digest})
    with pytest.raises(ValueError, match="digest"):
        read_sample_audio(root, {"file": "sample.wav", "sha256": "0" * 64})
    assert path.read_bytes() == content
