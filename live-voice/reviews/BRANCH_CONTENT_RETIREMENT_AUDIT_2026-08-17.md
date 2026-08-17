# Live Voice branch content retirement audit — 2026-08-17

> **Frozen read-only audit.** This record describes branch content at
> `ca9a9d9a3be5f76c4feee980030a1b3ce065b9ab`, relative to the
> `origin/develop` merge base
> `3f3cdbb7f45fdd29e7d03deafa5bca10e363434e`. Current state and priority
> remain in [STATUS](../STATUS.md). Candidate classification is not deletion
> authorization. Audit state: **ANALYSIS COMPLETE / DOCUMENT BATCH A COMPLETE /
> CODE REMOVAL NOT STARTED**.

## 1. Purpose and classification

This audit records what on the current Live Voice branch may be removed before
final integration, what must first be moved or replaced, and what must remain.
The companion [duplication audit](CODE_DUPLICATION_AND_RETIREMENT_AUDIT_2026-08-17.md)
owns repeated-code findings; this file owns the branch-retirement inventory and
deletion gates.

Each candidate is assigned one of five dispositions:

| Disposition | Meaning |
|---|---|
| `REMOVE-CANDIDATE` | No current product owner was found; perform one final caller/flag/evidence search in the deletion diff, then remove with affected tests |
| `RE-HOME` | The asset remains useful but is placed in a production or root-document boundary that misstates its ownership |
| `REPLACE-THEN-REMOVE` | A current compatibility/demo path still depends on it; delete only after the named formal replacement and acceptance gate |
| `RETAIN` | Current product authority, trust-boundary validation or immutable evidence still requires it |
| `LOCAL-ONLY` | Generated local output is not branch source; keep it ignored and out of the final commit |

The audit used branch-delta inspection, import/call-site searches, feature-flag
searches, test ownership, current product-root wiring, document routing and
accepted replacement boundaries. It made no source deletion and ran no product
acceptance.

## 2. High-confidence removal candidates

These can form a Tier 0/1 mechanical cleanup package after a final scoped
ownership search. The deletion batch must preserve any unique regression before
removing its old entrypoint.

| Candidate | Disposition | Evidence/reason | Required check before removal |
|---|---|---|---|
| W2 dotenv preservation flags and their isolated tests in `jiuwenswarm/dotenv_early.py` | `REMOVE-CANDIDATE` | They belong to the retired W2 environment split and no current product launcher owns the flags | Search source, tests, docs and launchers for both flag names; prove default/current dotenv loading is unchanged |
| Legacy ticket-in-path dedicated-media routing in `dedicated_media_registration.py` and `web_connect.py` | `REMOVE-CANDIDATE` | Current product routing does not select it; ownership is explicit compatibility construction/tests | Prove header/query/current media-ticket routing and negative cross-session/expired-ticket cases still pass |
| `scripts/live_voice_snapshot.ps1` | `REMOVE-CANDIDATE` | It reads retired Resume-capsule/“Verified code base” concepts and conflicts with D-082 plus current STATUS orientation | Ensure README/REFERENCE_INDEX/runbook no longer instruct use; retain plain Git bootstrap commands |
| `scripts/live_voice/s7_alpha_verification.py` and `s7_*` probe helpers | `REMOVE-CANDIDATE` after regression transplant | They encode an obsolete numbered-stage acceptance harness rather than current capability ownership | Map every still-relevant scenario to module tests or current acceptance before deleting scripts and `test_s7_*` |
| `scripts/live_voice/s8_readiness.py` plus `test_s8_readiness.py` and `test_s8_readiness_cli.py` | `REMOVE-CANDIDATE` after regression transplant | They encode a retired stage/readiness entrypoint | Preserve current isolation/source-ref and defect regressions in capability-owned tests |

The S7/S8 removal is an entrypoint/topology cleanup, not permission to discard
unique safety assertions. Any still-applicable privacy, secure-deployment,
benchmark, failure-injection, source-isolation or real-Agent scenario must move
before the stage-named owner disappears.

