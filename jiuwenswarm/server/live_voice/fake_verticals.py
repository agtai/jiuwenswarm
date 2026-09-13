# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Deterministic P1, P2, and P3-alpha integration verticals."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import MappingProxyType

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ContractViolation,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
)

from .agent_bridge import AgentBridgePort, AgentEvent
from .conversation_runtime import (
    ConversationRuntime,
    ConversationSnapshot,
    ResponseState,
    RuntimeEffect,
)
from .executor_port import ExecutorPort
from .speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEvent,
    RecognitionEventKind,
    RecognitionHypothesis,
    RecognitionPort,
    SpeechCapability,
    SpeechMode,
    SynthesisEvent,
    SynthesisPort,
    SynthesisRequest,
)
from .task_core import (
    AuthorizationContext,
    TaskCommand,
    TaskCore,
    TaskRecord,
    WorkProgress,
    project_work_progress,
)
from .voice_task_bridge import TaskIntent, VoiceTaskBridge


class FakeVerticalViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class FakeTrackAvailability:
    p1: bool = True
    p2: bool = True
    p3alpha: bool = True


@dataclass(frozen=True, slots=True)
class FakeRouteFact:
    segment_id: str
    implementation_class: str
    owner_module: str
    capability_provider: str | None
    safe_reason: str


@dataclass(frozen=True, slots=True)
class FakeP1Result:
    committed_text: str
    recognition_events: tuple[RecognitionEvent, ...]
    partial_synthesis_events: tuple[SynthesisEvent, ...]
    synthesis_events: tuple[SynthesisEvent, ...]
    route: FakeRouteFact


@dataclass(frozen=True, slots=True)
class FakeP2Result:
    submit_returned_before_completion: bool
    original_response: ResponseRef
    replacement_response: ResponseRef | None
    agent_events: tuple[AgentEvent, ...]
    output_effects: tuple[RuntimeEffect, ...]
    stale_output_blocked: bool
    snapshot: ConversationSnapshot
    route: FakeRouteFact


@dataclass(frozen=True, slots=True)
class FakeP3Result:
    command: TaskCommand
    task_id: str
    attempt_id: str
    progress: tuple[WorkProgress, ...]
    terminal_task: TaskRecord
    tts_effects: tuple[object, ...]
    route: FakeRouteFact


class _CommittedTextBoundary:
    def __init__(self) -> None:
        self._committed_text: str | None = None

    def accept(self, event: RecognitionEvent, commit: TurnCommit) -> bool:
        if event.kind is not RecognitionEventKind.FINAL:
            return False
        resolved = RecognitionPort.resolve(event)
        if resolved.display_text != commit.text:
            raise FakeVerticalViolation(
                "COMMITTED_TEXT_MISMATCH",
                "recognition final must match the externally committed text",
            )
        self._committed_text = commit.text
        return True

    @property
    def text(self) -> str:
        if self._committed_text is None:
            raise FakeVerticalViolation(
                "TEXT_NOT_COMMITTED", "synthesis requires committed text"
            )
        return self._committed_text


