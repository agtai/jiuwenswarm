# AgentCore PR 10: bound external-effect authority implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Expose a least-privilege, lifecycle-bound public orchestration seam
for the generic external-effect journal without exporting live continuation
tokens, raw evidence writers or arbitrary per-call Adapter injection.

**Architecture:** `TeamAgent.effect_authority` is an explicit sub-capability of
the exact accepted PR 09 lease, not a separately string-bound handle. It
composes PR 07's accepted internal intent/claim/CALL/OBSERVE/result-finalization
primitives. A trusted host registers a provider namespace and token-free Adapter
Port once; the bound coordinator verifies the declared operation/request digest,
retains every opaque continuation internally, invokes the exact registered Port
and finalizes its typed result before returning a redacted authority-free
outcome. External-call, observation, settlement and read grants are structural
and separate. No public projection can be converted back into call authority.

**Risk and dependency:** Tier 3 public external-side-effect/security boundary.
Depends on accepted PR 07 and PR 09 contracts. The historical review-only range
is `503cf538..db821683` on `codex/ac-pr10-bound-effect`; it is evidence, not a
replay base.

## Owned surfaces

- Public capability/facade and safe Adapter Port:
  `openjiuwen/agent_teams/effect.py`,
  `openjiuwen/agent_teams/effect_authority.py`,
  `openjiuwen/agent_teams/__init__.py` and
  `openjiuwen/agent_teams/agent/team_agent.py`.
- Minimum internal composition support for the accepted PR 09 lease and PR 07
  purpose/result-bound primitives. PR 10 does not fork PR 07's journal verifier,
  mutation schema, token model or reaper.
- Compatibility boundary: every current root import or caller of
  `ExternalEffectCoordinator`, `ExecutionEffectAuthority`, raw claim/
  authorization/result values, `TeamAgent.task_manager`,
  `TeamAgent.team_backend`, `TeamDatabase.effect` or Manager/DAO fact writers.
- Primary tests:
  `tests/unit_tests/agent_teams/test_effect_authority.py`,
  `test_execution_effect_journal.py` and `test_task_authority.py`, plus accepted
  PR 07/09 lifecycle, export and corruption regressions.
- Historical candidate docs are F_91/S_33; allocate fresh names at replay after
  recounting the then-current documentation tree and update only the accepted
  PR 07 cross-reference.

## Contract

- `TeamAgent.effect_authority` derives from the exact opaque PR 09 session lease,
  Team/member incarnation, trusted-host principal identity and capability set.
  Reader/member identity does not automatically grant plan, call, observe or
  settle. Jiuwen/LiveVoice principal authentication remains downstream; PR 10
  binds the opaque identity and grants supplied by the trusted host.
- The public surface is a capability bundle. Exact names are frozen only after
  PR 07/09 replay, but reader, intent/plan, call, observe and settlement grants
  are distinguishable. Maintenance/reaping, raw Manager/DAO access and provider
  credentials are never product capabilities.
- PR 07 remains the sole journal/projection authority. PR 10 reuses its verified
  record/paged-prefix/result primitives and only adds lease admission, capability
  routing, Adapter binding, redaction and orchestration. It does not maintain a
  second JSON/envelope/prefix/settlement verifier.
- A trusted host installs a stable Adapter namespace/implementation and
  operation allowlist through an internal registry/factory. The registry derives
  the provider namespace/key; ordinary callers cannot choose them or instantiate
  a coordinator with an arbitrary Adapter for each call. Intent binds the exact
  namespace, operation identity, target, replay policy and canonical request/
  intended-effect digests; the token-free Adapter request must match those
  facts. The Adapter owns credentials and provider-specific request bodies. PR 10 does not
  claim protection from a deliberately dishonest trusted Adapter, but it does
  prevent namespace/request substitution by ordinary callers.
- Raw claim, CALL, OBSERVE and result-finalization tokens never leave the
  coordinator/accepted PR 07 internals. Adapters receive an authority-free,
  token-free request and return a typed authority-free receipt/observation to
  the coordinator. Public records are redacted and omit claims, claim/owner/
  continuation tokens and any provider key that is itself a transferable
  capability.
- One high-level call operation obtains the purpose-specific PR 07 CALL
  authorization, appends exact dispatch truth, invokes the bound Adapter at
  most once and immediately attempts result-bound receipt finalization. A caller
  cannot invoke raw `authorize_effect_call`, `record_effect_dispatch` or
  `record_effect_receipt`, and an Adapter cannot use the request to write its
  own evidence.
