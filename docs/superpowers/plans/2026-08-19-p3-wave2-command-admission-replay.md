# P3 Wave 2 Command, Admission, and Replay Implementation Plan

> **Required sub-skill:** Use `superpowers:subagent-driven-development` to execute this plan, `superpowers:test-driven-development` for every behavior change, and `superpowers:verification-before-completion` before any completion claim.

**Goal:** Complete the bounded P3-2, P3-3, and P3-5A backend batch on `hx/0812_live_voice_w3`: closed command/successor semantics, capability-driven Direct Executor admission, and durable event/result unread consumption, with one locally integrated Tier-3 candidate and no remote-ref update.

**Architecture:** Keep the accepted P3-1 Task/Attempt/Event/outbox model as the sole lifecycle authority. A Core/Store lane owns the common v2 wire, formal records, schema-v4 P3-2 transactions, the single schema-v5 migration, admission queue facts, and P3-5A consumption. An Executor lane owns an immutable capability profile/selector plus Direct Adapter declarations and observations. Main integrates those lanes, binds the selected profile to the Core before Store creation, and alone resolves shared semantics and history.

**Tech stack:** Python 3.11, frozen dataclasses, asyncio, SQLite/WAL, pytest/pytest-asyncio, Ruff; TypeScript contract replica tested with Node's test runner; JiuwenSwarm Direct project-code Executor, real Agent and Tool in a disposable no-remote Git project for the final bounded physical proof.

**Specifications:** `live-voice/decisions/DECISIONS.md` D-087/D-088; `live-voice/reviews/P3_2_P3_5A_ACTIVATION_PREPARATION_2026-08-18.md`; `live-voice/reviews/P3_3_CAPABILITY_ADMISSION_ACTIVATION_PREPARATION_2026-08-18.md`; `live-voice/roadmap/FULL_P3_EXECUTION_PLAN.md` P3-2/P3-3/P3-5; root `TESTING.md` Tier-3 D-032/D-046/D-074.

## Global Constraints

- Start all implementation worktrees from the committed D-088 activation parent. Main is the sole integration-branch writer; workers never push or update `hx/0812_live_voice_w3`.
- Preserve `FormalTaskState={accepted,running,blocked,decision_required,terminal}` and `FormalAttemptState={accepted,running,terminal}`. `queued` is a read projection; do not add canonical `queued` or `paused` states.
- P3-2 runs and is proven on schema v4 before any v5 code is composed. It may not add DDL. Schema v5 is one Core/Store migration containing only frozen P3-3 selection/admission facts and P3-5A consumption facts; it must not pre-create P3-4 checkpoint/effect tables.
- Every mutating command requires authenticated exact scope/target authorization, one exact required capability, immutable fingerprinting, and closed payload parsing before Store authority. Raw instruction/input/reason values never enter logs, metrics, traces, review reports, or evidence.
- Command results carry `extensions["live_voice.command"]={disposition,admission_event_id,settlement_event_id}`. Dispositions are exactly `accepted|applied|rejected|unsupported|conflict|timeout|unknown`; pure queries carry no command disposition.
- `accepted` and `applied` use `ok=true`. Negative dispositions use `ok=false` with the existing matching error families. Exact replay precedes current-state checks; a changed fingerprint under the same command ID is `conflict`.
- `task.update` is positive only for accepted Task + accepted Attempt + never-claimed dispatch. Current `task.adjust` remains the only positive running checkpoint operation. `provide_input`, pause, resume, generic running update, and running reprioritize remain truthful unsupported/conflict without a real primitive.
- Accepted/queued `task.reprioritize` becomes positive only through the persisted P3-3 admission queue; it must change real queue ordering. Once dispatch has been claimed, or the Task is running/blocked/decision-required/terminal, it is `conflict`.
- Static capability mismatch returns `unsupported` before Task/Attempt/Event/outbox writes and before Adapter/project effects. After Adapter acceptance or an unknown external outcome, never fall back to another Adapter.
- Store claim token, Direct journal lease/generation/runtime deadline, and OS ownership lock are three distinct fences. No one fence proves another. Unknown ownership/outcome yields durable `reconciliation_required`, no fake terminal state, no replacement Attempt, and no automatic D2 retry.
- Admission default is an absolute 60-minute deadline. Capacity/project-busy retains the same accepted Attempt, increments a persisted attempt count, records closed reason and next-eligible time, and uses bounded deterministic backoff without moving the deadline. Deadline/budget exhaustion settles Task/Attempt failed with reason `EXECUTOR_ADMISSION_TIMEOUT`, no TaskResult and no Executor call at/after expiry.
- Admission priority is exactly `low|normal|high|urgent`; claim order is urgent, high, normal, low, then stable creation order within a priority.
- Stable P3-5A consumer identity is derived server-side from authenticated `(subject_id, project_id)` and ignores `session_id`. Presentation class is exactly `text|voice`, with independent watermarks. Wrong subject/project remains unauthorized and has zero effect.
- `task.events`, `task.result`, `task.unread_events`, and display are pure reads. Only `task.ack_events` advances a watermark. ACK never mutates or deletes Task, Attempt, Event, Result, outbox, Executor, presentation, or the other class.
- Events and legal immutable results are retained for the Task lifetime in this batch. Production retention/compaction/SLO, P3-4 D1/D2, P3-5B presentation composition, P3-6 targeting, P3-7 UI, P1/P2 deferred repair, Production, `develop`, and remote refs are excluded.
- Every red/green cycle must record the failing assertion and the passing focused command. Every rejected/unsupported/conflict/timeout/unknown/stale/duplicate/wrong-scope/failpoint path asserts zero forbidden Agent, Tool, other Task/Attempt, Executor/project/file, audio/history, presentation, and other-consumer-class effects.

