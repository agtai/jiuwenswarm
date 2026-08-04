# W1-K1 implementation review record

> Review date: 2026-08-03
> Scope: five non-Sol implementation candidates for the ACG v2 critical kernel
> Current progress and next action remain authoritative only in [STATUS.md](STATUS.md).
> The accepted ownership change is recorded in [D-049](decisions/DECISIONS.md).
> [D-052](decisions/DECISIONS.md) supersedes future model-allocation statements in this historical record; it does not change the reviewed code-source history.

## 1. Reviewed candidates

All five candidates were produced from the same clean planning baseline, `73448519be9ee7cb2bb384e8aa2c4914178f9291`, by repeatedly replacing the remote `agtai/hx/0803_live_voice_ds` candidate rather than adding a linear series of fixes:

1. `a5f91654141146b440216b8190b25a07fbf189f3`;
2. `ca3836ba8d24898ed86cbe60b28d475b771c50de`;
3. `1b9d3b8349873cb918e3b4f308dd9970c6904563`;
4. `a1c6d3d22af534b7fe61a282c0b72ab08175f69f`;
5. `6ce74a4b5ad9a3ea6f5be044e7114315826f6baa`.

The latest remote ref points to `6ce74a4b`. None of these candidates is integrated into `hx/0803_live_voice`.

## 2. Review result

The fifth review did not accept W1-K1. Of the 15 tracked correction categories, one was substantially corrected, seven were only partly corrected, and seven remained incomplete.

| Category | Result after `6ce74a4b` | Remaining problem |
|---|---|---|
| Event sequence | Partial | gap replay can erase the reported sequence error; same-sequence conflict does not quarantine the sequence |
| Event causation | Partial | a valid Adapter cannot identify itself while referencing the source; later legal roots are rejected |
| TurnCommit | Incomplete | arbitrary payload plus caller-supplied ID; no complete immutable binding or atomic once-only operation |
| Parent binding | Incomplete | parent existence/type is checked, but ownership of the current child is not |
| Runtime rule immutability | Partial | exported transition/authority tables can still be mutated at runtime |
| Response fence | Partial | callbacks validate generation without the full response tuple; replacement does not allocate a new response ID |
| Cancel | Incomplete | target/owner/policy rules are not enforced and default barge-in behavior is wrong |
| JSON boundary | Incomplete | inherited/accessor/sparse/cyclic/non-scalar input is not rejected consistently before validation |
| Numeric range | Incomplete decision | code enforces a safe-integer proposal still marked as awaiting owner confirmation |
| Result ownership/replay | Incomplete | Result is not bound to one request/command owner and replay does not guarantee zero re-execution |
| Scope | Partial | ordinary cases improved, but TypeScript prototype inheritance can bypass the checks |
| Attempt default lifecycle | Substantially corrected | the default accepted-to-terminal shortcut was removed; mutable rule tables can still reintroduce it |
| Capability | Partial | ordinary major-version checking improved, but inherited descriptors and missing registry authority remain |
| Event vocabulary/authority | Incomplete | unknown event, capability, stream, or authority combinations can be accepted |
| ContractError | Partial | wire/throwable separation improved, but the documented Python copy/pickle behavior is false |

The main affected implementation locations in `6ce74a4b` are:

