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

Stage 1 scoped checks pass; Host `ee1eb695` pairs with SDK `b5534de51`.
Host `c58ee065` adds Stage 2 diagnostics and startup error classification.
The official launcher deployed this pair and passed its real speech/identity
probes. The subsequent user session provides bounded Stage 3 evidence below;
overall Task delivery and Voice stability acceptance remain open.

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

### September 15 deployed session and scoped follow-up

Session `web_1a0a216a82b_dc64829d305e`, Host `c58ee065`, SDK `b5534de51`.
Raw evidence stays in local `logs/SESSION_20260915_0043_REVIEW.md`, the service
log `swarm-20260914-212432.log`, SQLite stores and retained project baselines.
Times here are local UTC+02:00. This is not a complete product acceptance.

The Shenzhen creation and adjustment share one Task and one execution attempt.
The 00:43:58 adjustment was adopted at the 00:44:16 model checkpoint; both later
writes contain the empty afternoon. APPLIED means requirement adoption, not
completed artifact delivery. The separate Hangzhou Task waited for the project
executor and was cancelled without an execution attempt. Weather Work completed
with a saved fetched result. This proves the previous missing Harness callback
repair worked on this path; running cancellation remains unproved here.

The Shenzhen Task failed at `_attempt_patch` with NO_EFFECTIVE_TARGET_CHANGE:
both writes equal the pre-existing itinerary after Git line-ending normalization.
The original file hash matches both predeployment baselines. Empty-diff failure
is the current executor contract, not another missing adjustment callback.
Allowing verified existing artifacts as success versus requiring a separate new
artifact is a pending user product decision. Merely removing the empty-patch
guard would conflict with artifact collection, apply and durable recovery.

The apparent 21.70 s audio delay is not proof of an admission stall. For the
generation 18 notification, source event `event_EO9iZQLioX6jiPpT7nSci` arrived
at 00:45:35.533. Predecessor presentation completed at 00:45:42.158; the prepared
continuation was promoted at 00:45:42.812. Frame 0 was admitted at 00:45:43.006;
frame 716 mapped at 00:45:56.963. The 14 seconds between these frame positions
is consistent with the existing 20 ms sample-credit release in
`_prepared_delivery_control` / `_release_event`. The last admission RPC took
26 ms. No timeout, buffer or pacing change is justified by this sample. Separate
maximum lock/RPC waits and earlier audible stalls remain unresolved.

A bounded Tier 2 feedback repair follows a proven race: a task.cancel proposal
was waiting for authority revalidation when speech_started arrived at
00:44:37.208. The source became interrupted at 00:44:37.209; Runtime rejected it
as NATIVE_DELEGATE_RESPONSE_STALE at 00:44:37.224. Gateway then incorrectly
published failed after interrupted. Keep the Runtime rejection and zero business
acceptance; when that exact interaction/generation has a retained barge fence,
retire the call as interrupted without overwriting its state with failed.
Other stale generations, foreign interactions and actual conflicts retain their
failure feedback. Owned surfaces: gateway delegate error handling and focused
gateway regressions. No change to Task cancellation, durable results, transport,
authorization, Provider timing or recovery policy. Acceptance requires a delayed
rejection/barge race, wrong-identity and unrelated-error controls, existing
accepted-result preservation checks and independent scoped review.

The follow-up passes 12 scoped checks in one process with `--no-cov`: gateway
barge rejection controls, accepted receipt/Task association preservation,
reservation ordering and Native cancelled/older-source isolation. Earlier
overlapping coverage runs produced a shared `.coverage` report error and were
not credited as complete; the final check does not claim coverage measurement.
An independent read-only review found no introduced defect (static review,
without independently verifying the private logs). The production delta is
10 added / 1 removed lines; there is no new state owner or retry mechanism.
The deferred result-semantics decision, earlier recovery/audio faults and
read-scope audit remain open. This follow-up is not yet deployed or physically
accepted.
