# P3-5B and P3-6 activation preparation — 2026-08-18

Status at the preparation snapshot: **PREPARATION ONLY / NOT YET ACTIVATED / NO CREDIT**

This packet prepares two Wave-3 implementation lanes from the accepted scheduling
contract in the [complete P3 plan](../roadmap/FULL_P3_EXECUTION_PLAN.md):

- `P3-5B`: Runtime/Web delivery, durable consumption and presentation ACK over an
  already accepted `P3-5A` result/event/cursor/unread Store contract; and
- `P3-6`: generalized committed-input routing, multi-Task target clarification
  and voice/text operation parity over accepted `P3-2` commands and `P3-5A`
  result/event truth.

It selects the source seams, candidate contracts, historical oracle IDs, test
destinations, collision rules, activation Gates and re-review triggers that
applied at the 2026-08-18 preparation point. It inherited the scoped P3-G0
foundation and accepted P3-1 facts but did **not** itself authorize production
implementation while the named P3-5A/P3-2 hard dependencies were then
unaccepted. Later outcomes are recorded in current [STATUS](../STATUS.md), the
[P3-5B review](P3_5B_PRESENTATION_CONSUMPTION_IMPLEMENTATION_REVIEW_2026-08-21.md)
and the
[Wave-3 review](P3_WAVE3_DURABILITY_PRESENTATION_INTENT_IMPLEMENTATION_REVIEW_2026-08-21.md).

## 1. Evidence identity, scope and committed source facts

### 1.1 Integrated baseline

| Identity | Role in this preparation | What it does not prove |
|---|---|---|
| `f24dd17d336c8266954f2d7299ca13bd0314d424`; `8df7d38227b684177efca8cad83d77278ad42c19` | Formal G0_FINAL product source and scoped P3-G0 close. | D-086 preserves the controlled product-readiness candidate as `FAIL`; neither commit proves a physical candidate PASS. |
| `5787eda931159ba533e0a81ca8be8b744f449a8b`; `40afbda89453cc465b00d78c51a87c0661307a65` | Rebaselined historical audit/57-asset manifest and the integrated P3-2/P3-5A preparation on the G0_FINAL lineage. | They add documentation only and do not accept P3-2, P3-5A, P3-5B or P3-6 implementation. |
| `d40e0ee391fdf162faa9d9938eb9b9610020c1a7` | Accepted P3-1 source used for exact current files, symbols and inherited evidence. | It does not satisfy the P3-5A/P3-2 hard dependencies or this packet's product/real-path evidence. |

These identities are one linear integration history. Activation must use an
exact clean descendant containing its accepted hard dependencies and must
re-audit every fact affected after `d40e0ee3`.

### 1.2 Formal G0_FINAL prepared-source facts

The former pre-amend workspace snapshot is superseded. The following relevant
changes are committed on formal source `f24dd17d` and remain present at accepted
P3-1 source `d40e0ee3`:

- `P3AuthenticatedComposition.product_progress_authority_atomic_replay` exposing
  whether the exact concrete Store can supply an atomic progress prefix;
- `ProductP3TextAdapter.replay_text_from_prepared_source` and Registry wiring to
  reuse `TaskEventAuthorityProgressSource` for text as well as voice;
- `TaskProgressReturnBridge` generalizing prepared-source start/read/close,
  attempt fencing and initial sequence validation to any exact prepared source;
  and
- a text projection test that replays Store sequences `0` and `3` with zero
  voice intent and zero Store mutation.

These are committed replay/source seams, but they grant no durable-consumption,
P3-5A, P3-5B or P3-6 acceptance. They must be re-read from the exact accepted
P3-5A/P3-2 descendant at activation. Other media/capture behavior remains
outside this packet.

## 2. Exact current target facts and gaps

The following are facts of accepted P3-1 source `d40e0ee3`, not the intended
final P3-5B/P3-6 design.