## Parallel Ownership

| Lane | Exclusive implementation surfaces | Must not edit |
|---|---|---|
| Core/Store | `jiuwenswarm/common/schema/live_voice_contract_v2.py`; TypeScript replica; `formal_task_models.py`; `persistent_task_core.py`; `task_store.py`; matching contract/Core/Store tests | `project_code_executor.py`; Direct journal/lock internals; product composition until Main integration |
| Executor | new `jiuwenswarm/server/live_voice/executor_capabilities.py`; `project_code_executor.py`; executor unit/integration tests | common contract; formal records; Core; Store; SQLite schema; TypeScript; integration branch |
| Main integration | `p3_authenticated_composition.py`, exports, shared seam tests, evidence/status, conflict resolution, all Git integration | No remote update before the user's exact final authorization |

## Task 1: Close the Python and TypeScript command/query contract

**Files:**

- Modify: `jiuwenswarm/common/schema/live_voice_contract_v2.py`
- Modify: `tests/unit_tests/common/test_live_voice_contract_v2.py`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceContractV2.test.mjs`

**Step 1: Add failing cross-language contract tests.**

Cover all seven new commands and the unread query:

```text
task.update
task.provide_input
task.pause
task.resume
task.reprioritize
task.create_successor
task.ack_events
task.unread_events
```

Assert exact keys, target kind, singleton required capability, stable fingerprint, unknown-key rejection, UTF-8/NUL/boundary cases, priority/class enums, JSON-safe unsigned integers, lowercase 64-hex result digest, and the exact `live_voice.command` result extension. Assert a query result rejects a command disposition.

Run and observe RED:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/common/test_live_voice_contract_v2.py -q
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-contract-v2
```

**Step 2: Implement the closed Python parser.**

Add the command/query target names and exact payload validators:

```text
task.update = {attempt_id, expected_event_head, instruction, constraints}
task.provide_input = {attempt_id, expected_event_head, responds_to_event_id, text}
task.pause = {attempt_id, expected_event_head, reason}
task.resume = {attempt_id, expected_event_head, reason}
task.reprioritize = {attempt_id, expected_event_head, priority, reason}
task.create_successor = {
  expected_predecessor_revision_number,
  expected_predecessor_event_head,
  predecessor_terminal_event_id,
  predecessor_outcome,
  predecessor_result_sha256,
  name,
  instruction,
  constraints,
  executor_id,
  side_effect_class,
  attributes
}
task.ack_events = {
  presentation_class,
  acked_through_seq,
  acked_event_id,
  expected_event_head
}
task.unread_events = {presentation_class, limit}
```

