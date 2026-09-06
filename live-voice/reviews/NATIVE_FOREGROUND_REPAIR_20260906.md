# Native foreground interruption, failure and state repair

## Authorized boundary

The user authorized the five repairs diagnosed from the 12:49 project-material
request and a controlled redeployment when needed. Native uses Provider-confirmed
speech starts and its existing response/playout interruption, not Cascade's
speculative ASR classifier. A new utterance must be observable while semantics or
an Agent delegate is pending. Only the superseded foreground work/output is
cancelled or fenced; an admitted durable business Task remains independently owned.

Owners: Native Engine, Gateway delivery, Conversation Runtime/semantic admission,
and the existing integrated Web voice surface. This is Tier 3 at the narrow
activation-bound notification and interruption seam, Tier 2 for execution lifetime,
deadline and recovery. No new public RPC, Task authority, classifier, provider/model
configuration, history policy, or data migration is intended.

Implementation:

- Keep input/control delivery responsive while a retained Native delegate runs.
  Provider-confirmed interruption targets the exact activation/source response;
  cancelled/late delegates never create a successor answer. Use an explicit
  foreground cancellation signal, preserving ordinary caller-disconnect replay.
- Cancel read-only semantic work and the exact foreground Agent round. Once a
  durable Task operation is admitted, preserve its normal reconciliation and only
  retire the old foreground delivery. Never infer Task cancellation from speech.
- Replace the 25/28-second whole-Agent limit with coordinated bounded Native
  Agent/transport budgets; retain timeout cleanup and exact failure reasons.
- Project bounded request state through the existing Native notification route.
  Processing is independent of microphone capture, failure survives capture
  recovery, and interrupted/old generations cannot overwrite the next turn.
- Add metadata-only lifecycle/outcome diagnostics using existing IDs and bounded
  collectors; no raw audio, prompts, document content or secrets in diagnostics.

## Integration scope checkpoint

Independent review identified a completion/admission race and Provider-send
cancellation gaps. The repair therefore also owns the internal Native delegate
result settlement vocabulary (`completed`, or Task-receipt-only `interrupted` /
`failed`). This remains Tier 3 at the existing internal route: a settled Task
receipt uses the original response solely for discovery, never authorizes speech,
ACK, history, or a new response. Task origin is registered when its formal receipt
arrives, independently of the cancellable Agent acknowledgement. This is required
to preserve the already accepted durable-Task boundary; no new public RPC or Task
operation is introduced.

## Acceptance and exclusions

Prove project-style Agent work can exceed the old deadline and finish; interrupt
during semantics and Agent/tool waiting; admit the next utterance without waiting
for the old result; reject stale/wrong-scope/replayed controls without extra Agent,
Tool, Task, history or audio effects; fence late success/failure; preserve existing
playout/cursor and Task-discovery behavior; show truthful processing/failure state;
and prove failure recovery never replays a committed business request.

Use focused Python/Node integration regressions, frontend build, a cold complete
diff review and independent review under root TESTING.md. Exercise the real Agent
boundary in an isolated project before controlled startup. Physical headset
perception remains human acceptance unless actually exercised. No full performance
optimization, model changes, broad Task redesign or remote Git update is included.

## Evidence

Baseline: `d4b4c0b9c1f6edc16f9c2bab1541c47ceb2befb3`. Existing incident evidence is
retained privately under `logs/realtime-incident-web_1a07655f3a5_938567d63534/`.
Private verification artifacts below are under `logs/native-foreground-repair/`.

### Implemented behavior and review

- The Gateway retains delegate operations separately from ordered input/control
  delivery. Only Provider-confirmed speech stops the exact foreground. A completed
  function-call response remains a valid source for its retained delegate; a
  cancelled, stale or foreign source cannot acquire that authority.
- The Native owner retains source/successor interruption fences. Queued obsolete
  response creation is removed; in-flight Provider sends settle and late created
  responses are cancelled without speech. Provider cancellation is serialized and
  shares an exact receipt between processing STOP and playback cursor truncation.
- Semantic work and the exact Agent round respond to the foreground signal.
  Durable dispatch is not cancelled. A completed Task receipt is projected once
  for authenticated discovery even when its acknowledgement is interrupted or
  fails; the result carries no new speech, history or ACK authority.
- Default Agent deadline is 120 seconds (supported ceiling 180); Native delegate
  transport is 300 seconds, covering semantic admission (100), Agent (180) and
  settlement overhead (20). Existing shorter media/control deadlines remain.
  Timeout cleanup and the original `NATIVE_DELEGATE_AGENT_TIMEOUT` reason remain.
- `native.request_state` carries closed, bounded, exact-activation state with a
  monotonic sequence. Processing stays visible while capture remains active;
  failure persists until the next turn. Old/interrupted audio cannot revive an
  answer or stall notification polling. Native failures do not become STT errors.