## 3. Move out of the production tree or integrate deliberately

These modules appear production-owned by location, but the audited product-root
search found test/harness ownership or an incomplete integration boundary. Each
needs an explicit `integrate`, `move to tests/support`, or `delete` decision.

### 3.1 Backend foundation cluster

| File under `jiuwenswarm/server/live_voice/` | Current classification | Proposed disposition |
|---|---|---|
| `alpha_benchmark.py` | Benchmark/fault test support | Move reusable benchmark helpers to test/tool support; otherwise delete with obsolete stage probes |
| `alpha_privacy_conformance.py` | Conformance oracle | Move to validation/test support; keep production only if a real runtime policy caller is introduced |
| `observability_exporter.py` | Export foundation without current product-root ownership | Integrate into the real observability sink or re-home/delete |
| `observability_fault_harness.py` | Fault-injection support | Move under tests/support; never present it as normal runtime capability |
| `product_observability_adapter.py` | Product adapter foundation with test ownership | Integrate at the product root or remove the unused production surface |
| `product_p2_readiness.py` | Readiness verification support | Move with current acceptance tooling or delete after stage-harness retirement |
| `realtime_media.py` | Foundation/simulation boundary distinct from the current dedicated-media root | Confirm whether any supported runtime consumes it; otherwise move useful fakes to test support and delete production exposure |

Disposition: **`RE-HOME` or `REMOVE-CANDIDATE`, not automatic deletion**. The
cluster includes useful oracles; directory placement is the immediate defect.

### 3.2 Frontend formal test/conformance cluster

| File under `src/features/live-voice/formal/` | Proposed disposition |
|---|---|
| `conversationRuntimeReplica.ts` | Move to test/support if it is only a runtime replica |
| `fakeP1Vertical.ts` | Move to test/support or delete with obsolete fake integration |
| `formalTaskResultRoute.ts` | Integrate into the real formal route if still required; otherwise remove with its isolated tests |
| `liveVoiceContractV2.ts` | `RETAIN` until the cross-language v2 validator is replaced by an accepted generated contract |
| `liveVoiceObservability.ts` | Keep only the product-consumed subset; move recorder/fake-only support to tests |
| `productCompositionContract.ts` | Retain if it is the Web trust-boundary validator; otherwise generate/re-home with contract tests |
| `webLifecycleObservationRecorder.ts` | Move test-only observation recording out of production source unless the real product exports it |

Disposition: **mixed `RE-HOME` / `RETAIN`**. Do not bulk-delete this directory.
The protocol and product-composition validators enforce trust boundaries even
when their current caller graph resembles test ownership.

## 4. Replace before removal

These items are not suitable for final integration unchanged, but deleting them
now would remove the only current Demo or compatibility journey.

| Candidate | Why it remains today | Exact retirement gate |
|---|---|---|
| Legacy `useLiveVoiceDemo`/`liveVoiceCore`/streaming-speech/Task client-adapter-bridge-monitor lane | `ChatPanel` still constructs the legacy hook and selects it when the formal flags are off | Make the formal product route the default tested path, stop constructing the legacy hook on that path, pass flag-off regressions and one clean immutable microphone/TTS Journey, then remove callers, flags, modules and owned tests |
| Old `task_core.py` model beside persistent/formal Task models | `voice_task_bridge.py` and compatibility tests still consume old Task types | Migrate bridge/product callers to one formal Task state machine; pass create/status/result/cancel/restart cases; remove before multi-task generalization |
| `ProjectCodeExecutorAdapter` | Covered compatibility/test path; current P3 uses `DirectProjectCodeExecutorAdapter` | Audit non-Live-Voice callers, then require Direct executor terminalization, retry-readiness, recovery and cancellation acceptance before deletion |
| `.env.production` default-on partial Live Voice Demo flags | Currently makes the Demo easy to start, but makes “production” configuration overclaim readiness | Introduce an explicit Demo build/profile and leave ordinary production/default configuration honest |
| `scripts/live_voice/start_hands_free_demo.ps1` branch, itinerary, model, port and bypass assumptions | It is the current bounded physical Demo launcher | Retain through the next clean physical acceptance; parameterize durable inputs and move it to explicit demo/test support or delete it |
| Three-day-itinerary prompt/file fixture, adjustment checkpoint and trusted Demo bypass | They enable the exact bounded Demo but are not generalized confirmation/policy | Replace with general task input, confirmation and policy; remove before claiming generalized production support |
| `scripts/live_voice/w2_rehearsal/` fixture/barrier/diagnostics | Some current defect reproduction may still depend on transplanted W2 assets | Move the live defect regression and any needed WAV asset to capability-owned tests, then delete obsolete rehearsal ownership |