For update, `instruction` and `constraints` are nullable but not both null; an empty constraints array clears them. Instruction/input text is at most 4096 UTF-8 bytes; optional reason at most 1024; constraints are at most 16 unique non-empty strings, each at most 1024 bytes and at most 4096 bytes combined. `limit` is 1..500.

Add a closed command-result extension normalizer used by `ResultEnvelope.from_dict`, `success`, and `failure`; preserve existing result serialization for queries and legacy results without silently attaching a disposition.

**Step 3: Mirror the parser exactly in TypeScript.**

Implement the same operations, payload bounds, disposition validation, result extension, and canonical fingerprint behavior. Do not add a frontend business-state owner.

**Step 4: Run GREEN and parity checks.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/common/test_live_voice_contract_v2.py -q
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-contract-v2
.\.venv\Scripts\python.exe -m ruff check jiuwenswarm/common/schema/live_voice_contract_v2.py tests/unit_tests/common/test_live_voice_contract_v2.py
```

**Step 5: Commit the coherent contract tranche on the Core/Store task branch.**

```powershell
git add jiuwenswarm/common/schema/live_voice_contract_v2.py tests/unit_tests/common/test_live_voice_contract_v2.py jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts jiuwenswarm/channels/web/frontend/tests/liveVoiceContractV2.test.mjs
git commit -m "feat(live-voice): close P3 wave 2 contract"
```

## Task 2: Implement schema-v4 P3-2 commands and successor transactions

**Files:**

- Modify: `jiuwenswarm/server/live_voice/formal_task_models.py`
- Modify: `jiuwenswarm/server/live_voice/persistent_task_core.py`
- Modify: `jiuwenswarm/server/live_voice/task_store.py`
- Modify: `tests/unit_tests/live_voice/test_persistent_task_core.py`
- Modify where exact authorization cases already live: `tests/unit_tests/live_voice/test_formal_task_policy.py`

**Step 1: Add RED formal-model and disposition tests.**

Add canonical `constraints: tuple[str,...]=()` to `FormalTaskSpec`, reading absent legacy JSON as empty. Add result-extension helpers that never leak command payload. Verify schema remains exactly v4 and old v1/v3/v4 databases reopen.

**Step 2: Add RED transaction tests for pre-dispatch update.**

Test one transaction changes the Task spec and matching pending dispatch payload, appends immutable `task.update_requested` and `task.update_applied`, stores final `applied`, and leaves Task/Attempt accepted. Test replay, changed fingerprint, stale attempt/head, claimed/delivered dispatch, running/blocked/decision-required/terminal races, failpoints, reopen, and two Store connections. Every losing path leaves spec/events/outbox/Executor calls unchanged.

Implement:

```python
SqliteTaskStore.update(command: CommandEnvelope, *, observed_at: str) -> ResultEnvelope
```

No DDL is permitted.

**Step 3: Add RED unsupported/state-decider tests.**

Implement a single Store-owned decision path for `provide_input`, pause, resume, and reprioritize before P3-3 composition. It may persist only sanitized command fingerprint/result after canonical authorization. Nonterminal unsupported and terminal/state conflict paths must add no Task/Attempt/Event/outbox changes and call no Executor. `provide_input` must additionally require the exact current `task.decision_required` event; absence of a real input primitive remains `unsupported`.

**Step 4: Narrow compatibility operations.**

Keep `task.adjust` positive only for running exact Attempt and current event head via its existing payload compatibility. Narrow new `task.retry` admission to cancelled predecessor only while preserving replay/reopen of already-applied historical completed retry ledgers. Correct cancel result semantics so durable request is `accepted`; only authoritative cancelled settlement is `applied`; terminal race is exact replay or `conflict`, never a false applied terminal.

**Step 5: Add RED successor matrix and failpoints.**

Test eligible completed/failed/cancelled/interrupted predecessor, ineligible unknown/nonterminal, completed result digest, no-result outcomes, exact replay, changed fingerprint, one concurrent winner, corrupt lineage, old Attempt callbacks, restart, and rollback after command/new Task/new Attempt/event/outbox boundaries. Snapshot predecessor Task/Attempts/Events/Result bytes before the call and assert unchanged after every path.

Implement:

```python
SqliteTaskStore.create_successor(
    command: CommandEnvelope,
    spec: FormalTaskSpec,
    *,
    observed_at: str,
) -> ResultEnvelope
```

Use the existing unique predecessor constraint. Create a new `task_id`, attempt #1, `task.accepted`, dispatch outbox, and command replay atomically with `revision_number=predecessor+1`; never mutate predecessor rows.

**Step 6: Route commands through `PersistentTaskCore.execute`.**

Authorize exact operations first, require server-resolved context for successor, preserve predecessor project identity and current authorization, and return disposition-bearing Store decisions. Do not add Executor methods for unsupported controls.

**Step 7: Run GREEN, affected schema, and zero-effect checks.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_formal_task_policy.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/common/test_live_voice_contract_v2.py -q
.\.venv\Scripts\python.exe -m ruff check jiuwenswarm/server/live_voice/formal_task_models.py jiuwenswarm/server/live_voice/persistent_task_core.py jiuwenswarm/server/live_voice/task_store.py tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_formal_task_policy.py
```