- Outcomes are typed and truthful. Rejection/registry/digest failure before
  Adapter entry proves zero provider call. Once Adapter entry begins, exception,
  timeout, cancellation, malformed response or lost finalization is an invoked-
  unknown/ambiguous result, never the same `None` as pre-call rejection and
  never automatic retry permission. A verified receipt may be reported only
  after the accepted PR 07 finalizer records its exact provider result.
- Observation follows the same topology with a purpose-specific one-use OBSERVE
  authorization and token-free registered probe. It finalizes the exact returned
  observation internally. Replaying a public response never repeats a probe;
  another probe requires a newly admitted PR 07 observation operation.
- Settlement accepts only an explicitly granted downstream decision plus exact
  authority-free journal/result references and the accepted PR 07 result-bound
  settlement capability. Callers cannot supply an evidence enum/digest or
  compensation ID as if it were proof. Provider/project/file confirmation,
  compensation selection and retry policy remain downstream, while every
  compensation call is itself a separately planned/authorized effect.
- Reconciliation/read results are redacted authority-free views. A decision
  such as safely retryable does not itself mint CALL authority; a later call
  must pass fresh exact admission and stable-key/quiescence rules.
- PR 09 lifecycle linearization covers provider start. If release/rebind wins
  before Adapter entry, provider invocation count is zero. If call-start wins,
  release cannot claim the external effect was cancelled; dispatch remains
  durable, the result is finalized or remains truthfully ambiguous, and no
  second call is admitted. After release returns, no old capability can start a
  new call/probe or append a caller-chosen fact; the only permitted later write
  is internal result-bound finalization or durable ambiguity recording for the
  operation that already won call-start.
- Before Adapter entry, PR 07 durably registers the exact effect in-flight
  authority and PR 09 revalidates the active lease. The PR 03/05 Team lifecycle
  owner retains its deletion reservation and consults that exact effect record
  through a narrow internal seam, failing clean closed while the provider may
  run. Exact finalize, cancel/durable-ambiguity transition or the PR 07 watchdog/
  reaper converges only effect-owned state, then asks the Team owner to release
  the exact reservation token. PR 07/10 neither scans/owns general Team
  reservations nor chooses product settlement.
- Ordinary Task deletion and normal Team clean preserve PR 07 effect/event
  tombstones and identity-first replay. Active plan/call/observe/settle leases
  revoke; separately granted tombstone read/exact-replay follows the accepted
  PR 07/09 retirement policy and never crosses same-name reincarnation. Explicit
  session-domain destruction is the only path permitted to remove retained
  effect/event tombstones and history.
- Current DDL, `DbSessions` locking/watchdog/retry and `SessionFileStore`
  hydration/rollback behavior remain unchanged. Provider/file/product side
  effects are outside `SessionFileStore`, but every rejected pre-call path still
  asserts zero journal, Task, event and file mutation.

## Replay and verification

1. Rebase after accepted PR 07/09 and record their exact SHAs, selected lease/
   capability types, Adapter registry owner and root export set.
2. Rebuild the three primary test files from the accepted contract, using
   `8db056f5` and PR-owned `fbfb4c5f` corrections only as historical evidence.
   Do not restore direct `_bind`, public token, raw evidence-writer, arbitrary
   Adapter injection, repeated OBSERVE or two-step call/then-manual-finalize
   positive tests. Run before implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_effect_authority.py tests/unit_tests/agent_teams/test_execution_effect_journal.py tests/unit_tests/agent_teams/test_task_authority.py -q

3. From the exact accepted dependency tips, implement only the lease-bound,
   redacted orchestration delta. Do not cherry-pick `53dfcc7c`; fold only PR
   10-owned `fbfb4c5f` quality corrections.
4. Rerun the three primary files plus accepted PR 07 journal and PR 09 lease/
   capability/export suites. Repeat provider-start/result-finalize/observation/
   settlement versus release/rebind/cancel races in both linearization orders.
5. Run file-backed SQLite reopen/concurrency/corruption/normal-clean cases,
   current database/concurrency/watchdog/TaskManager/SessionFileStore
   regressions, supported-dialect compilation and a real registered deterministic
   Adapter through the exact public facade.
6. Run changed-file Ruff/format, isolated Mypy for the facade/Port, compileall
   and `git diff --check`.
7. Obtain an independent Tier-3 review focused on token escape, raw writer or
   construction bypass, Adapter/request binding, invoked-unknown truth,
   lifecycle/provider-start linearization and accidental product policy.

