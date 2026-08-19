# P3-2 and P3-5A activation preparation — 2026-08-18

> **PRE-ACTIVATION DESIGN AND ORACLE MAP — NO PRODUCT OR COMPLETION CREDIT.**
> Current package status and the active queue remain owned by
> [STATUS](../STATUS.md). The complete package outcomes, dependencies and Gates
> remain in the [complete P3 execution plan](../roadmap/FULL_P3_EXECUTION_PLAN.md).
> This record prepares one future Core/Store activation packet; it implements no
> production code or schema change. It inherits the recorded scoped P3-G0
> foundation acceptance and accepted P3-1 source, but grants no P3-2 or P3-5A
> implementation or completion credit.

## 1. Scope, risk and integrated-baseline identity

This preparation covers the shared Task Control Core/Store boundary for:

- `P3-2`: the complete command/result vocabulary, operation-specific state and
  capability rules, idempotent application and explicit terminal successor;
- `P3-5A`: canonical `TaskResult`, TaskEvent replay cursor, durable unread and
  consumption persistence; and
- the one-owner schema and transaction seams where those tranches collide.

It deliberately excludes production implementation, migration execution,
Executor capability/admission implementation (`P3-3`), Runtime/Web delivery and
presentation ACK invocation (`P3-5B`), natural-language target resolution
(`P3-6`), UI composition (`P3-7`) and product-profile activation/retirement
(`P3-8`). It also excludes Production retention, authentication/tenancy, public
deployment and remote-ref updates.

The preparation is now bound to one integrated lineage:

| Role | Exact identity | Meaning |
|---|---|---|
| Formal P3-G0 product source | `f24dd17d336c8266954f2d7299ca13bd0314d424` (`fix(live-voice): repair product-truth blocker set`) | Exact G0_FINAL product source. Decision D-086 records scoped foundation acceptance while preserving the controlled product-readiness candidate as `FAIL`; no physical candidate PASS is inferred. |
| G0 close and audit rebaseline | `8df7d38227b684177efca8cad83d77278ad42c19`; `5787eda931159ba533e0a81ca8be8b744f449a8b` | The first records the scoped P3-G0 close/queue transition; the second integrates the frozen [coverage/reuse audit](P3_IMPLEMENTATION_COVERAGE_AND_HISTORICAL_REUSE_AUDIT_2026-08-18.md) and [source-asset manifest](P3_HISTORICAL_SOURCE_ASSET_EXTRACTION_MANIFEST_2026-08-18.md) on the G0_FINAL lineage. |
| Accepted P3-1 source and preparation target | `d40e0ee391fdf162faa9d9938eb9b9610020c1a7` (`feat(live-voice): complete canonical multi-task P3-1`) | Clean integrated descendant containing the formal G0 source, rebaselined audit authorities and accepted P3-1 implementation/evidence. It is the code-fact baseline for this preparation. |

The former split documentation/code histories and the transient pre-amend G0
workspace description are historical only. They have been rebaselined into the
single lineage above. Any later implementation must still name its exact clean
descendant and recheck facts affected after `d40e0ee3`; this preparation itself
does not award new runtime or product-readiness evidence.

The eventual implementation remains D-046 **Tier 3**: it changes shared command
protocol, canonical mutation/result authority, SQLite migration, terminal
settlement, replay and consumption state. This document alone is Tier 0 and is
verified only as documentation under root [TESTING](../../TESTING.md).

## 2. Current target files and symbol facts

The following facts were rechecked against accepted P3-1 source `d40e0ee3`;
links name the current owners.