**Step 8: Commit the schema-v4 command tranche.**

```powershell
git add jiuwenswarm/server/live_voice/formal_task_models.py jiuwenswarm/server/live_voice/persistent_task_core.py jiuwenswarm/server/live_voice/task_store.py tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_formal_task_policy.py
git commit -m "feat(live-voice): implement P3-2 task controls"
```

## Task 3: Build the immutable capability profile, selector, and Direct declaration

**Files:**

- Create: `jiuwenswarm/server/live_voice/executor_capabilities.py`
- Create: `tests/unit_tests/live_voice/test_executor_capabilities.py`
- Modify: `jiuwenswarm/server/live_voice/project_code_executor.py`
- Modify: `tests/unit_tests/live_voice/test_project_code_executor.py`
- Modify: `tests/integration/live_voice/test_formal_task_executor_adapter.py`

This task runs in parallel with Tasks 1, 2, 4, and 5 and may touch only Executor-lane files.

**Step 1: Add RED immutable profile/requirements/selector tests.**

Define frozen, strict, canonical-hashable version-1 values:

```python
ExecutorCapabilityProfile(
    schema_version="live-voice.executor-capability-profile.v1",
    profile_id: str,
    executor_id: str,
    adapter_id: str,
    adapter_protocol_version: str,
    operation_versions: tuple[tuple[str, str], ...],
    durability_level="D0",
    durability_version: str,
    project_serialization="exclusive",
    max_live_attempts: int,
    enforcement_facts: tuple[str, ...],
)

TaskExecutionRequirements(
    schema_version="live-voice.task-execution-requirements.v1",
    executor_id: str,
    operation_versions: tuple[tuple[str, str], ...],
    durability_level="D0",
    side_effect_class: str,
    project_serialization="exclusive",
)

ExecutorSelection(profile, profile_digest, requirements)
```

Canonicalize sorted unique operation/enforcement facts, reject unknown fields/versions/duplicates/invalid bounds, and compute lowercase SHA-256 over canonical JSON. The selector filters exact compatibility before ranking by `(profile_id, adapter_id)` and returns a stable unsupported violation if none match.

**Step 2: Declare the real Direct profile.**

`DirectProjectCodeExecutorAdapter.capability_profile()` must truthfully declare:

```text
dispatch.v1
status.v1
cancel.v1
adjust.demo-itinerary-checkpoint.v1
reconcile.d0.v1
```

It must not declare provide-input, pause, resume, generic update, running priority, D1 checkpoint, or D2 effect recovery. Include max live capacity 32, exclusive same-project serialization, Direct journal/lease/runtime-deadline and OS-lock enforcement facts, and a stable Adapter protocol/build identity that does not include secrets or host paths.

**Step 3: Prove selection and Direct boundaries.**

Add leaf tests for stable digest, exact supported selection, pure static mismatch with zero selector effect, status/cancel/adjust version truth, same-project serialization, two distinct-project concurrent workers, capacity exhaustion reason, late generation/lock fences, and explicit unsupported declarations. This Executor-only tranche has no product lifecycle caller: the real pre-Store/Adapter/project mismatch ordering and no-fallback-after-accepted/unknown proofs are blocking Task 6 integration-seam acceptance, not claims of this leaf commit. Fakes may cover negative/race cases only.

