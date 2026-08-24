# L0 ordinary-Chrome batch automation review — 2026-08-24

## Post-run disposition — 2026-08-25

This dated disposition updates current credit without rewriting the
pre-implementation and source-review facts below. Behaviour source
`ba06d9825c92602066756118dd5cac9572c22827` completed the ordinary installed
Chrome warm path with one non-counted warm-up, first-audio `20/20`, dedicated
barge-in `20/20`, zero failed/dropped attempts and a sanitized cross-layer
aggregate. Exact values and log review are in the
[warm closure evidence](../evidence/L0_WARM_STEADY_STATE_CLOSURE_EVIDENCE_20260825.md).

The attempted transition then disclosed a cross-epoch runner defect not covered
by the source review: the Browser controller treats the warm profile's
`batch_complete` as whole-series completion, while the supervisor proceeds to a
new cold coordinator. The cold epoch remained unattempted and has no result
credit. [D-097](../decisions/DECISIONS.md) explicitly removes cold and
cold-minus-warm from this bounded L0 completion gate, records that defect as
deferred and accepts the warm steady-state baseline. The cold runner branch is
therefore neither fixed nor accepted by this closeout.

Under D-097 the real-path `X` requirement for the bounded warm L0 scope is PASS:
the installed-Chrome/Provider/Browser/Gateway/Runtime/Agent seam ran and its
eligible evidence was reviewed. This does not grant cold, physical-acoustic,
feature-complete, product-readiness or release credit. The original matrix and
pending wording below remain the exact 2026-08-24 source-review checkpoint.

## Pre-implementation scope checkpoint

- Capability: D-095 observability, benchmark and latency closure support.
- Risk: Tier 3. The local-only controller coordinates Browser, Gateway,
  Runtime and Agent measurement labels, while retaining no business or media
  authority of its own.
- Intended behaviour: one explicit user gesture in an ordinary installed
  Chrome page unlocks microphone/playout. A local loopback coordinator then
  drives the unchanged fixed short-dialogue and playout-barge scenarios,
  records one unmeasured warm-up, fences every sample with exact run labels,
  restarts a controlled launcher epoch for every cold attempt, evaluates
  automatic completeness, and emits one sanitized cold/warm aggregate.
- Owned product/test surfaces: the L0 fixed-corpus profiles, local coordinator,
  ordinary-Chrome L0 Web controller, controlled launcher/supervisor, generic
  aggregation provenance, and their focused Python/TypeScript/PowerShell
  tests.
- Explicit exclusions: production-default enablement, shared Live Voice wire
  schema, Agent/Tool/Task policy, Provider/model/billing changes, raw audio or
  transcript retention, isolated Chrome, physical-audibility inference,
  acoustic p95, AEC/double-talk, generation-time interruption, P3 recovery,
  and remote-ref updates.
- Acceptance: feature-off has zero controller or hot-path effects; loopback
  origin/nonce/source/configuration/corpus/epoch identity fails closed; warm
  has exactly one non-counted warm-up; cold admits at most one attempt per
  fresh launcher epoch; every failure/fallback/cancel/drop remains outside the
  inapplicable success percentile; the final report contains attempts,
  eligible/failure/drop counts, both required p50/p95 metrics, cold/warm
  differences and anomaly classifications; ordinary Chrome is used without a
  managed isolated profile.

The implementation, verification, matrix disposition and final evidence are
recorded below only after they exist.

## Implementation and verification

- `l0_ordinary_chrome_batch.py` owns a nonce/origin-bound loopback session,
  in-memory fixed-corpus speech fixtures, exact dynamic run labels, one active
  job, eligibility correlation and the sanitized D-095 report. It does not
  retain audio or recognized text.
- `l0OrdinaryChromeBatch.ts` and the opt-in ChatPanel mount expose the existing
  production voice start/stop owner to one explicit user gesture. They run the
  warm-up, short first-audio and long-playout/prerecorded-voice-barge journeys,
  snapshot only the existing content-free L0 envelopes, and continue after
  separately accounted sample failures. A lost completion response remains an
  unknown outcome and is recovered through the exact session/job rather than
  converted to a false failure.
- The first real ordinary-Chrome attempt on `15b389b54` exposed a runner defect
  before any sample became eligible. The fixture was audible through a Jabra
  headset, while the product capture used the headset microphone with requested
  AEC/NS/AGC. No fixture therefore entered Live Voice; each empty Realtime STT
  session was closed at its idle boundary and logged a later
  `STREAMING_SPEECH_PROVIDER_UNAVAILABLE`. Direct same-config socket and full
  transcription-session probes passed, proving that warning was a downstream
  symptom rather than the initiating failure. The invalid directory contains
  no attempts or report and is not resumable or creditable.
