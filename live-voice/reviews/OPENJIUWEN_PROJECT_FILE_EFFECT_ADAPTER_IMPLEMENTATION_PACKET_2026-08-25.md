# OpenJiuwen Project/File Effect Adapter Implementation Packet

## Status and scope

- Date: 2026-08-25
- Capability: OJ-G1 / D2-02 / EXE-06 isolated project-file effect Adapter
- Risk: Tier 3 — an AgentCore continuation can authorize a real Git/file
  mutation, and recovery must distinguish applied, not-applied and ambiguous
  outcomes without retrying silently.
- AgentCore dependency: exact committed local candidate
  `db8216839562de36fa24fd6f5ce807acea5a132a`, including S_29 and S_33.
- LiveVoice baseline: `0228b738d8a9cba7d87d5960da387745cb19ab31`.
- Mode: additive, default-off and uncomposed. It grants no cutover, migration,
  deletion or product-readiness credit.

## Intended behaviour

Add one coordinator-owning LiveVoice Adapter that accepts an immutable,
server-prepared project-effect plan plus an AgentCore call or observation
authorization. It verifies exact product scope, AgentCore binding, effect
identity, patch/project state and attempt identity, then delegates the
authorization to the root-public `ExternalEffectCoordinator`. Only the
coordinator may invoke the private Adapter Port.

For a valid fresh call authorization, the Adapter acquires an injected narrow
project ownership Port, revalidates the exact disposable Git root,
head/tree/support baseline, and calls the retained `_apply_attempt_patch`. The
isolated candidate injects the existing cross-process `_AttemptOwnershipLock`.
Future production composition must hand off the lock already held by the
worker; a second acquisition in that path would self-reject and is explicitly
outside this packet. A synchronous successful return produces one stable
AgentCore `ACCEPTED` transport receipt. It does not claim that a receipt alone
proves the effect was applied.

For a valid observation authorization, the Adapter acquires the same attempt
lock and reports:

- `OBSERVED` when the expected project state is present;
- `NOT_OBSERVED` with `call_quiesced=True` only when the exact before-state is
  still present while the ownership lock is held;
- `AMBIGUOUS` otherwise.

If the lock is already held, the project root is unsafe, the plan/binding is
malformed, or inspection/application raises, the operation fails closed. It
does not invent `NOT_SENT`, `NOT_OBSERVED`, a receipt or settlement.

## Owned surfaces

- Production:
  `jiuwenswarm/server/live_voice/openjiuwen_project_file_effect_adapter.py`
- Unit tests:
  `tests/unit_tests/live_voice/test_openjiuwen_project_file_effect_adapter.py`
- Exact-candidate integration:
  `tests/integration/live_voice/test_openjiuwen_project_file_effect_candidate.py`
- This packet.

No registry, product composition, legacy journal, Task Store, executor
lifecycle or current project-code path is modified.

## Frozen plan and mapping

The authority-free plan freezes:

- authenticated `ScopeRef` and its derived AgentCore session/team/member;
- Task ID, execution/attempt ID, profile digest and generation;
- effect ID, `project.apply_patch`, operation/dispatch ordinal, provider key,
  target digest, intended-effect digest and replay policy `never`;
- project source/stable ID/URI and canonical Git root;
- patch bytes/digest, expected project state, before head/tree/content and the
  exact protected-support fingerprint tuple.

The isolated target digest is domain-separated and binds both the logical
project facts and a hash-derived canonical physical Git-root key. Only the
digest reaches AgentCore; the path is not persisted there. This intentionally
differs from the legacy logical-only target digest, so one continuation cannot
be moved to another checkout with identical bytes. Legacy identity import is a
later migration decision and receives no credit here.

The isolated intended-effect digest is also domain-separated. In addition to
the patch and expected state it binds the exact before head/tree/content and
protected-support fingerprints. A continuation therefore cannot be paired
with altered preconditions even when its patch bytes are unchanged.

Initial isolated mapping fixes `execution_id == attempt_id`, generation `0`,
operation ordinal `1`, dispatch ordinal `1`, provider key equal to effect ID,
and replay policy `never`. The Adapter recomputes target and intended digests
from the frozen product facts. It does not mint an effect identity, claim,
continuation, observation authority or settlement authority.

The patch is bounded to 1 MiB for this isolated Adapter. This is a safety bound
on the new default-off surface, not a change to the current production
executor. Identifiers use the AgentCore 255-character boundary; paths use a
4096-character boundary; signed integers and SHA-256 values are type-exact.

## Required fail-closed behaviour

The following produce zero file/Tool/Task/audio/history/legacy-effect/other-
scope mutation:

- missing, foreign or drifted handle session/team/member binding;
- wrong scope, task, execution, profile, generation, effect, operation,
  ordinal, provider key, target/intended digest or replay policy;
- malformed, stale, expired, wrong-phase or second-use authorization;
- treating an authority-free fact/prefix/reconciliation decision as an
  authorization;
- missing/corrupt/changed plan, non-canonical root, unsafe link, non-Git root,
  wrong head/tree/content/support baseline, malformed patch or patch bound
  violation;
- inability to acquire the exact attempt ownership lock;

