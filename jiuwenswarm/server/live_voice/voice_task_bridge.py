# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Committed natural-language Task intent resolution without Task authority.

The bounded resolver in this module is the first Alpha implementation of the
Voice--Task resolver Port.  It intentionally accepts only documented, exact
English and Chinese command forms.  It is not a general NLU system and never
guesses a task identifier, pronoun, instruction span, or confirmation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    InputCommitState,
    ScopeRef,
    TurnCommit,
    canonical_json_bytes,
)

from .task_core import TaskCommand, TaskSpec


class VoiceTaskBridgeViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class TaskIntentDisposition(StrEnum):
    DISPATCHED = "dispatched"
    CLARIFICATION = "clarification"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TaskIntentSourceSpan:
    """One exact Python-string span into the authoritative TurnCommit text."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ResolvedTaskIntent:
    """Content-bound output from a resolver that still owns no Task authority."""

    disposition: TaskIntentDisposition
    reason: str
    provider: str
    implementation_class: str
    resolution_id: str
    commit_sha256: str
    operation: str | None = None
    task_id: str | None = None
    name: str | None = None
    instruction: str | None = None
    source_span: TaskIntentSourceSpan | None = None
    target_span: TaskIntentSourceSpan | None = None
    requires_confirmation: bool = False
    confirmation_token: str | None = None


@runtime_checkable
class CommittedTaskIntentResolverPort(Protocol):
    """Provider-neutral resolver seam; implementations receive only a commit."""

    def resolve(self, commit: TurnCommit) -> ResolvedTaskIntent: ...


_TASK_ID = r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}"
_CONFIRMATION_TOKEN = r"[0-9a-f]{32}"


def _resolution_identity(
    *,
    provider: str,
    implementation_class: str,
    commit_sha256: str,
    operation: str | None,
    task_id: str | None,
    name: str | None,
    instruction: str | None,
    source_span: TaskIntentSourceSpan | None,
    target_span: TaskIntentSourceSpan | None,
    requires_confirmation: bool,
    confirmation_token: str | None,
    reason: str,
) -> dict[str, object]:
    return {
        "provider": provider,
        "implementation_class": implementation_class,
        "commit_sha256": commit_sha256,
        "operation": operation,
        "task_id": task_id,
        "name": name,
        "instruction": instruction,
        "source_span": (
            None
            if source_span is None
            else {"start": source_span.start, "end": source_span.end}
        ),
        "target_span": (
            None
            if target_span is None
            else {"start": target_span.start, "end": target_span.end}
        ),
        "requires_confirmation": requires_confirmation,
        "confirmation_token": confirmation_token,
        "reason": reason,
    }


class BoundedAlphaTaskIntentResolver:
    """High-precision closed-form resolver for the Integrated Web Alpha.

    Accepted forms (surrounding whitespace is ignored):

    * ``create task: <instruction>`` / ``创建任务：<instruction>``
    * ``create task named <name>: <instruction>`` /
      ``创建任务“<name>”：<instruction>``
    * ``task status <exact-task-id>`` / ``任务状态 <exact-task-id>``
    * ``cancel task <exact-task-id>`` / ``取消任务 <exact-task-id>``
    * ``confirm task request <32-hex-token>`` /
      ``确认任务请求 <32-hex-token>``

    Create and cancel resolve to clarification until a later, independently
    committed confirmation turn binds the returned resolution token.
    """

    provider = "local.closed_schema"
    implementation_class = "bounded_deterministic_alpha_v1"
    max_commit_chars = 8_192
    max_instruction_chars = 4_096

    _CREATE = (
        re.compile(r"^\s*create\s+task\s*:\s*(?P<instruction>.+?)\s*$", re.I | re.S),
        re.compile(
            r"^\s*create\s+task\s+named\s+(?P<name>[A-Za-z0-9][A-Za-z0-9 ._-]{0,63})\s*:\s*(?P<instruction>.+?)\s*$",
            re.I | re.S,
        ),
        re.compile(r"^\s*创建任务\s*[：:]\s*(?P<instruction>.+?)\s*$", re.S),
        re.compile(
            r"^\s*创建任务\s*[“\"](?P<name>[^”\"\r\n]{1,64})[”\"]\s*[：:]\s*(?P<instruction>.+?)\s*$",
            re.S,
        ),
    )
    _STATUS = (
        re.compile(rf"^\s*task\s+status\s+(?P<task_id>{_TASK_ID})\s*$", re.I),
        re.compile(rf"^\s*status\s+task\s+(?P<task_id>{_TASK_ID})\s*$", re.I),
        re.compile(rf"^\s*任务状态\s+(?P<task_id>{_TASK_ID})\s*$"),
        re.compile(rf"^\s*查询任务\s+(?P<task_id>{_TASK_ID})\s*$"),
    )
    _CANCEL = (
        re.compile(rf"^\s*cancel\s+task\s+(?P<task_id>{_TASK_ID})\s*$", re.I),
        re.compile(rf"^\s*取消任务\s+(?P<task_id>{_TASK_ID})\s*$"),
    )
    _CONFIRM = (
        re.compile(
            rf"^\s*confirm\s+task\s+request\s+(?P<token>{_CONFIRMATION_TOKEN})\s*$",
            re.I,
        ),
        re.compile(rf"^\s*确认任务请求\s+(?P<token>{_CONFIRMATION_TOKEN})\s*$"),
    )
    _TASK_WORD = re.compile(
        r"(?:\btask\b|\bcreate\b|\bcancel\b|\bstatus\b|任务|创建|取消|状态|确认)",
        re.I,
    )
    _KNOWN_UNSUPPORTED_FULL_P3 = re.compile(
        rf"^\s*(?:(?:pause|resume)\s+task\s+{_TASK_ID}|(?:暂停|恢复)任务\s+{_TASK_ID})\s*$",
        re.I,
    )

    def resolve(self, commit: TurnCommit) -> ResolvedTaskIntent:
        if not isinstance(commit, TurnCommit):
            raise VoiceTaskBridgeViolation(
                "COMMITTED_ORIGIN_REQUIRED",
                "task intent resolution requires an authoritative TurnCommit",
                ErrorCode.PERMISSION_DENIED,
            )
        text = commit.text
        if len(text) > self.max_commit_chars:
            return self._result(
                commit,
                TaskIntentDisposition.REJECTED,
                "TASK_INTENT_TOO_LARGE",
            )

        for pattern in self._CONFIRM:
            match = pattern.fullmatch(text)
            if match is not None:
                span = TaskIntentSourceSpan(*match.span("token"))
                return self._result(
                    commit,
                    TaskIntentDisposition.CLARIFICATION,
                    "TASK_CONFIRMATION_CANDIDATE",
                    source_span=span,
                    confirmation_token=match.group("token"),
                )

        for pattern in self._STATUS:
            match = pattern.fullmatch(text)
            if match is not None:
                span = TaskIntentSourceSpan(*match.span("task_id"))
                return self._result(
                    commit,
                    TaskIntentDisposition.DISPATCHED,
                    "TASK_INTENT_RESOLVED",
                    operation="task.status",
                    task_id=match.group("task_id"),
                    source_span=span,
                    target_span=span,
                )

        for pattern in self._CANCEL:
            match = pattern.fullmatch(text)
            if match is not None:
                span = TaskIntentSourceSpan(*match.span("task_id"))
                return self._result(
                    commit,
                    TaskIntentDisposition.CLARIFICATION,
                    "TASK_CONFIRMATION_REQUIRED",
                    operation="task.cancel",
                    task_id=match.group("task_id"),
                    source_span=span,
                    target_span=span,
                    requires_confirmation=True,
                )

        for pattern in self._CREATE:
            match = pattern.fullmatch(text)
            if match is not None:
                instruction = match.group("instruction")
                if len(instruction) > self.max_instruction_chars:
                    return self._result(
                        commit,
                        TaskIntentDisposition.REJECTED,
                        "TASK_INSTRUCTION_TOO_LARGE",
                    )
                span = TaskIntentSourceSpan(*match.span("instruction"))
                name = match.groupdict().get("name") or "Voice task"
                return self._result(
                    commit,
                    TaskIntentDisposition.CLARIFICATION,
                    "TASK_CONFIRMATION_REQUIRED",
                    operation="task.create",
                    name=name.strip(),
                    instruction=instruction,
                    source_span=span,
                    requires_confirmation=True,
                )

        if self._KNOWN_UNSUPPORTED_FULL_P3.fullmatch(text) is not None:
            return self._result(
                commit,
                TaskIntentDisposition.REJECTED,
                "UNSUPPORTED_TASK_INTENT",
            )

        return self._result(
            commit,
            (
                TaskIntentDisposition.CLARIFICATION
                if self._TASK_WORD.search(text)
                else TaskIntentDisposition.REJECTED
            ),
            (
                "TASK_INTENT_EXACT_FORM_REQUIRED"
                if self._TASK_WORD.search(text)
                else "UNSUPPORTED_TASK_INTENT"
            ),
        )

    def _result(
        self,
        commit: TurnCommit,
        disposition: TaskIntentDisposition,
        reason: str,
        *,
        operation: str | None = None,
        task_id: str | None = None,
        name: str | None = None,
        instruction: str | None = None,
        source_span: TaskIntentSourceSpan | None = None,
        target_span: TaskIntentSourceSpan | None = None,
        requires_confirmation: bool = False,
        confirmation_token: str | None = None,
    ) -> ResolvedTaskIntent:
        commit_sha256 = hashlib.sha256(commit.canonical_bytes()).hexdigest()
        identity = _resolution_identity(
            provider=self.provider,
            implementation_class=self.implementation_class,
            commit_sha256=commit_sha256,
            operation=operation,
            task_id=task_id,
            name=name,
            instruction=instruction,
            source_span=source_span,
            target_span=target_span,
            requires_confirmation=requires_confirmation,
            confirmation_token=confirmation_token,
            reason=reason,
        )
        resolution_id = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
        return ResolvedTaskIntent(
            disposition=disposition,
            reason=reason,
            provider=self.provider,
            implementation_class=self.implementation_class,
            resolution_id=resolution_id,
            commit_sha256=commit_sha256,
            operation=operation,
            task_id=task_id,
            name=name,
            instruction=instruction,
            source_span=source_span,
            target_span=target_span,
            requires_confirmation=requires_confirmation,
            confirmation_token=confirmation_token,
        )


@dataclass(frozen=True, slots=True)
class TaskIntent:
    state: InputCommitState
    operation: str
    request_id: str
    command_id: str
    scope: ScopeRef
    origin_commit_id: str | None
    task_id: str | None = None
    name: str | None = None
    instruction: str | None = None
    ambiguous: bool = False
    destructive: bool = False
    confirmed: bool = False


class VoiceTaskBridge:
    def __init__(self, resolver: CommittedTaskIntentResolverPort | None = None) -> None:
        candidate = resolver or BoundedAlphaTaskIntentResolver()
        if not isinstance(candidate, CommittedTaskIntentResolverPort):
            raise VoiceTaskBridgeViolation(
                "TASK_INTENT_RESOLVER_REQUIRED",
                "Voice--Task Bridge requires the committed-intent resolver Port",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        self._resolver = candidate

    def resolve(
        self, commit: TurnCommit, authorized_scope: ScopeRef
    ) -> ResolvedTaskIntent:
        """Resolve and independently verify content binding before dispatch.

        The Bridge rechecks every resolver-supplied digest and source span
        against the authoritative commit.  A model-backed resolver may be
        injected later, but it cannot smuggle caller-declared ambiguity,
        confirmation, target, or instruction through this boundary.
        """

        if not isinstance(commit, TurnCommit) or commit.scope != authorized_scope:
            raise VoiceTaskBridgeViolation(
                "TASK_SCOPE_MISMATCH",
                "committed task intent must match the exact authorized scope",
                ErrorCode.PERMISSION_DENIED,
            )
        result = self._resolver.resolve(commit)
        if not isinstance(result, ResolvedTaskIntent):
            raise VoiceTaskBridgeViolation(
                "INVALID_TASK_INTENT_RESOLUTION",
                "task intent resolver returned an unsupported result",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if (
            not isinstance(result.disposition, TaskIntentDisposition)
            or type(result.provider) is not str
            or not 0 < len(result.provider) <= 128
            or re.fullmatch(r"[A-Za-z0-9._-]+", result.provider) is None
            or type(result.implementation_class) is not str
            or not 0 < len(result.implementation_class) <= 128
            or re.fullmatch(r"[A-Za-z0-9._-]+", result.implementation_class) is None
            or type(result.reason) is not str
            or not 0 < len(result.reason) <= 128
            or re.fullmatch(r"[A-Z0-9_]+", result.reason) is None
            or type(result.requires_confirmation) is not bool
            or (
                result.source_span is not None
                and not isinstance(result.source_span, TaskIntentSourceSpan)
            )
            or (
                result.target_span is not None
                and not isinstance(result.target_span, TaskIntentSourceSpan)
            )
            or any(
                value is not None and type(value) is not str
                for value in (
                    result.operation,
                    result.task_id,
                    result.name,
                    result.instruction,
                    result.confirmation_token,
                )
            )
            or (
                result.task_id is not None
                and re.fullmatch(_TASK_ID, result.task_id) is None
            )
            or (result.name is not None and not 0 < len(result.name) <= 64)
            or (
                result.instruction is not None
                and not 0 < len(result.instruction) <= 4_096
            )
            or (
                result.confirmation_token is not None
                and re.fullmatch(_CONFIRMATION_TOKEN, result.confirmation_token, re.I)
                is None
            )
        ):
            raise VoiceTaskBridgeViolation(
                "INVALID_TASK_INTENT_RESOLUTION",
                "task intent resolver returned invalid bounded fields",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        digest = hashlib.sha256(commit.canonical_bytes()).hexdigest()
        if result.commit_sha256 != digest:
            raise VoiceTaskBridgeViolation(
                "TASK_INTENT_COMMIT_MISMATCH",
                "task intent resolution changed its authoritative commit",
                ErrorCode.PERMISSION_DENIED,
            )
        expected_resolution_id = hashlib.sha256(
            canonical_json_bytes(
                _resolution_identity(
                    provider=result.provider,
                    implementation_class=result.implementation_class,
                    commit_sha256=result.commit_sha256,
                    operation=result.operation,
                    task_id=result.task_id,
                    name=result.name,
                    instruction=result.instruction,
                    source_span=result.source_span,
                    target_span=result.target_span,
                    requires_confirmation=result.requires_confirmation,
                    confirmation_token=result.confirmation_token,
                    reason=result.reason,
                )
            )
        ).hexdigest()
        if result.resolution_id != expected_resolution_id:
            raise VoiceTaskBridgeViolation(
                "TASK_INTENT_RESOLUTION_ID_MISMATCH",
                "task intent resolution changed its content-bound identity",
                ErrorCode.PERMISSION_DENIED,
            )
        source_value = result.instruction or result.confirmation_token or result.task_id
        self._verify_span(commit.text, result.source_span, source_value)
        self._verify_span(commit.text, result.target_span, result.task_id)
        if result.operation == "task.create":
            if not result.instruction or result.task_id is not None:
                raise VoiceTaskBridgeViolation(
                    "INVALID_TASK_CREATE_INTENT",
                    "resolved create intent requires one exact instruction span",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
        elif result.operation in {"task.status", "task.cancel"}:
            if not result.task_id or result.instruction is not None:
                raise VoiceTaskBridgeViolation(
                    "EXACT_TASK_REQUIRED",
                    "resolved targeted intent requires one exact task id span",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
        elif result.operation is not None:
            raise VoiceTaskBridgeViolation(
                "UNSUPPORTED_TASK_INTENT",
                "resolver selected an operation outside the Alpha schema",
                ErrorCode.UNSUPPORTED,
            )
        if result.requires_confirmation != (
            result.operation in {"task.create", "task.cancel"}
        ):
            raise VoiceTaskBridgeViolation(
                "INVALID_TASK_CONFIRMATION_DECISION",
                "only resolved create/cancel intents require confirmation",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if result.confirmation_token is not None and result.operation is not None:
            raise VoiceTaskBridgeViolation(
                "INVALID_TASK_CONFIRMATION_DECISION",
                "a confirmation turn cannot introduce a second operation",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        return result

    @staticmethod
    def _verify_span(
        text: str, span: TaskIntentSourceSpan | None, expected: str | None
    ) -> None:
        if span is None:
            if expected is not None:
                raise VoiceTaskBridgeViolation(
                    "TASK_INTENT_SOURCE_SPAN_REQUIRED",
                    "resolved content must retain its exact commit source span",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            return
        if (
            type(span.start) is not int
            or type(span.end) is not int
            or not 0 <= span.start < span.end <= len(text)
            or expected is None
            or text[span.start : span.end] != expected
        ):
            raise VoiceTaskBridgeViolation(
                "TASK_INTENT_SOURCE_SPAN_MISMATCH",
                "resolved content does not match its exact commit source span",
                ErrorCode.PERMISSION_DENIED,
            )

    def map(self, intent: TaskIntent, authorized_scope: ScopeRef) -> TaskCommand:
        if intent.state is not InputCommitState.COMMITTED:
            raise VoiceTaskBridgeViolation(
                "INPUT_NOT_COMMITTED",
                "partial or uncommitted speech cannot create Task commands",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.scope != authorized_scope:
            raise VoiceTaskBridgeViolation(
                "TASK_SCOPE_MISMATCH",
                "voice intent must match the exact authorized scope",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.ambiguous:
            raise VoiceTaskBridgeViolation(
                "TASK_INTENT_AMBIGUOUS",
                "ambiguous task intent requires clarification",
                ErrorCode.INVALID_ARGUMENT,
            )
        if intent.destructive and not intent.confirmed:
            raise VoiceTaskBridgeViolation(
                "TASK_CONFIRMATION_REQUIRED",
                "destructive task intent requires explicit confirmation",
                ErrorCode.PERMISSION_DENIED,
            )
        if not intent.origin_commit_id:
            raise VoiceTaskBridgeViolation(
                "COMMITTED_ORIGIN_REQUIRED",
                "Task commands require a committed turn origin",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.operation == "task.create":
            if intent.task_id is not None or not intent.name or not intent.instruction:
                raise VoiceTaskBridgeViolation(
                    "INVALID_TASK_CREATE_INTENT",
                    "create intent requires name and instruction but no task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
            spec = TaskSpec(intent.name, intent.instruction)
            target_task_id = None
        elif intent.operation == "task.cancel":
            if intent.task_id is None:
                raise VoiceTaskBridgeViolation(
                    "EXACT_TASK_REQUIRED",
                    "cancel intent requires an exact task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
            spec = None
            target_task_id = intent.task_id
        else:
            raise VoiceTaskBridgeViolation(
                "UNSUPPORTED_TASK_INTENT",
                f"unsupported task intent {intent.operation!r}",
                ErrorCode.UNSUPPORTED,
            )
        return TaskCommand(
            request_id=intent.request_id,
            command_id=intent.command_id,
            operation=intent.operation,
            scope=intent.scope,
            target_task_id=target_task_id,
            spec=spec,
            origin_commit_id=intent.origin_commit_id,
        )


__all__ = [
    "BoundedAlphaTaskIntentResolver",
    "CommittedTaskIntentResolverPort",
    "ResolvedTaskIntent",
    "TaskIntent",
    "TaskIntentDisposition",
    "TaskIntentSourceSpan",
    "VoiceTaskBridge",
    "VoiceTaskBridgeViolation",
]