| Current file / symbol | Existing fact on `d40e0ee3` | Required activation interpretation |
|---|---|---|
| [`task_store.py`](../../jiuwenswarm/server/live_voice/task_store.py) — `_SCHEMA_VERSION = 4`, `SqliteTaskStore.event_authority_snapshot()` and TaskResult methods | The Store has immutable bounded TaskResult records and a Store-owned atomic TaskEvent prefix/cursor snapshot. | Preserve this durable replay foundation. Do not describe the target as having no durable event replay; the missing boundary is durable per-consumer unread/consumption/presentation ACK. |
| [`task_event_subscription.py`](../../jiuwenswarm/server/live_voice/task_event_subscription.py) — `TaskEventAuthoritySource`, `TaskEventSubscription` | Authority mode validates the complete Store prefix against its cursor, then follows the durable suffix; default mode is live-only. Closing detaches only. | P3-5B consumes the accepted P3-5A replay source; it must not add a caller-selected history cursor or mutate Task state. |
| [`task_progress_return.py`](../../jiuwenswarm/server/live_voice/task_progress_return.py) — `TaskEventAuthorityProgressSource`, `TaskProgressReturnBridge`, `TaskProgressOriginBinding` | The exact Store source supports atomic prefix/cursor replay. The Bridge revalidates canonical events and projects text or a notification intent; it has no TTS, history, Agent, Tool or Task-mutation Port. | Retain source validation and non-authority. Its arbiter ACK, pending delivery and generation state are not a durable consumer/unread owner. |
| [`progress_notification_arbiter.py`](../../jiuwenswarm/server/live_voice/progress_notification_arbiter.py) — `ProgressNotificationArbiter`, `acknowledge()` | Selects bounded display/speech candidates and keeps a failed consumer candidate pending in process. It explicitly has no UI, audio, TTS, lifecycle, timer, network or persistence Port. | Use as Runtime candidate arbitration only. Never equate `acknowledge()` with durable P3-5A consumption. |
| [`product_p3_text_adapter.py`](../../jiuwenswarm/server/live_voice/product_p3_text_adapter.py) — `ProductP3TextAdapter.activate_prepared_text_progress()`, cleanup handles | Authority-first text/UI activation validates exact generation and retains failed cleanup. With `replay_text_from_prepared_source`, accepted G0 wiring can select the prepared atomic Store replay source for text as well as voice. | Recheck after P3-5A. P3-5B must use the accepted replay source for every presentation class without making this adapter a Store owner. |
| [`product_composition_registry.py`](../../jiuwenswarm/server/live_voice/product_composition_registry.py) — `_emit_text_progress()`, `_remember_terminal_notification()`, `_deliver_terminal_notification()`, `handle_p3_progress_activate/ack/close()` | Text delivery has exact task/session/origin/generation/delivery/event/evidence binding and in-memory replay. Voice activation intentionally falls back to visible text because the product has no audible progress consumer. Terminal pending/response maps are process memory and are cleared by `stop()`. | Existing delivery binding is an oracle, not durable unread. The existing Web ACK says it proves only that a validated fact reached the stock Web consumer; it is not `PresentationAck`, history truth, Task transition, voice delivery or proof a person saw it. |
| [`presentation_ledger.py`](../../jiuwenswarm/server/live_voice/presentation_ledger.py) — `PresentationSurface`, `PresentationAck`, `PresentationLedger` | Runtime-local text/audio units have exact `ResponseRef`, unit and contiguous cursor ACKs. The module is explicitly in-memory. | Reuse response/unit/surface validation. Only an authorized P3-5A consumption transaction can clear durable unread after the correct accepted presentation ACK. |
| [`product_p2_interaction_adapter.py`](../../jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py) — `present_task_notification()`, `deliver_task_progress()`, `acknowledge_presentation()` | Existing current-response presentation and history seam can present a terminal notification and validate text/audio ACK. | Runtime remains response/generation/TTS owner. A TaskEvent must never call TTS or allocate a response itself. |
| [`productTextProgress.ts`](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts) — parser, `ProductTextProgressAckOwner` | Strict event parsing and exact delivery ACK retry exist; reconnect retries in page memory and capacity never evicts unacknowledged deliveries. `close()` clears them. | Preserve parser/fence oracles, but browser memory is a delivery helper, not consumer truth or unread storage. |
| [`productP3ProgressGenerationJournal.ts`](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3ProgressGenerationJournal.ts) — `claimProductP3ProgressGeneration()` | Session storage holds a bounded monotonic Web generation hint before activation. | Revalidate it server-side. It cannot be the durable unread watermark or cross-restart consumption owner. |
| [`productTaskProgressPresentation.ts`](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/productTaskProgressPresentation.ts) | Only accepted/running-specific translation selection exists. | P3-5B needs truthful blocking/decision/progress and completed/failed/cancelled/interrupted/unknown projection; P3-7 owns the final control experience. |
| [`voice_task_bridge.py`](../../jiuwenswarm/server/live_voice/voice_task_bridge.py) — `BoundedAlphaTaskIntentResolver`, `resolve_unified()`, `VoiceTaskBridge` | The resolver declares a narrow deterministic English/Chinese grammar. Unified routes are `create/update/query/status/cancel/dialogue` and target mainly one Store-derived `CurrentBackgroundTaskContext`. `VoiceTaskBridge.map()` maps only create/cancel. | Treat exact phrases, negation and source-span checks as seeds/oracles. There is no multi-Task target clarification or full operation parity. |
| [`voice_task_policy.py`](../../jiuwenswarm/server/live_voice/voice_task_policy.py) — `FormalTaskPolicyInput`, `FormalTaskPolicyAdapter` | Structured policy accepts queries `get/list/status/events/result` and commands `create/adjust/cancel/retry`, with committed voice/text origin and exact authority/confirmation validation. | This is broader than the unified voice resolver but still not full P3. Structured text support must not be reported as voice/text parity. |
| [`product_composition_registry.py`](../../jiuwenswarm/server/live_voice/product_composition_registry.py) — `handle_unified_submit()`, `handle_p3_intent()`, `_confirm_pending_task_intent()` | Registry currently coordinates unified foreground work, committed intent acquisition and confirmation recovery. | P3-6 may compose through this seam, but Registry must not become semantic classifier, target, Task, Result, Executor or TTS authority. |
| [`formalTaskIntentRoute.ts`](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskIntentRoute.ts) — `FormalTaskIntentOperation`, `ProductFormalTaskIntentOwner` | Web natural-language route supports only `task.create/status/cancel` and retains content-free recovery checkpoints for those operations. | Rewrite protocol ownership only after P3-6's operation/clarification contract freezes; do not infer parity from the current recovery journal. |

## 3. P3-5B delivery and consumption contract

### 3.1 Hard dependency and authority split

P3-5B production starts only after P3-5A is accepted on the integration lineage.
It may add no parallel Result/Event/Unread Store or migration. The accepted
P3-5A owner must provide:

1. canonical TaskResult and append-only TaskEvent reads;
2. bounded at-least-once replay with exact Task/scope cursor;
3. a durable, server-owned consumer watermark and idempotent consumption command;
4. unread derivation reconstructable after reconnect/restart; and
5. the result/event/consumer retention bounds for the selected product profile.

P3-5B owns delivery attempts, current Runtime generation selection, Web/voice
presentation and the exact call that applies an accepted presentation ACK to
the P3-5A consumption record. It does not own Task/result/event truth.

### 3.2 Consumer identity and unread watermark candidate

The following default must be explicitly accepted or replaced at activation:

- `consumer_key = (subject_id, project_id, server_minted_consumer_id,
  presentation_class)`;
- `server_minted_consumer_id` is opaque, authenticated and bound server-side to
  the declared product profile. A browser cannot claim another consumer;
- `presentation_class` is closed as `web_text` or `voice_audio`. An ACK in one
  class never suppresses the other class;
- `session_id`, interaction, response, activation, generation and `delivery_id`
  bind one attempt. They are not the stable consumer identity; and
- a requested voice notification that truthfully falls back to text may consume
  only `web_text`. It cannot mark `voice_audio` consumed.

For each `(consumer_key, task_id)`, the Store owns `acked_through_seq`. It may
advance only to the highest contiguous canonical event position for which every
applicable presentation item has an accepted exact consumption ACK, or was
deterministically classified by the accepted contract as not presentable.
An unacknowledged item blocks the watermark. Exact ACK replay is idempotent;
changed task/event/result/consumer/class/generation/delivery facts conflict.
No Web or Runtime caller supplies a higher watermark.

Terminal unread requires both the exact terminal TaskEvent and the legal stored
TaskResult for `completed`. Failed, cancelled, interrupted and unknown terminal
events remain presentable with their distinct outcome and do not fabricate a
result. A result query never consumes unread.

Every P3-5A event class selected for presentation must close the same consumer
matrix; terminal delivery is not the only positive path:

| Presentable class | Canonical source | Required `web_text` / `voice_audio` behavior |
|---|---|---|
| ordinary progress | exact append-only progress event and Attempt/source sequence | no active interaction leaves it unread; text adoption or exact audio ACK consumes only its own class; missing ACK, restart and reconnect replay at least once |
| blocking question | exact blocking event plus question/decision identity | same class-isolated unread/ACK rules; presentation never answers the question, and ordinary dialogue is not harvested as input |
| `decision_required` | exact durable decision-required event/evidence head | same class-isolated unread/ACK rules; presentation ACK grants no decision or Task mutation authority |
| terminal outcome | exact terminal event and, only for `completed`, its legal TaskResult | preserve completed/failed/cancelled/interrupted/unknown distinctions; same no-active, missing-ACK, restart and cross-class isolation rules |

Cross-device sharing of one `server_minted_consumer_id`, consumer retirement,
watermark retention and the treatment of non-presentable event gaps are product
decisions that must be frozen with P3-5A before this default becomes code.

### 3.3 Exact delivery state machine

1. **Read:** under current authorization, read a bounded P3-5A unread page and
   its frozen head. Validate scope, Task, Attempt, event ID/sequence, producer,
   outcome and, for completed terminal, exact legal result.
2. **Select:** identify the exact active interaction only through the Runtime
   owner. If none exists, leave the item unread and allocate no response, TTS,
   DOM or consumption effect.
3. **Reserve attempt:** bind `consumer_key`, presentation class, event ID/seq,
   result identity when applicable, session/interaction, response/delivery ID
   and a new current generation. A prior Task-create response generation must
   never be reused.
4. **Present text:** the Web/text adapter validates the closed schema and exact
   current session/task/generation, adopts the event into the owned text
   consumer, then returns one exact `web_ui_text_consumed` delivery ACK. It does
   not claim human perception.
5. **Present voice:** Runtime/arbiter creates a new response, generates the
   truthful notification text, owns TTS/audio scheduling and accepts only the
   exact `PresentationAck` for `PresentationSurface.AUDIO`. TaskEvent and Bridge
   never call TTS. Text units alone cannot consume `voice_audio`.
6. **Consume:** only after the applicable ACK is accepted does the server issue
   the exact idempotent P3-5A consumption command. That command changes consumer
   state only; it changes no Task, Attempt, Event, Result, outbox or Executor.
7. **Settle/replay:** durable consumption success suppresses later applicable
   replay for that consumer/class. A lost response after the consumption commit
   reconciles by exact command identity. Otherwise the same unread fact may be
   redelivered at least once.

### 3.4 Crash, disconnect and generation semantics

| Boundary | Required result |
|---|---|
| Crash before presentation publish | No consumption; unread replays. |
| Publish/DOM adoption or audio playout before ACK | No consumption; replay is allowed. This explicitly avoids an exactly-once speech claim. |
| ACK accepted in presentation owner, crash before P3-5A consumption commit | Still unread; exact ACK/consumption reconciliation may replay without Task mutation. |
| Consumption commit succeeds, response is lost | Exact command reconciliation returns consumed; no second watermark advance or presentation is required. |
| Browser disconnect / Runtime route close | Fence late callbacks and release delivery resources; do not consume, cancel Task or clear Store unread. |
| Newer response/presentation generation | Older generation cannot publish or ACK. Its unread item remains available for a new current generation. |
| Result/event append races with a frozen page | Deliver only the frozen prefix; later items appear on a later read. Never advance beyond an unseen gap. |
| Consumer or scope changes | No watermark reuse; foreign ACK and existence probing fail closed with zero presentation/consumption effect. |

