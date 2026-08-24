# OpenJiuwen G1 isolated facade implementation packet — 2026-08-24

Status: closed local implementation packet for the isolated facade slice. This
packet creates and verifies an isolated JiuwenSwarm adapter over the local
AgentCore candidate. It does not switch production callers, import legacy data,
enable dual writes, update a remote ref, or authorize cutover.

## 1. Capability and risk

- Capability: `COMP-01` / `OJ-G1-FACADE`, isolated facade slice.
- Risk: Tier 3. The changed boundary translates authenticated product scope to
  canonical Task, event, result and consumer-cursor authority, and rejects
  product commands before downstream authority until their inputs are fully
  bound.
- Candidate dependency: local AgentCore `codex/oj-g2-local-base` at
  `a514fe06` (S31/F89 production, tests and documentation) or an explicitly
  revalidated descendant preserving the same contracts.
- Product authority input: one fresh `ResolvedProductAuthority`; browser fields,
  bearer values and client-supplied scope are never accepted as grants.

## 2. Intended behaviour

1. A domain/version-separated digest maps the exact authenticated
   subject/project/session tuple to one AgentCore physical session, team and
   member identity. The facade is pinned to that mapping when it is constructed.
2. Durable presentation consumer identity is derived from subject plus project.
   The Task remains the AgentCore stream and `text`/`voice` remain separate
   channels; response IDs and generation IDs are not cursor identity.
3. Every call revalidates authority type, assurance, expiry, exact operation,
   capability, scope and targeted Task resource before calling AgentCore.
4. Task reads return immutable JiuwenSwarm projections of canonical AgentCore
   Task/execution/result facts. They neither mint launch/call/resume authority
   nor infer a product display state.
5. Ordered events and unread pages retain AgentCore event identity, sequence,
   payload JSON and payload digest. Cursor advance uses the exact acknowledged
   event facts and the AgentCore CAS result.
6. Although S31/F89 now provides an event-head CAS for generic AgentCore
   updates, the current product confirmation fact does not bind the first raw
   `title/content` patch. This isolated facade therefore fails `task.update`
   closed before AgentCore. Enabling it requires a separately scoped
   server-owned PreparedUpdate/origin binding; mixing the confirmation digest
   into a new request digest is not accepted as proof of user confirmation.
7. Product operations without a fully bound generic AgentCore command contract
   (`task.update`, `task.cancel`, `task.retry`, `task.adjust`,
   `task.reprioritize`, `task.create_successor`, and Task creation in this
   slice) fail closed. They never fall back to `SqliteTaskStore`.
8. The facade owns no database, Task row, execution token, result bytes, event,
   cursor, cache, background worker, Agent, Tool or filesystem effect.

## 3. Owned surfaces

- Production: one new import-safe LiveVoice facade module using structural
  protocols, so the repository's currently locked OpenJiuwen release can still
  import without pretending to contain the candidate APIs.
- Tests: Tier-3 unit oracles with a recording fake, plus an opt-in integration
  run against the exact local AgentCore candidate and real SQLite tables.
- Documentation: this packet and the later closure record. Protected user edits
  in `live-voice/STATUS.md` and the symbol migration map are not changed.

## 4. Acceptance matrix

- `P`: exact authorized get/list/events/result/unread/advance paths work; text
  and voice cursors are independent.
- `N`: wrong operation, capability, scope, Task resource, team/member binding,
  expired authority, malformed record and unsupported product command fail
  closed with zero downstream calls. Canonical AgentCore negative-command
  decisions belong to the later PreparedUpdate packet and are not credited by
  this command-free slice.
- `B`: product scope inputs retain their 256-character product bound;
  AgentCore-facing identifiers use its 255-character bound, Task text uses
  65,535 characters, result locators use 2,048 characters, and canonical event
  JSON uses a 16-KiB UTF-8 bound. Digests, limits, versions, event sequences and
  timestamps are bounded; booleans are not accepted as integers.
