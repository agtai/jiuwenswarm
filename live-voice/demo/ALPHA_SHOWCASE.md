# Live Voice Integrated Web Alpha human acceptance showcase

> Current stage/node: [STATUS.md](../STATUS.md)
> Pass/fail authority: [ALPHA_ACCEPTANCE.md](../validation/ALPHA_ACCEPTANCE.md)
> Environment/startup procedure: [E2E_RUNBOOK.md](../runbooks/E2E_RUNBOOK.md)
> Stable package map: [WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md](../roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md)

This is the D-075 `A3 Product Acceptance` script. The active S5–S8 task contract is [ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md](../roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md). Run this journey once only after its A2 automation and cumulative review pass on one exact clean tested source. W2 observations may guide setup but do not automatically pass any Alpha step.

## S7-04 handoff binding

The current S7 handoff is **not ready for A3**: automation and cumulative source
review are complete, but all five S7 real probes are `ENVIRONMENT` with zero
valid samples. Do not start this showcase until [STATUS](../STATUS.md) records
S7/A2 closed and the external sanitized `s7-final-automation.json` identifies
the same exact clean candidate as the five `VERIFY` real results. The detailed
reason and shortest path are in the
[S7 integration review](../S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md).

The frozen handoff profile is desktop Chrome on Windows; private same-origin
HTTPS/WSS; system-selected input/output devices recorded by sanitized reference;
the official OpenAI Speech origin with D-078 STT/TTS models and `marin`;
JiuwenSwarm Agent Provider; formal Task Core and
`DirectProjectCodeExecutorAdapter`; disposable no-remote Git fixtures; and
Streaming -> W2 Batch -> Browser/text explicit fallback. Integrated Web, P1,
P2, P3 text/mutation, dedicated media, EOT, critical-input, credential and
formal batch/streaming flags are exactly `true`; the superseded frontend Task
Demo and Streaming Speech entry flags are unset. Current known non-blocking
build warnings are limited to a duplicate i18n key, mixed static/dynamic import
and large chunks. No source repair, hidden route switch, public deployment or
real-user project is permitted during A3.

## 1. Preflight and candidate identity

Record without secrets:

- tested Git source, comparison base and clean worktree before the run;
- exact Chrome, OS, origin/secure-context, actual input/output device and network
  labels for reproducibility; hardware brand/model is not an acceptance allowlist;
- selected real Speech/Media/Agent/Tool/Executor routes and declared fallbacks;
- persistent Session, registered isolated project, runtime-data label and enabled Alpha flags;
- automated A2 result, open accepted deviations and any human step explicitly approved for reuse.

Stop as `BLOCKED` if the page, project, model, device, Provider, Executor or declared deployment route differs from the A2 candidate. Do not repair source, change flags or silently switch fallbacks during A3.

## 2. Platform lifecycle before the business journey

1. Verify microphone grant, denial and revocation each produce a visible truthful state and leave text Chat usable.
2. Restore permission, select the declared device, then exercise device change or loss and recovery without stale capture or playback resurrection.
3. Verify autoplay/user-activation handling and that hidden/background/resume transitions do not duplicate submission, lose the current truth or silently keep an unauthorized microphone active.
4. Refresh/reconnect the same page and confirm no duplicate Agent/Tool/Task dispatch, old response audio or foreign task target appears.

If candidate scope uses non-localhost deployment, also verify HTTPS/WSS or equivalent secure context, proxy routing, CSP/CORS and WebSocket/transport diagnostics. A localhost candidate records that controlled-test topology explicitly and does not claim public deployment.

## 3. P1 — physical speech, correction boundary and playout

1. Start the real physical microphone and speak a fixed-corpus request containing at least one technical or critical token.
2. Observe ordered partial/final/cancel behavior where the selected route supports it. Inspect or clarify uncertain critical text, then explicitly commit the final text.
3. Verify partial/unconfirmed input caused zero Agent, Tool or Task mutation and only the committed text reached the real Agent.
4. Verify the truthful response is displayed, synthesized through the declared route and heard completely.
5. Stop the exact response during a second playout and verify no stale chunk returns and no wrong response/round/task is cancelled.
6. Verify successor capture starts or the declared fallback is shown, then stop it without a second unintended submission.