The current Registry's in-memory `_progress_deliveries`,
`_pending_terminal_notifications`, `_terminal_notification_responses` and Web
ACK flags cannot satisfy any crash/restart row above.

### 3.5 Voice/text presentation ownership

| Surface | Owns | Must not own |
|---|---|---|
| P3-5A Store/Core | Canonical result/event, unread derivation, consumer watermark, exact consumption transaction | Runtime response, TTS, DOM, active interaction choice |
| Conversation Runtime + arbiter | Active interaction, response/generation, interruption policy, TTS/audio units and audio PresentationAck | Task lifecycle, result creation, unread schema or silent Task cancel |
| Text/Web adapter | Strict event schema, actual owned text adoption, delivery retry and exact Web ACK | Canonical Task/result, voice consumption, human-perception claim or cross-consumer watermark |
| Bridge | Source-backed event projection and candidate handoff | Task/Result/Executor/TTS/presentation/consumption authority |

## 4. P3-6 operation, target, clarification and confirmation matrix

All natural-language voice and natural-language text operations begin with an
authoritative committed input. An interim speech hypothesis or editable text
draft has zero Task effects. Structured UI may supply an exact stable Task ref
without NLU, but it still passes the same authorization, target reread, state,
capability, confirmation and Core result policy.

`C` below means the frozen P3-2 confirmation policy. The recommended default is
exact fingerprint confirmation for create, materially redirecting update,
cancel and successor; capability-control and provide-input choices remain the
explicit P3-2 design decisions, not Bridge inventions.

| Operation | Voice committed input | Natural/structured text | Multi-Task target rule | Clarification | Confirmation / canonical result |
|---|---|---|---|---|---|
| `create` | Resolver proposes bounded name/spec from one exact source span. | Natural text uses the same resolver; structured form supplies bounded fields. | Collection operation; no existing Task is selected. | Missing/ambiguous goal or required context creates a clarification handle; answer is a new commit. | `C` binds exact scope/spec/context/capability/command. Success is P3-2 `accepted`, never `running` or completed. |
| `query` (`get/list/status/events/result`) | Resolver distinguishes query kind and explicit target/reference. | Structured query is preferred; list has no target, other queries require exact target. | Stable task ID/reference first; unique authorized name may narrow; recency/current selection is a hint only. | Zero/multiple candidates or ambiguous query kind clarifies; no guessed “latest”. | No mutation confirmation. Return exact P3-5A event/result or P3-1 Task truth; queries never consume unread. |
| `update` | Resolver proposes exact bounded patch/instruction, never authority. | Same natural resolver or structured patch. | Exact nonterminal Task and version/Attempt facts from Store reread. | Ambiguous target, patch or update-vs-input meaning clarifies. | `C` by recommended default; P3-2 returns accepted/applied/rejected/unsupported/conflict/timeout/unknown. Terminal target redirects only through explicit successor. |
| `provide_input` | Answer must reference one exact blocking question/decision and be a new commit. | Structured answer carries exact question/decision token; natural answer resolves only against one pending candidate. | Exact Task, Attempt, question/decision ID and version; ordinary dialogue is never harvested as input. | Multiple pending questions, missing target or ambiguous answer clarifies. | Follow frozen P3-2 policy; confirmation never replaces the answer commit. Result is ordered accepted then applied/rejected, or safe failure. |
| `pause` | Proposal only for an exact running Task. | Structured control uses exact Task. | Exact current Attempt/owner; selected Executor must advertise accepted pause capability/version. | Missing/multiple target clarifies; unsupported is not clarification. | Follow `C`. Without frozen paused state and real capability return stable `unsupported` with zero effects; ACK is not paused truth. |
| `resume` | Proposal only for the frozen paused/recoverable representation. | Structured control uses exact Task/checkpoint facts. | Exact Task, Attempt/recovery identity and checkpoint/owner facts. | Ambiguous target or recovery identity clarifies. | Follow `C`. No accepted representation/capability means `unsupported`; no replacement Attempt is inferred. |
| `reprioritize` | Resolver proposes a bounded priority value. | Structured control supplies closed priority vocabulary. | Exact Task/version and real scheduler/admission owner; lifecycle state is unchanged. | Missing target/value or multiple Tasks clarifies. | Follow `C`. No scheduler capability returns `unsupported`; a local label is not application proof. |
| `cancel` | Negation is evaluated before an affirmative proposal; exact target required. | Natural text uses same resolver; structured control uses stable ID. | Exact nonterminal Task/current Attempt; current/previous pronouns cannot select among multiple candidates. | Any target ambiguity clarifies and allocates zero cancel/outbox effect. | `C` is required. Accepted cancel request/Executor ACK is not cancelled terminal truth; result follows P3-2 categories. |
| `successor` revision | Explicit revision proposal; never inferred from a failed terminal update. | Structured form binds predecessor and new bounded spec. | Exact immutable terminal predecessor, version/result fingerprint and accepted eligibility; new `task_id` is allocated once. | Ambiguous predecessor/spec or successor-vs-retry meaning clarifies. | `C` required. Returns the same new Task on exact replay; changed facts conflict. Predecessor/result remain immutable. |

### 4.1 Target resolution protocol

1. Read the authorized visible Task set and stable references from Store; do not
   let the resolver enumerate foreign Tasks.
2. A classifier/grammar/model proposes operation, arguments and zero or more
   candidate refs with confidence/provenance. Its output is untrusted data.
