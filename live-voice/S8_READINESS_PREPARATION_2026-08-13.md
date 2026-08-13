# S8 readiness preparation record

> Status: `S8 READINESS PREPARED`, not S8 started and not A3 entry.
>
> Authority: current stage remains [STATUS](STATUS.md); S8 requirements remain
> [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md) and the
> [Alpha showcase](demo/ALPHA_SHOWCASE.md).

## 1. Packet identity and boundary

- Stage/node: Pre-S8 preparation for `S7-04 → S8-01`; S8/A3 is not active.
- Track/module: Shared-X / A3 operator workflow, preflight, cleanup and sanitized
  observation support.
- Risk: Tier 2/3 because candidate identity, private environment boundaries,
  Task/response identity and final acceptance records are consumed.
- Preparation base: closed S6 HEAD `b7573d51917eca2c3b6070c2bbc8632da4b2a2b1`.
- S7 interface input at worktree creation: committed automation source
  `d2727f20669b1996257f5215d69c118447332138`. The later integrated S7 reference
  observed on the owning branch is `75cdafeaae6f393e92681aa3c2c6afe7e8ec7d53`;
  this preparation now consumes its exact generated-artifact candidate state.
  The preparation branch remains intentionally based on S6 and must be combined
  with the Integration Owner's final S7 candidate before S7-04 freeze.
- Included: the unsigned helper, disposable fixture ownership, S7 report/handoff
  binding, preflight, observation/decision schema, cleanup validation, tests and
  operator procedure.
- Excluded: product source repair, S7 execution, S8 execution, physical
  observation, Alpha decision, credentials/accounts, public deployment, full P3,
  D1/D2, Production, remote refs and retired Gate machinery.

The helper consumes S7 facts and requires the S7 Integration Owner to freeze the
handoff. It does not create a second candidate, Task or acceptance authority.

## 2. Showcase executability audit

The table uses stable showcase/acceptance sections rather than copying their
full text. `Auto` means a prerequisite the helper can verify; `User` means a
fact automation must not supply.

