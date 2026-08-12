# Live Voice current status

> Updated: 2026-08-12
> This is the only mutable source for current branch expectations, stage/task,
> module closure state, blockers and next actions. Detailed contracts remain in
> the linked plan/acceptance documents; history is conditional.

## Resume capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `origin/hx/0812_live_voice_w3`. Always verify live Git; do not copy a HEAD or
  ahead/behind count from prose.
- Current stage/node: `S5 — Alpha Baseline & Gap Freeze` / `A0`, `IN PROGRESS`.
- Current task: `S5-01 — exact-source acceptance audit` in the active
  [S5–S8 plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md).
- Next gate: `S5-02` freezes user-controlled Speech/product/environment inputs;
  `S5-03` then activates the first A1 closure batch.
- Closed: S0 V0, S1 Shared Foundations, S2 D-031 bounded compatibility,
  S3 W2 Integrated Demo (`PRODUCT-ACCEPTED`) and S4 develop rebaseline.
- Open: every Alpha module closure, A1, A2 and A3. Existing implementation is
  substantial, but no module is yet labeled `Alpha CLOSED`.

Terminology follows D-075: S0–S9 are sequential stages; A0–A3 are Alpha nodes;
P1/P2/P3alpha/Shared-X are capability tracks; named components are modules;
`*-A/B/C` are work packages; W1/W2/W3/W4 are historical windows only.

## Current S5/A0 result

D-076 has frozen task IDs, dependencies, risk, oracles and exclusions. The
source audit currently supports this verify-first split:

| Closure group | Existing source-backed base | Alpha closure still required |
|---|---|---|
| Shared/X | ACG v2 foundations, critical-token policy/tests, correlated metrics/exporter/fault harness and Web diagnostics exist | Wire protected critical-input safety; complete consumer audit; add benchmark reporting and controlled whole-stack audio/privacy proof |
| P1 — AIO/SR/SS | Browser capture/playout lifecycle, formal batch STT/TTS, exact stop and Browser fallbacks exist | Select streaming route or accepted deviation; verify declared Chrome/device lifecycle, ordered provenance, corpus quality and p50/p95/failure/sample results |
| P2 — RM/CR/II/AB | Bounded media, generation/presentation fencing, non-blocking Agent/progress, recovery and broad race/failure tests exist | Close real network/fault/load, slow-Harness, notification, stop/revise/delegate and latency behavior |
| P3alpha — TC/ED/VB | Formal structured Task operations, durable Store/outbox, real project Executor, restart reconciliation, create/cancel mapping and origin progress exist | Add formal committed natural-language `task.status`; verify full authorization/fault/restart/real-Executor and cross-task zero-effect matrix |
| X-E2E | Many vertical/product integration and flag-off tests exist | Add one slow conversational round + detached Task joint scenario and close the complete candidate matrix |

This table is a current summary, not the detailed acceptance matrix. If source or
tests disagree, source is the implementation fact and this file must be updated.

## Decisions/blockers before A1 closes

User-controlled S5-02 inputs still required:

1. selected Alpha streaming STT/TTS Provider/Adapter and fallback, or an explicit
   bounded non-streaming deviation;
2. exact desktop Chrome/Windows, secure origin/topology, microphone/output device
   and fixed network labels;
3. real Provider/model/voice and safe failure profiles, without credentials; and
4. real D0 Executor plus recoverable isolated project target.

Machine-private credentials, Provider configuration, project registration,
browser permissions/profile, devices, runtime data and network state are not
restored by Git. Full P3, D1/D2, production auth, broader browsers/mobile/PWA,
public deployment and audit-grade certification remain outside Alpha.

## Execution policy

- Read only plan §1–2 and the current task section; do not load all S5–S8 or
  historical reviews during ordinary work.
- Verify existing formal behavior before implementing a gap. D-031 is not a
  second Task authority, and the retired signed Gate/Ledger must not return.
- Apply D-074: focused affected checks during development, complete scoped review
  at module closure, cumulative review/automation at A2, one human journey at A3.
- Coherent local commits are allowed; every remote-ref update requires separate
  exact approval. No push is authorized by this status.

## Next actions

1. Finish S5-01 by mapping every Alpha acceptance row to inspected source/tests
   and one of `SATISFIED/IMPLEMENT/VERIFY/ENVIRONMENT/DEVIATION/LATER`.
2. Present only the unresolved S5-02 product/environment choices to the user,
   then freeze S5-03 ownership and module-close commands.
3. Execute S6-01→S6-06, S7-01→S7-04 and S8-01→S8-03 in dependency order.

For a specific older milestone, module review, migration record or forensic
question, use the conditional [reference index](REFERENCE_INDEX.md). Do not read
it during ordinary resume.