## Replay preflight — 2026-08-25

Formal replay is blocked on accepted PR 07/09 tips and on the capability,
Adapter-registry and typed-outcome decisions below. Historical commits are
`53dfcc7c` (source), `8db056f5` (tests) and `db821683` (docs); their 15-file,
3,642-insertion range must not be layered onto a formal dependency branch.

The historical implementation cannot be replayed mechanically. Reimplementation
must:

- inherit PR 09 rather than recreate its bypasses. `TeamExecutionEffectAuthority`
  is independently string-bound, its public constructor accepts
  `_agentcore_binding=True`, `_bind` is callable, and raw Manager/backend access
  remains. Same-ID rebind and in-flight release therefore revive or fail to
  fence external-call authority;
- replace monolithic member authority with structural grants. Every bound
  member receives plan/claim/dispatch/receipt/observation/settlement/read/
  reconcile methods and may supply another execution's owner/version tokens.
  Exact executor/runtime/phase/incarnation and trusted-host principal authority
  must be inherited from PR 09/07 rather than reconstructed from public rows;
- eliminate token and raw-writer escape. Historical `claim_effect` and dispatch
  results return claim/CALL/OBSERVE tokens, `get_effect` returns a record whose
  live claim contains `claim_token`, and public record/settle methods accept
  caller-supplied receipt/observation/settlement evidence. A caller can
  manufacture durable evidence without invoking any provider;
- reject wrong-purpose finalization explicitly. Historical receipt recording
  does not require a prior consumed call authorization, receipt/observation
  writers accept either CALL continuation or RECONCILE claim tokens, settlement
  accepts both, and OBSERVE authorization is reusable before first write. A
  dispatch can therefore become `OBSERVED`/`RESOLVED` without a provider call;
- make the coordinator own provider-result finalization. Historical tests call
  the coordinator, receive an authority-free result, then manually reuse the
  token to append receipt/observation and an arbitrary settlement digest. This
  preserves PR 07's rejected CALL/OBSERVE/result-finalizer topology and creates
  response-loss gaps between provider return and durable truth;
- bind the actual Adapter and request. `ExternalEffectCoordinator(authority,
  adapter)` accepts any injected object, while the effect binding has no stable
  registry-derived Adapter namespace/key and the Adapter receives only an authorization/digests, not
  a request whose canonical digest can be checked. The Adapter also receives
  the live continuation token. Historical intent therefore does not prove that
  the invoked request/provider was the one authorized;
- replace `None` outcome conflation. Historical coordinator returns `None` for
  pre-call rejection, authority corruption, Adapter exception after possible
  effect, malformed post-call receipt/observation and duplicate authorization.
  These states require distinct zero-call versus invoked-unknown/finalized
  outcomes so callers cannot infer safe retry from ambiguity;
- linearize the PR 09 lease with provider start and PR 07 one-use authorization.
  Historical authorization is consumed, then Adapter invocation occurs outside
  the lease/Manager transaction; release/rebind can win between them and a
  provider call can begin under an already-revoked handle. Cancellation and
  claim expiry after call start also lack explicit finalization/ambiguity rules;
- close the cleanup erasure window. Historical effect journal/effect/fact rows
  cascade from Team deletion, and no deletion reservation or in-flight runtime
  registration spans authorization -> provider -> finalization. Normal clean
  can erase the complete audit while the provider runs; replay after same-name
  rebuild then looks like a never-planned effect;
- expose redacted views and bounded work only. Historical public records leak
  live claim/producer fields, `read_effect_prefix` returns the complete fact
  tuple, row-count and per-fact limits multiply without one cumulative byte/work
  budget, and nearly the whole PR 07 record/fact/prefix/settlement verifier is
  copied into `effect_authority.py`. Compose PR 07's bounded verified reader and
  define public page/byte/effect/cumulative-work limits instead of creating
  another truth;
- leave subordinate semantics with PR 07. The source commit changes
  `effect_dao.py` authorization/prefix-limit behavior and carries broad
  formatter noise; those changes must already exist in the accepted PR 07 tip
  or be routed back to it. PR 10 owns no journal schema, migration, reaper or
  normal-clean policy; and
- require, but do not publicly expose, PR 07's accepted claim-release and
  watchdog/reaper integration. Historical reaping is only a raw Manager method;
  cancellation, caller loss or Adapter failure can otherwise leave execution
  quiescence blocked with no runtime maintenance path; and
