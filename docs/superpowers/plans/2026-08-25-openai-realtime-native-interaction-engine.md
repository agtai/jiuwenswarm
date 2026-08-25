# OpenAI Realtime Native Interaction Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and connect a true `OpenAIRealtimeNativeInteractionEngine` that owns one continuous OpenAI Realtime speech-to-speech session while preserving Conversation Runtime, Agent/Tool, Voice–Task/P3, history, presentation, and audio authority.

**Architecture:** Extract one bounded OpenAI Realtime WebSocket/session/finalization kernel from the existing Speech Adapter, then build an independent Native Engine that maps GA Provider events to closed action proposals. A Runtime adapter validates every proposal against exact interaction/turn/response/generation authority; Gateway owns Provider/media transport, AgentServer owns Runtime and business bridges, and a closed internal E2A carrier moves only v1 proposals, admissions, delegate results, cancel facts, and presentation facts between them.

**Tech Stack:** Python 3.11, asyncio, frozen dataclasses, `websockets`, pytest/pytest-asyncio, Ruff, mypy, TypeScript, Node test runner, existing dedicated media WebSocket v1, existing Conversation Runtime/Agent Bridge/Voice–Task Bridge/P3 composition.

**Spec:** `live-voice/architecture/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_2026-08-25.md`

## Global Constraints

- Work only in `C:\Users\admin\Desktop\live voice hx-openai-realtime-native-engine` on `codex/openai-realtime-native-interaction-engine`, based on `1742c1b4e5fa5e7a25a7b41dad9c8eef8453e3cc`.
- Leave `codex/openai-realtime-native-voice@42f448aff7f8af9b0759c59a841f6a57a5792449` untouched; reuse concepts or bounded transport code, never merge the old Speech-only product claim.
- `LIVE_VOICE_INTERACTION_ENGINE=cascade` is the default. Only exact `openai-realtime-native` activates Native. `LIVE_VOICE_NATIVE_REALTIME_MODEL` defaults in one place to `gpt-realtime-2.1-mini` and accepts a bounded explicit server-side override.
- Do not modify existing `TurnCommit` serialization, SQLite schema, P3 command contract, browser dedicated-media v1 wire, or canonical Task/history authority.
- The new Gateway→AgentServer methods are internal, exact, closed members of `live-voice.native-interaction.v1`; document that shared carrier before adding the methods to `ReqMethod` and route allowlists. Browser clients cannot call them and cannot mint their capability token.
- The only browser-visible schema expansion is an exact `native.audio` variant carried by the existing P2 notification RPC; document its fields in D-099 before implementation. It reuses the existing response-bound dedicated-media downlink descriptor and adds no RPC method, media control/frame type, or browser authority.
- Provider exposes only `jiuwen_delegate({request_text})`. It never receives Jiuwen Tool/Task/MCP schemas and never directly mutates Agent, Tool, Task, Store, history, or Audio Device state.
- Direct Native audio is permitted only after Runtime returns an exact `ResponseRef`; every PCM unit is bound to that response/generation and existing dedicated-media downlink/presentation authority.
- Barge-in uses Browser actual played cursor, Runtime exact cancel admission, Provider `response.cancel`, then `conversation.item.truncate`. Stale generation PCM/transcript/done/function/ACK is rejected.
- No silent in-session fallback to Cascade. Activation failure closes the partial Native allocation and returns typed unavailable; Cascade requires a new activation/interaction.
- Provider conversation is not canonical history. Interrupted/partial Native responses never write assistant text. Complete assistant text requires exact transcript provenance, Provider done, complete audio presentation ACK, and current generation.
- Every behavior change follows RED → focused GREEN → regression. Deterministic race tests use futures, barriers, manual clocks, and injected events; no arbitrary sleep.
- Every rejected, stale, malformed, timeout, cancel, replay, cross-scope, and cleanup path that could mutate Agent, Tool, Task, audio, history, presentation, or another scope asserts all forbidden side effects are zero.
- Real Provider/network/device/human checks remain `NOT_RUN` until source/automation and independent Tier-3 review pass. Never print, commit, move, or log an API key, prompt, raw audio, or delegate arguments.
- Local commits are allowed; do not push or update any remote ref.

---

### Task 1: Freeze the internal Native v1 contract, configuration, and carrier re-scope

**Files:**

- Create: `jiuwenswarm/server/live_voice/native_interaction_contract.py`
- Create: `jiuwenswarm/server/live_voice/native_interaction_config.py`
- Create: `tests/unit_tests/live_voice/test_native_interaction_contract.py`
- Create: `tests/unit_tests/live_voice/test_native_interaction_config.py`
- Modify: `live-voice/architecture/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_2026-08-25.md`
- Modify: `live-voice/decisions/DECISIONS.md`
- Modify: `live-voice/STATUS.md`

**Interfaces:**

- Produces: `NativeInteractionBinding`, `NativeTurnCommit`, `NativeDelegateProposal`, `NativePresentationCursor`, and their exact `to_dict()/from_dict()` codecs.
- Produces: `InteractionEngineKind`, `NativeInteractionSelection`, and `select_interaction_engine_environment(environ)`.
- Produces: a recorded closed internal carrier operation set used by Task 5; no `ReqMethod` edit occurs in this task.

- [x] **Step 1: Write failing closed-contract tests**

```python
def test_native_turn_commit_allows_audio_authority_without_transcript() -> None:
    commit = NativeTurnCommit.from_dict(native_commit_payload(audit_transcript=None))
    assert commit.contract_version == "live-voice.native-interaction.v1"
    assert commit.audit_transcript is None
    assert commit.committed_audio_ms == 640


@pytest.mark.parametrize("changed", ["scope", "interaction_id", "provider_event_id"])
def test_native_turn_commit_rejects_changed_replay_binding(changed: str) -> None:
    ledger = NativeContractLedger(capacity=4)
    accepted = NativeTurnCommit.from_dict(native_commit_payload())
    assert ledger.accept_commit(accepted)[0] is True
    payload = native_commit_payload()
    payload[changed] = changed_native_value(changed)
    with pytest.raises(NativeInteractionContractViolation, match="cannot change"):
        ledger.accept_commit(NativeTurnCommit.from_dict(payload))


def test_delegate_rejects_unknown_arguments_before_any_bridge_call() -> None:
    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeDelegateProposal.from_function_call(
            binding=native_binding(),
            provider_event_id="event-4",
            provider_call_id="call-1",
            provider_item_id="item-2",
            arguments='{"request_text":"create a task","tool":"shell"}',
        )
    assert raised.value.reason == "NATIVE_DELEGATE_ARGUMENTS_NOT_CLOSED"
```

