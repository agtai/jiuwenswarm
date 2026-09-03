"""Small state-driven audio journey against an owned isolated browser/runtime.

No transcript submission, Task RPC or structured business buttons. Read-only
SQLite observations are test oracles, never inputs to the production parser.
Each invocation records all attempts; a failed dependent step stops that run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import time
from pathlib import Path

from scripts.live_voice.semantic_audio_assertions import (
    assert_effects,
    project_snapshot,
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def observe(runtime):
    store = runtime / "runtime/live_voice/p3alpha/formal_tasks.sqlite3"
    with sqlite3.connect(store.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        tasks = [
            dict(row)
            for row in connection.execute(
                "SELECT task_id,attempt_id,state,outcome,spec_json,predecessor_task_id,event_head FROM tasks"
            )
        ]
        commands = [
            dict(row)
            for row in connection.execute(
                "SELECT command_id,command_type,result_json FROM commands ORDER BY created_at"
            )
        ]
        events = [
            dict(row)
            for row in connection.execute(
                "SELECT task_id,attempt_id,event_type,outcome,details_json FROM task_events ORDER BY occurred_at,seq"
            )
        ]
        results = [
            dict(row) for row in connection.execute("SELECT * FROM task_results")
        ]
    journal = Path(str(store) + ".unified-committed-input.sqlite3")
    with sqlite3.connect(journal.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        turns = []
        for row in connection.execute(
            "SELECT * FROM unified_committed_inputs ORDER BY created_at"
        ):
            binding = (
                json.loads(row["semantic_binding_json"])
                if row["semantic_binding_json"]
                else None
            )
            turns.append(
                {
                    "request_id": row["request_id"],
                    "status": row["status"],
                    "result": json.loads(row["result_json"])
                    if row["result_json"]
                    else None,
                    "semantics": binding,
                }
            )
        pending = [
            dict(row)
            for row in connection.execute(
                "SELECT context_id,source_id,kind,payload_json,consumed_by,expires_at FROM semantic_pending_contexts"
            )
        ]
    return {
        "tasks": tasks,
        "commands": commands,
        "events": events,
        "results": results,
        "turns": turns,
        "pending": pending,
    }


class Journey:
    def __init__(self, browser, runtime, output):
        self.browser, self.runtime, self.output = browser, runtime, output
        self.source = read_json(runtime / "source.json")
        self.project = Path(self.source["project"])
        self.symbols = {}
        self.index = max(
            [
                int(p.stem.split("-")[1])
                for p in browser.glob("command-*.json")
                if not p.name.endswith(".result.json")
            ]
            + [0]
        )

    async def command(self, value):
        self.index += 1
        path = self.browser / f"command-{self.index:03}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        target = path.with_name(path.stem + ".result.json")
        deadline = time.monotonic() + 15
        while not target.exists():
            if time.monotonic() > deadline:
                raise TimeoutError("browser command deadline")
            await asyncio.sleep(0.1)
        result = read_json(target)
        if result["status"] != "PASS":
            raise RuntimeError(f"browser action failed: {result}")
        return result["result"]

    async def listening(self, timeout=480):
        deadline = time.monotonic() + timeout
        while True:
            state = await self.command({"kind": "snapshot"})
            if "语音恢复失败" in state["text"]:
                raise RuntimeError(
                    "formal voice recovery failure (see browser snapshot)"
                )
            if (
                "正在听你说话" in state["text"]
                and state.get("audio", {}).get("captures") == 1
            ):
                return state
            if time.monotonic() > deadline:
                raise TimeoutError("listening window not reached")
            await asyncio.sleep(0.5)

    async def fresh_capture(self):
        """Use a full real capture window, never inject over its known rollover."""
        state = await self.listening()
        if self.source["engine"] == "openai-realtime-native":
            return  # The Native route has a continuous, not rotating, capture.
        if state["audio"].get("capture_age_ms", 10000) < 1000:
            return
        opened = max(
            [
                e["sequence"]
                for e in self.output_events()
                if e["kind"] == "capture-opened"
            ]
            + [0]
        )
        deadline = time.monotonic() + 45
        while True:
            new = [
                e
                for e in self.output_events()
                if e["kind"] == "capture-opened" and e["sequence"] > opened
            ]
            if new:
                await self.listening()
                return
            if time.monotonic() > deadline:
                raise TimeoutError("new normal capture window not observed")
            await asyncio.sleep(0.1)

    def output_events(self):
        path = self.browser / "events.jsonl"
        return (
            [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            if path.exists()
            else []
        )

    async def sample(self, name):
        result = {"sample": name, "status": "FAIL", "stage": "ready"}
        before = observe(self.runtime)
        before_files = project_snapshot(self.project)
        existing = {row["request_id"] for row in before["turns"]}
        try:
            await self.fresh_capture()
            event_start = max(
                [event["sequence"] for event in self.output_events()] + [0]
            )
            result["stage"] = "capture"
            result["injection"] = await self.command({"kind": "speak", "sample": name})
            result["stage"] = "formal-commit-and-semantics"
            deadline = time.monotonic() + 150
            while True:
                observed = observe(self.runtime)
                fresh = [
                    row
                    for row in observed["turns"]
                    if row["request_id"] not in existing
                ]
                if fresh and all(row["status"] == "completed" for row in fresh):
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("formal committed semantic result missing")
                await asyncio.sleep(0.4)
            result["turns"] = fresh
            if len(fresh) != 1:
                raise AssertionError("audio final duplicated")
            if not fresh[0]["result"]["ok"]:
                raise AssertionError("formal submit failed")
            body = fresh[0]["semantics"]["body"]
            result["transcript"] = body["input"]["commit"]["text"]
            decision = body["output"]
            result["stage"] = "normal-output-playback"
            await self.listening()
            # Drain lag is bounded by the existing test observer queue, not a
            # product delay. Ended+non-silent PCM proves render, not queued TTS.
            deadline = time.monotonic() + 15
            while True:
                audio = [
                    event
                    for event in self.output_events()
                    if event["sequence"] > event_start
                ]
                ended = {
                    event["id"] for event in audio if event["kind"] == "output-ended"
                }
                rendered = [
                    event
                    for event in audio
                    if event["kind"] == "output-buffer"
                    and event["rms"] > 0.001
                    and event["id"] in ended
                ]
                if rendered:
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("non-silent output render not observed")
                await asyncio.sleep(0.25)
            if any(event["kind"] == "observation-failed" for event in audio):
                raise AssertionError("audio observation failed")
            result["audio"] = {
                "rendered_chunks": len(rendered),
                "pcm_sha256": [e["pcm_sha256"] for e in rendered],
            }
            result["stage"] = "authority-and-effects"
            after = observe(self.runtime)
            if name == "analysis":
                # Listening is not proof that asynchronous proposal extraction
                # settled. Wait for this exact presented source, never another
                # conversation's pending proposal, then assess its real outcome.
                deadline = time.monotonic() + 65
                while True:
                    sources = [
                        p
                        for p in after["pending"]
                        if p["kind"] == "analysis"
                        and json.loads(p["payload_json"])["commit"]["commit_id"]
                        == body["input"]["commit"]["commit_id"]
                    ]
                    if sources and sources[0]["consumed_by"] is not None:
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            "exact presented analysis extraction did not settle"
                        )
                    await asyncio.sleep(0.25)
                    after = observe(self.runtime)
            result["after"] = after
            new_commands = [
                row
                for row in after["commands"]
                if row not in before["commands"]
                and row["command_type"] != "task.ack_events"
            ]
            if name in {
                "missing_proposal",
                "negation",
                "missing_target",
                "ambiguous_cancel",
                "analysis",
                "foreground",
                "compare",
                "costs",
                "departure",
            }:
                assert not new_commands, "unrequested Task command"
            if name in {"missing_proposal", "missing_target", "ambiguous_cancel"}:
                assert decision["route"] == "clarification", decision
            if name == "negation":
                assert decision["route"] in {"clarification", "dialogue"}, decision
            if name == "analysis":
                assert decision["route"] == "dialogue", decision
            expected = {
                "accept_proposal": "task.create",
                "confirm_A": "task.create",
                "create_B": "task.create",
                "confirm_B": "task.create",
                "adjust_A": "task.adjust",
                "confirm_adjust": "task.adjust",
                "query_A": "task.status",
                "query_B": "task.status",
                "clarify_B": "task.cancel",
                "confirm_cancel_B": "task.cancel",
                "successor": "task.create_successor",
                "confirm_successor": "task.create_successor",
                "garden_create": "task.create",
                "garden_confirm": "task.create",
            }.get(name)
            if expected:
                assert decision["operation"] == expected, decision
            candidate_symbols = dict(self.symbols)
            result["effects"] = assert_effects(
                name,
                before,
                after,
                body,
                candidate_symbols,
                before_files,
                project_snapshot(self.project),
                fresh[0]["result"]["result"],
            )
            self.symbols = candidate_symbols
            result["status"] = "PASS"
            result["stage"] = "completed"
            return result
        except Exception as error:
            result["error"] = str(error)
            result["after"] = observe(self.runtime)
            return result


async def run(options):
    if options.output.exists():
        raise ValueError("never overwrite a previous attempt report")
    journal = Journey(
        options.browser.resolve(), options.runtime.resolve(), options.output
    )
    if options.symbols_from:
        prior = read_json(options.symbols_from)
        if prior["source"]["project_id"] != journal.source["project_id"]:
            raise ValueError("symbol observation belongs to another project")
        journal.symbols = prior["symbols"]
    report = {
        "version": 1,
        "overall": "PARTIAL",
        "source": read_json(options.runtime / "source.json"),
        "cases": [],
        "limitations": [
            "digital audio only; no physical microphone/speaker claim",
            "Task cases additionally require exact effect/artifact assertions before acceptance",
        ],
    }
    for name in options.samples:
        case = await journal.sample(name)
        report["cases"].append(case)
        report["symbols"] = journal.symbols
        options.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: case.get(k)
                    for k in ("sample", "status", "stage", "transcript", "error")
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if case["status"] != "PASS":
            return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--symbols-from", type=Path)
    parser.add_argument(
        "--samples",
        nargs="+",
        default=[
            "missing_proposal",
            "negation",
            "missing_target",
            "analysis",
            "accept_proposal",
            "confirm_A",
        ],
    )
    raise SystemExit(asyncio.run(run(parser.parse_args())))
