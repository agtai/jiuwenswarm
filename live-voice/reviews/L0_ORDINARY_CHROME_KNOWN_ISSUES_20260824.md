# L0 ordinary Chrome known issues — 2026-08-24

## Current L0 disposition — 2026-08-25

[D-097](../decisions/DECISIONS.md) accepts the ordinary-Chrome 8/8 basic
journey, authoritative terminal barge rerun and the later warm automatic
first-audio `20/20` plus dedicated barge-in `20/20` result as the bounded D-095
L0 closure. Cold, cold-minus-warm, positive formal background-Task semantics
and the retained natural-status/recovery defects are no longer conjunctive
requirements for this L0 closeout. They remain honest later work and receive no
retroactive PASS.

The Speech cancellation cleanup part of KI-05 is now separately repaired on
behaviour source `ba06d9825c`. The warm run contains zero
`STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED` and zero
`live_voice_speech_transport_cleanup_incomplete`; 13 owned cleanup tasks that
outlived the caller budget are INFO
`live_voice_speech_transport_cleanup_deferred`. See the
[Speech cancel review](L0_SPEECH_CANCEL_OBSERVABILITY_REPAIR_REVIEW_20260825.md)
and [warm closure evidence](../evidence/L0_WARM_STEADY_STATE_CLOSURE_EVIDENCE_20260825.md).

Two later non-blocking issues are added below as KI-07 and KI-08. They prevent
cold-runner and zero-runtime-anomaly claims but do not invalidate the 40 exact
eligible warm samples.

## Later repair disposition — 2026-08-24

This header updates current repair status without rewriting the exact-source
session findings below. KI-05 was traced to the Conversation Runtime treating
Agent generation terminality as proof that downstream browser playout had also
ended. The repair now accepts an exact terminal-response barge action as a
replayable, playback-only stop: it emits no response, round or Task cancel.
KI-06 is also repaired for new runs by logging only bounded stable error
`code`/`reason` tokens while excluding messages, credentials and payload
content. The scoped automated Runtime, Product P2, AgentServer/E2A and
Integrated Web checks pass; details are in the
[repair review](L0_TERMINAL_BARGE_IN_REPAIR_REVIEW_20260824.md).

The original ordinary-Chrome evidence remains unchanged and cannot receive
retroactive server-acknowledgement credit. A later physical rerun on repair
behaviour source `39932971f8` repeated button interruption, voice interruption
and Stop/Exit in the same ordinary Chrome Session. Its three exact P2 barge
requests all returned `e2a.complete`; see the
[post-repair evidence](../evidence/L0_TERMINAL_BARGE_IN_REPAIR_EVIDENCE_20260824.md).
This supplies new repair-boundary credit rather than rewriting the old run.
Provider transport-cleanup diagnostics in KI-05 and KI-01 through KI-04 remain
outside this repair.

## Purpose and disposition

This record isolates the problems found while reviewing the ordinary-Chrome L0
session on clean source
`362403cd6c6671b04d4c4129019047bf81df1d53`. It is intentionally separate from
the [manual acceptance report](../evidence/L0_ORDINARY_CHROME_MANUAL_ACCEPTANCE_20260824.md)
so each issue can be understood and repaired later without rewriting the
operator's bounded 8/8 basic functional judgement.

Disposition: **DEFERRED BY USER; DIAGNOSIS ONLY.** No source, test, runtime
configuration, Provider setting or deployment behaviour is changed in this
documentation closeout. These findings do not turn the eight user-visible basic
scenarios into failures. They do limit which formal Task, interruption and
D-095 closure claims the session can support.

## Evidence identity

- Branch/source: `hx/0812_live_voice_w3@362403cd6c`, clean before closeout.
- Session: `web_1a034feac64_9781824cb619` in an ordinary installed Chrome
  window, not an isolated Chrome launch.
- Runtime: `formal-web-validation`, configured real Speech round trip,
  disposable no-remote project and Direct D2 executor profile.
- Reviewed truth: runtime log, Agent history, unified committed-input Store,
  formal Task Store and the exact source paths named below. Raw artifacts remain
  ignored and machine-local.

## KI-01 — task-like scenarios 7 and 8 were Agent dialogue, not formal Tasks