- [x] **Step 2: Run the contract tests and capture RED**

Run:

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_native_interaction_contract.py
```

Expected: collection failure because `native_interaction_contract` does not exist.

- [x] **Step 3: Implement frozen bounded dataclasses and codecs**

Use these public signatures:

```python
NATIVE_INTERACTION_CONTRACT_VERSION = "live-voice.native-interaction.v1"
MAX_NATIVE_DELEGATE_UTF8_BYTES = 16_384

@dataclass(frozen=True, slots=True)
class NativeInteractionBinding:
    scope: ScopeRef
    interaction_id: str
    activation_id: str
    activation_generation: int
    correlation_id: str

@dataclass(frozen=True, slots=True)
class NativeTurnCommit:
    contract_version: str
    commit_id: str
    binding: NativeInteractionBinding
    turn_id: str
    provider_session_id: str
    provider_item_id: str
    provider_event_id: str
    causation_id: str
    input_audio_start_ms: int
    input_audio_end_ms: int
    committed_audio_ms: int
    audit_transcript: str | None = None
    audit_transcript_event_id: str | None = None

@dataclass(frozen=True, slots=True)
class NativeDelegateProposal:
    binding: NativeInteractionBinding
    turn_id: str
    response_generation: int
    provider_event_id: str
    provider_call_id: str
    provider_item_id: str
    request_text: str

@dataclass(frozen=True, slots=True)
class NativePresentationCursor:
    response: ResponseRef
    provider_item_id: str
    content_index: int
    audio_end_ms: int
```

All mappings are exact-key; all identities are trimmed, single-line, bounded to 256 characters/1024 UTF-8 bytes; all cursors use `0..MAX_SAFE_INTEGER`; optional transcript fields are both absent or both present; `committed_audio_ms == input_audio_end_ms - input_audio_start_ms`; `request_text` is non-empty and at most `MAX_NATIVE_DELEGATE_UTF8_BYTES`; embedded NUL/control characters are rejected. `NativeContractLedger` retains exact replay by stable identity and rejects changed replay/capacity overflow.

- [x] **Step 4: Add failing environment selection tests**

```python
def test_cascade_is_the_default_and_does_not_require_openai_secret() -> None:
    selection = select_interaction_engine_environment({})
    assert selection.kind is InteractionEngineKind.CASCADE
    assert selection.native_model is None


def test_native_uses_one_default_model_and_accepts_override() -> None:
    default = select_interaction_engine_environment(
        {"LIVE_VOICE_INTERACTION_ENGINE": "openai-realtime-native"}
    )
    override = select_interaction_engine_environment(
        {
            "LIVE_VOICE_INTERACTION_ENGINE": "openai-realtime-native",
            "LIVE_VOICE_NATIVE_REALTIME_MODEL": "gpt-realtime-custom",
        }
    )
    assert default.native_model == "gpt-realtime-2.1-mini"
    assert override.native_model == "gpt-realtime-custom"


def test_unknown_engine_fails_closed_without_cascade_fallback() -> None:
    with pytest.raises(NativeInteractionConfigurationError) as raised:
        select_interaction_engine_environment(
            {"LIVE_VOICE_INTERACTION_ENGINE": "native-ish"}
        )
    assert raised.value.reason == "INTERACTION_ENGINE_UNSUPPORTED"
```

- [x] **Step 5: Run config tests RED, implement selection, then run focused GREEN**

Public implementation:

```python
INTERACTION_ENGINE_ENV = "LIVE_VOICE_INTERACTION_ENGINE"
NATIVE_REALTIME_MODEL_ENV = "LIVE_VOICE_NATIVE_REALTIME_MODEL"
DEFAULT_NATIVE_REALTIME_MODEL = "gpt-realtime-2.1-mini"

class InteractionEngineKind(StrEnum):
    CASCADE = "cascade"
    OPENAI_REALTIME_NATIVE = "openai-realtime-native"

@dataclass(frozen=True, slots=True)
class NativeInteractionSelection:
    kind: InteractionEngineKind
    native_model: str | None
```

Implement exact `NativeTurnCommit.to_dict()`, `NativeTurnCommit.from_dict(value)`, and `select_interaction_engine_environment(environ)` using the validation rules above; the selector reads only the passed mapping so tests never mutate process environment.

Run:

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_native_interaction_contract.py tests/unit_tests/live_voice/test_native_interaction_config.py
```

Expected: all focused tests pass.

- [x] **Step 6: Record the internal carrier before its protocol edit**

Add one design subsection and D-099 stating that exact Gateway→AgentServer request methods are `native.propose`, `native.presentation_ack`, and `native.close`; activation remains the existing P2 activation and returns a Gateway-private capability, while delegate completion is a typed result of `native.propose`, not another request method. The three requests carry only v1 values, require the single-activation capability, are absent from Web handler allowlists, and cannot be called by Browser payload. The same decision freezes one browser-visible `native.audio` variant inside the existing `p2.notification.next` carrier with exact activation binding, `ResponseRef`, audio `PresentationUnit`, and ordinary response-bound dedicated-media downlink descriptor; it adds no new Browser RPC or media v1 frame/control. Tier remains 3, no persistence/schema migration is added, and any broader client schema reopens scope.

