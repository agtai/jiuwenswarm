# P2 Real Agent + CR Interface Blocker Review — 2026-08-05

## 1. Result

- Task: `P2-REAL-AGENT-CR`
- Branch: `codex/lv-p2-agent-cr`
- Base: `1e76dbd6aa0ebb011842f31beb98ca2cb11d2496`
- Risk: D-046 Tier 2, with authority/concurrency findings requiring fail-closed handling
- Result: `BLOCKED`; no implementation candidate and no commit proposed

The current public JiuwenSwarm Agent/Harness surface cannot support the Task Packet's
formal source-backed WorkProgress or exact round cancellation without an accepted
adjacent interface change. An exploratory package-local implementation was reviewed,
found to violate those authorities, and removed rather than retained as a candidate.

## 2. Verified interface blockers

### 2.1 No authoritative round event source

`JiuWenSwarm.process_message_stream()` returns legacy `AgentResponseChunk` values with
request/channel identity, payload and `is_complete`. It does not return an ACG
authoritative `round.accepted|running|terminal` `EventEnvelope`, a stable source
`event_id`, source sequence, canonical `round_id`, scope, correlation or terminal
outcome. AB-B deliberately projects only an already-authoritative Harness round event.

Creating `round.*` envelopes in a compatibility Adapter from call admission, arbitrary
chunks or stream end would invent execution facts and label the Adapter as Harness
authority. That conflicts with ACG §§3, 4, 5.2, 6.2 and 8: Agent Bridge maps but never
creates round facts, and an Adapter cannot impersonate source authority.

### 2.2 Existing cancel is session-current, not exact-round

The legacy `CHAT_CANCEL` path in
`jiuwenswarm/server/runtime/agent_adapter/interface.py::_process_interrupt()` reads the
intent and normalized session, but ignores supplied `request_id` and `round_id`. It
invokes session/current-work interrupt and cancellation. DeepAdapter's internal
`cancel_round(reason=...)` also accepts no canonical round identity.

Therefore an Adapter cannot prove that an acknowledged legacy cancel targeted the
requested `(scope, request_id, round_id)`. Concurrent or adjacent direct Chat work in
the same Session may be cancelled instead. The formal Adapter must report exact round
cancel as unsupported until the owning Agent/Harness surface performs an atomic target
check before effects.

### 2.3 Formal history ownership is also unavailable

The real `JiuWenSwarm.process_message_stream()` path writes legacy user/assistant
history while processing `CHAT_SEND`. That occurs before any CR PresentationAck and
bypasses the formal presented-history selector. This behavior may remain a clearly
labelled direct-Chat compatibility/fallback route, but it cannot be described as the
formal P2 history-authority route without a no-history Agent execution seam (or another
accepted ownership design).

## 3. Required Integration Owner decisions/interfaces

1. Accept an Agent/Harness-owned round instrumentation interface that emits immutable
   canonical round envelopes with exact scope, round/request/correlation identity,
   stable event ID/sequence and truthful terminal outcome. The compatibility Adapter
   may then map those source events but must not create them.
2. Accept an exact Agent/Harness cancel operation keyed by the original scoped round
   binding. A mismatch, absent target or stale target must reject before Agent, Tool or
   Task effects; ACK remains distinct from terminal evidence.
3. Decide how formal execution suppresses or defers legacy history writes until CR's
   surface-specific PresentationAck authority is applied, while preserving the existing
   direct Chat fallback unchanged.
4. Define atomic dispatch reservation before CR response mutation, including concurrent
   replay and conflicting request/round admission behavior.
5. Define retained, shielded and bounded shutdown for stalled Agent streams so caller
   cancellation cannot mark an incomplete teardown closed.

These changes touch the Agent/Harness execution and history authority boundaries and
must not be silently introduced by this Worker.

## 4. Review findings from the discarded exploration

- Adapter-generated round states/outcomes falsely claimed Harness authority.
- Legacy session-current cancel was reported as exact-round ACK.
- Concurrent duplicate/conflicting dispatch could mutate/fence CR before Bridge
  admission rejected it.
- A cancelled or stalled close could leave Bridge workers/transport and the consumer
  alive while the composition reported closed.
