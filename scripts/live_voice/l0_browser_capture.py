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
import sys
import urllib.request
from pathlib import Path
from typing import Final

import websockets

from jiuwenswarm.server.live_voice.latency_measurement import (
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


SESSION_VERSION: Final = "live-voice.l0-browser-session.v1"
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
        "physical_evidence",
        "raw_audio_retained",
        "transcript_retained",
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
    endpoint = session["browser_endpoint"]
    if not isinstance(endpoint, str) or not endpoint.startswith("http://127.0.0.1:"):
        raise ValueError("browser endpoint must be loopback-only")
    evidence_directory = Path(str(session["evidence_directory"])).resolve()
    labels_path = Path(str(session["run_labels_file"])).resolve()
    if path.resolve().parent != evidence_directory or labels_path.parent != evidence_directory:
        raise ValueError("browser session paths escaped the exact evidence directory")
    return session


def _discover_page(endpoint: str) -> str:
    with urllib.request.urlopen(f"{endpoint}/json", timeout=3) as response:  # noqa: S310 - loopback-only validated endpoint
        pages = json.loads(response.read().decode("utf-8"))
    if type(pages) is not list:
        raise RuntimeError("Chrome debugger returned an invalid page list")
    candidates = [
        item
        for item in pages
        if type(item) is dict
        and item.get("type") == "page"
        and "live_voice_l0_measurement=1" in str(item.get("url", ""))
        and isinstance(item.get("webSocketDebuggerUrl"), str)
    ]
    if len(candidates) != 1:
        raise RuntimeError("expected exactly one opt-in Live Voice Chrome page")
    return str(candidates[0]["webSocketDebuggerUrl"])


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


async def _capture(args: argparse.Namespace) -> int:
    session_path = args.session.resolve()
    session = _load_session(session_path)
    if clean_source_head() != session["source_head"]:
        raise RuntimeError("current source HEAD differs from the launched Formal Web session")
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
    if profile["temperature_policy"] != args.temperature:
        raise ValueError("profile and temperature disagree")
    if args.successful_rounds < 20:
        raise ValueError("successful-rounds must be at least 20 for physical evidence")

    evidence_directory = Path(str(session["evidence_directory"])).resolve()
    labels_path = Path(str(session["run_labels_file"])).resolve()
    browser_jsonl = evidence_directory / "browser.jsonl"
    acceptance_jsonl = evidence_directory / "physical-acceptance.jsonl"
    websocket_url = _discover_page(str(session["browser_endpoint"]))
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

        while not _scenario_matrix_complete(
            successful_by_scenario, args.successful_rounds
        ):
            case = cases[attempted % len(cases)]
            scenario_id = str(case["case_id"])
            run_labels = _labels(
                profile_id=args.profile,
                scenario_id=scenario_id,
                sample_index=attempted,
                temperature=args.temperature,
            )
            _write_json_atomic(labels_path, run_labels)
            browser_labels = dict(run_labels)
            browser_labels.pop("schema_version")
            configured = await cdp.evaluate(
                "(() => { const c=globalThis.__JIUWENSWARM_LIVE_VOICE_L0__; "
                f"c.clear(); return c.configure({json.dumps(browser_labels, ensure_ascii=True)}); }})()"
            )
            if configured is not True:
                raise RuntimeError("browser rejected the exact run labels")

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
                        "sample_index": attempted,
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
                accepted_keys.add((args.profile, scenario_id, attempted - 1))
            if verdict == "q":
                break

    _write_json_atomic(
        labels_path,
        {"schema_version": L0_RUN_LABELS_VERSION, "measurement": "disabled"},
    )
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
            environment_ref="environment-physical-formal-web-current-room",
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
        f"evidence={evidence_directory}"
    )
    return (
        0
        if _scenario_matrix_complete(correlated_by_scenario, args.successful_rounds)
        else 2
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture physical Formal Web L0 evidence without manual timing."
    )
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--profile", default="physical-formal-web-warm")
    parser.add_argument("--temperature", choices=("cold", "warm"), default="warm")
    parser.add_argument("--successful-rounds", type=int, default=20)
    parser.add_argument("--scenario", action="append", default=[])
    return parser


def main() -> int:
    try:
        return asyncio.run(_capture(_parser().parse_args()))
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # noqa: BLE001 - stable content-free CLI boundary
        print(f"L0_BROWSER_CAPTURE_FAILED {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
