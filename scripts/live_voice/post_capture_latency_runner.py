"""Closed fixture-manifest validation for post-capture latency runs."""

from __future__ import annotations

import argparse
import json
import hashlib
import hmac
import re
import subprocess
import sys
import time
import urllib.parse
import wave
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Condition, Thread
from collections.abc import Sequence
from typing import Any, Callable, cast

from jiuwenswarm.server.live_voice.latency_probe import (
    _parse_latency_run_config,
    load_latency_run_config,
)
from jiuwenswarm.server.live_voice.latency_probe_report import (
    read_latency_batches,
    reduce_latency_run,
    write_latency_report,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_WAV_BYTES = 4 * 1024 * 1024
_PUBLIC_TOKEN = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,255}$")


def _validated_web_origin(value: str) -> urllib.parse.SplitResult:
    try:
        origin = urllib.parse.urlsplit(value)
        origin_port = origin.port
    except (TypeError, ValueError) as error:
        raise ValueError("WEB_ORIGIN_INVALID") from error
    if (
        origin.scheme != "http"
        or origin.hostname not in ("localhost", "127.0.0.1")
        or origin_port is None
        or origin.username is not None
        or origin.password is not None
        or origin.path not in ("", "/")
        or origin.query
        or origin.fragment
    ):
        raise ValueError("WEB_ORIGIN_INVALID")
    return origin


def parse_browser_command_json(value: str, url: str) -> tuple[str, ...] | None:
    """Decode a bounded argv without ever invoking a command shell."""
    try:
        raw = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("BROWSER_COMMAND_INVALID") from error
    if raw == []:
        return None
    if not isinstance(raw, list) or not 1 <= len(raw) <= 32:
        raise ValueError("BROWSER_COMMAND_INVALID")
    if any(
        not isinstance(argument, str)
        or not 1 <= len(argument) <= 4096
        or any(ord(character) < 32 for character in argument)
        for argument in raw
    ):
        raise ValueError("BROWSER_COMMAND_INVALID")
    if sum(argument.count("{url}") for argument in raw) != 1:
        raise ValueError("BROWSER_COMMAND_INVALID")
    return tuple(argument.replace("{url}", url) for argument in raw)


def build_benchmark_url(
    web_origin: str,
    session_id: str,
    identity: AttemptIdentity,
    fixture_server_port: int,
    start_delay_ms: int,
) -> str:
    """Build the real saved-chat route with the closed benchmark query."""
    origin = _validated_web_origin(web_origin)
    if (
        not 1 <= fixture_server_port <= 65535
        or not 250 <= start_delay_ms <= 5_000
        or not all(
            _PUBLIC_TOKEN.fullmatch(value)
            for value in (
                session_id,
                identity.run_id,
                identity.profile_id,
                identity.input_case_id,
            )
        )
        or not 0 <= identity.round_index <= 255
    ):
        raise ValueError("BENCHMARK_URL_INVALID")
    fixture_origin = f"http://127.0.0.1:{fixture_server_port}"
    query = urllib.parse.urlencode(
        {
            "live_voice_post_capture_benchmark": "1",
            "run_id": identity.run_id,
            "profile_id": identity.profile_id,
            "input_case_id": identity.input_case_id,
            "round_index": str(identity.round_index),
            "session_id": session_id,
            "fixture_url": f"{fixture_origin}/fixture/{identity.input_case_id}.wav",
            "result_url": f"{fixture_origin}/result",
            "start_delay_ms": str(start_delay_ms),
        }
    )
    origin_base = f"{origin.scheme}://{origin.netloc}"
    return f"{origin_base}/chat/{urllib.parse.quote(session_id, safe='')}?{query}"


