# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Coordinate source-bound D-095 samples in an ordinary installed Chrome.

The loopback server exposes only a nonce-bound, content-free job contract and
three in-memory fixed-corpus speech fixtures.  It never retains audio,
recognized text, prompts, credentials, device identity, URLs, or project
content.  The Browser digital milestones remain separate from the already
recorded human physical acceptance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import sys
import tempfile
import threading
from collections import Counter
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final, Mapping, Sequence
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jiuwenswarm.server.live_voice.latency_measurement import (  # noqa: E402
    L0_RUN_LABELS_VERSION,
    canonical_json_bytes,
    create_l0_measurement_envelope,
    load_l0_corpus_manifest,
)

try:  # noqa: E402
    from scripts.live_voice.l0_measurement_baseline import (
        aggregate_jsonl,
        clean_source_head,
    )
except ModuleNotFoundError as error:  # pragma: no cover - direct script import
    if error.name not in {"scripts", "scripts.live_voice"}:
        raise
    from l0_measurement_baseline import aggregate_jsonl, clean_source_head


BATCH_SESSION_VERSION: Final = "live-voice.l0-ordinary-batch.v1"
BATCH_JOB_VERSION: Final = "live-voice.l0-ordinary-job.v1"
BATCH_COMPLETION_VERSION: Final = "live-voice.l0-ordinary-completion.v1"
BATCH_ATTEMPT_VERSION: Final = "live-voice.l0-ordinary-attempt.v1"
BATCH_REPORT_VERSION: Final = "live-voice.l0-d095-report.v1"
BROWSER_SESSION_VERSION: Final = "live-voice.l0-ordinary-browser-session.v1"
DEFAULT_CORPUS: Final = Path(__file__).with_name("l0_fixed_corpus.json")
DEFAULT_ORIGIN: Final = "http://localhost:5173"
MAX_REQUEST_BYTES: Final = 16 * 1024 * 1024
MAX_ATTEMPTS_PER_METRIC: Final = 40
METRICS: Final = ("first_audio", "barge_in")
PROFILE_BY_TEMPERATURE: Final = {
    "cold": "ordinary-chrome-prerecorded-cold",
    "warm": "ordinary-chrome-prerecorded-warm",
}
SCENARIO_BY_METRIC: Final = {
    "first_audio": "short-no-tool-zh",
    "barge_in": "playout-barge-in-zh",
}
_SAFE_TOKEN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_HEX_32: Final = re.compile(r"^[0-9a-f]{32}$")
_HEX_40: Final = re.compile(r"^[0-9a-f]{40}$")
_HEX_64: Final = re.compile(r"^[0-9a-f]{64}$")

_ATTEMPT_KEYS: Final = frozenset(
    {
        "schema_version",
        "epoch_id",
        "temperature",
        "metric",
        "profile_id",
        "scenario_id",
        "sample_index",
        "browser_record_count",
        "browser_dropped_record_count",
        "automated_browser_complete",
        "classification",
        "eligible",
        "reason",
    }
)


def _safe_token(value: object, field: str) -> str:
    if type(value) is not str or _SAFE_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field} is invalid")
    return value


