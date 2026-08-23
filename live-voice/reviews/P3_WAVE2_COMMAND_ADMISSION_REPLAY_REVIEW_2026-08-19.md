# P3 Wave-2 command/admission/replay implementation review — 2026-08-20

> Status: **PASS — SCOPED WAVE-2 ACCEPTANCE.** P3-2, P3-3 and P3-5A source
> implementation, affected automation, schema compatibility, independent Tier-3
> code review and the required physical file-Tool/A2/control/cleanup journey
> pass. This review does not grant complete P3, controlled-candidate,
> feature-complete or Production credit.

## 1. Authority, baseline and scope

- Branch: `hx/0812_live_voice_w3`.
- Activation baseline: `b1a6290b6ccbe5948c5700a8c6e103798160d7f1`.
- Exact physical-attempt source: `fcf029625a589d4843a35d81ec69724d2ab453e1`.
- Exact post-diagnostic source candidate:
  `534a04fbac40be633d0f275357958992a25cfca1`.
- Exact successful physical source:
  `3aa61f0193ac25e3da277f2dd632870355baf95a`.
- Governing decisions: D-060/D-062 parallel ownership, D-084 completion
  boundaries, D-087 command/admission/replay contract and D-088 Wave-2 packet.
- Preparation maps:
  [P3-2/P3-5A](P3_2_P3_5A_ACTIVATION_PREPARATION_2026-08-18.md) and
  [P3-3](P3_3_CAPABILITY_ADMISSION_ACTIVATION_PREPARATION_2026-08-18.md).
- Risk: Tier 3. The package changes shared wire authority, SQLite migration and
  verification, Executor selection/admission, Direct lifecycle composition and
  persistent consumption.

Explicit exclusions are P3-4 D1/D2, P3-5B presentation filtering/invocation,
P3-6 product successor targeting, P3-7 UI, P3-8B retirement, deferred P1/P2
repair, complete P3, controlled-candidate, feature-complete, Production,
`develop` integration and every remote update.

## 2. Accepted implementation facts

### P3-2

- Shared Python/TypeScript contracts define the closed Wave-2 command and
  disposition vocabulary.
- Store schema v4 implements one-transaction pre-dispatch update, exact replay,
  narrowed retry/adjust/cancel settlement and one-winner successor creation.
- Authorized Store-owned rejected/unsupported/conflict decisions persist only a
  versioned irreversible sanitized binding; sensitive instruction/input/reason/
  adjustment/spec text is never persisted in reversible negative fingerprints.
- `provide_input`, `pause`, `resume` and unsupported running-update variants
  remain truthfully durable `unsupported|conflict`; no Executor control method
  is invented.

### P3-3

- The Direct capability profile and execution requirements are immutable,
  canonical and digest-bound. The selector closes operation versions, D0,
  project mutation, exclusive project serialization and enforcement facts.
- The sole schema-v5 migration adds exactly ten nullable Attempt selection/
  admission fields plus the P3-5A consumption table. Legacy Attempts keep all
  ten fields null.
- Admission implements priority/FIFO, closed project-busy/capacity defer,
  exponential capped backoff, absolute deadline/attempt exhaustion, safe
  timeout versus reconciliation gap, and legal queued reprioritization.
- Composition selects before Store/Agent allocation, persists the exact
  selection, reuses it on retry and binds Direct dispatch/status/cancel/adjust
  to the selected adapter/profile without fallback.

### P3-5A

- Retained immutable TaskResult and TaskEvent reads survive restart and do not
  depend on mutable artifact bytes.
- `task.unread_events` is a pure query. `task.ack_events` is the only consumption
  mutation; text and voice traverse the same sequence with independent
  watermarks.
- ACK authority binds the exact retained event by composite FK and a type-exact
  chained command history with canonical one-to-nine-digit timestamp ordering.
- The narrowly grandfathered v5 legacy seed must be adopted before advancing;
  runtime-owned rows reconstruct exactly from ledger history.

### Integration and tooling

- The product factory composes selected admission into the current
  authenticated Direct path; historical cancel settlement is verified against
  its owning Attempt segment.
- A default-off, content-free stream observer emits only closed identities,
  counters, kinds, statuses, timestamps and one-way digests. It never exposes
  raw arguments/content/results/provider values or host paths and cannot affect
  execution.
- The private evidence producer/validator uses a closed 64 KiB schema, strict
  identity pairing, canonical time, Windows Job ownership, private DACL and
  reparse/junction protection. Non-Windows physical production fails closed
  before spawn because a portable whole-descendant ownership primitive is not
  implemented.
- Post-run repairs preserve closed stage failures across the worker boundary,
  mark success only at the trusted Tool callback completion boundary with
  failure-first structured validation, and settle Direct terminal status into
  canonical Store truth before releasing shutdown bindings.

## 3. Review and repair history

Every child implementation used isolated worktrees and strict RED→GREEN. Main
alone composed local history. Review repairs included:

- P3-2: irreversible durable decision binding, malformed-successor rejection,
  command-specific reopen proof, cross-scope isolation, historical v4 replay and
  command-local correlation.