- Public raw Bridge/CR properties could bypass the committed-only composition gate.
- Empty `chat.final` could lead to terminal `completed` with no usable final response.
- Mutable `PermissionContext` could be changed after one-time scope validation.
- Real legacy history writes were not represented by the fake-facade tests.

All findings remain blocking or inapplicable because the exploratory implementation was
removed; none is claimed fixed by a candidate diff.

## 5. Review passes

| Pass | Result | Method and limitation |
|---|---|---|
| Implementation self-review | `FAIL / BLOCKED` | Found swallowed stream cancellation and transport cleanup issues, then identified the source-authority and exact-cancel interface gaps. |
| Cold complete-diff review | `FAIL / BLOCKED` | Re-read the complete exploratory files against the Task Packet, root `AGENTS.md`, ACG, AB-B/CR-B reviews, real Agent facade and actual tests. The interface gaps prevent a valid candidate. |
| Independent review | `FAIL / BLOCKED` | Native `/review` was unavailable. A separate read-only agent reviewed the complete exploratory diff and independently audited the real Agent/Harness call path. This is an equivalent independent review, not a claim that `/review` ran. |

## 6. Exploratory verification (not acceptance evidence)

Before the invalid prototype was removed, the following passed:

- focused package tests: `13 passed`
- AB-B/CR-B plus focused affected tests: `48 passed`
- all `tests/unit_tests/live_voice`: `181 passed`
- existing Chat/E2A cancel regressions: `51 passed`
- Ruff format/check, `py_compile`, and isolated mypy

These tests used fake facades for the new path and did not prove authoritative Harness
source events, exact real-facade round cancellation, PresentationAck history ownership,
or credentialed service behavior. They must not be used for Gate credit.

## 7. Explicit exclusions and evidence still required

- No RM-B/C, II-B/C, Speech Provider, Task authority, VB-C/TC-C or final Web route.
- No shared `STATUS`, README, decisions, roadmap, validation or Replacement Ledger
  update.
- No real credentialed Agent/Tool service run and no external side effects.
- No Integrated Demo, Web Alpha or Replacement Ledger credit.
- After the required interfaces are accepted and implemented, repeat Tier 2 tests and
  all three D-053 review passes, then obtain separate commit approval.

## 8. D-059 superseding implementation review

Sections 1-7 above are retained as the historical record of the discarded exploration.
They are not evidence for this implementation. The Integration Owner subsequently
froze D-059 recommendations `1A 2A 3A 4A 5A` in
`P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md`. The implementation below uses
that contract and is reviewed as D-046 Tier 3 with Tier 2 concurrency and shutdown
semantics.

Package result: `D-053 PASS AFTER FIXES / FORMAL FOUNDATION`. The package-local
implementation, affected regressions and all three review passes are complete after
the independent findings were fixed and the bounded final independent equivalent
returned `PASS - no actionable findings`. This does not mean integrated route,
production, Gate acceptance or Replacement Ledger credit.

## 9. Delivered D-059 interfaces and composition

- The new Harness owner reserves opaque round and reservation identities before CR
  mutation, owns the actual formal execution task, and alone emits canonical
  source-backed `round.accepted`, `round.running` and `round.terminal` envelopes.
  Unsupported blocked/decision capabilities remain absent.
- Exact round cancel validates the trusted handle plus command, scope, request, round,
  correlation and committed origin. ACK remains distinct from terminal; replay is
  stable; changed fingerprints, repeated new cancel commands, wrong bindings, replaced
  rounds and terminal targets cause zero new cancel effects.
- `JiuWenSwarm.process_formal_live_voice_stream()` and its Deep Adapter seam bypass the
  legacy Chat orchestration/history/cloud/auto-memory path, accept only the immutable
  committed turn plus CR-selected context, and leave `process_message_stream()` intact.
  A trusted exact-session guard suppresses real Tool-level legacy history calls and is
  deliberately retained if Agent cleanup is not proven safe.
- Bridge and Harness implement reserve -> COMMITTING -> commit/abort. Capacity,
  request/round binding, immutable fingerprint, feature/capability and input admission
  complete before `CR.accept_response`; the retained admission coordinator is shielded
  from caller cancellation.
