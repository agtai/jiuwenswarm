# Three-stage session repair

Source baseline: Host `1b38df02cf`, SDK `7c81d886d1`.
The user authorized three stages and multiple local commits, prioritizing proven
fixes over commit count. No history rewrites or remote updates are authorized.
After end-to-end repair, audit every change against the established root causes
and remove incorrect fixes, unnecessary compensation and temporary diagnostics
that no longer provide useful evidence.

## Stage 1 — Task correctness (Tier 2)

Bind task checkpoints before the real Harness supervisor starts. Preserve the
native callback mechanism, exact task/session identity and scope revocation.
Running adjustments must reach the next model boundary; file mutations must
pass the current file plan. Preserve specific safe failure reasons. Verify the
real Host/Harness seam, cancellation/stale isolation and real project/SQLite
delivery. Audit read scope against existing authority; do not invent a broader
permission policy. No changes to user runtime data or automatic task replay.

## Stage 2 — Voice stability (Tier 2)

Measure and repair confirmed local audio admission bottlenecks, context-read
recovery and obsolete activation retries. Preserve playback/history truth,
authorization and interruption. Do not change the deferred prepared-response
timeout, buffering or latency policy to mask failures.

## Stage 3 — Verification and remaining faults

Verify the deployed changed boundary in the current environment, use a second
environment only if available, and fix implicated initialization faults.
Physical audio and unavailable environment evidence remain explicitly open.
Each stage receives scoped checks and review before its commit; a green test
count does not establish human acceptance.

## Progress

Stage 1 implementation and scoped checks pass; deployment acceptance remains
open. Host `ee1eb695` pairs with SDK `b5534de51`. Stage 2 source/timeline investigation has started; no
Stage 2 behavior repair yet; passive diagnostics are being completed. Stage 3
has not started.

### Stage 1 evidence

The Host now enters the existing native scoped callback rail before preparation
creates the Harness supervisor. It binds the exact root before submitting input.
Failed preparation does not clean up an existing session owned by another call.
AgentCore preserves typed file-plan failure causes and logs only normalized
codes, exception type and source location, not arbitrary exception payloads.

- The baseline Host method, loaded in an isolated test process without changing
  source or the service, fails all four initial supervisor regression cases.
- The repaired real supervisor/ReAct boundary passes nine cases: adjustment
  adoption, rejected adoption with zero model calls, planned/unplanned writes,
  duplicate preparation, and delayed model/tool callbacks after normal exit and
  cancellation. The latter execute while the outer task checkpoint is still
  open and prove that facade scope revocation prevents their effects.
- Callback/file-plan checks: 54 passed (before adding the four delayed-callback
  cases and duplicate-preparation case). Targeted project adjustment/cancel and
  real facade checks: 33 passed, 121 unrelated cases deselected.
- SDK real Git/SQLite application checks: four passed, including typed and
  latched failure causes, private error redaction and unchanged original files.
- Independent read-only diff review found no introduced correctness defect.
  Its delayed-supervisor coverage gap is addressed by the four cases above.

These checks do not prove deployed model behavior or audible playback. The
original Hangzhou adjustment did execute late in isolation, followed by failed
delivery; its original generic error does not establish the precise final cause.
Existing broad read permissions remain under audit; no new permission policy
has been introduced. Runtime tasks and project files have not been replayed or
modified during this repair.

### Stage 2 investigation

An isolated real Native owner/runtime control admitted 50 batches of 16 audio
observations (800 total): median 2.97 ms, maximum 19.89 ms on this host. This
does not reproduce the deployed 1,487 ms batch and cannot establish browser or
Provider fault. The slow deployed sample's 0.038 ms lock wait measures only the
outer composition lock. Production injects a separate shared admission lock,
which bypassed the Native owner's default observed lock. That production lock
now uses the existing passive ObservedAsyncLock. Slow runtime operations also
report queue wait separately from synchronous callback duration; no raw content,
new timeout, buffer size or scheduling priority is introduced.

The 8.28 s context read includes 2.64 s authorization, 0.96 s Task read,
0.04 s history read and 1.09 s projection restoration. Other uninstrumented work
and scheduling account for the remainder; this is not proof of a single database
or Git bottleneck. Fresh authority rechecks remain in place.

The admission-lock diagnostics and Native owner regressions pass 40 cases.
Runtime-loop checks pass 43 cases, including separated wait/processing metrics
and a broken diagnostic sink preserving the successful operation result.
Gateway startup now reports `MEDIA_NATIVE_BUSINESS_CONTEXT_START_FAILED` for
initial context-read failure before Provider connection. Provider-start failures
retain their existing code and cleanup owner. Three focused startup checks pass.
These diagnostics still need deployed evidence before claiming the audio
bottleneck or recovery failure is fixed.

Stage 2 independent read-only review completed with no actionable introduced
defect. It does not close the unresolved performance/recovery defects.
The user resolved the commit-count question and authorized continuation. The
reviewed diagnostic build will be committed and deployed through the official
launcher, which requires clean source. Final acceptance must include a second
review of necessity: keep only changes supported by root-cause and regression
evidence; report removed ineffective fixes explicitly.

The earlier page's diagnostic stream contains 40 notification route-not-found,
37 stale activation-generation and 42 generic Task-query failures. Existing
frontend code already treats NOT_FOUND as definitive for an individual request,
and predecessor reconciliation already handles stale activation generations.
Therefore adding another generic retry classifier would not establish a fix:
the page/journal recovery cycle and retained operations still require reproduction.