- Metadata-only `native_foreground`, `native_request_state` and Agent round spans
  retain phase, elapsed/remaining budget, IDs and actual terminal outcome. Existing
  diagnostics/export remain bounded. Existing Native transcript-to-chat delivery
  still requires its normal presentation/ACK boundary.

Cold scoped diff review and independent read-only review completed. Findings
fixed and rechecked: completed-source admission races, in-flight/queued Provider
send cancellation, the send-before-created gap, allocated successor cancellation,
Task receipt/origin loss, malformed STOP mutation, ignored-audio poll starvation,
and duplicate Provider cancellation across processing and playback. The final
review found no remaining blocker in these seams.

### Automated verification

Commands use the repository virtualenv and an isolated `JIUWENSWARM_DATA_DIR`.
Python invocations use `-o addopts= -q --tb=short` and distinct ignored basetemp
paths. Repeated targeted results overlap and must not be added as unique tests.

| Boundary / command | Evidence and result |
|---|---|
| Native Engine, Agent Runtime, Native owner, Registry, Gateway delivery and Native client: six affected files with `-k 'native and not native_available_result_uses_toolless_agent_delegate and not native_delegate_late_done_and_ack_keep_successor_fence_authoritative and not native_background_delegate_clarifies_or_rejects_without_task_effect'` | `native-final.txt`: 216 passed; four baseline failures explicitly excluded |
| Full Native Engine and Native client after import/retirement follow-up | `postreview.txt`: 107 passed |
| Full Native Engine after shared Provider cancel receipt repair | `cancel-receipts.txt`: 86 passed; audio-present and zero-sample concurrent cursor/STOP each send one cancel and one truncate |
| Full Agent Bridge, profiling and Gateway audio diagnostics | `common-final.txt`: 64 passed |
| `npm run test:live-voice-native-interaction` | `frontend-native-final.txt`: 128 passed |
| Mounted React lifecycle/activity scenarios | `frontend-mounted-final.txt`: 2 passed; processing, failure, next turn, stale state and zero old-audio/history effects |
| `npm run test:live-voice-integrated-web` | `frontend-integrated-final.txt`: 605 passed, 25 failed, 1 skipped; comparison below |
| `npm run build:live-voice` | `build-final.txt`: TypeScript and Vite passed; existing bundle-size warning retained |
| Changed Python syntax/undefined-name checks | `ruff-final.txt`: `ruff check --select F821,F822,F823,E9` passed |

Positive and negative scenarios include delayed Agent completion beyond 25 seconds,
interruption during semantic/Agent waits, exact Task receipt settlement, next-input
responsiveness, malformed/foreign/stale STOP with zero cancellation or ledger
mutation, replay without duplicate effects, stale success/failure suppression,
Provider send barriers, audio cursor preservation and truthful mounted UI state.

The delayed 26-second Agent completion is a controlled real-Harness regression,
not a real-Provider latency measurement. Task-dispatch interruption tests use a
controlled formal dispatch receipt; they do not claim a complete real durable
Task/restart/audio journey.

### Baseline comparison and limitations

A detached worktree at the exact baseline reproduces four existing Registry
failures (`backend-baseline.txt`): available-result route expectation, late
source/done expectation, and two old background-route expectations. They were
not rewritten or silently counted as passing.

The wider Web suite at baseline has 605 passed, 24 failed, 1 skipped
(`frontend-integrated-baseline.txt`). All 24 failures are also present in the
current run. The extra failure is an unchanged first-frame diagnostic test's
10-`setImmediate` wait (successor hash callback had not arrived); its source and
adapter have zero diff, and it passes in isolation on the current bundle
(`frontend-uplink-recheck.txt`). This timing-sensitive wider check is recorded,
not claimed as a clean full-suite pass. No wider Task or legacy-oracle cleanup
was included.

### Real Agent boundary and controlled deployment preparation

`real_native_agent.py` creates six synthetic material files in an isolated
project and uses the existing configured formal JiuwenSwarm Agent and file tools
through Native Runtime / Agent Bridge. Provider input facts are synthesized;
this does not exercise the browser microphone or Realtime audio network path.
`real-agent-134113/result.json` records:

- Read all six files, correct total 135, completed in 9.938 seconds, zero cancels.
- Interrupt the second round after real file-tool start: exact Agent cancellation
  once, 0.016-second cancellation settlement; no audio/history effects.
- Project inputs unchanged in both runs; no business Tasks were created.

Before controlled restart, the existing browser has Live Voice off, and all 89
retained Tasks are terminal (58 completed, 14 cancelled, 13 failed, 4 interrupted).
`tasks-before.json` fingerprints Tasks, results, events and consumption. The
controlled launcher preserves the registered project/data, configured Agent,
`openai-realtime-native` / `gpt-realtime-2`, headset profile and NoBrowser. Actual
new source/PID/ports, Speech readiness, served bundle and unchanged Task hashes
must be verified in `deployment-verified.json` after startup; this preparation
record alone does not claim a deployment.

Physical headset interruption/continuity and the complete Native business-audio
A/B/A2 journey remain open. No blanket product-readiness or performance claim is
made.
