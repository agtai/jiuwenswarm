# L0 Speech cancel observability repair review — 2026-08-25

## Scope before implementation

- Capability: OpenAI streaming Speech Adapter cancellation and bounded transport-cleanup observability.
- Risk: Tier 3 Speech Port control/cleanup boundary under root `TESTING.md`.
- Intended behaviour: normal recognition or synthesis cancellation immediately fences the exact local session and closes its transport. When the Adapter truthfully declares `provider_cancel_ack=unavailable`, that expected capability gap must remain visible in capability and route-control provenance, but it must not be promoted to a user-visible streaming-to-text failure. A cleanup task that outlives the 50 ms caller budget remains owned and is a deferred cleanup observation; only capacity, identity conflict, failed cleanup or owner-close timeout is an incomplete-cleanup error.
- Owned product/test surfaces: `openai_streaming_speech.py`, the Gateway streaming-synthesis cancel completion barrier and their unit regressions; post-repair validation also exercises Product P1/P2, Integrated Web, real Provider probe and ordinary installed Chrome.
- Explicit exclusions: no fabricated Provider cancel ACK or terminal event; no protocol/schema, Agent, Tool, Task, classifier, history, audio-cursor or fallback-policy change; no change to local WebAudio fence authority; no remote-ref update.
- Acceptance: cancellation closes and retires the exact stream, including when its RPC waiter is cancelled during Provider cleanup; stale output remains fenced, `provider_cancel_ack` remains `unavailable`, no visible degradation fact or failure metric is emitted for normal cancel, deferred cleanup remains bounded/owned, actual incomplete cleanup still fails visibly, and the ordinary-Chrome focused barge sequence has no cancel-degradation warning.

## Located causes and repair

The OpenAI Adapter declares both cancel-ACK capabilities as `unavailable`,
which is truthful for the selected Realtime transcription and SSE TTS
transports. The cancel methods nevertheless called the generic failure emitter
after they had successfully fenced the exact session, closed the transport and
retired the state. That emitter always records `visible=true`, `to_tier=text`
and a failure metric. Every normal interruption therefore generated
`STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED` even though the local/browser fence and
P2 barge settlement succeeded.

The repair removes only that false degradation emission. Capability provenance
remains `unavailable`; no `CANCELLED` Provider event or terminal ACK is
fabricated. Actual transport/protocol/timeout failures still use the generic
failure path. A cleanup that exceeds the caller's 50 ms wait but remains owned
is now logged as `live_voice_speech_transport_cleanup_deferred` at INFO. The
existing incomplete-cleanup ERROR remains for capacity, identity-conflict,
failed cleanup and owner-close timeout.

The affected route regression also exposed a second cancel-control defect:
after its waiter was cancelled, `StreamingSynthesisRouteOwner.cancel()` retried
cleanup in the already-cancelled task. The retry could be cancelled again and
leave the exact handle active with `cleanup_complete=false`. The retry now runs
as one named route-owned task behind a shielded completion barrier; repeated
waiter cancellation cannot abandon it, and the original caller cancellation is
re-raised after cleanup settles.

## Applicable D-032 matrix

| Dimension | Evidence and result |
|---|---|
| P | Recognition and synthesis cancel close their transports, retire the exact session and return normal route control; PASS. |
| N | Provider/protocol/timeouts, non-cooperative cleanup, stale events and invalid cancel ACKs remain rejected or visibly failed; zero business effects retained; PASS. |
| B | The 50 ms cleanup wait is bounded; retained cleanup stays capacity-counted and actual close/capacity failure remains explicit; PASS. |
| S | Cancel keeps the session terminal/fenced and preserves capability provenance without inventing a Provider terminal; PASS. |
| T | Cancel-during-Provider-cleanup now joins its exact retry before rethrowing caller cancellation; PASS. |
| C | Cleanup lock plus the retained completion barrier keep one exact handle linearized; PASS. |
| R | Repeated cancel/close and retained cleanup reuse the exact stream identity and produce no duplicate business effect; PASS. |
| I | Existing response/generation/stream and Provider bindings remain unchanged; PASS. |
| F | Selection flag-off and unavailable Provider paths remain zero-effect; PASS. |
| K | Adapter, synthesis route, Product synthesis, Runtime/P2 and Integrated Web regressions pass; PASS. |
| X | Behaviour source `ba06d9825c` passed the real Provider launcher probes and ordinary installed-Chrome warm sequence; 20/20 dedicated barge samples produced zero cancel-unacknowledged and zero cleanup-incomplete diagnostics; PASS for this repair boundary. |

No shared schema or product policy changed, so migration and classifier corpus
dimensions are inapplicable. Agent, Tool, Task and history effects remain zero
for this control-only boundary.

## Automated verification

- OpenAI Adapter + Gateway synthesis route + Product synthesis: **129 passed**.
- L0 coordinator + Conversation Runtime + focused Product P2: **52 passed**.
- Integrated Web: TypeScript strict compilation and **479/479 passed**.
- Ordinary-Chrome batch and L0 measurement frontend suites: **5/5 + 5/5 passed**.
- Browser Audio I/O and processor: **105/105 passed**.
- Production frontend build: passed; only the existing chunk-size and mixed-import warnings remain.
- Ruff, compileall and `git diff --check`: passed.

## Post-deployment validation

Behaviour source `ba06d9825c92602066756118dd5cac9572c22827` was launched with
the formal profile and ordinary installed Chrome. The launcher passed the real
Speech TTS→STT, critical-receipt, identity-mismatch and forged-claim probes.
The warm automatic sequence then completed 20/20 first-audio and 20/20
dedicated barge samples with zero failed or dropped attempts.

Log review found zero `STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED` and zero
`live_voice_speech_transport_cleanup_incomplete`. Thirteen cleanup operations
outlived the 50 ms caller budget and were retained as the intended INFO
`live_voice_speech_transport_cleanup_deferred`; none became visible
cancel-degradation. One separate `recognition.stream` Provider-unavailable
event recovered through a new media connection and was not correlated to an
eligible sample. It is recorded as a reliability anomaly, not cancel-repair
credit.

**Disposition: PASS — SPEECH CANCEL OBSERVABILITY REPAIR.** The deployment and
ordinary-Chrome log acceptance step is complete. The result does not fabricate
a Provider cancel ACK or claim physical silence; full sanitized counts and
non-claims are in the
[warm closure evidence](../evidence/L0_WARM_STEADY_STATE_CLOSURE_EVIDENCE_20260825.md).
