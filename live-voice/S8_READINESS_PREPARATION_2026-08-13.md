# S8 readiness preparation record

> Status: `S8 READINESS INTEGRATED`; exact A3 entry is fail-closed on the final
> external S7 report/handoff. S8 human acceptance has not started.
>
> Authority: current stage remains [STATUS](STATUS.md); S8 requirements remain
> [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md) and the
> [Alpha showcase](demo/ALPHA_SHOWCASE.md).

## 1. Packet identity and boundary

- Stage/node: `S7-04 → S8-01` entry boundary; S8/A3 human acceptance is not
  active and remains blocked unless the exact current handoff validates.
- Track/module: Shared-X / A3 operator workflow, preflight, cleanup and sanitized
  observation support.
- Risk: Tier 2/3 because candidate identity, private environment boundaries,
  Task/response identity and final acceptance records are consumed.
- Integration base: historical S7/A2 documentation-handoff HEAD
  `a53856de0af12e2c1b11e6cc8f2dc0a18150a99a`; reviewed product source remains
  `c209e4a6cb88779277254751aa52354050a813a2`, and the reviewed readiness source
  is `e58df618d3ee00776e004e8dfacd8d4d88b744dc`.
- Port source: `b7efa14f4c2e9bcefac8e2773867be9b79036b6a` from the local
  `codex/s8-readiness-prep` branch. That earlier-S6-base work was audited and
  adapted rather than replayed, then committed on the current line as
  `e58df618d3ee00776e004e8dfacd8d4d88b744dc`. The final handoff history also
  records `b7efa14f` as a formal ancestor through a no-tree-change integration
  merge, so the packet's ancestry check passes without restoring stale bytes.
- The previously generated S7 report remains valid history for `a53856de`, but
  it cannot authorize A3 after the readiness workflow changed candidate bytes.
  A3 entry instead consumes the new external report/handoff produced by the
  complete exact-clean-documentation-HEAD S7 run.
- Included: the unsigned helper, S7 production-build identity binding, disposable
  fixture ownership, S7 report/handoff binding, preflight, observation/decision
  schema, cleanup validation, runner/readiness tests and operator procedure.
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
| `S8-01.IDENTITY`; Showcase §1; Acceptance §0–1 | exact report, runtime digest, S7-03 review, S7-04 freeze | restore the frozen runtime only | HEAD/branch/upstream/dependency hashes, S7-frozen ignored `dist` manifest, complete private-443 served-content match and clean-before/after | approve reuse IDs/deviations | runner identity/report | exact match / any stale, dirty, foreign-root or missing input is `BLOCKED` | no patch, flag or fallback change | recheck candidate after cleanup | yes |
| `S8-01.ENVIRONMENT`; Showcase §1; Acceptance §1, §7 | frozen Chrome/OS/origin/device/network and routes | restore external configuration without printing it | exact sanitized labels, candidate-rooted Agent/Gateway listeners, external private HTTPS proxy, secret presence | confirm actual device/profile/network labels | `secure-deployment`, `privacy` | declarations match / public, missing or mismatched route is `BLOCKED` | zero secret/path/audio persistence | list private artifacts by ref | yes |
| `S8-01.ISOLATION`; Showcase §1; Acceptance §1, §5 | data/project labels, Direct Executor | bind new runtime, Task Store and fixture | external absolute paths, `S8_TASK_STORE_PATH` exactly equals product-authoritative `JIUWENSWARM_LIVE_VOICE_P3_DATABASE` under data root, standalone no-remote fixture, marker/session/ref | confirm fixture is the intended disposable target | `agent-executor` | exact isolation / production repo, split Store, remote or wrong ref is `BLOCKED` | zero user-project/cross-project mutation | preserve or explicitly delete exact fixture | yes |
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
| `S8-03.SERVICES_RELEASED`; Showcase §8.3 | captured exact service PIDs/ports | stop owned services | candidate Agent/Gateway and external private-proxy PID identities gone; 18092/19000/19001/private 443 released | confirm no product process remains | bounded process principles | released / live or reused PID blocks | helper never kills unknown process | operator stops processes | yes |
| `S8-03.WORKTREE_UNCHANGED`; Showcase §8.4 | initial candidate snapshot | make no source change | exact snapshot before/after cleanup | none | runner identity | unchanged / any change blocks | zero candidate mutation | none | yes |
| `S8-03.DECISION`; Showcase §8.5; Acceptance §8 | complete observations/review | user chooses final outcome | schema and consistency only | all final judgment | none can replace user | user decision / automation cannot sign | no synthetic PASS | STATUS update belongs to owner | yes |

## 3. Findings and prepared resolutions