- The repair gives the opt-in controller an in-memory WebAudio capture stream.
  Every fixture is connected both to ordinary Chrome playout and to that stream;
  the unchanged Browser audio adapter, dedicated media route, Realtime STT,
  Agent and TTS path consume it. The factory is installed only by the exact
  nonce/query controller and is removed on controller close. Ordinary pages
  still open the selected physical microphone and request AEC/NS/AGC. This
  matches the already nonphysical D-096 profile and does not claim acoustic,
  microphone, AEC or double-talk evidence.
- `run_l0_ordinary_chrome_series.ps1` opens installed Chrome once, then invokes
  the controlled launcher for one warm epoch and fresh cold epochs. Later
  epochs reuse a build only when HEAD, frontend tree, lockfile and bundle
  digests all match. The ordinary block uses `--new-tab` only; it has no
  user-data-dir, profile, debugging port or isolated-Chrome operation.
- The fixed case set remains 13. Two nonphysical ordinary-Chrome profiles were
  added, making 9 profiles and corpus SHA-256
  `a51a17289edf1dbcd83da66526d2175e2f84c516240d585e9a78b814551e99d6`.
  D-096 records the required D-095 re-evaluation; historical old-digest
  evidence was not rewritten.

Verification on the implementation worktree:

- Python affected L0 and portable-launcher regression: `76 passed`.
- Ordinary-Chrome browser controller: `5 passed`; Browser audio adapter:
  `105 passed`; Browser L0: `5 passed`;
  build profiles: `2 passed`.
- Affected Formal Web integration: `479 passed`.
- `npm run build:live-voice`: PASS; the pre-existing duplicate-i18n-key and
  chunk-size warnings remain unchanged and outside this scope.
- Ruff, Python compileall, both PowerShell AST parses and `git diff --check`:
  PASS.

The repaired real Provider + installed-Chrome warm/cold sequence has not yet
completed at this checkpoint. Therefore this review accepts the repaired
source/runner boundary but does not close D-095 or grant result credit.

## Tier-3 matrix and review

| Dimension | Disposition |
|---|---|
| P | Warm-up plus first-audio and dedicated voice-barge controller journeys pass; the aggregate fixture reaches both cold/warm two-metric targets. |
| N | Wrong origin/nonce, wrong job labels, corpus mismatch, extra provenance fields and incomplete browser results reject before forbidden evidence or authority changes. |
| B | Target is exactly 20, port/path/nonce/body/record/attempt limits are closed, warm attempts are bounded to 40 per metric and cold has at most one attempt per epoch. |
| S | Labels move disabled → exact active job → disabled; terminal cold epochs cannot issue a second job, and feature-off exposes no browser control. |
| T | Warm-up is non-counted; sample milestones use the existing ordered aggregate; completion transport loss stays unknown rather than becoming terminal truth. |
| C | The state lock linearizes eight concurrent `/next` requests to one job and sample index; only the exact active job can complete. |
| R | Single-sample failures retain their snapshot, are recorded separately and continue. Coordinator gaps are polled, fresh cold services reuse only a digest-bound build, released ports are awaited, and launcher failure stops its owned coordinator. |
| I | Source, environment, configuration, corpus, origin, nonce, epoch, profile, scenario, sample and evidence-source bindings are exact; cross-label records have zero writes. |
| F | The panel/controller is query-opt-in, ordinary production remains inert, drops/incomplete/fallback/cancel do not enter inapplicable success percentiles, and no operator verdict is fabricated. |
| K | Existing physical session-v6 provenance remains accepted, its isolated collector is unchanged, build profiles pass and the full affected Formal Web suite remains green. |
| X | Production build and the real Browser/Gateway/Runtime/Agent aggregation seam are wired. Actual installed-Chrome/Provider execution remains pending and cannot be replaced by the deterministic tests. |

Cold scoped diff review found and repaired three automation defects before this
record: sample failure stopped the full batch; completion-response loss cleared
the retained snapshot and could be misclassified; and the supervisor could race
the next epoch before the prior coordinator released its port. A fourth cleanup
finding ensured a launcher failure stops its owned coordinator. The affected
checks above were repeated after those repairs.

The repository has no callable independent `/review` facility in this session,
and subagent delegation was not authorized. The required substitute was a
second cold complete-diff review against the pre-implementation acceptance plus
the full affected integration/build run above. Limitation: independent-review
credit and the Tier-3 real-path cell remain open until the ordinary-Chrome run
is completed and its result is reviewed.

The later post-run disposition above closes that real-path cell only for the
D-097 warm steady-state scope. It does not retroactively claim the original
cold/warm series completed.
