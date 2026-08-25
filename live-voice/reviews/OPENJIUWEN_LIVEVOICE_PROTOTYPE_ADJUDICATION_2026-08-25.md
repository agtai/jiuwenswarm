# OpenJiuwen LiveVoice prototype adjudication — 2026-08-25

Status: preparation-only decision. This review decides how the five isolated
LiveVoice candidate commits and the ignored EVT-02 recovery archive may be used.
It does not select code for immediate feature-branch integration and grants no
migration, cutover, deletion or product-readiness credit.

This review applies the accepted
[slimming scope](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md), the
[complete module disposition](OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md),
the [symbol migration map](OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md)
and the
[AgentCore local PR preparation review](OPENJIUWEN_AGENTCORE_PR_PREPARATION_REVIEW_2026-08-25.md).

## 1. Decision

The five commits are useful design and test evidence, but none is a wholesale
LiveVoice integration input. Their combined change is 10,582 insertions and 23
deletions across implementation, tests and implementation packets. That batch
size identifies the isolated preparation artifact only; durable conclusions
below use module paths, symbols, public contracts and capability IDs rather
than source line numbers.

The final treatment is:

- rewrite the Task facade, query owner, D1 adapter and presentation adapter as
  smaller boundaries against the final public AgentCore contracts;
- preserve only the small product-owned asynchronous injection seams if the
  moving feature branch still needs them when implementation is later scoped;
- discard the current project/file Effect adapter implementation and first
  extract a public product-owned project-effect Port from the existing
  executor;
- keep relevant positive, negative, restart, race and zero-side-effect tests as
  behaviour oracles to port into later packets, not as proof that their current
  implementation must survive; and
- discard the ignored EVT-02 implementation and packet. Its test ideas may be
  reused against the final AgentCore event reader and a pure downstream
  projector; the archived subscription state machine is not restored.

## 2. Reproducible evidence

| Fact | Observed value |
|---|---|
| Read-only LiveVoice product fact | `hx/0812_live_voice_w3@acd873d0e93b2e82424e0d90a650df2c3515c34c` |
| Isolated preparation parent before this adjudication | `codex/livevoice-agentcore-hermes-prep@98832fa9500ab99dc2b6d4c275fa328fdfc13a9f` |
| Clean AgentCore candidate used by opt-in integration | `codex/oj-g2-local-base@50c065dc7fb5e0c21903128d1a033c52968be97e` |
| Production composition imports of the five candidate modules | none |
| Default candidate-suite result without an explicitly selected AgentCore source | `135 passed, 5 skipped`; all five skips state that an exact candidate was not requested |
| Exact-candidate suite result with candidate path, HEAD and import source verified | `140 passed`; includes five real public-facade/SQLite integration tests |

The D1 and project/file Effect integration tests previously coupled the minimum
required capability commit to the exact candidate HEAD. They now enforce two
separate facts: the requested SHA must equal the clean worktree HEAD, and that
HEAD must contain the required D1 or Effect public-facade commit. This preserves
reproducibility while allowing reviewed quality-fix descendants.

The only production files outside the candidate modules changed by these five
commits are `product_p3_text_adapter.py` and `presentation_ledger.py`. They add
optional asynchronous injection seams. No product registry, root or launcher
constructs any of the OpenJiuwen candidates.

## 3. Commit-by-commit adjudication

