# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Cancel background Tasks left behind by latency_baseline_driver task rounds.

The task scenario really creates background work in the disposable
validation project. Those Tasks keep executing after the measurement and
compete with later foreground turns for the Agent, so a quiet re-measurement
first lists the project's Tasks through the same product RPCs the browser uses
and cancels the ones that are still live. Nothing else is touched.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import websockets  # noqa: E402

from scripts.live_voice.latency_baseline_driver import (  # noqa: E402
    MODEL_NAME,
    ORIGIN,
    PROJECT_DIR,
    PROJECT_ID,
    WS_URL,
    Client,
    _ok,
)

LIVE_STATES = {"queued", "pending", "running", "scheduled", "accepted", "created", "starting", "in_progress", "waiting"}


def _header_kwarg() -> str:
    params = inspect.signature(websockets.connect).parameters
    return "additional_headers" if "additional_headers" in params else "extra_headers"


async def main_async(args: argparse.Namespace) -> int:
    async with websockets.connect(WS_URL, open_timeout=20, max_size=8 << 20, **{_header_kwarg(): {"Origin": ORIGIN}}) as socket:
        client = Client(socket)
        session_ids = list(args.session_id)
        if not session_ids:
            ok, created = _ok(await client.request("session.create", {"create_token": str(uuid.uuid4()), "mode": "agent", "is_swarm": False, "title": "lv-latency-cleanup", "work_mode": "code", "model_name": MODEL_NAME, "project_id": PROJECT_ID, "project_dir": PROJECT_DIR}))
            session_id = created.get("session_id") or (created.get("session") or {}).get("session_id")
            if not ok or not session_id:
                print(f"session.create failed: {json.dumps(created, ensure_ascii=False)[:400]}")
                return 2
            session_ids = [session_id]
        tasks: list[tuple[str, dict]] = []
        if args.task_id:
            # Explicit ids (e.g. live ids recovered from the runtime log) are
            # attempted under every supplied session; the server decides scope.
            tasks = [(session_id, {"task_id": task_id, "state": "running"}) for session_id in session_ids for task_id in args.task_id]
            session_ids = []
        for session_id in session_ids:
            ok, listed = _ok(await client.request("live_voice.task.list", {"session_id": session_id, "limit": 100}))
            if not ok:
                print(f"task.list failed for {session_id}: {json.dumps(listed, ensure_ascii=False)[:300]}")
                continue
            items = listed.get("tasks")
            if not isinstance(items, list):
                inner = listed.get("result") if isinstance(listed.get("result"), dict) else {}
                items = inner.get("tasks") if isinstance(inner.get("tasks"), list) else []
            print(f"{session_id}: {len(items)} tasks; keys of first: {sorted(items[0]) if items else []}")
            tasks.extend((session_id, item) for item in items if isinstance(item, dict))
        cancelled = skipped = failed = 0
        for session_id, task in tasks:
            task_id = task.get("task_id") or task.get("id")
            state = str(task.get("status") or task.get("state") or task.get("lifecycle") or "").lower()
            if not task_id:
                continue
            if state and state not in LIVE_STATES and not args.all:
                skipped += 1
                continue
            ok, result = _ok(await client.request("live_voice.task.cancel", {"session_id": session_id, "task_id": task_id, "reason": "latency-baseline-cleanup"}, timeout=60))
            if ok:
                cancelled += 1
                print(f"  cancelled {task_id} (was {state or '?'})")
            else:
                failed += 1
                print(f"  cancel failed {task_id} (was {state or '?'}): {json.dumps(result, ensure_ascii=False)[:240]}")
        client.close()
    print(f"cancelled={cancelled} skipped(terminal)={skipped} failed={failed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="attempt to cancel every listed task regardless of reported state")
    parser.add_argument("--session-id", action="append", default=[], help="existing session id that owns the tasks (repeatable); default creates a fresh session")
    parser.add_argument("--task-id", action="append", default=[], help="explicit task id to cancel under each supplied session (repeatable); skips listing")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