| Owner/surface at `d40e0ee3` | Current fact | Activation consequence |
|---|---|---|
| [`live_voice_contract_v2.py`](../../jiuwenswarm/common/schema/live_voice_contract_v2.py) and TypeScript parity | `CommandEnvelope.fingerprint()` excludes only `request_id`; the closed command set is `task.create`, `task.adjust`, `task.retry` and cancel scopes. Queries include `task.get/list/status/events/result`. `ResultEnvelope` has `ok`, result or error, but no canonical `accepted/applied/rejected/unsupported/conflict/timeout/unknown` disposition. | P3-2 needs one versioned cross-language schema change. It must extend the existing envelope/result owner, not install `full_p3_control_*` beside it. |
| [`formal_task_models.py`](../../jiuwenswarm/server/live_voice/formal_task_models.py) | Canonical Task states are `accepted/running/blocked/decision_required/terminal`; Attempt states are `accepted/running/terminal`. `queued` is a projection and `paused` is absent. `PersistentTaskRecord` now carries `create_command_id`, `predecessor_task_id` and `revision_number`. `TaskResultRecord` binds Task, Attempt, Executor source-event identity, bounded text/artifacts and completion time. | Operation rules must use this state vocabulary unless an accepted checkpoint changes it. Pause/resume cannot be implemented by relabelling `blocked`. Successor creation can extend the stored lineage but does not yet exist. |
| [`persistent_task_core.py`](../../jiuwenswarm/server/live_voice/persistent_task_core.py) | Product commands are `create/cancel/retry/adjust`; queries are addressed and include bounded list/event pagination. `FormalExecutor` exposes `dispatch/cancel/adjust/status/retry_readiness`, not a complete versioned capability catalog. | `update/provide_input/pause/resume/reprioritize` and successor need a frozen protocol and real P3-3 capability seam. Existing `adjust` and Attempt `retry` require explicit compatibility mapping; neither may silently become terminal revision. |
| [`task_store.py`](../../jiuwenswarm/server/live_voice/task_store.py) | `_SCHEMA_VERSION = 4`. The v3→v4 migration adds `create_command_id`, a unique `predecessor_task_id` and bounded `revision_number`; the new-task `create()` path still writes predecessor `NULL`, revision `1`. The Store has command ledger, Task/Attempt/Event/Executor-event/outbox tables, a `current_background_tasks` selection-hint table and `task_results`; it has no unread/consumer/presentation-ACK table. | One future migration must cohost P3-2 and P3-5A additions. Successor admission must atomically allocate a new Task/Attempt and populate the existing lineage. Consumption must be added without turning the selection hint or browser memory into authority. |
| Store event read path | `events_page(task_id, scope, after_seq, limit)` freezes the current per-Task `event_head`, returns a contiguous ordered page plus `head_seq`, `next_after_seq` and `has_more`, rejects a cursor beyond the head and survives reopen. Reads are mutation-free. | Preserve this sequence cursor as the starting point. It is replay position only, not unread/consumption state and not proof of presentation. |
| Store result/terminal path | A known terminal Executor observation, Attempt/Task terminal state/event, completed result row and relevant outbox suppression are committed inside the Store transaction. Non-completed terminal outcomes expose no result. Reads require exactly one result for the current Attempt and revalidate artifact bytes against the project. | Add explicit failpoints and stronger one-result/terminal-event constraints. Keep the canonical result record retrievable even when a separately authorized artifact dereference later fails; project-file reread must not replace or erase stored result truth. |
| P3-1 lineage/compatibility | The unique predecessor constraint permits one direct successor and a linear chain. Existing `task.retry` keeps the same `task_id` and creates a later Attempt only for eligible cancelled/completed attempts. | Successor is a different operation: new `task_id`, new create command, predecessor preserved byte-for-byte. Attempt retry remains recovery compatibility and must not be advertised as revision. |
| Current-selection hint | `current_background_tasks` is retained only for selection; addressed query and mutation revalidate the exact target. | No P3-2 or P3-5A transaction may infer target, unread owner or consumer identity from the hint. |

These facts supersede the pre-G0 audit only for target-code comparison. In
particular, schema v4 and event cursor replay exist at `d40e0ee3`; durable
unread/consumption and the complete command disposition model still do not.

## 3. Candidate P3-2 command/result contract

### 3.1 Result disposition vocabulary

The activation design should freeze one disposition field in the existing
`ResultEnvelope` result/extension schema and one durable replay representation:

| Disposition | Exact meaning | Forbidden inference |
|---|---|---|
| `accepted` | The exact authorized command, immutable fingerprint and any required request event/outbox work are durably admitted. | Does not mean Executor action, state change, terminal outcome or presentation. |
| `applied` | The operation-specific canonical effect has settled and its applied event/result is durable. Pure successful queries may use a separately named read-success value rather than pretending to be mutations. | Does not mean a Task completed unless the authoritative terminal/result contract says so. |
| `rejected` | Validation, authorization or an operation-specific precondition failed before an effect was admitted, or a selected Adapter returned a definitive rejection. | Must have zero forbidden effect; it cannot hide a capability absence or unknown external outcome. |
| `unsupported` | The product contract, selected Executor or real scheduler lacks the required capability. | Must not enqueue work or display success/fallback unless a separately declared fallback actually ran. |
| `conflict` | Command identity/fingerprint reuse, expected-version/state mismatch or a concurrent authoritative fact defeated this command. | Cannot rewrite terminal truth or allocate a replacement Task/Attempt. |
| `timeout` | A bounded wait expired while the authoritative external outcome is still known not to have applied, or the contract explicitly permits safe retry. | Must not be used when an external effect may have happened. |
| `unknown` | Dispatch/application may have happened but current evidence cannot prove the outcome. | Never maps to rejected, not-dispatched, applied, completed or safe automatic retry. |