| Commit and boundary | Production-code decision | Reusable evidence | Smallest possible later seam |
|---|---|---|---|
| `9c820fe1` — `openjiuwen_task_facade.py` | **MINIMIZE / REWRITE.** Do not retain its parallel Task/Event/Execution/Result/Cursor model layer or repeated generic validation. Public AgentCore types and `TeamTaskAuthority` must remain canonical. | Scope derivation, least-privilege binding, wrong-scope, stale-token, replay and public-import tests remain useful oracles. | One authenticated product-scope binder and a thin mapping facade over `TeamAgent.task_authority`; presentation ACK and product policy stay outside it. |
| `1a84b541` — `openjiuwen_product_query_adapter.py` plus the optional async query seam | **MINIMIZE / REWRITE.** The read-only translation is legitimate downstream work, but the current adapter is coupled to the large mirror facade. The optional `AsyncProductP3QueryOwner` seam is a valid design candidate, not pre-approved feature code. | Authorization rebinding, operation/limit bounds, concurrency and result-envelope tests remain useful. | Directly translate the product query into final public `TeamTaskAuthority` reads and map the result once; retain no query cache or durable state. |
| `0228b738` — `openjiuwen_d1_checkpoint_adapter.py` | **MINIMIZE / REWRITE.** AgentCore owns checkpoint publication/reference truth. The product keeps only codec, profile/compatibility and payload policy. The prototype's separate immutable file store and repeated generic validation are not selected. | Exact execution identity, response-loss replay, orphan/stale/corrupt reference, cross-scope, reopen and zero-resume-authority tests remain required oracles. | Map the retained product `D1Checkpoint` codec to `ExecutionCheckpointCoordinator` and the bound Task authority. Select an existing Checkpointer or explicit product payload store in the later packet. |
| `b0575038` — `openjiuwen_project_file_effect_adapter.py` | **DISCARD IMPLEMENTATION.** It imports private executor helpers such as patch application, ownership lock, Git/root and filesystem-safety probes. That is reverse coupling, not a stable Adapter boundary, and it duplicates project mutation policy. | Response-loss, ambiguous outcome, symlink/root drift, cancellation/quiescence, scope isolation and zero-file-effect scenarios remain high-value oracles. | First extract a public JiuwenSwarm-owned `ProjectEffectPort` from `project_code_executor.py`; a thin continuation adapter may then connect that Port to `TeamAgent.effect_authority` / `ExternalEffectCoordinator`. |
| `561e5e5f` — `openjiuwen_task_presentation_adapter.py` plus async consume | **MINIMIZE / REWRITE.** Product receipt verification remains necessary, but the current adapter repeats canonical event/cursor models and validation from the mirror facade. The asynchronous command seam is a valid design candidate only. | Independent text/voice cursors, authentic DOM/playout ACK, replay, stale receipt, cancellation, close and concurrency tests remain required. | Keep `TaskPresentationConsumptionOwner` as the product proof owner, then issue exactly one final AgentCore cursor CAS through a thin mapping; store no second cursor. |
| ignored EVT-02 archive — `openjiuwen_task_event_subscription.py` and packet | **DISCARD IMPLEMENTATION AND PACKET.** Do not restore the additional lifecycle/queue state machine. Existing LiveVoice transport may consume the final AgentCore event page/head API without creating another event truth owner. | Port bounded replay/head, wrong-scope, cancellation, close-race, corruption and cross-task isolation scenarios to the final event-reader/projector tests. | Prefer a pure envelope-to-product projector plus the minimum cancellation-aware polling wrapper already owned by the product transport. No durable state and no duplicate event sequence. |

## 4. Why passing tests do not select the implementations

The candidate tests prove that the explored contracts can be made fail-closed.
They do not prove that the explored object graph is the minimum boundary. Four
separate forms of duplication remain in the current prototypes:

1. mirror Task/Event/Execution/Result/Cursor dataclasses compete with final
   AgentCore public values;
2. validation is repeated on both sides of the boundary instead of translating
   only product-specific identity and policy;
3. local payload, subscription or mutation machinery recreates storage/runtime
   owners that already exist or are being prepared in AgentCore/JiuwenSwarm;
4. implementation packets describe experiments whose scope is larger than the
   future thin LiveVoice seam.

Therefore the tests are porting oracles. A later packet must first name the
final public AgentCore version, then write the smallest product adapter against
it and rerun the relevant oracle subset. Existing green code does not reverse
that dependency order.

## 5. Future LiveVoice allowlist, not an implementation order

Only the following kinds of LiveVoice changes may be considered after the
AgentCore public contracts are replayed and accepted:

1. authenticated product scope and project/session binding into public Agent /
   Runner and bound Task/effect authorities;
2. a read-only product query translation, with an async injection seam only if
   the then-current carrier still needs it;
3. a D1 codec/payload-policy adapter into the checkpoint coordinator;
4. a public product `ProjectEffectPort` and a thin AgentCore continuation
   mapping, without private executor imports;
5. product presentation receipt verification followed by one generic cursor
   advance; and
6. pure event/progress projection from AgentCore envelopes with no alternate
   event sequence or subscription authority.

This list authorizes no current code integration. Each item requires a later
feature-branch packet, current-source revalidation and the risk/evidence tier of
the boundary it changes.

## 6. Explicit exclusions

The following stay out of any wholesale merge into `hx/0812_live_voice_w3`:

- all five candidate production modules as currently written;
- the five implementation packets as implementation authority;
- duplicate facade models, generic validators, payload storage, subscription
  state and project mutation/probe machinery;
- the ignored EVT-02 implementation, tests and packet as tracked files; and
- the preparation branch history itself.

The isolated files remain available as local recovery/evidence while this task
runs. Future accepted tests or seams are ported deliberately; the preparation
branch is never merged as a unit.

## 7. Remaining preparation boundary

This adjudication closes prototype selection only. Remaining work is to package
the ten AgentCore capability groups as independent local PR candidates, prepare
their per-PR plans/descriptions/evidence, and converge the final LiveVoice
allowlist/discard list. Migration, dual write, default-on composition, canary,
Store retirement and source deletion remain explicitly deferred.