- [x] **Step 7: Verify and commit the contract tranche**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m ruff check jiuwenswarm/server/live_voice/native_interaction_contract.py jiuwenswarm/server/live_voice/native_interaction_config.py tests/unit_tests/live_voice/test_native_interaction_contract.py tests/unit_tests/live_voice/test_native_interaction_config.py
git diff --check
git add jiuwenswarm/server/live_voice/native_interaction_contract.py jiuwenswarm/server/live_voice/native_interaction_config.py tests/unit_tests/live_voice/test_native_interaction_contract.py tests/unit_tests/live_voice/test_native_interaction_config.py live-voice/architecture/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_2026-08-25.md live-voice/decisions/DECISIONS.md live-voice/STATUS.md
git commit -m "feat(live-voice): freeze native interaction contract"
```

---

### Task 2: Extract the single OpenAI Realtime session/finalization kernel

**Files:**

- Create: `jiuwenswarm/server/live_voice/openai_realtime_session.py`
- Create: `tests/unit_tests/live_voice/test_openai_realtime_session.py`
- Modify: `jiuwenswarm/server/live_voice/openai_streaming_speech.py`
- Modify: `tests/unit_tests/live_voice/test_openai_streaming_speech.py`

**Interfaces:**

- Consumes: existing socket fake shape `send(str)`, `recv()`, `close()` and OpenAI API-base/secret rules.
- Produces: `OpenAIRealtimeSession`, `OpenAIRealtimeSessionConfig`, `OpenAIRealtimeEvent`, `RealtimeSessionState`, `RealtimeSessionSnapshot`, `RealtimeTransport`, `RealtimeSocket`, `RealtimeSocketFactory`, `RealtimeSocketCleanupOwner`, `default_realtime_socket_factory()`, `official_realtime_url()`, and `validate_official_openai_api_base()`.

- [x] **Step 1: Add Speech characterization tests before extraction**

Freeze existing behavior for connect headers, transcription URL, session update order, receive timeout, duplicate close, receive-task cancellation, cleanup failure precedence, process-control propagation, and secret redaction. Add assertions to `test_openai_streaming_speech.py` that examine fake socket events without depending on private helper names.

Run:

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_openai_streaming_speech.py
```

Expected: characterization suite passes before extraction.

- [x] **Step 2: Write failing kernel tests**

```python
@pytest.mark.asyncio
async def test_session_negotiates_once_and_replays_identical_provider_event() -> None:
    socket = ScriptedRealtimeSocket([
        event("session.created", "evt-1", session={"id": "sess-1"}),
        event("session.updated", "evt-2", session={"id": "sess-1"}),
        event("input_audio_buffer.speech_started", "evt-3", audio_start_ms=20),
        event("input_audio_buffer.speech_started", "evt-3", audio_start_ms=20),
    ])
    session = OpenAIRealtimeSession(realtime_config(), socket_factory=factory(socket))
    await session.open(session_update=native_session_update())
    first = await session.receive_event()
    replay = await session.receive_event()
    assert first == replay
    assert session.snapshot().provider_event_count == 3


@pytest.mark.asyncio
async def test_changed_provider_event_replay_fails_and_close_remains_unique() -> None:
    socket = ScriptedRealtimeSocket([
        event("session.created", "evt-1", session={"id": "sess-1"}),
        event("session.updated", "evt-2", session={"id": "sess-1"}),
        event("response.created", "evt-3", response={"id": "r1"}),
        event("response.created", "evt-3", response={"id": "r2"}),
    ])
    session = OpenAIRealtimeSession(realtime_config(), socket_factory=factory(socket))
    await session.open(session_update=native_session_update())
    await session.receive_event()
    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await session.receive_event()
    assert raised.value.reason == "REALTIME_PROVIDER_EVENT_CONFLICT"
    await session.close()
    await session.close()
    assert socket.close_calls == 1
```

- [x] **Step 3: Run kernel tests RED and implement the minimal owner**

Use this API:

```python
@dataclass(frozen=True, slots=True)
class OpenAIRealtimeSessionConfig:
    api_key: str
    model: str
    api_base: str = "https://api.openai.com/v1"
    connect_timeout_seconds: float = 5.0
    operation_timeout_seconds: float = 30.0
    close_timeout_seconds: float = 0.025
    max_provider_events: int = 4096

class OpenAIRealtimeSession:
    """The unique owner of one bounded Realtime WebSocket lifecycle."""
```

The class implements exact public methods `open(*, session_update) -> None`, `send_event(event_type, payload) -> str`, `receive_event() -> OpenAIRealtimeEvent`, `close() -> RealtimeSessionSnapshot`, and `snapshot() -> RealtimeSessionSnapshot`.

`open()` connects to `wss://api.openai.com/v1/realtime?model=<urlencoded model>`, uses only `Authorization: Bearer`, requires `session.created`, sends one closed `session.update`, then requires matching `session.updated`. `send_event()` assigns monotonic `client_event_00000001` IDs. `receive_event()` parses one bounded JSON object, requires bounded `type` and `event_id`, exact-replays identical events, rejects changed replay and ledger overflow. One lock owns state transition and one close task owns transport finalization. First primary error remains primary; close error is retained in snapshot.

- [x] **Step 4: Make Speech consume the kernel without changing Speech semantics**

Move `RealtimeSocket`, socket factory compatibility, official API-base validation, WebSocket close timeout, realtime URL builder, and unique socket close into the kernel. Configure Speech transcription with `intent=transcription` via `official_realtime_url(intent="transcription")`; Native uses `model=<model>` via the same builder. `_RecognitionSession` holds the kernel transport/session handle; Speech retains recognition conformance and event parsing, and the existing cleanup owner retains only adapter receive tasks and SSE synthesis resources.

