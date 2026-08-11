# Week 1 A-package implementation review

> Review date: 2026-08-04
>
> Candidate base: `f12a790b3925ad85d1f96b44223139c3a3d5178d`
>
> Reviewed commit: the commit containing this record; obtain its exact SHA from Git
>
> Scope: `W1-P1A`, `W1-P2A-CR`, `W1-P2A-PORTS`, `W1-P3A-TC`, and `W1-P3A-PORTS`

This record contains the detailed W1-S2 implementation review. Current progress and next actions remain authoritative only in [STATUS.md](STATUS.md).

## Review result

The implementation matches the bounded A-package contracts. The applicable verification was repeated after creating the immutable commit containing this record, so the grouped W1-S2 review is `CLOSED` for these bounded A packages.

| Package | Implemented outcome | W1-S2 result |
|---|---|---|
| `W1-P1A` | Provider-neutral recognition/synthesis records and deterministic fakes; exact response playback queue in the frontend | `CLOSED` for the bounded Port/fake package |
| `W1-P2A-CR` | Server-owned interaction/turn/response reducer plus a fixture-backed validating frontend replica | `CLOSED` for the bounded reducer/replica package |
| `W1-P2A-PORTS` | Bounded media, capability-checked interaction actions, and non-blocking committed-turn Agent bridge | `CLOSED` for the bounded Port/fake package |
| `W1-P3A-TC` | Pure in-memory P3alpha command/query/task/attempt reducer with replay, authorization, cancel fence, and projection behavior | `CLOSED` for the bounded in-memory Core package |
| `W1-P3A-PORTS` | Truthful fake Executor and committed structured voice-intent mapper | `CLOSED` for the bounded Port/fake package |

No real Provider, media transport, Harness adapter, persistent Store/outbox, production authorization, restart guarantee, public API, UI route, or Integrated Demo is claimed. These packages receive no Demo Replacement Ledger credit.

## Actual implementation boundary

### P1 speech and audio

- Recognition declares batch/stream capability, preserves immutable raw/display alternatives, and keeps unknown confidence unknown.
- Partial, final, and cancel ordering is explicit. A recognition final is evidence only and cannot create a TurnCommit or invoke Agent, Tool, or Task behavior.
- Synthesis preserves display text, source spans, explicit transforms, response identity, response fence, and Provider/fallback provenance.
- The frontend audio queue accepts only the current exact response and contiguous chunks. Replacement, stale response, invalid Provider facts, and out-of-range acknowledgement have zero playback effect; local stop does not widen cancellation scope.

### P2 conversation and realtime

- The server runtime is the canonical owner of interaction, turn, response generation, cancellation, and output fencing for this package.
- TurnCommit is immutable and once-only. Response generations increase monotonically; replacement and interaction close fence stale output without cancelling a task.
- The frontend is a validating replica and effect selector, not a second lifecycle owner. The shared fixture proves server/replica parity.
- Realtime Media owns only bounded frame delivery and acknowledgement. Interaction Engine validates capabilities without changing lifecycle. Agent Bridge accepts committed turns only, preserves identity/source facts, and returns without waiting for a slow Agent result.

### P3alpha task

- Task Core accepts exact create/cancel commands and read-only get/list/status/events queries under a trusted scope and operation grant.
- Canonical fingerprints make same-command replay stable and conflicting reuse fail before mutation. Task and attempt transitions are closed; terminal outcome is required and irreversible.
- Cancel records one exact control intent and dispatch fence. Executor acknowledgement is not terminal evidence, and repeated cancellation does not emit another control intent.
- WorkProgress is a read-only projection. Executor and Voice Task Bridge own no Task state; partial, ambiguous, unconfirmed destructive, and cross-scope voice intents create no command or execution effect.

## Review corrections made before sign-off

The first implementation pass was corrected during independent diff review:

