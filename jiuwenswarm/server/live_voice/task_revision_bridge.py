# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Committed-voice bridge and confirmation preparation for S8.5 revisions.

The bridge extracts only an allowlisted revision payload from one authoritative
``TurnCommit``.  Task identity and revision identity always come from a Store
snapshot; neither speech text nor a model may invent them.  The policy layer
then creates one canonical ACG v2 command whose fingerprint must be confirmed
before the revision Store can admit it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    CommandEnvelope,
    ContractViolation,
    ErrorCode,
    OriginRef,
    ScopeRef,
    TurnCommit,
    TurnCommitLedger,
    canonical_json_bytes,
)

from .formal_task_models import FormalTaskViolation

from .task_revision import (
    S8_5_TASK_REVISION_EXTENSION,
    S8_5_TASK_REVISION_PROFILE,
    TaskConstraintPatch,
    TaskRevisionCommand,
    TaskRevisionGrant,
    TaskRevisionOperation,
    TaskRevisionTargetSnapshot,
    TaskRevisionViolation,
)


class TaskRevisionIntentDisposition(StrEnum):
    CONFIRMATION_REQUIRED = "confirmation_required"
    CLARIFICATION_REQUIRED = "clarification_required"
    REJECTED = "rejected"


class TaskRevisionBridgeViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


def _violation(
    reason: str,
    message: str,
    code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
) -> TaskRevisionBridgeViolation:
    return TaskRevisionBridgeViolation(reason, message, code)


@runtime_checkable
class TaskRevisionTargetReader(Protocol):
    """Trusted read-only Port implemented by the Task revision Store."""

    def read_target(
        self, task_id: str, scope: ScopeRef
    ) -> TaskRevisionTargetSnapshot: ...


@dataclass(frozen=True, slots=True)
class TaskRevisionSourceSpan:
    start: int
    end: int

    def __post_init__(self) -> None:
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or self.start < 0
            or self.end <= self.start
        ):
            raise _violation(
                "INVALID_TASK_REVISION_SOURCE_SPAN",
                "revision source span must be a non-empty bounded interval",
            )


@dataclass(frozen=True, slots=True)
class TaskRevisionDraft:
    disposition: TaskRevisionIntentDisposition
    reason: str
    resolution_id: str
    commit_id: str
    turn_id: str
    commit_sha256: str
    target: TaskRevisionTargetSnapshot
    operation: TaskRevisionOperation | None = None
    facts: tuple[str, ...] = ()
    constraint_patch: TaskConstraintPatch | None = None
    source_span: TaskRevisionSourceSpan | None = None

    def __post_init__(self) -> None:
        resolved = (
            self.disposition is TaskRevisionIntentDisposition.CONFIRMATION_REQUIRED
        )
        payload_valid = (
            self.operation is TaskRevisionOperation.PROVIDE_INPUT
            and bool(self.facts)
            and self.constraint_patch is None
        ) or (
            self.operation is TaskRevisionOperation.UPDATE_CONSTRAINTS
            and not self.facts
            and type(self.constraint_patch) is TaskConstraintPatch
        )
        if (
            type(self.disposition) is not TaskRevisionIntentDisposition
            or type(self.reason) is not str
            or not self.reason.strip()
            or re.fullmatch(r"[0-9a-f]{64}", self.resolution_id) is None
            or type(self.commit_id) is not str
            or not self.commit_id.strip()
            or type(self.turn_id) is not str
            or not self.turn_id.strip()
            or re.fullmatch(r"[0-9a-f]{64}", self.commit_sha256) is None
            or type(self.target) is not TaskRevisionTargetSnapshot
            or type(self.facts) is not tuple
            or resolved
            != (payload_valid and type(self.source_span) is TaskRevisionSourceSpan)
            or (
                not resolved
                and (
                    self.operation is not None
                    or self.facts
                    or self.constraint_patch is not None
                    or self.source_span is not None
                )
            )
        ):
            raise _violation(
                "INVALID_TASK_REVISION_DRAFT",
                "revision draft does not preserve one exact committed intent",
                ErrorCode.PROTOCOL_VIOLATION,
            )


