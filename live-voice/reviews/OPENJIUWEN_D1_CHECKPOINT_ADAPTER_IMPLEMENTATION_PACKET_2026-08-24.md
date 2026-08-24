# OpenJiuwen D1 checkpoint adapter implementation packet — 2026-08-24

Status: closed local implementation packet. This packet maps the existing
LiveVoice `D1Checkpoint` codec into the public AgentCore checkpoint publication
seam. It remains uncomposed and does not replace the legacy durability runtime,
admit recovery or launch an Executor.

## 1. Capability and risk

- Capability: `P3-4` / `OJ-D1-CHECKPOINT-ADAPTER`, isolated publication and
  current-reference read slice.
- Risk: Tier 3. The boundary stores durability payload bytes and publishes the
  sole AgentCore Task/execution reference under an exact owner token.
- Dependency: clean local AgentCore candidate
  `503cf538fd7403d0919e53b53f857fa68d624f31`, which closes S28/F86 and the
  bound-handle S32/F90 seam. A later descendant requires affected revalidation.
- Default state: off and uncomposed. Importing this module, constructing the
  existing production registry or running the legacy path does not create or
  inspect an OpenJiuwen payload store.

## 2. Intended behaviour

1. One adapter freezes an authenticated product `ScopeRef`, validates the exact
   public AgentCore handle binding derived by the existing G1 facade, and builds
   the public `ExecutionCheckpointCoordinator` over that same handle plus one
   injected immutable payload store.
2. Publication accepts an existing complete `D1Checkpoint` and an explicit
   producer fence: Task/execution, profile digest, generation, owner ID/epoch,
   execution version and expected outer checkpoint head. The embedded scope,
   Task, producer Attempt/execution, profile digest and generation must match.
3. AgentCore publication sequence is an outer, one-based contiguous sequence
   supplied as `expected_checkpoint_head + 1`. It is deliberately independent
   from the embedded LiveVoice checkpoint sequence, which remains opaque
   provenance and may start at zero or have its own prefix policy.
4. The outer checkpoint ID is a domain-separated deterministic digest over the
   exact AgentCore session/team/Task/execution and embedded checkpoint ID. It is
   stable across response-loss retry, globally separated inside a shared
   payload-store namespace, and does not include payload bytes; changing bytes
   under the same embedded identity therefore conflicts instead of rebinding.
5. The immutable file store derives every path from the outer ID, never from a
   caller locator. `put` is exact-idempotent and concurrent-safe: same ID/bytes
   returns the same stable non-credential locator, while same ID/different bytes
   rejects. `get` re-derives the path and verifies ID, locator, size and SHA-256.
6. The existing D1 canonical bytes are the opaque payload. Final wire bytes
   above AgentCore's 1 MiB limit reject before payload-store access. No silent
   compression, truncation or expansion of the AgentCore bound is introduced.
7. Current load uses a bounded stable before/load/after authority snapshot. It
   returns `None` only for a stable absent current reference. A present
   reference with missing/corrupt payload is a stable fail-closed error. Loaded
   bytes must pass `D1Checkpoint.from_bytes()` and exact outer/embedded scope,
   Task, execution, profile, generation, schema and digest checks.
8. AgentCore rejection may leave one S28 authority-free payload orphan because
   the coordinator is payload-first. It must leave Task fields, checkpoint head,
   reference, Task event, dispatch, Agent/Tool, file/project effect,
   audio/history, legacy Task Store and other scope unchanged.

## 3. Owned surfaces

- New `openjiuwen_d1_checkpoint_adapter.py`: structural public-handle and
  coordinator ports, producer/read values, D1 publication/load projection,
  deterministic outer identity and immutable file payload store.
- Focused unit tests and one opt-in exact-clean-candidate integration test.
- This packet only. Protected local `STATUS.md`, migration map and `.codex_tmp`
  changes remain untouched.

No AgentCore source/schema/DAO/Manager change belongs to this packet. No
existing LiveVoice Store, checkpoint codec, executor or composition is edited.

## 4. Tier-3 acceptance

- `P`: native D1 sequence zero and outer sequence one publish through the real
  public coordinator/handle, load back exact canonical bytes, and project one
  exact AgentCore reference/event; later outer publications remain contiguous.
- `N`: wrong scope/Task/execution/profile/generation/owner/version/head,
  incomplete or D2 profile, malformed result/receipt/snapshot and corrupt bytes
  reject with zero authoritative or product side effects. Payload-first
  rejection may leave only the declared authority-free orphan.
