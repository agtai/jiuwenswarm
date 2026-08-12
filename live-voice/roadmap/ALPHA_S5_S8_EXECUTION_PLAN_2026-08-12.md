# Live Voice S5–S8 Integrated Web Alpha execution plan

> Frozen task contract: 2026-08-12
>
> Current progress: [STATUS.md](../STATUS.md)
>
> Pass/fail authority: [ALPHA_ACCEPTANCE.md](../validation/ALPHA_ACCEPTANCE.md)
>
> Human A3 journey: [ALPHA_SHOWCASE.md](../demo/ALPHA_SHOWCASE.md)
>
> Stable module/package map: [WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md](WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md)
>
> Decisions: D-074–D-076 in [DECISIONS.md](../decisions/DECISIONS.md)

This is the active execution contract for `S5/A0 → S8/A3`. It turns the
stage exits into named work that can be assigned, reviewed and declared done.
It does not contain mutable progress, current Git divergence, tested SHAs or
test counts; those facts belong only in STATUS.

**Sectional read contract:** ordinary work reads §1–2 plus only the active task
named by STATUS. Read prerequisite task sections only when their output is
missing or conflicts. Stage planning reads only the current stage section;
S7 reads §5 and complete Alpha acceptance; S8 reads §6 plus acceptance/showcase.
Read the whole file only when auditing or changing the task graph.

Historical W3/W4 rows and completed Wave packets remain useful design and
dependency references, but they are not a queue to replay. The current source
already contains substantial P1/P2/P3alpha implementation. Every A1 task is
therefore **verify first**: retain behavior that already satisfies the Alpha
contract, implement only a proven gap, and never replace formal authority with
a Demo predecessor merely because that predecessor has older evidence.

## 1. Execution rules

Every activated task must declare:

- the task ID below, stage/node, capability track/module and D-046 risk tier;
- exact included source/tests and explicit exclusions;
- whether each acceptance row is `SATISFIED`, `IMPLEMENT`, `VERIFY`,
  `ENVIRONMENT`, `DEVIATION` or `LATER`;
- positive behavior, key negative/fault/flag-off behavior and forbidden effects;
- focused checks during development, the module-close check set and review
  boundary; and
- dependencies, semantic owner and integration owner. Main is the default
  semantic/integration owner until an active packet assigns non-overlapping
  ownership; historical workers or lanes are not current owners.

`SATISFIED` still requires inspection and applicable regression proof.
`DEVIATION` requires an explicit accepted decision before it can close an
Alpha requirement. `ENVIRONMENT` cannot be inferred from source or fake tests.
`LATER` is valid only for an item already outside the Alpha acceptance scope.

D-074 review applies at three boundaries:

1. during development: affected diff self-review plus focused checks;
2. at A1 module/group closure: cold review of the complete scoped diff and one
   independent review or recorded equivalent for changed Tier 2/3 boundaries;
3. at A2: cumulative candidate diff, cross-module seams and complete applicable
   automated/real-path verification.

No task may recreate the retired signed evidence Gate, Replacement Ledger or
fixed manifest. D-032 positive, fail-closed and zero-forbidden-effect invariants
remain mandatory.

## 2. Stage and dependency graph

```text
S5/A0
  S5-01 source/acceptance audit
      └─ S5-02 product + environment decisions
          └─ S5-03 closure graph freeze
              ├─ S6-01 Shared contract and critical-input safety
              ├─ S6-02 P1 speech/browser lifecycle
              ├─ S6-03 P2 realtime conversation
              ├─ S6-04 P3alpha task vertical
              └─ S6-05 observability, benchmark and privacy
                       └─ S6-06 cumulative/joint X-E2E closure
                              └─ S7-01 candidate assembly
                                  ├─ S7-02 automated/real-path acceptance
                                  └─ S7-03 cumulative review and repair
                                         └─ S7-04 A3 handoff freeze
                                                └─ S8-01 preflight
                                                    └─ S8-02 human journey
                                                        └─ S8-03 decision/cleanup
```

