# Rehearsal recovery follow-up — 2026-09-05

## Authorized boundary

The user requested repairs after rehearsal `web_1a072486128_b039b6189b78`:
recover unacknowledged completion after Live Voice closes/reopens, remove redundant
confirmation for an explicit local successor request, audit other operation
confirmation paths, and investigate notification/model/delivery latency. Baseline
`3e56341feaa988a946453e3fc8fc0797be8a7b1e`; private evidence is under ignored logs.

| Owner / risk | Intended behavior and owned surfaces | Acceptance |
|---|---|---|
| Notification / Runtime / Integrated Web — Tier 2 | Complete notifications survive off/on and refresh; foreground release and failure recovery advance the exact unread presentation. Registry, Progress Return, mounted panel and their existing tests. | Reproduce the actual off→complete→remount→on sequence, foreground races and retry; prove completion delivery and ACK, no duplicate after ACK, no stale audio revival or other Task/scope effects. Record any remaining physical limitation. |
| Voice–Task bridge / local consent — Tier 3 | A committed explicit local successor is authorized like local creation, with exact predecessor and capability checks; ambiguous requests still clarify. Internal semantic schema/validation, Registry, composition capability checks and real Store tests. | Positive successor preserves original and lineage, replay creates once; unclear/external/unsupported/stale/wrong-scope cases have zero forbidden mutation. Audit all supported operations without silently extending other operation policy. |
| Profiling diagnosis — read-only | Explain 19.7-second terminal-to-audio delay, 77-second confirmation, 11-second post-model tail, and prior/current foreground timing. | Distinguish measured model generation, dispatch/queue, transport and audio clocks. Use an isolated reproduction if necessary; disclose unresolved attribution rather than assuming a replacement model fixes it. |

Existing protocol and durable ACK/authority rules remain. No fixed travel answers,
output rewriting, artificial delays, model/provider changes, real Task mutations
or remote Git updates. Arithmetic and packing intent remain deferred. Performance
code changes beyond the reproduced notification repair need their own recorded
scope; diagnosis does not grant a global confirmation bypass. Applicable checks
and independent review follow root TESTING.md; source-level automation is not
microphone/speaker acceptance.

## Findings, implementation and verification

### Notification recovery

The rehearsal's restored selected Task acquired a TEXT subscription before Voice
Start, despite durable voice origin. A prepared but unconsumed TEXT prefix then
blocked later delivery (`_ProgressPresentationDeferred`, earlier presentable event
unconsumed). This was not a missing Task result or an AgentModel failure.

Integrated Web now waits for authenticated origin discovery before selecting the
subscription. A recovered voice Task waits for Start and uses its independent
voice owner. Unknown discovery is not treated as an empty successful discovery.
P1-off preserves the existing TEXT path and does not rebuild on P2 changes.
Discovery/state are read from the same current owner after asynchronous cleanup.
No ACK, watermark, history, timing constant or notification text is fabricated.

The old test omitted the restored selection. The expanded mounted test fails on
baseline with two premature progress activations instead of zero. It now covers
close → completion → remount/selected result → Start → TTS/browser source start →
playout receipt → ACK → second remount without replay, discovery failure/recovery,
P1-off, transient reads and delayed Exit cleanup. Its server watermark is a mock;
actual SQLite authority/ACK and reconnect are separately covered by backend tests.
The exact-P2-observation test now flushes React effects between actions instead of
waiting for an effect from inside a single unfinished `act`; playback/ACK oracles
are unchanged.

### Successor consent and operation audit

Explicit committed local `task.create_successor` now follows local creation's
consent path. The actual predecessor, current capability, original requirement
sources, normal durable consent claim and final authority reread remain required.
Original Task/result metadata and lineage remain immutable; replay creates once.

Independent review found two additional seams in the same continuation:
`local_artifacts + answer_clarification` was rejected, and the final reread tried
to consume the already-used target clarification a second time. A target-only
answer now retains exact pending arguments (including preserved original user
requirements); the final reread carries the same existing clarification digest.
Changing the retained operation/arguments remains rejected. This does not make a
hypothetical or external-effect request an authorized local delegation.

