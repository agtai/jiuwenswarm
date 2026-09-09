"""Bounded, authority-free storage for one unpublished Provider continuation.

This object never constructs a Runtime proposal. Its observations can establish
which audio needs zero-played truncation; they cannot establish played output.
"""

from __future__ import annotations

import base64
import binascii
import json
import unicodedata
from collections import deque
from dataclasses import dataclass, field

from jiuwenswarm.server.live_voice.openai_realtime_session import OpenAIRealtimeEvent
from jiuwenswarm.server.live_voice.native_business_tools import NATIVE_BUSINESS_FUNCTION_NAMES

MAX_PREPARED_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_PREPARED_OUTPUT_EVENTS = 4096


class PreparedOutputViolation(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def prepared_failure_shape(event_type, data):
    """Closed structural labels only; never serialize content, arguments or keys."""
    try:
        def label(value, allowed):
            return value if type(value) is str and value in allowed else "missing" if value is None else "other"
        item = data.get("item") if type(data) is dict else None
        part = data.get("part") if type(data) is dict else None
        return {
            "provider_event_type": label(event_type, {
                "response.output_item.added", "response.output_item.done",
                "response.content_part.added", "response.content_part.done",
                "response.function_call_arguments.delta", "response.function_call_arguments.done",
                "response.output_audio.delta", "response.output_audio.done",
                "response.output_audio_transcript.delta", "response.output_audio_transcript.done", "response.done"}),
            "output_item_type": label(item.get("type") if type(item) is dict else None, {"message", "function_call", "reasoning"}),
            "output_phase": label(item.get("phase") if type(item) is dict else None, {"final_answer", "commentary"}),
            "output_content_type": label(part.get("type") if type(part) is dict else None, {"audio", "output_audio", "text", "output_text"}),
            "part_field_count": len(part) if type(part) is dict else None,
            "part_has_transcript": type(part) is dict and "transcript" in part,
        }
    except Exception:
        return {}


def _identity(value):
    if (type(value) is not str or not value or value != value.strip() or len(value) > 256
            or len(value.encode("utf-8")) > 1024
            or any(unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} for c in value)):
        raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_INVALID")
    return value


def _transcript(value):
    if type(value) is not str:
        raise PreparedOutputViolation("NATIVE_PREPARED_TRANSCRIPT_INVALID")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if (len(normalized.encode("utf-8")) > 65536
            or any(c != "\n" and unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"}
                   for c in normalized.strip())):
        raise PreparedOutputViolation("NATIVE_PREPARED_TRANSCRIPT_INVALID")
    return normalized