Exact replay must return the durable original disposition/result before testing
new current preconditions; same `command_id` with changed semantic fingerprint
returns `conflict` with zero mutation. The activation decision must state which
pre-admission failures are recorded for replay without persisting sensitive
payloads; malformed unauthenticated wire input must not create Store authority.

### 3.2 Complete operation × state × capability × result matrix

State abbreviations below are the P3-1 canonical states: `A=accepted`,
`R=running`, `B=blocked`, `D=decision_required`, `T=terminal`. `Q` means the
derived queued view of `A` with no authoritative running Attempt. “Read success”
is mutation-free and is not a command `applied` claim.

The state grid makes every canonical state explicit. `read` is a pure success;
`accept` is a durable request, not application; `checkpoint` and `scheduler`
require real capability evidence; `wait` is a blocking design decision;
`unsupported` is the truthful current result; and `conflict` preserves existing
truth.

| Operation | `A/Q` | `R` | `B` | `D` | `T` |
|---|---|---|---|---|---|
| `create` | Collection operation; new Task becomes `A` | Same | Same | Same | Same |
| `get/list/status/events` | read | read | read | read | read |
| `result` | read `not_ready` | read `not_ready` | read `not_ready` | read `not_ready` | read `available` only for legal completed result, otherwise `unavailable` |
| `update` | pre-dispatch `applied` | checkpoint `accepted→applied/rejected` | wait | wait | conflict; use explicit successor |
| `provide_input` | rejected | rejected unless a future exact input-required checkpoint is accepted | wait | `accepted→applied/rejected` | conflict |
| `pause` | rejected/unsupported | wait; then `accepted→applied` only on proven pause | unsupported | unsupported | conflict |
| `resume` | unsupported | unsupported | unsupported | unsupported | unsupported; future paused/recoverable representation is not a current `T` |
| `reprioritize` | scheduler `accepted→applied` or unsupported | scheduler/wait | scheduler/wait | scheduler/wait | conflict |
| `cancel` | accepted request | accepted request | accepted request | accepted request | conflict or exact settled replay |
| successor revision | conflict | conflict | conflict | conflict | wait; then new Task `accepted` |