- `S/T`: a stable Task/execution snapshot is required; terminal outcome/result
  remain immutable projections; event order and cursor frozen-head facts are
  preserved without inventing product state.
- `C`: concurrent stable Task/list-set reads and independent cursor channels
  preserve AgentCore's transaction result. The facade contains no mutable
  shared cache.
- `R`: commit-before-return cursor retry returns the AgentCore replay;
  restart/reopen uses only AgentCore rows.
- `I`: product scopes, teams, Tasks, consumers, channels and candidate sessions
  cannot cross-bind, including case-sensitive raw identity checks.
- `F`: dependency absence, candidate mismatch, downstream exceptions and
  corrupt projections never report success and never invoke a legacy Store.
- `K/X`: existing LiveVoice imports remain compatible with the locked
  dependency; an opt-in real SQLite candidate path proves public TeamAgent
  construction and API shape, and rejects evidence unless the actual imported
  `openjiuwen` package is under the exact Git candidate root and that candidate
  worktree is clean. Real Agent/Tool and presentation-receipt wiring belong to
  the next packet.

Every pre-validation rejection that could otherwise mutate must assert zero
downstream call and zero Task/command/event/cursor/Agent/Tool/file/audio/history/
legacy-Store effect. No product mutation reaches AgentCore in this slice.

## 5. Explicit exclusions

- No production registry/composition route switch and no replacement of
  `SqliteTaskStore` in this packet.
- No legacy database import, shadow write, dual write, canary, rollback window,
  old-schema retirement or physical deletion.
- No real Agent/Tool launch, cancellation/quiescence chain, project worktree,
  D1 payload codec/store, D2 product effect adapter, DOM adoption or voice
  playout receipt integration.
- No product update patch, new generic AgentCore command kind or product-policy
  vocabulary. PreparedUpdate/confirmation content binding is routed to the
  next product-adapter packet.
- No PostgreSQL/MySQL service run, remote update, public deployment, dependency
  lock change or credential/configuration change.

These exclusions keep the facade an isolated conformance boundary. Production
cutover remains blocked until the retained product composition and real
Agent/Tool/presentation adapters use it exclusively and a separately authorized
quiesced import/canary/rollback packet succeeds.

## 6. Closure evidence

- Focused facade unit matrix: `16 passed`.
- Affected product-authority, text-query, presentation-ACK and result-consumer
  matrix: `193 passed`.
- Opt-in real candidate integration: `1 passed` against clean AgentCore
  `a514fe063bcd36e213f3e326cc9e598d2c481c34`, using public `TeamAgent`,
  file-backed SQLite, exact event/cursor facts, response loss after durable
  cursor commit, same-ID replay and close/reopen replay. The imported package
  resolved under the clean candidate root at
  `agent-core-oj-g2-local-base/openjiuwen/__init__.py`; the machine-private
  absolute root is intentionally not retained in source documentation.
- The repository-locked dependency imports the structural facade and skips the
  opt-in candidate test when the exact path/SHA request is absent.
- Scoped Ruff, import sorting, formatting, Python compilation and
  `git diff --check` passed.
- Independent read-only Tier-3 review closed at `C0 / I0 / M0 / L0` after the
  event JSON, candidate identity, response-loss replay, Unicode/length and dead
  command-code findings were repaired.

An exploratory complete `tests/unit_tests/live_voice` run was not a green
release suite: overriding repository addopts disabled automatic asyncio handling
and produced 26 spurious unmarked-async failures; the same conversation-runtime
file subsequently passed `35/35` with `--asyncio-mode=auto`. Seven unchanged
pre-existing registry/progress tests still reproduce independently and are not
credited to or repaired by this isolated facade packet. They concern legacy P3
projection/retry fixtures, not this new module or its candidate integration.

No real Agent/Tool dispatch, product presentation receipt, PreparedUpdate,
production composition route or physical cutover receives credit from this
closure. Protected local edits in `live-voice/STATUS.md`, the untracked symbol
migration map and `.codex_tmp/` remained outside this packet.
