"""Opt-in local Atlas execution adapter; no Swarm executor fallback.

The dedicated local service reads one Atlas-owned pairing file. Its secret is
never part of browser RPCs, URL parameters or provider context. This is not a
remote callback facility: the endpoint must be literal IPv4 loopback.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from .native_business_contract import NativeBusinessViolation

VERSION = "atlas.live-voice.local.v1"


class AtlasLocalHost:
    def __init__(self, pairing_file):
        self._path = Path(pairing_file)
        self._pins = {}

    @classmethod
    def configured(cls):
        path = os.environ.get("JIUWENSWARM_ATLAS_HOST_FILE")
        return cls(path) if path else None

    def _registration(self, binding):
        try:
            if self._path.stat().st_size > 4096:
                raise ValueError()
            value = json.loads(self._path.read_text(encoding="utf-8"))
            if (type(value) is not dict or set(value) != {"version", "endpoint", "token", "swarm_session_id", "binding"}
                    or value["version"] != VERSION or value["swarm_session_id"] != binding.session_id
                    or type(value["token"]) is not str or len(value["token"]) != 64
                    or any(c not in "0123456789abcdef" for c in value["token"])
                    or type(value["binding"]) is not dict or set(value["binding"]) != {"bindingId", "sessionId"}
                    or any(type(v) is not str or not v or len(v) > 256 for v in value["binding"].values())):
                raise ValueError()
            endpoint = urlsplit(value["endpoint"])
            if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not endpoint.port
                    or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                    or endpoint.path != "/live-voice/business"):
                raise ValueError()
            key = (binding.session_id, binding.interaction_id, binding.activation_id, binding.activation_generation)
            digest = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
            if key not in self._pins:
                if len(self._pins) >= 128:
                    raise ValueError()
                self._pins[key] = digest
            elif self._pins[key] != digest:
                raise ValueError()
            return value
        except (OSError, TypeError, ValueError, KeyError):
            raise NativeBusinessViolation("ATLAS_HOST_BINDING_UNAVAILABLE") from None

    async def _call(self, binding, method, params):
        registration = self._registration(binding)
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as client:
            async with client.post(registration["endpoint"], allow_redirects=False,
                    headers={"Authorization": "Bearer " + registration["token"]},
                    json={"version": VERSION, "binding": registration["binding"], "method": method, "params": params}) as response:
                if response.status != 200:
                    raise NativeBusinessViolation("ATLAS_HOST_UNAVAILABLE")
                body = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    body.extend(chunk)
                    if len(body) > 524288:
                        raise NativeBusinessViolation("ATLAS_HOST_RESULT_TOO_LARGE")
                result = json.loads(body)
        # A pairing change while HTTP was pending invalidates this observation.
        self._registration(binding)
        if type(result) is not dict or set(result) != {"ok", "result"} or result["ok"] is not True:
            raise NativeBusinessViolation("ATLAS_HOST_REQUEST_FAILED")
        return result["result"]

    async def context(self, binding):
        result = await self._call(binding, "context", {})
        if (type(result) is not dict or set(result) != {"history", "calls"}
                or type(result["history"]) is not list or type(result["calls"]) is not list
                or len(result["calls"]) > 128):
            raise NativeBusinessViolation("ATLAS_HOST_CONTEXT_INVALID")
        tasks, works, events = [], [], []
        for call in result["calls"]:
            call_id, revision, phase = call["callId"], call["revision"], call["status"]
            if (type(call_id) is not str or not call_id.startswith(("task:", "work:"))
                    or type(revision) is not int or revision < 1):
                raise NativeBusinessViolation("ATLAS_HOST_CONTEXT_INVALID")
            terminal = phase in {"completed", "failed", "aborted", "withdrawn", "unknown"}
            outcome = {"aborted": "cancelled", "withdrawn": "cancelled"}.get(phase, phase)
            target = "atlas:" + call_id
            common = {"execution_owner": "atlas", "atlas_turn_id": call["turnId"], "atlas_mandate_id": call["mandateId"],
                      "phase": phase, "result_text": call["text"] if terminal else None, "files": call["files"],
                      "result_truncated": call["textTruncated"]}
            if call_id.startswith("task:"):
                tasks.append({**common, "task_id": target, "name": call["requestText"][:80], "revision_number": revision,
                              "state": "terminal" if terminal else "running", "outcome": outcome if terminal else None,
                              "supported_operations": ["task.status", "task.result"]})
                # This identifies the Atlas execution for Native delivery. It is
                # not a Swarm Task adjustment and must not claim applied/rejected.
                identity = {"work_id": target}
            else:
                works.append({**common, "work_id": target, "revision": revision, "sequence": revision,
                              "instruction": call["requestText"], "state": outcome if terminal else "running",
                              "execution_settled": terminal, "reason": "awaiting_atlas_user" if phase == "waiting_for_user" else None})
                identity = {"work_id": target}
            if terminal:
                text = call["text"]
                if len(text.encode("utf-8")) > 131072:
                    text = text.encode("utf-8")[:131072].decode("utf-8", errors="ignore")
                events.append({**identity, "event_id": "atlas-result-" + hashlib.sha256(
                    json.dumps([binding.session_id, target, revision], separators=(",", ":")).encode()).hexdigest(),
                    "revision": revision, "state": outcome, "result_text": text or None,
                    "reason": "ATLAS_RESULT_TRUNCATED" if call["textTruncated"] else None})
        if len(works) > 32:
            raise NativeBusinessViolation("ATLAS_HOST_WORK_CAPACITY")
        return {"history": result["history"], "tasks": tasks, "works": works, "events": events}

    async def execute(self, binding, delegate):
        action = delegate.business
        if action.operation in {"task.create", "work.start"}:
            call_id = action.operation.split(".")[0] + ":" + delegate.source_identity
            text = delegate.request_text
            if action.instruction and action.instruction != text:
                text += "\n\n执行说明：\n" + action.instruction
            try:
                accepted = await self._call(binding, "submit", {"callId": call_id, "text": text,
                    "nativeTurnKey": json.dumps([binding.interaction_id, delegate.turn_id], separators=(",", ":")),
                    "userText": delegate.request_text})
                if type(accepted) is not dict or type(accepted.get("turnId")) is not str or not accepted["turnId"]:
                    raise ValueError()
            except Exception:
                # The Atlas request may already have run. Never label a lost
                # acceptance as rejection or retry with a different request ID.
                return {"status": "unknown", "reason": "ATLAS_ACCEPTANCE_UNKNOWN", "host_call_id": call_id}
            identity = "atlas:" + call_id
            if action.operation == "task.create":
                return {"status": "dispatched", "task_id": identity,
                        "receipt": {"task_id": identity, "state": "accepted", "execution_owner": "atlas",
                                    "atlas_turn_id": accepted["turnId"], "atlas_mandate_id": accepted.get("mandateId")}}
            return {"work": {"work_id": identity, "revision": 1, "sequence": 1, "state": "accepted",
                             "execution_settled": False, "reason": None, "execution_owner": "atlas"}}
        if action.operation in {"task.list", "task.status", "task.result", "work.list", "work.get"}:
            context = await self.context(binding)
            collection = context["tasks"] if action.operation.startswith("task.") else context["works"]
            if action.operation.endswith(".list"):
                return {"status": "observed", "tasks" if action.operation.startswith("task.") else "works": collection}
            id_key = "task_id" if action.operation.startswith("task.") else "work_id"
            fact = next((item for item in collection if item[id_key] == action.target_id), None)
            if fact is None:
                return {"status": "rejected", "reason": "ATLAS_TARGET_NOT_FOUND"}
            events = [event for event in context["events"] if event.get("work_id") == action.target_id]
            return {"status": "observed", "task" if id_key == "task_id" else "work": fact,
                    "host_notifications": events}
        return {"status": "rejected", "reason": "ATLAS_OPERATION_REQUIRES_EXISTING_ATLAS_UI"}
