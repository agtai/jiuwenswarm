# D108 — Project progress and governance review

> Date: 2026-08-12
>
> Type: frozen documentation/governance review
>
> Mutable project state remains in [STATUS.md](STATUS.md). This record explains the assessment and the rule changes accepted as D-074; it does not create a new product acceptance result.

## 1. Source boundary inspected

- Branch: `hx/0812_live_voice_w3`, tracking `origin/hx/0812_live_voice_w3`.
- Starting source: `9b8ede225dcc0c421c253a71358ffd676c4aad1b`, with the branch clean and `0/0` against its upstream at the start of this review.
- W2 tested product source remains `23686c5f87af4698ff350db19b28740a54d39713`; the W3 migration preserves that accepted result but does not manufacture a new Alpha acceptance.
- The W3 migration closure and its automated results are owned by [D107](D107_W3_DEVELOP_REBASELINE_MIGRATION_2026-08-12.md). This governance-only review does not rerun those runtime suites.

## 2. Completed work

1. V0 is frozen and closed: real microphone input reaches the real JiuwenSwarm Agent/Tool route and the truthful final response is spoken.
2. Week 1 foundations are closed: the ACG v2 kernel, P1/P2/P3alpha A packages, deterministic fakes, telemetry foundation and Browser fallback exist with their historical module reviews.
3. D-031 is closed only as a bounded Compatibility Adapter. It does not own formal Task Core, Event Store or Executor semantics.
4. W2 is `PRODUCT-ACCEPTED` under D-071. Automated checks and one complete user-observed journey passed physical P1, real Agent/Tool P2, audible correction/stop, non-blocking P2/P3alpha, same-task A→B→C, refresh/restart recovery and visible degradation/text fallback. [D105](D105_W2_PRODUCT_ACCEPTANCE_2026-08-11.md) is the acceptance record.
5. The signed evidence Gate, fixed 38-slot manifest, Replacement Ledger scoring, repeated full-showcase ceremony, evaluator/exporter/rehearsal controller and Gate-only fault seams are retired and removed under D-071/D-072. They are not current blockers or tools.
6. The W3 develop rebaseline is complete. The branch adopts develop's current APIs and deletion intent, removes accidental restoration of retired prompt/file-loading behavior, preserves the public Agent-start contract, connects the replacement anomaly rail, hardens Task Store WAL startup and updates the lock. D107 records backend `1211 passed, 2 skipped`, affected `49 passed`, WAL `20/20`, frontend `579 tests` and production build PASS.

## 3. Not completed

Integrated Web Alpha is the next milestone and has not yet passed its acceptance contract. The next implementation cycle must first turn these open requirements into a scoped gap assessment and coherent batch plan:

- P1: permission grant/denial/revocation, device selection/change/loss, autoplay and page hidden/background/resume lifecycle, plus real-device p50/p95 latency and failure measurements.
- P2: stronger multi-turn/streaming/load behavior, bounded media fault behavior and measurements beyond the accepted W2 journey.
- P3alpha: the complete structured plus committed-language create/get/list/status/cancel/events matrix, injected atomicity/recovery cases, and the full progress/failure journey rather than only the accepted W2 subset.
- Joint P2/P3alpha: the complete concurrent slow-round plus detached-task scenario, interruption/revision, exact task query/cancel, blocked/decision/terminal progress and cross-scope zero-error assertions.
- Web/platform/privacy: raw-audio zero-persistence regression, permission/device/background diagnostics, declared Chrome/OS/origin/device/network baseline, selected Provider/Executor failure profiles, and deployment-topology checks where non-localhost Alpha is claimed.
- X-OBS/release boundary: Alpha-relevant trace/metric reproduction remains to be selected; remote exporter, retention policy, operational SLO backend, production authentication, complete P3, wider browsers, public deployment and RC hardening remain later work unless scope changes.
- Final Alpha closure: identify a clean tested source, run applicable automated suites and one complete human Alpha journey. W2 observations may be reused only where later changes do not affect them.