@dataclass(frozen=True, slots=True)
class PreparedTaskRevision:
    draft: TaskRevisionDraft
    envelope: CommandEnvelope
    command: TaskRevisionCommand
    command_fingerprint_sha256: str
    confirmation_prompt: str

    def __post_init__(self) -> None:
        if (
            type(self.draft) is not TaskRevisionDraft
            or type(self.envelope) is not CommandEnvelope
            or type(self.command) is not TaskRevisionCommand
            or self.command_fingerprint_sha256
            != hashlib.sha256(self.command.fingerprint()).hexdigest()
            or type(self.confirmation_prompt) is not str
            or not self.confirmation_prompt.strip()
        ):
            raise _violation(
                "INVALID_PREPARED_TASK_REVISION",
                "prepared revision facts do not bind one canonical command",
                ErrorCode.PROTOCOL_VIOLATION,
            )


class BoundedTaskRevisionVoiceBridge:
    """Resolve four exact bilingual forms; every other form fails closed."""

    max_commit_characters = 4_096
    max_fact_characters = 2_000

    _PROVIDE_INPUT = (
        re.compile(
            r"^\s*(?:provide|add)\s+task\s+input\s*:\s*(?P<fact>.+?)\s*$",
            re.I | re.S,
        ),
        re.compile(r"^\s*补充任务输入\s*[：:]\s*(?P<fact>.+?)\s*$", re.S),
    )
    _WRITE_SCOPE = (
        re.compile(
            r"^\s*limit\s+task\s+write\s+scope\s+to\s*:\s*(?P<paths>.+?)\s*$",
            re.I,
        ),
        re.compile(r"^\s*限制任务写入范围\s*[：:]\s*(?P<paths>.+?)\s*$"),
    )
    _REQUIRE_VERIFIER = (
        re.compile(r"^\s*require\s+task\s+regression\s+verification\s*$", re.I),
        re.compile(r"^\s*要求任务回归验证\s*$"),
    )
    _REVISION_TERMS = re.compile(
        r"(?:task\s+(?:input|write|revision|change)|任务(?:输入|写入|修订|修改)|回归验证)",
        re.I,
    )
    _FORBIDDEN = re.compile(
        r"(?:\bgit\s+(?:commit|push)\b|\b(?:pause|resume|reprioritize|steer)\b|"
        r"\b(?:install|upgrade)\s+(?:a\s+)?dependenc|\bchange\s+(?:the\s+)?(?:api|config)|"
        r"暂停|恢复|调整优先级|提交代码|推送|安装依赖|升级依赖|修改接口|修改配置)",
        re.I,
    )

    def __init__(
        self,
        *,
        enabled: bool = False,
        commits: TurnCommitLedger | None = None,
        targets: TaskRevisionTargetReader | None = None,
    ) -> None:
        if type(enabled) is not bool:
            raise _violation(
                "INVALID_TASK_REVISION_FEATURE_FLAG",
                "task revision feature flag must be boolean",
            )
        if commits is not None and type(commits) is not TurnCommitLedger:
            raise _violation(
                "INVALID_TASK_REVISION_COMMIT_AUTHORITY",
                "commit authority must be an exact TurnCommitLedger",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if targets is not None and not isinstance(targets, TaskRevisionTargetReader):
            raise _violation(
                "INVALID_TASK_REVISION_TARGET_AUTHORITY",
                "target authority must implement the read-only revision Port",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        self._enabled = enabled
        self._commits = commits
        self._targets = targets

    def resolve(
        self,
        commit: TurnCommit,
        *,
        authorized_scope: ScopeRef,
        task_id: str,
    ) -> TaskRevisionDraft:
        if not self._enabled:
            raise _violation(
                "TASK_REVISION_FEATURE_DISABLED",
                "S8.5 task revision is disabled",
                ErrorCode.UNSUPPORTED,
            )
        if type(commit) is not TurnCommit or commit.scope != authorized_scope:
            raise _violation(
                "TASK_REVISION_SCOPE_MISMATCH",
                "committed input must share the authorized scope",
                ErrorCode.PERMISSION_DENIED,
            )
        if type(task_id) is not str or not task_id.strip():
            raise _violation(
                "INVALID_TASK_REVISION_TARGET",
                "task route must provide one non-empty Store identity",
            )
        if self._commits is None:
            raise _violation(
                "COMMIT_AUTHORITY_REQUIRED",
                "task revision requires the authoritative turn commit ledger",
                ErrorCode.UNAVAILABLE,
            )
        if self._targets is None:
            raise _violation(
                "TASK_REVISION_TARGET_AUTHORITY_REQUIRED",
                "task revision requires the authoritative Store target reader",
                ErrorCode.UNAVAILABLE,
            )
        try:
            accepted_commit = self._commits.require_origin(
                OriginRef("committed_turn", commit.turn_id, commit.commit_id),
                authorized_scope,
            )
        except ContractViolation as error:
            raise _violation(error.reason, str(error), error.code) from error
        if accepted_commit.canonical_bytes() != commit.canonical_bytes():
            raise _violation(
                "TASK_REVISION_COMMIT_MISMATCH",
                "revision input does not equal its accepted committed content",
                ErrorCode.PERMISSION_DENIED,
            )
        try:
            target = self._targets.read_target(task_id, authorized_scope)
        except FormalTaskViolation as error:
            raise _violation(error.reason, str(error), error.code) from error
        if (
            type(target) is not TaskRevisionTargetSnapshot
            or target.task_id != task_id
            or target.scope != authorized_scope
        ):
            raise _violation(
                "TASK_REVISION_TARGET_AUTHORITY_MISMATCH",
                "Store target does not bind the requested task and scope",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if (
            target.task_state not in {"running", "blocked", "decision_required"}
            or target.attempt_number != 1
            or target.task_revision != 1
            or target.pending_command_id is not None
        ):
            raise _violation(
                "TASK_REVISION_TARGET_INELIGIBLE",
                "revision target must be the original live attempt with no pending command",
                ErrorCode.CONFLICT,
            )
        text = commit.text
        digest = hashlib.sha256(commit.canonical_bytes()).hexdigest()
        if len(text) > self.max_commit_characters:
            return self._draft(
                commit,
                target,
                digest,
                TaskRevisionIntentDisposition.REJECTED,
                "TASK_REVISION_INPUT_TOO_LARGE",
            )
        if self._FORBIDDEN.search(text):
            return self._draft(
                commit,
                target,
                digest,
                TaskRevisionIntentDisposition.REJECTED,
                "TASK_REVISION_OPERATION_FORBIDDEN",
            )
        for pattern in self._PROVIDE_INPUT:
            match = pattern.fullmatch(text)
            if match is not None:
                fact = match.group("fact").strip()
                if len(fact) > self.max_fact_characters:
                    return self._draft(
                        commit,
                        target,
                        digest,
                        TaskRevisionIntentDisposition.REJECTED,
                        "TASK_REVISION_INPUT_TOO_LARGE",
                    )
                return self._draft(
                    commit,
                    target,
                    digest,
                    TaskRevisionIntentDisposition.CONFIRMATION_REQUIRED,
                    "TASK_REVISION_CONFIRMATION_REQUIRED",
                    operation=TaskRevisionOperation.PROVIDE_INPUT,
                    facts=(fact,),
                    source_span=TaskRevisionSourceSpan(*match.span("fact")),
                )
        for pattern in self._WRITE_SCOPE:
            match = pattern.fullmatch(text)
            if match is not None:
                raw_paths = re.split(r"\s*[,，]\s*", match.group("paths").strip())
                try:
                    patch = TaskConstraintPatch(write_scope=tuple(raw_paths))
                except TaskRevisionViolation as error:
                    raise _violation(error.reason, str(error), error.code) from error
                return self._draft(
                    commit,
                    target,
                    digest,
                    TaskRevisionIntentDisposition.CONFIRMATION_REQUIRED,
                    "TASK_REVISION_CONFIRMATION_REQUIRED",
                    operation=TaskRevisionOperation.UPDATE_CONSTRAINTS,
                    constraint_patch=patch,
                    source_span=TaskRevisionSourceSpan(*match.span("paths")),
                )
        if any(pattern.fullmatch(text) for pattern in self._REQUIRE_VERIFIER):
            return self._draft(
                commit,
                target,
                digest,
                TaskRevisionIntentDisposition.CONFIRMATION_REQUIRED,
                "TASK_REVISION_CONFIRMATION_REQUIRED",
                operation=TaskRevisionOperation.UPDATE_CONSTRAINTS,
                constraint_patch=TaskConstraintPatch(regression_verifier_required=True),
                source_span=TaskRevisionSourceSpan(0, len(text)),
            )
        return self._draft(
            commit,
            target,
            digest,
            (
                TaskRevisionIntentDisposition.CLARIFICATION_REQUIRED
                if self._REVISION_TERMS.search(text)
                else TaskRevisionIntentDisposition.REJECTED
            ),
            (
                "TASK_REVISION_EXACT_FORM_REQUIRED"
                if self._REVISION_TERMS.search(text)
                else "UNSUPPORTED_TASK_REVISION_INTENT"
            ),
        )

    @staticmethod
    def _draft(
        commit: TurnCommit,
        target: TaskRevisionTargetSnapshot,
        digest: str,
        disposition: TaskRevisionIntentDisposition,
        reason: str,
        *,
        operation: TaskRevisionOperation | None = None,
        facts: tuple[str, ...] = (),
        constraint_patch: TaskConstraintPatch | None = None,
        source_span: TaskRevisionSourceSpan | None = None,
    ) -> TaskRevisionDraft:
        identity = {
            "commit_id": commit.commit_id,
            "commit_sha256": digest,
            "task_id": target.task_id,
            "task_revision": target.task_revision,
            "attempt_id": target.attempt_id,
            "operation": None if operation is None else operation.value,
            "facts": list(facts),
            "constraints": (
                None if constraint_patch is None else constraint_patch.to_dict()
            ),
            "source_span": (
                None
                if source_span is None
                else {"start": source_span.start, "end": source_span.end}
            ),
            "reason": reason,
        }
        return TaskRevisionDraft(
            disposition=disposition,
            reason=reason,
            resolution_id=hashlib.sha256(canonical_json_bytes(identity)).hexdigest(),
            commit_id=commit.commit_id,
            turn_id=commit.turn_id,
            commit_sha256=digest,
            target=target,
            operation=operation,
            facts=facts,
            constraint_patch=constraint_patch,
            source_span=source_span,
        )


class TaskRevisionPolicyAdapter:
    """Prepare and verify one explicit-confirmation revision command."""

    def __init__(
        self,
        *,
        commits: TurnCommitLedger,
        targets: TaskRevisionTargetReader,
    ) -> None:
        if type(commits) is not TurnCommitLedger:
            raise _violation(
                "INVALID_TASK_REVISION_COMMIT_AUTHORITY",
                "policy commit authority must be an exact TurnCommitLedger",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if not isinstance(targets, TaskRevisionTargetReader):
            raise _violation(
                "INVALID_TASK_REVISION_TARGET_AUTHORITY",
                "policy target authority must implement the revision read Port",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        self._commits = commits
        self._targets = targets

    def _revalidate_draft(self, draft: TaskRevisionDraft) -> None:
        try:
            commit = self._commits.require_origin(
                OriginRef("committed_turn", draft.turn_id, draft.commit_id),
                draft.target.scope,
            )
        except ContractViolation as error:
            raise _violation(error.reason, str(error), error.code) from error
        if hashlib.sha256(commit.canonical_bytes()).hexdigest() != draft.commit_sha256:
            raise _violation(
                "TASK_REVISION_COMMIT_MISMATCH",
                "draft no longer binds its accepted committed content",
                ErrorCode.PERMISSION_DENIED,
            )
        canonical = BoundedTaskRevisionVoiceBridge(
            enabled=True,
            commits=self._commits,
            targets=self._targets,
        ).resolve(
            commit,
            authorized_scope=draft.target.scope,
            task_id=draft.target.task_id,
        )
        if canonical != draft:
            raise _violation(
                "TASK_REVISION_DRAFT_AUTHORITY_MISMATCH",
                "draft changed or its Store target is stale",
                ErrorCode.STALE,
            )

    def prepare(
        self,
        draft: TaskRevisionDraft,
        *,
        request_id: str,
        command_id: str,
        issued_at: str,
        correlation_id: str,
    ) -> PreparedTaskRevision:
        if (
            type(draft) is not TaskRevisionDraft
            or draft.disposition
            is not TaskRevisionIntentDisposition.CONFIRMATION_REQUIRED
            or draft.operation is None
            or draft.source_span is None
        ):
            raise _violation(
                "TASK_REVISION_NOT_PREPARABLE",
                "only an exact committed revision intent can request confirmation",
                ErrorCode.CONFLICT,
            )
        self._revalidate_draft(draft)
        payload: dict[str, object] = {
            "expected_task_revision": draft.target.task_revision,
            "expected_attempt_id": draft.target.attempt_id,
        }
        if draft.operation is TaskRevisionOperation.PROVIDE_INPUT:
            payload["facts"] = list(draft.facts)
        else:
            assert draft.constraint_patch is not None
            payload["constraints"] = draft.constraint_patch.to_dict()
        envelope = CommandEnvelope.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "request_id": request_id,
                "command_id": command_id,
                "command_type": draft.operation.value,
                "issued_at": issued_at,
                "scope": draft.target.scope.to_dict(),
                "correlation_id": correlation_id,
                "causation_id": draft.commit_id,
                "origin": {
                    "kind": "committed_turn",
                    "turn_id": draft.turn_id,
                    "commit_id": draft.commit_id,
                },
                "target_ref": {"kind": "task", "id": draft.target.task_id},
                "context_refs": [],
                "required_capabilities": [draft.operation.value],
                "payload": payload,
                "extensions": {
                    S8_5_TASK_REVISION_EXTENSION: {
                        "profile": S8_5_TASK_REVISION_PROFILE
                    }
                },
            }
        )
        command = TaskRevisionCommand.from_envelope(envelope)
        if (
            command.operation is not draft.operation
            or command.task_id != draft.target.task_id
            or command.expected_task_revision != draft.target.task_revision
            or command.expected_attempt_id != draft.target.attempt_id
            or command.origin_commit_id != draft.commit_id
            or command.facts != draft.facts
            or command.constraint_patch != draft.constraint_patch
        ):
            raise _violation(
                "TASK_REVISION_PREPARATION_MISMATCH",
                "prepared command changed the committed revision intent",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if command.operation is TaskRevisionOperation.PROVIDE_INPUT:
            summary = "append committed task fact: " + repr(command.facts[0])
        else:
            assert command.constraint_patch is not None
            patch = command.constraint_patch.to_dict()
            summary = "tighten allowlisted task constraints: " + ", ".join(
                f"{key}={value!r}" for key, value in sorted(patch.items())
            )
        fingerprint = hashlib.sha256(command.fingerprint()).hexdigest()
        return PreparedTaskRevision(
            draft=draft,
            envelope=envelope,
            command=command,
            command_fingerprint_sha256=fingerprint,
            confirmation_prompt=(
                f"Confirm {command.operation.value} for task {command.task_id}, "
                f"revision {command.expected_task_revision}, attempt "
                f"{command.expected_attempt_id}: {summary}. "
                f"Command fingerprint: {fingerprint}."
            ),
        )

    def authorize(
        self,
        prepared: PreparedTaskRevision,
        grant: TaskRevisionGrant,
        *,
        now: str,
    ) -> TaskRevisionCommand:
        if (
            type(prepared) is not PreparedTaskRevision
            or type(grant) is not TaskRevisionGrant
        ):
            raise _violation(
                "INVALID_TASK_REVISION_CONFIRMATION",
                "revision confirmation requires exact prepared and grant types",
                ErrorCode.PERMISSION_DENIED,
            )
        self._revalidate_draft(prepared.draft)
        try:
            narrowed = TaskRevisionCommand.from_envelope(prepared.envelope)
        except TaskRevisionViolation as error:
            raise _violation(error.reason, str(error), error.code) from error
        if narrowed != prepared.command:
            raise _violation(
                "TASK_REVISION_PREPARATION_MISMATCH",
                "prepared envelope no longer binds the confirmed revision command",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        try:
            grant.authorize(prepared.command, now=now)
        except TaskRevisionViolation as error:
            raise _violation(error.reason, str(error), error.code) from error
        return prepared.command


__all__ = [
    "BoundedTaskRevisionVoiceBridge",
    "PreparedTaskRevision",
    "TaskRevisionBridgeViolation",
    "TaskRevisionDraft",
    "TaskRevisionIntentDisposition",
    "TaskRevisionPolicyAdapter",
    "TaskRevisionSourceSpan",
    "TaskRevisionTargetReader",
]