| Natural operation | Current consent behavior |
|---|---|
| create / create_successor | Exact explicit local artifacts can execute on the current committed request; external/unclear work does not bypass consent |
| adjust / cancel | Exact explicit local control uses current consent; ambiguous targets clarify |
| get / list / status / events / result | Read-only; no second confirmation |
| update / reprioritize | Still use the existing separate confirmation; reported as remaining operation-policy scope, not silently broadened |
| pause / resume / provide_input | Unsupported by the current Direct boundary; not a missing confirmation bypass |
| retry | Separate structured lifecycle/admission operation; not added to natural semantic routing here |

### Measured latency and limits of attribution

Times below are rehearsal host UTC+2, not the travel fixture's simulated timezone.
Private raw evidence and content-free derived tables remain under ignored
`logs/rehearsal-web_1a072486128_b039b6189b78/`.

* A2 Executor terminal: 18:10:39.992; cleanup settled 40.230; notification preparation
  began 58.291 and finished 58.393; first browser audio clock 59.691. The 19.699 s
  consists of 18.299 s before preparation, 0.102 s preparing and 1.298 s to audio.
  Current service processes have no `JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS`
  override: source default is 30 s. Executor completion does not wake that loop;
  Core ingests status periodically and preserves the Executor's old `occurred_at`.
  This identifies a polling wait in the path, not 19.7 s of TTS. Actual reconciliation
  tick/ingestion timestamps are absent, so the entire 18.299 s cannot be assigned
  quantitatively to a specific poll from this log alone. An Executor completion
  wakeup plus periodic recovery, with an ingestion span, is the appropriate next
  performance design to evaluate; the interval is not blindly shortened here.
* “確認” committed 18:08:15.240; semantics took 2.275 s and A2 was created at
  18:08:18.286. The spelling was understood. The foreground model ran from
  18:08:19.271 to 18:09:19.928: 60.657 s, first output after 0.429 s, 7,224 chunks,
  longest chunk gap 2.694 s. These are chunks, not a token count. The final spoken
  reply had 131 characters; short visible output did not imply short generation.
* At model settlement the Bridge had processed event 4908; final event 7222 arrived
  at 18:09:30.031, and the Agent round settled at 31.198. Roughly 2,314 events still
  traversed the output pipeline: 10.103 s to final, 11.270 s to round settlement.
  No new model call or output-rewrite/verification call accounts for this tail.
  The evidence identifies queued stream delivery/draining. It does not isolate
  the remaining cost to one SDK function, CPU, logging or I/O; a controlled SDK
  streaming profile is needed before modifying that path. A different model may
  reduce generation and chunk volume, but cannot guarantee removal of this tail.
* First audio at 18:09:34.494 is 79.254 s after commit; the UI's roughly 77-second
  answer timestamp measures an earlier point and is not an exact audio latency.

Comparable foreground examples (seconds; model column sums observed AgentModel
calls, excluding the separate semantic classifier):

| Operation | Previous UI / model | Current UI / model | Interpretation |
|---|---:|---:|---|
| Initial analysis | 38.20 / 31.036 | 60.00 / 52.495 | Most of the increase is model generation |
| Delegate A | 8.43 / 5.447 | 15.74 / 7.236 | Model plus non-model delivery increased |
| Delegate B | 11.26 / 2.899 | 24.67 / 9.002 | Both components increased |
| Adjust A | 3.26 / 0 | 16.46 / 5.786 | Previous fixed status answer was retired; current truthful Agent explanation adds a model call |
| Query A | 2.39 / 0 | 13.50 / 3.990 | Same change of reply path; not comparable as a model-only benchmark |
| Final route/cost | 22.69 / 10.037 | 6.87 / 2.970 | Current run is faster |
| Hotel departure | 12.19 / 5.277 | 22.45 / 12.286 | Current Agent made three calls instead of one |
| A2 comparison | 40.54 / 32.907 | 25.87 / 15.593 | Current run is faster |

