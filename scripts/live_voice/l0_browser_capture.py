# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Drive one content-free physical Formal Web L0 capture through Chrome CDP.

The operator speaks, listens, and records a bounded pass/fail confirmation.
All timestamps and JSONL collection are automatic.  No audio, transcript,
credential, project content, device identity, or free-form operator note is
accepted or written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final
from urllib.parse import parse_qsl, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import websockets  # noqa: E402
import psutil  # noqa: E402

from jiuwenswarm.server.live_voice.latency_measurement import (  # noqa: E402
    L0_RUN_LABELS_VERSION,
    load_l0_corpus_manifest,
)
try:
    from scripts.live_voice.l0_measurement_baseline import (
        aggregate_jsonl,
        clean_source_head,
    )
except ModuleNotFoundError as error:
    if error.name not in {"scripts", "scripts.live_voice"}:
        raise
    # Direct ``python scripts/live_voice/l0_browser_capture.py`` execution puts
    # this directory, rather than the repository root, first on sys.path.
    from l0_measurement_baseline import aggregate_jsonl, clean_source_head


SESSION_VERSION: Final = "live-voice.l0-browser-session.v5"
ACCEPTANCE_VERSION: Final = "live-voice.l0-physical-acceptance.v1"
DEFAULT_CORPUS: Final = Path(__file__).with_name("l0_fixed_corpus.json")
_SESSION_KEYS: Final = frozenset(
    {
        "schema_version",
        "source_head",
        "runtime_profile",
        "evidence_directory",
        "run_labels_file",
        "browser_endpoint",
        "browser_page_origin",
        "browser_profile_path",
        "browser_launch_process_id",
        "browser_debugger_process_id",
        "browser_launch_nonce",
        "temperature_epoch_id",
        "cold_sample_available",
        "environment_ref",
        "configuration_sha256",
        "physical_evidence",
        "raw_audio_retained",
        "transcript_retained",
    }
)
_ACCEPTANCE_KEYS: Final = frozenset(
    {
        "schema_version",
        "profile_id",
        "scenario_id",
        "sample_index",
        "temperature_epoch_id",
        "temperature_state",
        "operator_confirmation",
        "browser_record_count",
        "browser_dropped_record_count",
        "automated_browser_complete",
        "physical_microphone",
        "physical_speaker",
        "subjective_audio",
    }
)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if type(value) is not dict:
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _write_json_atomic(path: Path, value: object) -> None:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(encoded + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _append_jsonl(path: Path, values: list[object]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(
                json.dumps(
                    value,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
        stream.flush()
        os.fsync(stream.fileno())


def _load_session(path: Path) -> dict[str, object]:
    session = _read_json(path)
    if set(session) != _SESSION_KEYS or session["schema_version"] != SESSION_VERSION:
        raise ValueError("browser session contract has an invalid closed shape")
    if session["runtime_profile"] != "formal-web-validation":
        raise ValueError("browser session is not formal-web-validation")
    if session["raw_audio_retained"] is not False or session["transcript_retained"] is not False:
        raise ValueError("browser session privacy facts are invalid")
    environment_ref = session["environment_ref"]
    if type(environment_ref) is not str or not re.fullmatch(
        r"[a-z0-9][a-z0-9._-]{0,63}", environment_ref
    ):
        raise ValueError("browser session environment reference is invalid")
    configuration_sha256 = session["configuration_sha256"]
    if type(configuration_sha256) is not str or not re.fullmatch(
        r"[0-9a-f]{64}", configuration_sha256
    ):
        raise ValueError("browser session configuration digest is invalid")
    endpoint = session["browser_endpoint"]
    _loopback_endpoint(endpoint)
    _loopback_page_origin(session["browser_page_origin"])
    profile_value = session["browser_profile_path"]
    if type(profile_value) is not str or not Path(profile_value).is_absolute():
        raise ValueError("browser session profile path is invalid")
    profile_path = Path(profile_value).resolve()
    if not profile_path.is_dir():
        raise ValueError("browser session profile path is unavailable")
    for process_field in (
        "browser_launch_process_id",
        "browser_debugger_process_id",
    ):
        process_id = session[process_field]
        if type(process_id) is not int or process_id <= 0:
            raise ValueError("browser session process identity is invalid")
    launch_nonce = session["browser_launch_nonce"]
    if type(launch_nonce) is not str or not re.fullmatch(r"[0-9a-f]{32}", launch_nonce):
        raise ValueError("browser session launch nonce is invalid")
    temperature_epoch_id = session["temperature_epoch_id"]
    if (
        type(temperature_epoch_id) is not str
        or len(temperature_epoch_id) != 32
        or any(character not in "0123456789abcdef" for character in temperature_epoch_id)
        or session["cold_sample_available"] is not True
    ):
        raise ValueError("browser session temperature epoch is invalid")
    evidence_directory = Path(str(session["evidence_directory"])).resolve()
    labels_path = Path(str(session["run_labels_file"])).resolve()
    if path.resolve().parent != evidence_directory or labels_path.parent != evidence_directory:
        raise ValueError("browser session paths escaped the exact evidence directory")
    return session


def _loopback_endpoint(value: object) -> tuple[str, int]:
    if not isinstance(value, str):
        raise ValueError("browser endpoint must be loopback-only")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("browser endpoint must be loopback-only") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or port is None
        or not 9222 <= port <= 9322
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("browser endpoint must be loopback-only")
    return value.rstrip("/"), port


def _loopback_page_origin(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("browser page origin must be the local Formal Web origin")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(
            "browser page origin must be the local Formal Web origin"
        ) from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or port != 5173
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("browser page origin must be the local Formal Web origin")
    return f"http://{parsed.hostname}:{port}"


def _page_has_origin(value: object, *, expected_origin: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname is None
        or port is None
    ):
        return False
    return f"http://{parsed.hostname}:{port}" == expected_origin


def _page_has_launch(
    value: object,
    *,
    expected_origin: str,
    launch_nonce: str,
) -> bool:
    if not _page_has_origin(value, expected_origin=expected_origin):
        return False
    assert isinstance(value, str)
    try:
        query = parse_qsl(urlsplit(value).query, keep_blank_values=True)
    except ValueError:
        return False
    return query == [
        ("live_voice_l0_measurement", "1"),
        ("live_voice_l0_launch_nonce", launch_nonce),
    ]


def _loopback_websocket(value: object, *, expected_port: int) -> str:
    if not isinstance(value, str):
        raise RuntimeError("Chrome debugger returned a non-loopback WebSocket URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise RuntimeError(
            "Chrome debugger returned a non-loopback WebSocket URL"
        ) from error
    if (
        parsed.scheme != "ws"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or port != expected_port
        or not parsed.path.startswith("/devtools/page/")
        or parsed.fragment
    ):
        raise RuntimeError("Chrome debugger returned a non-loopback WebSocket URL")
    return value


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("Chrome debugger endpoint must not redirect")


def _assert_browser_endpoint_owner(session: dict[str, object]) -> None:
    _, port = _loopback_endpoint(session["browser_endpoint"])
    expected_pid = int(session["browser_debugger_process_id"])
    launch_pid = int(session["browser_launch_process_id"])
    profile_path = Path(str(session["browser_profile_path"])).resolve()
    try:
        connections = psutil.net_connections(kind="tcp")
    except psutil.Error as error:
        raise RuntimeError("Chrome debugger listener identity is unavailable") from error
    listener_pids = {
        connection.pid
        for connection in connections
        if connection.status == psutil.CONN_LISTEN
        and connection.pid is not None
        and connection.laddr
        and connection.laddr.port == port
        and connection.laddr.ip in {"127.0.0.1", "::1"}
    }
    if listener_pids != {expected_pid}:
        raise RuntimeError("Chrome debugger listener owner differs from the launched session")
    try:
        process = psutil.Process(expected_pid)
        name = process.name().lower()
        command_line = process.cmdline()
        launch_process = psutil.Process(launch_pid)
        launch_name = launch_process.name().lower()
        launch_command_line = launch_process.cmdline()
        debugger_parent_pids = {parent.pid for parent in process.parents()}
    except psutil.Error as error:
        raise RuntimeError("Chrome debugger process identity is unavailable") from error
    expected_profile = f"--user-data-dir={profile_path}"
    if (
        name not in {"chrome", "chrome.exe"}
        or expected_profile not in command_line
        or f"--remote-debugging-port={port}" not in command_line
        or "--remote-debugging-address=127.0.0.1" not in command_line
    ):
        raise RuntimeError("Chrome debugger process does not own the exact isolated profile")
    if (
        launch_name not in {"chrome", "chrome.exe"}
        or expected_profile not in launch_command_line
        or (launch_pid != expected_pid and launch_pid not in debugger_parent_pids)
    ):
        raise RuntimeError("Chrome debugger process is not descended from the launched Chrome")


def _discover_page(endpoint: str, *, page_origin: str, launch_nonce: str) -> str:
    base, port = _loopback_endpoint(endpoint)
    expected_origin = _loopback_page_origin(page_origin)
    if not re.fullmatch(r"[0-9a-f]{32}", launch_nonce):
        raise ValueError("browser launch nonce is invalid")
    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(f"{base}/json", timeout=3) as response:  # noqa: S310 - exact loopback URL, redirects rejected
        final_url, final_port = _loopback_endpoint(response.geturl().removesuffix("/json"))
        if final_url != base or final_port != port:
            raise RuntimeError("Chrome debugger response escaped the exact loopback endpoint")
        pages = json.loads(response.read().decode("utf-8"))
    if type(pages) is not list:
        raise RuntimeError("Chrome debugger returned an invalid page list")
    candidates = [
        item
        for item in pages
        if type(item) is dict
        and item.get("type") == "page"
        and _page_has_launch(
            item.get("url"),
            expected_origin=expected_origin,
            launch_nonce=launch_nonce,
        )
        and isinstance(item.get("webSocketDebuggerUrl"), str)
    ]
    if len(candidates) != 1:
        raise RuntimeError("expected exactly one isolated Formal Web Chrome page")
    return _loopback_websocket(
        candidates[0]["webSocketDebuggerUrl"],
        expected_port=port,
    )


class _CdpClient:
    def __init__(self, socket: object) -> None:
        self._socket = socket
        self._next_id = 0

    async def command(self, method: str, params: dict[str, object] | None = None) -> object:
        self._next_id += 1
        command_id = self._next_id
        await self._socket.send(  # type: ignore[attr-defined]
            json.dumps(
                {
                    "id": command_id,
                    "method": method,
                    "params": params or {},
                },
                separators=(",", ":"),
            )
        )
        while True:
            message = json.loads(await self._socket.recv())  # type: ignore[attr-defined]
            if message.get("id") != command_id:
                continue
            if "error" in message:
                raise RuntimeError(f"Chrome command failed: {method}")
            return message.get("result")

    async def evaluate(self, expression: str) -> object:
        result = await self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if type(result) is not dict:
            raise RuntimeError("Chrome evaluation returned an invalid result")
        remote = result.get("result")
        if type(remote) is not dict or remote.get("subtype") == "error":
            raise RuntimeError("Chrome evaluation failed")
        return remote.get("value")


def _labels(
    *,
    profile_id: str,
    scenario_id: str,
    sample_index: int,
    temperature: str,
) -> dict[str, object]:
    return {
        "schema_version": L0_RUN_LABELS_VERSION,
        "profile_id": profile_id,
        "scenario_id": scenario_id,
        "sample_index": sample_index,
        "temperature": temperature,
        "evidence_source": "physical",
    }


def _select_cases(
    manifest: dict[str, object], requested: list[str]
) -> list[dict[str, object]]:
    cases = manifest["cases"]
    assert isinstance(cases, list)
    indexed = {str(item["case_id"]): item for item in cases if type(item) is dict}
    if requested:
        missing = sorted(set(requested) - indexed.keys())
        if missing:
            raise ValueError(f"unknown corpus scenarios: {', '.join(missing)}")
        selected = [indexed[item] for item in requested]
        if any(
            item["expected_classification"] != "success"
            or item["input_mode"] == "injected"
            or item["category"] == "degraded_network"
            for item in selected
        ):
            raise ValueError(
                "physical capture accepts only non-injected nominal success scenarios"
            )
        return selected
    selected = [
        item
        for item in indexed.values()
        if item["expected_classification"] == "success"
        and item["input_mode"] not in {"injected"}
        and item["category"] != "degraded_network"
    ]
    if not selected:
        raise ValueError("corpus has no default physical success scenarios")
    return selected


def _browser_round_complete(
    snapshot: object,
    labels: dict[str, object],
) -> bool:
    if type(snapshot) is not dict or set(snapshot) != {
        "enabled",
        "configured",
        "accepted_records",
        "dropped_records",
        "records",
    }:
        return False
    records = snapshot["records"]
    if (
        snapshot["enabled"] is not True
        or snapshot["configured"] is not True
        or type(records) is not list
        or type(snapshot["accepted_records"]) is not int
        or snapshot["accepted_records"] != len(records)
        or type(snapshot["dropped_records"]) is not int
        or snapshot["dropped_records"] != 0
        or not records
    ):
        return False
    expected = {
        "profile_id": labels["profile_id"],
        "scenario_id": labels["scenario_id"],
        "sample_index": labels["sample_index"],
        "temperature": labels["temperature"],
        "evidence_source": labels["evidence_source"],
    }
    terminals = 0
    for record in records:
        if type(record) is not dict or any(
            record.get(field_name) != field_value
            for field_name, field_value in expected.items()
        ):
            return False
        classification = record.get("classification")
        if classification not in {"unknown", "success"}:
            return False
        if record.get("milestone") == "playout_completed":
            if classification != "success":
                return False
            terminals += 1
    return terminals == 1


def _scenario_matrix_complete(counts: dict[str, int], target: int) -> bool:
    return sum(counts.values()) >= target and all(value >= 1 for value in counts.values())


def _correlated_success_counts(
    report: dict[str, object],
    accepted_keys: set[tuple[str, str, int]],
    scenario_ids: set[str],
) -> dict[str, int]:
    rounds = report.get("rounds")
    if type(rounds) is not list:
        raise RuntimeError("physical aggregate has no round detail")
    eligible: set[tuple[str, str, int]] = set()
    for item in rounds:
        if type(item) is not dict or item.get("success_eligible") is not True:
            continue
        profile_id = item.get("profile_id")
        scenario_id = item.get("scenario_id")
        sample_index = item.get("sample_index")
        if type(profile_id) is str and type(scenario_id) is str and type(sample_index) is int:
            eligible.add((profile_id, scenario_id, sample_index))
    counts = {scenario_id: 0 for scenario_id in scenario_ids}
    for _profile_id, scenario_id, _sample_index in accepted_keys & eligible:
        if scenario_id in counts:
            counts[scenario_id] += 1
    return counts


def _load_physical_acceptance(path: Path) -> list[dict[str, object]]:
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("physical acceptance evidence is missing or oversized")
    records: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw_line.strip():
            raise ValueError("physical acceptance JSONL contains an empty record")
        value = json.loads(raw_line)
        if type(value) is not dict or set(value) != _ACCEPTANCE_KEYS:
            raise ValueError("physical acceptance record has an invalid closed shape")
        epoch = value["temperature_epoch_id"]
        if (
            value["schema_version"] != ACCEPTANCE_VERSION
            or type(value["profile_id"]) is not str
            or not value["profile_id"]
            or type(value["scenario_id"]) is not str
            or not value["scenario_id"]
            or type(value["sample_index"]) is not int
            or value["sample_index"] < 0
            or type(epoch) is not str
            or len(epoch) != 32
            or any(character not in "0123456789abcdef" for character in epoch)
            or value["temperature_state"]
            not in {"fresh_launcher_epoch", "controlled_warmup_complete"}
            or value["operator_confirmation"] not in {"pass", "fail", "quit"}
            or type(value["browser_record_count"]) is not int
            or value["browser_record_count"] < 0
            or type(value["browser_dropped_record_count"]) is not int
            or value["browser_dropped_record_count"] < 0
            or type(value["automated_browser_complete"]) is not bool
            or value["physical_microphone"] != "operator_observed"
            or value["physical_speaker"] != "operator_observed"
            or value["subjective_audio"]
            not in {"operator_confirmed", "not_accepted"}
            or (
                value["operator_confirmation"] == "pass"
                and value["subjective_audio"] != "operator_confirmed"
            )
            or (
                value["operator_confirmation"] != "pass"
                and value["subjective_audio"] != "not_accepted"
            )
        ):
            raise ValueError("physical acceptance record contains invalid facts")
        records.append(value)
        if len(records) > 1_000:
            raise ValueError("physical acceptance record capacity exceeded")
    if not records:
        raise ValueError("physical acceptance evidence is empty")
    return records


def _load_cold_consumed_marker(path: Path) -> dict[str, object]:
    marker = _read_json(path)
    if (
        set(marker) != {"schema_version", "temperature_epoch_id", "sample_index"}
        or marker["schema_version"] != SESSION_VERSION
        or type(marker["temperature_epoch_id"]) is not str
        or len(marker["temperature_epoch_id"]) != 32
        or any(
            character not in "0123456789abcdef"
            for character in marker["temperature_epoch_id"]
        )
        or type(marker["sample_index"]) is not int
        or marker["sample_index"] < 0
    ):
        raise ValueError("cold-sample consumption marker is invalid")
    return marker


def _aggregate_cold_evidence(args: argparse.Namespace) -> int:
    manifest, corpus_digest = load_l0_corpus_manifest(args.corpus.resolve())
    cases = _select_cases(manifest, args.scenario)
    scenario_ids = {str(case["case_id"]) for case in cases}
    profile_id = "physical-formal-web-cold"
    profiles = {
        str(item["profile_id"]): item
        for item in manifest["profiles"]
        if type(item) is dict
    }
    profile = profiles.get(profile_id)
    if (
        profile is None
        or profile["evidence_source"] != "physical"
        or profile["temperature_policy"] != "cold"
    ):
        raise ValueError("corpus has no physical cold profile")
    profile_success_target = max(
        int(profile["minimum_successful_rounds"]),
        args.successful_rounds,
    )
    evidence_directories = [path.resolve() for path in args.evidence_directory]
    if not evidence_directories or len(evidence_directories) > 100:
        raise ValueError("cold aggregation requires 1 to 100 evidence directories")
    if len(set(evidence_directories)) != len(evidence_directories):
        raise ValueError("cold aggregation evidence directories must be unique")

    source_head = clean_source_head()
    accepted_keys: set[tuple[str, str, int]] = set()
    seen_keys: set[tuple[str, str, int]] = set()
    seen_epochs: set[str] = set()
    accepted_epochs: set[str] = set()
    operator_successes_by_scenario = {scenario_id: 0 for scenario_id in scenario_ids}
    measurement_inputs: list[Path] = []
    aggregate_environment_ref: str | None = None
    aggregate_configuration_sha256: str | None = None
    attempts = 0
    for evidence_directory in evidence_directories:
        session = _load_session(evidence_directory / "browser-session.json")
        if session["source_head"] != source_head:
            raise RuntimeError("cold evidence source HEAD differs from the clean worktree")
        epoch = str(session["temperature_epoch_id"])
        if epoch in seen_epochs:
            raise ValueError("cold evidence reused a launcher temperature epoch")
        seen_epochs.add(epoch)
        shard_report = _read_json(evidence_directory / "physical-report.json")
        shard_environment_ref = str(session["environment_ref"])
        shard_configuration_sha256 = str(session["configuration_sha256"])
        if (
            shard_report.get("source_head") != source_head
            or shard_report.get("corpus_sha256") != corpus_digest
            or shard_report.get("environment_ref") != shard_environment_ref
            or shard_report.get("physical_configuration_sha256")
            != shard_configuration_sha256
            or shard_report.get("physical_capture_kind") != "cold_epoch_shard"
            or shard_report.get("physical_temperature_epoch_id") != epoch
        ):
            raise ValueError(
                "cold shard report conflicts with its source, corpus, environment, configuration, or epoch"
            )
        if aggregate_environment_ref is None:
            aggregate_environment_ref = shard_environment_ref
            aggregate_configuration_sha256 = shard_configuration_sha256
        elif (
            shard_environment_ref != aggregate_environment_ref
            or shard_configuration_sha256 != aggregate_configuration_sha256
        ):
            raise ValueError(
                "cold evidence shards do not share one environment and configuration"
            )

        acceptance_records = _load_physical_acceptance(
            evidence_directory / "physical-acceptance.jsonl"
        )
        if len(acceptance_records) != 1:
            raise ValueError("each cold launcher epoch must contain exactly one attempt")
        acceptance = acceptance_records[0]
        scenario_id = str(acceptance["scenario_id"])
        sample_index = int(acceptance["sample_index"])
        sample_key = (profile_id, scenario_id, sample_index)
        if (
            acceptance["profile_id"] != profile_id
            or acceptance["temperature_state"] != "fresh_launcher_epoch"
            or acceptance["temperature_epoch_id"] != epoch
            or scenario_id not in scenario_ids
        ):
            raise ValueError("cold acceptance facts conflict with the selected corpus")
        if sample_key in seen_keys:
            raise ValueError("cold evidence reused a sample identity")
        seen_keys.add(sample_key)
        marker = _load_cold_consumed_marker(
            evidence_directory / "cold-sample-consumed.json"
        )
        if (
            marker["temperature_epoch_id"] != epoch
            or marker["sample_index"] != sample_index
        ):
            raise ValueError("cold consumption marker conflicts with acceptance")

        inputs = sorted(
            path
            for path in evidence_directory.glob("*.jsonl")
            if path.name != "physical-acceptance.jsonl"
        )
        if not inputs:
            raise ValueError("cold evidence directory has no measurement records")
        measurement_inputs.extend(inputs)
        attempts += 1
        if (
            acceptance["operator_confirmation"] == "pass"
            and acceptance["automated_browser_complete"] is True
            and acceptance["browser_record_count"] > 0
            and acceptance["browser_dropped_record_count"] == 0
        ):
            accepted_keys.add(sample_key)
            accepted_epochs.add(epoch)
            operator_successes_by_scenario[scenario_id] += 1

    if aggregate_environment_ref is None or aggregate_configuration_sha256 is None:
        raise ValueError("cold aggregation has no environment/configuration provenance")
    report = aggregate_jsonl(
        inputs=measurement_inputs,
        corpus_path=args.corpus.resolve(),
        source_head=source_head,
        environment_ref=aggregate_environment_ref,
        accepted_round_keys=frozenset(accepted_keys),
    )
    correlated_by_scenario = _correlated_success_counts(
        report,
        accepted_keys,
        scenario_ids,
    )
    correlated_successes = sum(correlated_by_scenario.values())
    complete = (
        len(accepted_epochs) >= profile_success_target
        and _scenario_matrix_complete(correlated_by_scenario, profile_success_target)
    )
    report["physical_capture_kind"] = "cold_epoch_aggregate"
    report["physical_temperature_state"] = "fresh_launcher_epoch_per_sample"
    report["physical_configuration_sha256"] = aggregate_configuration_sha256
    report["physical_cold_epoch_count"] = len(seen_epochs)
    report["physical_accepted_cold_epoch_count"] = len(accepted_epochs)
    report["physical_cold_temperature_epoch_ids"] = sorted(seen_epochs)
    report["physical_operator_confirmed_successes"] = len(accepted_keys)
    report["physical_operator_confirmed_successes_by_scenario"] = dict(
        sorted(operator_successes_by_scenario.items())
    )
    report["physical_correlated_successes"] = correlated_successes
    report["physical_correlated_successes_by_scenario"] = dict(
        sorted(correlated_by_scenario.items())
    )
    report["physical_attempts"] = attempts
    report["physical_profile_success_target"] = profile_success_target
    report["physical_capture_complete"] = complete
    report["physical_profile_complete"] = complete
    report["corpus_sha256"] = corpus_digest
    report["non_claims"] = [
        "browser/Gateway/Agent timestamps do not prove acoustic echo cancellation",
        "operator confirmation is subjective and separate from automated success filtering",
        "each cold sample came from a distinct launcher temperature epoch",
        "no raw audio or transcript was retained by the measurement evidence",
    ]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output, report)
    print(
        f"Cold aggregate complete: correlated_successes={correlated_successes} "
        f"accepted_epochs={len(accepted_epochs)} attempts={attempts} "
        f"profile_target={profile_success_target} evidence={output}"
    )
    return 0 if complete else 2


def _disabled_labels() -> dict[str, object]:
    return {
        "schema_version": L0_RUN_LABELS_VERSION,
        "measurement": "disabled",
    }


@asynccontextmanager
async def _configured_run_labels(
    *,
    labels_path: Path,
    cdp: _CdpClient,
    run_labels: dict[str, object],
    browser_labels: dict[str, object],
) -> AsyncIterator[None]:
    _write_json_atomic(labels_path, run_labels)
    try:
        configured = await cdp.evaluate(
            "(() => { const c=globalThis.__JIUWENSWARM_LIVE_VOICE_L0__; "
            f"c.clear(); return c.configure({json.dumps(browser_labels, ensure_ascii=True)}); }})()"
        )
        if configured is not True:
            raise RuntimeError("browser rejected the exact run labels")
        yield
    finally:
        _write_json_atomic(labels_path, _disabled_labels())
        try:
            await cdp.evaluate(
                "(() => { globalThis.__JIUWENSWARM_LIVE_VOICE_L0__.disable(); return true; })()"
            )
        except Exception:
            pass


def _validate_temperature_capture_policy(
    *,
    profile: dict[str, object],
    cases: list[dict[str, object]],
    temperature: str,
    successful_rounds: int,
    sample_index_start: int | None,
) -> int:
    if sample_index_start is not None and sample_index_start < 0:
        raise ValueError("sample-index-start must be non-negative")
    if profile["temperature_policy"] != temperature:
        raise ValueError("profile and temperature disagree")
    if temperature == "cold":
        if successful_rounds != 1 or len(cases) != 1:
            raise ValueError(
                "cold capture requires one scenario and one sample per fresh launcher epoch"
            )
        if sample_index_start is None:
            raise ValueError("cold capture requires an explicit unique sample-index-start")
        return sample_index_start
    if successful_rounds < 20:
        raise ValueError("warm physical evidence requires at least 20 successful rounds")
    return 0 if sample_index_start is None else sample_index_start


def _invalidate_cold_eligibility(
    *,
    marker_path: Path,
    temperature_epoch_id: object,
    sample_index: int,
    cold_capture: bool,
) -> None:
    if marker_path.exists():
        if cold_capture:
            raise RuntimeError(
                "this fresh launcher temperature epoch already consumed its cold sample"
            )
        return
    _write_json_atomic(
        marker_path,
        {
            "schema_version": SESSION_VERSION,
            "temperature_epoch_id": temperature_epoch_id,
            "sample_index": sample_index,
        },
    )


def _warmup_case(manifest: dict[str, object]) -> dict[str, object]:
    cases = manifest.get("cases")
    if type(cases) is not list:
        raise ValueError("fixed corpus cases are unavailable")
    candidates = [
        case
        for case in cases
        if type(case) is dict
        and case.get("case_id") == "short-no-tool-zh"
        and case.get("expected_route") == "dialogue"
        and case.get("expected_classification") == "success"
        and case.get("action_sequence") == ["submit", "await-audio"]
    ]
    if len(candidates) != 1:
        raise ValueError("fixed corpus has no unique non-mutating warm-up case")
    return candidates[0]


async def _capture(args: argparse.Namespace) -> int:
    session_path = args.session.resolve()
    session = _load_session(session_path)
    if clean_source_head() != session["source_head"]:
        raise RuntimeError("current source HEAD differs from the launched Formal Web session")
    _assert_browser_endpoint_owner(session)
    manifest, corpus_digest = load_l0_corpus_manifest(args.corpus.resolve())
    cases = _select_cases(manifest, args.scenario)
    profiles = {
        str(item["profile_id"]): item
        for item in manifest["profiles"]
        if type(item) is dict
    }
    profile = profiles.get(args.profile)
    if profile is None or profile["evidence_source"] != "physical":
        raise ValueError("profile must be one physical corpus profile")
    sample_index_start = _validate_temperature_capture_policy(
        profile=profile,
        cases=cases,
        temperature=args.temperature,
        successful_rounds=args.successful_rounds,
        sample_index_start=args.sample_index_start,
    )
    profile_success_target = max(
        int(profile["minimum_successful_rounds"]),
        args.successful_rounds,
    )

    evidence_directory = Path(str(session["evidence_directory"])).resolve()
    labels_path = Path(str(session["run_labels_file"])).resolve()
    cold_consumed_path = evidence_directory / "cold-sample-consumed.json"
    _invalidate_cold_eligibility(
        marker_path=cold_consumed_path,
        temperature_epoch_id=session["temperature_epoch_id"],
        sample_index=sample_index_start,
        cold_capture=args.temperature == "cold",
    )
    browser_jsonl = evidence_directory / "browser.jsonl"
    acceptance_jsonl = evidence_directory / "physical-acceptance.jsonl"
    websocket_url = _discover_page(
        str(session["browser_endpoint"]),
        page_origin=str(session["browser_page_origin"]),
        launch_nonce=str(session["browser_launch_nonce"]),
    )
    successful = 0
    attempted = 0
    successful_by_scenario = {str(case["case_id"]): 0 for case in cases}
    accepted_keys: set[tuple[str, str, int]] = set()
    async with websockets.connect(websocket_url, max_size=4 * 1024 * 1024) as socket:
        cdp = _CdpClient(socket)
        await cdp.command("Runtime.enable")
        available = await cdp.evaluate(
            "Boolean(globalThis.__JIUWENSWARM_LIVE_VOICE_L0__)"
        )
        if available is not True:
            raise RuntimeError("browser L0 control is unavailable; reload the opt-in page")

        _write_json_atomic(labels_path, _disabled_labels())
        await cdp.evaluate(
            "(() => { globalThis.__JIUWENSWARM_LIVE_VOICE_L0__.disable(); return true; })()"
        )
        if args.temperature == "warm":
            case = _warmup_case(manifest)
            print("\n" + "=" * 72)
            print(f"Unmeasured non-mutating warm-up | {case['case_id']}")
            print(f"Speak exactly as prompted: {case['stimulus_text']}")
            print(
                "Controlled actions: "
                + ", ".join(str(item) for item in case["action_sequence"])
            )
            input("Press Enter immediately before this unmeasured warm-up...")
            warmed = input(
                "After the warm-up settles, confirm [w]armed or [q]uit: "
            ).strip().lower()
            if warmed == "q":
                return 130
            if warmed != "w":
                raise RuntimeError("warm state was not explicitly established")

        while not _scenario_matrix_complete(
            successful_by_scenario, args.successful_rounds
        ):
            case = cases[attempted % len(cases)]
            scenario_id = str(case["case_id"])
            sample_index = sample_index_start + attempted
            run_labels = _labels(
                profile_id=args.profile,
                scenario_id=scenario_id,
                sample_index=sample_index,
                temperature=args.temperature,
            )
            browser_labels = dict(run_labels)
            browser_labels.pop("schema_version")
            async with _configured_run_labels(
                labels_path=labels_path,
                cdp=cdp,
                run_labels=run_labels,
                browser_labels=browser_labels,
            ):
                actions = ", ".join(str(item) for item in case["action_sequence"])
                print("\n" + "=" * 72)
                print(
                    f"Sample {attempted + 1} | success {successful}/{args.successful_rounds} | {scenario_id}"
                    f" | scenario_success={successful_by_scenario[scenario_id]}"
                )
                print(f"Speak exactly as prompted: {case['stimulus_text']}")
                print(f"Controlled actions: {actions}")
                input("Press Enter immediately before starting this round...")
                verdict = input(
                    "After audio/cancellation settles, confirm [p]ass, [f]ail, or [q]uit: "
                ).strip().lower()
                if verdict not in {"p", "f", "q"}:
                    verdict = "f"

                snapshot = await cdp.evaluate(
                    "globalThis.__JIUWENSWARM_LIVE_VOICE_L0__.snapshot()"
                )
                if type(snapshot) is not dict or type(snapshot.get("records")) is not list:
                    raise RuntimeError("browser returned an invalid content-free snapshot")
                records = snapshot["records"]
                browser_complete = _browser_round_complete(snapshot, browser_labels)
                if records:
                    _append_jsonl(browser_jsonl, records)
                _append_jsonl(
                    acceptance_jsonl,
                    [
                        {
                            "schema_version": ACCEPTANCE_VERSION,
                            "profile_id": args.profile,
                            "scenario_id": scenario_id,
                            "sample_index": sample_index,
                            "temperature_epoch_id": session["temperature_epoch_id"],
                            "temperature_state": (
                                "fresh_launcher_epoch"
                                if args.temperature == "cold"
                                else "controlled_warmup_complete"
                            ),
                            "operator_confirmation": (
                                "pass" if verdict == "p" else "fail" if verdict == "f" else "quit"
                            ),
                            "browser_record_count": len(records),
                            "browser_dropped_record_count": snapshot.get("dropped_records"),
                            "automated_browser_complete": browser_complete,
                            "physical_microphone": "operator_observed",
                            "physical_speaker": "operator_observed",
                            "subjective_audio": "operator_confirmed" if verdict == "p" else "not_accepted",
                        }
                    ],
                )
                attempted += 1
                if verdict == "p" and browser_complete:
                    successful += 1
                    successful_by_scenario[scenario_id] += 1
                    accepted_keys.add((args.profile, scenario_id, sample_index))
                if verdict == "q" or args.temperature == "cold":
                    break

    _write_json_atomic(labels_path, _disabled_labels())
    inputs = sorted(
        path
        for path in evidence_directory.glob("*.jsonl")
        if path.name != acceptance_jsonl.name
    )
    correlated_successes = 0
    correlated_by_scenario = {scenario_id: 0 for scenario_id in successful_by_scenario}
    if inputs:
        report = aggregate_jsonl(
            inputs=inputs,
            corpus_path=args.corpus.resolve(),
            source_head=str(session["source_head"]),
            environment_ref=str(session["environment_ref"]),
            accepted_round_keys=frozenset(accepted_keys),
        )
        report["physical_operator_confirmed_successes"] = successful
        report["physical_operator_confirmed_successes_by_scenario"] = dict(
            sorted(successful_by_scenario.items())
        )
        correlated_by_scenario = _correlated_success_counts(
            report,
            accepted_keys,
            set(successful_by_scenario),
        )
        correlated_successes = sum(correlated_by_scenario.values())
        report["physical_correlated_successes"] = correlated_successes
        report["physical_correlated_successes_by_scenario"] = dict(
            sorted(correlated_by_scenario.items())
        )
        report["physical_attempts"] = attempted
        capture_complete = _scenario_matrix_complete(
            correlated_by_scenario,
            args.successful_rounds,
        )
        report["physical_capture_kind"] = (
            "cold_epoch_shard" if args.temperature == "cold" else "warm_profile"
        )
        report["physical_temperature_state"] = (
            "fresh_launcher_epoch"
            if args.temperature == "cold"
            else "controlled_warmup_complete"
        )
        report["physical_temperature_epoch_id"] = session["temperature_epoch_id"]
        report["physical_configuration_sha256"] = session["configuration_sha256"]
        report["physical_capture_success_target"] = args.successful_rounds
        report["physical_capture_complete"] = capture_complete
        report["physical_profile_success_target"] = profile_success_target
        report["physical_profile_complete"] = _scenario_matrix_complete(
            correlated_by_scenario,
            profile_success_target,
        )
        report["corpus_sha256"] = corpus_digest
        report["non_claims"] = [
            "browser/Gateway/Agent timestamps do not prove acoustic echo cancellation",
            "operator confirmation is subjective and separate from automated success filtering",
            "no raw audio or transcript was retained by the measurement evidence",
        ]
        _write_json_atomic(evidence_directory / "physical-report.json", report)
    print(
        f"\nCapture complete: correlated_successes={correlated_successes} "
        f"operator_browser_successes={successful} attempts={attempted} "
        f"profile_target={profile_success_target} "
        f"evidence={evidence_directory}"
    )
    return 0 if _scenario_matrix_complete(
        correlated_by_scenario,
        args.successful_rounds,
    ) else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture physical Formal Web L0 evidence without manual timing."
    )
    parser.add_argument("--session", type=Path, default=None)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--temperature", choices=("cold", "warm"), default=None)
    parser.add_argument("--successful-rounds", type=int, default=20)
    parser.add_argument(
        "--sample-index-start",
        type=int,
        default=None,
        help="Explicit unique first sample index; required for each cold launcher epoch.",
    )
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument(
        "--aggregate-cold",
        action="store_true",
        help="Aggregate independently captured cold launcher epochs.",
    )
    parser.add_argument(
        "--evidence-directory",
        type=Path,
        action="append",
        default=[],
        help="One cold capture directory; repeat for every launcher epoch.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Required destination for --aggregate-cold.",
    )
    return parser


def main() -> int:
    try:
        args = _parser().parse_args()
        if args.aggregate_cold:
            if args.session is not None or args.sample_index_start is not None:
                raise ValueError("cold aggregation does not accept capture-only arguments")
            if args.profile not in {None, "physical-formal-web-cold"}:
                raise ValueError("cold aggregation has one fixed physical cold profile")
            if args.temperature not in {None, "cold"}:
                raise ValueError("cold aggregation requires cold temperature evidence")
            if args.output is None:
                raise ValueError("cold aggregation requires --output")
            return _aggregate_cold_evidence(args)
        if args.evidence_directory or args.output is not None:
            raise ValueError("cold aggregation arguments require --aggregate-cold")
        if args.session is None:
            raise ValueError("capture requires --session")
        args.profile = args.profile or "physical-formal-web-warm"
        args.temperature = args.temperature or "warm"
        return asyncio.run(_capture(args))
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # noqa: BLE001 - stable content-free CLI boundary
        print(f"L0_BROWSER_CAPTURE_FAILED {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