Finishing a P3 implementation package does not automatically retire all of
these. A candidate closes only when the replacement named above is implemented
and accepted; otherwise it remains visible as partial product debt.

## 5. Document intermediates and historical records

The documentation inventory is large enough to own a separate manifest. Use the
[documentation retirement audit](DOCUMENT_RETIREMENT_AUDIT_2026-08-17.md) for
the measured inventory, three deletion batches, 20-file interim working set,
content-level trimming and link/authority acceptance. Batch A is complete (19
files); Batches B/C have not started.

## 6. Content that must remain

- Current product-root implementations: dedicated media, formal Speech,
  product composition, persistent Task, Direct executor and their active
  adapters.
- Independent validation at DTO, confirmation, persistence, scope/authority and
  execution boundaries, even where fields are checked repeatedly.
- Backend/frontend v2 contract parity until an accepted generated replacement
  exists.
- Negative-path assertions proving zero Agent/Tool/Task/audio/history mutation.
- Current D118/D119 candidate context and the 2026-08-17 defect-discovery
  evidence until the repaired candidate receives clean acceptance.
- Accepted decision history, current status/routing, applicable acceptance and
  immutable product evidence.

“Not constructed by the current Demo root” is not by itself sufficient proof
for deletion. Compatibility, library/API and non-Live-Voice callers must be
checked at the repository boundary.

## 7. Local artifacts excluded from the final commit

Coverage output, Python/pytest caches, frontend `dist`, `node_modules`, logs and
runtime databases/audio are `LOCAL-ONLY`. They should remain ignored and must
not be added to the final commit. If cleanup is later requested, resolve and
verify their exact workspace-local paths before deleting them; this audit does
not authorize deletion of user data or runtime evidence.

## 8. Execution packages and acceptance

1. **Mechanical retirement:** W2 flags/path, stale snapshot, obsolete stage
   entrypoints and document routing. Preserve unique tests/evidence first.
2. **Ownership cleanup:** re-home test/conformance modules and redesign tests
   around capability/module contracts.
3. **Post-repair compatibility retirement:** remove the legacy Web/Task/Executor
   lane only after the formal clean candidate and caller audit.
4. **Pre-generalization convergence:** one Task model, one named capability
   catalog and no exact-Demo fixture in claimed production composition.
5. **Final merge audit:** repeat caller/flag/link/ignored-artifact searches on
   the final diff and confirm every retained compatibility path has a named
   owner and retirement reason.

Each removal package requires affected positive, negative and flag-off tests,
frontend/backend build or suites as applicable, forbidden-side-effect checks for
mutation/authority paths, a cold review, and D-074 Tier 2/3 independent review
where the boundary requires it.

## 9. Tracking state at audit time

| Work item | State in this snapshot |
|---|---|
| Branch-content removal analysis and durable record | **DONE** |
| Document Batch A removal | **DONE — 19 files; Git-recoverable** |
| Actual source/script implementation removal | **NOT STARTED** |
| Test/conformance file re-homing | **NOT STARTED** |
| Legacy/formal compatibility convergence | **PENDING REPLACEMENT AND CLEAN ACCEPTANCE** |
| Demo hardcode/fixture retirement | **PENDING GENERALIZATION / EXPLICIT DEMO PROFILE** |
| Final integration cleanup audit | **PENDING FINAL CANDIDATE** |
