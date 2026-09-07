"""Shared helpers for the LiveVoice slimming rebaseline scripts (read-only Git access)."""
from __future__ import annotations

import io
import re
import subprocess

SHARED_HOSTS = (
    "auto_harness/project_execution.py", "auto_harness/scheduler.py", "auto_harness/service.py",
    "auto_harness/task_store.py", "channels/web/app_web.py", "frontend/src/App.tsx",
    "ChatPanel/index.tsx", "ChatPanel/MessageItem.tsx", "featureFlags.ts", "useWebSocket.ts",
    "supplementOutputQuarantine.ts", "utils/tts.ts", "ttsOutputOwnership.ts", "ttsText.ts",
    "common/schema/message.py", "gateway/app_gateway.py", "app_web_handlers.py", "web_connect.py",
    "server/agent_ws_server.py", "agent_adapter/agent_adapters.py", "agent_adapter/interface_deep.py",
    "agent_adapter/interface.py", "runtime/agent_manager.py", "session/session_history.py",
)


def _repo_root() -> str:
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, encoding="utf-8", errors="replace")
    return result.stdout.strip() or "."


ROOT = _repo_root()


def git(*args: str) -> str:
    """Run git from the repository root so path specs are repo-relative regardless of cwd."""
    result = subprocess.run(["git", *args], capture_output=True, encoding="utf-8", errors="replace", cwd=ROOT)
    return result.stdout if result.returncode == 0 else ""


def show(rev: str, path: str) -> str:
    return git("show", f"{rev}:{path}")


def read_manifest(spec: str) -> list[str]:
    """Read the atomic manifest from a filesystem path (cwd or repo-root relative) or from REV:PATH."""
    match = re.match(r"^([0-9a-fA-F]{7,40}|HEAD[^:]*|[\w./-]+):(live-voice/.*)$", spec)
    if match and not spec[1:3] == ":\\":
        text = show(match.group(1), match.group(2))
        if not text:
            raise SystemExit(f"manifest not found at {spec}")
        return text.splitlines()
    import os
    for candidate in (spec, os.path.join(ROOT, spec)):
        if os.path.exists(candidate):
            return io.open(candidate, encoding="utf-8").read().splitlines()
    raise SystemExit(f"manifest not found: {spec}")


def manifest_rows(lines: list[str]) -> tuple[dict, list[dict]]:
    """Return ({path: {ars, codes}}, [register rows]) from the manifest."""
    idx = next(i for i, l in enumerate(lines) if l.startswith("## Exact 152-path coverage index"))
    reg = next(i for i, l in enumerate(lines) if l.startswith("## Atomic responsibility register"))
    dec = next(i for i, l in enumerate(lines) if l.startswith("## Decision boundary"))

    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    def separator(cs: list[str]) -> bool:
        return all(set(c) <= set("-: ") for c in cs)

    index: dict = {}
    for line in lines[idx:reg]:
        if not line.startswith("|"):
            continue
        cs = cells(line)
        if separator(cs) or cs[0].startswith("Frozen path"):
            continue
        index[cs[0].strip("`")] = {
            "ars": re.findall(r"`(AR-\d+)`", cs[1]),
            "codes": re.findall(r"`([A-Z_]+)`", cs[2]),
        }
    rows: list[dict] = []
    for line in lines[reg:dec]:
        if not line.startswith("|"):
            continue
        cs = cells(line)
        if len(cs) < 9 or cs[0] == "ID" or separator(cs):
            continue
        rows.append({
            "id": cs[0].strip("`"), "path": cs[1].strip("`"), "resp": cs[2],
            "symbols": re.findall(r"`([^`]+)`", cs[3]), "code": cs[5].strip("`"),
            "role": cs[6], "provider": cs[7], "gate": cs[8],
        })
    return index, rows


def is_shared(path: str) -> bool:
    return any(path.endswith(s) for s in SHARED_HOSTS)


def symbol_names(groups: list[str]) -> list[str]:
    """Split the manifest's stable-symbol cell into checkable names (ranges a..b give both ends)."""
    out: list[str] = []
    for grp in groups:
        for part in re.split(r"[,\s]+", grp):
            part = part.strip()
            if not part:
                continue
            parts = [x for x in part.split("..") if x] if ".." in part else [part]
            for name in parts:
                name = re.sub(r"\(.*$", "", name)
                comps = [c for c in re.split(r"[.:#]+", name) if c]
                if comps and all(re.match(r"^[A-Za-z_$][\w$]*$", c) for c in comps):
                    out.append(name)
    return out
