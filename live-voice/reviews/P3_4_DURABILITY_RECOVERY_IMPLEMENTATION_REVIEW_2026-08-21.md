# P3-4 durability/recovery implementation review — 2026-08-21

> Status: **PASS — SCOPED P3-4 SOURCE AND AFFECTED AUTOMATION.** The integrated
> durability/recovery source through
> `b2366e293e1f039140d6a84bc9383a8589d39bfb` passed focused and affected
> automation, cold review, independent Tier-3 review and fix-only re-review.
> This record grants no final Wave-3, complete P3, feature-complete, Production
> or remote-ref credit.

## 1. Authority, source and scope

- Branch: `hx/0812_live_voice_w3`.
- Activation baseline: `cfff0c43aa599c009ab9517397566fec5c1bdd95`.
- Reviewed integrated source:
  `b2366e293e1f039140d6a84bc9383a8589d39bfb`.
- Coherent source commits: `ec31463e`, `d8b09c78`, `5593bb55`, `39bfbd76`
  and the final migration-compatibility fix `b2366e29`.
- Governing decision: D-089 P3-4 durability/recovery packet.
- Risk: Tier 3. The package changes Executor capability truth, SQLite schema and
  verification, recovery authority, crash settlement and external-effect
  reconciliation.

Explicit exclusions are final cumulative automation, an independent
subprocess/host-crash physical oracle, P3-5B physical audio, P3-6 production
intent composition, complete Wave 3/P3, controlled candidate, feature complete,
Production, `develop` integration and every remote update.

## 2. Accepted implementation facts

- Executor durability is a closed cumulative `D0 < D1 < D2` capability. The
  ordinary Direct profile remains D0; D2 is an explicit same-Store-backed
  candidate and persisted selections never drift or silently upgrade.
- Store schema v6 is the sole checkpoint, effect-fact, recovery, mutator-lease
  and recovery-fence authority. v1-v5 migration, failpoint rollback, reopen and
  concurrent initialization retain their existing Task truth.
- Checkpoint and effect records are immutable, prefix-verified and bound to the
  selected adapter/profile, Task/Attempt/context, producer, claim and Store
  authority. Raw or copied recovery facts cannot mutate Store state.
- Operator-only Core recovery creates a linked Attempt only after independent
  Store, Runtime and OS-lock quiescence facts agree. The producer Attempt and
  its records remain immutable; cancel-versus-recovery has one transaction
  winner.
- Direct records effect intent before apply. Authoritative observation maps
  `APPLIED`, `NO_EFFECT` and ambiguous `UNKNOWN` to exact completion, safe
  replay or `manual_required`; ambiguous work is never blindly called twice.
- A lost settlement receipt after the real apply path recovers through a fresh
  Direct instance and linked Attempt without a second Agent or external apply.
- Legacy candidate-v6 databases whose only released-shape difference is
  `UNIQUE(cancel_command_id)` normalize atomically to final v6 without a schema
  bump. Any extra/changed index, CHECK, FK, PK, UNIQUE or DDL semantic fails
  closed before mutation. Rollback leaves metadata, schema and rows unchanged.

## 3. Tier-3 scenario closure

| Dimension | Accepted evidence |
| --- | --- |
| P | Real SQLite Store, public Core recovery and Direct dispatch/apply/reconcile paths complete a linked Attempt. |
| N | Forged/copied receipts, profile/context drift, corrupt prefixes and non-exact legacy-v6 shapes fail closed. |
| B | Bounded records/leases, closed capability levels and migration/index fingerprints. |
| S | Task/project/Store/profile bindings and same cancel ID in two authenticated scopes remain isolated. |
| T | Intent-before-apply, lost settlement receipt, cancel/recovery ordering and terminal producer immutability. |
| C | Two-Store claims, cancel-versus-recovery, concurrent initializer and Runtime/OS ownership races. |
| R | v1-v6 reopen, exact checkpoint resume, effect observation and linked Attempt recovery. |
| I | Per-process authenticated receipt, exact-object ownership, command/profile/status replay and immutable lineage. |
| F | Migration failpoints, corrupt record/prefix, apply-settlement failure and legacy-v6 after-replace rollback. |
| K | APPLIED/NO_EFFECT/UNKNOWN, D0/D1/D2 and completed/interrupted/manual-required truth remain distinct. |
| X | Rejected paths assert zero Task/Attempt/outbox/Agent/external-apply/foreign-scope changes as applicable. |

## 4. Automated and static evidence

- P3-4 Store plus shared Core after final compatibility repair:
  `377 passed in 51.76s`.
- Legacy candidate-v6 positive/negative shape set: `5 passed`; the two
  executable negatives first failed because extra index/CHECK shapes were
  accepted, then passed after the legacy-only exact signature fix.
- P3-5B cursor/retry regression nodes after the Store repair: `4 passed`.
- Earlier affected Direct executor set: `127 passed, 2 platform skips`;
  focused Runtime/capability and durability paths passed their scoped suites.
- Ruff check, scoped format check, `py_compile` and `git diff --check`: PASS.
  The whole-file formatter debt in `test_persistent_task_core.py` is identical
  on the clean parent and was not expanded.

## 5. Independent verdict and remaining Gates

The first final review found one Important: the legacy fallback accepted an
extra ordinary index or CHECK and silently removed it. Exact RED tests captured
both cases. The fix-only review then returned
`0 Critical / 0 Important / 0 Minor`, confirming that only the exact released
candidate shape can normalize and every drift is rejected before any migration
failpoint or write.

P3-4 source and affected automation are therefore scoped PASS. P3-6 product
composition, the final cumulative broad Gate and the minimum honest private
physical journey remain required before Wave-3 acceptance.