- [x] **Step 5: Run focused and characterization GREEN**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_openai_realtime_session.py tests/unit_tests/live_voice/test_openai_streaming_speech.py
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m ruff check jiuwenswarm/server/live_voice/openai_realtime_session.py jiuwenswarm/server/live_voice/openai_streaming_speech.py tests/unit_tests/live_voice/test_openai_realtime_session.py tests/unit_tests/live_voice/test_openai_streaming_speech.py
```

- [x] **Step 6: Commit the shared kernel**

```powershell
git add jiuwenswarm/server/live_voice/openai_realtime_session.py jiuwenswarm/server/live_voice/openai_streaming_speech.py tests/unit_tests/live_voice/test_openai_realtime_session.py tests/unit_tests/live_voice/test_openai_streaming_speech.py
git commit -m "refactor(live-voice): share OpenAI Realtime session kernel"
```

---

### Task 3: Implement the continuous Native Engine and GA event/action mapping

**Files:**

- Create: `jiuwenswarm/server/live_voice/openai_realtime_native_engine.py`
- Create: `tests/unit_tests/live_voice/test_openai_realtime_native_engine.py`
- Modify: `jiuwenswarm/server/live_voice/interaction_engine.py`
- Modify: `tests/unit_tests/live_voice/test_interaction_engine.py`

**Interfaces:**

- Consumes: `OpenAIRealtimeSession`, `NativeInteractionBinding`, `NativeTurnCommit`, `NativeDelegateProposal`, and existing `InteractionAction` vocabulary.
- Produces: `OpenAIRealtimeNativeInteractionEngine.start()`, `offer_audio()`, `next_event()`, `admit_response()`, `send_delegate_result()`, `cancel_response()`, `close()`.

- [x] **Step 1: Write failing direct-audio and multi-turn tests**

```python
@pytest.mark.asyncio
async def test_native_session_direct_audio_does_not_require_transcript_or_bridge() -> None:
    engine, provider, effects = native_engine_script(
        speech_started("e3", 0),
        speech_stopped("e4", 640),
        input_item_committed("e5", "item-u1"),
        response_created("e6", "resp-p1"),
        output_audio_delta("e7", "resp-p1", "item-a1", 0, pcm16=b"\x01\x00"),
        response_done("e8", "resp-p1"),
    )
    await engine.start()
    await drain_engine(engine)
    assert effects.actions == ["LISTEN", "SILENCE", "TURN_COMMIT", "SPEAK"]
    assert effects.audio == [b"\x01\x00"]
    assert effects.agent_calls == effects.task_calls == []
    assert effects.turn_commits[0].audit_transcript is None
    assert provider.connection_count == 1


@pytest.mark.asyncio
async def test_two_turns_reuse_one_session_and_contiguous_audio_input() -> None:
    engine, provider, effects = two_turn_native_engine_script()
    await engine.start()
    await engine.offer_audio(audio_frame(seq=0, sample_cursor=0))
    await engine.offer_audio(audio_frame(seq=1, sample_cursor=480))
    await complete_two_provider_turns(engine)
    assert provider.connection_count == 1
    assert effects.native_turn_ids == ["turn-1", "turn-2"]
    assert provider.appended_audio_sequences == [0, 1]
```

- [x] **Step 2: Write failing malformed/replay/state tests**

Cover unknown event type, missing/extra keys, bad base64, oversized delta, response/item mismatch, event ID changed replay, response before commit, audio before Runtime admission, speech restart before commit producing `REVISE`, queue capacity, operation timeout, remote close, cancel/process-control, and unique close. Snapshot action/audio/delegate sinks before each rejection and assert unchanged.

- [x] **Step 3: Run RED and implement Provider-facing state machine**

Define:

```python
class NativeProviderState(StrEnum):
    NEW = "new"
    CONNECTING = "connecting"
    NEGOTIATING = "negotiating"
    READY = "ready"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    TURN_COMMITTED = "turn_committed"
    RESPONSE_PENDING = "response_pending"
    SPEAKING = "speaking"
    DELEGATING = "delegating"
    DELEGATE_WAIT = "delegate_wait"
    CANCELLING = "cancelling"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"

@dataclass(frozen=True, slots=True)
class NativeAudioOutput:
    provider_event_id: str
    provider_response_id: str
    provider_item_id: str
    content_index: int
    sequence: int
    pcm16: bytes
    response: ResponseRef

@dataclass(frozen=True, slots=True)
class NativeEngineEvent:
    action: InteractionAction | None = None
    turn_commit: NativeTurnCommit | None = None
    audio: NativeAudioOutput | None = None
    delegate: NativeDelegateProposal | None = None
    provider_done: "NativeProviderDone" | None = None

@dataclass(frozen=True, slots=True)
class NativeProviderDone:
    provider_event_id: str
    provider_response_id: str
    response: ResponseRef
    completed: bool
    transcript: str | None
    transcript_event_id: str | None
```

Session update uses audio input/output, `semantic_vad`, `create_response=true`, `interrupt_response=false`, and one strict `jiuwen_delegate` function. Provider `speech_started` → `LISTEN` and optional STOP candidate, `speech_stopped` → `SILENCE`, committed input item → `TURN_COMMIT`, response created → `SPEAK` candidate, output delta → fenced `NativeAudioOutput`, function arguments done → `DELEGATE`, speech restart before commit → `REVISE`, cancelled/done → observations only. Unknown events outside an explicit harmless allowlist fail closed.

- [x] **Step 4: Add Runtime admission hooks to the Engine**

`admit_response(provider_response_id, response_ref)` binds Provider response to exact Runtime ref once; changed replay fails. Audio before admission remains buffered only up to the bounded queue and is not released; on admission it is released in Provider sequence. `send_delegate_result(call_id, response_ref, output)` requires current delegate wait and sends one `conversation.item.create` function output followed by `response.create`. No result text is logged.

- [x] **Step 5: Run focused GREEN and Cascade interaction regressions**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_openai_realtime_native_engine.py tests/unit_tests/live_voice/test_interaction_engine.py
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m ruff check jiuwenswarm/server/live_voice/openai_realtime_native_engine.py jiuwenswarm/server/live_voice/interaction_engine.py tests/unit_tests/live_voice/test_openai_realtime_native_engine.py tests/unit_tests/live_voice/test_interaction_engine.py
```

- [x] **Step 6: Commit the continuous Engine**

```powershell
git add jiuwenswarm/server/live_voice/openai_realtime_native_engine.py jiuwenswarm/server/live_voice/interaction_engine.py tests/unit_tests/live_voice/test_openai_realtime_native_engine.py tests/unit_tests/live_voice/test_interaction_engine.py
git commit -m "feat(live-voice): implement native Realtime interaction engine"
```

---

### Task 4: Bind Native proposals to Conversation Runtime fences and history eligibility

**Files:**