The A1 module groups may overlap in calendar time only after S5-03 records
non-overlapping ownership. `S6-05` can build shared tooling alongside module
work after the metric/event inputs it consumes are stable. `S6-06`, S7 and S8
are integration-owner work and are not parallel returns.

## 3. S5 / A0 — baseline and gap freeze

### S5-01 — exact-source acceptance audit

- **Scope:** Shared/ACG, P1, P2, P3alpha, joint P2/P3alpha and Web/degradation
  rows in Alpha acceptance; actual server/frontend source and adjacent tests.
- **Risk:** Tier 0 audit; any newly proposed authority/protocol change is routed
  to its later Tier 2/3 implementation task.
- **Work:** map every requirement to a real owner, source family and test family;
  distinguish existing implementation from W2-only proof and from an actual gap.
- **Exit:** no acceptance row is unmapped or justified only by package labels,
  test counts, old reviews or UI appearance.

The freeze-date inspection establishes these starting facts:

| Area | Source-backed starting fact | A0 classification used by this plan |
|---|---|---|
| AIO/X-WEB | Browser Audio I/O, permission/visibility/device listeners, exact stop, platform diagnostics and extensive lifecycle tests exist | `VERIFY`; fix only failures found in declared real Chrome lifecycle tests |
| SR/SS | Provider-neutral Ports, real Gateway batch STT/TTS and Browser fallbacks exist; current formal/browser capabilities declare non-streaming | `IMPLEMENT or DEVIATION` for Alpha streaming/provenance; `VERIFY` for retained batch/fallback |
| RM | Dedicated bounded media, ACK/backpressure/sequence/close behavior and payload-free logging checks exist | `VERIFY`; add real transport/fault/load measurements and only repair observed gaps |
| CR/II/AB | Canonical runtime, generation fence, presentation truth, non-blocking Agent route, progress and extensive race/failure tests exist | `VERIFY`; close slow-load, notification, stop/revise and joint-runtime coverage |
| Critical input | Critical-token policy and gate have deep standalone tests but are not composed into the protected committed product path | `IMPLEMENT` under Shared/II product composition |
| TC/ED | Formal persistent Core/Store, full structured queries, create/cancel/retry mutations, outbox, real project Executor and restart/fault tests exist | `VERIFY`; repair only acceptance gaps found by the complete matrix |
| VB | Committed create/cancel mapping, confirmation and origin progress exist; the low-level bridge has no committed `task.status` resolution | `IMPLEMENT` the formal natural-language status route without adding Task authority to VB |
| X-OBS | Correlated observation/metric, exporter and deterministic fault harness exist | `IMPLEMENT` a reproducible Alpha benchmark/report layer; `VERIFY` trace coverage |
| X-E2E | Many vertical and product integration tests exist | `IMPLEMENT/VERIFY` one joint slow-round + detached-task acceptance scenario and one complete candidate matrix |
| Privacy/deployment | Proxy/privacy/preflight and media-persistence unit checks exist | `VERIFY` in a controlled whole-stack topology; no source-only claim of raw-audio zero persistence |

### S5-02 — product and private-environment freeze

- **Scope:** choices that source inspection cannot make truthfully.
- **Risk:** Tier 3 decision boundary because route, privacy and real Executor
  choices affect the Alpha product claim.
- **Required inputs:**
  1. selected Alpha streaming STT/TTS Provider/Adapter and fallback, or an
     explicitly accepted bounded non-streaming deviation;
  2. exact desktop Chrome version, Windows build, secure origin/topology,
     actual microphone/output labels without a hardware-model allowlist, and
     fixed network profile;
  3. real Provider probe of the accepted model/voice defaults and safe failure
     profiles, without recording credentials;
  4. real D0 Executor/project target and recoverable isolation boundary; and
  5. any acceptance target that is intentionally a deviation rather than a bug.
- **Exit:** accepted decisions are in DECISIONS, machine-private values are
  recorded in the candidate workspace/run record, and no task silently chooses
  billing, credentials, deployment, destructive target or product scope.

This task can wait for usable OpenAI Speech API access and candidate-machine
facts while S5-01 read-only audit and noncontroversial verification preparation
continue. Hardware brand/model selection is not an input. S5/A0 cannot close
without the runtime facts and real probes.