- `jiuwenswarm/common/schema/live_voice_contract_v2.py`;
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts`;
- `tests/unit_tests/common/test_live_voice_contract_v2.py`;
- `jiuwenswarm/channels/web/frontend/tests/liveVoiceContractV2.test.mjs`;
- `tests/fixtures/live_voice_contract_v2/`.

## 3. Verification evidence

- Python focused suites: `92 passed`.
- TypeScript fresh single-file compilation: succeeded.
- TypeScript focused suite: `41 passed`.
- `git diff --check`: succeeded.
- Full Vite build was not counted because the detached review worktree could not resolve its local frontend dependency tree.
- Additional adversarial probes reproduced invalid acceptance or unstable failure for sequence replay, arbitrary parent/TurnCommit/Result binding, mutable transition rules, unknown event authority, prototype-based scope/capability input, cancel targeting, and cyclic JSON.

The green focused suites therefore prove only the encoded examples. They do not prove ACG semantic conformance. The added `protocol_manifest.json` is not loaded by either implementation or test suite and is not an enforcing oracle.

## 4. Sol takeover and source reuse

The current DeepSeek remote branch and its latest `6ce74a4b` candidate are retained as review history and a source of candidate fixtures. They must not be deleted, force-updated again, or described as accepted W1-K1 output. All five reviewed SHAs are recorded above; the first four are force-replaced objects without dedicated remote refs and are not promised as permanent integration sources.

Sol will implement W1-K1 from the clean `hx/0803_live_voice` baseline on a separate work branch. It will not amend `6ce74a4b`, merge the DeepSeek branch, or cherry-pick the candidate wholesale. The implementation should be rebuilt around the ACG invariants and one shared Python/TypeScript scenario oracle.

Selective reuse is allowed only after the copied unit is checked independently against the ACG and the adversarial scenarios. Likely inputs include useful fixture examples, test case ideas, enum spelling, error separation, and other mechanical definitions. Candidate state machines, causation logic, replay/Result ownership, TurnCommit storage, fence/cancel behavior, authority registries, JSON normalization, and mutable rule tables are not a trusted base.

After Sol establishes the reference implementation and shared scenario outputs, a non-Sol executor may handle exact-language translation, fixture expansion, ordinary Adapter/UI work, and other bounded tasks that do not choose new protocol semantics.

## 5. Next review condition

W1-S1 may be reconsidered only after the Sol implementation:

1. derives Python and TypeScript behavior from the same scenario oracle;
2. covers the positive journey plus the recorded adversarial cases;
3. enforces exact identity, parent, scope, authority, replay, Result, cancel, fence, TurnCommit, JSON, and immutable-rule behavior;
4. resolves every proposal still marked as awaiting owner confirmation;
5. runs the focused suites, affected regressions, TypeScript compilation, and frontend build in a dependency-complete workspace.

## 6. Sol reference candidate — 2026-08-04

The Sol candidate starts from `73448519be9ee7cb2bb384e8aa2c4914178f9291` on `hx/0803_live_voice` and is committed together with this record. A commit cannot self-record its final SHA; Git identifies the immutable candidate. D-051 superseded only D-049's separate-work-branch instruction during implementation; the rejected DeepSeek commits remain reference history and were not merged or cherry-picked.

Implemented W1-K1 scope:

- Python and TypeScript v2 Scope/identity, Command/Query/Result/Event, Capability/Error, and canonical JSON primitives;
- immutable parent/scope records, core lifecycle validation, exact four-cancel routing, TurnCommit acceptance/dispatch, command idempotency, full response-tuple fencing, and event sequence/causation validation;
- shared valid/invalid/v1 fixtures and matching Python/TypeScript scenario tests;
- namespace-only `jiuwenswarm/server/live_voice/`; no runtime, Provider, transport, store, UI, or legacy-v1 takeover.

D-050 resolves the earlier numeric decision: integer-valued JSON numbers are restricted to the shared IEEE-754 safe range so Python and TypeScript cannot disagree on canonical bytes or fingerprints.

## 7. Tier 3 scenario evidence

| Dimension | Evidence in the Sol candidate | Result after review 3 corrections |
|---|---|---|
| Positive / boundary | shared round-trip, canonical bytes, safe integers, every listed lifecycle edge, result success/failure | PASS |
| Negative / security | strict closed objects, kind/parent/scope/authority/capability/version rejection, JS accessor/prototype/sparse/cycle probes | PASS |
| State / temporal | terminal immutability, attempt no shortcut, response replacement/cancel fence, event duplicate/gap/conflict/causation | PASS |
| Concurrency / replay | Python threaded command and TurnCommit cases; TypeScript concurrent and synchronous-reentrant command delivery | PASS |
| Failure / recovery | cached handler failure, unsupported/unavailable/unknown/timeout/internal distinction, gap quarantine and external command-cause reconciliation | PASS for the pure kernel; no store/restart claim |
| Cross-layer / compatibility | the same JSON fixtures drive both languages; v1 parser/tests remain separate and unchanged | PASS |
| Privacy / observability | errors retain safe structured fields and correlation; fixtures contain no credentials/raw audio | PASS for schema behavior; no runtime logging claim |
| Performance / regression | focused suites, strict single-file TypeScript compile, Ruff, Vite production build, and v1 regression suite | PASS; no real latency/load claim |

Excluded by the W1-K1 package and still open at consumer Gates: non-empty ContextRef, rich WorkProgress, presentation ledger, real Provider/Executor/transport/UI, persistence/outbox/restart, production authorization, Windows/device evidence, and real E2E.

## 8. Requested review sequence

### Review 1 — Sol implementation self-review: corrected

Actionable defects found and fixed:

1. lifecycle rules existed but were not enforced by the event reducer;
2. conflicting event IDs/sequences could leave an unsafe quarantined event eligible;
3. command causation could not be registered, while invalid Adapter-to-Adapter authority remained indefinitely quarantined;
4. TypeScript failure Result used a non-wire field shape;
5. Capability modes/status and several lifecycle edges differed from the ACG or between languages;
6. response-target cancel routing discarded the exact interaction/response/generation data;
7. shared invalid fixtures initially indexed cases without executing each case.

After correction, the v1+v2 Python suite, TypeScript suite, Ruff, and Vite build passed.

### Review 2 — independent uncommitted-diff prompt: corrected

The review ignored prior rationale and judged the complete worktree against the original W1-K1 package, repository rules, ACG, APIs, diff, and real tests. Actionable defects found and fixed:

1. public TypeScript stateful helpers trusted structural interfaces without re-parsing immutable snapshots;
2. the TypeScript command ledger invoked the handler before publishing its pending idempotency entry, permitting synchronous reentrant duplicate execution;
3. TurnCommit acceptance and committed-origin checking were separate, so consumers lacked one atomic once-only dispatch helper and exact accepted-commit binding;
4. event lifecycle rejection surfaced a business `CONFLICT` instead of the ACG-required `PROTOCOL_VIOLATION`;
5. timestamp and several stable validation reasons were not fully aligned across Python and TypeScript;
6. `STATUS.md` and the environment blocker still described pre-implementation facts.

All code findings were corrected and focused suites passed again. Documentation now records the current uncommitted candidate and restored Node environment. Review 3 remains pending below.

### Review 3 — Codex `/review`: corrected

The installed WindowsApps CLI alias was ACL-blocked, so the same official Codex review command was run through `npx @openai/codex review --uncommitted`. It inspected tracked and untracked changes and found six actionable defects:

1. applied event and external-command causal links did not enforce exact scope and correlation;
2. lifecycle state was stored per producer instance, allowing a restarted producer to regress a terminal object;
3. TypeScript copying of an own `__proto__` field could invoke the prototype setter and hide an unknown field;
4. Python `IdentityRegistry.register` trusted directly constructed records without normalizing their IDs and scope;
5. TypeScript unsafe unsigned integers returned a different stable reason from Python;
6. TypeScript exposed only canonical strings, not the required canonical UTF-8 byte/fingerprint helper.

All six were corrected in both implementations where applicable. New tests cover cross-scope/correlation causation, lifecycle continuity across producer instances, own-`__proto__` rejection without changing ordinary output objects, direct Python registry input, unsafe sequence parity, and non-ASCII canonical/fingerprint bytes. The post-fix focused suites pass (`76` Python and `24` TypeScript tests); Ruff, Python/TypeScript formatting, the Vite production build, `git diff --check`, and all Live Voice Markdown relative links also pass.

An additional full Codex rerun was attempted after correction but failed to terminate normally and returned no result, so it is not counted as a clean review. The successful Review 3 findings, direct fix inspection, new adversarial tests, and final local checks above are the evidence for the corrected state.

The W1-K1 implementation and requested review sequence are complete in the commit containing this record. That immutable candidate closes W1-S1. Runtime consumers, persistence/restart, real Providers/transports/UI, and real E2E remain explicitly outside W1-K1 and must be proven at their consumer or release Gates.

## 9. Post-commit correction review — 2026-08-04

An independent review of committed candidate `bd1965ad8ebff6218b15ced1e29afd46be739c98` reproduced two actionable P1 gaps and separated them from two documented limitations:

1. the dated W1-K1 TypeScript command compiled to a nested output path while its Node test imported a flat path, and the exact command exposed a `cloneJson` type error; the TypeScript branch is corrected and the package now uses the single canonical `npm run test:live-voice-contract-v2` command before `npm run build`;
2. identity registration omitted the ACG connection-epoch binding and incorrectly required a turn parent for `round`; both languages and the shared fixture now bind `connection`/`media_session` to the same numeric epoch, validate connection existence/scope/staleness, and keep `round` parent-free;
3. rejection of integer-valued JSON numbers beyond the cross-language safe range is the accepted D-050 rule, not a defect;
4. a conflicting event stream remaining fail-closed is intentional; ACG now states that consumers need authority-led reconciliation/rebuild or a verified replacement producer instance rather than automatically skipping the conflict.

The correction is included in the amended W1-K1 commit containing this record. Current results are `77` Python v1+v2 tests and `25` TypeScript W1-K1 tests passing; Ruff, Prettier, the Vite production build, `git diff --check`, Markdown links, and the final complete-diff review also pass with no additional actionable defect. The corrected immutable candidate closes W1-S1; STATUS owns the current branch fact and next action.
