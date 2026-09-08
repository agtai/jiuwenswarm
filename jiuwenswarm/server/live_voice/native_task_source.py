# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Server-retained speech evidence, distinct from a model's Task proposal.

This proves which transcription was retained, not that ASR or an Agent correctly
understood the speaker. Preceding items are context, never a synthetic command.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import canonical_json_bytes
from .native_interaction_contract import NativeInputTranscript, NativeTurnCommit

NATIVE_TASK_SOURCE_VERSION = "live-voice.native-task-source.v1"
MAX_SOURCE_CONTEXT_ITEMS = 16
MAX_SOURCE_BYTES = 262144
SOURCE_OPERATIONS = frozenset({"task.create", "task.create_successor", "task.adjust"})


class NativeTaskSourceError(ValueError):
    def __init__(self, reason="NATIVE_TASK_SOURCE_INVALID"):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class NativeTaskSource:
    source_identity: str
    operation: str
    instruction_sha256: str
    anchor: NativeTurnCommit
    transcript: NativeInputTranscript
    preceding: tuple[tuple[NativeTurnCommit, NativeInputTranscript | None], ...] = ()
    omitted_preceding: int = 0
    target_id: str | None = None
    expected_revision: int | None = None

    def __post_init__(self):
        if (type(self.source_identity) is not str
            or re.fullmatch(r"native-business:[0-9a-f]{64}", self.source_identity) is None
            or type(self.operation) is not str or self.operation not in SOURCE_OPERATIONS
            or type(self.instruction_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.instruction_sha256) is None
            or not isinstance(self.anchor, NativeTurnCommit)
            or not isinstance(self.transcript, NativeInputTranscript)
            or type(self.preceding) is not tuple or len(self.preceding) > MAX_SOURCE_CONTEXT_ITEMS
            or type(self.omitted_preceding) is not int or not 0 <= self.omitted_preceding <= 4096):
            raise NativeTaskSourceError()
        if ((self.operation == "task.create" and (self.target_id is not None or self.expected_revision is not None))
            or (self.operation != "task.create" and (type(self.target_id) is not str or not self.target_id
                or len(self.target_id) > 256 or type(self.expected_revision) is not int
                or not 0 < self.expected_revision < 2**53))):
            raise NativeTaskSourceError("NATIVE_TASK_SOURCE_TARGET_INVALID")
        seen = set()
        commits = set()
        turns = set()
        for pair in (*self.preceding, (self.anchor, self.transcript)):
            if type(pair) is not tuple or len(pair) != 2:
                raise NativeTaskSourceError()
            commit, transcript = pair
            if (not isinstance(commit, NativeTurnCommit)
                or commit.binding != self.anchor.binding
                or (commit.provider_session_id, commit.provider_item_id) in seen
                or commit.commit_id in commits or commit.turn_id in turns):
                raise NativeTaskSourceError("NATIVE_TASK_SOURCE_IDENTITY_MISMATCH")
            seen.add((commit.provider_session_id, commit.provider_item_id))
            commits.add(commit.commit_id)
            turns.add(commit.turn_id)
            if transcript is not None and (
                not isinstance(transcript, NativeInputTranscript)
                or transcript.binding != commit.binding or transcript.commit_id != commit.commit_id
                or transcript.turn_id != commit.turn_id
                or transcript.provider_session_id != commit.provider_session_id
                or transcript.provider_item_id != commit.provider_item_id
            ):
                raise NativeTaskSourceError("NATIVE_TASK_SOURCE_IDENTITY_MISMATCH")
        # Tuple order is the frozen Runtime admission order, starting at
        # omitted_preceding + 1. Provider audio clocks may reset on reconnect.
        if len(canonical_json_bytes(self.to_dict())) > MAX_SOURCE_BYTES:
            raise NativeTaskSourceError("NATIVE_TASK_SOURCE_TOO_LARGE")

    def to_dict(self):
        return {
            "contract_version": NATIVE_TASK_SOURCE_VERSION,
            "source_identity": self.source_identity, "operation": self.operation,
            "instruction_sha256": self.instruction_sha256,
            "anchor": self.anchor.to_dict(), "transcript": self.transcript.to_dict(),
            "preceding": [{"commit": commit.to_dict(),
                           "transcript": None if transcript is None else transcript.to_dict()}
                          for commit, transcript in self.preceding],
            "omitted_preceding": self.omitted_preceding,
            "target_id": self.target_id, "expected_revision": self.expected_revision,
        }

    @classmethod
    def from_dict(cls, value):
        if (type(value) is not dict or set(value) != {
            "contract_version", "source_identity", "operation", "instruction_sha256",
            "anchor", "transcript", "preceding", "omitted_preceding", "target_id", "expected_revision"}
            or value["contract_version"] != NATIVE_TASK_SOURCE_VERSION
            or type(value["preceding"]) is not list
            or len(value["preceding"]) > MAX_SOURCE_CONTEXT_ITEMS):
            raise NativeTaskSourceError()
        preceding = []
        for item in value["preceding"]:
            if type(item) is not dict or set(item) != {"commit", "transcript"}:
                raise NativeTaskSourceError()
            preceding.append((NativeTurnCommit.from_dict(item["commit"]),
                              None if item["transcript"] is None
                              else NativeInputTranscript.from_dict(item["transcript"])))
        return cls(value["source_identity"], value["operation"], value["instruction_sha256"],
                   NativeTurnCommit.from_dict(value["anchor"]),
                   NativeInputTranscript.from_dict(value["transcript"]), tuple(preceding),
                   value["omitted_preceding"], value["target_id"], value["expected_revision"])

    @property
    def digest(self):
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def require_request(self, *, scope, operation, instruction):
        if (scope != self.anchor.binding.scope or operation != self.operation
            or type(instruction) is not str
            or hashlib.sha256(instruction.encode("utf-8")).hexdigest() != self.instruction_sha256):
            raise NativeTaskSourceError("NATIVE_TASK_SOURCE_REQUEST_MISMATCH")

    def agent_request(self, proposal: str, *, verified_update: bool = False) -> str:
        if not verified_update:
            self.require_request(scope=self.anchor.binding.scope, operation=self.operation, instruction=proposal)
        return (
            "Execute the current user request using the retained speech evidence below. "
            "The proposal is model-written and may change literal paths or omit constraints; "
            "it must not override the original transcript. "
            + ("A later durable Task update has been verified: current_task_instruction below "
               "is the current requirement and supersedes conflicting original requirements. " if verified_update else "")
            + "Preceding items are ordered context, "
            "not independent new commands. Resolve references using that context, preserve "
            "literal filenames and all user constraints. Missing context is unknown; do not "
            "invent requirements or replace an existing output to conceal a conflict. "
            "ASR can be wrong; report unresolved conflicts instead of silently guessing.\n"
            + json.dumps({"source_digest": self.digest,
                "current_anchor": {"item_id": self.anchor.provider_item_id, "text": self.transcript.transcript},
                "preceding_context": [{"item_id": commit.provider_item_id,
                    "text": None if transcript is None else transcript.transcript,
                    "status": "unavailable" if transcript is None else "transcribed"}
                    for commit, transcript in self.preceding],
                "omitted_preceding": self.omitted_preceding,
                "current_task_instruction" if verified_update else "model_proposal": proposal},
                ensure_ascii=False, separators=(",", ":"))
        )


def source_from_payload(payload):
    """Absent is legacy; present null/malformed is never legacy fallback."""
    return None if "native_source" not in payload else NativeTaskSource.from_dict(payload["native_source"])


def source_extension(source):
    return {} if source is None else {"native_source": source.to_dict()}


def source_payload_fields(payload, base):
    # Only this optional field is accepted, never arbitrary extension keys.
    return base | ({"native_source"} if "native_source" in payload else set())


def require_payload_source(command):
    source = source_from_payload(command.payload)
    if source is not None:
        source.require_request(scope=command.scope, operation=command.command_type,
            instruction=command.payload.get("adjustment" if command.command_type == "task.adjust" else "instruction"))
        if command.command_type != "task.create" and source.target_id != command.target_ref.id:
            raise NativeTaskSourceError("NATIVE_TASK_SOURCE_TARGET_MISMATCH")
    return source