### S5-03 — A1 batch and ownership freeze

- **Scope:** activate the A1 task graph below with exact file boundaries,
  dependency state and module-close commands.
- **Risk:** Tier 1 planning; an activated task retains the risk shown below.
- **Exit:** every mandatory Alpha row has exactly one closure owner, shared-file
  collisions are resolved, each task has a coherent commit/review boundary and
  STATUS names the first executable batch.

## 4. S6 / A1 — module closure tasks

### S6-01 — Shared contract consumers and critical-input safety

- **Track/modules/packages:** Shared ACG consumers, II critical-input policy,
  Product Composition; consumes the relevant A foundations.
- **Risk:** Tier 3 — shared authority/security/committed-input boundary.
- **Dependencies:** S5-02 Speech/input decision; precedes protected P1/P3alpha
  product closure and S6-06.
- **Verify first:** v2 identities, scopes, capability/error/unknown behavior,
  committed-only effects, cancel scopes, fence, WorkProgress/Context,
  authorization and flag-off behavior across actual consumers.
- **Implement only proven gaps:** compose `CriticalTokenSafetyGate` into the
  committed text/voice path before protected Agent/Tool/Task dispatch; preserve
  clarification evidence and stale-generation rejection.
- **Required oracles:** eligible committed input reaches only its authorized
  owner; partial, mismatched, stale, low-confidence or conflicting critical
  input produces clarification/rejection with zero Agent/Tool/Task/audio/history/
  Store side effects; feature-off remains explicit and does not bypass base
  commit/scope checks.
- **Exit:** all Alpha-consumed ACG rows have a conformant consumer and the
  complete Shared/critical-input scoped diff closes under D-074.

### S6-02 — P1 Speech and browser lifecycle closure

- **Track/modules/packages:** P1 AIO/SR/SS plus their X-WEB lifecycle surface;
  `AIO-B/C`, `SR-B/C`, `SS-B/C`.
- **Risk:** Tier 2; Tier 3 if deployment/privacy/credential boundaries change.
- **Dependencies:** S5-02 selected Speech and browser/deployment baseline;
  S6-01 before protected committed actions are accepted.
- **Verify first:** existing Browser AIO lifecycle, exact-response stop, formal
  batch STT/TTS, Browser fallbacks, capture finalization, playout ACK and stale
  rejection on the declared Chrome baseline.
- **Implement only proven gaps:** the selected ordered partial/final/cancel and
  streaming audio-chunk/text-span provenance route, or encode the accepted
  deviation without mislabeling batch/fallback as streaming.
- **Required oracles:** permission grant/deny/revoke; device select/change/loss;
  autoplay/user activation; hidden/background/resume; Provider unavailable;
  editable final commit; wrong-response stop; stale audio zero; text fallback;
  fixed-corpus and real-device p50/p95/failure/sample report.
- **Exit:** AIO, SR and SS independently meet their Alpha rows and share one
  reviewed physical `microphone → STT → real Agent → TTS → playout` result.

### S6-03 — P2 realtime conversation closure

- **Track/modules/packages:** P2 RM/CR/II/AB; `RM-B/C`, `CR-B/C`, `II-B/C`,
  `AB-B`.
- **Risk:** Tier 2 state/concurrency; Tier 3 for changed shared cancel/authority.
- **Dependencies:** selected streaming/fallback path from S5-02; S6-01; P1
  capture/playout facts from S6-02 for the real vertical.
- **Verify first:** bounded media/ACK/backpressure, generation and presentation
  fencing, exact stop/cancel, non-blocking Agent dispatch, source-backed round
  progress, history and refresh/reconnect behavior already present.
- **Implement only proven gaps:** missing drop/reorder/corruption/network profile,
  notification arbitration, documented EOT/barge-in/stop/revise/delegate behavior
  or slow-Harness/load instrumentation required by Alpha.
- **Required oracles:** bounded queue/backlog; close and reconnect; slow/failing
  Harness; continued microphone/new Turn/progress; zero stale UI/audio/history;
  zero cross-response/round/task/playback cancel; route latency report.