| Check ID / authority | S7/A2 input | Operator action | Auto | User | Reused S7 check | Positive / blocked | Forbidden effect | Cleanup | Final candidate |
|---|---|---|---|---|---|---|---|---|---|
| `S8-01.IDENTITY`; Showcase §1; Acceptance §0–1 | exact report, runtime digest, S7-03 review, S7-04 freeze | restore the frozen runtime only | HEAD/branch/upstream/dependency hashes and clean-before/after | approve reuse IDs/deviations | runner identity/report | exact match / any stale, dirty or missing input is `BLOCKED` | no patch, flag or fallback change | recheck candidate after cleanup | yes |
| `S8-01.ENVIRONMENT`; Showcase §1; Acceptance §1, §7 | frozen Chrome/OS/origin/device/network and routes | restore external configuration without printing it | exact sanitized labels, private HTTPS DNS/address, secret presence | confirm actual device/profile/network labels | `secure-deployment`, `privacy` | declarations match / public, missing or mismatched route is `BLOCKED` | zero secret/path/audio persistence | list private artifacts by ref | yes |
| `S8-01.ISOLATION`; Showcase §1; Acceptance §1, §5 | data/project labels, Direct Executor | bind new runtime, Task Store and fixture | external absolute paths, Store under data root, standalone no-remote fixture, marker/session/ref | confirm fixture is the intended disposable target | `agent-executor` | exact isolation / production repo, remote or wrong ref is `BLOCKED` | zero user-project/cross-project mutation | preserve or explicitly delete exact fixture | yes |
| `S8-01.TEXT_TOOL_SMOKE`; plan S8-01; runbook §8 | real Agent/Tool route | send the fixed read-only Git-status prompt | services/listeners and S7 route already verified | observe real tool call/result/final | `agent-executor` | real sequence / missing Tool or guessed answer blocks | zero project mutation | retain sanitized response/round refs | yes |
| `S8-01.PROVIDER_DEVICE_PROBE`; plan S8-01 | Speech/Media VERIFY and fixed Provider route | use physical mic/output for one short committed request | Provider/device prerequisites only | permission, recognition, heard output | `speech-media`, `secure-deployment` | actual route heard / fake or fallback mismatch blocks | zero uncommitted Agent/Tool/Task effect | stop exact playout/capture | yes |
| `S8-02.PLATFORM.*`; Showcase §2; Acceptance §7 | platform lifecycle automation and secure route | grant/deny/revoke, device loss/recovery, autoplay/user activation, background/resume, refresh/reconnect | session/candidate binding | truthful visible states and usability | `speech-media`, `secure-deployment` | no stale resurrection / silent failure is `FAIL` | zero duplicate dispatch/stale audio | restore declared permission/device state | yes |
| `S8-02.P1.CRITICAL_COMMIT`; Showcase §3.1–3.3; Acceptance §2–3 | committed-only and critical-token proofs | speak, inspect/clarify and explicitly commit | exact response/round refs | final text and correction experience | `speech-media`, `benchmark-fault` | only committed text dispatches / partial mutation fails | zero Agent/Tool/Task effect before commit | stop successor capture safely | yes |
| `S8-02.P1.HEARD_PLAYOUT`; Showcase §3.4 | streaming TTS/receipt VERIFY | hear the full truthful response | response binding and receipt facts | audible completeness/quality | `speech-media` | full heard output / automation alone cannot pass | zero wrong-generation/stale output | exact response stop | yes |
| `S8-02.P1.EXACT_STOP`; Showcase §3.5–3.6 | cancel/fence fault facts | stop second playout and successor capture | response/round identity consistency | no returned stale chunk or duplicate submit | `benchmark-fault` | exact stop / wrong-target cancel fails | zero cross-response/task cancel | capture/playout off | yes |
| `S8-02.P2.READ_ONLY_TOOL`; Showcase §4.1; Acceptance §4 | real Agent/Tool route | force one safe read-only Tool call | response/round binding | exact fact, visible and audible result | `agent-executor` | truthful result / guessed or mutating result fails | zero unintended project effect | retain sanitized refs only | yes |
| `S8-02.P2.MULTI_TURN`; Showcase §4.2, §4.4 | slow-harness/fault VERIFY | continue voice turns during slow work | identity freshness and S7 latency/fault refs | responsive media/progress | `benchmark-fault` | nonblocking / hot-path wait or freeze fails | zero stale UI/audio/history | settle current round | yes |
| `S8-02.P2.INTERRUPT_REVISION`; Showcase §4.3 | cancel-domain facts | interrupt/revise exact response | response/round bindings | corrected output and presented history | `benchmark-fault` | old output fenced / cross-target cancel fails | zero Task mutation | exact response stop | yes |
| `S8-02.P3.STRUCTURED_*`; Showcase §5.1; Acceptance §5 | formal route/task/outbox VERIFY | create/get/list/status/events/cancel | task/attempt/work bindings | truthful replay/conflict/lifecycle UI | `agent-executor` | exact authority / wrong scope or partial effect fails | zero legacy/foreign Task mutation | settle outbox/owner/lease | yes |
| `S8-02.P3.AMBIGUOUS_ZERO_MUTATION`; Showcase §5.2 | committed-input contract | issue ambiguous/unconfirmed request | response/round binding | clarification/confirmation shown | `agent-executor`, `benchmark-fault` | zero mutation / any Task create fails | zero Task/Executor effect | none beyond session record | yes |
| `S8-02.P3.NATURAL_*`; Showcase §5.3–5.4 | voice-task bridge VERIFY | confirm create, then status/cancel named task | all five identity refs | committed language behavior | `agent-executor` | exact Task control / stale or wrong Task fails | zero partial/cross-scope effect | settle exact attempt/outbox | yes |
| `S8-02.P3.RESTART_RECONCILIATION`; Showcase §5.5 | restart/fault outcomes | refresh/reconnect and restart owned boundary | task/attempt/work refs | active/terminal/interrupted/unknown/pending truth | `benchmark-fault` | no silent rerun / false success fails | zero duplicate Executor effect | stop restarted service later | yes |
| `S8-02.P3.FULL_P3_UNSUPPORTED`; Showcase §5.6 | accepted P3alpha boundary | invoke only if safe | scoped task/attempt/work refs | explicit unsupported outcome | `agent-executor` | unsupported / hidden full-P3 behavior blocks | zero unsupported mutation | settle exact attempt | yes |
| `S8-02.JOINT.*`; Showcase §6; Acceptance §6 | joint and cancel-domain VERIFY | slow conversation plus detached Task; target each independently | task/attempt/response/round/work bindings | responsive product and correct progress | `agent-executor`, `benchmark-fault` | target isolation / any cross-cancel fails | zero cross-domain/stale effect | settle both domains | yes |
| `S8-02.DEGRADATION.SPEECH_ROUTE`; Showcase §7.1 | closed Speech fault matrix | select only the frozen safe Speech profile | response/round and route declaration | visible route/error and usable text | `benchmark-fault` | named fallback / hidden switch fails | zero duplicate side effect | restore frozen primary route | yes |
| `S8-02.DEGRADATION.EXECUTOR_TRUTH`; Showcase §7.2 | closed Executor fault matrix | select only the frozen safe Executor profile | task/attempt/work binding | exact failed/interrupted/unknown/pending truth | `benchmark-fault`, `agent-executor` | truthful terminal / false success fails | zero duplicate Task/Executor effect | settle exact attempt; do not change source | yes |
| `S8-02.PRIVACY`; Showcase §7.3–7.4; Acceptance §7 | privacy surfaces and trace VERIFY | inspect declared surfaces and trace reference | report/source label privacy | UI/storage/log usability inspection | `privacy`, all trace probes | zero secret/raw audio / any leak fails | zero persistence/unauthorized content | artifacts remain external | yes |
| `S8-03.LIVE_VOICE_STOPPED`; Showcase §8.1 | exact response/round | exit Live Voice | record consistency only | capture/playout/timer/reconnect visibly stop | fault/cleanup facts | all stopped / stale restart fails | zero audio/capture resurrection | stop exact UI session | yes |
| `S8-03.TASK_STATE_SETTLED`; Showcase §8.2 | Task/attempt/outbox facts | settle or truthfully record exact task | terminal/outbox/owner/lease enum validation | confirm product state | `agent-executor` | settled truth / missing row blocks | zero silent retry/owner leak | preserve sanitized refs | yes |
| `S8-03.PROJECT_EFFECT`; Showcase §8.2 | no-remote fixture baseline | compare expected paths and tracked/untracked effect digest | HEAD, paths, content digest and remote read-only checks | inspect semantic effect | `agent-executor` | exact effect / any unexpected path fails | zero user/candidate mutation | preserve or exact marked delete | yes |
| `S8-03.SERVICES_RELEASED`; Showcase §8.3 | captured exact service PIDs/ports | stop owned services | PID identity gone and four ports closed | confirm no product process remains | bounded process principles | released / live or reused PID blocks | helper never kills unknown process | operator stops processes | yes |
| `S8-03.WORKTREE_UNCHANGED`; Showcase §8.4 | initial candidate snapshot | make no source change | exact snapshot before/after cleanup | none | runner identity | unchanged / any change blocks | zero candidate mutation | none | yes |
| `S8-03.DECISION`; Showcase §8.5; Acceptance §8 | complete observations/review | user chooses final outcome | schema and consistency only | all final judgment | none can replace user | user decision / automation cannot sign | no synthetic PASS | STATUS update belongs to owner | yes |

