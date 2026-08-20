# P3 Wave-2 command/admission/replay evidence — 2026-08-20

> Result: **PARTIAL — SOURCE/AUTOMATION ACCEPTED; COMPLETE PHYSICAL TOOL
> EVIDENCE NOT PRODUCED.** P3-2, P3-3 and P3-5A are implemented, locally
> integrated and independently reviewed. The bounded private production run
> proved two-project Direct dispatch/start/running, but it did not produce the
> required paired real file-Tool observations or reach A2 queue/dequeue,
> adjustment and cancel. No positive evidence JSON is synthesized.

## 1. Exact source and privacy boundary

- Activation baseline: `b1a6290b6ccbe5948c5700a8c6e103798160d7f1` on
  `hx/0812_live_voice_w3`.
- Exact second-run source: `fcf029625a589d4843a35d81ec69724d2ab453e1`.
- The source worktree was clean before and after the bounded run. Both target
  repositories were source-external, ACL-private, no-remote Git repositories.
- Existing `config.yaml` and `.env` were copied by basename only into each
  private root. Their values, hashes and diffs were never read, printed,
  uploaded, staged or included here.
- The producer suppressed Python/native/child stdout and stderr. Its only
  second-run output was the closed line
  `{"ok":false,"reason":"REAL_PRODUCER_FAILED"}`.
- Remote refs were untouched.

The positive JSON contract in
[`p3_wave2_real_evidence.schema.json`](../../scripts/live_voice/p3_wave2_real_evidence.schema.json)
requires exact A1/A2/B1 bindings, paired observations, the complete control
journey and cleanup truth. Those facts were not all present. Consequently
`P3_WAVE2_REAL_EVIDENCE_V1_20260819.json` is intentionally absent rather than
filled with invented IDs, observations or booleans.

## 2. Current-source automated evidence

| Boundary | Exact result |
|---|---|
| Integrated P3-2/P3-3/P3-5A/Task6/Task7 affected suite | **879 passed, 5 skipped, 0 failed** in 322.09 s; skips are platform-specific POSIX/configuration-symlink cases on Windows |
| Shared Python contract and formal policy | **87 passed, 0 failed** |
| Strict TypeScript/JavaScript contract | **40 passed, 0 failed** |
| Task7 Store-root/junction final affected suite | **184 passed, 3 skipped, 0 failed**; final junction reviewer also ran 8 counterexamples |
| Static/build | broad changed-surface Ruff, `compileall`, Git diff check and frontend production `npm run build` passed; Vite emitted only existing chunk/dynamic-import warnings |
| Independent review | Tasks 1–6 cumulative review and final Task7 security review each reported **0 Critical / 0 Important / 0 Minor** after their recorded repair rounds |

These results establish automated and source-review credit. They do not replace
the missing physical file-Tool proof.

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

## 4. Physical claim disposition

| Required claim | Disposition |
|---|---|
| Production registration/factory and persisted Direct dispatch | **PROVED by durable closed facts**, but not packaged by the positive JSON validator |
| Two different projects simultaneously Direct-running | **PROVED** by overlapping Direct journal intervals and distinct clean project roots |
| Persisted selected Direct adapter/profile | **PROVED** for A1/B1 |
| Paired real file write/edit Tool observations | **NOT PROVED**; no validated observer artifact or target effect |
| A2 `EXECUTOR_PROJECT_BUSY`, zero pre-release effect and same-Attempt dequeue | **NOT REACHED** |
| A2 checkpoint adjustment and completion | **NOT REACHED** |
| Exact A1/B1 cancellation | **NOT REACHED** |
| Store reopen/terminal/result match | **CONTRADICTED by unresolved running Core state after Direct interruption** |
| Complete Agent/worker cleanup | **NOT PROVED**; Direct owner/lease facts cleared and targets are clean, but Store reconciliation remains pending |

The second root is retained under its private ACL as `CLEANUP_PENDING`; no
recursive deletion is attempted while full cleanup authority is unproved.

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
  projects manual reconciliation without fallback. D1/D2 remain P3-4 scope.
- **Physical limitation:** A1/B1 real Direct overlap is proved, but the required
  file-Tool pair and A2 busy/dequeue/control journey remain unproved.

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

The Wave-2 source package is reviewable and automated-green, while its required
complete physical Direct/Agent/file-Tool proof remains **PARTIAL**. Overall P3,
feature completeness, controlled product readiness and Production remain false.
Another private Provider run is outside this packet's one-fresh-root retry
limit and requires a new explicit execution decision after diagnosing the real
file-Tool emission/cleanup environment. See the scoped
[implementation review](../reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md)
and current [STATUS](../STATUS.md).