- **Exit:** RM, CR, II and AB Alpha rows close together under a complete P2
  scoped review; fake evidence is not used for real media/Agent claims.

### S6-04 — P3alpha formal Task vertical closure

- **Track/modules/packages:** P3alpha TC/ED/VB; `TC-B/C`, `ED-B`, `VB-B/C`.
- **Risk:** Tier 3 — mutation, authorization, durability and real project effects.
- **Dependencies:** S5-02 safe Executor/project; S6-01 committed-input safety;
  S6-03 Runtime path for voice-origin progress.
- **Verify first:** structured `create/get/list/status/cancel/events`, bounded
  retry, durable command/task/event/result/outbox authority, duplicate/conflict,
  gap/reorder/concurrency, restart reconciliation, project binding and origin
  progress already present in formal source/tests.
- **Implement only proven gaps:** committed natural-language `task.status`
  resolution through the formal query path; any source-proven missing
  clarification/confirmation/correlation behavior. VB remains a mapper and must
  not become a second Task Core or Executor.
- **Required oracles:** structured and committed text/voice routes; ambiguous and
  wrong-target/scope rejection; exact destructive confirmation; disconnect
  survival; restart active/terminal/interrupted/unknown/pending truth; real D0
  status/cancel/capability/outcome; progress to voice via Runtime and text via
  Chat/UI; zero unauthorized or partial mutation.
- **Exit:** TC, ED and VB Alpha rows close on one formal vertical, with real
  mutation tests confined to a recoverable exact target and a Tier 3 review.

### S6-05 — observability, benchmark, privacy and Web deployment closure

- **Track/packages:** Shared/X — `X-OBS` and the release-facing part of `X-WEB`.
- **Risk:** Tier 3 — privacy, deployment and release evidence boundary.
- **Dependencies:** stable metric/event inputs from each participating module;
  may build in increments but closes after S6-02 through S6-04.
- **Verify first:** correlation/redaction schema, bounded exporter/fault harness,
  route diagnostics, proxy/privacy checks and deployment preflight already
  present.
- **Implement only proven gaps:** a deterministic benchmark runner/report that
  emits p50, p95, failures and sample count for every declared target; controlled
  whole-stack route-to-disk regression and any missing sanitized trace segment.
- **Required oracles:** trace reproduces route/cancel/fence/queue/task facts;
  overflow/export failure does not affect product authority; raw audio is absent
  from configured storage/log/browser surfaces; browser receives no long-lived
  Provider credential; HTTPS/WSS, proxy, CSP and CORS are correct for the declared
  topology; text path survives feature/provider/media failure.
- **Exit:** X-OBS and X-WEB acceptance rows are reproducible from sanitized
  outputs on the declared environment, or a specific user-accepted deviation is
  recorded.

### S6-06 — X-E2E and joint P2/P3alpha closure

- **Track/package:** Shared/X — `X-E2E`, consuming every mandatory A1 return.
- **Risk:** Tier 3 — cumulative state, mutation and cross-authority integration.
- **Dependencies:** S6-01 through S6-05 complete for the behaviors consumed.
- **Work:** create one deterministic joint scenario with a slow conversational
  Harness round and one detached Task while multiple committed voice/text Turns,
  response interruption/revision, exact task status/cancel and blocked/decision/
  terminal progress continue.
- **Required oracles:** bounded microphone/media; zero hot-path synchronous
  Harness wait; exact response/round/task/attempt targets; response interruption
  does not cancel Task; task cancel does not stop response/playback/round; source
  correlation is complete; partial/stale/wrong-scope effects are zero; flag-off
  preserves existing text behavior.
- **Exit:** one cumulative automated route passes all applicable Shared, P1, P2,
  P3alpha, joint, Web, degradation and privacy requirements without using fake
  success for a required real path.

## 5. S7 / A2 — integrated candidate tasks

### S7-01 — candidate assembly and identity

- Integrate all mandatory A1 closure returns into one coherent branch state.
- Resolve dependency and generated-artifact drift; do not include machine-private
  data, credentials, raw audio or unrelated user changes.
