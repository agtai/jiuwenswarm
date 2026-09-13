# Live Voice code duplication and retirement audit — 2026-08-17

> **Frozen read-only audit.** This record describes source at
> `ca9a9d9a3be5f76c4feee980030a1b3ce065b9ab`, relative to the
> `origin/develop` merge base
> `3f3cdbb7f45fdd29e7d03deafa5bca10e363434e`. It does not replace current
> [STATUS](../STATUS.md), authorize a deletion, or change an accepted contract.
> Audit state: **ANALYSIS COMPLETE / CLEANUP NOT STARTED**.

## 1. Question and scope

This audit answers four related cleanup questions:

1. Which Live Voice implementations are literally or structurally duplicated?
2. Which repetition is intentional boundary validation and must remain?
3. Which branch additions are development intermediates or compatibility paths
   that should not survive the final integration unchanged?
4. At what product boundary can each candidate be consolidated or removed?

The inspection covered the Live Voice backend, Gateway/media registration,
Web frontend formal and legacy paths, adjacent Task/Executor integration,
Live Voice tests/scripts and branch-owned documents. It used exact-file and
normalized function comparisons, import/call-site searches, feature-flag and
test-ownership searches, and a branch-delta review. This was a static,
read-only audit: no product behaviour was changed and no runtime acceptance was
claimed.

No duplicated production file was byte-for-byte identical to another complete
production file. The meaningful findings are repeated helpers, repeated
authority-handler structure, and parallel legacy/formal implementations.

## 2. Consolidate without changing product behaviour

These are small, high-confidence consolidation candidates. They should be
handled in a focused cleanup package with existing negative/error-contract tests
kept intact.

| Repeated logic | Current locations | Recommendation | Earliest safe time |
|---|---|---|---|
| Strict record validation: `recordDescriptors`, `strictRecord`, timestamp parsing | `formal/liveVoiceContractV2.ts`, `formal/liveVoiceRouteTelemetry.ts`, `formal/liveVoiceObservability.ts` | Create one internal formal-contract validation utility; preserve each caller's exact field/error wording where it is part of the contract | Now, or with the next formal Web cleanup |
| Exact-object validation | `formal/productP2ActivationJournal.ts`, `formal/productP3ProgressGenerationJournal.ts`; a related variant exists in `formal/productP1VoiceRoute.ts` | Share the identical P2/P3 helper; keep the P1 variant separate until its error contract is compared | Now |
| P2 activation binding equality | `formal/productP2ActivationJournal.ts` and `formal/productWebActivation.ts` | Move equality to the binding model/utility used by both owners | Now |
| Visible-task cloning | `liveVoiceTaskBridge.ts` and `liveVoiceTaskMonitor.ts` | Use one immutable snapshot helper or make the bridge expose the already-cloned view | With the legacy Task-path retirement decision |
| Closed/response generation-index traversal | `_p2_response_generation_indices` and `_closed_p2_generation_indices` in `product_composition_registry.py` | Extract one narrow traversal helper while keeping different state predicates explicit | During the current registry defect-repair batch |

The “Now” entries above mean technically safe, not current priority. D-083
schedules them for the later code-organization batch; only the generation-index
traversal should be combined during the product-truth defect batch, and only if
that owner is already being changed.

This audit intentionally does **not** recommend a broad generic “handler
framework.” Registry confirmation/mutation, P2 close/P3 progress close, and
presentation-ACK/barge-in handlers have similar envelopes, but they bind
different authority, idempotency, side-effect and error semantics. A premature
abstraction would hide security differences and make negative-path review
harder.

## 3. Structural duplication and retirement gates

### 3.1 Legacy and formal Web voice paths

`ChatPanel/index.tsx` constructs `useLiveVoiceDemo(...)` even when the formal
product path is selected later. It then switches between formal and legacy bar
props, while `LiveVoiceIntegratedRoutePanel` separately mounts the formal
surface. The legacy cluster (`useLiveVoiceDemo`, `liveVoiceCore`,
`liveVoiceStreamingSpeech`, `liveVoiceTaskClient`, `liveVoiceTaskAdapter`,
`liveVoiceTaskBridge` and `liveVoiceTaskMonitor`) therefore overlaps the formal
Speech/product-composition/Task surface.

Do not remove this cluster during the current defect state. First make the
formal product route the default tested route, complete one clean immutable
microphone/TTS journey, verify flag-off behaviour, and identify any remaining
compatibility consumer. Then stop constructing the legacy hook on the formal
path and remove each legacy feature flag/module together with its owned tests.

### 3.2 Parallel Task models

`task_core.py` and the formal persistent Task model/store retain overlapping
Task state and lifecycle concepts. `voice_task_bridge.py` still consumes the old
types. Removing the older core before migrating that bridge would break the
compatibility surface; retaining both through generalization would make the
single-/multi-task authority ambiguous.

The safe gate is: migrate the bridge and product callers to the formal Task
contract, close restart/result/cancel regressions, then retire the old model and
rewrite tests around one canonical Task state machine. This should happen before
multi-task/generalization work, not be deferred until after it.

### 3.3 Direct and compatibility executors

The current authenticated P3 product composition constructs
`DirectProjectCodeExecutorAdapter`. `ProjectCodeExecutorAdapter` remains a
covered compatibility/test path. It is not safe to delete merely because the
current product root does not construct it.

Retire the compatibility adapter only after the Direct executor passes a clean
terminalization, restart/recovery, retry-readiness and cancel journey, and an
import/caller audit proves that no supported non-Live-Voice flow depends on the
old adapter. The Direct executor itself is current product code, not a cleanup
candidate.

### 3.4 Operation-name duplication with contract drift

Allowed-operation sets appear in `p3_authenticated_composition.py`,
`product_p3_text_adapter.py` and `product_composition_registry.py`. They are not
identical today: for example, result/retry capability differs by surface. Do not
deduplicate them into an unqualified global set. Before generalization, define a
canonical capability catalog and derive surface-specific allowlists from it so
that intentional differences are named and tested.

## 4. Repetition that must remain for now

- The backend canonical v2 protocol and frontend validation replica enforce a
  cross-language trust boundary. Keep both under D-043 until the protocol is
  frozen and a generated schema/validator can replace manual parity safely.
- DTO, confirmation, persistence and execution-authority checks may validate
  the same field more than once. Those are independent trust boundaries, not
  ordinary duplicate code.
- Authority handlers with different target binding, idempotency keys, forbidden
  side effects or failure codes stay explicit even when their control flow looks
  similar.
- Test oracles may repeat literal contract values when the repetition proves
  independent compatibility; they should not import the value under test just
  to reduce text duplication.

## 5. Retirement analysis routing

Branch content removal, re-homing, hardcode retirement and final-integration
cleanup are large enough to own a separate frozen record. Use the
[branch content retirement audit](BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md)
for the candidate inventory, exact removal gates, retained content and execution
order. This duplication audit owns only repeated implementation analysis and
the consolidation/retirement gates in sections 2–4.

| Work item | State in this snapshot |
|---|---|
| Duplicate-code analysis and durable record | **DONE** |
| Small helper consolidation | **NOT STARTED** |
| Structural duplicate-path convergence | **PENDING REPLACEMENT AND CLEAN ACCEPTANCE** |
