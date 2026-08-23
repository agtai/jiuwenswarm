# P3 Wave-2 command/admission/replay evidence — 2026-08-20

> Result: **PASS — WAVE-2 SOURCE/AUTOMATION/PHYSICAL GATE.** P3-2, P3-3 and
> P3-5A are implemented, locally integrated and independently reviewed. A third
> explicitly authorized fresh private production run on the exact integrated
> source produced a schema-valid content-free artifact and proved the required
> real file-Tool, A2 queue/dequeue, adjustment, cancellation, reopen and cleanup
> journey. This scoped result does not grant complete P3, controlled-candidate,
> feature-complete or Production credit.

## 1. Exact source and privacy boundary

- Activation baseline: `b1a6290b6ccbe5948c5700a8c6e103798160d7f1` on
  `hx/0812_live_voice_w3`.
- Exact second-run source: `fcf029625a589d4843a35d81ec69724d2ab453e1`.
- Exact post-diagnostic source candidate:
  `534a04fbac40be633d0f275357958992a25cfca1`.
- Exact successful third-run source:
  `3aa61f0193ac25e3da277f2dd632870355baf95a`.
- The source worktree was clean before and after the successful run. The target
  repositories were source-external, ACL-private, no-remote Git repositories.
- Existing `config.yaml` and `.env` were copied by basename only into each
  private root. Their values, hashes and diffs were never read, printed,
  uploaded, staged or included here.
- The producer suppressed Python/native/child stdout and stderr. The successful
  run emitted only the closed aggregate
  `{"observation_count":14,"ok":true,"paired_file_tool_count":7,"write_edit_pair_count":4}`.
- Remote refs were untouched.

The positive JSON contract in
[`p3_wave2_real_evidence.schema.json`](../../scripts/live_voice/p3_wave2_real_evidence.schema.json)
requires exact A1/A2/B1 bindings, paired observations, the complete control
journey and cleanup truth. The successful private artifact is 9,404 bytes and
passed the independent validator with the same aggregate. Under the
documentation privacy rule it remains outside Git. This record retains the
closed booleans/counts, exact source Git facts, historical truncated target Git
facts and private-root basenames needed to correlate the attempts; it excludes
full Task/Attempt/run IDs, Tool identity digests, configuration and raw
Agent/Tool content.

## 2. Current-source automated evidence

| Boundary | Exact result |
|---|---|
| Final integrated P3-2/P3-3/P3-5A/Task6/Task7/rail suite | **1008 passed, 5 skipped, 0 failed** in 235.33 s; skips are platform-specific symlink/process cases on Windows |
| Shared Python contract and formal policy | **133 passed, 0 failed** |
| Strict TypeScript/JavaScript contract | **40 passed, 0 failed** |
| Task7 Store-root/junction final affected suite | **184 passed, 3 skipped, 0 failed**; final junction reviewer also ran 8 counterexamples |
| Static/build | broad changed-surface Ruff, `py_compile`, Git diff check and frontend production `npm run build:live-voice` passed; Vite emitted only existing chunk/dynamic-import warnings |
| Independent review | Tasks 1–7 cumulative reviews plus the post-run diagnostics, shutdown and callback repairs each reported **0 Critical / 0 Important / 0 Minor** after their recorded repair rounds |

These results establish automated and source-review credit. The separate third
run below supplies the scoped physical file-Tool proof.

## 3. Bounded private attempts

### 3.1 First root — product Store path rejection

- Private basename: `p3-wave2-d7496ca0eb37481abd36ad3bd62897dd`.
- Source: `80cc05b28be8bc474409a63009a11482bc8f679b`.
- The run failed in about ten seconds, before the product Store opened. A
  content-free diagnostic identified `INVALID_P3_AUTH_CONFIGURATION`: the
  producer had placed the configured database outside the product-owned
  `<DATA_DIR>/live_voice/p3alpha` directory.
- TDD repairs moved the Store into the product-owned directory and then closed
  a real Windows `live_voice|p3alpha` junction escape. The final repair at
  `fcf02962` received an independent **0/0/0 APPROVED** verdict.
- The failed root is not reused and remains private as `CLEANUP_PENDING`.

### 3.2 Second root — real Direct concurrency, incomplete Tool journey

- Private basename: `p3-wave2-70a51c78e32d495e868d06f8cb1a5d26`.
- Exact source: `fcf029625a589d4843a35d81ec69724d2ab453e1`.
- The run remained inside the Windows Job-owned 12-minute process bound and
  returned the closed top-level reason `REAL_PRODUCER_FAILED`. No output JSON
  was created.