@dataclass(slots=True)
class PreparedProviderOutput:
    provider_id: str
    event_queue_capacity: int = 256
    events: deque[OpenAIRealtimeEvent] = field(default_factory=deque, repr=False)
    byte_count: int = 0
    event_count: int = 0
    terminal: bool = False
    terminal_status: str | None = None
    discarded: bool = False
    cleanup_unsupported: bool = False
    audio_targets: set[tuple[str, int]] = field(default_factory=set)
    truncate_sent: set[tuple[str, int]] = field(default_factory=set)
    truncate_acknowledged: set[tuple[str, int]] = field(default_factory=set)
    pending_truncate: tuple[str, int] | None = None
    _early_truncate_ack: bool = False
    _audio_indices: dict[int, tuple[str, int]] = field(default_factory=dict)
    _audio_done: set[int] = field(default_factory=set)
    _transcript_bytes: dict[int, int] = field(default_factory=dict)
    _calls: dict[str, str] = field(default_factory=dict)
    _transcript_done: set[int] = field(default_factory=set)
    _metadata_items: dict[str, str] = field(default_factory=dict)
    _item_indices: dict[int, tuple[str, str]] = field(default_factory=dict)
    _item_done: dict[int, dict] = field(default_factory=dict, repr=False)
    _content_done: dict[tuple[str, int], str] = field(default_factory=dict, repr=False)
    _audio_bytes: dict[int, int] = field(default_factory=dict)
    _audio_remainder: dict[int, int] = field(default_factory=dict)
    _transcript_partial: dict[int, str] = field(default_factory=dict, repr=False)
    _transcript_final: dict[int, str] = field(default_factory=dict, repr=False)
    _argument_partial: dict[int, tuple[str, str, str]] = field(default_factory=dict, repr=False)

    def discard(self) -> None:
        self.discarded = True
        self.events.clear()
        self.byte_count = 0
        self._item_done.clear()
        self._content_done.clear()
        self._transcript_partial.clear()
        self._transcript_final.clear()
        self._argument_partial.clear()
        self._calls.clear()

    def observe(self, event: OpenAIRealtimeEvent, data: dict) -> None:
        """Validate bounded observations before storing anything publishable."""
        try:
            self._observe(event, data)
        except (UnicodeError, TypeError, KeyError, RecursionError, OverflowError):
            self.cleanup_unsupported = True
            raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_INVALID") from None

    def _observe(self, event: OpenAIRealtimeEvent, data: dict) -> None:
        kind = event.event_type
        if self.terminal:
            # A fresh event after terminal cannot be used to prove cleanup.
            self.cleanup_unsupported = True
            raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_AFTER_TERMINAL")
        self.event_count += 1
        if self.discarded and kind != "response.done":
            self._observe_cleanup_identity(kind, data)
            return
        if kind == "response.done":
            self.terminal = True
            self.terminal_status = data["response"]["status"]
            self._terminal_output(data["response"]["output"])
        elif kind.startswith("response.output_audio"):
            item_id = _identity(data["item_id"])
            index, content = data["output_index"], data["content_index"]
            if (type(index) is not int or not 0 <= index < 64
                    or type(content) is not int or not 0 <= content < 64):
                raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_INVALID")
            target = (item_id, content)
            self._remember_audio_target(target)
            self._bind(index, item_id, "message")
            if index in self._audio_indices and self._audio_indices[index] != target:
                self.cleanup_unsupported = True
                raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_IDENTITY_CONFLICT")
            self._audio_indices[index] = target
            self._remember_audio_target(target)
            if len(self.audio_targets) > 1 or self._calls:
                raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_COMPOSITION_UNSUPPORTED")
            if kind == "response.output_audio.delta":
                if index in self._audio_done:
                    raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_AFTER_AUDIO_DONE")
                if type(data["delta"]) is not str:
                    raise PreparedOutputViolation("NATIVE_PREPARED_AUDIO_INVALID")
                try:
                    pcm = base64.b64decode(data["delta"], validate=True)
                except (binascii.Error, ValueError):
                    raise PreparedOutputViolation("NATIVE_PREPARED_AUDIO_INVALID") from None
                if not pcm or len(pcm) % 2 or len(pcm) > 96000:
                    raise PreparedOutputViolation("NATIVE_PREPARED_AUDIO_INVALID")
                combined = self._audio_remainder.get(index, 0) + len(pcm)
                if combined // 960 > self.event_queue_capacity:
                    raise PreparedOutputViolation("NATIVE_PREPARED_AUDIO_EXPANSION_OVERFLOW")
                self._audio_remainder[index] = combined % 960
                self._audio_bytes[index] = self._audio_bytes.get(index, 0) + len(pcm)
            elif kind == "response.output_audio.done":
                if index in self._audio_done:
                    raise PreparedOutputViolation("NATIVE_PREPARED_AUDIO_DONE_CONFLICT")
                self._audio_done.add(index)
                self._audio_remainder[index] = 0
            else:
                partial = kind.endswith(".delta")
                if index in self._transcript_done:
                    raise PreparedOutputViolation("NATIVE_PREPARED_TRANSCRIPT_AFTER_DONE")
                value = data["delta" if partial else "transcript"]
                if type(value) is not str:
                    raise PreparedOutputViolation("NATIVE_PREPARED_TRANSCRIPT_INVALID")
                raw = self._transcript_partial.get(index, "") + value if partial else value
                self._transcript_bytes[index] = len(_transcript(raw).encode("utf-8"))
                if sum(self._transcript_bytes.values()) > 65536:
                    raise PreparedOutputViolation("NATIVE_PREPARED_TRANSCRIPT_TOO_LARGE")
                if not partial:
                    if index in self._transcript_partial and self._transcript_partial[index] != raw:
                        raise PreparedOutputViolation("NATIVE_PREPARED_TRANSCRIPT_CONFLICT")
                    self._transcript_done.add(index)
                    self._transcript_final[index] = raw
                else:
                    self._transcript_partial[index] = raw
        elif kind == "response.function_call_arguments.done":
            self.cleanup_unsupported = True  # No negotiated function-item delete receipt.
            if self.audio_targets:
                raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_COMPOSITION_UNSUPPORTED")
            call_id = _identity(data["call_id"])
            item_id = _identity(data["item_id"])
            if (type(data["name"]) is not str or data["name"] not in NATIVE_BUSINESS_FUNCTION_NAMES
                    or type(data["output_index"]) is not int
                    or not 0 <= data["output_index"] < 64):
                raise PreparedOutputViolation("NATIVE_PREPARED_FUNCTION_INVALID")
            index = data["output_index"]
            self._bind(index, item_id, "function_call")
            if type(data["arguments"]) is not str or len(data["arguments"].encode("utf-8")) > 16384:
                raise PreparedOutputViolation("NATIVE_PREPARED_ARGUMENTS_TOO_LARGE")
            fingerprint = json.dumps(data, ensure_ascii=True, sort_keys=True, allow_nan=False)
            if (call_id in self._calls or any(json.loads(call)["output_index"] == index for call in self._calls.values())
                    or index in self._argument_partial
                    and self._argument_partial[index] != (call_id, item_id, data["arguments"])):
                raise PreparedOutputViolation("NATIVE_PREPARED_CALL_CONFLICT")
            self._calls[call_id] = fingerprint
            if len(self._calls) > 8:
                raise PreparedOutputViolation("NATIVE_PREPARED_CALL_LIMIT")
        elif kind in {"response.function_call_arguments.delta", "response.output_item.added",
                       "response.output_item.done", "response.content_part.added", "response.content_part.done"}:
            # These metadata events never become proposals. Terminal output and
            # the closed audio events must independently establish audio cleanup.
            if kind == "response.function_call_arguments.delta":
                self.cleanup_unsupported = True
                index = data["output_index"]
                if type(index) is not int or not 0 <= index < 64 or type(data["delta"]) is not str:
                    raise PreparedOutputViolation("NATIVE_PREPARED_FUNCTION_INVALID")
                item_id, call_id = _identity(data["item_id"]), _identity(data["call_id"])
                self._bind(index, item_id, "function_call")
                prior = self._argument_partial.get(index)
                if (prior is not None and prior[:2] != (call_id, item_id)
                        or any(json.loads(call)["output_index"] == index for call in self._calls.values())):
                    raise PreparedOutputViolation("NATIVE_PREPARED_CALL_CONFLICT")
                raw = (prior[2] if prior else "") + data["delta"]
                if len(raw.encode("utf-8")) > 16384:
                    raise PreparedOutputViolation("NATIVE_PREPARED_ARGUMENTS_TOO_LARGE")
                self._argument_partial[index] = (call_id, item_id, raw)
            elif kind.startswith("response.output_item."):
                item = data.get("item")
                if type(item) is not dict or item.get("type") not in {"message", "function_call"}:
                    self.cleanup_unsupported = True
                    raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_UNSUPPORTED")
                if item["type"] == "message" and "phase" in item and item["phase"] != "final_answer":
                    self.cleanup_unsupported = True
                    raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_UNSUPPORTED")
                item_id = _identity(item.get("id"))
                index = data["output_index"]
                self._bind(index, item_id, item["type"])
                if kind.endswith(".done"):
                    if index in self._item_done:
                        raise PreparedOutputViolation("NATIVE_PREPARED_ITEM_DONE_CONFLICT")
                    self._item_done[index] = item
                if len(self._metadata_items) >= 64 and item_id not in self._metadata_items:
                    self.cleanup_unsupported = True
                    raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_OVERFLOW")
                if item_id in self._metadata_items and self._metadata_items[item_id] != item["type"]:
                    self.cleanup_unsupported = True
                    raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_IDENTITY_CONFLICT")
                self._metadata_items[item_id] = item["type"]
                if item["type"] == "function_call":
                    self.cleanup_unsupported = True
            else:
                item_id, index, content = _identity(data["item_id"]), data["output_index"], data["content_index"]
                self._bind(index, item_id, "message")
                part = data["part"]
                if (type(content) is not int or not 0 <= content < 64 or type(part) is not dict
                        or set(part) != {"type", "transcript"} or part["type"] != "audio"):
                    self.cleanup_unsupported = True
                    raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_UNSUPPORTED")
                self._remember_audio_target((item_id, content))
                _transcript(part["transcript"])
                if kind.endswith(".done"):
                    if (item_id, content) in self._content_done:
                        raise PreparedOutputViolation("NATIVE_PREPARED_ITEM_DONE_CONFLICT")
                    self._content_done[item_id, content] = part["transcript"]
        else:
            self.cleanup_unsupported = True
            raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_UNSUPPORTED")
        if not self.discarded:
            size = len(json.dumps(data, ensure_ascii=True, allow_nan=False).encode("ascii"))
            if (self.byte_count + size > MAX_PREPARED_OUTPUT_BYTES
                    or self.event_count > MAX_PREPARED_OUTPUT_EVENTS):
                raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_OVERFLOW")
            self.byte_count += size
            if kind not in {"response.function_call_arguments.delta", "response.output_item.added",
                            "response.output_item.done", "response.content_part.added", "response.content_part.done"}:
                self.events.append(event)

    def _bind(self, index, item_id, kind):
        if type(index) is not int or not 0 <= index < 64:
            raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_INVALID")
        identity = (item_id, kind)
        if (index in self._item_indices and self._item_indices[index] != identity
                or any(other != index and value[0] == item_id for other, value in self._item_indices.items())):
            self.cleanup_unsupported = True
            raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_IDENTITY_CONFLICT")
        self._item_indices[index] = identity

    def _remember_audio_target(self, target):
        if len(self.audio_targets) >= 64 and target not in self.audio_targets:
            self.cleanup_unsupported = True
            raise PreparedOutputViolation("NATIVE_PREPARED_CLEANUP_IDENTITY_OVERFLOW")
        self.audio_targets.add(target)

    def _observe_cleanup_identity(self, kind, data):
        # Discarded content can never return to replay. Continue observing only
        # bounded identities needed for conservative zero-played cleanup.
        if kind.startswith("response.function_call_arguments."):
            self.cleanup_unsupported = True
        elif kind.startswith("response.output_audio") or kind.startswith("response.content_part."):
            item_id, content = _identity(data["item_id"]), data["content_index"]
            if type(content) is not int or not 0 <= content < 64:
                self.cleanup_unsupported = True
                raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_INVALID")
            self._remember_audio_target((item_id, content))
        elif kind.startswith("response.output_item."):
            item = data["item"]
            if type(item) is not dict or item.get("type") != "message":
                self.cleanup_unsupported = True
                return
            item_id = _identity(item.get("id"))
            if len(self._metadata_items) >= 64 and item_id not in self._metadata_items:
                self.cleanup_unsupported = True
                raise PreparedOutputViolation("NATIVE_PREPARED_CLEANUP_IDENTITY_OVERFLOW")
            self._metadata_items[item_id] = "message"
        else:
            self.cleanup_unsupported = True

    def _terminal_output(self, output: list) -> None:
        if len(output) > 64:
            self.cleanup_unsupported = True
            raise PreparedOutputViolation("NATIVE_PREPARED_TERMINAL_UNREPRESENTED")
        manifest, audio, calls = {}, {}, {}
        for output_index, item in enumerate(output):
            if type(item) is dict and item.get("type") == "function_call":
                self.cleanup_unsupported = True
                manifest[output_index] = (_identity(item.get("id")), "function_call")
                calls[output_index] = item
                continue
            if (type(item) is not dict or item.get("type") != "message"
                    or item.get("role") != "assistant"
                    or item.get("status") not in {"completed", "incomplete", "in_progress"}
                    or (self.terminal_status == "completed" and item.get("status") != "completed")
                    or not {"id", "type", "role", "status", "content"}.issubset(item)
                    or set(item) - {"id", "object", "type", "role", "status", "content", "phase"}
                    or "phase" in item and item["phase"] != "final_answer"
                    or type(item["content"]) is not list or len(item["content"]) > 64):
                self.cleanup_unsupported = True
                raise PreparedOutputViolation("NATIVE_PREPARED_TERMINAL_UNREPRESENTED")
            item_id = _identity(item["id"])
            manifest[output_index] = (item_id, "message")
            for index, content in enumerate(item["content"]):
                if (type(content) is not dict or content.get("type") not in ("audio", "output_audio")
                        or set(content) != {"type", "transcript"}
                        or type(content["transcript"]) is not str):
                    self.cleanup_unsupported = True
                    raise PreparedOutputViolation("NATIVE_PREPARED_TERMINAL_UNREPRESENTED")
                else:
                    self._remember_audio_target((item_id, index))
                    audio[output_index] = (item_id, index, content["transcript"])
        represented_ids = {target[0] for target in self.audio_targets} | {
            json.loads(call)["item_id"] for call in self._calls.values()}
        if set(self._metadata_items) - represented_ids:
            self.cleanup_unsupported = True
            raise PreparedOutputViolation("NATIVE_PREPARED_TERMINAL_UNREPRESENTED")
        if len(self.audio_targets) > 1 or (self.audio_targets and self._calls):
            raise PreparedOutputViolation("NATIVE_PREPARED_OUTPUT_COMPOSITION_UNSUPPORTED")
        if self.terminal_status != "completed" or self.discarded:
            return  # Cancellation retains known cleanup targets, not a completed manifest.
        observed_calls = {json.loads(call)["output_index"]: json.loads(call) for call in self._calls.values()}
        if (not manifest or manifest != self._item_indices
                or len({item_id for item_id, _ in manifest.values()}) != len(manifest)
                or set(audio) != set(self._audio_indices) or set(calls) != set(observed_calls)):
            raise PreparedOutputViolation("NATIVE_PREPARED_TERMINAL_UNREPRESENTED")
        for index, item in enumerate(output):
            if (item.get("status") != "completed"
                    or index in self._item_done and self._item_done[index] != item):
                raise PreparedOutputViolation("NATIVE_PREPARED_TERMINAL_UNREPRESENTED")
        for index, (item_id, content, transcript) in audio.items():
            _transcript(transcript)
            if (self._audio_indices[index] != (item_id, content)
                    or not self._audio_bytes.get(index) or index not in self._audio_done
                    or index not in self._transcript_final or self._transcript_final[index] != transcript
                    or (item_id, content) in self._content_done and self._content_done[item_id, content] != transcript):
                raise PreparedOutputViolation("NATIVE_PREPARED_TERMINAL_UNREPRESENTED")
        for index, item in calls.items():
            call = observed_calls[index]
            if (set(item) - {"id", "object", "type", "status", "name", "call_id", "arguments"}
                    or item.get("call_id") != call["call_id"] or item.get("name") != call["name"]
                    or item.get("arguments") != call["arguments"]):
                raise PreparedOutputViolation("NATIVE_PREPARED_TERMINAL_UNREPRESENTED")

    def acknowledge_truncate(self, data: dict) -> bool:
        if (type(data["item_id"]) is not str or type(data["content_index"]) is not int
                or type(data["audio_end_ms"]) is not int or data["audio_end_ms"] != 0):
            return False
        target = (data["item_id"], data["content_index"])
        if target == self.pending_truncate:
            # Receipt arrival is retained, not proof that our send succeeded.
            self._early_truncate_ack = True
            return False
        if target not in self.truncate_sent:
            return False
        self.truncate_acknowledged.add(target)
        return True

    def begin_truncate(self, target: tuple[str, int]) -> None:
        if (self.pending_truncate is not None or target not in self.audio_targets
                or target in self.truncate_sent or not self.discarded or not self.terminal
                or self.cleanup_unsupported):
            raise PreparedOutputViolation("NATIVE_PREPARED_TRUNCATE_INTENTION_INVALID")
        self.pending_truncate = target
        self._early_truncate_ack = False

    def confirm_truncate(self, target: tuple[str, int]) -> None:
        if self.pending_truncate != target or self.cleanup_unsupported:
            raise PreparedOutputViolation("NATIVE_PREPARED_TRUNCATE_CONFIRMATION_INVALID")
        self.truncate_sent.add(target)
        if self._early_truncate_ack:
            self.truncate_acknowledged.add(target)
        self.abandon_truncate(target)

    def abandon_truncate(self, target: tuple[str, int]) -> None:
        if self.pending_truncate == target:
            self.pending_truncate = None
            self._early_truncate_ack = False

    @property
    def cleanup_complete(self) -> bool:
        return (self.terminal and not self.cleanup_unsupported
                and self.pending_truncate is None
                and self.audio_targets <= self.truncate_sent
                and self.audio_targets <= self.truncate_acknowledged)