| Operation | Legal state / target | Required capability and exact precondition | Successful result progression | Invalid/race result and zero-effect rule |
|---|---|---|---|---|
| `create` | Collection/create identity; no prior Task state | Authenticated `task.create`; exact resolved context, Task requirements and selected Executor admission facts | Local transaction returns `accepted` with new Task/Attempt/request event/outbox; `running` waits for authoritative Attempt evidence | Malformed/unauthorized → `rejected`; missing requirement → `unsupported`; duplicate exact replay returns the same IDs; changed fingerprint → `conflict` and no second Task/Attempt/outbox |
| `get` | Exact Task in `A/R/B/D/T` | `task.get`, exact scope/target | Read success with canonical Task | Wrong/foreign/unknown target → rejected/not-found with zero mutation |
| `list` | Exact authorized collection; state filter, if later added, is projection only | `task.list`, exact scope and bounded keyset cursor | Read success with stable page metadata | Foreign/stale/malformed cursor → rejected/stale; no Task/Event/consumer mutation |
| `status` | Exact Task in `A/R/B/D/T` | `task.status`, exact scope/target | Read success with canonical Task plus current Attempt | No inferred queued/running/paused label; wrong target has zero mutation |
| `events` | Exact Task in `A/R/B/D/T` | `task.events`, exact scope, bounded per-Task cursor | Read success with one frozen-head page | Future/foreign/malformed cursor → rejected/stale; reading never consumes |
| `result` | Exact Task in `A/R/B/D/T` | `task.result`, exact scope/target | `A/R/B/D` → read success with `not_ready`; completed `T` with one legal immutable row → `available`; other `T` → `unavailable` with canonical reason | Missing/corrupt binding fails closed; no query may fabricate a result, consume unread or invoke artifact/Agent/Executor/TTS mutation |
| `update` | `Q/A` before dispatch; `R` only at a real declared update checkpoint. `B/D` handling is **WAITING DECISION**; `T` is immutable | `task.update`; expected Task version; for live Attempt, selected Executor `update`/checkpoint capability and exact Attempt/epoch | Pre-dispatch atomic spec update may settle `applied`; live update is first `accepted`, then `applied` or definitive `rejected` after exact Adapter evidence | Capability absent → `unsupported`; terminal/version/Attempt race → `conflict`; timeout/uncertain Adapter → `timeout` or `unknown` according to effect evidence; no partial spec/event/outbox effect |
| `provide_input` | At minimum exact `D`. Whether input-required `B` is also legal is **WAITING DECISION**; all other states reject/conflict | `task.provide_input`; exact current question/decision ID, version, Task/Attempt and bounded answer; selected Executor input/checkpoint capability | Durable request → `accepted`; exact applied/rejected event settles `applied`/`rejected` once | Stale/wrong question, ordinary dialogue, changed fingerprint or concurrent decision/terminal → `conflict`/`rejected`; answer never becomes a system instruction and has zero cross-Task/Agent/Tool effect |
| `pause` | Proposed `R` only; the authoritative paused representation is **WAITING DECISION** | `task.pause` plus real selected-Executor pause capability and exact live Attempt/owner epoch | Request `accepted`; only observed proven pause boundary may become `applied` | Until state/Attempt semantics freeze, return `unsupported`; timeout/late terminal never relabels blocked/accepted as paused and never implies success |
| `resume` | Only the frozen paused/recoverable representation; currently no legal P3-1 state | `task.resume` plus matching resume capability, exact checkpoint/Attempt/owner facts and accepted recovery identity choice | `accepted` then `applied` only on authoritative resume evidence | Current target must return `unsupported`; stale checkpoint/owner or concurrent terminal → conflict/unknown as evidence requires; no replacement Attempt without the frozen recovery rule |
| `reprioritize` | `Q/A`; optionally `R/B/D` only if a real scheduler contract says priority remains meaningful. It never changes Task lifecycle state. | `task.reprioritize`, bounded priority value, expected version and real scheduler/admission capability | `accepted` then `applied` after scheduler receipt, with state unchanged | No scheduler → `unsupported`; stale/terminal race → conflict; no fake priority label, Attempt allocation or running transition |
| `cancel` | Exact nonterminal `A/R/B/D`; terminal truth wins | `task.cancel`, exact Task/current Attempt and cancel capability where an Attempt exists | Durable cancel request/ACK → `accepted`; only authoritative cancelled terminal settlement → `applied`. Exact duplicate replays; a second equivalent request creates no second outbox. | Concurrent terminal → conflict or replay of already-settled truth; Adapter timeout/unknown remains timeout/unknown; ACK never means cancelled and no unrelated response/round/Task is stopped |
| successor revision | Exact immutable `T`; eligible terminal outcomes and command name/payload are **WAITING DECISION** | Dedicated successor-create capability; exact predecessor ID/version/result fingerprint, new bounded spec/context, new command identity and authorization/confirmation | One transaction returns `accepted` with a new Task/Attempt/outbox, `predecessor_task_id` and next revision number; duplicate exact replay returns the same new `task_id` | Nonterminal, existing direct successor, changed predecessor/result/version or concurrent creator → conflict; predecessor Task/Attempts/events/result stay byte-for-byte unchanged; no automatic successor from ambiguous update |

Existing compatibility operations need an explicit activation disposition:

- `task.adjust` currently represents one bounded live checkpoint adjustment.
  Decide whether it becomes a compatibility spelling of `update`, is narrowed to
  one update subtype, or is retired after callers migrate. It must not also mean
  `provide_input`.
- `task.retry` currently creates a later Attempt on the same Task for eligible
  cancelled/completed outcomes. Preserve it only as bounded execution recovery;
  it is not successor revision and cannot change the immutable terminal goal or
  result.

### 3.3 Decisions that block production code

The Integration Owner must freeze these before allocating shared schema work:

1. **Successor:** exact command name/payload; eligible terminal outcomes;
   predecessor version/result binding; whether the existing one-direct-successor
   uniqueness remains the product rule; and the relationship to same-Task
   `task.retry`. In particular, current completed-Task retry can produce another
   completed Attempt on one `task_id`; the decision must either retire/narrow
   that path or define immutable historical-result ownership without violating
   P3-5's one legal result per completed Task.
2. **`provide_input`:** exact blocking-question/decision identity and payload;
   whether `blocked` may be input-required or only `decision_required`; answer
   bounds/redaction; and ordered application relative to update/cancel/terminal.