- P3-3: immutable selected-versus-legacy authority, manual reconciliation
  monotonicity, single-read snapshots, enqueue-time authority and finite/numeric
  policy bounds.
- P3-5A: immutable legacy-seed provenance, temporal separation, chained ACK
  history, nanosecond ordering and recursive JSON type equality.
- Task6: persisted Direct control selection, adjustment completion reread,
  reverse factory cleanup, journal connection/setup closure and historical
  cancel outbox/count verification.
- Task7: invalid Tool identity pairing, canonical timestamp/run binding, A2
  authority-surface proof, DACL/junction/FD/source protection, global deadline,
  stable Windows Job ownership, non-owned output retention, POSIX positive-claim
  retirement, product Store-root placement and two-level Store junction rejection.
- Post-run diagnostics: exact stage-reason propagation, immediate predicate
  failure, real rail→adapter→observer success provenance, nested failure-first
  classification and status-only post-Direct-close settlement. A broad rerun
  also exposed and closed nested business-status misclassification and a
  load-sensitive physical-process test window without changing production timeouts.

Final child and cumulative reviewers reported **0 Critical / 0 Important /
0 Minor** after these fixes. The final Store-junction review independently
proved both junction levels cause zero external database and registration
effect.

## 4. Verification

| Boundary | Result |
|---|---|
| Final integrated P3-2/P3-3/P3-5A/Task6/Task7/rail suite | **1008 passed, 5 skipped, 0 failed** in 235.33 s |
| Final Store-root/junction affected suite | **184 passed, 3 skipped, 0 failed** |
| Shared Python contract/policy | **133 passed** |
| Strict TypeScript/JavaScript contract | **40 passed** |
| Frontend production build | **PASS**, 4,643 modules transformed; existing Vite warnings only |
| Python Ruff/`py_compile`, schema v5 and Git whitespace | **PASS** |
| Tasks 1–6 cumulative independent review | **APPROVED, 0/0/0** with additional Core/Store/ACK/Direct/JS focused cases |
| Task7 final security review | **APPROVED, 0/0/0** after all process/output/ACL/path repairs |
| Fresh private Wave-2 production journey | **PASS** on `3aa61f0193ac25e3da277f2dd632870355baf95a`; producer and independent validator both returned 14 observations, 7 paired file Tools and 4 successful write/edit streams, with every scenario/cleanup check true |

The exact commands and physical facts are recorded in the scoped
[evidence](../evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md).
The final fresh combined rerun above, shared contract checks, production build,
static checks and the full Live Voice local-link inspection all passed before
this document was committed.

## 5. Tier-3 disposition

The detailed P/N/B/S/T/C/R/I/F/K/X mapping is in the evidence record. Review
conclusions are:

- **P3-2:** all applicable automated/source dimensions pass. Core/Store
  successor completion does not imply a P3-6 product-carrier journey.
- **P3-3:** all applicable automated/source dimensions pass. The successful
  private run proves real selected Direct concurrency, successful file-Tool
  pairing, A2 admission/control and clean settlement.
- **P3-5A:** all applicable automated/source dimensions pass. P3-5B filtering,
  presentation invocation and Production retention remain excluded.
- Every unauthorized, malformed, mismatch, stale, duplicate, timeout, unknown,
  failpoint and cross-scope mutation path retains its scoped zero-forbidden-
  effect evidence.

## 6. Physical review disposition

The first two bounded attempts remain immutable historical failures. A third,
separately authorized fresh ACL-private Windows run executed the repaired source
at `3aa61f0193ac25e3da277f2dd632870355baf95a` and returned the closed aggregate
`14 observations / 7 paired file Tools / 4 successful write-edit streams`.

The producer observed and recorded distinct A1/A2/B1 Task and Attempt bindings,
four exact run bindings, production registration/factory use, persisted
profile/requirements, real Agent and Tool observation, two-project concurrency,
A2 busy queuing with zero pre-release effect, same-Attempt dequeue, A2
adjustment, exact A1/B1 cancellation, Store reopen match, source integrity and
cleanup. The independent validator does not re-observe the runtime; it enforces
the closed schema, binding/pair/count consistency and that every required check
is true. Observer failures, drops, unknowns, sequence gaps and unpaired
observations are all zero.

The 9,404-byte positive artifact and machine-private configuration remain
outside Git. The evidence document retains only its closed aggregate/boolean
dispositions, exact Git source and private-root basename; full Task/Attempt/run
IDs and Tool identity digests remain private. No process remained bound to the
successful private root after the run; the older two failed roots remain
`CLEANUP_PENDING` and were not reused or deleted.

## 7. Final judgement and non-claims

The source implementation and scoped physical Wave-2 Gate are **PASS** on the
exact clean source `3aa61f0193ac25e3da277f2dd632870355baf95a`.

No complete P3, feature-complete, controlled product-readiness, Production,
P3-4/P3-5B/P3-6/P3-7/P3-8B, deferred P1/P2, `develop`, remote-ref or push credit
is granted by this review.
