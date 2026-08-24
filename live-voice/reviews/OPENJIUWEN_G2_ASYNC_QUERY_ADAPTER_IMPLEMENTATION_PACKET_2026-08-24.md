# OpenJiuwen G2 async query adapter implementation packet — 2026-08-24

Status: closed local implementation packet. This packet connects the existing
authority-first product query adapter to the isolated OpenJiuwen Task facade
through an explicitly asynchronous, read-only owner. It does not select that
owner in the production registry or claim compatibility with the legacy Task
Core projection.

## 1. Capability and risk

- Capability: `COMP-04` / `OJ-G2-ASYNC-QUERY`, isolated read adapter slice.
- Risk: Tier 3. The changed seam carries authenticated Task read authority
  across an async boundary and projects canonical AgentCore facts into a
  product `ResultEnvelope`.
- Dependency: closed `OJ-G1-FACADE` at LiveVoice commit `9c820fe1`, backed by
  clean local AgentCore candidate `a514fe06` or an explicitly revalidated
  descendant preserving S31/F89.
- Default state: off and uncomposed. Existing production construction retains
  the synchronous legacy owner and its worker-thread invocation.

## 2. Intended behaviour

1. `ProductP3TextAdapter` accepts exactly one query owner mode: the existing
   synchronous owner or a new asynchronous owner. The sync path remains off
   the event loop; the async path is awaited directly and propagates caller
   cancellation.
2. `OpenJiuwenProductP3QueryOwner` accepts only a structurally complete
   `ProductP3AuthorizedQuery`. It revalidates the exact Query envelope,
   authenticated product authority and Task authorization grant before calling
   the bound facade.
3. Positive operations are read-only `task.get`, `task.status`, `task.events`,
   `task.result`, and bounded `task.list` without a continuation cursor.
   Missing Tasks on `get/status/result` return a stable `NOT_FOUND` result.
   Missing/corrupt event streams remain a redacted dependency failure because
   the public G1 event seam does not expose a distinguishable missing-stream
   fact. A non-empty list cursor or unsupported direct-owner operation returns
   a stable failure without a facade call; the outer product adapter rejects
   unsupported operations before allocating the owner.
4. Results use the explicit projection identifier
   `openjiuwen.agentcore.task-query.v1`. They contain only facts owned by the
   facade: Task, execution, result-reference and canonical event facts. They do
   not invent legacy `spec`, `attempt`, `admission`, retry-readiness, display
   state, runtime-start proof or result bytes.
5. A bounded list reports its requested limit, returned count and whether the
   boundary was reached. It does not claim `has_more` because the current
   public AgentCore list seam has no frozen continuation token.
6. Downstream corruption, scope drift, authority expiry, dependency failure or
   a malformed result fails closed. No fallback call reaches the legacy Task
   Store, Agent, Tool, file/project effect, audio/history or another scope.

## 3. Owned surfaces

- `product_p3_text_adapter.py`: additive async-owner protocol and exact-one
  invocation mode; no default registry change.
- `openjiuwen_product_query_adapter.py`: versioned read-only query owner.
- `openjiuwen_task_facade.py`: additive `task.status` read using the same
  canonical snapshot projection as `task.get`.
- Focused unit and exact-candidate integration tests.
- This packet only. Protected local `STATUS.md`, migration-map and `.codex_tmp`
  changes remain untouched.

## 4. Tier-3 acceptance

- `P`: each supported operation returns one canonical, JSON-safe versioned
  result through the directly awaited owner; the existing sync owner still
  works unchanged.
- `N/F`: wrong scope/operation/target/capability/grant, missing Task, malformed
  payload, list cursor, facade error and malformed owner return fail closed;
  prevalidation failures make zero facade/legacy/Agent/Tool/effect calls.
- `B`: query identifiers, paging values and returned collections retain their
  existing bounds; booleans are not integers; list never scans beyond the
  facade's 100-item cap and event reads retain the 500-item cap.
- `S/T`: Task/execution/result/event facts are copied exactly; no lifecycle or
  presentation state is inferred and event order/head remain unchanged.
- `C`: async calls do not share mutable adapter state; caller cancellation is
  not converted to a success/failure envelope; sync calls remain off-loop.
- `R`: the adapter owns no durability. Closed G1 candidate evidence owns
  AgentCore reopen/response-loss semantics; T8a does not take new durability
  credit for its stateless owner.
- `I`: two product scopes/AgentCore bindings cannot cross-use an owner or
  authority; list collection authority cannot carry a Task resource.
- `K`: all existing sync callers and repository-locked imports remain
  compatible; no registry constructor changes are required.
- `X`: an opt-in exact-clean-candidate test crosses real
  `ProductP3TextAdapter -> async owner -> facade -> public TeamAgent authority ->
  file-backed SQLite` without a fake at the AgentCore boundary.

Independent read-only review is required before closure. Positive tests alone
do not close the packet; every negative path with mutation potential must also
assert the forbidden effects remain zero.

## 5. Explicit exclusions

- No production registry/composition switch, feature-mode selector, canary,
  rollback window, dependency-lock change, remote update or deployment.
- No legacy result-shape compatibility claim and no consumer/UI/voice renderer
  migration. The versioned AgentCore projection requires a later explicit
  presentation adapter.
- No mutation, PreparedUpdate, Task creation, scheduling, Agent/Tool launch,
  subscription/progress stream, presentation ACK, checkpoint payload, effect
  adapter, legacy import or physical Store retirement.
- No PostgreSQL/MySQL service execution and no credentials/provider changes.

These exclusions keep this packet independently reversible and prevent an
async integration seam from silently becoming a production cutover.

## 6. Closure evidence

- Focused async-owner, facade and versioned-projection matrix: `77 passed`.
- Affected product authority, query, presentation, registry-construction and
  exact-negative matrix: `151 passed`.
- Exact clean AgentCore candidate integration: `2 passed` against
  `a514fe063bcd36e213f3e326cc9e598d2c481c34`. The new X case crosses
  `ProductP3TextAdapter -> OpenJiuwenProductP3QueryOwner -> facade -> public
  TeamAgent authority -> file-backed SQLite`; text/voice effects remain zero
  and no legacy Task Store file is created.
- Independent read-only Tier-3 review closed at `C0 / I0 / M0 / L0` after
  exact-grant capability/expiry equality, pre-facade scope/resource binding,
  missing-event wording, list cursor/error classification and import-order
  findings were repaired.
- Scoped Ruff, Ruff import sorting, Ruff formatting, Python compilation and
  `git diff --check` passed. The repository-locked dependency imports the new
  modules without the optional AgentCore candidate.

The independent compatibility run over the complete product registry plus
retirement manifest produced `186 passed / 6 failed`. The six failures exactly
match the already disclosed inherited P3 projection/fixture failures (bounded
list/events/result, two retry-admission status cases, disconnect cleanup,
stop/in-flight query and natural-text status grouped by the existing tests);
none imports or selects this default-off owner. They remain exclusions and are
not presented as a green broad-suite result.

Residuals are explicit: only `task.status` received the new full async X path;
the other operation branches rely on focused owner/facade tests plus closed G1
candidate evidence. The owner has no persistence, production composition is
unchanged, and legacy result-shape/UI/voice, canary/cutover, PostgreSQL/MySQL,
Agent/Tool execution and physical audio remain outside this packet.