3. **Pause/resume:** canonical paused representation, proven Executor boundary,
   whether resume keeps or links the Attempt, and the exact capability/version
   evidence. Without this decision both operations remain `unsupported`.
4. **Update:** pre-dispatch spec replacement versus live checkpoint adjustment,
   the mapping/retirement of `task.adjust`, and whether `B/D` can accept an
   update distinct from `provide_input`.
5. **Reprioritize:** the real scheduler/admission owner and stable priority
   vocabulary. Without one, the operation remains `unsupported`.
6. **Disposition persistence:** immutable admission receipt plus later
   settlement representation, replay behavior after settlement, and mapping to
   existing `ErrorCode`/cross-language consumers.

## 4. Candidate P3-5A persistence contract

### 4.1 Canonical records and authority

| Record | Required durable contract | Not authority for |
|---|---|---|
| `TaskResult` | Exactly one legal immutable result per completed Task, bound to exact `task_id`, producing `attempt_id`, terminal TaskEvent identity and source Executor event/provenance; bounded summary and authorized artifact references; schema/version and completion time are explicit. A non-completed outcome has no result. | Artifact bytes as instructions, credentials, conversation truth, presentation or Task mutation |
| `TaskEvent` | Append-only `event_id` plus contiguous per-Task `seq`, exact scope/Task/Attempt, event kind, canonical state/outcome, producer/source authority, causation/correlation, time and closed bounded details. Requested events are non-projecting; applied/rejected events record settlement. | Executor action inferred from request, Task truth inferred from projection, presentation ACK |
| Replay cursor | Exact Task/scope-bound “after sequence” position plus the frozen `head_seq` observed for a page; pages are bounded and ordered. Reopen yields the same retained prefix. A later append appears only on a later read. | Unread, consumption, presentation, Task selection or retention deletion |
| Consumption | One server-owned, monotonically advancing acknowledged prefix for an exact authorized consumer, scope, Task and presentation class, with idempotent ACK command identity/fingerprint and `acked_through_seq`. | Canonical Event/Task/Result mutation or proof that audio/text was perceived |
| Unread | Derived from retained applicable events above the consumer watermark; terminal-result unread additionally requires the exact terminal event and legal stored result. It must be reconstructable after restart and must not depend on Session memory, browser storage or `current_background_tasks`. | A second event/result store, running/terminal inference or cross-consumer suppression |

The activation packet must freeze the stable consumer identity and presentation
classes. A Session or response generation is too short-lived to own unread; a
subject-level consumer may be appropriate, but voice and text consumption must
not silently suppress each other unless that product rule is explicitly
accepted.

### 4.2 Read, replay, unread and ACK behavior

- `task.events` and `task.result` remain pure reads. Fetching or displaying a
  page does not advance consumption.
- A consumer ACK is a separate authenticated mutation bound to consumer, scope,
  Task, presentation class, exact event/through-sequence and immutable ACK
  fingerprint. It updates only the consumption ledger and its command replay
  row.
- An exact ACK replay returns the original result. A lower/equal watermark is
  an idempotent no-op; a future sequence, missing event, wrong Task/scope/
  consumer/class or changed fingerprint is rejected/conflicted with zero change.
- Concurrent ACKs linearize to the greatest valid contiguous acknowledged
  prefix. They cannot skip an event outside the acknowledged presentation class
  without an accepted product rule.
- Presentation is at-least-once. Playout/display followed by crash before ACK
  remains unread and may replay; an ACK suppresses later applicable presentation
  replay but never deletes the Event or Result.
- A terminal event is the notification identity. Runtime response/generation/
  TTS and final presentation ACK remain P3-5B owners; P3-5A persists only the
  canonical source and consumption primitive.
- Result retrieval returns the immutable result record independently of later
  artifact-byte availability. Artifact dereference is a separate authorized,
  version/scope/hash-revalidated operation and may report its own unavailability
  without erasing result truth.
- The feature-complete profile must freeze exact cursor/event/result/consumer
  count and byte limits before implementation. Page limits may retain the
  current 1–500 event range; numeric retention and compaction policy remain an
  activation decision. Production retention/SLO operations are not imported.

### 4.3 Atomic terminal settlement

The single Store transaction owner must validate all untrusted result/event
facts before mutation, then atomically settle:

```text
Executor source fact
  + Attempt terminal state/outcome
  + Task terminal state/outcome
  + canonical terminal TaskEvent
  + legal TaskResult iff outcome=completed
  + command/outbox/lease settlement owned by the active seam
  + discoverable unread source event
```