- Create: `jiuwenswarm/server/live_voice/native_interaction_runtime.py`
- Create: `tests/unit_tests/live_voice/test_native_interaction_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/conversation_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_conversation_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/conversation_runtime_loop.py`
- Modify: `tests/unit_tests/live_voice/test_conversation_runtime_loop.py`
- Modify: `jiuwenswarm/server/live_voice/presentation_ledger.py`
- Create: `tests/unit_tests/live_voice/test_presentation_ledger.py`

**Interfaces:**

- Consumes: Engine events and existing Runtime loop operations.
- Produces: `NativeInteractionRuntimeOwner`, `NativeResponseAdmission`, `NativeBargeAdmission`, `NativeHistoryAdmission`.

- [x] **Step 1: Write failing authority and stale-audio tests**

```python
@pytest.mark.asyncio
async def test_response_created_requires_runtime_admission_before_audio_release() -> None:
    owner, engine, runtime, media = active_native_runtime()
    await owner.accept_turn(native_commit("turn-1"))
    admission = await owner.accept_provider_response("provider-r1", "native-r1")
    assert admission.response.response_generation == 1
    assert engine.admissions == [("provider-r1", admission.response)]
    assert await owner.accept_audio(native_audio(admission.response, seq=0)) is True
    assert media.frames == [(admission.response, 0)]


@pytest.mark.asyncio
async def test_stale_generation_audio_and_done_have_zero_effect() -> None:
    owner, _engine, runtime, media = active_native_runtime()
    old = await admitted_native_response(owner, provider_response_id="provider-r1")
    await admitted_native_response(owner, provider_response_id="provider-r2")
    before = runtime.snapshot()
    assert await owner.accept_audio(native_audio(old.response, seq=0)) is False
    assert await owner.accept_done(native_done(old.response)) is False
    assert runtime.snapshot() == before
    assert media.frames == []
```

- [x] **Step 2: Add a Native audio history policy without weakening text history**

Extend `HistorySurfacePolicy` with `NATIVE_AUDIO`. A Native audio `PresentationUnit` carries content reference/digest and PCM cursor, while complete assistant transcript is held separately in `NativeInteractionRuntimeOwner`. `PresentationLedger` marks the response presentation complete only after all contiguous audio units ACK. It returns history eligibility, not text. Existing `TEXT` and `AUDIO` behavior remains byte-for-byte compatible.

- [x] **Step 3: Implement Runtime owner methods**

```python
@dataclass(frozen=True, slots=True)
class NativeResponseAdmission:
    provider_response_id: str
    response: ResponseRef

@dataclass(frozen=True, slots=True)
class NativeBargeAdmission:
    applied: bool
    response: ResponseRef
    cursor: NativePresentationCursor
    cancel_command_id: str

@dataclass(frozen=True, slots=True)
class NativeHistoryAdmission:
    response: ResponseRef
    transcript: str
    presented_at: str

class NativeInteractionRuntimeOwner:
    """The only adapter allowed to turn Native proposals into Runtime writes."""
```

The owner implements `start()`, `accept_turn(commit)`, `accept_provider_response(provider_response_id, response_id)`, `accept_audio(output)`, `barge_in(*, action_id, response, cursor)`, `accept_provider_done(observation)`, `acknowledge_audio(ack)`, and `close()`. `accept_turn()` opens/starts the exact turn and retains Native commit without converting it to standard `TurnCommit`. `accept_provider_response()` calls Runtime `accept_response` with `history_policy=HistorySurfacePolicy.NATIVE_AUDIO`. `accept_audio()` produces/enqueues one existing PresentationUnit and media effect only if the ref is current and unfenced. `barge_in()` first calls Runtime exact barge/cancel and only then returns permission for Provider cancel/truncate. `accept_provider_done()` does not write history. `acknowledge_audio()` yields assistant history only when done + complete presentation + current generation + exact complete transcript provenance are all true.

- [x] **Step 4: Write and pass barge/cancel/history races**

Cover browser local stop before Provider speech-start, Provider speech-start before local cursor, duplicate cancel, cancel vs done, done vs final ACK, close during delegate wait, stale transcript, missing transcript, partial presentation, complete presentation, and history writer failure. Assert old PCM and history remain zero after fence.

Task 4 closes every race expressible at the Runtime-owner boundary, including both cancel/done orders, missing or ahead playback cursors, ACK-before-done, stale generations and transcripts, partial presentation, and exact replay. The transport-owned browser speech-start/cursor ordering remains assigned to Task 6, close during a delegate wait remains assigned to Task 7, and history-writer failure remains assigned to Task 8 where this task's immutable eligibility value is consumed. Those candidate acceptance cases are deferred to their owning boundaries, not scoped out.

- [x] **Step 5: Run GREEN and commit**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_native_interaction_runtime.py tests/unit_tests/live_voice/test_conversation_runtime_loop.py tests/unit_tests/live_voice/test_presentation_ledger.py
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m ruff check jiuwenswarm/server/live_voice/native_interaction_runtime.py jiuwenswarm/server/live_voice/conversation_runtime_loop.py jiuwenswarm/server/live_voice/presentation_ledger.py tests/unit_tests/live_voice/test_native_interaction_runtime.py
git add jiuwenswarm/server/live_voice/native_interaction_runtime.py jiuwenswarm/server/live_voice/conversation_runtime_loop.py jiuwenswarm/server/live_voice/presentation_ledger.py tests/unit_tests/live_voice/test_native_interaction_runtime.py tests/unit_tests/live_voice/test_conversation_runtime_loop.py tests/unit_tests/live_voice/test_presentation_ledger.py
git commit -m "feat(live-voice): enforce native Runtime audio fences"
```

---

### Task 5: Add the closed Gateway–AgentServer authority carrier and Native activation

**Files:**

- Modify: `jiuwenswarm/common/schema/message.py`
- Create: `jiuwenswarm/server/live_voice/native_interaction_carrier.py`
- Create: `tests/unit_tests/live_voice/test_native_interaction_carrier.py`
- Modify: `jiuwenswarm/server/live_voice/native_interaction_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_native_interaction_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_agent_conversation_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py`
- Modify: `tests/unit_tests/live_voice/test_product_p2_interaction_adapter.py`
- Create: `jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py`
- Create: `tests/unit_tests/gateway/test_native_interaction_runtime_client.py`
- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Modify: `tests/unit_tests/live_voice/test_product_composition_registry.py`
- Modify: `jiuwenswarm/server/agent_ws_server.py`
- Modify: `tests/unit_tests/agentserver/test_live_voice_p3_route.py`
- Modify: `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`
- Modify: `tests/unit_tests/gateway/test_dedicated_media_registration.py`
- Modify: `jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py`
- Modify: `jiuwenswarm/gateway/channel_manager/web/web_connect.py`
- Modify: `tests/unit_tests/channel/test_web_channel_ws_sessions.py`
- Modify: `jiuwenswarm/gateway/app_gateway.py`
- Modify: `tests/unit_tests/test_app_web_handlers.py`

**Interfaces:**

- Consumes: v1 codecs, `NativeInteractionRuntimeOwner`, existing authenticated P2 activation binding, `AgentServerClient.send_request()`.
- Produces: exact internal ReqMethods and a server-minted activation capability consumed only by Gateway.

- [x] **Step 1: Write failing carrier authorization tests**

```python
@pytest.mark.asyncio
async def test_gateway_native_proposal_requires_server_minted_activation_capability() -> None:
    client, agent = runtime_client_fixture()
    with pytest.raises(NativeRuntimeClientError) as raised:
        await client.propose(binding=native_binding(), capability="browser-value", event=listen_event())
    assert raised.value.reason == "NATIVE_RUNTIME_CAPABILITY_REJECTED"
    assert agent.requests == []