def validate_attempt_artifacts(run_dir: Path, identity: AttemptIdentity) -> None:
    """Require one clean, successful Browser/STT/TTS/Agent shard set."""
    try:
        run = load_latency_run_config(Path(run_dir) / "run.json")
        batches = read_latency_batches(run_dir)
    except Exception as error:
        raise ValueError("ARTIFACTS_INVALID") from error
    if (
        run.run_id != identity.run_id
        or run.source_state != "clean"
        or run.optimization_track != "post_capture_pipeline"
        or run.benchmark_lane != "controlled_browser_fixture"
        or identity.profile_id not in run.profile_ids
        or run.input_case_for_profile(identity.profile_id) != identity.input_case_id
        or not 0 <= identity.round_index < run.intended_attempts
    ):
        raise ValueError("ARTIFACTS_INCOMPATIBLE")
    exact = tuple(
        batch
        for batch in batches
        if batch.profile_id == identity.profile_id
        and batch.input_case_id == identity.input_case_id
        and batch.round_index == identity.round_index
    )
    required = {
        ("browser", "browser_round"),
        ("gateway", "gateway_stt"),
        ("gateway", "gateway_tts"),
        ("agent_server", "agent_foreground"),
    }
    observed = [(batch.component, batch.phase) for batch in exact]
    if any(observed.count(item) != 1 for item in required) or len(exact) != len(required):
        raise ValueError("ARTIFACTS_INCOMPLETE")
    forbidden_points = {
        "probe.capacity",
        "browser.playout_underrun",
        "browser.playout_rebuffer",
    }
    forbidden_outcomes = {"failed", "cancelled", "fallback", "unknown"}
    if any(
        not batch.marks
        or batch.terminal_outcome != "completed"
        or any(
            mark.point in forbidden_points or mark.outcome in forbidden_outcomes
            for mark in batch.marks
        )
        for batch in exact
    ):
        raise ValueError("ARTIFACTS_FAILED")
    try:
        attempt_report = reduce_latency_run(run, exact)
        attempt_response_total = attempt_report.profile(identity.profile_id).segment("response_total")
        report = reduce_latency_run(run, batches)
    except Exception as error:
        raise ValueError("ARTIFACTS_INVALID") from error
    if attempt_response_total.successful_samples != 1:
        raise ValueError("ARTIFACTS_FAILED")
    try:
        write_latency_report(report, run_dir)
    except Exception as error:
        raise ValueError("ARTIFACTS_INVALID") from error


def write_a_b_a_comparison(
    baseline_before: Path,
    candidate: Path,
    baseline_after: Path,
    output: Path,
    *,
    run_command: Callable[..., Any] = subprocess.run,
) -> None:
    inputs = (baseline_before, candidate, baseline_after)
    if not output.is_absolute() or output.exists():
        raise ValueError("COMPARISON_OUTPUT_EXISTS")
    if any(not path.is_absolute() or not path.is_file() for path in inputs):
        raise ValueError("COMPARISON_INPUT_INVALID")
    command = (
        sys.executable,
        "-m",
        "jiuwenswarm.server.live_voice.latency_probe_report",
        "compare-a-b-a",
        "--baseline-before",
        str(baseline_before),
        "--candidate",
        str(candidate),
        "--baseline-after",
        str(baseline_after),
    )
    try:
        completed = run_command(
            command,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
    except Exception as error:
        raise ValueError("COMPARISON_FAILED") from error
    expected_keys = {
        "schema_version", "status", "reason", "baseline_before_run_id",
        "candidate_run_id", "baseline_after_run_id", "before_to_candidate",
        "after_to_candidate", "baseline_drift",
    }
    if (
        completed.returncode != 0
        or not isinstance(payload, dict)
        or set(payload) != expected_keys
        or payload["schema_version"] != "live-voice.latency-comparison-a-b-a.v0"
    ):
        raise ValueError("COMPARISON_FAILED")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
    except FileExistsError as error:
        raise ValueError("COMPARISON_OUTPUT_EXISTS") from error


@dataclass(frozen=True)
class FixtureCase:
    profile_id: str
    input_case_id: str
    wav_path: Path
    sha256: str
    sample_rate_hz: int


@dataclass(frozen=True)
class AttemptIdentity:
    run_id: str
    profile_id: str
    input_case_id: str
    round_index: int


@dataclass(frozen=True)
class AttemptResult:
    identity: AttemptIdentity
    outcome: str


class AttemptExecutionFailed(ValueError):
    """An attempt ran but did not earn diagnostic success credit."""


class LoopbackFixtureServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        expected_result: AttemptIdentity | None,
    ) -> None:
        super().__init__(server_address, handler)
        self.expected_result = expected_result
        self.received_result: AttemptResult | None = None
        self.result_condition = Condition()

    def accept_result(self, result: AttemptResult) -> bool:
        with self.result_condition:
            if self.expected_result is None or result.identity != self.expected_result or self.received_result is not None:
                return False
            self.received_result = result
            self.result_condition.notify_all()
            return True

    def wait_for_result(self, timeout_seconds: float) -> AttemptResult | None:
        deadline = time.monotonic() + timeout_seconds
        with self.result_condition:
            while self.received_result is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.result_condition.wait(remaining)
            return self.received_result