Record the A2 fixed-corpus p50/p95/sample/failure report by reference; do not estimate latency from the live presentation.

## 4. P2 — realtime conversation under slow work

1. Submit a request that forces one safe read-only real Tool operation; verify the exact Tool fact, visible final result and audible result.
2. Start a deliberately slow Harness/Agent round. While it is running, continue multiple voice Turns.
3. Interrupt or revise the exact current response. Verify microphone/media remain responsive, old output is fenced, the correction targets the correct response/round and history contains only presented facts.
4. Observe bounded working/progress behavior under load. A synchronous slow-Harness wait on the realtime hot path, cross-response cancellation or stale UI/audio/history effect is a failure.

## 5. P3alpha — structured and committed natural-language control

Using one isolated safe project:

1. Through the authorized structured UI/API path, exercise `create`, `get`, `list`, `status`, `events` and exact `cancel`; verify stable task/command/attempt identities and truthful replay/conflict behavior.
2. Issue an ambiguous or unconfirmed natural-language task request and verify zero task mutation plus a clarification/confirmation prompt.
3. Commit and confirm a safe natural-language create. Verify Task Core, real D0 Executor, TaskEvent and WorkProgress provenance on the origin surface.
4. Query status and cancel the exact task through committed text or voice. Verify wrong-task/wrong-scope mutation and partial-command effects remain zero.
5. Refresh/reconnect while a task is active, then restart the applicable service boundary. Verify exact active/terminal/interrupted/unknown/pending reconciliation and no silent rerun.
6. Invoke a full-P3-only operation such as pause/resume only if safe, and verify explicit `unsupported` unless an independently accepted stretch contract exists.

## 6. Joint P2/P3alpha non-blocking journey

Run one slow conversational round and one detached task concurrently:

1. Continue multiple voice Turns while both remain active.
2. Interrupt/revise only the conversational response; verify the detached task is unchanged.
3. Query or cancel only the named task; verify playback, response and round are unchanged.
4. Observe `accepted/running/blocked/decision_required/terminal` progress as applicable. Notification must be Runtime-arbitrated rather than direct Task→TTS.
5. Verify every progress fact maps to the exact work/task/attempt/source sequence and the terminal outcome is exact.

Cross-target cancellation, partial-speech mutation, stale post-fence effects or unresponsive media is an Alpha failure.

## 7. Degradation, privacy and recovery

1. Exercise the selected safe Speech/Media/Provider failure profile and verify a bounded visible error plus usable text fallback.
2. Exercise the selected safe Executor failure profile and verify exact failed/interrupted/unknown/pending truth without false success or duplicate side effects.
3. Inspect the declared browser storage, URL/query, client/server logs, Context, TaskEvent and WorkProgress surfaces for credentials, unauthorized content and raw audio. Any long-lived Provider credential or default raw-audio persistence is a failure.
4. Confirm the A2 route/metric trace can reproduce the declared Alpha latency, queue, cancel/fence and failure facts or points to an explicitly accepted deviation.

## 8. Closeout and decision record

1. Exit Live Voice and confirm microphone, capture/playout, timers and reconnect loops stop.
2. Settle or truthfully record every task/attempt/outbox/owner/lease; confirm the isolated project and Git worktree have only the expected effect.
3. Stop dedicated frontend/Gateway/AgentServer services and confirm ports are released.
4. Confirm the worktree remains clean and the tested source did not change during A3.
5. Record each section as `PASS`, `FAIL`, `BLOCKED` or `NOT APPLICABLE`, with the reason for every N/A or reused observation.

The final result must use one [Alpha acceptance](../validation/ALPHA_ACCEPTANCE.md) outcome:

- `PASS — INTEGRATED WEB ALPHA`;
- `PARTIAL`;
- `BLOCKED`;
- `FAIL`.

Recommended closing statement:

> This A3 run used the exact A2 Integrated Web Alpha candidate. The declared desktop Chrome product path passed the applicable P1, P2, P3alpha, joint interaction, platform lifecycle, degradation, privacy and cleanup observations listed above. The result does not claim full P3, production authentication, broad browser/mobile compatibility, public deployment or RC/Production readiness.