Any validation, uniqueness, failpoint, disk, constraint or commit failure rolls
back the whole group. No transaction invokes the Executor, reads an external
artifact as authority, emits TTS or performs another external effect. Duplicate
canonical Executor/event/result facts are idempotent; changed facts under an
existing identity conflict. Late predecessor facts may remain diagnostic but
cannot mutate a successor Task, its result or its consumption state.

## 5. One Core/Store owner and collision boundary

`P3-2` and `P3-5A` collapse into one owner whenever they touch the common
protocol, formal records, Store schema/migration or a transaction. Separate
worktrees do not make those edits semantically independent.

| Centrally owned surface | One-owner rule |
|---|---|
| Command/query/result schema and Python/TypeScript parity | One shared semantic owner freezes operation names, payloads, disposition and ACK carrier before either lane edits consumers. |
| Formal Task/Event/Result/consumption records | One record vocabulary; no `full_p3_*`, `s85_*` or UI replica becomes a second backend authority. |
| Next SQLite schema/migration | Allocate one next schema version at activation. One migration cohosts command metadata/lineage constraints and result/event/consumer additions, including initialization order, rollback, corruption and v1→current compatibility. Neither lane independently bumps schema. |
| Successor transaction | Command replay, predecessor/version/result reread, new Task/Attempt, lineage, accepted event, dispatch outbox and command result commit together under the Store owner. |
| Control request/application | Admission command/request event/outbox commit together; later Executor settlement, applied/rejected event, command disposition and outbox release commit under the same owner. External Executor action stays outside SQLite transactions. |
| Terminal/result transaction | Executor fact, terminal Task/Attempt/Event, legal result and outbox/lease settlement are one recoverable truth chain. P3-5A cannot append a competing terminal or mutate capability/lease vocabulary owned by P3-3. |
| Consumption ACK transaction | ACK command replay plus monotonic consumer watermark only. It cannot update Task, Attempt, Result, Executor outbox or presentation generation. |

Safe parallel preparation remains possible: a P3-2 lane may prepare pure
operation/fingerprint/decider oracles, and a P3-5A lane may prepare pure
result/event/cursor/consumer records and tests. Both return their exact mapping
to the Integration Owner; only the Core/Store owner composes shared files and
history.

## 6. Historical asset disposition

“Drop” below means omit from the current activation mapping, not delete Git
history. No entire old commit or branch is admitted.

| Asset ID | Preserve | Rewrite into current owner | Drop/defer |
|---|---|---|---|
| `P3A-CTRL-01` | Closed command fields, immutable fingerprint, exact replay/conflict, confirmation binding and result-category oracles | Map operations/payloads/dispositions into the existing v2 envelope, formal policy and P3-2 owner after G2 | The parallel `full_p3_control_contract.py` production owner and historical Task→Attempt state map |
| `P3A-EXEC-CTRL-01` | Capability mismatch, duplicate/conflict/concurrency and unsupported zero-effect oracles | Map only after P3-3 freezes the real Adapter capability seam | Deterministic candidate fake as positive pause/resume/update/reprioritize evidence |
| `P3A-CTRL-TXN-01` | Authorization-before-write, authority reread, admission→application CAS, event/outbox atomicity, failpoint and one-winner tests | Rebuild inside schema-v4-descendant `SqliteTaskStore` and current D119 adjustment owner | Old `full_p3_control_*` Store/Core patch and any schema-v2 assumption |
| `3B-AUTH-DOMAIN` / `3B-AUTH-POLICY` | Exact-scope, default-deny, replay and zero-forbidden-effect oracle cases | Translate only to the existing product authority tests when applicable | Auth/tenant types and policy implementation; they remain future Production scope |
| `S85-RK-01` | Pure bounds, canonical parsing/fingerprint, confirmation and target revalidation invariants | Map running update to the frozen checkpoint contract and terminal revision to new-Task successor | Same-Task one-revision limit, fixed Attempt and historical `update_constraints` authority |
| `S85-STORE-01` | Atomic command/state/event/outbox/ACK shape, claim fencing and late-event quarantine invariants | Rebuild only the admitted P3-2/P3-5A transactions in the current Store migration | Entire `task_revision_store.py`, all `s85_*` sidecar tables and Executor effects inside DB transactions |
| `S85-STORE-ORACLE-01` | Feature-off/no-schema, corrupt schema, request/complete failpoints, replay/conflict, concurrent winner, restart and immutable-ACK scenarios | Rewrite assertions for live checkpoint update or terminal new-Task successor and durable consumer ACK | Same-Task successor assertions and stage-named acceptance ownership |
| `S85-EVENT-01` | Requested-versus-applied separation, exact replay, sequence binding and late-predecessor diagnostics | Extend current `task_events`, result and consumer owners after G2+G5 | S8 event namespace and projection-derived authority |
| `S85-CONFIRM-01` | Every semantic fact in the mutation fingerprint; target/version reread and confirmation conflict zero effects | Add missing P3-2 operation/version/successor/input facts to the current confirmation ledger | S8 flag/owner, voice-only confirmation and any execution claim |
| `S85-PRODUCT-01` | Committed input → prepared exact facts → later confirmation → reread → one Store write ordering oracle | Rebuild through the eventual P3-6/product adapter after G2/G5/G6 | Old Registry semantics, S8 grammar, same-Task revision and voice-only path |
| `S85-WEB-01` | Strict keys, wrong-target, monotonic lineage and generation-fence oracles for later consumers | Defer mapping until P3-5B/P3-7 schemas freeze; at most reuse backend closed-schema cases now | Old revision replica as P3-5A authority or any UI code in this Store lane |
| `S85-DOC-CONTRACT-01` | Identity/admission/fence/successor layering questions | Use only as design checklist against current accepted decisions | Old D-079/D-080, same-Task revision and historical queue |
| `S85-DOC-ACCEPT-01` | Replay/conflict, concurrent winner, terminal/cancel races, failpoints, restart, late facts, unsafe target/verifier and zero-effect scenarios | Route each oracle to the current capability-owned test destination below | Old acceptance label, one-revision journey and runner authority |