class FakeIntegratedVerticals:
    _TRACKS = MappingProxyType(
        {
            "p1": ("p1.speech", "speech_ports", "deterministic-speech-fake"),
            "p2": (
                "p2.conversation",
                "conversation_runtime+agent_bridge",
                "deterministic-agent-fake",
            ),
            "p3alpha": (
                "p3alpha.task",
                "task_core+executor_port+voice_task_bridge",
                "deterministic-executor-fake",
            ),
        }
    )

    def __init__(self, availability: FakeTrackAvailability | None = None) -> None:
        self._availability = availability or FakeTrackAvailability()
        if any(
            type(value) is not bool
            for value in (
                self._availability.p1,
                self._availability.p2,
                self._availability.p3alpha,
            )
        ):
            raise FakeVerticalViolation(
                "INVALID_AVAILABILITY", "track availability must be boolean"
            )

    def routes(self) -> tuple[FakeRouteFact, ...]:
        return tuple(self._route(track) for track in self._TRACKS)

    def run_p1(
        self,
        commit: TurnCommit,
        response: ResponseRef,
        *,
        recognized_display_text: str | None = None,
        audio: bytes = b"deterministic-audio",
    ) -> FakeP1Result:
        self._require_track("p1")
        if response.interaction_id != commit.interaction_id:
            raise FakeVerticalViolation(
                "RESPONSE_SCOPE_MISMATCH",
                "speech output must target the committed interaction",
            )
        provider = ProviderRef("deterministic-speech-fake", "demo_substitute")
        capability = SpeechCapability(
            provider,
            frozenset({SpeechMode.STREAM}),
            frozenset({SpeechMode.STREAM}),
        )
        recognition = RecognitionPort(capability)
        session = recognition.start(commit.turn_id, SpeechMode.STREAM)
        display_text = (
            commit.text if recognized_display_text is None else recognized_display_text
        )
        hypothesis = RecognitionHypothesis(
            (RecognitionAlternative(display_text, display_text, 1.0),)
        )
        partial = recognition.emit(
            session.session_id,
            session.generation,
            RecognitionEventKind.PARTIAL,
            hypothesis,
        )
        boundary = _CommittedTextBoundary()
        partial_synthesis: list[SynthesisEvent] = []
        if boundary.accept(partial, commit):
            partial_synthesis.extend(
                self._synthesize(capability, response, boundary.text, audio)
            )
        final = recognition.emit(
            session.session_id,
            session.generation,
            RecognitionEventKind.FINAL,
            hypothesis,
        )
        if not boundary.accept(final, commit):
            raise FakeVerticalViolation(
                "FINAL_REQUIRED", "the fake recognition final was not accepted"
            )
        synthesis = self._synthesize(capability, response, boundary.text, audio)
        return FakeP1Result(
            boundary.text,
            (partial, final),
            tuple(partial_synthesis),
            synthesis,
            self._route("p1"),
        )

    @staticmethod
    def _synthesize(
        capability: SpeechCapability,
        response: ResponseRef,
        text: str,
        audio: bytes,
    ) -> tuple[SynthesisEvent, ...]:
        synthesis = SynthesisPort(capability)
        synthesis.activate_response(response)
        plan = synthesis.create_render_plan(text, text)
        request = SynthesisRequest(
            f"synthesis-{response.response_id}",
            response,
            "unit-1",
            0,
            len(text),
            plan,
            SpeechMode.STREAM,
        )
        return (
            synthesis.start(request),
            synthesis.emit_chunk(request.request_id, audio),
            synthesis.complete(request.request_id),
        )

    def run_p2(
        self,
        commit: TurnCommit,
        *,
        replace_response: bool,
    ) -> FakeP2Result:
        self._require_track("p2")
        if type(replace_response) is not bool:
            raise FakeVerticalViolation(
                "INVALID_REPLACEMENT_FLAG", "replace_response must be boolean"
            )
        runtime = ConversationRuntime(commit.scope)
        runtime.open_interaction(commit.interaction_id)
        runtime.start_turn(commit.interaction_id, commit.turn_id)
        accepted, _ = runtime.commit_turn(commit)
        if not accepted:
            raise FakeVerticalViolation(
                "TURN_COMMIT_NOT_ACCEPTED", "the fake vertical requires a new commit"
            )
        original, _ = runtime.accept_response(commit.turn_id, "response-original")
        runtime.transition_response(original, ResponseState.GENERATING)

        entered = threading.Event()
        release = threading.Event()
        bridge = AgentBridgePort(max_workers=1)

        def delayed_handler(request):
            entered.set()
            if not release.wait(timeout=2):
                raise FakeVerticalViolation(
                    "FAKE_AGENT_TIMEOUT", "the deterministic Agent was not released"
                )
            return (
                AgentEvent(
                    request.request_id,
                    request.interaction_id,
                    request.turn_id,
                    request.commit_id,
                    0,
                    "agent.output",
                    request.source_provenance,
                    text="deterministic answer",
                    capability="agent.fake",
                ),
            )

        try:
            _, future = bridge.submit("agent-request-1", commit, delayed_handler)
            if not entered.wait(timeout=1):
                raise FakeVerticalViolation(
                    "FAKE_AGENT_NOT_STARTED", "the deterministic Agent did not start"
                )
            non_blocking = not future.done()
            replacement: ResponseRef | None = None
            if replace_response:
                replacement, _ = runtime.accept_response(
                    commit.turn_id, "response-replacement"
                )
            release.set()
            agent_events = future.result(timeout=1)
            effects: list[RuntimeEffect] = []
            stale_blocked = False
            try:
                for effect_type in ("ui.render", "history.append", "audio.enqueue"):
                    effects.append(runtime.apply_output(original, effect_type))
            except ContractViolation as exc:
                if exc.reason != "STALE_RESPONSE_OUTPUT":
                    raise
                effects.clear()
                stale_blocked = True
            return FakeP2Result(
                non_blocking,
                original,
                replacement,
                agent_events,
                tuple(effects),
                stale_blocked,
                runtime.snapshot(),
                self._route("p2"),
            )
        finally:
            release.set()
            bridge.close()

    def run_p3(
        self,
        intent: TaskIntent,
        authorized_scope: ScopeRef,
        *,
        outcome: TerminalOutcome = TerminalOutcome.COMPLETED,
    ) -> FakeP3Result:
        self._require_track("p3alpha")
        command = VoiceTaskBridge().map(intent, authorized_scope)
        if command.operation != "task.create":
            raise FakeVerticalViolation(
                "CREATE_VERTICAL_REQUIRED",
                "the P3alpha fake vertical demonstrates task.create",
            )
        authorization = AuthorizationContext(
            authorized_scope.subject_id,
            authorized_scope,
            frozenset({"task.create", "task.execute", "task.get", "task.events"}),
        )
        core = TaskCore()
        executor = ExecutorPort()
        created = core.execute(command, authorization)
        dispatch = core.snapshot().dispatch_intents[0]
        executor.dispatch(dispatch)
        executor.start(created.attempt_id)
        core.mark_attempt_running(created.task_id, created.attempt_id, authorization)
        executor.finish(created.attempt_id, outcome)
        core.finish_attempt(created.task_id, created.attempt_id, outcome, authorization)
        snapshot = core.snapshot()
        task = snapshot.tasks[0]
        if task.task_id != created.task_id or task.attempt_id != created.attempt_id:
            raise FakeVerticalViolation(
                "TASK_IDENTITY_LOST", "task and attempt identity must remain exact"
            )
        progress = tuple(
            project_work_progress(event)
            for event in snapshot.events
            if event.event_type.startswith("task.")
        )
        return FakeP3Result(
            command,
            created.task_id,
            created.attempt_id,
            progress,
            task,
            (),
            self._route("p3alpha"),
        )

    def _route(self, track: str) -> FakeRouteFact:
        segment, owner, provider = self._TRACKS[track]
        available = getattr(self._availability, track)
        if available:
            return FakeRouteFact(
                segment,
                "demo_substitute",
                owner,
                provider,
                "DETERMINISTIC_FAKE_ONLY",
            )
        return FakeRouteFact(
            segment,
            "unsupported",
            owner,
            None,
            "TRACK_UNAVAILABLE",
        )

    def _require_track(self, track: str) -> None:
        if not getattr(self._availability, track):
            raise FakeVerticalViolation(
                "TRACK_UNAVAILABLE", f"{track} is unavailable in this fake harness"
            )
