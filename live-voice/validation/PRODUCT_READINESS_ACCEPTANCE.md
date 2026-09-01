# Live Voice product-readiness acceptance

> Current state and exact candidate: [STATUS](../STATUS.md)
> Human product journey: [PRODUCT_READINESS_SHOWCASE](../demo/PRODUCT_READINESS_SHOWCASE.md)
> Environment/startup: [E2E runbook](../runbooks/E2E_RUNBOOK.md)
> Verification/review policy: root [TESTING](../../TESTING.md)
> Architecture: [ACG v1](../architecture/ARCHITECTURE_CONTRACT_GATE_V1.md)
> and the historical [complete solution](../architecture/FULL_SOLUTION_2026-07-30.md)

> Sequencing note (2026-08-19): [D-086](../decisions/DECISIONS.md) keeps this
> contract authoritative for a controlled product-readiness decision but no
> longer requires that decision before P3-1 starts. The failed `f24dd17d`
> attempt remains FAIL; its post-TTS continuation defect is deferred to P1/P2
> completion and must close before a later PASS or feature-complete claim.

This contract decides whether one identified Live Voice desktop-Web source is a
truthful controlled product candidate. It uses product capability/module status
and does not use numbered delivery stages as progress or acceptance.

Under [D-084](../decisions/DECISIONS.md), this is the first of four cumulative
completion boundaries. Passing it grants the named controlled-candidate credit;
under D-086 it is no longer the sequencing Gate for P3 expansion. It does not
prove the feature-complete matrix in STATUS or trigger integration with
`develop`.

The accepted Integrated Web Alpha remains a historical exact-source result. It
does not automatically pass later hands-free, running-task adjustment,
authoritative result or terminal-notification changes. Conversely, defects in a
later candidate do not rewrite that historical result.

A pass here is not feature-complete, productized or RC/Production approval.
Complete P1/P2/P3, multiple addressed Tasks, full Task operations, supported
D1/D2 durability, generalization, cleanup, latency closure, competitor
comparison and independent cumulative review remain in the feature-complete
boundary. Production authentication, multi-tenancy, public deployment, broad
compatibility, production-scale SLOs and release operations remain later.

## 1. Candidate entry

- STATUS identifies the product boundary, current defects and exact source.
- Every changed capability/module has risk-proportional automated evidence and
  the required review under root TESTING.
- The candidate composes formal product routes rather than crediting a fake,
  Demo substitute or compatibility path as the completed capability.
- Required Provider, Agent/Tool, Task/Executor, browser/device, project,
  deployment and isolation inputs are available. Missing external conditions
  produce `BLOCKED`, not an invented pass.
- No known Critical/High product-truth or forbidden-side-effect finding remains
  open in the accepted scope.

## 2. Tested-source and environment boundary

- Identify the source containing every runtime, schema, Adapter, flag, fixture,
  model/default and documentation input used by the run.
- The final automated and human acceptance source is clean and has an explicit
  relation to its branch/upstream.
- Record sanitized OS, browser/version, secure origin, microphone/output,
  Provider/model, Agent/Tool, Executor, isolated project/data and network facts.
- Credentials, private configuration and runtime data remain outside Git.
- A source, behavioural input, route or environment change invalidates the
  affected evidence; it cannot silently inherit the prior result.

## 3. Shared contract and truth requirements

- Versioned identity, scope, authority and Command/Query/Result/Event envelopes
  bind exact session/project/interaction/turn/response/round/task/attempt and
  generation identities.
- Only committed final input may reach Agent, Tool or Task mutation. Partial,
  ambiguous, stale, wrong-scope and unconfirmed inputs cause zero forbidden
  side effects.
- ACK, accepted, queued, running, timeout and unknown never masquerade as
  applied, presented, terminal, successful or result-available.
- Cancel/fence, WorkProgress, Context, capability/error/fallback and restart
  semantics retain exact provenance and explicit known/unknown truth.
- Unsupported operations remain explicit. A legacy Adapter is not relabeled as
  the formal v2 owner.

## 4. Speech and browser audio

Pass the real `microphone → authoritative STT final → Agent → TTS → browser
playout` path:

- permission/device/autoplay/visibility lifecycle is truthful and recoverable;
- partial/final/cancel and audio chunk/text-span order/provenance are exact;
- critical-token and side-effect clarification cannot be bypassed by an
  untrusted surface;
- exact-response stop prevents stale playout and never cancels another response,
  round or Task;
- Provider/permission/media failure leaves an explicit bounded state and usable
  text fallback;
- raw audio and credentials are not persisted or exposed by default;
- required latency and quality observations record p50/p95, sample/failure count
  and route, rather than relying on a subjective estimate alone.

## 5. Realtime conversation and presentation

- Real committed text reaches the real JiuwenSwarm Agent and applicable tools.
- Slow Agent/Tool work does not block bounded media, progress or a supported new
  interaction.
- Response/generation and presentation ownership fence stale UI, audio and
  history effects.
