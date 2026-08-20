# P3 Wave-3 durability, presentation and intent execution packet (2026-08-20)

Status: `ACTIVE / IMPLEMENTATION AND EVIDENCE PENDING`

This is the scoped D-089 execution and eventual review record for P3-4,
P3-5B and P3-6. It grants no implementation, test, review, physical or product
credit until the corresponding evidence is recorded on an exact clean source.
Current product judgement remains owned by [STATUS](../STATUS.md), design choices
by [D-089](../decisions/DECISIONS.md), and risk/review rules by root
[`TESTING.md`](../../TESTING.md).

## 1. Baseline, owner and dependencies

- Integration branch: `hx/0812_live_voice_w3`.
- Activation HEAD and upstream: `cfff0c43aa599c009ab9517397566fec5c1bdd95`.
- Activation state: clean, ahead/behind `0/0`.
- Main is the sole W3 Integration Owner, shared semantic/schema/composition
  owner, evidence owner and remote gate owner.
- P3-4 consumes accepted P3-3 profile/admission facts; P3-5B consumes accepted
  P3-5A unread/ACK facts; P3-6 consumes accepted P3-2 command and P3-5A
  Task/Event/Result facts.
- Local branches/worktrees are `codex/w3-p3-4`, `codex/w3-p3-5b` and
  `codex/w3-p3-6`. Workers may commit only their lane and must not push.

## 2. Intended behavior and owned surfaces

### P3-4 — Executor durability/recovery, Tier 3

Implement current-Store-owned checkpoint/effect/recovery records, linked D1
recovery Attempt admission, stable D2 logical-operation reconciliation,
bounded manual-required truth and one idempotent recovery coordinator over the
selected Direct profile. The lane owns the five prepared `durability_*.py`
modules and P3-4 tests. It has a narrow, single-writer implementation lease for
`formal_task_models.py`, `task_store.py`, `persistent_task_core.py` and
`project_code_executor.py` only under D-089; Main retains their semantics and
owns final composition.

### P3-5B — presentation consumption, Tier 3

Connect P3-5A unread facts to real text DOM adoption and Runtime-owned audio
`PresentationAck`, then invoke exact class-isolated `task.ack_events`. The lane
owns presentation/parser/ACK modules and product tests. It owns no Store,
consumer schema, Task lifecycle, Result/Event truth or shared Registry/profile.

### P3-6 — multi-Task intent resolution, Tier 3

Implement a production resolver and bounded clarification state that consume
only authenticated Core-visible facts and provide natural voice, natural text
and structured parity through the existing closed policy/Core. The lane owns
Bridge/resolver/clarification/corpus modules and tests. It owns no Task/Store,
confirmation, Executor, presentation, Registry or frontend authority.

## 3. Frozen shared interfaces and exclusions

- D1 is same Task plus linked/new recovery Attempt; same-Attempt positive
  recovery is excluded.
- Store v5 is the only migration parent; at most one v6 P3-4 migration may land.
- Direct may declare only the durability/effect subset exercised through its
  public real seam. Legacy and undeclared levels remain unsupported.
- Store claim lease, Direct owner generation/runtime lease and OS lock are
  independent; no single fact proves recovery authority.
- Durable presentation key is `(subject_id, project_id, task_id,
  presentation_class)` with `text|voice`; Session is never part of the key.
- Presentation is at-least-once across the ACK/commit crash window. ACK is
  neither human-perception nor Task-lifecycle truth.
- P3-6 supports the frozen English/Chinese 68-case corpus and 14 parity groups.
  Explicit Task ID wins; exact authorized name must be unique; ambiguity never
  resolves from recency/current UI state.
- Clarification handles expire across process restart. Confirmation is separate,
  single-use and bound to exact operation/target/arguments/Task-set facts.
- P1/P2 continuation repair, P3-7/P3-8B/P3-9, complete P3, feature-complete,
  product-readiness, Production, `develop` integration and all remote updates
  are excluded.

## 4. Acceptance and physical evidence plan

Each lane records intended RED, GREEN and affected commands, then maps all
applicable `P/N/B/S/T/C/R/I/F/K/X` dimensions and forbidden side effects. Lane
closure requires cold self-review, one independent Tier-3 review, one bounded
fix batch and one fix-only review. Main integrates P3-4, P3-5B, P3-6 and shared
composition in that order, then runs one fresh broad Python suite, one Formal
Web suite, the strict JavaScript/TypeScript contracts, production frontend build
and final Ruff/format/compile/schema/diff checks.

Physical evidence first proves factory/registration, migration/reopen,
profile/checkpoint/effect identity, real DOM/audio sinks, Core-visible Task
resolution, deadlines/process ownership, cleanup and failure-artifact retention
without a Provider. The final bounded journey uses only a fresh ACL-private
root and existing private configuration. A failed root is retained as
`CLEANUP_PENDING`; no raw content or credentials enter Git.

## 5. Results

Pending implementation, integration, review, automation and physical evidence.