**Observation.** The operator received plausible create/report and status
answers, so both scenarios passed as user-visible basic journeys. However, both
unified Store rows have `route=dialogue`, `reason=DIALOGUE_RESOLVED` and
`task_id=null`. No formal Task was created by scenario 7 and no formal
`task.status` operation was performed by scenario 8.

**Why the replies looked successful.** Private Agent history shows that the
ordinary Agent created an internal todo, invoked the terminal and later reported
that todo as completed. That is real Agent/Tool work, but it is a different
authority from the formal P3 Task Store.

**Impact and later repair target.** User-visible wording can make an internal
Agent todo look like a formal background Task. A later repair/evaluation packet
must decide whether the bounded semantic classifier should recognize these
forms or whether acceptance prompts must use the explicit supported background
form. Until then, scenarios 7 and 8 grant no positive formal Task credit.

## KI-02 — explicit background read-only work was classified as project mutation

**Observation.** A later explicit background formulation correctly resolved as
`background.create` and created Task
`task-31d79c352d444c5aa97732295ade6123`. Its durable spec assigned
`side_effect_class=project_mutation` even though the instruction only asked to
inspect the current Git branch and report it. The Direct executor then recorded
`accepted -> running -> terminal/failed` with
`NO_EFFECTIVE_TARGET_CHANGE`.

**Cause boundary.** The create route and durable Task authority worked. The
failure is downstream of creation: the admitted mutation contract expected a
target change, while the requested operation was observational. It should not
be summarized as “background Task was never created”.

**Impact and later repair target.** Read-only background work cannot complete
positively under this selected mutation contract. A later packet must examine
the instruction-to-executor/side-effect classification and its admission
contract; this review does not choose a new product policy or executor class.

## KI-03 — natural status query lost the current formal Task context

**Observation.** The Web task monitor issued structured `live_voice.task.status`
and `live_voice.task.events` requests after creation. At 20:47:50, the user's
natural status question was separately committed through the unified voice
route, but its semantic binding was `dialogue / DIALOGUE_RESOLVED` with
`task_id=null`.

**Cause boundary.** The formal Task existed and had a current running state, so
this was not “no Task available”. The natural-language resolver did not bind the
referential phrase to that Task and therefore sent it to ordinary dialogue.

**Impact and later repair target.** The user may receive an Agent-generated
answer instead of Store-authoritative Task truth. A later classifier/context
packet should reproduce the referential query against one current Task and
assert exact Task binding; no classifier change is made here.

## KI-04 — presentation-failure replay caused the long “recovering” stall

**Observed chain.** Task progress audio reported
`task_audio_playout_failed`. The first
`live_voice.composition.p2.presentation.failed` request reached AgentServer and
returned `e2a.error`. About 0.25 seconds later the Browser retried the retained
operation with the same request ID. The retry also reached AgentServer and
returned `e2a.error`, but the Gateway did not deliver that response to the new
waiter. Later 15-second Browser retries were coalesced onto the same retained
Gateway unary operation, which finally logged a 600-second AgentServer timeout.
This is the log counterpart of the page staying in “recovering”.

**Located mechanism.** The Browser intentionally retains the operation request
ID and retries ambiguous errors in
[`productWebActivation.ts`](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts).
Ordinary Web requests time out after 15 seconds in
[`webClient.ts`](../../jiuwenswarm/channels/web/frontend/src/services/webClient.ts).
The Gateway cleanup path in
[`agent_client.py`](../../jiuwenswarm/gateway/routing/agent_client.py) places
every removed request ID behind a two-second `_cancelled_request_ids` fence; the
receiver drops any response whose ID is inside that fence. The exact retained
retry arrives inside this window. Once that response is dropped, exact later
replays coalesce with the still-running 600-second unary waiter.

**Impact and later repair target.** A short, valid same-ID retained retry can be
mistaken for residual traffic from an old owner, creating a long false recovery
state. The later fix must preserve protection against stale response cross-talk
while distinguishing a completed owner from a replacement retained retry. This
review deliberately does not prescribe or implement that concurrency change.

## KI-05 — interruption looked effective locally but every barge RPC was an error

