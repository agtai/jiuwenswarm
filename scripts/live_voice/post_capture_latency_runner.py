"""Closed fixture-manifest validation for post-capture latency runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FixtureCase:
    profile_id: str
    input_case_id: str
    wav_path: Path
    sha256: str
    sample_rate_hz: int


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
        seen.add((profile, case))
        cases.append(FixtureCase(profile, case, resolved, digest, rate))
    return tuple(cases)


def create_loopback_fixture_server(web_origin: str, cases: tuple[FixtureCase, ...]) -> ThreadingHTTPServer:
    """Create an unstarted, loopback-only fixture server."""
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
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", web_origin)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)