No current source defect is recorded as a blocker to starting this assessment. Provider credentials, project registration, browser permission/device state, runtime data and network availability remain machine-private external conditions.

## 4. Governance audit

| Rule or decision | Assessment | Current treatment |
|---|---|---|
| Signed evidence Gate, Replacement Ledger, 38-slot manifest and repeated rehearsal | No longer proportional to the product goal; already consumed excessive time | Retired by D-071 and removed by D-072; never restore without a new audit/compliance requirement |
| Architecture Contract Gate | Still useful, but the word “Gate” can be confused with the retired evidence process | Keep as the shared protocol/authority contract; clarify that it is not the deleted signed-evidence acceptance system |
| Per-commit explicit approval | Unnecessarily interrupts a coherent implementation or documentation batch | Removed by D-074 for ordinary local stage/commit inside authorized scope |
| Very small/checkpoint commits | Add noise and make review/integration harder | Avoid; commit at coherent module, defect batch, integration batch or documentation-decision boundaries |
| Remote push approval | Still appropriate because it changes shared external state | Keep exact approval for each remote/ref/commit/update mode; workers never push |
| D-032 universal pre/post ceremony | Already partially superseded by risk tiers; its invariant checks remain valuable | Keep contract-first scenarios and zero forbidden effects; require a design checkpoint only for a new/changed high-risk contract |
| D-053 three passes for every Tier 2/3 implementation batch | Too frequent when a module needs several small iterations; repeated complete diffs do not add proportional evidence | Superseded in cadence by D-074: affected review during work, full scoped review at module closure, cumulative review at phase closure |
| Independent `/review` | Valuable for high-risk semantic blind spots, but not for every intermediate edit/commit | Require once at Tier 2/3 module or grouped-boundary closure and for risk-critical phase integration; record an honest substitute if unavailable |
| Full diff review | Correct in principle, but its comparison boundary must match the work | Use affected diff while iterating, module-start→module-end diff at module closure, and phase-baseline→candidate cumulative diff at milestone closure |
| D-060 fixed four Sessions | Historical decomposition, already superseded by D-062 | Do not treat four lanes as current; use only an active packet's non-overlapping ownership graph |
| D-062 adaptive parallelism and single integration owner | Still useful when work is actually independent | Keep as optional execution mechanics; do not create work merely to occupy capacity |
| D-070 cross-model role assignment | Completed W2-specific execution choice | Historical only; it does not assign current Alpha work |
| D-061 one cumulative smoke after a reviewed integration batch | Proportional and efficient | Keep; conflict resolution/integration glue still gets focused checks before the aggregate run |
| D-071 automated verification plus one complete human journey | Fits the current Demo/Alpha objective | Keep; rerun only affected human steps after later changes |
| D-073 develop deletion/migration intent | Correct and recently proven necessary | Keep for future rebaseline work |

## 5. New operating cadence

1. **During module work:** inspect the affected diff, run focused positive/negative/flag-off/regression checks and add tests for newly exposed risks. Commit only when the change is a coherent reviewable unit.
2. **At module or grouped-package closure:** review the complete scoped diff against the original request, current contracts, existing behavior and actual tests. Tier 2/3 changed boundaries receive one independent review or an explicitly documented equivalent.
3. **At integration-batch closure:** review conflicts and glue, run affected checks, then one cumulative smoke after the reviewed batch is assembled.
4. **At phase/milestone closure:** review the cumulative candidate diff and cross-module seams, run the broad applicable automated matrix, then complete one D-071 human product journey on the identified tested source.
5. **After findings:** fix and rerun the affected scope. Repeat a larger review only when the fix materially changed that larger scope.

This cadence is recorded normatively in D-074, root `AGENTS.md`, the roadmap and documentation rules.

## 6. Decision

The project is ready to move from W3 migration closure into an Alpha gap-assessment batch. Governance cleanup is necessary because the current documents still carried W2-only lane assignments, a retired Gate vocabulary and a review/commit cadence stricter than the current delivery goal. D-074 corrects that execution overhead without weakening authority, safety, negative-path or human-product acceptance requirements.
