"""Run the Atlas-only local backend without modifying the existing demo instance.

Use the existing Swarm virtualenv. Configuration is copied once into --data;
credentials never enter the Atlas renderer, command line or pairing URL.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time

from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--pairing-file", type=Path, required=True)
    parser.add_argument("--project-id", default="atlas-local")
    parser.add_argument("--agent-port", type=int, default=18192)
    parser.add_argument("--web-port", type=int, default=19100)
    parser.add_argument("--gateway-port", type=int, default=19101)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    data, source = args.data.resolve(), args.config.resolve()
    if data == source or data in source.parents or source in data.parents:
        parser.error("Use an isolated data directory outside the existing configuration")
    for port in (args.agent_port, args.web_port, args.gateway_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    config = data / "config"
    config.mkdir(parents=True, exist_ok=True)
    for name in (".env", "config.yaml"):
        if not (config / name).exists():
            shutil.copyfile(source / name, config / name)
    (data / "agent").mkdir(exist_ok=True)
    projects = data / "agent" / "projects.json"
    if not projects.exists():
        projects.write_text(json.dumps({"version": 1, "projects": [{"project_id": args.project_id,
            "name": "Atlas local voice", "project_dir": str(args.project.resolve()), "work_mode": "code",
            "created_at": time.time(), "updated_at": time.time(), "hidden": False, "pinned": False}]}), encoding="utf-8")
    env = {**os.environ, **{key: value for key, value in dotenv_values(config / ".env").items() if value is not None}}
    env.update({"PYTHONPATH": str(root), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        "JIUWENSWARM_CONFIG_DIR": str(config), "JIUWENSWARM_DATA_DIR": str(data),
        "JIUWENSWARM_CLI_PORTS": "1", "AGENT_SERVER_PORT": str(args.agent_port), "AGENT_PORT": str(args.agent_port),
        "WEB_PORT": str(args.web_port), "GATEWAY_PORT": str(args.gateway_port),
        "JIUWENSWARM_ATLAS_HOST_FILE": str(args.pairing_file.resolve()),
        "JIUWENSWARM_ENABLE_ORIGIN_CHECK": "1", "JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS": "127.0.0.1,localhost",
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN": secrets.token_urlsafe(32),
        "JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID": "local-atlas",
        "JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS": args.project_id,
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=12)).isoformat(),
        "JIUWENSWARM_LIVE_VOICE_P3_DATABASE": str(data / "live_voice" / "p3alpha" / "formal_tasks.sqlite3"),
        "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE": "live-voice.direct-project-code.d2.v2",
        "LIVE_VOICE_INTERACTION_ENGINE": "openai-realtime-native", "LIVE_VOICE_NATIVE_REALTIME_MODEL": "gpt-realtime-2.1-mini",
        "LIVE_VOICE_NATIVE_ENDPOINT_MODE": "server-vad-300", "LIVE_VOICE_SPEECH_PROVIDER": "openai",
        "LIVE_VOICE_SPEECH_TTS_VOICE": "marin", "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED": "1",
        "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED": "1"})
    for feature in ("P3", "PRODUCT_COMPOSITION", "PRODUCT_P2", "PRODUCT_P3_TEXT", "PRODUCT_P3_MUTATION",
                    "CRITICAL_INPUT", "DEDICATED_MEDIA", "END_OF_TURN", "WEB_ALPHA_CREDENTIAL"):
        env["JIUWENSWARM_LIVE_VOICE_" + feature + "_ENABLED"] = "1"
    (data / "live_voice" / "p3alpha").mkdir(parents=True, exist_ok=True)
    children = []
    try:
        for module in ("jiuwenswarm.server.app_agentserver", "jiuwenswarm.gateway.app_gateway"):
            log = open(data / (module.rsplit(".", 1)[-1] + ".log"), "ab", buffering=0)
            children.append(subprocess.Popen([sys.executable, "-m", module], cwd=root, env=env,
                stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
            log.close()
        print(json.dumps({"agent_port": args.agent_port, "web_port": args.web_port, "gateway_port": args.gateway_port,
            "pids": [child.pid for child in children], "data": str(data)}), flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise RuntimeError("Local backend exited; inspect its logs in the isolated data directory")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()