- preserve PR 07/09 effect-intent event anchor, purpose-specific one-use CALL/
  OBSERVE/result finalization, normal-clean tombstones, current DDL and
  `SessionFileStore`. Historical docs/tests/counts do not transfer.

Before rebuilding the red suite, freeze:

1. the PR 09 effect capability grants and exact shared lease/incarnation object;
2. safe root exports and removal/transition of raw Manager/DAO/token/finalizer
   paths;
3. trusted Adapter registry/factory ownership, server-derived namespace/key,
   operation allowlist and in-process trust boundary;
4. token-free call/observation request shape and canonical request/provider/
   target binding;
5. typed zero-call, invoked-unknown, finalized and replay outcomes;
6. provider-start versus release/cancel/expiry linearization and internal result
   finalization/recovery;
7. redacted effect/claim/fact/prefix views and bounded page/work budgets;
8. downstream settlement/compensation decision input without evidence forgery;
   and
9. strict reuse of PR 07 journal verification and current DDL/SessionFileStore.

Tier-3 red/green evidence must rebuild, rather than copy, the historical cases
and record the complete D-032 matrix:

- **P:** one exact non-Voice executor obtains deliberate plan/call/read grants,
  plans an effect, invokes one registered deterministic Adapter through the
  public coordinator, internally finalizes its receipt, performs one admitted
  probe, submits one authorized downstream settlement decision and reopens a
  redacted verified journal with exactly one provider call;
- **N/I:** forged constructor/`_bind`, raw Manager/backend/DAO/coordinator,
  foreign principal/capability/session lease/Team/member/Task/execution/runtime/
  phase/incarnation/effect/claim purpose/Adapter namespace/operation/request/
  target/digest/prefix and stolen owner/token fields reject. Pre-Adapter paths
  assert zero provider, Task, event, journal, checkpoint, file and other-scope
  effects. Missing/corrupt intent genesis, PR 05 source event, complete journal,
  prefix/projection or runtime registration never collapses into a fresh effect
  or new authority;
- **B:** empty/malformed/maximum identities, request/result/evidence size,
  registry and page limits, prefix cumulative work, lease/expiry, ordinal/
  version/signed-integer and typed enum/digest boundaries are explicit;
- **S/T:** lease acquire/release, same-ID rebind, member/Team/Task/effect
  retirement/recreation, planned/call-started/unknown/observed/settled states,
  delayed/duplicate/expired callbacks and tombstone replay remain coherent and
  non-revivable;
- **C:** duplicate call authorization, provider start versus release/rebind/
  expiry/cancel in both orders, receipt finalization, concurrent call/probe/
  settle/reaper/normal-clean and same/different effect operations prove at-most-
  once Adapter entry and exact journal linearization;
- **R:** crash/cancel/response loss before and after intent, claim, dispatch,
  Adapter entry, provider return and receipt/observation/finalize commit produces
  truthful zero-call/finalized/ambiguous state after restart without duplicate
  call or probe. Exact replay never re-enters the Adapter;
- **F:** missing/wrong Adapter registration, exception/timeout/cancel before
  versus after Adapter entry, malformed receipt/observation, unavailable PR 07
  verifier and corrupt subordinate result are typed and fail closed; no Provider
  success or no-effect claim is inferred from an exception;
- **K:** accepted PR 07/09 suites, root import transition, current Manager/
  database callers, supported-dialect compilation and `SessionFileStore`
  hydration/update/rollback regressions remain compatible with the selected
  public transition. Replay validates the then-current `develop` DDL/migrations,
  write-lock helpers and explicit drop/destroy path rather than historical
  dialect compilation alone;
  and
- **X:** exact clean AgentCore with real `TeamAgent`/`SessionManager`, real
  file-backed SQLite, accepted PR 07 journal, shared PR 09 lease and one real
  registered deterministic Adapter exercises the actual Port. LiveVoice,
  project/file policy, credentials and a real external Provider remain explicit
  non-claims.

The independent preflight review reports **5 Critical / 4 Important** against
the historical candidate. These findings are replay requirements above, not
findings accepted into a formal branch. Historical tests and review counts do
not transfer. Formal PR 10 branch readiness is **No**.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): expose lifecycle-bound external-effect orchestration”.

The PR body must explain the shared lease/capability model, trusted Adapter
binding, token-free requests, internal result finalization, typed ambiguous
outcomes and lifecycle/provider-start evidence. Exclude provider-specific
Adapters, credentials/request bodies, Jiuwen project/file mutation policy,
retry/compensation product decisions, LiveVoice confirmation/composition,
migration, rollout and remote submission.