## 3. Findings and prepared resolutions

| Audit question | Finding | Preparation result |
|---|---|---|
| Executable order | Showcase order is coherent, but it deliberately delegates environment/startup detail to the runbook. | The operator guide supplies the exact preparation/preflight/session/cleanup sequence and preserves the showcase as authority. |
| Explicit start/stop | Backend and frontend basics exist in runbook §6–7.1; the private reverse-proxy/certificate command is machine-owned and cannot safely be committed. | Require the exact S7-verified topology, check its listeners/private origin, and stop on mismatch. No invented localhost substitute. |
| Candidate/environment/Task identity | Showcase §1 names candidate/environment facts, but no single machine-checkable A3 record schema existed. | Bind S7 report bytes + runtime digest + S7-04 state and freeze the active product session plus unique per-scope product correlations in a private pre-action binding whose bytes are reloaded by capture/validation/cleanup; recompute a sanitized trace manifest from an external product export; require the frozen product correlation as the journey discriminator plus mutually exclusive event/segment and exact per-scope source/route semantics, scoped task/attempt/response/round/work refs and every referenced task/attempt pair to settle. |
| Failure recovery | Showcase §7–8 names recovery/cleanup but does not protect an automated destructive target. | Cleanup is read-only by default; it never kills processes. Fixture deletion requires declared `DELETE`, `--execute`, marker/session/ref/no-remote checks and protected-target rejection. |
| Privacy | Existing authorities forbid secrets/raw audio, but the runbook's legacy free-text record template could invite private detail. | Generated records accept only hashes, booleans, enums, IDs and ports. Files stay outside Git; errors are content-free reason codes. |
| Automation wording | S7 real probes intentionally return `VERIFY`, while only the user may produce A3/Alpha PASS. | Preflight returns `AUTOMATED_PREFLIGHT_VERIFIED`, never `PASS`; every human row rejects `observer=AUTOMATION`. |
| A3 source repair | Showcase already says mismatch blocks rather than inviting repair. | Helper has no source-repair, flag-write or fallback-switch path. Any mismatch is `BLOCKED`. |