**Step 4: Run GREEN and affected Executor tests.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_executor_capabilities.py tests/unit_tests/live_voice/test_project_code_executor.py tests/integration/live_voice/test_formal_task_executor_adapter.py -q
.\.venv\Scripts\python.exe -m ruff check jiuwenswarm/server/live_voice/executor_capabilities.py jiuwenswarm/server/live_voice/project_code_executor.py tests/unit_tests/live_voice/test_executor_capabilities.py tests/unit_tests/live_voice/test_project_code_executor.py tests/integration/live_voice/test_formal_task_executor_adapter.py
```

**Step 5: Commit the Executor leaf tranche.**

```powershell
git add jiuwenswarm/server/live_voice/executor_capabilities.py jiuwenswarm/server/live_voice/project_code_executor.py tests/unit_tests/live_voice/test_executor_capabilities.py tests/unit_tests/live_voice/test_project_code_executor.py tests/integration/live_voice/test_formal_task_executor_adapter.py
git commit -m "feat(live-voice): declare P3-3 executor capabilities"
```

## Task 4: Add the single v5 selection and admission migration

**Files:**

- Modify: `jiuwenswarm/server/live_voice/formal_task_models.py`
- Modify: `jiuwenswarm/server/live_voice/task_store.py`
- Modify: `jiuwenswarm/server/live_voice/persistent_task_core.py`
- Modify: `tests/unit_tests/live_voice/test_persistent_task_core.py`
- Create: `tests/unit_tests/live_voice/test_task_admission.py`

**Step 1: Add RED v4→v5 and historical-chain migration tests.**

Schema v5 adds nullable historical selection columns on `attempts` and non-null selection for every new selected Attempt:

```text
adapter_id
capability_profile_json
capability_profile_digest
execution_requirements_json
admission_priority
admission_reason
admission_attempt_count
admission_next_eligible_at
admission_deadline_at
admission_enqueued_at
```

Add the P3-5A table from Task 5 in this same migration, even if its behavioral tests are implemented next. Test direct v4→v5, v1→v4→v5, corrupt/partial migration rollback, reopen, concurrent initializers, and that no P3-4 tables/columns appear. Historical Attempts retain null selection/admission facts and are never relabelled.

**Step 2: Add RED creation/selection tests.**

Add a strict Store carrier such as `PersistedExecutorSelection` in `formal_task_models.py`. Extend `SqliteTaskStore.create` and successor/retry creation to persist the exact canonical profile snapshot/digest and requirements received from Core. Reopen must reconstruct the same bytes. Changed digest/snapshot or late callbacks under another digest fail closed.

**Step 3: Add RED admission queue ordering/backoff/deadline tests.**

Use one `AdmissionPolicy` with defaults `deadline=3600s`, `initial_backoff=1s`, `max_backoff=60s`, and `max_attempts=120`. All four values remain configuration inputs. The absolute deadline is calculated once at accepted creation and never extended. Persist machine reasons only from `EXECUTOR_PROJECT_BUSY|EXECUTOR_CAPACITY_EXHAUSTED`.

Implement Store APIs equivalent to:

```python
SqliteTaskStore.defer_admission(
    item: PersistentOutboxItem,
    *,
    reason: str,
    policy: AdmissionPolicy,
    observed_at: str,
) -> AdmissionDisposition

SqliteTaskStore.reprioritize(
    command: CommandEnvelope,
    *,
    observed_at: str,
) -> ResultEnvelope

