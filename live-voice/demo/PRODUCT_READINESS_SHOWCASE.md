# Live Voice product-readiness human showcase

> Current candidate and blockers: [STATUS](../STATUS.md)
> Pass/fail authority: [PRODUCT_READINESS_ACCEPTANCE](../validation/PRODUCT_READINESS_ACCEPTANCE.md)
> Environment/startup procedure: [E2E runbook](../runbooks/E2E_RUNBOOK.md)
> Verification/review policy: root [TESTING](../../TESTING.md)

Run this once after the applicable automated checks and cumulative review pass
on one exact clean source. It is the current controlled product journey, not a
numbered-stage handoff and not a public production demonstration. Historical
Integrated Web Alpha acceptance remains bound to its historical exact source;
it cannot be reused to pass later hands-free/background-task changes.

This smaller journey must not be reused as complete-P3 evidence. A future
complete-P3 candidate uses the prepared
[complete-P3 minimal acceptance questions](COMPLETE_P3_MINIMAL_ACCEPTANCE_QUESTIONS.md)
in addition to its exact-source automated, fault/recovery and review Gate; that
question set is preparation only until it is actually run.

## 1. Preflight and candidate identity

Record without secrets:

- exact source, comparison base, branch/upstream relationship and clean status;
- browser/version, OS, origin/secure context, actual microphone/output and
  network labels;
- real Speech/Media/Agent/Tool/Task/Executor routes and declared fallbacks;
- isolated data root, persistent Session, registered disposable no-remote
  project and enabled flags;
- automated/review result and every still-open accepted deviation.

Stop as `BLOCKED` if the source, route, model, project, device, Provider,
Executor or deployment differs from the reviewed candidate. Do not repair source
or silently switch routes during the journey.

## 2. Platform lifecycle

1. Verify microphone grant, denial and revocation show truthful states and keep
   text Chat usable.
2. Restore permission and exercise device loss/change and recovery without stale
   capture or playout resurrection.
3. Verify user activation/autoplay and hidden/background/resume do not duplicate
   submission or retain an unauthorized microphone.
4. Refresh/reconnect and confirm no duplicate Agent/Tool/Task dispatch, old
   response audio or foreign target appears.
5. For non-localhost deployment, verify HTTPS/WSS, proxy, CSP/CORS and transport
   diagnostics; otherwise record localhost as a controlled-test exception.

## 3. Real voice conversation

1. Start the physical microphone and speak a request containing a technical or
   critical token.
2. Observe the authoritative final/clarification boundary. Confirm partial or
   uncommitted input caused zero Agent/Tool/Task mutation.
3. Verify the committed request reaches the real JiuwenSwarm Agent and a safe
   real Tool operation where applicable.
4. Hear the truthful response through the declared TTS route.
5. Interrupt the exact playout and confirm no stale chunk returns and no other
   response/round/Task is cancelled.

Record measured latency by reference to the tested corpus/trace; do not invent
p50/p95 from this single presentation.

## 4. Create and observe one detached Task

Using only the disposable project:

1. Commit and confirm a safe natural-language Task create.
2. Verify the exact command/task/attempt identities and that accepted/queued is
   not presented as applied, completed or successful.
3. Confirm the real Agent/Executor begins authoritative work and emits
   source-backed progress.
4. Continue at least one foreground voice Turn while the Task runs. The Task
   must not freeze microphone, response control or bounded progress.

## 5. Apply a running adjustment

1. Speak one bounded adjustment that targets the active Task and wait for the
   authoritative committed final.
2. Verify clarification/confirmation and exact task/attempt/generation binding.
3. Verify the adjustment reaches the application/Executor path and produces the
   intended project or result change.
4. Treat dialogue acknowledgement without authoritative application evidence as
   `FAIL`; it cannot pass as an applied update.
5. Send a stale, ambiguous or wrong-target variant safely and confirm zero
   project/Task mutation.

## 6. Status, result and terminal notification

1. Query status while the Task is active. The reply must match authoritative
   state and must not claim completion/result availability early.
2. Interrupt or revise only the foreground response and verify the detached Task
   remains unchanged.
3. When the Task settles, verify one exact terminal TaskEvent/result and one
   Runtime-arbitrated user notification through the current TTS owner.
4. Query the final result and verify the answer is grounded in immutable result
   context. Missing/truncated context must be explicit, never fabricated.
5. Confirm duplicate, stale or wrong-generation terminal notifications are zero.

## 7. Degradation, privacy and recovery

1. Exercise one selected safe Speech/Media/Provider failure and verify a bounded
   visible error plus usable text fallback.
2. Exercise one selected safe Executor failure/recovery case and verify exact
   failed/interrupted/pending/unknown truth with no duplicate effect.
3. Inspect browser storage, URLs, logs, Context, TaskEvent and WorkProgress for
   credentials, unauthorized content or raw-audio persistence.
4. Refresh/reconnect once around active or terminal state and prove no silent
   rerun, duplicate notification or cross-session target.

## 8. Closeout and decision

1. Exit Live Voice and confirm microphone, capture/playout, timers and reconnect
   loops stop.
2. Settle or truthfully record every task/attempt/outbox/owner/lease.
3. Confirm the disposable project contains only expected effects and has no
   remote/push credential.
4. Stop dedicated services, confirm ports release and verify the tested source
   did not change during the journey.
5. Record each section as `PASS`, `FAIL`, `BLOCKED` or `NOT APPLICABLE`, with a
   reason for every N/A or reused observation.

The final result must use one
[product-readiness acceptance](../validation/PRODUCT_READINESS_ACCEPTANCE.md)
outcome. A passing controlled candidate still does not claim production
authentication, broad browser/mobile compatibility, public deployment,
feature completeness, complete P3 or RC/Production readiness, and does not
trigger integration with `develop`.