No product-source defect was found during this preparation audit. A mismatch
seen only on the future exact S7 candidate is a `FINDING_FOR_S7`; the Integration
Owner must decide the fix and rerun affected A2 checks before a new handoff.

## 4. Prepared versus deferred status

| Status | Items |
|---|---|
| `PREPARED` | S7 report/handoff consumer including generated-artifact state, exact candidate checks, raw flag checks, sanitized route/environment checks, candidate-rooted process and HTTPS/CSP/WSS-ACK diagnostics, fixture ownership/isolation and pre-journey effect plan, product-session/unique-scope-correlation-bound trace capture with per-scope semantics, scoped identity/settlement checks, decision consistency, task/project/process cleanup checks, dry-run and exact delete safety, operator sequence and tests. |
| `NEEDS_S7_CANDIDATE` | Combine with the Integration Owner's final S7 candidate; create the real S7 report; complete S7-03; let the Integration Owner freeze S7-04; rerun all S7 affected checks after integrating this prep commit because candidate HEAD changes. |
| `ENVIRONMENT` | Gateway-only Speech access, Agent model/tool route, private HTTPS/WSS proxy/cert/DNS, exact Chrome/OS/devices/network, isolated runtime/Store, service processes and real observations. |
| `USER_REQUIRED` | S8-01 text/Tool and physical Provider/device probes; every Showcase §2–8 interaction/usability observation; final Alpha decision. |
| `FINDING_FOR_S7` | None on the S6 preparation base. Future candidate mismatch or product behavior failure must return to the S7 owner and A2 reruns. |
| `OUT_OF_SCOPE` | Formal S8 execution, Alpha PASS, product repairs, full P3, D1/D2, Production auth/public deployment, mobile/PWA/wide browsers, credentials/accounts/billing, remote refs, signed Gate/manifest/score. |

## 5. Integration and rerun boundary

The helper/source/tests/documentation can be integrated before S7-04, but they
must be included before the S7 candidate identity is frozen. Integrating any of
these files after S7-02 changes candidate HEAD and invalidates the existing S7
report/handoff; S7-01 identity, affected automation, complete S7-02, S7-03 and
S7-04 must then run again.

After combining with the final S7 candidate, rerun at minimum:

- `tests/unit_tests/live_voice/test_s7_alpha_verification.py`;
- `tests/unit_tests/live_voice/test_s7_real_probes.py`;
- `tests/unit_tests/live_voice/test_s8_readiness.py`;
- the S7 runner source/privacy and Markdown-link checks;
- the complete candidate run, all five real probes and cumulative review because
  the candidate identity has changed.

Only external handoff binding and all runtime/human execution occur after
S7-04. The shortest command sequence is maintained in
[the operator guide](../scripts/live_voice/S8_READINESS.md#shortest-s7-04-to-s8-01-sequence).