This zero-file guarantee applies through coordinator rejection and before the
private Port starts the call. Once AgentCore has consumed a call authorization
and the owned apply thread starts, cancellation is delayed until that thread
quiesces and the lock remains held, but response loss, apply attribution
failure or evidence-factory failure may still leave an applied or ambiguous
project. Those paths return no fabricated receipt/observation and require the
recorded dispatch to be reconciled. Probe exceptions likewise return no
fabricated observation.

The Adapter revalidates canonical root/ancestor safety and exact Git-root
identity after ownership acquisition, immediately before each blocking
apply/probe. The ownership Port and composition must control cooperative
writers and provide a non-adversarial project root; hostile out-of-band
directory replacement after that revalidation requires stable directory-handle
hardening and is outside this isolated slice.

The Adapter never writes the LiveVoice durability effect rows and never falls
back to `_prepare_d2_project_effect`, `_append_effect`,
`_settle_d2_project_effect` or another direct file call.

## Tier-3 acceptance matrix

| Dimension | Required evidence |
|---|---|
| P | Exact clean AgentCore candidate, file-backed SQLite, real bound effect handle, real coordinator, disposable no-remote Git root and OS ownership lock prove (1) synchronous dispatch/receipt/observation/settlement and (2) a separate response-loss/reconciliation observation path, each with at most one file mutation. |
| N | Every foreign/stale/forged/fact-as-authority/project-drift path is rejected with explicit zero file, Agent/Tool, Task, audio/history and legacy journal effects. |
| B | Empty/NUL/surrogate and 255/256 identifier bounds, signed-bigint/bool, digest, URI 2048/2049, support tuple and patch 1 MiB are explicit. A real canonical root is positive and a path over 4096 is rejected; this Windows slice does not claim that an artificial 4096-character path can exist. |
| S | Planned/claimed/dispatch-possible/observed/settled remain AgentCore-owned; the Adapter reports project evidence only and cannot revive a terminal effect. |
| T | Pre-call, post-authorize/pre-file, post-file/pre-receipt and delayed observation remain truthful; no ACK/receipt is treated as applied. |
| C | Concurrent use of one call authorization performs at most one file call; the attempt OS lock prevents two project mutations. |
| R | Response loss after file application is recovered by an `OBSERVED` probe without a second call; exact before-state yields only quiesced `NOT_OBSERVED`; drift yields `AMBIGUOUS`. |
| I | Two scopes/teams/executions/effects and two project roots cannot cross-bind even with colliding local IDs. |
| F | Module import and ordinary production remain feature-off with zero allocation; exceptions return no fabricated evidence and there is no legacy fallback/dual write. |
| K | Existing D1/G1/query adapters, project executor and legacy D2 tests remain unchanged and pass affected regression. |
| X | The positive path uses the exact clean AgentCore commit, public `TeamAgent.effect_authority`, real SQLite, real coordinator, real Git subprocesses, real patch application and real OS lock. Fakes receive no X credit. |

## Explicit exclusions and later decisions

- No production registry/composition enablement and no replacement of the two
  current raw `_apply_attempt_patch` paths.
- No import/quiesce/delete of LiveVoice effect rows and no raw-client
  no-bypass or retirement credit.
- No compatibility mapping from the legacy logical-only project target digest
  to the new root-bound isolated identity.
- No automatic retry, compensation policy, linked/new Attempt recovery,
  Task/execution settlement, cleanup acknowledgement or D1↔D2 recovery anchor.
- Claimant identity is deliberately not part of the immutable effect plan.
  AgentCore binds the current call/recovery actor, purpose, token, version,
  lease and global prefix at the coordinator boundary; a valid recovery actor
  may differ from the original runtime claimant.
- D2 profile eligibility is a trusted composition precondition in this slice.
  The Adapter binds the exact profile digest from the AgentCore authorization
  but does not classify durability levels; production composition must only
  prepare this plan under the selected D2 profile.
- Production handoff of the worker's already-held project ownership lease is a
  later composition seam. The isolated candidate uses a fresh real lock and
  does not modify the current worker lifecycle.
- Restart reconstruction of exact patch/expected-state is not solved here.
  This isolated packet accepts a server-prepared immutable plan. Cutover must
  separately choose a product payload store or explicit D2 recovery anchor;
  generic AgentCore facts intentionally store only digests.
- No PostgreSQL/MySQL, physical Provider/audio, production authentication or
  human product acceptance.

## Closure evidence

- Focused Adapter unit suite: `37 passed`.
- Exact clean AgentCore `db8216839562de36fa24fd6f5ce807acea5a132a`
  integration: `1 passed`, using public `TeamAgent.effect_authority`, real
  file-backed SQLite, disposable Git roots, real apply and OS ownership lock.
- Affected project executor, legacy D2, recovery/readers, D1, G1 facade and
  new Adapter regression: `236 passed, 2 skipped`; the skips are the existing
  platform-conditioned symlink cases.
- Scoped Ruff default/import ordering/format, AST parse and diff check: pass.
- Independent Tier-3 read-only review: `Critical 0 / Important 0 / Moderate 0 /
  Low 0` after closing cancellation/lock, observation authority, unsafe-link,
  physical-root and boundary findings.