SqliteTaskStore.admission_projection(task_id, scope) -> PersistentAdmissionRecord
```

`claim_outbox` selects only eligible pending dispatches, orders priority urgent→low then stable creation order, and atomically expires already-dead admissions before any Executor call. Deferral retains the same Attempt/outbox and clears only the Store claim. Timeout makes Task/Attempt terminal failed with reason `EXECUTOR_ADMISSION_TIMEOUT`, appends one terminal event, suppresses pending outbox, creates no TaskResult, and never claims/calls Executor again.

**Step 4: Integrate Core delivery handling.**

On Direct pre-effect busy/capacity violations, call `defer_admission`; do not use generic immediate `release_outbox`. Other unavailable/timeout/unknown errors retain their current safe handling and must not be reclassified as capacity. Add a read-only queued projection to `task.get/status/list` results without changing canonical lifecycle.

**Step 5: Make queued reprioritize real.**

Only accepted Task + accepted Attempt + pending never-delivered dispatch can update admission priority. The command commits fingerprint/result plus queue priority and requested/applied events atomically; a replay is stable. Running/claimed/blocked/decision-required/terminal/stale Attempt or head is conflict with zero ordering change.

**Step 6: Prove three-fence and orphan projection.**

Persist a bounded `reconciliation_required` reason/manual-action projection when exact Direct ownership or outcome cannot be proved. Tests must keep Store claim, Direct lease/generation/deadline, and OS lock distinct; an expired Store claim or Direct lease alone must never produce terminal/reallocation. Late predecessor/profile-digest facts have zero effect.

**Step 7: Run GREEN and commit.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_task_admission.py -q
.\.venv\Scripts\python.exe -m ruff check jiuwenswarm/server/live_voice/formal_task_models.py jiuwenswarm/server/live_voice/task_store.py jiuwenswarm/server/live_voice/persistent_task_core.py tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_task_admission.py
git add jiuwenswarm/server/live_voice/formal_task_models.py jiuwenswarm/server/live_voice/task_store.py jiuwenswarm/server/live_voice/persistent_task_core.py tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_task_admission.py
git commit -m "feat(live-voice): persist P3-3 executor admission"
```

## Task 5: Implement P3-5A unread and explicit class-isolated ACK

**Files:**

- Modify: `jiuwenswarm/server/live_voice/formal_task_models.py`
- Modify: `jiuwenswarm/server/live_voice/task_store.py`
- Modify: `jiuwenswarm/server/live_voice/persistent_task_core.py`
- Create: `tests/unit_tests/live_voice/test_task_result_event_consumption.py`
- Modify: `tests/unit_tests/live_voice/test_task_event_subscription.py` only if new requested/applied events affect its closed projection

**Step 1: Add RED schema/table integrity tests.**

Use the Task 4 v5 migration to create exactly one consumption table keyed by:

```text
(subject_id, project_id, task_id, presentation_class)
```

Persist `acked_through_seq`, `acked_event_id`, and `updated_at`; validate `presentation_class in ('text','voice')`, exact Task/event foreign binding, and a monotonic nonnegative watermark (initial logical watermark is `-1` with no row). Session ID is never stored in the consumer key.

**Step 2: Add RED pure unread tests.**

Implement:

```python
SqliteTaskStore.unread_events_page(
    task_id: str,
    scope: ScopeRef,
    *,
    presentation_class: str,
    limit: int,
) -> TaskUnreadPage
```

Authorize authenticated subject/project, permit a new session with the same pair, reject a wrong subject/project, and return retained events strictly above that class's watermark against one frozen `head_seq`. Return watermark, events, next cursor metadata, and `has_more`; perform no write. Terminal-result unread is anchored by its terminal event and existing legal result, never by a fabricated second result store.

**Step 3: Add RED ACK replay/monotonicity/concurrency tests.**

Implement:

```python
SqliteTaskStore.ack_events(
    command: CommandEnvelope,
    *,
    observed_at: str,
) -> ResultEnvelope
```

Validate the event at `acked_through_seq` exists, matches `acked_event_id`, is within `expected_event_head`, and belongs to the exact Task. Exact replay returns the original result. Lower/equal ACK is an idempotent `applied` no-op; future/missing/wrong Task/subject/project/class/changed fingerprint fails with zero mutation. Concurrent ACKs from separate Store instances linearize to the greatest valid prefix. Text ACK never changes voice and vice versa.

**Step 4: Route Core query/command.**

Add `task.unread_events` to `PersistentTaskCore.query` as a pure read and `task.ack_events` to `execute` as the only consumption mutation. Return command disposition only on ACK. Do not touch Runtime, Web delivery, generation, TTS, or presentation callbacks.

**Step 5: Prove terminal/result/event atomicity and restart.**

Extend failpoint tests around Executor source fact + Attempt terminal + Task terminal + terminal event + legal completed TaskResult + outbox settlement. Any failure rolls the group back. Crash before ACK remains unread; committed ACK survives reopen; events/results remain present after ACK.