- Freeze the exact source identity, clean-worktree fact, upstream relation,
  dependency lock, flags and sanitized runtime labels in the candidate record.
- **Exit:** one reproducible candidate exists; no module is represented by an
  unintegrated worktree/branch or an unreviewed local patch.

### S7-02 — complete automated and real-path acceptance

- Run affected module suites plus the cumulative Shared/P1/P2/P3alpha/X matrix,
  frontend test/build/static checks, backend regressions and `git diff --check`.
- Run the selected real Speech/Media/Agent/Executor probes, fixed corpus,
  benchmark/fault profiles, secure deployment preflight and privacy regression.
- Record exact commands, failures, sample count and sanitized outputs against the
  candidate identity. Historical W2/W3 counts do not satisfy this task.
- **Exit:** every applicable automated requirement passes; any accepted deviation
  is explicit and no critical finding remains.

### S7-03 — cumulative review and repair loop

- Cold-review the cumulative Alpha diff from its declared comparison base against
  the original Alpha request, repository rules, actual behavior and tests.
- Review P1↔P2 speech/media, P2↔P3 progress/cancel, frontend↔Gateway↔AgentServer,
  Store↔Executor/restart and observability/privacy seams.
- Obtain one independent review or record the exact substitute and limitation.
- Fix findings and rerun affected plus cumulative checks. Repeat the final review
  only when a fix materially changes integration semantics.
- **Exit:** review has no unresolved critical finding and tested source still
  matches S7-01.

### S7-04 — A3 handoff freeze

- Bind the A3 script to the exact candidate, environment, Provider/Executor,
  disposable project, flags, known deviations and automated report.
- Confirm that A3 contains no source repair, hidden route switch or new scope.
- **Exit:** [ALPHA_SHOWCASE.md](../demo/ALPHA_SHOWCASE.md) is executable end to end
  by the user on the frozen candidate.

## 6. S8 / A3 — product acceptance tasks

### S8-01 — human-run preflight

- Reconfirm exact candidate/clean worktree, Chrome/OS/origin/device/network,
  Provider/model/voice, isolated runtime data, project/Executor and route facts.
- Run the text/Tool smoke and minimum real Provider/device probes without changing
  the candidate. Mismatch is `BLOCKED`, not an invitation to patch during A3.

### S8-02 — one complete Alpha human journey

- The user runs the Alpha showcase once on the A2 source: platform lifecycle,
  physical P1 speech and heard playout, P2 slow-work interruption/correction,
  structured and committed natural-language P3alpha control, the joint P2/P3alpha
  journey, degradation, refresh/reconnect, privacy and cleanup.
- Automation, an audio-file corpus and programmatic audio inspection may support
  the run, but they do not replace the user's physical permission/device, audible
  quality and product-usability observations required by the showcase.

### S8-03 — decision, cleanup and documentation

- Stop capture/playout/services, preserve only sanitized records and verify the
  disposable task target and worktree state.
- Record `PASS`, `PARTIAL`, `BLOCKED` or `FAIL` under Alpha acceptance; update
  STATUS once with the exact tested source, observations, deviations and next
  action. Add a dated acceptance/review record only when it adds source facts not
  appropriate for STATUS.
- `PASS — INTEGRATED WEB ALPHA` closes S8/A3. It does not claim full P3, D1/D2,
  production authentication, broad browser/mobile/PWA support, public deployment,
  RC/Production readiness or audit-grade certification.

## 7. Mandatory exclusions

Unless a newer user-approved decision expands scope, S5–S8 do not include:

- rebuilding or extending D-031 into a second Task authority;
- reviving the retired signed Gate, fixed manifest or Replacement Ledger;
- full P3 operations, D1/D2/external exactly-once or production auth/multitenancy;
- provider billing, key creation/relocation, public deployment or destructive
  real-project mutation outside the isolated Executor target;
- Chrome+Edge/public browser matrix, Firefox/Safari, mobile/PWA or production SLO;
- repeating the completed W2 acceptance or W3 develop migration without a
  specific regression that enters an A1 task.
