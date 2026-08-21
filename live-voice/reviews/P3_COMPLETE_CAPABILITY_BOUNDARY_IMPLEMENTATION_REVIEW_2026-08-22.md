# P3 complete capability boundary implementation review — 2026-08-22

## Disposition

**PASS — `0 Critical / 0 Important / 0 Minor` after fixes.**

Reviewed implementation source:
`b4e70efebc1f1eb499c883566263af5275a3d48e`.

The review is Tier 3 because the packet touches formal configuration,
authorization, durability truth, cross-language observability vocabulary and
privacy projection. It grants the scheduled pre-P3-9 code boundary only.

## Scope and non-goals

Reviewed:

- exact Direct D0/D2 profile selection and fail-closed missing/D1/unknown input;
- stable unsupported control behaviour and forbidden effects;
- Store-owned current outbox/checkpoint/effect/recovery/reconcile diagnostics;
- Registry post-authority projection, event-head race fencing and backend
  lifecycle isolation;
- HMAC identity projection, metric cardinality and Python/TypeScript fixture
  parity;
- retained D-092 retirement boundary.

Not reviewed as a positive claim: a new control primitive, D1 or generic
Executor, schema migration, external OTLP/persistent telemetry, physical audio,
P1/P2 repairs, P3-9, product readiness, deployment or remote history.

## Findings and corrections

The initial independent review returned `C0/I2/M1`.

1. Current outbox diagnostics originally used an attempt-wide sequence without
   proving every row's full identity. The final code reads the current row per
   outbox kind, uses its row-owned delivery count as the record revision, and
   validates canonical Task, Attempt, scope, Executor and command-or-recovery
   binding before projection.
2. Reconciliation state was originally present only inside an opaque seam ID.
   The final code adds `task.reconciliation_observed` with the closed
   `required/in_progress/pending/resolved` vocabulary in Python, TypeScript and
   the shared fixture. The state is a bounded dimension; no reason or raw
   identity becomes a metric label.
3. The new public diagnostics reader relied on the Registry's prior authority
   gate. It now independently revalidates current Context usability before the
   exact persisted Task context and Store snapshot read.
4. Cold review also caught missing TypeScript parity for adjustment outbox and
   potential recovery misattribution. The final code adds exact adjustment
   vocabulary parity and binds recovered checkpoint/effect facts to their
   producer Attempt. Snapshot and status event heads must match before export.

The independent focused follow-up found no remaining actionable issue and
returned **`C0/I0/M0`**.

## Verification judgement

- backend/configuration/durability/observability/retirement/AgentServer:
  `387 passed`;
- product Registry affected authority/feature-off/failed-Journey set:
  `13 passed`;
- shared TypeScript observability contract: `19 passed`;
- build profiles: `2 passed`;
- production build: PASS, 4,644 modules;
- Ruff, compileall and `git diff --check`: PASS.

This is sufficient for this coherent code boundary without repeating the full
historical Formal Web or physical-device matrix. P3-9 remains the owner of the
cumulative product Journey.