**Observation.** The operator confirmed effective button interruption, voice
interruption and playback Stop/Exit. The log contains nine P2 `barge_in`
requests across the base and focused journeys; every corresponding unary result
is `e2a.error`. Some close/interrupt paths also emit
`STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED` and
`live_voice_speech_transport_cleanup_incomplete` diagnostics.

**Interpretation boundary.** The user-visible stop can be produced by the local
WebAudio/fence path before server settlement completes. Therefore the operator's
observation is valid, but it is not proof that Runtime accepted the authoritative
barge transition. The Provider cancellation diagnostics also do not by
themselves prove that audio continued; they say the transport did not provide a
clean acknowledgement/cleanup observation.

**Impact and later repair target.** Do not use this session as a successful
dedicated D-095 barge-in sample or as proof of authoritative stop settlement. A
later packet must capture the actual error payload, correlate active response
ownership at each request and separately verify local silence and Runtime state.

## KI-06 — INFO error logs omit the fields needed to diagnose the error

**Observation.** The shared E2A wire INFO line in
[`wire_codec.py`](../../jiuwenswarm/common/e2a/wire_codec.py) logs only request
ID, response ID and `response_kind`. For the `barge_in` and
`presentation.failed` failures above, it records `e2a.error` but not the error
code, reason or sanitized message. The later 600-second timeout consequently
dominates the visible log even though the initial AgentServer error happened
immediately.

**Impact and later repair target.** Operators cannot distinguish an expected
stale/conflict response from an availability, authorization or protocol defect
using the INFO log alone. A later observability packet should add bounded,
sanitized error code/reason logging without exposing text, credentials or
private project content. This closeout records the gap only.

## KI-07 — warm completion terminates the Browser controller before cold epochs

**Observation.** The warm profile completed its 20 first-audio and 20 barge-in
targets. The supervisor then created a fresh cold coordinator, but the Browser
never requested its first job. The cold session remained
`epoch_attempted=false`, wrote zero Browser records and produced no epoch
completion marker.

**Located mechanism.** The coordinator's session `batch_complete` means that
the current temperature has reached both targets. The Browser controller treats
that value as whole-series completion and returns; the panel disables its
button in `complete`. The supervisor independently assumes the page will keep
polling across coordinator replacement and starts cold without reopening the
controller. Existing tests exercise warm and cold sessions separately and do
not cover this cross-coordinator lifecycle.

**Disposition.** Deferred under D-097. Cold is no longer required for this L0
closeout, so the runner is not changed or credited. Requiring a future cold
baseline must first reopen this exact orchestration boundary and add the missing
warm→cold lifecycle regression.

## KI-08 — one warm-run Realtime STT stream became unavailable and recovered

**Observation.** The warm runtime emitted one visible
`recognition.stream / STREAMING_SPEECH_PROVIDER_UNAVAILABLE` degradation after
an established Realtime STT socket closed. A new media connection opened about
0.18 seconds after the degradation record and the later measured round
completed.

**Interpretation and disposition.** The event was not correlated to an eligible
measurement round, so the aggregate correctly contains 20 first-audio success
and 20 expected barge cancellation outcomes with no fallback. It is still a
real Provider/network reliability anomaly and prevents a claim that the whole
runtime interval was error-free. No Provider, retry or fallback policy is
changed in this L0 documentation closeout.

## Relationship to the original 2026-08-24 L0 closeout

The operator's basic journey result remains **8/8 PASS**. The exact D-095 claims
remain narrower:

- Tool-path credit: yes, bounded to the observed terminal call;
- positive formal Task create/status completion: no;
- user-visible button/voice interruption and Stop/Exit effect: yes;
- authoritative successful server-side barge-in: no;
- explicit silence-rejection evidence: not recorded;
- cold/warm scripted sequences and sanitized p50/p95 aggregate: not run.

Accordingly, this issue list is deferred work, while the overall D-095 L0
engineering measurement closure remains open for missing conjunctive evidence.

That final sentence is the exact 2026-08-24 disposition. The current status is
superseded by D-097 and the 2026-08-25 header: bounded warm steady-state L0 is
closed, while the listed Task/recovery, cold orchestration and Provider
reliability issues remain separately deferred.