| Audit question | Finding | Preparation result |
|---|---|---|
| Executable order | Showcase order is coherent, but it deliberately delegates environment/startup detail to the runbook. | The operator guide supplies the exact preparation/preflight/session/cleanup sequence and preserves the showcase as authority. |
| Explicit start/stop | Backend and frontend basics exist in runbook §6–7.1; the private reverse-proxy/certificate command is machine-owned and cannot safely be committed. | Require the exact S7-verified topology, check its listeners/private origin, and stop on mismatch. No invented localhost substitute. |
| Candidate/environment/Task identity | Showcase §1 names candidate/environment facts, but no single machine-checkable A3 record schema existed. | Bind S7 report bytes + runtime digest + S7-04 state and freeze the active product session plus unique per-scope product correlations in a private pre-action binding whose bytes are reloaded by capture/validation/cleanup; recompute a sanitized trace manifest from an external product export; require the frozen product correlation as the journey discriminator plus mutually exclusive event/segment and exact per-scope source/route semantics, scoped task/attempt/response/round/work refs and every referenced task/attempt pair to settle. |
| Served frontend identity | The private proxy serves Git-ignored `frontend/dist`, so candidate HEAD plus proxy PID cannot prove which build A3 sees. | S7 freezes a bounded complete path/size/content manifest and verifies it again after all checks. S8 recomputes disk identity and reads `/` plus every canonical file from private 443 using identity encoding, exact 200/length/hash checks and a global deadline. Stale build, redirect, compressed substitution and foreign-root SPA fallback block. |
| Failure recovery | Showcase §7–8 names recovery/cleanup but does not protect an automated destructive target. | Cleanup is read-only by default; it never kills processes. Fixture deletion requires declared `DELETE`, `--execute`, marker/session/ref/no-remote checks and protected-target rejection. |
| Privacy | Existing authorities forbid secrets/raw audio, but the runbook's legacy free-text record template could invite private detail. | Generated records accept only hashes, booleans, enums, IDs and ports. Files stay outside Git; errors are content-free reason codes. |
| Automation wording | S7 real probes intentionally return `VERIFY`, while only the user may produce A3/Alpha PASS. | Preflight returns `AUTOMATED_PREFLIGHT_VERIFIED`, never `PASS`; every human row rejects `observer=AUTOMATION`. |
| A3 source repair | Showcase already says mismatch blocks rather than inviting repair. | Helper has no source-repair, flag-write or fallback-switch path. Any mismatch is `BLOCKED`. |

No product-source defect was found during the preparation audit or the read-only
port audit against the closed S7 line. Any later exact-entry mismatch is a new
`FINDING_FOR_S7`; the Integration Owner must stop S8, decide the fix and rerun
affected A2 checks before replacing the handoff.

## 4. Prepared versus deferred status

| Status | Items |
|---|---|
| `INTEGRATED` | S7 report/handoff consumer including generated-artifact state and the S7-frozen production-build manifest, exact candidate checks, disk/private-443 served-content binding, raw flag checks, sanitized route/environment checks, candidate-rooted process and HTTPS/CSP/WSS-ACK diagnostics, fixture ownership/isolation and pre-journey effect plan, product-session/unique-scope-correlation-bound trace capture with per-scope semantics, scoped identity/settlement checks, decision consistency, task/project/process cleanup checks, dry-run and exact delete safety, operator sequence and tests are integrated on the closed S7 line. |
| `S7_REFREEZE_CONDITIONAL` | The source candidate received affected tests, all 40 automatic checks, five real `VERIFY` probes and independent cumulative review. The final test-only candidate removes a reproduced wall-clock-sensitive deadline assertion. Re-freeze is satisfied only when the complete post-commit runner, clean identity, independent review and external report/handoff all validate the exact current HEAD; otherwise S8 entry remains blocked. |
| `ENVIRONMENT` | Gateway-only Speech access, Agent model/tool route, private HTTPS/WSS proxy/cert/DNS, exact Chrome/OS/devices/network, isolated runtime/Store, service processes and real observations. |
| `USER_REQUIRED` | S8-01 text/Tool and physical Provider/device probes; every Showcase §2–8 interaction/usability observation; final Alpha decision. |
| `FINDING_FOR_S7` | `CLOSED`: the prior handoff did not bind Git-ignored `frontend/dist` to the exact frontend served by external private 443. The S7 runner and S8 consumer close it with build/served-content identities, negative tests, complete S7 rerun and independent Tier-3 review. |
| `OUT_OF_SCOPE` | Formal S8 execution, Alpha PASS, product repairs, full P3, D1/D2, Production auth/public deployment, mobile/PWA/wide browsers, credentials/accounts/billing, remote refs, signed Gate/manifest/score. |

## 5. Integration and rerun boundary

The helper, S7 runner build-identity extension, tests and documentation were
integrated after the prior S7-04 handoff. This changed candidate HEAD and made
the `a53856de` report/handoff historical rather than current A3 authority. The
coherent source candidate then received S7-01 identity, affected automation,
complete S7-02, S7-03 and all five real probes on exact clean `e58df618`.
The first exact lineage-merge run then exposed one low-frequency test-only 20 ms
wall-clock race; the deterministic clock repair received affected verification
without changing product implementation.

The final test/documentation-handoff commit must repeat the complete S7 run
before the external handoff becomes current. The affected check boundary
includes:

- `tests/unit_tests/live_voice/test_s7_alpha_verification.py`;
- `tests/unit_tests/live_voice/test_s7_real_probes.py`;
- `tests/unit_tests/live_voice/test_s8_readiness.py`;
- the S7 runner source/privacy and Markdown-link checks;
- the complete candidate run, all five real probes and cumulative review because
  the candidate identity changed.

Only external handoff binding and all runtime/human execution occur after
S7-04. The shortest command sequence is maintained in
[the operator guide](../scripts/live_voice/S8_READINESS.md#shortest-s7-04-to-s8-01-sequence).