These runs differ in source, question sequence, Task facts and model/tool calls;
they are not a controlled model A/B. Background A/A2 model totals fell from
603.322/713.362 s to 427.440/118.007 s, which does not predict foreground reply
latency. Keep the accepted next step: change AgentModel separately, then repeat
the same scenario and compare model duration, post-model drain, semantic route,
notification ingestion and first-audio clocks. No model/provider setting changed.

### Verification and review

Baseline `3e56341feaa988a946453e3fc8fc0797be8a7b1e`; logs under ignored
`logs/recovery-followup-tests/` retain failed reproductions and final checks.

* Semantic Registry full suite: 96 passed; subsequently added same-origin voice
  clarification case: all four direct/clarified text/voice successor cases passed.
  Actual parser/Registry/Core/SQLite, controlled model and Executor. Scope, target,
  capability drift, unfinished predecessor, external request, original retention
  and replay fences are included. Physical file production is not claimed here.
* Backend affected selection: 61 passed / 5 failed. All five failures reproduce
  with baseline backend modules loaded in an isolated process: one Native delegate
  fence and four legacy accepted-event/retry-prefix expectations. No new failure.
  Passing paths include real SQLite presentation authority/ACK, terminal after
  owner close/recovery and successor lifecycle/concurrency/fault rollback.
* Mounted affected selection: 12 passed. Independent final frontend review ran
  11 relevant cases, all passing. An adjacent AUDIO→TEXT test has the same 3-vs-2
  activation-count failure on baseline/current; retained as existing broader
  coverage debt, not silently changed to a passing count.
* `npm run build`: TypeScript and Vite passed; existing locale duplicate-key and
  chunk-size warnings remain. This ordinary build is verification, not the
  controlled deployment default. Deployment uses the accepted launcher.
* Independent successor review: original clarification finding fixed; subsequent
  13 targeted checks passed and the exact origin digest/final reread reviewed.
  Independent notification review: P1-off/discovery-failure findings fixed and
  retested. Scoped cold diff and whitespace/link review complete before commit.

Module automation supports these bounded repairs. Broader legacy failures,
unmeasured hot spots and a clean physical microphone/speaker journey remain open;
this is not cumulative product acceptance.

### Deployment

Local controlled deployment completed at 19:48 (UTC+2), using clean source
`0650e7ef39` plus predecessor consent commit `017597309`:

```powershell
.\scripts\live_voice\start_hands_free_demo.ps1 -RuntimeProfile formal-web-validation -AllowDirtyProject -PreflightOnly -NoBrowser
.\scripts\live_voice\start_hands_free_demo.ps1 -RuntimeProfile formal-web-validation -AllowDirtyProject -RestartExisting -NoBrowser
```

`AllowDirtyProject` preserved two existing changes in the private demo project;
the source checkout was clean. Runtime contract verifies Cascade, generation
interruption **true without an enable argument**, validated bundle/backend routes
and real Speech TTS→STT/receipt/identity rejection probes with zero business
side effects. Existing VAD/startup and AgentModel settings were not changed.
Service log: ignored `logs/swarm-20260905-194833.log`.

The served `/assets/index-DNnI6BSZ.js` matches the local controlled bundle:
SHA-256 `a9b3e24f522a82a5c653773b98dc633b165c396efa9a7891d5ed525067feb31f`.
Pre/post read-only checks found no nonterminal Tasks, identical Task/event/result/
consumption row counts and identical outcome counts (41 completed, 8 cancelled,
13 failed, 4 interrupted). Original rehearsal voice ACK watermarks remain A=3,
B=3, A2=5 with their original timestamps. No rehearsal page was opened, result
document edited or completion notification consumed. Physical reopen/listening
acceptance remains for the user's next rehearsal. The subsequent evidence-only
commit does not require another restart.