def supervise_browser_attempt(
    server: LoopbackFixtureServer,
    browser_argv: tuple[str, ...] | None,
    *,
    timeout_seconds: float,
    popen_factory: Callable[..., Any] = subprocess.Popen,
) -> AttemptResult:
    """Own one loopback server and, optionally, exactly one Browser child."""
    if not 1 <= timeout_seconds <= 3_600:
        raise ValueError("ATTEMPT_TIMEOUT_INVALID")
    thread = Thread(target=server.serve_forever, daemon=True)
    process: Any | None = None
    thread.start()
    try:
        if browser_argv is not None:
            try:
                process = popen_factory(browser_argv, shell=False)
            except Exception as error:
                raise ValueError("BROWSER_START_FAILED") from error
        result = server.wait_for_result(timeout_seconds)
        if result is None:
            raise ValueError("ATTEMPT_TIMEOUT")
        return result
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def load_fixture_manifest(path: Path, fixture_profile_id: str) -> tuple[FixtureCase, ...]:
    """Load a closed private manifest without resolving paths outside its root."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise ValueError("FIXTURE_MANIFEST_INVALID") from error
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "fixture_profile_id", "cases"}:
        raise ValueError("FIXTURE_MANIFEST_INVALID")
    if raw["schema_version"] != "live-voice.fixed-audio-fixture.v0" or raw["fixture_profile_id"] != fixture_profile_id:
        raise ValueError("FIXTURE_PROFILE_MISMATCH")
    if not isinstance(raw["cases"], list) or not raw["cases"]:
        raise ValueError("FIXTURE_MANIFEST_INVALID")
    root = path.parent.resolve()
    cases: list[FixtureCase] = []
    seen: set[tuple[str, str]] = set()
    for item in raw["cases"]:
        if not isinstance(item, dict) or set(item) != {"profile_id", "input_case_id", "wav_path", "sha256", "sample_rate_hz"}:
            raise ValueError("FIXTURE_MANIFEST_INVALID")
        profile, case, relative, digest, rate = (item[key] for key in ("profile_id", "input_case_id", "wav_path", "sha256", "sample_rate_hz"))
        if not all(isinstance(value, str) and value for value in (profile, case, relative, digest)) or not isinstance(rate, int):
            raise ValueError("FIXTURE_MANIFEST_INVALID")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or not _SHA256.fullmatch(digest):
            raise ValueError("FIXTURE_PATH_INVALID")
        resolved = (root / candidate).resolve()
        if root not in resolved.parents or (profile, case) in seen:
            raise ValueError("FIXTURE_PATH_INVALID")
        if not resolved.is_file():
            raise ValueError("FIXTURE_FILE_UNAVAILABLE")
        try:
            if resolved.stat().st_size > _MAX_WAV_BYTES:
                raise ValueError("FIXTURE_WAV_TOO_LARGE")
        except OSError as error:
            raise ValueError("FIXTURE_FILE_UNAVAILABLE") from error
        try:
            actual_digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as error:
            raise ValueError("FIXTURE_FILE_UNAVAILABLE") from error
        if not hmac.compare_digest(actual_digest, digest):
            raise ValueError("FIXTURE_HASH_MISMATCH")
        try:
            with wave.open(str(resolved), "rb") as audio:
                valid_wav = (
                    audio.getnchannels() == 1
                    and audio.getsampwidth() == 2
                    and audio.getframerate() == rate
                    and audio.getnframes() > 0
                    and audio.getcomptype() == "NONE"
                )
        except (EOFError, OSError, wave.Error) as error:
            raise ValueError("FIXTURE_WAV_INVALID") from error
        if not valid_wav:
            raise ValueError("FIXTURE_WAV_INVALID")
        seen.add((profile, case))
        cases.append(FixtureCase(profile, case, resolved, digest, rate))
    return tuple(cases)


def create_loopback_fixture_server(
    web_origin: str,
    cases: tuple[FixtureCase, ...],
    expected_result: AttemptIdentity | None = None,
) -> LoopbackFixtureServer:
    """Create an unstarted, loopback-only fixture server."""
    _validated_web_origin(web_origin)
    by_case = {case.input_case_id: case for case in cases}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.headers.get("Origin") != web_origin:
                self.send_error(403)
                return
            prefix = "/fixture/"
            if not self.path.startswith(prefix) or not self.path.endswith(".wav"):
                self.send_error(404)
                return
            case = by_case.get(self.path[len(prefix):-4])
            if case is None:
                self.send_error(404)
                return
            try:
                payload = case.wav_path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            if (
                len(payload) > _MAX_WAV_BYTES
                or not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), case.sha256)
            ):
                self.send_error(409)
                return
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", web_origin)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/result":
                self.send_error(404)
                return
            if self.headers.get("Origin") != web_origin:
                self.send_error(403)
                return
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdecimal() or not 1 <= int(length) <= 4096:
                self.send_error(400)
                return
            try:
                raw = json.loads(self.rfile.read(int(length)).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400)
                return
            keys = {
                "schema_version", "run_id", "profile_id", "input_case_id",
                "round_index", "outcome",
            }
            if not isinstance(raw, dict) or set(raw) != keys:
                self.send_error(400)
                return
            if raw["schema_version"] != "live-voice.post-capture-result.v0" or raw["outcome"] not in ("completed", "unknown"):
                self.send_error(400)
                return
            if not all(isinstance(raw[key], str) for key in ("run_id", "profile_id", "input_case_id")) or not isinstance(raw["round_index"], int):
                self.send_error(400)
                return
            result = AttemptResult(
                AttemptIdentity(raw["run_id"], raw["profile_id"], raw["input_case_id"], raw["round_index"]),
                raw["outcome"],
            )
            server = cast(LoopbackFixtureServer, self.server)
            if not server.accept_result(result):
                self.send_error(409)
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", web_origin)
            self.end_headers()

    return LoopbackFixtureServer(("127.0.0.1", 0), Handler, expected_result)


def _add_prepare_run_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    prepare = commands.add_parser("prepare-run")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--git-commit", required=True)
    prepare.add_argument("--source-state", choices=("clean", "docs_only_dirty", "product_code_dirty"), required=True)
    prepare.add_argument("--fixture-profile-id", required=True)
    prepare.add_argument("--profile-id", action="append", required=True)
    prepare.add_argument("--input-case-id", action="append", required=True)
    prepare.add_argument("--environment-profile", required=True)
    prepare.add_argument("--browser-profile", required=True)
    prepare.add_argument("--browser-os-class", required=True)
    prepare.add_argument("--gateway-profile", required=True)
    prepare.add_argument("--agent-profile", required=True)
    prepare.add_argument("--stt-profile", required=True)
    prepare.add_argument("--tts-profile", required=True)
    prepare.add_argument("--audio-profile", required=True)
    prepare.add_argument("--vad-profile", required=True)
    prepare.add_argument("--playout-profile", required=True)
    prepare.add_argument("--cold-or-warm", choices=("cold", "warm"), required=True)
    prepare.add_argument("--intended-attempts", type=int, required=True)
    prepare.add_argument("--required-successes", type=int, required=True)


def _add_run_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    run = commands.add_parser("run")
    run.add_argument("--run-json", type=Path, required=True)
    run.add_argument("--fixture-manifest", type=Path, required=True)
    run.add_argument("--profile-id", required=True)
    run.add_argument("--round-index", type=int, required=True)
    run.add_argument("--session-id", required=True)
    run.add_argument("--web-origin", required=True)
    run.add_argument("--browser-command-json", required=True)
    run.add_argument("--timeout-seconds", type=float, required=True)
    run.add_argument("--start-delay-ms", type=int, default=1_000)


def _add_compare_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    compare = commands.add_parser("compare")
    compare.add_argument("--baseline-before", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--baseline-after", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)


def _prepare_run(args: argparse.Namespace) -> None:
    output = args.output
    if not output.is_absolute() or output.name != "run.json":
        raise ValueError("RUN_OUTPUT_INVALID")
    payload = {
        "schema_version": "live-voice.latency-run.v1",
        "run_id": output.parent.name,
        "git_commit": args.git_commit,
        "source_state": args.source_state,
        "environment_profile": args.environment_profile,
        "browser_family_and_version": args.browser_profile,
        "browser_os_class": args.browser_os_class,
        "gateway_runtime_class": args.gateway_profile,
        "agent_runtime_class": args.agent_profile,
        "stt_provider_and_model": args.stt_profile,
        "tts_provider_and_model": args.tts_profile,
        "audio_format": args.audio_profile,
        "vad_configuration": args.vad_profile,
        "playout_configuration": args.playout_profile,
        "allowlisted_feature_flags": {
            "formal_integrated_web": True,
            "formal_integrated_p1": True,
            "latency_probe": True,
            "post_capture_benchmark": True,
        },
        "cold_or_warm": args.cold_or_warm,
        "input_case_ids": args.input_case_id,
        "profile_ids": args.profile_id,
        "intended_attempts": args.intended_attempts,
        "required_successes": args.required_successes,
        "experiment": None,
        "optimization_track": "post_capture_pipeline",
        "benchmark_lane": "controlled_browser_fixture",
        "fixture_profile_id": args.fixture_profile_id,
    }
    run = _parse_latency_run_config(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(run.to_dict(), handle, sort_keys=True, indent=2)
        handle.write("\n")


def _run_attempt(args: argparse.Namespace) -> None:
    try:
        run = load_latency_run_config(args.run_json)
    except Exception as error:
        raise ValueError("RUN_CONFIG_INVALID") from error
    input_case_id = run.input_case_for_profile(args.profile_id)
    if (
        run.schema_version != "live-voice.latency-run.v1"
        or run.optimization_track != "post_capture_pipeline"
        or run.benchmark_lane != "controlled_browser_fixture"
        or input_case_id is None
        or not 0 <= args.round_index < run.intended_attempts
    ):
        raise ValueError("RUN_CONFIG_INCOMPATIBLE")
    cases = load_fixture_manifest(args.fixture_manifest, run.fixture_profile_id)
    selected = tuple(
        case
        for case in cases
        if case.profile_id == args.profile_id and case.input_case_id == input_case_id
    )
    if len(selected) != 1:
        raise ValueError("FIXTURE_CASE_MISSING")
    identity = AttemptIdentity(
        run.run_id,
        args.profile_id,
        input_case_id,
        args.round_index,
    )
    server = create_loopback_fixture_server(args.web_origin, selected, identity)
    url = build_benchmark_url(
        args.web_origin,
        args.session_id,
        identity,
        server.server_port,
        args.start_delay_ms,
    )
    browser_argv = parse_browser_command_json(args.browser_command_json, url)
    if browser_argv is None:
        print(url)
    try:
        result = supervise_browser_attempt(
            server,
            browser_argv,
            timeout_seconds=args.timeout_seconds,
        )
        if result.outcome != "completed":
            raise AttemptExecutionFailed("ATTEMPT_UNKNOWN")
        validate_attempt_artifacts(args.run_json.parent, identity)
    except AttemptExecutionFailed:
        raise
    except ValueError as error:
        raise AttemptExecutionFailed("ATTEMPT_FAILED") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="post_capture_latency_runner")
    commands = parser.add_subparsers(dest="command", required=True)
    _add_prepare_run_parser(commands)
    _add_run_parser(commands)
    _add_compare_parser(commands)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-run":
            _prepare_run(args)
            return 0
        if args.command == "run":
            _run_attempt(args)
            return 0
        if args.command == "compare":
            write_a_b_a_comparison(
                args.baseline_before,
                args.candidate,
                args.baseline_after,
                args.output,
            )
            return 0
        return 2
    except AttemptExecutionFailed:
        return 3
    except (OSError, ValueError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