All other manifest assets are deliberately out of this mapping. D1/D2,
secure-Executor, recovery facts, Bridge product code, privacy/OTel, deployment,
SLO and historical-status rows remain with their named P3-3/P3-4/P3-6/P3-8/
future owners; importing them here would broaden this packet.

## 7. Test and evidence landing map

This preparation names destinations and required behavior, not passing results.
Exact filenames may be split at activation if current discovery has changed,
but ownership must remain capability-based.

| Evidence family | Proposed current destination | Required cases |
|---|---|---|
| Closed protocol and cross-language parity | [`test_live_voice_contract_v2.py`](../../tests/unit_tests/common/test_live_voice_contract_v2.py), frontend `liveVoiceContractV2.test.mjs` | Every operation/payload/disposition; unknown fields; bounds/Unicode; stable fingerprint; exact replay owner binding; sensitive-field rejection |
| Formal policy/authorization/confirmation | [`test_formal_task_policy.py`](../../tests/unit_tests/live_voice/test_formal_task_policy.py) and current confirmation-owner tests | Exact target/scope/version/capability; destructive confirmation; wrong/stale/foreign/changed-fingerprint zero effects |
| Core/Store command, migration and transaction | [`test_persistent_task_core.py`](../../tests/unit_tests/live_voice/test_persistent_task_core.py), or activation-time capability-owned files split from it without reducing discovery | Positive operation/state matrix; invalid state; accepted≠applied; successor immutability; update/input ordering; cancel/terminal and update/terminal races; schema migration/cohost/failpoints/restart |
| Result/event/cursor/unread/consumption | Current persistent Core/Store suite plus a capability-owned `test_task_result_event_consumption.py` if split | One result only for completed; terminal transaction rollback; contiguous cursor; unread reconstruction; ACK idempotency/monotonicity; crash-before-ACK replay; wrong consumer/scope/task/class zero effects |
| Event projection compatibility | [`test_task_event_subscription.py`](../../tests/unit_tests/live_voice/test_task_event_subscription.py) and current progress projection owners | Requested events non-projecting; applied/rejected settlement; no duplicate progress; late predecessor diagnostic only |
| Authenticated structured seam | [`test_p3_authenticated_composition.py`](../../tests/unit_tests/live_voice/test_p3_authenticated_composition.py) and current text-adapter tests | Exact addressed parity for structured callers, page metadata, command disposition and result/unread queries; no natural-language P3-6 credit |
| Real Executor/product seam | P3-3/P3-5B/P3-7/P3-9 evidence destinations selected later | Positive live update/input/pause/resume/priority only on real declared capability; at-least-once presentation and real ACK; fake/candidate positives are supporting evidence only |

The Tier-3 D-032 matrix must be made explicit at activation:

- **Positive:** every supported matrix row, two independent Tasks, ordered
  update/input, immutable terminal successor and durable unread/result replay.