@pytest.mark.asyncio
async def test_internal_native_methods_are_absent_from_browser_allowlist() -> None:
    assert set(NATIVE_INTERNAL_REQ_METHODS).isdisjoint(WEB_CLIENT_REQ_METHODS)
```

- [x] **Step 2: Add exact internal methods and codec parity tests**

Add enum members:

```text
live_voice.internal.native.propose
live_voice.internal.native.presentation_ack
live_voice.internal.native.close
```

They are accepted only on Gateway→AgentServer E2A. Add them to internal server dispatch, never Web registered/forwarded/allowlisted method sets. Each request contains exact v1 payload plus a random 256-bit capability returned only inside the Gateway-observed P2 activation response; Browser response transformation removes the capability before sending the response to JavaScript.

- [x] **Step 3: Implement AgentServer Native route ownership**

On P2 activation with exact `interaction_engine="openai-realtime-native"`, create one `NativeInteractionRuntimeOwner`, mint one capability, and return a Gateway-only activation descriptor through the existing response observer seam. Cascade activation remains unchanged. Exact replay returns the same descriptor; changed activation generation closes the predecessor before replacement. Native internal handlers validate capability with constant-time comparison, scope/interaction/activation generation, request replay ID/fingerprint, and current route lease before any Runtime call.

- [x] **Step 4: Implement Gateway client and activation wiring**

`GatewayNativeInteractionRuntimeClient` constructs E2A envelopes with bounded request IDs and calls `AgentServerClient.send_request`; it validates exact result keys and never logs payload/capability. `app_web_handlers.py` selects the Engine once from environment, creates the client only for Native, and injects it into `DedicatedMediaProductRegistry`. Unknown/failed Native selection keeps Native unavailable and never installs Cascade as a fallback for that activation.

- [x] **Step 5: Test lifecycle, replay, timeout, and cleanup**

Cover activation replay/conflict, wrong capability/scope/session/connection/generation, client timeout, AgentServer unavailable, Runtime failure, close replay, Gateway shutdown, AgentServer route close, and response observer error. Each negative case asserts no Engine socket, Runtime turn/response, Agent/Task call, media ticket, history, or retained registry entry.

- [x] **Step 6: Run GREEN and commit**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/gateway/test_native_interaction_runtime_client.py tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/test_app_web_handlers.py
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m ruff check jiuwenswarm/common/schema/message.py jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py jiuwenswarm/server/live_voice/product_composition_registry.py jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py jiuwenswarm/gateway/app_gateway.py
git add jiuwenswarm/common/schema/message.py jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py jiuwenswarm/server/live_voice/product_composition_registry.py jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py jiuwenswarm/gateway/app_gateway.py tests/unit_tests/gateway/test_native_interaction_runtime_client.py tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/test_app_web_handlers.py
git commit -m "feat(live-voice): bind native Gateway Runtime authority"
```

---

### Task 6: Connect continuous Provider audio to dedicated media and Browser playout

**Files:**

- Modify: `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`
- Modify: `jiuwenswarm/gateway/live_voice/dedicated_media_route.py`
- Modify: `tests/unit_tests/gateway/test_dedicated_media_registration.py`
- Modify: `tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceStreamingSpeech.test.mjs`
- Create: `jiuwenswarm/channels/web/frontend/tests/liveVoiceNativeInteraction.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**

- Consumes: Engine audio events, Runtime admissions, existing uplink/downlink media v1, existing Product P1 audio owner.
- Produces: Native activation descriptor and per-response ordinary dedicated-media downlink tickets; no new browser media wire type.

- [ ] **Step 1: Write failing Gateway direct-audio journey test**

```python
@pytest.mark.asyncio
async def test_native_audio_reuses_uplink_session_and_allocates_fenced_downlink() -> None:
    registry, provider, runtime = native_media_registry()
    uplink = activate_and_consume_native_uplink(registry)
    registry.accept_streaming_frame(uplink, media_frame(seq=0))
    provider.emit(input_item_committed("e5", "item-u1"))
    provider.emit(response_created("e6", "provider-r1"))
    runtime.admit_response("provider-r1", response_ref(generation=1))
    provider.emit(output_audio_delta("e7", "provider-r1", "item-a1", 0, b"\x01\x00"))
    downlink = registry.take_native_downlink(response_ref(generation=1))
    assert downlink.binding.direction is MediaDirection.DOWNLINK
    assert collect_downlink_pcm(downlink) == b"\x01\x00"
    assert runtime.agent_calls == runtime.task_calls == []
