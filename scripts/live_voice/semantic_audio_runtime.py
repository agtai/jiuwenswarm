"""Small isolated runtime for real semantic audio tests, not a production route.

Reads Provider configuration in place. Owns only newly created runtime/project,
build output and subprocesses. No Task/Agent/Provider mocks or transcript RPCs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "jiuwenswarm/channels/web/frontend"


def manifest_source():
    def git(*args):
        return subprocess.check_output(["git", "-C", str(REPO), *args])

    paths = set(git("ls-files", "-z").decode().split("\0"))
    paths.update(
        git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
    )
    files = {
        name: hashlib.sha256((REPO / name).read_bytes()).hexdigest()
        for name in sorted(paths)
        if name and (REPO / name).is_file()
    }
    return {
        "head": git("rev-parse", "HEAD").decode().strip(),
        "status": git("status", "--porcelain").decode(),
        "files": files,
    }


def prepare(
    root: Path, configuration: Path, ports: list[int], engine: str, reuse: bool = False
):
    previous = None
    if reuse:
        previous = json.loads((root / "source.json").read_text(encoding="utf-8"))
        cleanup = json.loads((root / "cleanup.json").read_text(encoding="utf-8"))
        if cleanup != {
            "owned_processes_stopped": True,
            "configuration_unchanged": True,
        }:
            raise ValueError("only a fully stopped owned runtime can be reused")
        expected_project = root / "business-project"
        expected_store = root / "runtime/live_voice/p3alpha/formal_tasks.sqlite3"
        if (
            Path(previous["project"]).resolve() != expected_project
            or Path(previous["task_store"]).resolve() != expected_store
        ):
            raise ValueError("owned runtime paths do not match")
        if subprocess.check_output(
            ["git", "-C", str(expected_project), "remote"]
        ).strip():
            raise ValueError("test project must remain without remotes")
        with sqlite3.connect(
            expected_store.as_uri() + "?mode=ro", uri=True
        ) as connection:
            if connection.execute(
                "SELECT count(*) FROM tasks WHERE state != 'terminal'"
            ).fetchone()[0]:
                raise ValueError("drain live tasks before ordinary test redeployment")
        for name, key in (
            ("config.yaml", "configuration_sha256"),
            (".env", "configuration_env_sha256"),
        ):
            if (
                hashlib.sha256((configuration / name).read_bytes()).hexdigest()
                != previous[key]
            ):
                raise ValueError(
                    "source configuration changed; explicit new isolated run required"
                )
    elif root.exists() and any(root.iterdir()):
        raise ValueError(
            "runtime output must be a new empty directory; never reuse another run"
        )
    root.mkdir(parents=True, exist_ok=True)
    if len(set(ports)) != 4:
        raise ValueError("four distinct ports required")
    for port in ports:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    from dotenv import dotenv_values
    import yaml

    values = {
        k: v for k, v in dotenv_values(configuration / ".env").items() if v is not None
    }
    # These would relocate source credentials/data or activate unrelated routes
    # when the normal child dotenv loader runs. Reject, never rewrite the source.
    if any(values.get(k) for k in ("JIUWENSWARM_DATA_DIR", "JIUWENSWARM_CONFIG_DIR")):
        raise ValueError("source dotenv overrides runtime/config ownership")
    configured = yaml.safe_load(
        (configuration / "config.yaml").read_text(encoding="utf-8")
    )
    if any(
        v.get("enabled") is True
        for k, v in configured.get("channels", {}).items()
        if k not in {"web", "tui"} and isinstance(v, dict)
    ):
        raise ValueError("unrelated external channels enabled in source configuration")
    os.environ.update(values)
    runtime = root / "runtime"
    os.environ.update(
        JIUWENSWARM_DATA_DIR=str(runtime),
        JIUWENSWARM_CONFIG_DIR=str(configuration),
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
    )
    from jiuwenswarm.common.utils import prepare_workspace

    if not reuse:
        prepare_workspace(overwrite=False, workspace_dir=runtime)
    project = root / "business-project"
    if not reuse:
        project.mkdir()
        shutil.copyfile(
            REPO / "tests/support/live_voice/audio_journey/business-facts.md",
            project / "资料.md",
        )
        for command in (
            ["init"],
            # The executor requires byte-identical checkout baselines. Keep this
            # disposable fixture independent of the host's CRLF conversion.
            ["config", "core.autocrlf", "false"],
            ["add", "资料.md"],
            [
                "-c",
                "user.name=Semantic Audio Test",
                "-c",
                "user.email=local-test@invalid",
                "commit",
                "-m",
                "Add simulated business inputs",
            ],
        ):
            subprocess.run(
                ["git", "-C", str(project), *command], check=True, capture_output=True
            )
    from jiuwenswarm.server.runtime.session.project_store import (
        find_or_create_code_project_for_dir,
    )

    registered = find_or_create_code_project_for_dir(str(project))
    if registered is None:
        raise RuntimeError("disposable project registration failed")
    task_store = runtime / "live_voice/p3alpha/formal_tasks.sqlite3"
    task_store.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "JIUWENSWARM_LIVE_VOICE_RUNTIME_PROFILE": "formal-web-validation",
            "JIUWENSWARM_ENABLE_ORIGIN_CHECK": "1",
            "JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS": "localhost,127.0.0.1",
            "JIUWENSWARM_LIVE_VOICE_P3_ENABLED": "1",
            "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN": secrets.token_urlsafe(32),
            "JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID": "isolated-semantic-audio",
            "JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS": registered.project_id,
            "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT": (
                datetime.now(UTC) + timedelta(hours=6)
            ).isoformat(),
            "JIUWENSWARM_LIVE_VOICE_P3_DATABASE": str(task_store),
            "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE": "live-voice.direct-project-code.d2.v2",
            "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED": "1",
            "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED": "1",
            "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED": "1",
            "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED": "1",
            "JIUWENSWARM_LIVE_VOICE_CRITICAL_INPUT_ENABLED": "1",
            "JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED": "1",
            "JIUWENSWARM_LIVE_VOICE_END_OF_TURN_ENABLED": "1",
            "JIUWENSWARM_LIVE_VOICE_WEB_ALPHA_CREDENTIAL_ENABLED": "1",
            "LIVE_VOICE_SPEECH_PROVIDER": "openai",
            "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED": "1",
            "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED": "1",
            "LIVE_VOICE_INTERACTION_ENGINE": engine,
            "LIVE_VOICE_NATIVE_REALTIME_MODEL": "gpt-realtime-2.1-mini",
            "LIVE_VOICE_SPEECH_TTS_VOICE": "marin",
            "JIUWENSWARM_CLI_PORTS": "1",
            "AGENT_SERVER_HOST": "127.0.0.1",
            "GATEWAY_HOST": "127.0.0.1",
            "WEB_HOST": "127.0.0.1",
            "FRONTEND_HOST": "127.0.0.1",
            "VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB": "true",
            "VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1": "true",
            "VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION": "true",
            "VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION": "true",
        }
    )
    for key, value in zip(
        ("AGENT_SERVER_PORT", "WEB_PORT", "GATEWAY_PORT", "FRONTEND_PORT"), ports
    ):
        env[key] = str(value)
    env.pop("AGENT_SERVER_URL", None)
    source = manifest_source()
    source["configuration_sha256"] = hashlib.sha256(
        (configuration / "config.yaml").read_bytes()
    ).hexdigest()
    source["configuration_env_sha256"] = hashlib.sha256(
        (configuration / ".env").read_bytes()
    ).hexdigest()
    source["engine"] = engine
    source["ports"] = ports
    source["project_id"] = registered.project_id
    source["project"] = str(project)
    source["task_store"] = str(task_store)
    if previous is not None:
        (
            root
            / (
                "source-before-"
                + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
                + ".json"
            )
        ).write_text(
            json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (root / "source.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return env, source


def serve(root, configuration, ports, engine, reuse=False):
    env, source = prepare(root, configuration, ports, engine, reuse)
    epoch = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    if reuse:
        # Own control marker only; previous source, logs and attempts are retained.
        (root / "stop.request").unlink(missing_ok=True)
        for name in ("ready", "cleanup"):
            marker = root / f"{name}.json"
            if marker.exists():
                marker.rename(root / f"{name}-before-{epoch}.json")
    processes, logs = [], []

    def start(name, command, cwd=REPO):
        log = (root / f"{name}.log").open("a", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        processes.append(process)
        return process

    try:
        # Build outside the normal dist directory: an existing user's service
        # must not begin serving this candidate before its own deployment.
        build = start(
            "build",
            [
                shutil.which("node") or "node",
                "node_modules/vite/bin/vite.js",
                "build",
                "--mode",
                "live-voice",
                "--outDir",
                str(root / "dist"),
            ],
            FRONTEND,
        )
        if build.wait(timeout=300) != 0:
            raise RuntimeError("isolated frontend build failed; see build.log")
        start("agent", [sys.executable, "-m", "jiuwenswarm.server.app_agentserver"])
        start("gateway", [sys.executable, "-m", "jiuwenswarm.gateway.app_gateway"])
        start(
            "web",
            [
                sys.executable,
                "-m",
                "jiuwenswarm.channels.web.app_web",
                "--dist",
                str(root / "dist"),
            ],
        )
        deadline = time.monotonic() + 150
        ready = set()
        while len(ready) < 4:
            if time.monotonic() > deadline or any(
                p.poll() is not None for p in processes[1:]
            ):
                raise RuntimeError(
                    "isolated runtime did not become ready; inspect owned logs"
                )
            for port in ports:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        ready.add(port)
                except OSError:
                    pass
            time.sleep(0.25)
        descriptor = {
            "ports": ports,
            "url": f"http://127.0.0.1:{ports[3]}",
            "pids": [p.pid for p in processes[1:]],
            "engine": engine,
            "project_id": source["project_id"],
            "readiness": "ports-only-not-business-evidence",
        }
        (root / "ready.json").write_text(
            json.dumps(descriptor, indent=2), encoding="utf-8"
        )
        print(json.dumps(descriptor), flush=True)
        while not (root / "stop.request").exists():
            if any(p.poll() is not None for p in processes[1:]):
                raise RuntimeError("owned runtime process exited")
            time.sleep(0.5)
        return 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=8)
        for log in logs:
            log.close()
        unchanged = all(
            hashlib.sha256((configuration / name).read_bytes()).hexdigest()
            == source[key]
            for name, key in (
                ("config.yaml", "configuration_sha256"),
                (".env", "configuration_env_sha256"),
            )
        )
        (root / "cleanup.json").write_text(
            json.dumps(
                {"owned_processes_stopped": True, "configuration_unchanged": unchanged}
            ),
            encoding="utf-8",
        )
        if not unchanged:
            raise RuntimeError(
                "source configuration changed during run; investigate without restoring over user data"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument(
        "--ports", type=int, nargs=4, default=[18192, 19100, 19101, 6173]
    )
    parser.add_argument(
        "--engine", choices=["cascade", "openai-realtime-native"], default="cascade"
    )
    parser.add_argument(
        "--reuse-owned-runtime",
        action="store_true",
        help="Reuse only this tool's fully stopped runtime; preserve project, tasks and all attempts",
    )
    options = parser.parse_args()
    raise SystemExit(
        serve(
            options.output_dir.resolve(),
            options.config_dir.resolve(),
            options.ports,
            options.engine,
            options.reuse_owned_runtime,
        )
    )