def _atomic_json(path: Path, value: object) -> None:
    # Session metadata intentionally contains one machine-private local path.
    # It remains ignored runtime provenance and is never copied into the
    # sanitized report; use the strict canonical privacy scanner at the report
    # and measurement-record boundaries instead.
    encoded = (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("ascii")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _append_jsonl(path: Path, values: Sequence[object]) -> None:
    if not values:
        return
    with path.open("ab") as stream:
        for value in values:
            stream.write(canonical_json_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if type(value) is not dict:
        raise ValueError(f"{path.name} must contain one object")
    return value


def _load_attempts(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    if not path.is_file() or path.stat().st_size > MAX_REQUEST_BYTES:
        raise ValueError("batch attempt evidence is unavailable or oversized")
    attempts: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line:
            raise ValueError("batch attempt evidence contains an empty record")
        value = json.loads(line)
        if type(value) is not dict or set(value) != _ATTEMPT_KEYS:
            raise ValueError("batch attempt evidence has an invalid closed shape")
        if (
            value["schema_version"] != BATCH_ATTEMPT_VERSION
            or _HEX_32.fullmatch(str(value["epoch_id"])) is None
            or value["temperature"] not in {"cold", "warm"}
            or value["metric"] not in METRICS
            or _SAFE_TOKEN.fullmatch(str(value["profile_id"])) is None
            or _SAFE_TOKEN.fullmatch(str(value["scenario_id"])) is None
            or type(value["sample_index"]) is not int
            or int(value["sample_index"]) < 0
            or type(value["browser_record_count"]) is not int
            or int(value["browser_record_count"]) < 0
            or type(value["browser_dropped_record_count"]) is not int
            or int(value["browser_dropped_record_count"]) < 0
            or type(value["automated_browser_complete"]) is not bool
            or value["classification"]
            not in {"success", "failure", "fallback", "cancelled", "unknown"}
            or type(value["eligible"]) is not bool
            or _SAFE_TOKEN.fullmatch(str(value["reason"])) is None
        ):
            raise ValueError("batch attempt evidence contains invalid facts")
        temperature = str(value["temperature"])
        metric = str(value["metric"])
        if (
            value["profile_id"] != PROFILE_BY_TEMPERATURE[temperature]
            or value["scenario_id"] != SCENARIO_BY_METRIC[metric]
            or (
                value["eligible"] is True
                and (
                    value["automated_browser_complete"] is not True
                    or value["browser_dropped_record_count"] != 0
                    or value["reason"] != "eligible"
                    or value["classification"]
                    != ("success" if metric == "first_audio" else "cancelled")
                )
            )
            or (value["eligible"] is not True and value["reason"] == "eligible")
        ):
            raise ValueError("batch attempt evidence contains contradictory facts")
        attempts.append(value)
        if len(attempts) > 2 * MAX_ATTEMPTS_PER_METRIC * 2:
            raise ValueError("batch attempt evidence exceeds its bounded capacity")
    sample_keys = {
        (str(value["profile_id"]), int(value["sample_index"]))
        for value in attempts
    }
    if len(sample_keys) != len(attempts):
        raise ValueError("batch attempt evidence reuses a sample identity")
    return attempts


def _measurement_inputs(directory: Path) -> list[Path]:
    inputs = sorted(directory.glob("l0-*.jsonl"))
    browser = directory / "browser.jsonl"
    if browser.is_file():
        inputs.append(browser)
    return inputs


def _profile_group(
    aggregate: Mapping[str, object] | None,
    profile_id: str,
) -> Mapping[str, object] | None:
    if aggregate is None:
        return None
    profiles = aggregate.get("profiles")
    if type(profiles) is not list:
        return None
    matching = [
        value
        for value in profiles
        if type(value) is dict and value.get("profile_id") == profile_id
    ]
    return matching[0] if len(matching) == 1 else None


def _metric_percentile(
    group: Mapping[str, object] | None,
    metric: str,
    quantile: str,
) -> float | None:
    if group is None:
        return None
    percentiles = group.get("percentiles")
    if type(percentiles) is not dict:
        return None
    summary = percentiles.get(metric)
    if type(summary) is not dict:
        return None
    value = summary.get(quantile)
    return float(value) if type(value) in {int, float} else None


def _metric_sample_count(
    group: Mapping[str, object] | None,
    metric: str,
) -> int:
    if group is None:
        return 0
    percentiles = group.get("percentiles")
    summary = percentiles.get(metric) if type(percentiles) is dict else None
    value = summary.get("sample_count") if type(summary) is dict else None
    return int(value) if type(value) is int and value >= 0 else 0


def build_d095_report(
    *,
    aggregate: Mapping[str, object] | None,
    attempts: Sequence[Mapping[str, object]],
    source_head: str,
    environment_ref: str,
    configuration_sha256: str,
    corpus_sha256: str,
    target: int,
) -> dict[str, object]:
    """Build the sanitized D-095 result without retaining round identities."""

    profiles: list[dict[str, object]] = []
    by_temperature: dict[str, dict[str, object]] = {}
    for temperature in ("cold", "warm"):
        profile_id = PROFILE_BY_TEMPERATURE[temperature]
        group = _profile_group(aggregate, profile_id)
        temperature_attempts = [
            item for item in attempts if item["temperature"] == temperature
        ]
        first_attempts = [
            item for item in temperature_attempts if item["metric"] == "first_audio"
        ]
        barge_attempts = [
            item for item in temperature_attempts if item["metric"] == "barge_in"
        ]
        first_eligible = sum(item["eligible"] is True for item in first_attempts)
        barge_eligible = sum(item["eligible"] is True for item in barge_attempts)
        classifications = Counter(
            str(item["classification"]) for item in temperature_attempts
        )
        reasons = Counter(
            str(item["reason"])
            for item in temperature_attempts
            if item["eligible"] is not True
        )
        cold_epochs = {
            str(item["epoch_id"]) for item in temperature_attempts
        }
        epoch_unique = temperature != "cold" or len(cold_epochs) == len(
            temperature_attempts
        )
        first_metric = {
            "attempt_count": len(first_attempts),
            "eligible_count": first_eligible,
            "failure_count": sum(item["eligible"] is not True for item in first_attempts),
            "drop_count": sum(
                int(item["browser_dropped_record_count"]) for item in first_attempts
            ),
            "p50_ms": _metric_percentile(
                group, "speech_end_to_webaudio_started_ms", "p50_ms"
            ),
            "p95_ms": _metric_percentile(
                group, "speech_end_to_webaudio_started_ms", "p95_ms"
            ),
        }
        barge_metric = {
            "attempt_count": len(barge_attempts),
            "eligible_count": barge_eligible,
            "failure_count": sum(item["eligible"] is not True for item in barge_attempts),
            "drop_count": sum(
                int(item["browser_dropped_record_count"]) for item in barge_attempts
            ),
            "p50_ms": _metric_percentile(group, "stop_to_silence_ms", "p50_ms"),
            "p95_ms": _metric_percentile(group, "stop_to_silence_ms", "p95_ms"),
        }
        # The attempt oracle and generic aggregate must agree. A mismatch is an
        # anomaly and cannot be promoted to completion.
        aggregate_first = _metric_sample_count(
            group, "speech_end_to_webaudio_started_ms"
        )
        aggregate_barge = _metric_sample_count(group, "stop_to_silence_ms")
        counts_agree = (
            aggregate_first == first_eligible and aggregate_barge == barge_eligible
        )
        profile = {
            "profile_id": profile_id,
            "temperature": temperature,
            "first_audio": first_metric,
            "barge_in": barge_metric,
            "classification_counts": dict(sorted(classifications.items())),
            "anomaly_classifications": dict(sorted(reasons.items())),
            "cold_launcher_epoch_count": len(cold_epochs) if temperature == "cold" else None,
            "cold_launcher_epochs_unique": epoch_unique if temperature == "cold" else None,
            "aggregate_counts_agree": counts_agree,
            "complete": (
                first_eligible >= target
                and barge_eligible >= target
                and counts_agree
                and epoch_unique
            ),
        }
        profiles.append(profile)
        by_temperature[temperature] = profile

    def difference(metric: str, quantile: str) -> float | None:
        cold = by_temperature["cold"][metric]
        warm = by_temperature["warm"][metric]
        assert type(cold) is dict and type(warm) is dict
        cold_value = cold[quantile]
        warm_value = warm[quantile]
        if type(cold_value) not in {int, float} or type(warm_value) not in {
            int,
            float,
        }:
            return None
        return round(float(cold_value) - float(warm_value), 3)

    report = {
        "schema_version": BATCH_REPORT_VERSION,
        "source_head": source_head,
        "environment_ref": environment_ref,
        "configuration_sha256": configuration_sha256,
        "corpus_sha256": corpus_sha256,
        "browser_mode": "ordinary-installed-chrome",
        "evidence_source": "prerecorded",
        "target_per_temperature_and_metric": target,
        "profiles": profiles,
        "cold_minus_warm_ms": {
            "speech_end_to_webaudio_started_p50": difference(
                "first_audio", "p50_ms"
            ),
            "speech_end_to_webaudio_started_p95": difference(
                "first_audio", "p95_ms"
            ),
            "stop_to_silence_p50": difference("barge_in", "p50_ms"),
            "stop_to_silence_p95": difference("barge_in", "p95_ms"),
        },
        "complete": all(profile["complete"] is True for profile in profiles),
        "audio_retained": False,
        "recognized_text_retained": False,
        "physical_evidence": "not-claimed",
        "non_claims": [
            "prerecorded acoustic stimulus is not per-round operator confirmation",
            "WebAudio actually-started is not physical-first-audible",
            "Browser fence-cancel completion is not physical-silence",
            "the batch does not prove AEC, double-talk, device or room generalization",
        ],
    }
    canonical_json_bytes(report)
    return report


@dataclass(frozen=True, slots=True)
class BatchJob:
    job_id: str
    epoch_id: str
    temperature: str
    metric: str
    profile_id: str
    scenario_id: str
    sample_index: int

    @property
    def labels(self) -> dict[str, object]:
        return {
            "schema_version": L0_RUN_LABELS_VERSION,
            "profile_id": self.profile_id,
            "scenario_id": self.scenario_id,
            "sample_index": self.sample_index,
            "temperature": self.temperature,
            "evidence_source": "prerecorded",
        }

    def public(self) -> dict[str, object]:
        return {
            "schema_version": BATCH_JOB_VERSION,
            "job_id": self.job_id,
            "epoch_id": self.epoch_id,
            "temperature": self.temperature,
            "metric": self.metric,
            "labels": self.labels,
            "setup_audio": "short" if self.metric == "first_audio" else "long",
            "barge_audio": None if self.metric == "first_audio" else "barge",
        }


class OrdinaryChromeBatchState:
    def __init__(
        self,
        *,
        evidence_directory: Path,
        run_labels_file: Path,
        corpus_path: Path,
        source_head: str,
        environment_ref: str,
        configuration_sha256: str,
        browser_origin: str,
        nonce: str,
        temperature: str,
        epoch_id: str,
        target: int,
        audio_wav: Mapping[str, bytes],
    ) -> None:
        if temperature not in {"cold", "warm"}:
            raise ValueError("temperature is invalid")
        if _HEX_32.fullmatch(epoch_id) is None:
            raise ValueError("epoch identity is invalid")
        if _HEX_40.fullmatch(source_head) is None:
            raise ValueError("source HEAD is invalid")
        if _HEX_64.fullmatch(configuration_sha256) is None:
            raise ValueError("configuration digest is invalid")
        if _HEX_32.fullmatch(nonce) is None:
            raise ValueError("batch nonce is invalid")
        _safe_token(environment_ref, "environment_ref")
        if browser_origin != DEFAULT_ORIGIN:
            raise ValueError("ordinary Chrome origin is invalid")
        if type(target) is not int or target != 20:
            raise ValueError("success target is invalid")
        if set(audio_wav) != {"short", "long", "barge"} or any(
            type(value) is not bytes or not value for value in audio_wav.values()
        ):
            raise ValueError("fixed audio fixtures are unavailable")

        self.directory = evidence_directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.directory.is_dir():
            raise ValueError("evidence directory is unavailable")
        self.run_labels_file = run_labels_file.resolve()
        if self.run_labels_file.parent != self.directory:
            raise ValueError("run-label file escaped the evidence directory")
        self.corpus_path = corpus_path.resolve()
        self.manifest, self.corpus_sha256 = load_l0_corpus_manifest(self.corpus_path)
        self.source_head = source_head
        self.environment_ref = environment_ref
        self.configuration_sha256 = configuration_sha256
        self.browser_origin = browser_origin
        self.nonce = nonce
        self.temperature = temperature
        self.epoch_id = epoch_id
        self.target = target
        self.audio_wav = dict(audio_wav)
        self.profile_id = PROFILE_BY_TEMPERATURE[temperature]
        self.attempts_path = self.directory / "batch-attempts.ndjson"
        self.epochs_path = self.directory / "batch-epochs.ndjson"
        self.browser_path = self.directory / "browser.jsonl"
        self.report_path = self.directory / "d095-report.json"
        self.active_job: BatchJob | None = None
        self.epoch_attempted = False
        self.shutdown_requested = False
        self._lock = threading.RLock()
        self._initialize_metadata()
        self._write_disabled_labels()
        _append_jsonl(
            self.epochs_path,
            [
                {
                    "schema_version": BATCH_SESSION_VERSION,
                    "epoch_id": epoch_id,
                    "temperature": temperature,
                    "source_head": source_head,
                    "configuration_sha256": configuration_sha256,
                    "corpus_sha256": self.corpus_sha256,
                    "browser_mode": "ordinary-installed-chrome",
                }
            ],
        )

    @property
    def warmup_path(self) -> Path:
        return self.directory / "warmup-complete.json"

    def _initialize_metadata(self) -> None:
        metadata_path = self.directory / "browser-session.json"
        expected = {
            "schema_version": BROWSER_SESSION_VERSION,
            "source_head": self.source_head,
            "runtime_profile": "formal-web-validation",
            "evidence_directory": str(self.directory),
            "run_labels_file": str(self.run_labels_file),
            "browser_page_origin": self.browser_origin,
            "browser_mode": "ordinary-installed-chrome",
            "environment_ref": self.environment_ref,
            "configuration_sha256": self.configuration_sha256,
            "corpus_sha256": self.corpus_sha256,
            "physical_evidence": "not-claimed",
            "raw_audio_retained": False,
            "transcript_retained": False,
        }
        if metadata_path.exists():
            if _read_json(metadata_path) != expected:
                raise ValueError("existing ordinary-browser session provenance differs")
        else:
            _atomic_json(metadata_path, expected)

    def _write_disabled_labels(self) -> None:
        _atomic_json(
            self.run_labels_file,
            {
                "schema_version": L0_RUN_LABELS_VERSION,
                "measurement": "disabled",
            },
        )

    def _attempts(self) -> list[dict[str, object]]:
        return _load_attempts(self.attempts_path)

    def _counts(self) -> dict[str, int]:
        attempts = self._attempts()
        return {
            metric: sum(
                item["eligible"] is True
                for item in attempts
                if item["temperature"] == self.temperature
                and item["metric"] == metric
            )
            for metric in METRICS
        }

    def session(self) -> dict[str, object]:
        with self._lock:
            counts = self._counts()
            return {
                "schema_version": BATCH_SESSION_VERSION,
                "temperature": self.temperature,
                "epoch_id": self.epoch_id,
                "profile_id": self.profile_id,
                "target": self.target,
                "first_audio_eligible": counts["first_audio"],
                "barge_in_eligible": counts["barge_in"],
                "warmup_required": self.temperature == "warm" and not self.warmup_path.is_file(),
                "epoch_attempted": self.epoch_attempted,
                "batch_complete": all(counts[metric] >= self.target for metric in METRICS),
                "browser_mode": "ordinary-installed-chrome",
                "physical_evidence": "not-claimed",
            }

    def accept_warmup(self, value: object) -> dict[str, object]:
        with self._lock:
            if self.temperature != "warm":
                raise ValueError("cold epoch does not accept a warm-up")
            if type(value) is not dict or set(value) != {
                "schema_version",
                "automated_browser_complete",
                "browser_record_count",
                "browser_dropped_record_count",
            }:
                raise ValueError("warm-up has an invalid closed shape")
            if (
                value["schema_version"] != BATCH_COMPLETION_VERSION
                or value["automated_browser_complete"] is not True
                or type(value["browser_record_count"]) is not int
                or type(value["browser_dropped_record_count"]) is not int
                or value["browser_record_count"] != 0
                or value["browser_dropped_record_count"] != 0
            ):
                raise ValueError("warm-up is incomplete")
            _atomic_json(
                self.warmup_path,
                {
                    "schema_version": BATCH_SESSION_VERSION,
                    "temperature": "warm",
                    "warmup": "automated-complete-not-counted",
                    "source_head": self.source_head,
                    "configuration_sha256": self.configuration_sha256,
                    "corpus_sha256": self.corpus_sha256,
                },
            )
            return self.session()

    def next_job(self) -> dict[str, object]:
        with self._lock:
            if self.active_job is not None:
                return self.active_job.public()
            if self.temperature == "warm" and not self.warmup_path.is_file():
                raise RuntimeError("warm-up is required before measured samples")
            if self.temperature == "cold" and self.epoch_attempted:
                raise RuntimeError("cold launcher epoch already consumed its attempt")
            attempts = self._attempts()
            counts = self._counts()
            metric = next((item for item in METRICS if counts[item] < self.target), None)
            if metric is None:
                self.shutdown_requested = True
                return {
                    "schema_version": BATCH_JOB_VERSION,
                    "batch_complete": True,
                }
            metric_attempts = [
                item
                for item in attempts
                if item["temperature"] == self.temperature and item["metric"] == metric
            ]
            if len(metric_attempts) >= MAX_ATTEMPTS_PER_METRIC:
                self.shutdown_requested = True
                raise RuntimeError("metric attempt budget is exhausted")
            sample_indices = [
                int(item["sample_index"])
                for item in attempts
                if item["profile_id"] == self.profile_id
            ]
            sample_index = max(sample_indices, default=-1) + 1
            job = BatchJob(
                job_id=secrets.token_hex(16),
                epoch_id=self.epoch_id,
                temperature=self.temperature,
                metric=metric,
                profile_id=self.profile_id,
                scenario_id=SCENARIO_BY_METRIC[metric],
                sample_index=sample_index,
            )
            _atomic_json(self.run_labels_file, job.labels)
            self.active_job = job
            return job.public()

    def _aggregate(
        self,
        pending_browser_records: Sequence[Mapping[str, object]] = (),
    ) -> dict[str, object] | None:
        inputs = _measurement_inputs(self.directory)
        staged_browser_path: Path | None = None
        if pending_browser_records:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="live-voice-l0-browser-",
                suffix=".jsonl",
                dir=self.directory,
                delete=False,
            ) as stream:
                staged_browser_path = Path(stream.name)
                for record in pending_browser_records:
                    stream.write(canonical_json_bytes(record) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            inputs.append(staged_browser_path)
        if not inputs:
            return None
        try:
            return aggregate_jsonl(
                inputs=inputs,
                corpus_path=self.corpus_path,
                source_head=self.source_head,
                environment_ref=self.environment_ref,
            )
        finally:
            if staged_browser_path is not None:
                staged_browser_path.unlink(missing_ok=True)

    def complete(self, value: object) -> dict[str, object]:
        with self._lock:
            job = self.active_job
            if job is None:
                raise RuntimeError("no exact batch job is active")
            if type(value) is not dict or set(value) != {
                "schema_version",
                "job_id",
                "automated_browser_complete",
                "browser_dropped_record_count",
                "records",
                "failure_reason",
            }:
                raise ValueError("completion has an invalid closed shape")
            if (
                value["schema_version"] != BATCH_COMPLETION_VERSION
                or value["job_id"] != job.job_id
                or type(value["automated_browser_complete"]) is not bool
                or type(value["browser_dropped_record_count"]) is not int
                or value["browser_dropped_record_count"] < 0
                or type(value["records"]) is not list
                or len(value["records"]) > 4096
                or _SAFE_TOKEN.fullmatch(str(value["failure_reason"])) is None
            ):
                raise ValueError("completion contains invalid facts")

            checked_records = []
            for raw in value["records"]:
                record = create_l0_measurement_envelope(raw)
                if (
                    record.profile_id != job.profile_id
                    or record.scenario_id != job.scenario_id
                    or record.sample_index != job.sample_index
                    or record.temperature.value != job.temperature
                    or record.evidence_source.value != "prerecorded"
                ):
                    raise ValueError("completion record escaped the exact job labels")
                checked_records.append(record.to_dict())
            # Close dynamic backend labels before aggregation. A barge
            # utterance can become a successor response while a growing batch
            # is being aggregated; it must remain outside this completed
            # sample even if aggregation takes longer than that response.
            self._write_disabled_labels()

            # Aggregate the proposed completion before mutating durable
            # browser/attempt/report evidence. A correlation or provenance
            # rejection must not leave a half-committed evidence sample.
            aggregate = self._aggregate(checked_records)
            matching_round: Mapping[str, object] | None = None
            if aggregate is not None:
                rounds = aggregate.get("rounds")
                if type(rounds) is list:
                    matches = [
                        item
                        for item in rounds
                        if type(item) is dict
                        and item.get("profile_id") == job.profile_id
                        and item.get("scenario_id") == job.scenario_id
                        and item.get("sample_index") == job.sample_index
                    ]
                    if len(matches) == 1:
                        matching_round = matches[0]
            oracle_eligible = (
                matching_round is not None
                and value["automated_browser_complete"] is True
                and value["browser_dropped_record_count"] == 0
                and (
                    matching_round.get("success_eligible") is True
                    if job.metric == "first_audio"
                    else matching_round.get("cancel_eligible") is True
                )
            )
            classification = (
                str(matching_round.get("classification"))
                if matching_round is not None
                else "unknown"
            )
            failure_reason = str(value["failure_reason"])
            if oracle_eligible:
                reason = "eligible"
            elif value["browser_dropped_record_count"] > 0:
                reason = "browser_records_dropped"
            elif value["automated_browser_complete"] is not True:
                reason = failure_reason
            elif matching_round is None:
                reason = "correlation_incomplete"
            elif job.metric == "first_audio":
                reason = "first_audio_ineligible"
            else:
                reason = "barge_in_ineligible"
            attempt = {
                "schema_version": BATCH_ATTEMPT_VERSION,
                "epoch_id": job.epoch_id,
                "temperature": job.temperature,
                "metric": job.metric,
                "profile_id": job.profile_id,
                "scenario_id": job.scenario_id,
                "sample_index": job.sample_index,
                "browser_record_count": len(checked_records),
                "browser_dropped_record_count": value[
                    "browser_dropped_record_count"
                ],
                "automated_browser_complete": value[
                    "automated_browser_complete"
                ],
                "classification": classification,
                "eligible": oracle_eligible,
                "reason": reason,
            }
            _append_jsonl(self.browser_path, checked_records)
            _append_jsonl(self.attempts_path, [attempt])
            attempts = self._attempts()
            report = build_d095_report(
                aggregate=aggregate,
                attempts=attempts,
                source_head=self.source_head,
                environment_ref=self.environment_ref,
                configuration_sha256=self.configuration_sha256,
                corpus_sha256=self.corpus_sha256,
                target=self.target,
            )
            _atomic_json(self.report_path, report)
            self.active_job = None
            self.epoch_attempted = True
            counts = self._counts()
            temperature_complete = all(
                counts[metric] >= self.target for metric in METRICS
            )
            if self.temperature == "cold" or temperature_complete:
                self.shutdown_requested = True
            _atomic_json(
                self.directory / f"epoch-{self.epoch_id}.json",
                {
                    "schema_version": BATCH_SESSION_VERSION,
                    "epoch_id": self.epoch_id,
                    "temperature": self.temperature,
                    "metric": job.metric,
                    "eligible": oracle_eligible,
                    "temperature_complete": temperature_complete,
                },
            )
            return {
                "schema_version": BATCH_COMPLETION_VERSION,
                "eligible": oracle_eligible,
                "reason": reason,
                "temperature_complete": temperature_complete,
                "batch_complete": report["complete"],
            }


async def _synthesize_fixtures(
    manifest: Mapping[str, object],
) -> dict[str, bytes]:
    from jiuwenswarm.server.live_voice.batch_speech import (
        ProviderSynthesisRequest,
        create_environment_batch_speech_provider,
    )

    cases = manifest.get("cases")
    if type(cases) is not list:
        raise RuntimeError("fixed corpus cases are unavailable")
    indexed = {
        str(item["case_id"]): item for item in cases if type(item) is dict
    }
    stimulus_ids = {
        "short": "short-no-tool-zh",
        "long": "long-answer-zh",
        "barge": "playout-barge-in-zh",
    }
    provider = create_environment_batch_speech_provider()
    capability = provider.capability()
    if not (capability.available and capability.synthesis_batch):
        raise RuntimeError("configured batch synthesis Provider is unavailable")
    audio: dict[str, bytes] = {}
    for fixture, case_id in stimulus_ids.items():
        case = indexed.get(case_id)
        if case is None:
            raise RuntimeError("fixed corpus stimulus is unavailable")
        result = await provider.synthesize(
            ProviderSynthesisRequest(
                f"l0-ordinary-{fixture}-{secrets.token_hex(8)}",
                str(case["stimulus_text"]),
                "zh-CN",
                None,
                24_000,
            )
        )
        audio[fixture] = bytes(result.audio_wav)
    return audio


class _Server(ThreadingHTTPServer):
    state: OrdinaryChromeBatchState


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _authorized(self) -> bool:
        return (
            self.headers.get("Origin") == self.server.state.browser_origin
            and self.headers.get("X-L0-Batch-Nonce") == self.server.state.nonce
        )

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", self.server.state.browser_origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-L0-Batch-Nonce")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Origin")

    def _json(self, status: int, value: object) -> None:
        encoded = canonical_json_bytes(value)
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, status: int, reason: str) -> None:
        self._json(status, {"error": _safe_token(reason, "reason")})

    def _body(self) -> object:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or not raw_length.isdigit():
            raise ValueError("request length is unavailable")
        length = int(raw_length)
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body is empty or oversized")
        return json.loads(self.rfile.read(length))

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self.headers.get("Origin") != self.server.state.browser_origin:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._error(HTTPStatus.FORBIDDEN, "unauthorized")
            return
        path = urlsplit(self.path).path
        if path == "/v1/session":
            self._json(HTTPStatus.OK, self.server.state.session())
            return
        if path.startswith("/v1/audio/"):
            fixture = path.removeprefix("/v1/audio/")
            audio = self.server.state.audio_wav.get(fixture)
            if audio is None:
                self._error(HTTPStatus.NOT_FOUND, "audio_not_found")
                return
            self.send_response(HTTPStatus.OK)
            self._cors()
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
            return
        self._error(HTTPStatus.NOT_FOUND, "route_not_found")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._error(HTTPStatus.FORBIDDEN, "unauthorized")
            return
        path = urlsplit(self.path).path
        try:
            if path == "/v1/next":
                result = self.server.state.next_job()
            elif path == "/v1/warmup":
                result = self.server.state.accept_warmup(self._body())
            elif path == "/v1/complete":
                result = self.server.state.complete(self._body())
            else:
                self._error(HTTPStatus.NOT_FOUND, "route_not_found")
                return
        except (ValueError, RuntimeError):
            self._error(HTTPStatus.CONFLICT, "request_rejected")
            return
        self._json(HTTPStatus.OK, result)
        if self.server.state.shutdown_requested:
            threading.Thread(target=self.server.shutdown, daemon=True).start()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve one source-bound ordinary-Chrome D-095 batch epoch."
    )
    parser.add_argument("--evidence-directory", type=Path, required=True)
    parser.add_argument("--run-labels-file", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--environment-ref", required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--browser-origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--temperature", choices=("cold", "warm"), required=True)
    parser.add_argument("--epoch-id", required=True)
    parser.add_argument("--target", type=int, default=20)
    parser.add_argument("--port", type=int, choices=range(9222, 9323), default=9233)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        source_head = clean_source_head(args.source_head)
        manifest, _digest = load_l0_corpus_manifest(args.corpus.resolve())
        audio = asyncio.run(_synthesize_fixtures(manifest))
        state = OrdinaryChromeBatchState(
            evidence_directory=args.evidence_directory,
            run_labels_file=args.run_labels_file,
            corpus_path=args.corpus,
            source_head=source_head,
            environment_ref=args.environment_ref,
            configuration_sha256=args.configuration_sha256,
            browser_origin=args.browser_origin,
            nonce=args.nonce,
            temperature=args.temperature,
            epoch_id=args.epoch_id,
            target=args.target,
            audio_wav=audio,
        )
        server = _Server(("127.0.0.1", args.port), _Handler)
        server.state = state
        try:
            print(
                "L0_ORDINARY_CHROME_COORDINATOR_READY "
                f"temperature={args.temperature} epoch={args.epoch_id} port={args.port}",
                flush=True,
            )
            server.serve_forever(poll_interval=0.1)
        finally:
            state._write_disabled_labels()
            server.server_close()
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # noqa: BLE001 - bounded content-free CLI error
        print(
            f"L0_ORDINARY_CHROME_COORDINATOR_FAILED {type(error).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