3. Closed policy validates committed origin, exact source spans, supported
   operation, bounds, scope, state, permission and current capability.
4. An explicit stable ID/ref wins only if it resolves to one authorized Task.
   A name is usable only when unique in the authorized snapshot. Recency,
   current selection and conversation mention may narrow but never decide an
   ambiguous mutation.
5. Zero or multiple candidates produce a bounded clarification containing no
   private result/input data. The user's answer is another authoritative commit
   bound to the clarification identity and a re-read Task set.
6. Confirmation is a later commit bound to one immutable command fingerprint.
   It neither selects the Task nor repairs ambiguity, and a clarification answer
   never silently confirms a destructive operation.
7. Before Core invocation, reread Task/version/Attempt/question/result and
   capability. Stale facts yield the P3-2 safe disposition with zero other-Task
   effects.

### 4.2 Clarification handle lifecycle

Clarification is pre-command interaction state, not a Task mutation or an
implicit confirmation. Activation must select one owner—recommended: the
existing committed-input/interaction ledger owner, not Bridge or Registry maps—
and one restart policy. A handle binds at minimum subject/project/scope,
committed-source identity, proposed operation, ambiguous field names, authorized
candidate-set fingerprint, created/expiry bounds and a single-use generation;
it contains no foreign/private result or input payload.

Capacity, TTL and per-subject limits are bounded. Consuming a handle is a CAS:
the answer is a new committed input, the authorized Task set and capabilities
are reread, and exact replay returns the same clarification outcome while a
changed answer/generation conflicts. Expired, abandoned, superseded, foreign or
already-consumed handles allocate no command/outbox/Task effect.

The Integration Owner must freeze one of two restart semantics: either the
handle is durably reopened by the selected interaction-ledger owner, or every
pre-restart handle becomes unusable and the user is asked a new clarification
with a new identity. Process-local recovery must never silently accept the old
answer, and P3-6 cannot claim restart closure until the selected rule has
focused and product-path evidence.

### 4.3 Bridge authority firewall

The generalized Bridge may parse/propose, bind source spans, request candidate
lookup and return clarification. It must not:

- create or mutate Task/Attempt/Command/Event/Result/consumer rows;
- infer running, paused, applied, terminal, result-ready or presentation truth;
- call Agent, Tool, Executor, scheduler, file/artifact, network, TTS or history;
- select a foreign/ambiguous Task or treat current/recency/name as authority;
- mint authorization, capability, confirmation or presentation ACK; or
- make Registry, Web state, dialogue text or project files a second semantic
  owner.

The closed policy/Core owner is the only mutation admission boundary. P3-5A is
the only result/event source. Runtime is the only voice presentation owner.

## 5. Parallel eligibility and mandatory serialization

| Surface | May proceed in parallel | Must serialize / single owner |
|---|---|---|
| P3-5B Runtime/Web | Runtime arbitration and presentation tests can run beside Bridge resolver/corpus work after accepted P3-5A. Strict Web parser/ACK tests can be prepared against a frozen wire. | Any `presentation_ledger`, current response generation, TTS/audio ACK or shared Runtime notification path touched by another lane. |
| P3-6 Bridge | `voice_task_bridge.py`, capability-owned corpus fixtures and Bridge-only tests may be isolated from P3-5B. | P3-2 command/result policy, P3-5A result/event semantics, target visibility and confirmation policy remain with their owners. |
| Product composition | Read-only seam review may overlap. | `product_composition_registry.py`, `p3_authenticated_composition.py`, AgentServer routing, shared product flags/profile, `formalTaskIntentRoute.ts`, `productWebActivation.ts`, Panel and wire schema have one integration writer. These are P3-7 collision surfaces when final carrier work begins. |
| Store | P3-5B may call an accepted P3-5A Port. | No P3-5B or P3-6 Store schema/migration/transaction change without re-scoping to the P3-5A/Core owner. |
| Tests | Non-overlapping unit/corpus files can be separate lanes. | Cross-module product journeys, shared fixtures and cumulative candidate evidence are integrated and reviewed centrally. |

P3-5B and P3-6 are therefore conditionally parallel, not freely composable.
P3-5B requires accepted P3-5A. P3-6 requires accepted P3-2 plus the accepted
P3-5A result/event contract. A branch existing does not open either Gate.

## 6. Historical asset disposition from the 57-asset manifest

Whole 3A/S8.5 commits and old product wiring are not conforming patches. Select
only the following named assets through the current owners.