- Barge-in/stop/revise targets only the exact current response and preserves
  truthful presented history.
- Progress is source-backed, bounded and Runtime-arbitrated; Task or background
  work cannot write direct Chat/TTS lifecycle truth.
- Cross-response/round/task/playback cancellation and stale post-fence effects
  are zero.

## 6. Task, Executor and result truth

- Authorized create/get/list/status/cancel/events use the formal Task owner with
  stable command/task/attempt identities and truthful replay/conflict behavior.
- A committed safe create reaches the real Agent/Executor path for the isolated
  project; accepted/queued does not count as application or completion.
- Running-task adjustment is bound to the exact active Task/attempt, reaches the
  authoritative application/Executor path, and produces a verifiable intended
  project/result change. Dialogue acknowledgement alone is failure.
- Task state, result and terminal notification are derived from authoritative
  TaskEvent/result/application facts. Missing or oversized result context is
  explicit and cannot become a fabricated success summary.
- Retry, timeout, orphan and restart reconciliation are bounded, non-duplicating
  and truthful about active/terminal/interrupted/pending/unknown outcomes.
- Wrong-task/scope mutation, partial command effects, silent rerun and duplicate
  terminal/result effects are zero.

## 7. Combined hands-free product journey

Run foreground conversation and one detached background Task through a single
real microphone/TTS journey:

1. create the Task from committed speech and verify the exact authoritative
   task/attempt;
2. continue normal conversation while the Task is running;
3. issue one running adjustment and verify it is actually applied, not merely
   acknowledged;
4. query status and later result without false completion or missing-context
   invention;
5. interrupt/revise only the foreground response while leaving the Task alive;
6. receive one exact terminal/result notification through Runtime/TTS arbitration;
7. exit and prove capture, playout, timers, reconnect and leases stop cleanly.

The journey fails if media becomes unresponsive, dialogue claims unproven Task
truth, the adjustment does not reach the authoritative path, the result is lost
or fabricated, or terminal speech targets the wrong response/task.

## 8. Platform, degradation, privacy and recovery

- Record the exact supported desktop browser/OS/origin/device/network baseline;
  do not extrapolate it to a public compatibility matrix.
- Non-localhost deployment uses HTTPS/WSS or an equivalent secure context and
  proves applicable proxy/CSP/CORS/WebSocket routing.
- Refresh/reconnect, page hidden/resume, permission/device loss, Provider/media
  failure and selected Executor failure produce no duplicate dispatch, stale
  audio resurrection or cross-scope state.
- Feature/capability off preserves the supported text/legacy boundary without
  constructing formal owners or claiming formal capability.
- Browser storage, URLs, logs, Context, TaskEvent and WorkProgress contain no
  long-lived Provider credential, raw secret, unauthorized content or default
  raw-audio persistence.

## 9. Final decision

Review the cumulative candidate diff and integration seams, run all applicable
automated/static/build/real-path checks, then complete the product showcase once
on the exact clean source. Reuse a prior human observation only when source,
route and relevant environment are unchanged and the later delta cannot affect
it.

Record one result:

- `PASS — CONTROLLED PRODUCT-READINESS CANDIDATE`;
- `PARTIAL — runnable, but one or more required product truths remain open`;
- `BLOCKED — a required external condition or authority decision is missing`;
- `FAIL — a committed invariant or required real path is violated`.

The record must list tested source, automated/review commands, human
observations, unresolved gaps and every accepted deviation. A pass remains
bounded to this contract; it does not trigger `develop` integration or claim
feature-complete, productized or RC/Production readiness.

## 10. Current bounded result — 2026-09-02

**PASS — CONTROLLED PRODUCT-READINESS CANDIDATE** on exact product source
`83fde562284e96df12f2e2546797c4703a75132b`.

The ordinary-Chrome 8+2 microphone/Agent/Task/TTS journey passed on that clean
source, and a separate Session completed the final Tier-3 changed-boundary
review with `Critical 0 / Important 0` and `Assessment: Ready`. The review made
no source change, so the source-, route- and environment-bound human evidence
remains applicable. See the sanitized
[human evidence](../evidence/P3_9_CUMULATIVE_PRODUCT_ACCEPTANCE_20260902.md) and
[final review](../reviews/P3_9_FINAL_INDEPENDENT_TIER3_REVIEW_2026-09-02.md).

Accepted deviations remain explicit: the broad frontend diagnostic is
`493 passed / 5 failed / 1 skipped`, with the five mounted timing failures
outside the P3-9 repair overlay and a representative failure reproduced on the
comparison source. The final review therefore ran the focused changed-boundary
candidate rather than relabelling or rerunning the broad diagnostic as a pass.

This result grants only the controlled-candidate boundary. It does not trigger
`develop` integration and does not claim feature completeness, productization,
fixed-corpus latency/generalization, production authentication or tenancy,
public deployment, SLOs, RC or Production readiness.
