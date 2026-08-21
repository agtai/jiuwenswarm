"""Private, hash-bound corpus support for the no-Browser VAD benchmark."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import struct
import unicodedata
import wave
from dataclasses import dataclass, field
from pathlib import Path


CORPUS_SCHEMA_VERSION = "live-voice.vad-eot-corpus.v0"
SAMPLE_RATE_HZ = 48_000
CHANNEL_COUNT = 1
SAMPLE_WIDTH_BYTES = 2
FINAL_SILENCE_MS = 2_000
PAUSES_MS = (0, 300, 600, 1_000)
CASE_IDS = (
    "no-internal-pause",
    "internal-pause-300",
    "internal-pause-600",
    "internal-pause-1000",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "corpus_id",
        "source_wav",
        "source_sha256",
        "split_frame",
        "sample_rate_hz",
        "channel_count",
        "sample_width_bytes",
        "final_silence_ms",
        "expected_normalized_transcript",
        "required_post_pause_tokens",
        "cases",
    }
)
_CASE_KEYS = frozenset(
    {
        "case_id",
        "pause_ms",
        "wav_path",
        "sha256",
        "final_voiced_frame",
        "second_clause_first_frame",
    }
)
_EXPECTATION_KEYS = frozenset(
    {"expected_normalized_transcript", "required_post_pause_tokens"}
)


@dataclass(frozen=True, slots=True)
class Pcm16MonoWav:
    samples: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class VadCorpusCase:
    case_id: str
    pause_ms: int
    wav_path: Path
    wav_sha256: str
    final_voiced_frame: int
    second_clause_first_frame: int
    expected_normalized_transcript: str = field(repr=False)
    required_post_pause_tokens: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VadCorpusManifest:
    schema_version: str
    corpus_id: str
    source_sha256: str
    split_frame: int
    cases: tuple[VadCorpusCase, ...]


@dataclass(frozen=True, slots=True)
class PrepareVadCorpusRequest:
    source_wav: Path
    source_sha256: str
    output_root: Path
    corpus_id: str
    split_frame: int
    expectation_json: Path = field(repr=False)


def normalize_transcript(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("VAD_CORPUS_EXPECTATION_INVALID")
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if category.startswith(("L", "N")):
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return " ".join(tokens)


def _private_regular_file(path: Path) -> bool:
    try:
        facts = path.stat()
    except OSError:
        return False
    return stat.S_ISREG(facts.st_mode) and stat.S_IMODE(facts.st_mode) & 0o077 == 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(64 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise ValueError("VAD_CORPUS_FILE_INVALID") from error
    return digest.hexdigest()


def read_pcm16_mono_wav(path: Path) -> Pcm16MonoWav:
    if not isinstance(path, Path) or not path.is_absolute() or not path.is_file():
        raise ValueError("VAD_CORPUS_WAV_INVALID")
    try:
        with wave.open(str(path), "rb") as source:
            if (
                source.getnchannels() != CHANNEL_COUNT
                or source.getsampwidth() != SAMPLE_WIDTH_BYTES
                or source.getframerate() != SAMPLE_RATE_HZ
                or source.getcomptype() != "NONE"
            ):
                raise ValueError("VAD_CORPUS_WAV_INVALID")
            frame_count = source.getnframes()
            if frame_count <= 0 or frame_count > SAMPLE_RATE_HZ * 120:
                raise ValueError("VAD_CORPUS_WAV_INVALID")
            payload = source.readframes(frame_count)
            if source.readframes(1):
                raise ValueError("VAD_CORPUS_WAV_INVALID")
    except (EOFError, wave.Error) as error:
        raise ValueError("VAD_CORPUS_WAV_INVALID") from error
    if len(payload) != frame_count * SAMPLE_WIDTH_BYTES:
        raise ValueError("VAD_CORPUS_WAV_INVALID")
    return Pcm16MonoWav(struct.unpack(f"<{frame_count}h", payload))


def _require_exact_dict(value: object, keys: frozenset[str], reason: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(reason)
    return value


def _required_int(value: object, *, minimum: int, maximum: int, reason: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(reason)
    return value


def _load_expectation(path: Path) -> tuple[str, tuple[str, ...]]:
    if not isinstance(path, Path) or not path.is_absolute() or not _private_regular_file(path):
        raise ValueError("VAD_CORPUS_EXPECTATION_INVALID")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("VAD_CORPUS_EXPECTATION_INVALID") from error
    record = _require_exact_dict(raw, _EXPECTATION_KEYS, "VAD_CORPUS_EXPECTATION_INVALID")
    expected = normalize_transcript(record["expected_normalized_transcript"])
    raw_tokens = record["required_post_pause_tokens"]
    if not expected or type(raw_tokens) is not list or not raw_tokens:
        raise ValueError("VAD_CORPUS_EXPECTATION_INVALID")
    tokens = tuple(normalize_transcript(token) for token in raw_tokens)
    if any(not token or " " in token for token in tokens) or len(set(tokens)) != len(tokens):
        raise ValueError("VAD_CORPUS_EXPECTATION_INVALID")
    if any(token not in expected.split() for token in tokens):
        raise ValueError("VAD_CORPUS_EXPECTATION_INVALID")
    return expected, tokens


def _validate_request(request: PrepareVadCorpusRequest) -> None:
    if not isinstance(request, PrepareVadCorpusRequest):
        raise ValueError("VAD_CORPUS_REQUEST_INVALID")
    if (
        not request.source_wav.is_absolute()
        or not request.expectation_json.is_absolute()
        or not request.output_root.is_absolute()
        or request.output_root.exists()
        or not _SHA256.fullmatch(request.source_sha256)
        or not _PUBLIC_ID.fullmatch(request.corpus_id)
        or type(request.split_frame) is not int
        or request.split_frame <= 480
    ):
        raise ValueError("VAD_CORPUS_REQUEST_INVALID")


def _validate_source(request: PrepareVadCorpusRequest) -> tuple[Pcm16MonoWav, int]:
    if _sha256_file(request.source_wav) != request.source_sha256:
        raise ValueError("VAD_CORPUS_SOURCE_HASH_MISMATCH")
    decoded = read_pcm16_mono_wav(request.source_wav)
    samples = decoded.samples
    split = request.split_frame
    if split + 480 >= len(samples):
        raise ValueError("VAD_CORPUS_SPLIT_INVALID")
    if max(abs(sample) for sample in samples[split - 480 : split + 480]) > 512:
        raise ValueError("VAD_CORPUS_SPLIT_INVALID")
    if not any(abs(sample) > 512 for sample in samples[split + 480 : -96_000]):
        raise ValueError("VAD_CORPUS_SPLIT_INVALID")
    if len(samples) < 96_000 or any(samples[-96_000:]):
        raise ValueError("VAD_CORPUS_FINAL_SILENCE_INVALID")
    final_voiced = next(
        (index + 1 for index in range(len(samples) - 1, -1, -1) if samples[index]),
        0,
    )
    if final_voiced <= split:
        raise ValueError("VAD_CORPUS_SPLIT_INVALID")
    return decoded, final_voiced


def _write_wav(path: Path, samples: tuple[int, ...]) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(CHANNEL_COUNT)
        output.setsampwidth(SAMPLE_WIDTH_BYTES)
        output.setframerate(SAMPLE_RATE_HZ)
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    path.chmod(0o600)


def prepare_vad_corpus(request: PrepareVadCorpusRequest) -> VadCorpusManifest:
    _validate_request(request)
    expected, required_tokens = _load_expectation(request.expectation_json)
    decoded, final_voiced = _validate_source(request)
    created: list[Path] = []
    root_created = False
    try:
        request.output_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        root_created = True
        cases: list[dict[str, object]] = []
        for case_id, pause_ms in zip(CASE_IDS, PAUSES_MS, strict=True):
            pause_samples = pause_ms * 48
            samples = (
                decoded.samples[: request.split_frame]
                + (0,) * pause_samples
                + decoded.samples[request.split_frame :]
            )
            output_path = request.output_root / f"{case_id}.wav"
            _write_wav(output_path, samples)
            created.append(output_path)
            cases.append(
                {
                    "case_id": case_id,
                    "pause_ms": pause_ms,
                    "wav_path": output_path.name,
                    "sha256": _sha256_file(output_path),
                    "final_voiced_frame": final_voiced + pause_samples,
                    "second_clause_first_frame": request.split_frame + pause_samples,
                }
            )
        manifest_raw = {
            "schema_version": CORPUS_SCHEMA_VERSION,
            "corpus_id": request.corpus_id,
            "source_wav": request.source_wav.name,
            "source_sha256": request.source_sha256,
            "split_frame": request.split_frame,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "channel_count": CHANNEL_COUNT,
            "sample_width_bytes": SAMPLE_WIDTH_BYTES,
            "final_silence_ms": FINAL_SILENCE_MS,
            "expected_normalized_transcript": expected,
            "required_post_pause_tokens": list(required_tokens),
            "cases": cases,
        }
        manifest_path = request.output_root / "manifest.json"
        with manifest_path.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(manifest_raw, output, ensure_ascii=False, separators=(",", ":"))
            output.write("\n")
        manifest_path.chmod(0o600)
        created.append(manifest_path)
        return load_vad_corpus_manifest(manifest_path)
    except BaseException:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        if root_created:
            try:
                request.output_root.rmdir()
            except OSError:
                pass
        raise


def load_vad_corpus_manifest(path: Path) -> VadCorpusManifest:
    reason = "VAD_CORPUS_MANIFEST_INVALID"
    if not isinstance(path, Path) or not path.is_absolute() or not _private_regular_file(path):
        raise ValueError(reason)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(reason) from error
    record = _require_exact_dict(raw, _MANIFEST_KEYS, reason)
    if (
        record["schema_version"] != CORPUS_SCHEMA_VERSION
        or type(record["corpus_id"]) is not str
        or not _PUBLIC_ID.fullmatch(record["corpus_id"])
        or type(record["source_wav"]) is not str
        or Path(record["source_wav"]).name != record["source_wav"]
        or type(record["source_sha256"]) is not str
        or not _SHA256.fullmatch(record["source_sha256"])
        or record["sample_rate_hz"] != SAMPLE_RATE_HZ
        or record["channel_count"] != CHANNEL_COUNT
        or record["sample_width_bytes"] != SAMPLE_WIDTH_BYTES
        or record["final_silence_ms"] != FINAL_SILENCE_MS
    ):
        raise ValueError(reason)
    split_frame = _required_int(record["split_frame"], minimum=1, maximum=1 << 31, reason=reason)
    expected = normalize_transcript(record["expected_normalized_transcript"])
    raw_tokens = record["required_post_pause_tokens"]
    raw_cases = record["cases"]
    if (
        not expected
        or type(raw_tokens) is not list
        or not raw_tokens
        or type(raw_cases) is not list
        or len(raw_cases) != 4
    ):
        raise ValueError(reason)
    tokens = tuple(normalize_transcript(token) for token in raw_tokens)
    if any(not token or " " in token for token in tokens) or len(set(tokens)) != len(tokens):
        raise ValueError(reason)
    cases: list[VadCorpusCase] = []
    for index, raw_case in enumerate(raw_cases):
        case = _require_exact_dict(raw_case, _CASE_KEYS, reason)
        case_id = case["case_id"]
        pause_ms = case["pause_ms"]
        relative = case["wav_path"]
        digest = case["sha256"]
        if (
            case_id != CASE_IDS[index]
            or pause_ms != PAUSES_MS[index]
            or type(relative) is not str
            or Path(relative).name != relative
            or type(digest) is not str
            or not _SHA256.fullmatch(digest)
        ):
            raise ValueError(reason)
        wav_path = (path.parent / relative).resolve()
        if wav_path.parent != path.parent.resolve() or not _private_regular_file(wav_path):
            raise ValueError(reason)
        if _sha256_file(wav_path) != digest:
            raise ValueError(reason)
        decoded = read_pcm16_mono_wav(wav_path)
        final_voiced = _required_int(case["final_voiced_frame"], minimum=1, maximum=len(decoded.samples), reason=reason)
        second_clause = _required_int(case["second_clause_first_frame"], minimum=split_frame, maximum=final_voiced, reason=reason)
        if any(decoded.samples[-96_000:]):
            raise ValueError(reason)
        cases.append(
            VadCorpusCase(
                case_id=case_id,
                pause_ms=pause_ms,
                wav_path=wav_path,
                wav_sha256=digest,
                final_voiced_frame=final_voiced,
                second_clause_first_frame=second_clause,
                expected_normalized_transcript=expected,
                required_post_pause_tokens=tokens,
            )
        )
    return VadCorpusManifest(
        schema_version=CORPUS_SCHEMA_VERSION,
        corpus_id=record["corpus_id"],
        source_sha256=record["source_sha256"],
        split_frame=split_frame,
        cases=tuple(cases),
    )


__all__ = [
    "PrepareVadCorpusRequest",
    "VadCorpusCase",
    "VadCorpusManifest",
    "load_vad_corpus_manifest",
    "normalize_transcript",
    "prepare_vad_corpus",
    "read_pcm16_mono_wav",
]