| Asset ID | Preserve | Rewrite into current target | Drop / forbid |
|---|---|---|---|
| `P3A-CTRL-01` | Closed operation/payload, fingerprint, confirmation, replay/conflict and result-category oracles. | Feed accepted P3-2 operations into the P3-6 closed policy and parity corpus. | Parallel `full_p3_control_contract.py`, old state map and any claim that candidate control proves execution. |
| `P3A-CTRL-TXN-01` | Exact replay, atomic command/state/outbox and failpoint principles as dependency evidence. | Consume only through accepted P3-2/P3-5A Core contracts. | Bridge/Registry transaction authority or an old schema patch. |
| `P3A-EXEC-CTRL-01` | Capability mismatch, exact control binding, concurrent winner and zero-effect rejection oracles. | Inherit through accepted P3-2/P3-3 command/admission contracts; add only missing P3-6 parity/corpus cases. | Direct historical port, Bridge-owned capability truth or credit from a fake Executor. |
| `3B-AUTH-DOMAIN` / `3B-AUTH-POLICY` | Exact scope/default-deny/expiry/forgery/existence-hiding negative oracles. | Map to current `product_authority.py` and P3-6 zero-effect tests. | Historical production auth/tenant owner or claims of real IDP/product auth. |
| `S85-RK-01` | Unicode/bounds, canonical parse/fingerprint and target revalidation. | Generalize for all accepted operations, multi-Task, new-Task successor and exact blocking input. | Same-Task one-revision, fixed Attempt, `update_constraints` authority and exact regex as product NLU. |
| `S85-STORE-01` / `S85-STORE-ORACLE-01` | Atomic request/ACK, replay/conflict, failpoints, race/restart and late-event quarantine oracles. | Apply only in accepted Core/P3-5A schema and transaction tests when needed. | `s85_*` sidecar, second consumer/result store or Store effect inside Bridge/Runtime. |
| `S85-EVENT-01` | Requested-versus-applied settlement, exact event sequence and late predecessor diagnostic oracles. | Map to P3-5A event/replay and P3-6 canonical result handling. | S8 event namespace or projection as authority. |
| `S85-BRIDGE-01` | Committed input, Store-derived target, source spans, stale reread, wrong-scope/ineligible/ambiguous rejection. | Multi-Task candidate set, bounded clarification, exact blocking input and common voice/text policy. | Voice-only, single-current-Task and Demo/exact-regex product semantics. |
| `S85-CONFIRM-01` | Every semantic field in fingerprint, exact target/version reread, confirmation conflict. | Extend the current confirmation ledger with all accepted P3-2 fields. | Confirmation as target selection, language understanding or execution proof; S8 owner/flag. |
| `S85-EXEC-01` / `S85-EXEC-ORACLE-01` | Negative cleanup/fence/restart facts relevant to capability-controlled operations. | Consume P3-3/4 outcome/capability truth only after their Gates. | Bridge/Result/presentation authority, private Executor fields or P3-6 claiming capability from an interface. |
| `S85-WEB-01` | Strict exact-key schema, wrong-task rejection, application distinct from success, unknown cleanup/verifier non-success, monotonic replay, lifecycle-regression rejection, disconnect generation fence and no inferred success. | Prepare/characterize its parser/fence scenarios now, but port unique fields only into the eventual current `FormalTaskControlLeaf`/P3-7 replica after `G2+G5+G6+G7` and only where the accepted current wire matches. | A second Web truth replica, old revision schema, early P3-7 production wiring or any cleanup/verifier schema not accepted by current owners. |
| `S85-WEB-02` | Feature-off/no-DOM/no-read negative scenario idea. | Rebuild later for multi-Task, full operations and common voice/text semantics. | Old Panel JSX/CSS, polling, S8 selector, voice-only confirmation and bespoke flag. |
| `S85-PRODUCT-01` | Commit → Store target → prepared facts → later confirmation → reread → one write ordering. | Rebuild through P3-6 Bridge/current policy and P3-2 Core. | Registry semantic ownership, S8 grammar, same-Task revision and voice-only route. |
| `S85-RECOVERY-01` | Restart/reopen ordering as a test idea. | Only current P3-3/4 Core/Executor recovery may own it. | Parallel Registry worker, polling-derived terminal or P3-5B consumption pump. |
| `S85-COMPOSE-01` | Missing one prerequisite creates no authority; feature-off is zero-touch. | Current profile/composition tests under the owning package. | Old environment variables, duplicate confirmation/worker owners and implicit production enablement. |
| `S85-DOC-CONTRACT-01` / `S85-DOC-ACCEPT-01` | Identity/admission/successor questions and negative/failpoint/race/restart/zero-effect scenarios. | Add multi-Task, full operation, text/voice, result/unread and real Runtime/Web dimensions. | Old readiness, same-Task scenario, pass count or acceptance credit. |
| `S85-DOC-SHOWCASE-01`, `S85-DOC-REVIEW-01`, `S85-DOC-CLAIMS-01`, `S85-DOC-MUTABLE-01` | Provenance only. | None for production. | Old journey, status/queue/decision edits, competitor claims, pass counts and historical PARTIAL labels as current evidence. |

## 7. Tier-3 test and evidence landing

Both lanes touch authority/product-presentation seams and therefore require the
complete applicable D-032 `P/N/B/S/T/C/R/I/F/K/X` matrix from root
[`TESTING.md`](../../TESTING.md), explicit inapplicable rows, independent
module-boundary review and later cumulative real-path/human evidence.

### 7.1 P3-5B test destinations