- Read-only inspection was restricted to closed SQLite lifecycle fields, target
  Git HEAD/status and file basenames. It did not inspect configuration, prompts,
  command payloads, Agent history, Provider/model details or raw results.

The permitted durable facts are:

| Fact | Observed result |
|---|---|
| Tasks / Attempts | 2 / 2: A1 and B1 only; each Task and Attempt reached `running` |
| Dispatch | two `attempt.dispatch` rows, each `delivered`, `delivery_count=1`, no delivery error |
| Direct overlap | A1/B1 Direct running intervals overlap from `2026-08-20T11:57:25.036131Z` through `2026-08-20T12:08:06.366233Z` on two distinct project roots |
| Selection | both Attempts retain the same Direct adapter/profile binding; selected admission fields are present |
| A2 | no A2 Task or Attempt exists; busy queue, zero pre-release proof, dequeue and same-Attempt continuation were not reached |
| Controls | no adjustment row, no cancel event and both cancel flags remain zero |
| Results | zero `task_results`; no terminal Core event |
| Target effects | both target repositories remain clean at their initial HEADs (`f02787b8…`, `686e4c54…`) and contain only tracked `README.md` |
| Post-bound truth | canonical Tasks/Attempts remain `running` with null outcomes; Direct journals are `terminal/interrupted`; both Tasks project `pending / EXECUTOR_STATUS_SELECTION_PROOF_REQUIRED` reconciliation |
| Source | main source remains clean and unchanged at `fcf02962` |

The ordered scenario creates A2 only after A1 and B1 are both running **and**
each has a successful initial write/edit Tool call/result pair. Because A2 does
not exist and the target trees never changed, the run did not pass that first
pairing gate. `REAL_CONCURRENT_INITIAL_TIMEOUT` is consistent with the source
ordering, but it is not a persisted authorized field and is therefore an
inference, not the reported run reason. The Provider, model, network, Agent
initialization and Tool-emission root cause is explicitly unknown.

### 3.3 Post-run source diagnosis and repair

The second run's immutable facts are not upgraded, but three source gaps were
closed without reading private configuration or running a Provider:

- The producer now carries only an allowlisted closed stage reason across its
  Windows worker boundary and maps predicate failures immediately instead of
  consuming the remaining scenario budget under a generic failure.
- The trusted Tool callback boundary now marks normal callback completion as
  success without parsing private result text. Explicit, nested or malformed
  structured failure remains failure-first and content-free. The complete rail
  → adapter → Direct observer seam proves an ordinary file-Tool result can form
  a successful paired observation without a Provider.
- Composition shutdown now performs pre-close reconciliation, Direct
  quiescence/terminalization, status-only canonical reconciliation and then
  binding release. A real Direct adapter with temporary SQLite and a blocking
  fake Agent reproduces the former Direct-interrupted/Store-running split and
  proves terminal `interrupted` settlement with no new outbox delivery.

These repairs did not alter the second run's immutable facts. Their real
environment result is recorded separately in the successful third run below.

### 3.4 Third root — complete validated Wave-2 journey

- Private basename: `p3-wave2-3e06e75427c44cb5b2f48677bc578a68`.
- Exact source: `3aa61f0193ac25e3da277f2dd632870355baf95a`.
- The user explicitly authorized one fresh ACL-private Windows run using the
  existing machine-private model/Provider configuration and real Tool calls.
- The production CLI ran inside its Windows Job-owned bound and exited zero.
  Independent validation of the private artifact also returned `ok=true`.

The executed entrypoint was:

```powershell
.\.venv\Scripts\python.exe -m scripts.live_voice.p3_wave2_real_evidence_producer --private-root <fresh-ACL-private-root> --output <fresh-ACL-private-root>\raw-evidence.json
```

The absolute private parent is intentionally omitted; its unique basename and
the exact Git source above are sufficient to bind this sanitized record.

The schema-closed facts are:

| Fact | Producer-recorded, validator-accepted result |
|---|---|
| Production path | production registration and factory used; persisted profile and requirements checks all true |
| Real boundary | real Agent and real Tool observed; 7 calls and 7 results form 7 exact file-Tool pairs |
| Required successful streams | 4 write/edit pairs cover A1 initial, A2 initial, A2 adjustment and B1 initial |
| Observation integrity | 14 observations; zero observer failures, drops, unknowns, sequence gaps or unpaired observations |
| Concurrency/admission | two projects concurrent; A2 busy-queued with zero pre-release effect; the same A2 Attempt dequeued |
| Controls | A2 adjustment applied; exact A1 and B1 cancellation checks true |
| Durable close | Store reopen matched and cleanup completed |
| Source/privacy | source untouched; output stayed below 64 KiB; no process remained bound to the private root after the run |