**Step 6: Run GREEN and commit.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_task_result_event_consumption.py tests/unit_tests/live_voice/test_task_event_subscription.py tests/unit_tests/live_voice/test_persistent_task_core.py -q
.\.venv\Scripts\python.exe -m ruff check jiuwenswarm/server/live_voice/formal_task_models.py jiuwenswarm/server/live_voice/task_store.py jiuwenswarm/server/live_voice/persistent_task_core.py tests/unit_tests/live_voice/test_task_result_event_consumption.py tests/unit_tests/live_voice/test_task_event_subscription.py
git add jiuwenswarm/server/live_voice/formal_task_models.py jiuwenswarm/server/live_voice/task_store.py jiuwenswarm/server/live_voice/persistent_task_core.py tests/unit_tests/live_voice/test_task_result_event_consumption.py tests/unit_tests/live_voice/test_task_event_subscription.py
git commit -m "feat(live-voice): persist P3-5A unread acknowledgements"
```

## Task 6: Main integrates capability selection into the product factory

**Files:**

- Modify: `jiuwenswarm/server/live_voice/p3_authenticated_composition.py`
- Modify: `jiuwenswarm/server/live_voice/__init__.py` or the nearest existing export owner only where required
- Modify: `tests/unit_tests/live_voice/test_p3_authenticated_composition.py`
- Modify: `tests/integration/live_voice/test_d90_formal_task_vertical.py`
- Modify shared Executor/Core files only for the minimum typed seam after both reviewed lanes land

**Step 1: Review and integrate the Core/Store lane first.**

Generate a review package per coherent commit, dispatch an independent Tier-3 task reviewer, fix every Critical/Important issue on the task branch, and re-review only the fix diff. Cherry-pick reviewed Core commits into `hx/0812_live_voice_w3` in contract→P3-2→v5 admission→P3-5A order.

**Step 2: Review and integrate the Executor lane.**

Review the full Executor diff against Task 3 and D-088, including truthful unsupported declarations and real Direct boundary. Fix/re-review, then cherry-pick the reviewed Executor commit.

**Step 3: Add RED seam tests.**

The product factory must obtain the Direct profile, construct requirements from the resolved Task spec, select before Store creation, persist exact selection, and reuse that persisted digest for delivery/reconcile. Test static mismatch with zero Store/Adapter/project effects, successful Direct selection, restart with the same digest, changed current profile not rewriting an old Attempt, and no fallback after acceptance/unknown. This step is the sole owner that closes those two lifecycle-level requirements; the Executor leaf must not invent an unowned duplicate caller to simulate them.

**Step 4: Implement the minimum typed seam.**

Adapt Core's persisted carrier to `ExecutorSelection` without duplicating canonical JSON/digest logic. Product composition passes the selected facts and the admission policy (`3600s`, bounded backoff) into `PersistentTaskCore`. Legacy compatibility Adapter may expose its own truthful limited profile but must not be selected for the P3-3 positive path.

**Step 5: Run the combined seam.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_executor_capabilities.py tests/unit_tests/live_voice/test_project_code_executor.py tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_task_admission.py tests/unit_tests/live_voice/test_task_result_event_consumption.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py tests/integration/live_voice/test_formal_task_executor_adapter.py tests/integration/live_voice/test_d90_formal_task_vertical.py -q
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-contract-v2
```

**Step 6: Commit the integration seam.**

```powershell
git add jiuwenswarm/server/live_voice/p3_authenticated_composition.py jiuwenswarm/server/live_voice/__init__.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py tests/integration/live_voice/test_d90_formal_task_vertical.py
git commit -m "feat(live-voice): integrate P3 wave 2 admission"
```

Stage any minimum shared seam files actually changed and report them explicitly.

## Task 7: Execute Tier-3 affected, static, build, and bounded real evidence

**Files:**

- Create: `live-voice/evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md`
- Create: `live-voice/reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md`
- Modify: `live-voice/STATUS.md`
- Modify: `live-voice/decisions/DECISIONS.md` only if implementation facts require a non-product corrective decision

**Step 1: Run affected Python suites.**

At minimum run the complete owned and immediate-consumer suites named by the preparation maps: contract, formal policy, persistent Core/Store, admission, consumption, event subscription, project Executor, authenticated composition, formal Executor integration, and D90 vertical integration. Record exact commands, exit codes, counts/skips, and source SHA.

