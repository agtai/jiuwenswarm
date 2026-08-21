from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[3]
SUPPORT_PATH = ROOT / "scripts" / "live_voice" / "vad_eot_benchmark_support.py"
BUILDER_PATH = ROOT / "scripts" / "live_voice" / "prepare_vad_eot_corpus.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_source(path: Path) -> tuple[int, ...]:
    first_clause = (1200, -1200) * 1200
    boundary = (0,) * 960
    second_clause = (1800, -1800) * 1200
    final_silence = (0,) * 96_000
    samples = first_clause + boundary + second_clause + final_silence
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48_000)
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return samples


def _expectation(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "expected_normalized_transcript": "first clause second clause",
                "required_post_pause_tokens": ["second", "clause"],
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def test_prepare_derives_only_declared_pause_and_preserves_source(tmp_path: Path) -> None:
    support = _load(SUPPORT_PATH, "vad_support_derivation")
    source = tmp_path / "source.wav"
    source_samples = _write_source(source)
    expectation = tmp_path / "expectation.json"
    _expectation(expectation)
    output_root = tmp_path / "vad-en-v1"
    split_frame = 2400 + 480

    manifest = support.prepare_vad_corpus(
        support.PrepareVadCorpusRequest(
            source_wav=source,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            output_root=output_root,
            corpus_id="vad-en-v1",
            split_frame=split_frame,
            expectation_json=expectation,
        )
    )

    assert [case.pause_ms for case in manifest.cases] == [0, 300, 600, 1000]
    for case in manifest.cases:
        derived = support.read_pcm16_mono_wav(case.wav_path).samples
        pause_samples = case.pause_ms * 48
        assert derived[:split_frame] == source_samples[:split_frame]
        assert derived[split_frame : split_frame + pause_samples] == (0,) * pause_samples
        assert derived[split_frame + pause_samples :] == source_samples[split_frame:]
        assert case.second_clause_first_frame == split_frame + pause_samples
        assert case.final_voiced_frame == 5760 + pause_samples
        assert hashlib.sha256(case.wav_path.read_bytes()).hexdigest() == case.wav_sha256
        assert stat.S_IMODE(case.wav_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((output_root / "manifest.json").stat().st_mode) == 0o600
    assert support.load_vad_corpus_manifest(output_root / "manifest.json") == manifest


def test_manifest_is_closed_hash_bound_and_path_confined(tmp_path: Path) -> None:
    support = _load(SUPPORT_PATH, "vad_support_manifest")
    source = tmp_path / "source.wav"
    _write_source(source)
    expectation = tmp_path / "expectation.json"
    _expectation(expectation)
    request = support.PrepareVadCorpusRequest(
        source_wav=source,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        output_root=tmp_path / "valid",
        corpus_id="vad-en-v1",
        split_frame=2880,
        expectation_json=expectation,
    )
    support.prepare_vad_corpus(request)
    manifest_path = request.output_root / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))

    for mutation in (
        {**raw, "unexpected": True},
        {**raw, "split_frame": False},
        {**raw, "cases": [*raw["cases"], raw["cases"][0]]},
        {**raw, "cases": [{**raw["cases"][0], "wav_path": "../escape.wav"}, *raw["cases"][1:]]},
        {**raw, "cases": [{**raw["cases"][0], "sha256": "0" * 64}, *raw["cases"][1:]]},
    ):
        invalid = tmp_path / f"invalid-{len(list(tmp_path.glob('invalid-*')))}.json"
        invalid.write_text(json.dumps(mutation), encoding="utf-8")
        with pytest.raises(ValueError, match="VAD_CORPUS_MANIFEST_INVALID"):
            support.load_vad_corpus_manifest(invalid)


@pytest.mark.parametrize(
    ("channels", "width", "rate"),
    ((2, 2, 48_000), (1, 1, 48_000), (1, 2, 44_100)),
)
def test_noncanonical_wav_is_rejected(
    tmp_path: Path, channels: int, width: int, rate: int
) -> None:
    support = _load(SUPPORT_PATH, f"vad_support_wav_{channels}_{width}_{rate}")
    wav_path = tmp_path / "invalid.wav"
    with wave.open(str(wav_path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(b"\0" * channels * width * 100)
    with pytest.raises(ValueError, match="VAD_CORPUS_WAV_INVALID"):
        support.read_pcm16_mono_wav(wav_path)


def test_transcript_normalization_is_unicode_and_punctuation_stable() -> None:
    support = _load(SUPPORT_PATH, "vad_support_normalize")
    assert support.normalize_transcript("  PARIS—Café, № ２!  ") == "paris café no 2"


def test_builder_cli_reads_private_expectation_file_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.wav"
    _write_source(source)
    expectation = tmp_path / "expectation.json"
    _expectation(expectation)
    output_root = tmp_path / "vad-en-v1"
    argv = [
        sys.executable,
        str(BUILDER_PATH),
        "--source-wav",
        str(source.resolve()),
        "--source-sha256",
        hashlib.sha256(source.read_bytes()).hexdigest(),
        "--output-root",
        str(output_root.resolve()),
        "--corpus-id",
        "vad-en-v1",
        "--split-frame",
        "2880",
        "--private-expectation-json",
        str(expectation.resolve()),
    ]

    completed = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    assert completed.stdout == '{"corpus_id":"vad-en-v1"}\n'
    assert completed.stderr == ""
    assert "first clause" not in completed.stdout

    repeated = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
    assert repeated.returncode != 0
    assert repeated.stdout == ""
    assert repeated.stderr == "VAD_EOT_CORPUS_FAILED\n"
    assert "first clause" not in repeated.stderr


def test_private_expectation_permissions_and_open_fields_fail_before_output(
    tmp_path: Path,
) -> None:
    support = _load(SUPPORT_PATH, "vad_support_expectation")
    source = tmp_path / "source.wav"
    _write_source(source)
    expectation = tmp_path / "expectation.json"
    expectation.write_text(
        json.dumps(
            {
                "expected_normalized_transcript": "private",
                "required_post_pause_tokens": ["private"],
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )
    expectation.chmod(0o644)
    output_root = tmp_path / "vad-en-v1"
    request = support.PrepareVadCorpusRequest(
        source_wav=source,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        output_root=output_root,
        corpus_id="vad-en-v1",
        split_frame=2880,
        expectation_json=expectation,
    )

    with pytest.raises(ValueError, match="VAD_CORPUS_EXPECTATION_INVALID"):
        support.prepare_vad_corpus(request)
    assert not output_root.exists()


def test_wrong_source_hash_or_non_low_energy_split_creates_nothing(tmp_path: Path) -> None:
    support = _load(SUPPORT_PATH, "vad_support_source")
    source = tmp_path / "source.wav"
    _write_source(source)
    expectation = tmp_path / "expectation.json"
    _expectation(expectation)
    for index, (digest, split_frame) in enumerate((("0" * 64, 2880), (hashlib.sha256(source.read_bytes()).hexdigest(), 100))):
        output_root = tmp_path / f"output-{index}"
        request = support.PrepareVadCorpusRequest(
            source_wav=source,
            source_sha256=digest,
            output_root=output_root,
            corpus_id="vad-en-v1",
            split_frame=split_frame,
            expectation_json=expectation,
        )
        with pytest.raises(ValueError):
            support.prepare_vad_corpus(request)
        assert not output_root.exists()
