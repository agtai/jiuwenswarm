# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Deterministic critical-token clarification and committed-route guard.

This module does not recognize speech, create ``TurnCommit`` records, or own any
Agent, Tool, Task, Chat, or speech-response lifecycle.  It evaluates immutable
recognition evidence and issues a once-only authorization that a product
composition layer may place immediately before choosing a protected route.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Generic, Iterable, TypeVar

from jiuwenswarm.common.schema.live_voice_contract_v2 import TurnCommit


class CriticalTokenSafetyViolation(ValueError):
    """Raised only for invalid policy configuration or caller-owned evidence."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class CriticalTokenKind(StrEnum):
    NEGATION = "negation"
    NUMBER = "number"
    DATE_OR_TIME = "date_or_time"
    SHA = "sha"
    PATH_OR_BRANCH = "path_or_branch"
    IDENTIFIER = "identifier"
    COMMAND = "command"
    SIDE_EFFECT_VERB = "side_effect_verb"
    DOMAIN_TERM = "domain_term"


class EvidenceSource(StrEnum):
    SPEECH = "speech"
    EXPLICIT_TEXT = "explicit_text"


class EvidenceTextKind(StrEnum):
    RAW = "raw"
    DISPLAY = "display"


class CriticalTokenDecisionStatus(StrEnum):
    ELIGIBLE = "eligible"
    CLARIFICATION_REQUIRED = "clarification_required"
    BLOCKED = "blocked"
    BYPASSED = "bypassed"


class ClarificationState(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    REPLACED = "replaced"


class AuthorizationState(StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"
    REPLACED = "replaced"


class ProtectedRoute(StrEnum):
    AGENT = "agent"
    TOOL = "tool"
    TASK = "task"
    OTHER = "other"


class GuardDispatchStatus(StrEnum):
    DISPATCHED = "dispatched"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class CriticalTokenReason(StrEnum):
    FINAL_REQUIRED = "FINAL_REQUIRED"
    EVIDENCE_LIMIT_EXCEEDED = "EVIDENCE_LIMIT_EXCEEDED"
    CRITICAL_TOKEN_LIMIT_EXCEEDED = "CRITICAL_TOKEN_LIMIT_EXCEEDED"
    COMMIT_HYPOTHESIS_MISMATCH = "COMMIT_HYPOTHESIS_MISMATCH"
    CRITICAL_CONFIDENCE_UNKNOWN = "CRITICAL_CONFIDENCE_UNKNOWN"
    CRITICAL_LOW_CONFIDENCE = "CRITICAL_LOW_CONFIDENCE"
    CRITICAL_ALTERNATIVES_DISAGREE = "CRITICAL_ALTERNATIVES_DISAGREE"
    EXPLICIT_CRITICAL_UNCERTAINTY = "EXPLICIT_CRITICAL_UNCERTAINTY"
    EXPLICIT_CLARIFICATION_CONFIRMATION_REQUIRED = (
        "EXPLICIT_CLARIFICATION_CONFIRMATION_REQUIRED"
    )
    CLARIFICATION_BINDING_MISMATCH = "CLARIFICATION_BINDING_MISMATCH"
    CORRECTION_REQUIRES_NEW_TURN = "CORRECTION_REQUIRES_NEW_TURN"
    STALE_CLARIFICATION = "STALE_CLARIFICATION"
    STALE_INPUT = "STALE_INPUT"
    STALE_INPUT_GENERATION = "STALE_INPUT_GENERATION"
    INPUT_GENERATION_CONFLICT = "INPUT_GENERATION_CONFLICT"
    INPUT_GENERATION_PROVENANCE_MISMATCH = "INPUT_GENERATION_PROVENANCE_MISMATCH"
    COMMIT_ID_CONFLICT = "COMMIT_ID_CONFLICT"
    INTERACTION_CLOSED = "INTERACTION_CLOSED"
    GATE_CAPACITY_EXCEEDED = "GATE_CAPACITY_EXCEEDED"


@dataclass(frozen=True, slots=True)
class SpeechAlternativeEvidence:
    raw_text: str
    display_text: str
    confidence: float | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.raw_text, str)
            or not self.raw_text.strip()
            or not isinstance(self.display_text, str)
            or not self.display_text.strip()
        ):
            raise CriticalTokenSafetyViolation(
                "EMPTY_ALTERNATIVE",
                "speech alternatives must contain raw and display text",
            )
        if self.confidence is not None and (
            type(self.confidence) not in {int, float} or not 0 <= self.confidence <= 1
        ):
            raise CriticalTokenSafetyViolation(
                "INVALID_CONFIDENCE", "confidence must be between zero and one"
            )


@dataclass(frozen=True, slots=True)
class CommittedSpeechCandidate:
    commit: TurnCommit
    alternatives: tuple[SpeechAlternativeEvidence, ...]
    input_generation: int
    selected_index: int = 0
    is_final: bool = True
    source: EvidenceSource = EvidenceSource.SPEECH
    uncertainty_reasons: tuple[str, ...] = ()
    supersedes_commit_id: str | None = None

    def __post_init__(self) -> None:
        if not self.alternatives:
            raise CriticalTokenSafetyViolation(
                "EMPTY_HYPOTHESIS", "at least one recognition alternative is required"
            )
        if type(self.input_generation) is not int or self.input_generation < 0:
            raise CriticalTokenSafetyViolation(
                "INVALID_INPUT_GENERATION",
                "input_generation must be a non-negative integer",
            )
        if type(self.selected_index) is not int or not (
            0 <= self.selected_index < len(self.alternatives)
        ):
            raise CriticalTokenSafetyViolation(
                "INVALID_ALTERNATIVE_INDEX", "selected alternative is unavailable"
            )
        if type(self.is_final) is not bool:
            raise CriticalTokenSafetyViolation(
                "INVALID_FINAL_FLAG", "is_final must be a strict boolean"
            )
        try:
            EvidenceSource(self.source)
        except ValueError as error:
            raise CriticalTokenSafetyViolation(
                "INVALID_EVIDENCE_SOURCE", "unsupported evidence source"
            ) from error
        if any(
            not isinstance(reason, str) or not reason.strip()
            for reason in self.uncertainty_reasons
        ):
            raise CriticalTokenSafetyViolation(
                "INVALID_UNCERTAINTY_REASON",
                "uncertainty reasons must be non-empty strings",
            )
        if self.supersedes_commit_id is not None and (
            not isinstance(self.supersedes_commit_id, str)
            or not self.supersedes_commit_id.strip()
        ):
            raise CriticalTokenSafetyViolation(
                "INVALID_SUPERSEDED_COMMIT",
                "supersedes_commit_id must be non-empty when provided",
            )

    @property
    def selected(self) -> SpeechAlternativeEvidence:
        return self.alternatives[self.selected_index]


@dataclass(frozen=True, slots=True)
class CriticalTokenObservation:
    kind: CriticalTokenKind
    text: str
    normalized: str
    start: int
    end: int
    alternative_index: int
    evidence_text: EvidenceTextKind


@dataclass(frozen=True, slots=True)
class CriticalTokenDecision:
    status: CriticalTokenDecisionStatus
    reasons: tuple[CriticalTokenReason, ...]
    critical_tokens: tuple[CriticalTokenObservation, ...]
    requires_downstream_confirmation: bool

    @property
    def eligible(self) -> bool:
        return self.status is CriticalTokenDecisionStatus.ELIGIBLE


@dataclass(frozen=True, slots=True)
class ClarificationRequirement:
    clarification_id: str
    interaction_id: str
    source_turn_id: str
    source_commit_id: str
    source_input_generation: int
    reasons: tuple[CriticalTokenReason, ...]
    critical_tokens: tuple[CriticalTokenObservation, ...]
    prompt: str


@dataclass(frozen=True, slots=True)
class DispatchAuthorization:
    authorization_id: str
    interaction_id: str
    turn_id: str
    commit_id: str
    input_generation: int
    clarification_id: str | None
    safety_bypassed: bool


@dataclass(frozen=True, slots=True)
class CriticalTokenGateResult:
    decision: CriticalTokenDecision
    clarification: ClarificationRequirement | None = None
    authorization: DispatchAuthorization | None = None


_ResultT = TypeVar("_ResultT")


@dataclass(frozen=True, slots=True)
class GuardDispatchResult(Generic[_ResultT]):
    status: GuardDispatchStatus
    route: ProtectedRoute
    value: _ResultT | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class InteractionFenceResult:
    interaction_id: str
    clarification_id: str | None
    clarification_state: ClarificationState | None
    authorization_id: str | None
    authorization_state: AuthorizationState | None


@dataclass(slots=True)
class _ClarificationRecord:
    requirement: ClarificationRequirement
    source_commit: TurnCommit
    state: ClarificationState = ClarificationState.PENDING


@dataclass(slots=True)
class _AuthorizationRecord:
    authorization: DispatchAuthorization
    commit: TurnCommit
    state: AuthorizationState = AuthorizationState.ACTIVE


_PATTERNS: tuple[tuple[CriticalTokenKind, re.Pattern[str]], ...] = (
    (
        CriticalTokenKind.DATE_OR_TIME,
        re.compile(
            r"(?<!\w)(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
            r"\d{1,2}:\d{2}(?::\d{2})?)(?!\w)"
        ),
    ),
    (
        CriticalTokenKind.DATE_OR_TIME,
        re.compile(
            r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|monday|tuesday|"
            r"wednesday|thursday|friday|saturday|sunday)\b"
            r"(?:\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)?|"
            r"(?<![A-Za-z0-9])\d{1,2}(?::\d{2})?\s*"
            r"(?:a\.?m\.?|p\.?m\.?)(?![A-Za-z])",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.SHA,
        re.compile(
            r"(?<![0-9a-f])(?=[0-9a-f]{7,64}(?![0-9a-f]))"
            r"(?=[0-9a-f]*[a-f])[0-9a-f]+",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.PATH_OR_BRANCH,
        re.compile(r"(?:[A-Za-z]:\\|\\\\)[^\s\"'<>|]+"),
    ),
    (
        CriticalTokenKind.PATH_OR_BRANCH,
        re.compile(
            r'"(?:(?:[A-Za-z]:\\|\\\\)|\.{0,2}/)[^"\r\n]+"|'
            r"'(?:(?:[A-Za-z]:\\|\\\\)|\.{0,2}/)[^'\r\n]+'"
        ),
    ),
    (
        CriticalTokenKind.PATH_OR_BRANCH,
        re.compile(r"(?<!\w)(?:\.{0,2}/)[^\s\"'<>|]+"),
    ),
    (
        CriticalTokenKind.PATH_OR_BRANCH,
        re.compile(
            r"(?<!\w)(?!(?:and|or)/)(?:refs/(?:heads|tags)/|"
            r"[A-Za-z][A-Za-z0-9._-]*/)[A-Za-z0-9._/-]+",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.PATH_OR_BRANCH,
        re.compile(
            r"(?<!\w)(?:(?:checkout|switch|branch)\s+(?:-b\s+)?"
            r"[A-Za-z0-9][A-Za-z0-9._/-]*|"
            r"[A-Za-z0-9][A-Za-z0-9._/-]*\s+branch)(?!\w)|"
            r"(?:切换到|检出|分支)\s*[A-Za-z0-9][A-Za-z0-9._/-]*|"
            r"[A-Za-z0-9][A-Za-z0-9._/-]*\s*分支",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.PATH_OR_BRANCH,
        re.compile(
            r"(?<!\w)(?:git\s+)?(?:push|merge|rebase|reset)"
            r"(?:\s+--?[A-Za-z][A-Za-z0-9-]*(?:=[^\s,;]+)?)?"
            r"\s+[A-Za-z0-9][A-Za-z0-9._/-]*"
            r"(?:\s+[A-Za-z0-9][A-Za-z0-9._/-]*)?",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.COMMAND,
        re.compile(r"`[^`\r\n]+`|^\s*(?:\$|>)\s*\S.*$", re.MULTILINE),
    ),
    (
        CriticalTokenKind.COMMAND,
        re.compile(r"(?<!\w)--?[A-Za-z][A-Za-z0-9-]*"),
    ),
    (
        CriticalTokenKind.COMMAND,
        re.compile(
            r"(?<![\w.-])(?:git|checkout|rm|del|remove-item|npm|pnpm|yarn|python|"
            r"pytest|powershell|cmd|curl|wget|docker|kubectl)(?![\w.-])",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.IDENTIFIER,
        re.compile(
            r"\b(?:[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+|"
            r"[a-z]+[A-Z][A-Za-z0-9]*|"
            r"[A-Z][a-z]+[A-Z][A-Za-z0-9]*)\b"
        ),
    ),
    (
        CriticalTokenKind.IDENTIFIER,
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.IDENTIFIER,
        re.compile(
            r"\b[A-Za-z_]\w*(?:(?:\.|::)[A-Za-z_]\w*)+\b|"
            r"\b[A-Za-z_]\w*(?=\s*\()|"
            r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%[A-Za-z_][A-Za-z0-9_]*%"
        ),
    ),
    (
        CriticalTokenKind.IDENTIFIER,
        re.compile(
            r"\b(?=[A-Za-z0-9.-]*[A-Za-z])(?=[A-Za-z0-9.-]*\d)"
            r"[A-Za-z][A-Za-z0-9.-]*\b"
        ),
    ),
    (
        CriticalTokenKind.IDENTIFIER,
        re.compile(
            r"\b[A-Za-z0-9_-]+\."
            r"(?:py|ts|tsx|js|jsx|json|ya?ml|toml|md|txt|sh|ps1|java|go|"
            r"rs|cpp|h|css|html)\b",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.NEGATION,
        re.compile(
            r"(?<![A-Za-z])(?:not|no|never|without|don't|do\s+not)(?![A-Za-z])|"
            r"不要|不用|不能|不可|没有|尚未|未曾|禁止|别(?:再)?|"
            r"[不未](?=删除|移除|提交|推送|覆盖|重置|强制|发布|部署|执行|"
            r"运行|安装|卸载|取消|创建|发送)",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.SIDE_EFFECT_VERB,
        re.compile(
            r"(?<![A-Za-z])(?:delete|remove|rm|del|remove-item|commit|push|"
            r"checkout|merge|rebase|overwrite|reset|drop|truncate|shutdown|kill|chmod|chown|"
            r"force|publish|deploy|execute|run|install|uninstall|cancel|"
            r"create|send)(?![A-Za-z])|"
            r"删除|移除|提交|推送|覆盖|重置|强制|发布|部署|执行|运行|"
            r"安装|卸载|取消|创建|发送",
            re.IGNORECASE,
        ),
    ),
    (
        CriticalTokenKind.NUMBER,
        re.compile(r"(?<![A-Za-z0-9_.])[-+]?\d+(?:\.\d+)?%?(?![A-Za-z0-9_.])"),
    ),
    (
        CriticalTokenKind.NUMBER,
        re.compile(
            r"(?:第[零〇一二两三四五六七八九十百千万亿]+|"
            r"[零〇一二两三四五六七八九十百千万亿]{2,}|"
            r"[零〇一二两三四五六七八九](?=次|天|小时|分钟|秒|年|月|日|"
            r"号|点|项|条|份|台|轮|版|倍))"
        ),
    ),
    (
        CriticalTokenKind.NUMBER,
        re.compile(
            r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
            r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
            r"eighty|ninety|hundred|thousand|million|billion|first|second|"
            r"third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b",
            re.IGNORECASE,
        ),
    ),
)


def _normalize_token(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _normalize_comparison_token(value: str) -> str:
    """Normalize presentation variants without erasing case or token order."""

    return " ".join(unicodedata.normalize("NFKC", value).split())


class CriticalTokenPolicy:
    """Explainable lexical policy; no model judgment is required for release."""

    def __init__(
        self,
        *,
        minimum_confidence: float = 0.8,
        domain_terms: Iterable[str] = (),
        max_text_chars: int = 16_384,
        max_alternatives: int = 16,
        max_critical_tokens: int = 256,
    ) -> None:
        if type(minimum_confidence) not in {int, float} or not (
            0 <= minimum_confidence <= 1
        ):
            raise CriticalTokenSafetyViolation(
                "INVALID_CONFIDENCE_THRESHOLD",
                "minimum confidence must be between zero and one",
            )
        self._minimum_confidence = float(minimum_confidence)
        terms = tuple(domain_terms)
        for field_name, value in (
            ("max_text_chars", max_text_chars),
            ("max_alternatives", max_alternatives),
            ("max_critical_tokens", max_critical_tokens),
        ):
            if type(value) is not int or value <= 0:
                raise CriticalTokenSafetyViolation(
                    "INVALID_POLICY_LIMIT", f"{field_name} must be a positive integer"
                )
        if len(terms) > 1024 or any(
            not isinstance(term, str) or not term.strip() or len(term) > 256
            for term in terms
        ):
            raise CriticalTokenSafetyViolation(
                "INVALID_DOMAIN_TERM",
                "domain terms must be bounded non-empty strings",
            )
        self._max_text_chars = max_text_chars
        self._max_alternatives = max_alternatives
        self._max_critical_tokens = max_critical_tokens
        self._domain_patterns = tuple(
            (
                term,
                re.compile(
                    (r"(?<!\w)" if term[0].isalnum() else "")
                    + re.escape(term)
                    + (r"(?!\w)" if term[-1].isalnum() else ""),
                    re.IGNORECASE,
                ),
            )
            for term in sorted(set(terms), key=lambda item: (-len(item), item))
        )

    def scan(
        self,
        text: str,
        *,
        alternative_index: int = 0,
        evidence_text: EvidenceTextKind = EvidenceTextKind.DISPLAY,
    ) -> tuple[CriticalTokenObservation, ...]:
        observations: list[CriticalTokenObservation] = []
        seen: set[tuple[CriticalTokenKind, int, int, str]] = set()
        for kind, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                normalized = _normalize_token(match.group(0))
                key = (kind, match.start(), match.end(), normalized)
                if key in seen:
                    continue
                seen.add(key)
                observations.append(
                    CriticalTokenObservation(
                        kind,
                        match.group(0),
                        normalized,
                        match.start(),
                        match.end(),
                        alternative_index,
                        evidence_text,
                    )
                )
        for _, pattern in self._domain_patterns:
            for match in pattern.finditer(text):
                normalized = _normalize_token(match.group(0))
                key = (
                    CriticalTokenKind.DOMAIN_TERM,
                    match.start(),
                    match.end(),
                    normalized,
                )
                if key in seen:
                    continue
                seen.add(key)
                observations.append(
                    CriticalTokenObservation(
                        CriticalTokenKind.DOMAIN_TERM,
                        match.group(0),
                        normalized,
                        match.start(),
                        match.end(),
                        alternative_index,
                        evidence_text,
                    )
                )
        return tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.start,
                    item.end,
                    item.kind.value,
                    item.normalized,
                ),
            )
        )

    def evaluate(self, candidate: CommittedSpeechCandidate) -> CriticalTokenDecision:
        integrity = self.evaluate_commit_integrity(candidate)
        if integrity.status is CriticalTokenDecisionStatus.BLOCKED:
            return integrity
        if (
            len(candidate.alternatives) > self._max_alternatives
            or any(
                len(alternative.raw_text) > self._max_text_chars
                or len(alternative.display_text) > self._max_text_chars
                for alternative in candidate.alternatives
            )
            or len(candidate.uncertainty_reasons) > 16
            or any(len(reason) > 256 for reason in candidate.uncertainty_reasons)
        ):
            return self._decision(
                CriticalTokenDecisionStatus.BLOCKED,
                (CriticalTokenReason.EVIDENCE_LIMIT_EXCEEDED,),
                (),
            )
        all_tokens = tuple(
            token
            for index, alternative in enumerate(candidate.alternatives)
            for token in self._scan_alternative(alternative, index=index)
        )
        if not all_tokens and candidate.uncertainty_reasons:
            return self._decision(
                CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED,
                (CriticalTokenReason.EXPLICIT_CRITICAL_UNCERTAINTY,),
                (),
            )
        if not all_tokens:
            return self._decision(CriticalTokenDecisionStatus.ELIGIBLE, (), ())
        if len(all_tokens) > self._max_critical_tokens:
            return self._decision(
                CriticalTokenDecisionStatus.BLOCKED,
                (CriticalTokenReason.CRITICAL_TOKEN_LIMIT_EXCEEDED,),
                (),
            )

        reasons: list[CriticalTokenReason] = []
        signatures = tuple(
            signature
            for alternative in candidate.alternatives
            for signature in (
                self._signature(alternative.raw_text),
                self._signature(alternative.display_text),
            )
        )
        if any(signature != signatures[0] for signature in signatures[1:]):
            reasons.append(CriticalTokenReason.CRITICAL_ALTERNATIVES_DISAGREE)
        if candidate.uncertainty_reasons:
            reasons.append(CriticalTokenReason.EXPLICIT_CRITICAL_UNCERTAINTY)
        if EvidenceSource(candidate.source) is EvidenceSource.SPEECH:
            if candidate.selected.confidence is None:
                reasons.append(CriticalTokenReason.CRITICAL_CONFIDENCE_UNKNOWN)
            elif candidate.selected.confidence < self._minimum_confidence:
                reasons.append(CriticalTokenReason.CRITICAL_LOW_CONFIDENCE)

        status = (
            CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
            if reasons
            else CriticalTokenDecisionStatus.ELIGIBLE
        )
        return self._decision(status, tuple(dict.fromkeys(reasons)), all_tokens)

    def evaluate_commit_integrity(
        self, candidate: CommittedSpeechCandidate
    ) -> CriticalTokenDecision:
        """Check invariants that remain mandatory when clarification is disabled."""

        if not _matches_input_generation_provenance(candidate):
            return self._decision(
                CriticalTokenDecisionStatus.BLOCKED,
                (CriticalTokenReason.INPUT_GENERATION_PROVENANCE_MISMATCH,),
                (),
            )
        if not candidate.is_final:
            return self._decision(
                CriticalTokenDecisionStatus.BLOCKED,
                (CriticalTokenReason.FINAL_REQUIRED,),
                (),
            )
        if candidate.commit.text != candidate.selected.display_text:
            return self._decision(
                CriticalTokenDecisionStatus.BLOCKED,
                (CriticalTokenReason.COMMIT_HYPOTHESIS_MISMATCH,),
                (),
            )
        return self._decision(CriticalTokenDecisionStatus.ELIGIBLE, (), ())

    def _signature(self, text: str) -> tuple[tuple[str, str], ...]:
        return tuple(
            (token.kind.value, _normalize_comparison_token(token.text))
            for token in self.scan(text)
        )

    def _scan_alternative(
        self, alternative: SpeechAlternativeEvidence, *, index: int
    ) -> tuple[CriticalTokenObservation, ...]:
        raw = self.scan(
            alternative.raw_text,
            alternative_index=index,
            evidence_text=EvidenceTextKind.RAW,
        )
        if alternative.display_text == alternative.raw_text:
            return raw
        return raw + self.scan(
            alternative.display_text,
            alternative_index=index,
            evidence_text=EvidenceTextKind.DISPLAY,
        )

    @staticmethod
    def _decision(
        status: CriticalTokenDecisionStatus,
        reasons: tuple[CriticalTokenReason, ...],
        tokens: tuple[CriticalTokenObservation, ...],
    ) -> CriticalTokenDecision:
        return CriticalTokenDecision(
            status,
            reasons,
            tokens,
            any(token.kind is CriticalTokenKind.SIDE_EFFECT_VERB for token in tokens),
        )


class CriticalTokenSafetyGate:
    """Stateful clarification fence and once-only protected-route dispatch seam."""

    def __init__(
        self,
        policy: CriticalTokenPolicy | None = None,
        *,
        enabled: bool = True,
        capacity: int = 4_096,
    ) -> None:
        if type(enabled) is not bool:
            raise CriticalTokenSafetyViolation(
                "INVALID_FEATURE_FLAG", "enabled must be a strict boolean"
            )
        if type(capacity) is not int or not 1 <= capacity <= 65_536:
            raise CriticalTokenSafetyViolation(
                "INVALID_GATE_CAPACITY", "capacity must be an integer from 1 to 65536"
            )
        self._policy = policy or CriticalTokenPolicy()
        self._enabled = enabled
        self._capacity = capacity
        self._lock = threading.RLock()
        self._candidate_fingerprints: dict[str, str] = {}
        self._commit_interactions: dict[str, str] = {}
        self._commit_generations: dict[str, int] = {}
        self._blocked_commit_ids: set[str] = set()
        self._latest_input_generation: dict[str, int] = {}
        self._results: dict[str, CriticalTokenGateResult] = {}
        self._clarifications: dict[str, _ClarificationRecord] = {}
        self._authorizations: dict[str, _AuthorizationRecord] = {}
        self._active_clarification: dict[str, str] = {}
        self._active_authorization: dict[str, str] = {}
        self._closed_interactions: set[str] = set()

    def evaluate(self, candidate: CommittedSpeechCandidate) -> CriticalTokenGateResult:
        with self._lock:
            if candidate.commit.interaction_id in self._closed_interactions:
                return _blocked_result(CriticalTokenReason.INTERACTION_CLOSED)
            if not _matches_input_generation_provenance(candidate):
                return _blocked_result(
                    CriticalTokenReason.INPUT_GENERATION_PROVENANCE_MISMATCH
                )
            known_commit = candidate.commit.commit_id in self._candidate_fingerprints
            known_blocked = candidate.commit.commit_id in self._blocked_commit_ids
            if (
                not known_commit
                and not known_blocked
                and (
                    len(self._commit_interactions) >= self._capacity
                    or (
                        candidate.commit.interaction_id
                        not in self._latest_input_generation
                        and len(self._latest_input_generation) >= self._capacity
                    )
                )
            ):
                return _blocked_result(CriticalTokenReason.GATE_CAPACITY_EXCEEDED)
            if known_commit or known_blocked:
                if self._known_commit_conflicts(candidate):
                    return _blocked_result(CriticalTokenReason.COMMIT_ID_CONFLICT)
                latest = self._latest_input_generation.get(
                    candidate.commit.interaction_id
                )
                if latest is not None and candidate.input_generation < latest:
                    return _blocked_result(CriticalTokenReason.STALE_INPUT_GENERATION)
                if known_blocked:
                    return _blocked_result(CriticalTokenReason.STALE_INPUT)
            else:
                latest = self._latest_input_generation.get(
                    candidate.commit.interaction_id
                )
                if latest is not None and candidate.input_generation < latest:
                    return _blocked_result(CriticalTokenReason.STALE_INPUT_GENERATION)
                if latest is not None and candidate.input_generation == latest:
                    return _blocked_result(
                        CriticalTokenReason.INPUT_GENERATION_CONFLICT
                    )
                self._replace_active(candidate.commit.interaction_id)
                self._latest_input_generation[candidate.commit.interaction_id] = (
                    candidate.input_generation
                )
            policy_decision = (
                self._policy.evaluate(candidate)
                if self._enabled
                else self._policy.evaluate_commit_integrity(candidate)
            )
            if policy_decision.status is CriticalTokenDecisionStatus.BLOCKED:
                if not known_commit:
                    self._mark_blocked(candidate)
                return CriticalTokenGateResult(policy_decision)
            if not self._enabled:
                decision = CriticalTokenDecision(
                    CriticalTokenDecisionStatus.BYPASSED,
                    (),
                    (),
                    False,
                )
                fingerprint = _commit_fingerprint(candidate.commit)
            else:
                decision = policy_decision
                fingerprint = _candidate_fingerprint(candidate)
            replay = self._replay(candidate.commit.commit_id, fingerprint)
            if replay is not None:
                return replay

            return self._accept_decision(candidate, fingerprint, decision)

    def resolve(
        self,
        clarification_id: str,
        corrected: CommittedSpeechCandidate,
        *,
        confirmed: bool,
    ) -> CriticalTokenGateResult:
        if type(confirmed) is not bool:
            raise CriticalTokenSafetyViolation(
                "INVALID_CONFIRMATION_FLAG", "confirmed must be a strict boolean"
            )
        with self._lock:
            if corrected.commit.interaction_id in self._closed_interactions:
                return _blocked_result(CriticalTokenReason.INTERACTION_CLOSED)
            if not _matches_input_generation_provenance(corrected):
                return _blocked_result(
                    CriticalTokenReason.INPUT_GENERATION_PROVENANCE_MISMATCH
                )
            record = self._clarifications.get(clarification_id)
            if record is None or record.state is not ClarificationState.PENDING:
                return _blocked_result(CriticalTokenReason.STALE_CLARIFICATION)
            if not confirmed:
                return _blocked_result(
                    CriticalTokenReason.EXPLICIT_CLARIFICATION_CONFIRMATION_REQUIRED
                )
            if (
                corrected.commit.interaction_id != record.requirement.interaction_id
                or corrected.commit.scope != record.source_commit.scope
                or corrected.supersedes_commit_id != record.requirement.source_commit_id
                or not _matches_clarification_provenance(
                    corrected.commit,
                    clarification_id=clarification_id,
                    supersedes_commit_id=record.requirement.source_commit_id,
                    input_generation=corrected.input_generation,
                )
            ):
                return _blocked_result(
                    CriticalTokenReason.CLARIFICATION_BINDING_MISMATCH
                )
            if (
                corrected.commit.commit_id == record.requirement.source_commit_id
                or corrected.commit.turn_id == record.requirement.source_turn_id
            ):
                return _blocked_result(CriticalTokenReason.CORRECTION_REQUIRES_NEW_TURN)

            if (
                corrected.commit.commit_id in self._candidate_fingerprints
                or corrected.commit.commit_id in self._blocked_commit_ids
            ):
                if self._known_commit_conflicts(corrected):
                    return _blocked_result(CriticalTokenReason.COMMIT_ID_CONFLICT)
                return _blocked_result(CriticalTokenReason.STALE_INPUT)
            if len(self._commit_interactions) >= self._capacity:
                return _blocked_result(CriticalTokenReason.GATE_CAPACITY_EXCEEDED)
            latest = self._latest_input_generation.get(
                corrected.commit.interaction_id,
                record.requirement.source_input_generation,
            )
            if corrected.input_generation <= latest:
                return _blocked_result(CriticalTokenReason.STALE_INPUT_GENERATION)

            self._replace_active(corrected.commit.interaction_id)
            self._latest_input_generation[corrected.commit.interaction_id] = (
                corrected.input_generation
            )
            decision = self._policy.evaluate(corrected)
            if decision.status is CriticalTokenDecisionStatus.BLOCKED:
                self._mark_blocked(corrected)
                return CriticalTokenGateResult(decision)
            fingerprint = _candidate_fingerprint(corrected)
            replay = self._replay(corrected.commit.commit_id, fingerprint)
            if replay is not None:
                return _blocked_result(CriticalTokenReason.STALE_INPUT)

            record.state = (
                ClarificationState.REPLACED
                if decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED
                else ClarificationState.RESOLVED
            )
            return self._accept_decision(
                corrected,
                fingerprint,
                decision,
                resolved_clarification_id=clarification_id,
            )

    def cancel_clarification(self, clarification_id: str) -> ClarificationState:
        with self._lock:
            record = self._clarifications.get(clarification_id)
            if record is None:
                raise CriticalTokenSafetyViolation(
                    "UNKNOWN_CLARIFICATION", "clarification_id is unknown"
                )
            if record.state is ClarificationState.PENDING:
                record.state = ClarificationState.CANCELLED
                if (
                    self._active_clarification.get(record.requirement.interaction_id)
                    == clarification_id
                ):
                    self._active_clarification.pop(
                        record.requirement.interaction_id, None
                    )
            return record.state

    def cancel_authorization(self, authorization_id: str) -> AuthorizationState:
        with self._lock:
            record = self._authorizations.get(authorization_id)
            if record is None:
                raise CriticalTokenSafetyViolation(
                    "UNKNOWN_AUTHORIZATION", "authorization_id is unknown"
                )
            if record.state is AuthorizationState.ACTIVE:
                record.state = AuthorizationState.CANCELLED
                if (
                    self._active_authorization.get(record.authorization.interaction_id)
                    == authorization_id
                ):
                    self._active_authorization.pop(
                        record.authorization.interaction_id, None
                    )
            return record.state

    def clarification_state(self, clarification_id: str) -> ClarificationState:
        with self._lock:
            record = self._clarifications.get(clarification_id)
            if record is None:
                raise CriticalTokenSafetyViolation(
                    "UNKNOWN_CLARIFICATION", "clarification_id is unknown"
                )
            return record.state

    def authorization_state(self, authorization_id: str) -> AuthorizationState:
        with self._lock:
            record = self._authorizations.get(authorization_id)
            if record is None:
                raise CriticalTokenSafetyViolation(
                    "UNKNOWN_AUTHORIZATION", "authorization_id is unknown"
                )
            return record.state

    def close_interaction(self, interaction_id: str) -> InteractionFenceResult:
        if not isinstance(interaction_id, str) or not interaction_id.strip():
            raise CriticalTokenSafetyViolation(
                "INVALID_INTERACTION_ID", "interaction_id must be non-empty"
            )
        with self._lock:
            if (
                interaction_id not in self._closed_interactions
                and interaction_id not in self._latest_input_generation
                and len(self._closed_interactions) >= self._capacity
            ):
                raise CriticalTokenSafetyViolation(
                    "GATE_CAPACITY_EXCEEDED",
                    "the bounded interaction fence is full",
                )
            self._closed_interactions.add(interaction_id)
            clarification_id = self._active_clarification.pop(interaction_id, None)
            clarification_state = None
            if clarification_id is not None:
                clarification = self._clarifications[clarification_id]
                if clarification.state is ClarificationState.PENDING:
                    clarification.state = ClarificationState.CANCELLED
                clarification_state = clarification.state

            authorization_id = self._active_authorization.pop(interaction_id, None)
            authorization_state = None
            if authorization_id is not None:
                authorization = self._authorizations[authorization_id]
                if authorization.state is AuthorizationState.ACTIVE:
                    authorization.state = AuthorizationState.CANCELLED
                authorization_state = authorization.state

            return InteractionFenceResult(
                interaction_id,
                clarification_id,
                clarification_state,
                authorization_id,
                authorization_state,
            )

    def release_commit(self, commit_id: str) -> None:
        """Release terminal per-commit evidence while preserving generation fences."""

        if not isinstance(commit_id, str) or not commit_id.strip():
            raise CriticalTokenSafetyViolation(
                "INVALID_COMMIT_ID", "commit_id must be non-empty"
            )
        with self._lock:
            result = self._results.pop(commit_id, None)
            self._candidate_fingerprints.pop(commit_id, None)
            self._blocked_commit_ids.discard(commit_id)
            self._commit_interactions.pop(commit_id, None)
            self._commit_generations.pop(commit_id, None)
            if result is None:
                return
            if result.clarification is not None:
                clarification_id = result.clarification.clarification_id
                record = self._clarifications.pop(clarification_id, None)
                if (
                    record is not None
                    and self._active_clarification.get(
                        record.requirement.interaction_id
                    )
                    == clarification_id
                ):
                    self._active_clarification.pop(
                        record.requirement.interaction_id, None
                    )
            if result.authorization is not None:
                authorization_id = result.authorization.authorization_id
                record = self._authorizations.pop(authorization_id, None)
                if (
                    record is not None
                    and self._active_authorization.get(
                        record.authorization.interaction_id
                    )
                    == authorization_id
                ):
                    self._active_authorization.pop(
                        record.authorization.interaction_id, None
                    )

    def release_interaction(self, interaction_id: str) -> None:
        """Release a product-owned interaction after its outer route is fenced."""

        if not isinstance(interaction_id, str) or not interaction_id.strip():
            raise CriticalTokenSafetyViolation(
                "INVALID_INTERACTION_ID", "interaction_id must be non-empty"
            )
        with self._lock:
            commit_ids = tuple(
                commit_id
                for commit_id, owner in self._commit_interactions.items()
                if owner == interaction_id
            )
            for commit_id in commit_ids:
                self.release_commit(commit_id)
            for clarification_id, record in tuple(self._clarifications.items()):
                if record.requirement.interaction_id == interaction_id:
                    self._clarifications.pop(clarification_id, None)
            for authorization_id, record in tuple(self._authorizations.items()):
                if record.authorization.interaction_id == interaction_id:
                    self._authorizations.pop(authorization_id, None)
            self._active_clarification.pop(interaction_id, None)
            self._active_authorization.pop(interaction_id, None)
            self._latest_input_generation.pop(interaction_id, None)
            self._closed_interactions.discard(interaction_id)

    def reset(self) -> None:
        """Release every retained fact after the composition owner stops."""

        with self._lock:
            self._candidate_fingerprints.clear()
            self._commit_interactions.clear()
            self._commit_generations.clear()
            self._blocked_commit_ids.clear()
            self._latest_input_generation.clear()
            self._results.clear()
            self._clarifications.clear()
            self._authorizations.clear()
            self._active_clarification.clear()
            self._active_authorization.clear()
            self._closed_interactions.clear()

    def dispatch(
        self,
        authorization: DispatchAuthorization,
        route: ProtectedRoute,
        effect: Callable[[TurnCommit], _ResultT],
    ) -> GuardDispatchResult[_ResultT]:
        try:
            parsed_route = ProtectedRoute(route)
        except (TypeError, ValueError):
            return GuardDispatchResult(
                GuardDispatchStatus.REJECTED,
                ProtectedRoute.OTHER,
                reason="INVALID_PROTECTED_ROUTE",
            )
        with self._lock:
            record = self._authorizations.get(authorization.authorization_id)
            if record is None or record.authorization != authorization:
                return GuardDispatchResult(
                    GuardDispatchStatus.REJECTED,
                    parsed_route,
                    reason="AUTHORIZATION_NOT_ISSUED",
                )
            if authorization.interaction_id in self._closed_interactions:
                if record.state is AuthorizationState.ACTIVE:
                    record.state = AuthorizationState.CANCELLED
                return GuardDispatchResult(
                    GuardDispatchStatus.REJECTED,
                    parsed_route,
                    reason="INTERACTION_CLOSED",
                )
            if record.state is AuthorizationState.CONSUMED:
                return GuardDispatchResult(
                    GuardDispatchStatus.DUPLICATE,
                    parsed_route,
                    reason="AUTHORIZATION_ALREADY_CONSUMED",
                )
            if record.state is not AuthorizationState.ACTIVE:
                return GuardDispatchResult(
                    GuardDispatchStatus.REJECTED,
                    parsed_route,
                    reason=f"AUTHORIZATION_{record.state.value.upper()}",
                )
            if (
                self._active_authorization.get(authorization.interaction_id)
                != authorization.authorization_id
            ):
                record.state = AuthorizationState.REPLACED
                return GuardDispatchResult(
                    GuardDispatchStatus.REJECTED,
                    parsed_route,
                    reason="AUTHORIZATION_STALE",
                )
            record.state = AuthorizationState.CONSUMED
            self._active_authorization.pop(authorization.interaction_id, None)
            commit = record.commit

        # Consume before invoking the route: an exception cannot safely prove that a
        # protected downstream effect did not already occur.
        value = effect(commit)
        return GuardDispatchResult(
            GuardDispatchStatus.DISPATCHED, parsed_route, value=value
        )

    def _accept_decision(
        self,
        candidate: CommittedSpeechCandidate,
        fingerprint: str,
        decision: CriticalTokenDecision,
        *,
        resolved_clarification_id: str | None = None,
    ) -> CriticalTokenGateResult:
        if decision.status is CriticalTokenDecisionStatus.CLARIFICATION_REQUIRED:
            clarification = self._issue_clarification(candidate, decision)
            return self._remember(
                candidate,
                fingerprint,
                CriticalTokenGateResult(decision, clarification=clarification),
            )
        authorization = self._issue_authorization(
            candidate,
            clarification_id=resolved_clarification_id,
            safety_bypassed=decision.status is CriticalTokenDecisionStatus.BYPASSED,
        )
        return self._remember(
            candidate,
            fingerprint,
            CriticalTokenGateResult(decision, authorization=authorization),
        )

    def _issue_clarification(
        self,
        candidate: CommittedSpeechCandidate,
        decision: CriticalTokenDecision,
    ) -> ClarificationRequirement:
        clarification_id = _stable_id(
            "clarification", candidate.commit.canonical_bytes()
        )
        prompt_tokens = sorted(
            {f"{token.kind.value}={token.text!r}" for token in decision.critical_tokens}
        )
        prompt = (
            "Confirm the exact critical tokens before dispatch: "
            + ", ".join(prompt_tokens)
            if prompt_tokens
            else "Confirm the exact committed speech before dispatch; critical uncertainty was reported."
        )
        requirement = ClarificationRequirement(
            clarification_id,
            candidate.commit.interaction_id,
            candidate.commit.turn_id,
            candidate.commit.commit_id,
            candidate.input_generation,
            decision.reasons,
            decision.critical_tokens,
            prompt,
        )
        self._clarifications[clarification_id] = _ClarificationRecord(
            requirement, candidate.commit
        )
        self._active_clarification[candidate.commit.interaction_id] = clarification_id
        return requirement

    def _issue_authorization(
        self,
        candidate: CommittedSpeechCandidate,
        *,
        clarification_id: str | None,
        safety_bypassed: bool,
    ) -> DispatchAuthorization:
        authorization_id = _stable_id(
            "authorization", candidate.commit.canonical_bytes()
        )
        authorization = DispatchAuthorization(
            authorization_id,
            candidate.commit.interaction_id,
            candidate.commit.turn_id,
            candidate.commit.commit_id,
            candidate.input_generation,
            clarification_id,
            safety_bypassed,
        )
        self._authorizations[authorization_id] = _AuthorizationRecord(
            authorization, candidate.commit
        )
        self._active_authorization[candidate.commit.interaction_id] = authorization_id
        return authorization

    def _replace_active(self, interaction_id: str) -> None:
        clarification_id = self._active_clarification.pop(interaction_id, None)
        if clarification_id is not None:
            clarification_record = self._clarifications[clarification_id]
            if clarification_record.state is ClarificationState.PENDING:
                clarification_record.state = ClarificationState.REPLACED
        authorization_id = self._active_authorization.pop(interaction_id, None)
        if authorization_id is not None:
            authorization_record = self._authorizations[authorization_id]
            if authorization_record.state is AuthorizationState.ACTIVE:
                authorization_record.state = AuthorizationState.REPLACED

    def _remember(
        self,
        candidate: CommittedSpeechCandidate,
        fingerprint: str,
        result: CriticalTokenGateResult,
    ) -> CriticalTokenGateResult:
        self._candidate_fingerprints[candidate.commit.commit_id] = fingerprint
        self._commit_interactions[candidate.commit.commit_id] = (
            candidate.commit.interaction_id
        )
        self._commit_generations[candidate.commit.commit_id] = (
            candidate.input_generation
        )
        self._results[candidate.commit.commit_id] = result
        return result

    def _mark_blocked(self, candidate: CommittedSpeechCandidate) -> None:
        self._blocked_commit_ids.add(candidate.commit.commit_id)
        self._commit_interactions[candidate.commit.commit_id] = (
            candidate.commit.interaction_id
        )
        self._commit_generations[candidate.commit.commit_id] = (
            candidate.input_generation
        )

    def _known_commit_conflicts(self, candidate: CommittedSpeechCandidate) -> bool:
        return (
            self._commit_interactions[candidate.commit.commit_id]
            != candidate.commit.interaction_id
            or self._commit_generations[candidate.commit.commit_id]
            != candidate.input_generation
        )

    def _replay(
        self, commit_id: str, fingerprint: str
    ) -> CriticalTokenGateResult | None:
        existing = self._candidate_fingerprints.get(commit_id)
        if existing is None:
            return None
        if existing != fingerprint:
            return _blocked_result(CriticalTokenReason.COMMIT_ID_CONFLICT)
        result = self._results[commit_id]
        if result.clarification is not None:
            clarification_record = self._clarifications[
                result.clarification.clarification_id
            ]
            if clarification_record.state is ClarificationState.PENDING:
                return result
            return _blocked_result(CriticalTokenReason.STALE_INPUT)
        if result.authorization is not None:
            authorization_record = self._authorizations[
                result.authorization.authorization_id
            ]
            if authorization_record.state is AuthorizationState.ACTIVE:
                return result
            return _blocked_result(CriticalTokenReason.STALE_INPUT)
        return result


def _candidate_fingerprint(candidate: CommittedSpeechCandidate) -> str:
    payload = {
        "commit": candidate.commit.to_dict(),
        "alternatives": [
            {
                "raw_text": alternative.raw_text,
                "display_text": alternative.display_text,
                "confidence": alternative.confidence,
            }
            for alternative in candidate.alternatives
        ],
        "selected_index": candidate.selected_index,
        "input_generation": candidate.input_generation,
        "is_final": candidate.is_final,
        "source": EvidenceSource(candidate.source).value,
        "uncertainty_reasons": list(candidate.uncertainty_reasons),
        "supersedes_commit_id": candidate.supersedes_commit_id,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _commit_fingerprint(commit: TurnCommit) -> str:
    return hashlib.sha256(commit.canonical_bytes()).hexdigest()


def _matches_clarification_provenance(
    commit: TurnCommit,
    *,
    clarification_id: str,
    supersedes_commit_id: str,
    input_generation: int,
) -> bool:
    provenance = commit.hypothesis_provenance
    binding = provenance.get("critical_token_clarification")
    provenance_generation = (
        binding.get("input_generation") if isinstance(binding, dict) else None
    )
    return (
        isinstance(binding, dict)
        and binding.get("clarification_id") == clarification_id
        and binding.get("supersedes_commit_id") == supersedes_commit_id
        and type(provenance_generation) is int
        and provenance_generation == input_generation
    )


def _matches_input_generation_provenance(
    candidate: CommittedSpeechCandidate,
) -> bool:
    provenance = candidate.commit.hypothesis_provenance
    binding = provenance.get("critical_token_input")
    provenance_generation = (
        binding.get("input_generation") if isinstance(binding, dict) else None
    )
    return (
        isinstance(binding, dict)
        and type(provenance_generation) is int
        and provenance_generation == candidate.input_generation
    )


def _stable_id(prefix: str, value: bytes) -> str:
    digest = hashlib.sha256(prefix.encode("ascii") + b"\0" + value).hexdigest()
    return f"{prefix}-{digest[:24]}"


def _blocked_result(reason: CriticalTokenReason) -> CriticalTokenGateResult:
    return CriticalTokenGateResult(
        CriticalTokenDecision(
            CriticalTokenDecisionStatus.BLOCKED,
            (reason,),
            (),
            False,
        )
    )


__all__ = [
    "AuthorizationState",
    "ClarificationRequirement",
    "ClarificationState",
    "CommittedSpeechCandidate",
    "CriticalTokenDecision",
    "CriticalTokenDecisionStatus",
    "CriticalTokenGateResult",
    "CriticalTokenKind",
    "CriticalTokenObservation",
    "CriticalTokenPolicy",
    "CriticalTokenReason",
    "CriticalTokenSafetyGate",
    "CriticalTokenSafetyViolation",
    "DispatchAuthorization",
    "EvidenceSource",
    "EvidenceTextKind",
    "GuardDispatchResult",
    "GuardDispatchStatus",
    "InteractionFenceResult",
    "ProtectedRoute",
    "SpeechAlternativeEvidence",
]