| Destination | Required additions / preserved oracles |
|---|---|
| [`test_task_event_subscription.py`](../../tests/unit_tests/live_voice/test_task_event_subscription.py) | Store-owned prefix plus concurrent suffix, restart terminal prefix, frozen cursor, auth expiry, corruption, close-before-delivery and zero Task effects. Preserve existing durable replay facts. |
| [`test_task_progress_return.py`](../../tests/unit_tests/live_voice/test_task_progress_return.py) | Text and voice use the accepted exact replay source; ordinary progress, blocking question, decision-required and terminal event/result binding; stale generation/Attempt; sink failure; close race; Bridge zero Task/Executor/TTS/history effects. |
| [`test_progress_notification_arbiter.py`](../../tests/unit_tests/live_voice/test_progress_notification_arbiter.py) | Busy/unknown defer, exact candidate ACK, consumer failure retention, duplicate/gap/reorder, concurrent drain/ACK and no persistence-authority claim. |
| [`test_product_p3_text_adapter.py`](../../tests/unit_tests/live_voice/test_product_p3_text_adapter.py) | Exact authority before replay, cleanup fence, Store-prefix handoff for text, generation race, disconnect and no consumption on failure. |
| [`test_product_composition_registry.py`](../../tests/unit_tests/live_voice/test_product_composition_registry.py) | Correct active interaction, no-active unread retention and new response generation for progress/blocking/decision-required/terminal; completed result requirement and four other terminal outcomes; each class covers ACK/missing-ACK, crash-before-ACK, ACK-before/after-consumption failpoints, response loss, restart, two consumers/classes and zero Task cancel/mutation. |
| P3-5A Store/Core tests named by its accepted packet | Durable consumer identity/watermark, exact ACK replay/conflict, page gap, transaction failpoints, restart, concurrent ACK winner, retention and wrong consumer/task/scope isolation. P3-5B must not create a parallel file owner if P3-5A already names it. |
| [`productTextProgress.test.mjs`](../../jiuwenswarm/channels/web/frontend/tests/productTextProgress.test.mjs) | Strict parse, wrong scope/task/attempt, monotonic generation, retain every unacked delivery, reconnect retry, server response loss, close fence and no DOM/ACK on invalid input. |
| [`productP3ProgressGenerationJournal.test.mjs`](../../jiuwenswarm/channels/web/frontend/tests/productP3ProgressGenerationJournal.test.mjs) | High-water monotonicity and storage corruption remain hint-only; prove it cannot consume unread. |
| [`productWebActivation.test.mjs`](../../jiuwenswarm/channels/web/frontend/tests/productWebActivation.test.mjs) and [`liveVoiceIntegratedRoutePanel.test.mjs`](../../jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs) | Exact activation/close recovery, actual text adoption before ACK, truthful fallback, progress/blocking/decision-required/terminal labels, per-class missing-ACK and restart behavior, stale generation, refresh/reconnect and feature-off zero DOM/network. Final carrier/control claims remain P3-7. |

### 7.2 P3-6 test destinations

| Destination | Required additions / preserved oracles |
|---|---|
| [`test_voice_task_bridge.py`](../../tests/unit_tests/live_voice/test_voice_task_bridge.py) | All nine operation families; multi-Task ID/unique-name/zero/multiple candidates; clarification as new commit; exact spans; negation/ordinary dialogue/partial/low-confidence; no current/recency guess; no Bridge effect Ports. |
| [`test_formal_task_policy.py`](../../tests/unit_tests/live_voice/test_formal_task_policy.py) | Same closed authorization/state/capability/confirmation/result mapping for voice, natural text and structured text; wrong/stale/foreign/changed fingerprint zero effects. |
| [`test_p3_authenticated_composition.py`](../../tests/unit_tests/live_voice/test_p3_authenticated_composition.py) | Exact current context, Task set visibility, confirmation single-use/restart, accepted P3-2 operation mapping and result/event source truth. |
| [`test_product_composition_registry.py`](../../tests/unit_tests/live_voice/test_product_composition_registry.py) | Committed-origin acquisition/recovery, multi-Task target drift, clarification/confirmation separation, response loss/restart, two simultaneous Tasks, dialogue continuity and no Registry semantic authority. |
| [`formalTaskIntentRoute.test.mjs`](../../jiuwenswarm/channels/web/frontend/tests/formalTaskIntentRoute.test.mjs) | Generalized operation schema only after freeze; content-free recovery, clarification remount, exact scope/target/fingerprint, structured/natural equivalence and disconnect zero mutation. |
| P3-2/Core capability-owned tests | Canonical command result equality, accepted≠applied, unsupported capability, exact successor, provide-input ordering and races. P3-6 consumes these outcomes rather than duplicating Core tests. |

### 7.3 Multilingual golden corpus

The capability owner must declare supported languages and an accepted precision/
recall target before implementation. The current English/Chinese fixtures are
seeds, not proof of general product language. At minimum the corpus partitions:

- each operation, query subtype and supported disposition;
- explicit ID, stable user ref, unique name, duplicate name, no target and
  stale/foreign target across two or more visible Tasks;
- paraphrases and word-order variation, including Chinese updates without
  `把/将` and examples unrelated to the Demo itinerary;
- negation, correction, hypothetical/question forms, ordinary dialogue,
  partial/interim input, low confidence and adversarial Task-like text;
- clarification request, valid answer, changed Task set, abandoned answer and
  confirmation that tries to change operation/target/arguments; and
- voice-origin and natural-text-origin copies with the same expected canonical
  policy outcome, plus structured equivalents for every supported operation.

Corpus/fake success supports precision and safety only. It cannot replace one
real committed Speech path, real text path, Core/Executor operation, Runtime
notification or human-perceived journey where required.

### 7.4 D-032 scenario commitments and forbidden effects

- `P`: exact result/unread journeys and every declared operation succeed.
- `N/B`: malformed, over-bound, ambiguous, partial, unauthorized, foreign,
  negated and unknown-schema inputs fail closed.
- `S/T`: terminal immutability, frozen replay head, stale/late/duplicate/reordered
  events, generations, confirmations and target snapshots are fenced.
- `C`: concurrent ACKs, deliveries, clarifications, confirmations, target
  changes, terminal/control and two-Task operations linearize as contracted.
- `R`: reconnect, browser refresh, process restart, response loss, crash before
  ACK and transaction failpoints do not lose truth or duplicate mutation.
