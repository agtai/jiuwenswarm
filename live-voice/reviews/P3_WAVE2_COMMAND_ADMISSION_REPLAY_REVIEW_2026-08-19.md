# P3 Wave-2 command/admission/replay implementation review — 2026-08-20

> Status: **PARTIAL ACCEPTANCE.** P3-2, P3-3 and P3-5A source implementation,
> affected automation, schema compatibility and independent Tier-3 code review
> pass. The bounded real run proves two-project Direct concurrency but not the
> required successful file-Tool/A2/control/cleanup journey. This review does not
> grant complete physical P3-3 acceptance, complete P3, controlled-candidate or
> feature-complete credit.

## 1. Authority, baseline and scope

- Branch: `hx/0812_live_voice_w3`.
- Activation baseline: `b1a6290b6ccbe5948c5700a8c6e103798160d7f1`.
- Exact physical-attempt source: `fcf029625a589d4843a35d81ec69724d2ab453e1`.
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

Final child and cumulative reviewers reported **0 Critical / 0 Important /
0 Minor** after these fixes. The final Store-junction review independently
proved both junction levels cause zero external database and registration
effect.

## 4. Verification

| Boundary | Result |
|---|---|
| Integrated affected Python suite through Task7 tooling | **879 passed, 5 skipped, 0 failed** in 322.09 s |
| Final Store-root/junction affected suite | **184 passed, 3 skipped, 0 failed** |
| Shared Python contract/policy | **87 passed** |
| Strict TypeScript/JavaScript contract | **40 passed** |
| Frontend production build | **PASS**, 4,643 modules transformed; existing Vite warnings only |
| Python static/compile and Git whitespace | **PASS** |
| Tasks 1–6 cumulative independent review | **APPROVED, 0/0/0** with additional Core/Store/ACK/Direct/JS focused cases |
| Task7 final security review | **APPROVED, 0/0/0** after all process/output/ACL/path repairs |

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
- **P3-3:** all applicable automated/source dimensions pass. The private run
  proves real selected Direct concurrency only; successful file-Tool pairing,
  A2 admission/control and clean settlement remain unproved.
- **P3-5A:** all applicable automated/source dimensions pass. P3-5B filtering,
  presentation invocation and Production retention remain excluded.
- Every unauthorized, malformed, mismatch, stale, duplicate, timeout, unknown,
  failpoint and cross-scope mutation path retains its scoped zero-forbidden-
  effect evidence.

## 6. Physical review disposition

The second bounded run produced two selected A1/B1 Tasks on distinct projects,
two delivered dispatches and overlapping Direct-running intervals. Both target
repositories remained clean. It produced no positive evidence JSON, no A2, no
adjustment/cancel and no successful file write/edit target effect. After the
Job-owned interruption, canonical Tasks remain running while Direct journals
are interrupted and Store reconciliation is pending with
`EXECUTOR_STATUS_SELECTION_PROOF_REQUIRED`.

The precise Provider/model/network/Agent/Tool cause is not established because
private content was deliberately not inspected. Full Agent/OS-worker cleanup
is also not proved, so the private root remains `CLEANUP_PENDING`. These facts
forbid a complete physical or P3-3 acceptance claim.

## 7. Final judgement and non-claims

The source implementation is accepted as a clean local Wave-2 package candidate
subject to the final post-document regression. The physical evidence Gate is
**PARTIAL**, not PASS. A further real run is outside the accepted one-fresh-root
retry bound and requires a new explicit execution decision after diagnosing the
file-Tool/cleanup environment.

No complete P3, feature-complete, controlled product-readiness, Production,
P3-4/P3-5B/P3-6/P3-7/P3-8B, deferred P1/P2, `develop`, remote-ref or push credit
is granted by this review.