The successful root is retained under its private ACL as out-of-Git evidence.
Unlike the first two failed roots, its validated state is `cleanup_complete`,
not `CLEANUP_PENDING`.

## 4. Physical claim disposition

| Required claim | Disposition |
|---|---|
| Production registration/factory and persisted Direct dispatch | **PROVED** by the validated third-run production checks |
| Two different projects simultaneously Direct-running | **PROVED** by the validated concurrency check |
| Persisted selected Direct adapter/profile | **PROVED** together with the exact requirements binding |
| Paired real file write/edit Tool observations | **PROVED**: 7 exact pairs, including all 4 required successful write/edit streams |
| A2 `EXECUTOR_PROJECT_BUSY`, zero pre-release effect and same-Attempt dequeue | **PROVED** |
| A2 checkpoint adjustment and completion | **PROVED** by adjustment and durable reopen checks |
| Exact A1/B1 cancellation | **PROVED** |
| Store reopen/terminal/result match | **PROVED** by the third-run reopen check; the older second-run contradiction remains historical |
| Complete Agent/worker cleanup | **PROVED within the scoped producer contract**; cleanup check true and no process remained bound to the root |

The first two roots remain retained under their private ACLs as
`CLEANUP_PENDING`; the successful third root is retained separately as validated
private evidence. No recursive deletion was performed.

## 5. D-032 package evidence map

### P3-2 — complete commands and successor Store authority

- **P/N/B:** canonical closed command/result vocabulary, pre-dispatch update,
  queued reprioritize after admission integration, exact successor creation and
  bounded UTF-8/enums/digests pass; invalid, stale, claimed, terminal and
  unsupported operations fail closed.
- **S/T/C:** durable negative decisions change only the sanitized command
  ledger; failpoints, changed fingerprints and two-Store one-winner races prove
  zero unauthorized Task/Attempt/Event/outbox/Executor effects and exact replay.
- **R/I/F/K/X:** v1–v4 compatibility, restart verification, command-local
  correlation, exact scope/Task/Attempt/event bindings and unknown/conflict/
  unsupported dispositions pass. P3-6 product successor routing and real
  unsupported controls remain excluded.

### P3-3 — capability selection and bounded admission

- **P/N/B:** immutable Direct profile/requirements selection, capacity 32,
  exclusive project serialization, priority/FIFO, busy/capacity defer, numeric
  policy bounds and absolute timeout pass. Foreign/forged profiles and invalid
  defer reasons fail before effects.
- **S/T/C:** selection mismatch has zero resolver/Store/Agent/project effect;
  deadline, TTL, three-fence, reprioritize and two-Store races preserve exact
  ownership. Store claims, Direct lease and OS lock remain separate facts.
- **R/I/F/K/X:** v5 reopen binds profile/requirements/digest and legacy all-null
  Attempts; selected observations preserve adapter/digest; unknown ownership
  projects manual reconciliation without fallback. Post-close status-only
  reconciliation now settles exact Direct terminal truth without draining new
  work. D1/D2 remain P3-4 scope.
- **Physical result:** the successful third run proves the required real
  file-Tool pairs, two-project concurrency, A2 busy/dequeue/control journey and
  clean durable settlement on the exact integrated source.

### P3-5A — retained result/event and explicit unread ACK

- **P/N/B:** immutable retained results/events, logical watermark `-1`, limits
  1–500, text/voice class isolation and monotonic explicit ACK pass; malformed,
  foreign, future, mismatched and stale ACKs fail closed.
- **S/T/C:** unread is byte-pure; durable ACK decisions do not mutate canonical
  Task authority; failpoints, frozen snapshots and two-Store races prove no
  regression or other-consumer effect.
- **R/I/F/K/X:** v5 composite event FK, exact scope/session command replay,
  legacy-seed adoption, chained ACK provenance, nanosecond ordering and
  type-exact reopen verification pass. P3-5B filtering/presentation invocation,
  retention/SLO and out-of-band whole-tail rollback detection are excluded.

## 6. Conclusion and next gate

The Wave-2 source package is automated-green, independently reviewed and its
scoped physical Direct/Agent/file-Tool Gate is **PASS** on
`3aa61f0193ac25e3da277f2dd632870355baf95a`. Overall P3, feature completeness,
controlled product readiness and Production remain false; P3-4, P3-5B, P3-6
and the deferred P1/P2 journey retain their own implementation and acceptance
boundaries. See the scoped
[implementation review](../reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md)
and current [STATUS](../STATUS.md).