```

- [ ] **Step 2: Implement Native media ownership in Gateway registry**

For a Native activation, consuming the existing uplink ticket starts one Engine session and feeds each accepted PCM frame to `offer_audio()` after exact media binding/sequence validation. Engine actions are sent through `GatewayNativeInteractionRuntimeClient`. On Runtime response admission, allocate an existing response-bound dedicated-media downlink record and expose its ordinary descriptor through the existing P2 notification pull. Audio delta is framed as existing media PCM frames only after response/generation admission. Queue capacity and downlink backpressure close that response, not the whole process.

- [ ] **Step 3: Extend Product P1 route without changing Cascade orchestration**

Activation response accepts an optional exact native descriptor:

```ts
export type ProductP1InteractionEngine = 'cascade' | 'openai-realtime-native';

export interface NativeInteractionActivation {
  readonly contract_version: 'live-voice.native-interaction.v1';
  readonly engine: 'openai-realtime-native';
  readonly model: string;
}
```

Add this exact package script so the focused TypeScript owner and both route tests compile together:

```json
"test:live-voice-native-interaction": "tsc src/features/live-voice/formal/productP1VoiceRoute.ts --target ES2020 --module ES2020 --moduleResolution Bundler --rootDir src --outDir node_modules/.cache/live-voice-integrated-web --lib ES2020,DOM --skipLibCheck --noEmitOnError --strict --noUnusedLocals --noUnusedParameters && esbuild src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts --bundle --platform=node --format=esm --outfile=node_modules/.cache/live-voice-browser-dedicated-media/browserDedicatedMediaRoute.mjs && node --test tests/liveVoiceNativeInteraction.test.mjs tests/productP1VoiceRoute.test.mjs"
```

Cascade continues `stopAndRecognize()` → product submit → `playAgentText()`. Native keeps the capture route open across turns, does not call recognition final or batch/streaming TTS for direct answers, polls existing P2 notifications for response-bound downlink descriptors, and feeds those frames to the existing Audio I/O playout/ACK path. Engine choice is read from server activation, not browser local storage or query input.

- [ ] **Step 4: Implement exact played-cursor barge-in**

When Native speech-start arrives during playout, Product P1 stops the exact current Audio I/O response, obtains its confirmed contiguous frame cursor, sends the existing downlink playback-stop receipt, and includes the derived `NativePresentationCursor` in the internal presentation/cancel call. Gateway sends `response.cancel` and then `conversation.item.truncate` only after Runtime admission. Stale or missing cursor closes/fences output without an invented truncate position.

- [ ] **Step 5: Test stale PCM, replay, backpressure, close, and frontend branch isolation**

Cover old generation delta after replacement, delta after cancel, response done before last ACK, zero/last cursor, duplicate truncate, uplink reconnect attempt, remote Provider close, browser Exit, downlink attach failure, backpressure, Native descriptor malformed, Cascade descriptor absent, and Native path proving zero recognition-final/synthesis calls. Use fake socket callbacks/manual schedulers in Node; no timed sleep.

- [ ] **Step 6: Run Python/Node GREEN and commit**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-native-interaction
git add jiuwenswarm/gateway/live_voice/dedicated_media_registration.py jiuwenswarm/gateway/live_voice/dedicated_media_route.py tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts jiuwenswarm/channels/web/frontend/tests/liveVoiceStreamingSpeech.test.mjs jiuwenswarm/channels/web/frontend/tests/liveVoiceNativeInteraction.test.mjs jiuwenswarm/channels/web/frontend/package.json
git commit -m "feat(live-voice): connect native audio media path"
```

---

### Task 7: Route safe delegate proposals through Agent Bridge and Voice–Task/P3

**Files:**

- Modify: `jiuwenswarm/server/live_voice/native_interaction_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Modify: `tests/unit_tests/live_voice/test_native_interaction_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_agent_bridge_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_voice_task_bridge.py`
- Modify: `tests/unit_tests/live_voice/test_product_composition_registry.py`

**Interfaces:**

- Consumes: validated `NativeDelegateProposal`, existing unified committed-input resolver, Agent Bridge, Voice–Task Bridge/P3, canonical results.
- Produces: `NativeDelegateResult` returned through Task 5 carrier and expressed in a new Runtime-admitted Provider response.

- [ ] **Step 1: Write failing Agent/Tool and Task delegate tests**

```python
@pytest.mark.asyncio
async def test_delegate_uses_existing_agent_bridge_and_returns_canonical_result() -> None:
    owner, agent, task, provider = native_delegate_runtime()
    proposal = delegate_proposal("Use the weather tool for Paris")
    result = await owner.delegate(proposal)
    assert agent.standard_turn_commits == [result.turn_commit]
    assert agent.tool_calls == ["weather"]
    assert task.commands == []
    assert provider.function_outputs == [(proposal.provider_call_id, result.canonical_text)]


@pytest.mark.asyncio
async def test_background_task_uses_only_voice_task_bridge_p3() -> None:
    owner, agent, task, provider = native_delegate_runtime()
    proposal = delegate_proposal("Create a background task to analyze the repository")
    result = await owner.delegate(proposal)
    assert task.standard_turn_commits == [result.turn_commit]
    assert task.p3_commands == ["task.create"]
    assert agent.tool_calls == []
    assert provider.function_outputs == [(proposal.provider_call_id, result.canonical_text)]
```

- [ ] **Step 2: Convert only validated delegate text to standard TurnCommit**

Define `NativeDelegateResult(turn_commit: TurnCommit, canonical_text: str, route: UnifiedCommittedInputRoute, response: ResponseRef)`. Use a deterministic commit ID derived from scope/interaction/turn/provider call/request digest. Add extensions/provenance using existing supported fields only; do not change v2 wire. Invoke the existing unified committed-input resolver once. Dialogue route uses the existing Agent Bridge runtime; background route uses existing Voice–Task Bridge/P3. No second keyword classifier is added.

- [ ] **Step 3: Return Jiuwen result to Provider under a new response generation**

The Agent/Task canonical result is bounded and sanitized, then Task 4 Runtime owner accepts a new Native response before Task 3 sends `function_call_output` and `response.create`. Provider audio from this response remains fenced. Result production does not imply presentation; only final audio ACK settles presented history.

- [ ] **Step 4: Test forbidden proposals and zero side effects**

Cover unknown function, duplicate/changed call ID, invalid JSON, unknown args, empty/oversized/control-character request, stale turn/generation, closed route, Agent failure, Tool confirmation requirement, Task clarification/unsupported/conflict, bridge timeout, result overflow, function output send failure, and cancel during bridge work. Snapshot Agent calls, Tool effects, Task Store/Event/outbox, Runtime responses, Provider sends, media, and history before each rejected path.

- [ ] **Step 5: Run GREEN and commit**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_native_interaction_runtime.py tests/unit_tests/live_voice/test_agent_bridge_runtime.py tests/unit_tests/live_voice/test_voice_task_bridge.py tests/unit_tests/live_voice/test_product_composition_registry.py
git add jiuwenswarm/server/live_voice/native_interaction_runtime.py jiuwenswarm/server/live_voice/product_composition_registry.py tests/unit_tests/live_voice/test_native_interaction_runtime.py tests/unit_tests/live_voice/test_agent_bridge_runtime.py tests/unit_tests/live_voice/test_voice_task_bridge.py tests/unit_tests/live_voice/test_product_composition_registry.py
git commit -m "feat(live-voice): route native delegates through Jiuwen bridges"
```

