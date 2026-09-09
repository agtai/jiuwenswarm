# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded Native conversation facts selected after authenticated scope checks.

Snapshots are data, never grants. A command must retain the observed snapshot
and exact target revision, then pass the production service's final authority
reread. Audio history contains only the canonical acknowledged transcript.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import ContextRef, ScopeRef, canonical_json_bytes
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import FormalContextEntry, FormalContextSnapshot
from .native_business_contract import NativeBusinessAction, NativeBusinessViolation


def _digest(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def select_conversation_history(records, *, maximum_bytes=16384, maximum_messages=24):
    """Read committed user/visible assistant records, never drafts or tools."""
    selected, size = [], 0
    for record in reversed(records):
        if not isinstance(record, Mapping) or record.get("role") not in {"user", "assistant"}:
            continue
        content = record.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if record.get("is_streaming") or record.get("status") in {"pending", "streaming", "generating"}:
            continue
        binding = record.get("formal_binding")
        native = isinstance(binding, Mapping) and binding.get("surface") == "native_audio"
        # The canonical Native writer publishes assistant audio only after its
        # real presentation ACK. Do not infer that ordinary visible text was heard.
        entry = {"role": record["role"], "content": content,
                 "delivery": "user_input" if record["role"] == "user" else "heard" if native else "visible_text"}
        count = len(canonical_json_bytes(entry))
        if len(selected) >= maximum_messages:
            break
        if size + count > maximum_bytes:
            continue
        selected.append(entry)
        size += count
    return list(reversed(selected))


def formal_context(scope: ScopeRef, facts: Mapping[str, object], *, source="live_voice.native_business_context") -> FormalContextSnapshot:
    content = json.dumps(dict(facts), ensure_ascii=False, separators=(",", ":"))
    identity = _digest({"scope": scope.to_dict(), "facts": dict(facts)})
    ref = ContextRef.from_dict({
        "source": source, "stable_id": f"native-context:{identity}",
        "uri": f"live-voice-cr://context/{identity}",
        "revision": {"kind": "snapshot", "value": "sha256:" + hashlib.sha256(content.encode()).hexdigest()},
        "scope": scope.to_dict(), "permissions": ["agent.context.read"], "expires_at": None,
        "redaction": {"policy_id": "live_voice.presented_text.v1", "redacted": False, "fields": []},
        "extensions": {},
    })
    return FormalContextSnapshot(scope, (FormalContextEntry(ref, content),))


@dataclass(frozen=True)
class NativeContextSelection:
    scope: ScopeRef
    context_id: str
    payload_json: str
    formal: FormalContextSnapshot

    def payload(self):
        return json.loads(self.payload_json)


class NativeBusinessContextStore:
    def __init__(self, *, capacity=128):
        self._capacity = capacity
        self._snapshots = OrderedDict()

    def select(self, *, scope, history, tasks, works, model):
        facts = {"history": history, "tasks": tasks, "works": works, "model": model}
        # Scope participates in identity even when two sessions have equal text.
        identity = _digest({"scope": scope.to_dict(), **facts})
        key = (scope, identity)
        prior = self._snapshots.get(key)
        if prior is not None:
            self._snapshots.move_to_end(key)
            return prior
        payload = {"context_id": identity, **facts}
        selection = NativeContextSelection(scope, identity,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), formal_context(scope, facts))
        self._snapshots[key] = selection
        while len(self._snapshots) > self._capacity:
            self._snapshots.popitem(last=False)
        return selection

    def require(self, scope, action: NativeBusinessAction) -> NativeContextSelection:
        selection = self._snapshots.get((scope, action.context_id))
        if selection is None:
            raise NativeBusinessViolation("NATIVE_BUSINESS_CONTEXT_STALE")
        facts = selection.payload()
        # Other capability owners resolve their targets inside the authorized
        # session. Goal controls compare their own control revision under the
        # SDK lock; they cannot use a Work/Task snapshot as control authority.
        if action.target_id is not None and not action.operation.startswith(("workflow.", "goal.", "agent.", "team.", "core_workflow.")):
            collection = facts["tasks"] if action.operation.startswith("task.") else facts["works"]
            key = "task_id" if action.operation.startswith("task.") else "work_id"
            revision_key = "revision_number" if key == "task_id" else "revision"
            target = next((item for item in collection if item.get(key) == action.target_id), None)
            if target is None:
                raise NativeBusinessViolation("NATIVE_BUSINESS_TARGET_NOT_OBSERVED")
            if action.expected_revision is not None and target.get(revision_key) != action.expected_revision:
                raise NativeBusinessViolation("NATIVE_BUSINESS_REVISION_NOT_OBSERVED")
        return selection