- `I`: subject/project/session/task/attempt/event/result/consumer/presentation
  class/response/generation/delivery identity remains exact.
- `F/K`: feature-off, unsupported capability, fallback, old structured queries
  and existing accepted consumers remain truthful and bounded.
- `X`: real Store, Web, voice Runtime, Agent/Tool and applicable Executor seams
  are exercised on the exact clean source; fake and historical counts get no
  product credit.

For every rejected, stale, unsupported, conflict, timeout, unknown, crash and
wrong-scope case, assert zero forbidden Agent, Tool, Task/Attempt/Command/Event/
Result-other-than-the-exact-authorized-consumer-ACK, Executor/scheduler, file/
artifact, network/external, audio/TTS, response/round cancel, conversation/
history, DOM and other-consumer/other-scope effects. A Store row count alone is
insufficient when an external Port may have been called.

## 8. Separate activation Gates

### 8.1 P3-5B Gate

Production P3-5B may start only when all are true:

1. The scoped P3-G0 foundation is accepted at G0_FINAL and P3-1 is accepted at
   `d40e0ee3` on the exact integration lineage; this prerequisite is satisfied.
2. P3-5A is accepted with exact Result/Event/cursor/unread/consumer schema,
   migration, transaction, retention, Port and focused Tier-3 evidence.
3. The consumer identity, cross-class suppression rule, watermark/gap semantics,
   text adoption ACK, audio PresentationAck and crash-before-ACK contract in §3
   are accepted or deliberately replaced.
4. The Integration Owner assigns non-overlapping Runtime/Web files and the one
   presentation-generation/ACK owner; shared composition remains serialized.
5. Target code is re-audited for the G0 prepared-source changes and any P3-5A
   API/schema drift before a patch is written.

P3-5B closes only after focused/affected tests, independent Tier-3 review,
restart/reconnect/failpoint evidence and real Runtime/Web voice/text presentation
pass on one exact clean source. It alone does not complete the P3-5 package if
P3-5A or cumulative carrier evidence is open.

### 8.2 P3-6 Gate

Production P3-6 may start only when all are true:

1. The scoped P3-G0 foundation is accepted at G0_FINAL and P3-1 is accepted at
   `d40e0ee3` on the exact integration lineage; this prerequisite is satisfied.
2. P3-2 is accepted with exact operation names/payloads, state/capability rules,
   result dispositions, `provide_input`, pause/resume/reprioritize and terminal
   successor decisions.
3. P3-5A's result/event contract is accepted, so status/result speech and text
   cannot be sourced from dialogue or files.
4. Supported languages, corpus partitions, precision/recall thresholds, stable
   user-facing Task references, authorized visibility rules and confirmation
   policy are frozen; clarification handle owner, identity fields, capacity/TTL,
   single-use/replay rule and durable-reopen-versus-expire-on-restart policy are
   frozen with focused evidence destinations.
5. The Integration Owner assigns Bridge/corpus ownership and one central owner
   for Registry/composition/wire/frontend integration collisions.

P3-6 closes only when every declared natural operation matches its structured
canonical result, the corpus threshold passes, zero-effect negatives and races
pass, independent Tier-3 review is clean, and real voice/text multi-Task seams
work. The final Integrated Web experience remains P3-7.

## 9. Re-review triggers and decisions still required

Re-open the affected section and historical asset mapping before implementation
or integration if any of the following changes:

- P3-5A consumer key, presentation classes, cursor/watermark, event/result
  retention, terminal settlement, schema version/migration or consumption Port;
- canonical Task states, paused/recovery representation, successor/retry/result
  lineage, P3-2 operation payload or disposition;
- Runtime `ResponseRef`, generation, presentation ledger, TTS/playout ACK,
  barge-in, active-interaction or history policy;
- Bridge resolver Port, supported languages/model/provider, Task visibility/
  naming/ref policy, confirmation owner or committed-input ledger;
- shared Registry/AgentServer/product profile/wire/Panel files touched by P3-4,
  P3-7, P3-8A or later candidate work;
- cherry-pick/rebase conflicts, a different P3-1/P3-5A ancestor, or historical
  schema/product patches proposed for direct integration; or
- any new classifier, product policy, authority owner, persistence record,
  external effect or broader language/operation claim beyond this packet.

Key activation decisions are therefore: stable consumer identity and device/
profile sharing; presentation-class suppression; watermark gap/retention rules;
the exact Web consumption point; audio ACK meaning; supported languages and
corpus thresholds; multi-Task display/name/reference policy; per-operation
confirmation; clarification owner/identity/bounds/replay/restart semantics; and
the unresolved P3-2 capability/state decisions.

## 10. Explicit non-claims

This document adds no production source, test, schema, migration, Runtime/Web
delivery, consumer, Bridge, NLU, command, UI or telemetry behaviour. The
committed G0_FINAL/P3-1 facts, 57 historical assets and every proposed matrix
row are preparation inputs only. No historical test count, fake, strict parser,
checkpoint, review or acceptance label transfers to this packet's product
evidence.

Consequently this preparation does not alter the already recorded scoped P3-G0
or accepted P3-1 credit and grants **no P3-2, P3-5A, P3-5B, P3-5, P3-6, P3-7,
complete-P3, feature-complete, product-readiness, RC or Production credit**.
STATUS may change only after the owning implementation, migration, tests,
independent review and required real/human evidence pass on one exact clean
integrated source.