- `AgentConversationRuntime` is the product-consumable seam. It consumes Bridge output
  without blocking CR/media admission, forwards Harness-backed WorkProgress, turns only
  an unfenced usable final into a TEXT `PresentationUnit`, suppresses rejected late
  final content, and keeps response/barge cancel separate from exact round cancel.
- CR issues immutable TEXT history intents at its serialized PresentationAck boundary.
  The formal writer persists the committed user turn and only each newly acknowledged
  contiguous text prefix, idempotently; audio, wrong-generation, fenced and unACKed
  output write no assistant history. Concurrent exact ACKs serialize to one write.
- Shutdown has one retained coordinator and shielded bounded callers. Infrastructure
  close and subscription detach never issue round/task cancel; timeout stays pending;
  explicit interaction close targets only the latest exact conversational round and
  waits for Harness terminal truth. Output and dedicated-session cleanup use retained
  tasks plus bounded wait slices; terminal/closed is not published before cleanup, and
  permission context is released on every settled path.

## 10. Implementation and cold-review findings fixed

The implementation self-review and cold complete-diff review found and fixed:

1. a detached Harness subscriber could leave a producer blocked on a full output queue;
2. a rejected or concurrent PresentationAck could race history or terminal mutation;
3. missing formal-facade capability could start otherwise unused workers;
4. CR core violations could escape the consumer because only Loop violations were caught;
5. distinct cancel commands could call `Task.cancel()` more than once while cancelling;
6. invalid channel input could fail only after CR response mutation;
7. rejected late final text remained visible on the product notification seam;
8. Deep output-lease close was unbounded and could skip permission-context cleanup;
9. interaction close could cancel a replaced round rather than the latest generation;
10. the initial tests assumed synchronous worker start and the wrong CR exception wrapper.

The first independent equivalent review then returned `FAIL / BLOCKED` with two P0 and
five P1 implementation findings. None of that failed review is counted as D-053 PASS.
The implementation and tests were changed to fix all seven:

11. immediate post-commit cancel could cancel an unstarted task and permanently lose
    Harness terminal; cancel delivery now waits for the owned round task to enter and
    has a single observed-delivery path;
12. cancel ACK could be upgraded to CANCELLED before Agent/output cleanup settled;
    stream and dedicated-session cleanup are retained, explicit and shielded, and
    Harness terminal waits for their actual completion;
13. source terminal left CR generating and allowed a later unACKed suffix to enter
    history; source terminal now transitions/fences the exact response immediately;
14. real tools such as `SendFileToolkit` could call the legacy history writer inside
    the formal route; a trusted registered formal-session guard now makes those writes
    zero while leaving an unregistered Direct Chat session with the same prefix intact;
15. reservation expiry released capacity only when the same request or snapshot was
    touched; every new admission now expires the full retained reservation set first;
16. shutdown could set composition closed before pending or concurrent ACK history was
    settled; shutdown now serializes with ACK/history, and persistent history failure
    remains explicitly failed/closing with `closed == false`;
17. a facade method alone could hide an incompatible lower Code adapter until after CR
    mutation; optional lower capability is now distinct from the base Adapter protocol,
    preflighted before workers/reservations, and bound into Harness reservation truth.

The subsequent cold review additionally retained the exact no-history guard after an
unsafe cleanup failure, made formal per-round session cleanup part of terminal
settlement, waited for cancel coordinators during Harness close, and bound facade
identity at reservation so commit cannot newly fail an already-reserved admission
condition. Focused regressions cover each change.

The tool-enabled independent re-review was given a 120-second bounded window, timed
out without a conclusion and was interrupted. It is not counted as a D-053 result. A
hash-frozen, no-additional-tool independent equivalent over the already-loaded complete
diff then returned one further P1, which was fixed:

18. with `output_capacity == 1` and no subscriber, `round.accepted` could fill the
    output queue before the round reached its cancellation-ready barrier, so immediate
    exact cancel and Harness close could wait forever. Payload backpressure now uses a
    separate bounded semaphore, four Harness-owned control slots are retained for
    accepted/running/terminal/end, and cancellation waits for a non-blocking entered
    barrier plus canonical running publication. A real-facade, capacity-one,
    unsubscribed immediate-cancel regression proves terminal, zero Agent calls, one
    cancel effect and completed close.