- **Negative/bounds:** malformed/oversized payload/result/event/cursor/ACK,
  unsupported capability, invalid state, wrong question/version/consumer and
  no fabricated result.
- **State/time/order:** requested versus applied, duplicate/conflicting command
  and ACK, stale owner/Attempt/cursor, reordered/late predecessor events and
  terminal races.
- **Concurrency:** same and changed fingerprints across Store instances, two
  distinct ordered commands, one successor winner, terminal/control races and
  monotonic concurrent ACK watermarks.
- **Retry/restart:** reopen after every admitted/claimed/applied/terminal/ACK
  boundary; crash before/after commit; exact replay without duplicate Task,
  Attempt, Event, Result, outbox or consumption.
- **Failpoints:** next-version DDL/backfill/index/metadata; successor after each
  Task/Attempt/Event/outbox/command write; control request and settlement;
  terminal Executor-event/Attempt/TaskEvent/Result/outbox/commit; consumer
  command/watermark/commit. Every point must roll back to one valid old or new
  state.
- **Identity/isolation:** subject/project/session/task/attempt/command/event/
  result/consumer/presentation-class bindings and selection-hint non-authority.
- **Feature/compatibility:** feature-off zero schema/network/DOM/product effects;
  v1→v4→next migration; existing create/adjust/retry/cancel/query behavior until
  explicitly migrated; Python/TypeScript parity.
- **Cross-module/real path:** accepted P3-3 capability evidence and P3-5B
  Runtime/Web invocation are required before product claims. A Store fake is not
  real Adapter or user-observed evidence.

For every rejected, unsupported, conflict, timeout, unknown, stale, duplicate,
wrong-scope and failpoint case, assert zero forbidden Agent, Tool, Task-other-
than-the-exact-authorized-row, Attempt, Executor dispatch/effect, file/artifact,
audio/TTS, conversation/history, presentation, consumer-other-scope, network
and external side effects. “No row count changed” alone is insufficient when an
external Port could have been called.

## 8. Activation and re-review triggers

This preparation becomes eligible for conversion into an implementation packet
only when all applicable triggers are satisfied:

1. The scoped P3-G0 foundation Gate is satisfied on the formal G0_FINAL lineage;
   the controlled product-readiness candidate remains `FAIL` and is not a
   prerequisite for this code packet.
2. P3-1 is accepted at `d40e0ee3` on that same lineage, with schema/state/
   successor identity and current-Task-as-hint semantics rechecked. STATUS now
   activates P3-2; P3-5A requires a separately recorded parallel assignment or
   later activation before implementation. Diff and re-audit every affected
   fact if the implementation baseline moves beyond that source.
3. The Integration Owner selects the exact asset IDs from §6, current target
   files/symbols, next schema version, migration owner and non-overlapping
   worker leases.
4. The six decisions in §3.3 and the consumer/retention/presentation-class
   choices in §4 are frozen. A material authority/protocol choice goes through
   the repository decision process before code.
5. P3-3 freezes capability/admission/Attempt/lease vocabulary before any real
   live update/input/pause/resume/priority positive or Executor-owned field is
   composed.
6. Any change to common command/result schema, canonical states, terminal
   settlement, `TaskResult`, event pagination, lineage uniqueness, artifact
   policy, outbox/lease owner or profile composition triggers affected-row and
   asset-mapping re-review.
7. Any cherry-pick/rebase conflict or migration from another historical branch
   invalidates line-level assumptions; resolve it under the single Core/Store
   owner and rerun focused plus affected Tier-3 review.
8. Before historical refs retire, every selected `PORT`/`ORACLE` row is marked
   migrated, explicitly deferred or deliberately rejected with owner/reason.

At activation, create one bounded packet using the manifest §7 fields and root
TESTING review cadence. At module closure, run the complete scoped diff review,
focused/affected regressions and one independent Tier-3 review; at product
closure, real Adapter/Runtime/Web and human evidence remain required.

## 9. Explicit non-claims

This document adds no source, test, migration, schema, telemetry, UI or runtime
behavior. No command matrix row is implemented merely because a candidate
contract is written here. No historical module, fake, wire, test count or
review label transfers authority or acceptance. The exact integrated lineage
above is the inherited baseline; this preparation adds documentation only.

Consequently this preparation does not alter the already recorded scoped P3-G0
or accepted P3-1 credit and grants **no P3-2, P3-5A, P3-5, complete-P3,
feature-complete, product-readiness, RC or Production credit**. STATUS may
change only after the owning implementation, migration, tests, independent
review and required real product evidence run on one exact clean source.