---

### Task 8: Close configuration, history, cleanup, Cascade regressions, and candidate review

**Files:**

- Modify: `jiuwenswarm/server/live_voice/__init__.py`
- Modify: `jiuwenswarm/gateway/live_voice/__init__.py`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`
- Modify: `live-voice/STATUS.md`
- Modify: `live-voice/architecture/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_2026-08-25.md`
- Create: `live-voice/reviews/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_REVIEW_2026-08-25.md`
- Create: `live-voice/evidence/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_EVIDENCE_20260825.md`

**Interfaces:**

- Consumes: all prior tasks.
- Produces: one frozen clean local candidate with source/automation review credit and an explicit real-probe disposition.

- [ ] **Step 1: Run the full focused Native matrix**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_native_interaction_contract.py tests/unit_tests/live_voice/test_native_interaction_config.py tests/unit_tests/live_voice/test_openai_realtime_session.py tests/unit_tests/live_voice/test_openai_realtime_native_engine.py tests/unit_tests/live_voice/test_native_interaction_runtime.py tests/unit_tests/gateway/test_native_interaction_runtime_client.py tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py
```

Record exact counts, duration, and any excluded test with reason.

- [ ] **Step 2: Run affected cumulative Python regressions**

```powershell
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m pytest -q tests/unit_tests/live_voice/test_interaction_engine.py tests/unit_tests/live_voice/test_conversation_runtime.py tests/unit_tests/live_voice/test_conversation_runtime_loop.py tests/unit_tests/live_voice/test_presentation_ledger.py tests/unit_tests/live_voice/test_agent_bridge.py tests/unit_tests/live_voice/test_agent_bridge_runtime.py tests/unit_tests/live_voice/test_voice_task_bridge.py tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py tests/unit_tests/test_app_web_handlers.py
```

- [ ] **Step 3: Run frontend, static, format, compile, and diff gates**

```powershell
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-native-interaction
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-browser-dedicated-media
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-conversation-runtime
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-product-composition-contract
npm --prefix jiuwenswarm/channels/web/frontend run build
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m ruff check jiuwenswarm/server/live_voice jiuwenswarm/gateway/live_voice tests/unit_tests/live_voice tests/unit_tests/gateway
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m ruff format --check jiuwenswarm/server/live_voice jiuwenswarm/gateway/live_voice tests/unit_tests/live_voice tests/unit_tests/gateway
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m mypy --follow-imports=skip --ignore-missing-imports jiuwenswarm/server/live_voice/native_interaction_contract.py jiuwenswarm/server/live_voice/native_interaction_config.py jiuwenswarm/server/live_voice/openai_realtime_session.py jiuwenswarm/server/live_voice/openai_realtime_native_engine.py jiuwenswarm/server/live_voice/native_interaction_runtime.py jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py
& 'C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe' -m compileall -q jiuwenswarm/server/live_voice jiuwenswarm/gateway/live_voice
git diff --check
```

- [ ] **Step 4: Freeze and inspect the exact candidate**

Run `git status --short --branch`, `git rev-parse HEAD`, `git diff HEAD^`, list all commits from `13a1a1bf` to HEAD, and record the exact test manifest. Create a detached sibling worktree at the candidate commit only after the implementation worktree is clean. The detached candidate must have no machine-private env or copied runtime data.

- [ ] **Step 5: Perform one cold independent Tier-3 review**

Review the complete candidate once against the design and user request: Native speech-to-speech direct path, continuous session, GA event mapping, Runtime authority/fences, barge/truncate cursor, delegate Agent/Task firewall, history/presentation, config/no fallback, resource finalization, security/privacy, positive tests, negative zero effects, and Cascade regression. Record every finding as Critical/Important/Minor with exact file/line and required evidence. Fix root causes on the implementation branch; run only affected confirmations unless the fix changes an architecture boundary, then rerun cumulative gates. Follow-up review must close `C0/I0`.

- [ ] **Step 6: Synchronize documentation without overclaiming**

STATUS must say source/automation PASS only if the recorded gates pass. The evidence document records exact HEAD, commands/results, requirement-to-test mapping, reusable extraction, replaced Speech assumptions, exclusions, and real-probe readiness. The review document records candidate/finding/fix/follow-up facts. Real Provider/device/human remains `NOT_RUN` unless actually executed after review with the repository secret seam.

- [ ] **Step 7: Commit the candidate closeout and verify clean state**

```powershell
git add live-voice/STATUS.md live-voice/architecture/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_2026-08-25.md live-voice/reviews/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_REVIEW_2026-08-25.md live-voice/evidence/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_EVIDENCE_20260825.md
git commit -m "docs(live-voice): record native interaction candidate"
git status --short --branch
git log --oneline --decorate 1742c1b4e5fa5e7a25a7b41dad9c8eef8453e3cc..HEAD
```

Expected: clean local branch, no upstream, no push. The final report includes the absolute worktree, branch, baseline, final HEAD, every commit hash/message/purpose, reuse/rewrite inventory, Native/Cascade boundary, authority/resource conclusion, exact verification, exclusions, real-probe disposition, and the remaining credential/device/human Gate.