- `B`: identifiers, Unicode/NUL, signed-bigint, schema version, locator, empty
  payload and 1 MiB wire boundaries are explicit; booleans are not integers.
- `S`: only current `owned` execution can create a fresh reference. Current
  `owned` or `recoverable` may be read under the exact current version; terminal,
  reset, deleted and absent references do not mint resume authority.
- `T`: stale producer fences fail; delayed exact retry preserves the original
  outer ID/sequence and returns replay rather than advancing again.
- `C`: concurrent same-ID same-bytes store writes converge; changed bytes
  conflict; distinct checkpoint publications at the same head have one winner.
- `R`: file-store reopen preserves bytes; commit-before-return retry returns the
  AgentCore exact replay; store write before Task rejection is truthfully an
  orphan, not a published checkpoint; missing/corrupt payload fails closed.
- `I`: two scopes/sessions/teams/Tasks/executions cannot cross-load, publish or
  collide in a shared store. Handle drift and foreign ambient session reject.
- `F`: this module is not selected by the production registry. Dependency
  failure has no legacy fallback or dual write, and cancellation propagates.
- `K`: existing D1 codec/readers, facade/query owner, registry and legacy
  durability tests remain unchanged; repository imports do not require the
  optional AgentCore candidate.
- `X`: an opt-in test imports the exact clean candidate from its verified source
  path and crosses real file-backed AgentCore SQLite, public TeamAgent bound
  authority, public coordinator and the new file payload store without a fake
  at the AgentCore boundary.

## 5. Closure evidence

- Focused adapter tests: `29 passed`.
- D1 and legacy durability affected set: `87 passed`.
- Existing facade/query/default-off affected set: `88 passed`.
- Exact candidate integration: `3 passed` against clean AgentCore
  `503cf538fd7403d0919e53b53f857fa68d624f31` imported from
  `C:\Users\admin\Desktop\openjiuwen\agent-core-oj-g2-local-base`. This set
  crosses real file-backed SQLite, public TeamAgent lifecycle/authority and the
  immutable file payload store; the D1 case covers response-loss replay,
  owner/version rejection, outer sequences one through three, a distinct-ID
  same-head race, reopen, terminal current-read absence and two real isolated
  scopes sharing one store.
- Static closure: scoped Ruff, Ruff import order, Ruff format check, Python
  compile and Git diff checks passed.
- Independent Tier-3 read-only review: Critical `0`, Important `0`, Moderate
  `0`, Low `0`. The review independently reran all `29` focused tests and the
  exact D1 candidate integration.

The repository-owned test commands used `pytest -o addopts='' -p
no:cacheprovider`. The opt-in integration additionally set
`OPENJIUWEN_AGENTCORE_CANDIDATE_PATH`,
`OPENJIUWEN_AGENTCORE_CANDIDATE_SHA` and `PYTHONPATH` to the exact clean
candidate above; the test itself rejected a dirty or differently imported
candidate before awarding evidence.

## 6. Explicit exclusions

- No production registry/composition selection, feature-mode cutover, canary,
  rollback window, dependency-lock change, remote update or deployment.
- No call to `SqliteTaskStore.append_durability_checkpoint`, no wrapper around
  the legacy Store and no dual-write/shadow/mirror path.
- No recovery admission or launch. D-089 requires a linked/new Attempt, while
  the current public AgentCore checkpoint seam reads only the current execution;
  that lineage policy and API require a later explicit packet.
- No D2 effect-prefix verification, compensation/retry policy, payload GC,
  retention, encryption, key rotation or credentials. Embedded `effect_head`
  and `effect_prefix_digest` remain product-owned opaque D1 facts.
- No host-power-loss or kernel-crash durability claim for the local file-store
  directory entry. This slice proves file fsync followed by atomic hard-link,
  process-concurrent exactness, process response-loss retry and normal reopen;
  a later platform storage packet must own directory-flush policy and evidence.
- No PostgreSQL/MySQL service execution, physical Provider, project/file effect,
  browser/audio device or human product acceptance claim.
- The injected payload root is an access-controlled local platform resource;
  hostile out-of-band symlink or junction mutation is not hardened in this
  file-store slice.

These exclusions keep the slice reversible and prevent payload publication from
being misreported as recoverability, Executor runtime truth or production
retirement.