1. Shared transition validation received enum values instead of `StrEnum` objects, preserving strict string validation.
2. Closing an interaction now fences its active response and rejects new responses; a fenced old response may record terminal state without producing output.
3. The frontend replica now rejects response-generation rollback and response-ID reuse.
4. Agent source provenance is retained as canonical JSON and validated exactly instead of being flattened into lossy strings.
5. Media acknowledgement cannot discard a frame that has not been delivered to its consumer.
6. Output selection is restricted to UI, history, and audio effects and rejects Agent, Tool, or Task mutation effects.
7. Recognition rejects boolean confidence; synthesis rejects stale response fences while allowing a stale Provider cancellation callback to finish without output.
8. Task cancellation now records a dispatch fence and one deduplicated control intent; Executor capabilities and WorkProgress read-only behavior are explicit.
9. Audio playback validates Provider support/provenance, response reuse, delivery bounds, and display-span preservation.

The final diff review found no additional actionable defect within the bounded package contracts.

## Scenario evidence

| Dimension | Evidence and result | Excluded claim |
|---|---|---|
| P — positive | Recognition/final/synthesis/playback; turn commit/response replacement; task create/attempt terminal; exact committed voice create/cancel all pass | no real Provider, Agent, Harness, or UI journey |
| N — negative | Partial/uncommitted, unauthorized, cross-scope, unsupported capability/operation, wrong response/epoch/provider, and illegal transitions reject before effects | no production identity or authorization policy |
| B — boundary | Empty/unknown confidence, sequence gaps, bounded media overflow, acknowledgement bounds, terminal outcome, cursor reads, and exact IDs are covered | no production payload/retention limits |
| S — state | Closed transition tables, once-only commit, response fencing, recognition terminal order, task/attempt terminal immutability, and cancel orthogonality pass | no full P3 operation set |
| T — timing | Slow Agent submission is non-blocking; stale generation/chunk/callback and cancel-ack races retain the current authority | no real network/device timing evidence |
| C — concurrency | Concurrent TurnCommit and duplicate Task create converge on one result; idempotent Executor delivery and cancel-control dedup pass | no multi-process Store transaction claim |
| R — retry/recovery | Same-process command replay, duplicate delivery, response replacement, and stream cursor replay are stable | no restart reconciliation or durable recovery claim |
| I — isolation | Exact scope/response/task/attempt/connection identities prevent cross-scope mutation; interaction close cannot cancel Task | no authenticated multi-user isolation claim |
| F — failure | Invalid Handler output, overflow, conflict, unsupported behavior, and unknown Executor status fail closed and truthfully | no real Provider/Harness outage evidence |
| K — compatibility | Shared v2 contract plus existing schedule request/task service regressions pass; current V0/legacy routes are not wired or modified | no formal replacement credit |
| X — integration | Fake Core+Executor preserves task/attempt identity; server/replica fixture parity and production frontend build pass | `W1-X2` fake verticals and user-facing Integrated Demo remain next work |

All negative paths capable of affecting Agent, Tool, Task, audio, history, or lifecycle state assert rejection or zero forbidden effects. Dimensions that require real adapters, persistence, process restart, authentication, devices, or end-to-end wiring remain validation gaps rather than manufactured evidence.

## Verification evidence

Commands were first run in the worktree based on `f12a790b` and repeated after creating the commit containing this record. The committed tree is the immutable evidence identity; use Git to retrieve its exact SHA.

- Python focused plus affected regressions: `188 passed in 6.33s` using `.venv\Scripts\python.exe`, covering the shared v2 contract, all eight new Live Voice suites, schedule task service, and schedule request.
- Python focused A-package suites: `53 passed`.
- Frontend: shared v2 contract `25 passed`; conversation runtime `8 passed`; audio port `8 passed`; total `41 passed`.
- Ruff format/check: passed for the new Python source and tests.
- Prettier: passed for the new TypeScript source and tests.
- Vite production build: passed; only the pre-existing Browserslist age and chunk-size warnings remain.

The system-default Python now has pytest installed, but it does not contain all JiuwenSwarm runtime dependencies. The repository `.venv` is the verified Python environment for project tests.

## Remaining validation gaps and next package

1. Execute `W1-X2` to compose the three deterministic fake verticals and verify fault isolation and truthful route reporting.
2. Decide `W1-P1B` as a fallback Adapter package; it is not a real streaming Provider.
3. Use W1-S3 to decide whether the formal P3alpha projection can reach the cumulative Demo without adding the disposable D-031 polling path.
4. Real media, Agent/Harness, Store/outbox/restart, authentication, Windows device, and cumulative E2E acceptance remain later B/C or integration Gates.