The semantic-fix cold rereview also replaced a scheduling-sensitive queue-full test
assumption with an explicit wait for the two already-admitted Harness effects; it then
asserts the rejected third dispatch adds no Agent effect or partial CR response.

Each semantic fix has a focused regression. The final cold reread compared every tracked
diff and untracked package file with root `AGENTS.md`, the frozen D-059 packet, existing
AB-B/CR-B behavior and the actual final tests. No remaining actionable self/cold finding
is open.

## 11. Final verification

All commands used the repository virtual environment
`D:\\XGG AI\\openjiuwen\\jiuwenswarm-p2-agent-cr\\.venv\\Scripts\\python.exe` and disabled only
repository-wide coverage instrumentation with `--no-cov`; test selection and assertions
were unchanged.

- `python -m pytest -q --no-cov tests/unit_tests/live_voice tests/unit_tests/agentserver/test_formal_live_voice_adapter.py tests/unit_tests/test_session_history_paths.py`
  -> `203 passed`, one third-party Authlib deprecation warning.
- `python -m pytest -q --no-cov tests/unit_tests/e2a tests/unit_tests/gateway/test_message_handler_stream_cancel.py tests/unit_tests/test_session_history_empty_filter.py tests/unit_tests/test_compact_history_records.py tests/unit_tests/test_session_history_paths.py tests/unit_tests/agentserver/test_interface_session_runtime_cleanup.py tests/unit_tests/agentserver/test_deep_adapter_session_teardown.py tests/unit_tests/agentserver/test_interface_interrupts.py tests/unit_tests/agentserver/test_deep_adapter_interrupt.py tests/unit_tests/agentserver/test_stream_chunk_whitespace.py tests/unit/agentserver/test_interface_chat_error.py tests/unit_tests/test_app_agentserver.py`
  -> `144 passed`, one third-party Authlib deprecation warning.
- Focused source `py_compile`, Ruff on the affected set, fatal/undefined Ruff checks on
  the pre-existing delayed-import Deep Adapter file, scoped mypy on the five new source
  modules, new-file Ruff format checks and `git diff --check` pass.

The real-facade authority test instantiates the production `JiuWenSwarm` facade and
crosses its new formal method into a controlled lower Agent adapter. The Deep seam is
also tested directly, including retained output/session cleanup. A real in-repository
`SendFileToolkit.send_file()` call with a controlled local file and fake transport proves
that Tool-level legacy history writes are suppressed; no external side effect or
credentialed service was invoked. This does not prove provider credentials, network or
production model behavior.

## 12. D-053 review status after D-059

| Pass | Result | Method and limitation |
|---|---|---|
| Implementation self-review | `PASS AFTER FIXES` | Complete authority/concurrency review found and fixed the ten items in section 10; focused and affected tests were rerun. |
| Final cold complete-diff review | `PASS AFTER FIXES` | Re-read the final complete diff and all new files against the original request, root rules, D-059, AB-B/CR-B behavior and actual tests after the last semantic fix. |
| Independent review | `PASS AFTER FIXES` | Native `/review` is unavailable. The first separate read-only complete-diff review returned two P0 and five P1 findings. A 120-second tool-enabled re-review timed out and was interrupted, so it is not counted. A hash-frozen, no-additional-tool equivalent then returned the capacity-one P1 in section 10. The same independent reviewer assessed the previously frozen complete diff plus the exact final Harness/test/record delta, without tools, and returned `PASS - no actionable findings`. Limitation: the substitute relied on already-loaded complete-diff content and supplied final verification evidence rather than a callable native `/review`. |

## 13. Remaining exclusions and real evidence

- No RM-B/C, II-B/C, Speech Provider, Task authority, VB-C/TC-C, final Web UI/route or
  authenticated multi-tenant composition.
- No shared README, STATUS, DECISIONS, roadmap, acceptance, validation or Replacement
  Ledger update; no merge, rebase, cherry-pick or push.
- No credentialed model/provider or external Tool/service call, browser
  PresentationAck, microphone, speaker, media transport or Integrated Demo run. The
  controlled in-repository real `SendFileToolkit` authority test is not a service Gate.
- The package remains `PARTIAL` at product level until Integration Owner review,
  authenticated product composition and cumulative real browser/media/service Gates.