**Step 2: Run static and frontend verification.**

```powershell
.\.venv\Scripts\python.exe -m ruff check jiuwenswarm/common/schema/live_voice_contract_v2.py jiuwenswarm/server/live_voice/executor_capabilities.py jiuwenswarm/server/live_voice/formal_task_models.py jiuwenswarm/server/live_voice/persistent_task_core.py jiuwenswarm/server/live_voice/task_store.py jiuwenswarm/server/live_voice/project_code_executor.py jiuwenswarm/server/live_voice/p3_authenticated_composition.py tests/unit_tests/common/test_live_voice_contract_v2.py tests/unit_tests/live_voice
.\.venv\Scripts\python.exe -m compileall -q jiuwenswarm/common/schema/live_voice_contract_v2.py jiuwenswarm/server/live_voice
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-contract-v2
npm --prefix jiuwenswarm/channels/web/frontend run build
git diff --check
```

Use the repository's narrower documented Ruff target if the broad test-directory invocation surfaces unrelated pre-existing debt; record exclusions with evidence, never hide a changed-file violation.

**Step 3: Run bounded real Direct/Agent/Tool proof.**

Create a disposable absolute task data directory and a disposable no-remote Git project. Secret-safely copy only the required existing model/provider configuration into that private directory; never print, diff, stage, upload, or include values in evidence. Through the current product factory and selected Direct profile, execute one bounded project mutation requiring a real JiuwenSwarm Agent and real Tool, then prove:

- selected profile id/version/digest and requirements persisted;
- dispatch/start observation, running, real Tool mutation, validation/application, result and terminal facts bind the exact Task/Attempt;
- exact status and cancel semantics remain truthful;
- real checkpoint `task.adjust` is positive only at its existing legal checkpoint;
- two different disposable project roots can run concurrently;
- same project serializes; capacity/busy queues with persisted priority/deadline;
- no secrets appear in logs/evidence and the source repository is untouched by target effects.

If an external Provider/model is unavailable after the bounded retries, keep the automated batch complete, record the exact environment-only blocker and sanitized diagnostics, and do not fabricate physical credit.

**Step 4: Map D-032 evidence.**

For each of P3-2, P3-3, and P3-5A, explicitly map P/N/B/S/T/C/R/I/F/K/X, positive business paths, negative fail-closed paths, and zero forbidden effects. Mark inapplicable dimensions with owner/reason; do not use counts or coverage alone.

**Step 5: Dispatch the final independent complete-diff review.**

Review from the activation commit through candidate HEAD. Require no unresolved Critical/Important issues, no P1/P2 for the owned batch, migration backward compatibility, truthful unsupported operations, no D1/D2 leakage, secret safety, and exact non-claims. Fix, re-run focused/affected checks, and re-review before documentation closure.

**Step 6: Synchronize STATUS and commit evidence.**

Record exact accepted local source, commits, tests, real-path strength, exclusions, review findings, and remaining downstream work. Keep overall P3/product readiness `PARTIAL`; do not claim feature-complete, controlled-candidate PASS, Production, P1/P2 closure, P3-4, P3-5B, P3-6, or P3-7.

```powershell
git add live-voice/STATUS.md live-voice/evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md live-voice/reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md
git commit -m "docs(live-voice): record P3 wave 2 evidence"
```

## Task 8: Produce the clean local candidate and exact push packet

**Step 1: Verification-before-completion.**

Run fresh final status, log, diff-stat, `git diff --check`, the agreed affected suite, static checks, frontend contract/build, and documentation link checks. Confirm the working tree is clean and the checked-out branch remains `hx/0812_live_voice_w3`.

**Step 2: Report the local candidate.**

Return commit hashes/messages, exact activation base and candidate HEAD, test/review/evidence summaries, skipped/inapplicable items, physical evidence strength, downstream exclusions, and `git status --short --branch`.

**Step 3: Wait for the user.**

State the exact prospective operation without performing it:

```text
remote: origin
ref: refs/heads/hx/0812_live_voice_w3
range: <activation-base>..<candidate-head>
mode: normal fast-forward push
history rewritten: no
```

Do not push until the user grants explicit approval for those exact facts.
