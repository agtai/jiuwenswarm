# P3-1 canonical multi-Task implementation review — 2026-08-19

> Status: **PASS — SCOPED P3-1 ACCEPTED.** Current-source affected automation,
> static/build checks and independent Tier-3 review pass. No remaining P1/P2
> was found in the P3-1 candidate diff. This is Task Core/Store package credit,
> not a controlled product-readiness or physical microphone/TTS PASS.

## 1. Exact baseline, dependency and scope

- Git baseline: `5787eda931159ba533e0a81ca8be8b744f449a8b` on
  `hx/0812_live_voice_w3`.
- Imported implementation input: `d48559be719d225f343e05a9f3b660cb90e73b53`,
  applied once with `git cherry-pick -n` and rebaselined in the working tree.
  Its old parent `65a66db6`, COMPLETE label, test counts and review disposition
  are not evidence for this source.
- P3-G0 remains **PASS — AUTHORITATIVE P3 FOUNDATION** only under D-086. Exact
  product source `f24dd17d` remains a failed controlled product-readiness
  candidate; this Core/Store package neither reruns nor upgrades that result.
- Capability owner: Task Control Core/Store. Risk: Tier 3 because the package
  changes shared Task identity, state validation, SQLite schema/migration and
  authenticated query/mutation seams.

## 2. Implemented facts

The candidate provides:

- SQLite schema v4 with immutable create-Command identity, revision number and
  predecessor-Task fields; atomic v1/v2/v3-to-v4 migration and v4 reopen;
- pre-promotion/reopen semantic reconstruction of Task, Attempt, TaskEvent,
  control Command/outbox, canonical Executor observation, TaskResult and
  current-selection authority. Corrupt legacy truth fails closed and the whole
  migration transaction rolls back without metadata or DDL promotion;
- multiple non-terminal Tasks in one exact authorized scope; the persisted
  current Task is only a replaceable Session/UI selection hint;
- exact addressed `get/status/events/result/adjust/cancel` behavior, bounded
  keyset Task-list pagination and sequence-based Task-event pagination across
  restart;
- immutable three-state TaskResult reads (`not_ready`, `available`,
  `unavailable`) with exact artifact validation;
- authenticated product routing for list/events/result and structured addressed
  adjustment of a non-current Task;
- Voice/Demo convenience routing that still snapshots and binds the exact
  current Task. The shortcut cannot redirect an addressed mutation;
- one Task lifecycle contract per language: server Core, persistent Store and
  TaskEvent subscription reuse the shared Python `validate_transition` Task
  graph, while the TypeScript boundary implements the same fixture-tested wire
  contract and exact `task.adjust: {adjustment}` envelope;
- exact Store-owned exceptional terminal paths for pre-dispatch cancellation,
  non-retriable dispatch rejection and lost-attempt reconciliation. Their
  event, command, outbox, claim, error, spec and Executor bindings are verified;
- terminal/stale outbox lease fencing: reset, reconciliation and explicit
  release suppress stale claimed work, so it cannot resurrect as pending or
  permanently block retry. Store lifecycle validation occurs before TaskEvent
  or Task-row mutation.

The frozen Task graph is:

```text
accepted          -> running | blocked | decision_required | terminal
running           -> blocked | decision_required | terminal
blocked           -> running | decision_required | terminal
decision_required -> running | blocked | terminal
terminal          -> no normal lifecycle transition
```

`terminal` requires an exact outcome and non-terminal states forbid one.
`queued` is a projection, not a canonical state; `paused` remains unsupported.
The existing D-058 `task.retry_accepted` flow is explicitly isolated as a
bounded cross-Attempt epoch compatibility rule, not a normal Task edge.
P3-2 owns successor-Task creation and the complete update/provide-input/pause/
resume/reprioritize command model; P3-1 does not pre-implement it.

## 3. Corrections made during the current rebaseline

The imported candidate incorrectly required every `task.adjust` to carry the
current background Session and Task. Test-first correction established that:

- authenticated structured/text `task.adjust` uses exact scope, confirmation,
  authorization and addressed `task_id`, with no current-Task dependency;
- `PersistentTaskCore` and `SqliteTaskStore.adjust()` no longer accept or check
  a current-background Session;
- only the Voice/Demo current-task shortcut supplies a trusted current Task and
  must retain exact target/session binding;
- an authenticated two-Task test adjusts the non-current Task, proves the
  current Task unchanged and proves the selection hint remains unchanged;
- the Store rejects an illegal repeated/backward lifecycle transition before
  any event or Task write, and the subscription consumes the same shared graph
  instead of maintaining a second server-side Task transition table.

The independent review then found and drove closure of current-source gaps in
TypeScript `task.adjust`, AgentServer `task.result` routing, migration semantic
promotion, control-event ledger closure, Executor-event/result authority,
Store-owned terminal exceptions and terminal lease release. Every finding was
reproduced or demonstrated from the write/reopen path before repair; affected
tests were rerun after the final source change.

Red/green evidence for these corrections:

- before implementation: **3 failed, 1 passed** with
  `CURRENT_BACKGROUND_TASK_BINDING_REQUIRED`,
  `CURRENT_BACKGROUND_SESSION_REQUIRED`, and missing Store transition rejection;
- after implementation: the same focused command reported **4 passed**.

## 4. D-032 evidence and zero-effect coverage

- `P/N/B`: multiple active Tasks, bounded pages and exact addressed operations
  pass; malformed, missing, foreign, stale and over-bound identities/cursors
  fail closed.
- `S/T/C`: shared state graph, terminal/outcome rules, duplicate/conflicting
  commands, concurrent create/adjust/retry, Store-owned terminal settlements
  and terminal lease races are exercised. The D-058 retry rule remains
  separately lineage-bound.
- `R`: v1/v2/v3-to-v4 paths, failpoints, semantic corruption fixtures and v4
  reopen either reconstruct exact authority or roll back without partial
  promotion. Valid control/outbox/reconciliation/retry histories reopen.
- `I`: subject/project/session/task/attempt/command/event/result/revision,
  Executor observation and outbox bindings are exact. Selection-hint changes
  cannot redirect a read or mutation.
- `F/K`: feature-off behavior, legacy pure-Core/Bridge consumers, direct
  Executor recovery and Python/TypeScript contract compatibility pass.
- `X`: authenticated composition and AgentServer product routes exercise the
  real SQLite Core/Store; formal integration tests cover disconnect/restart and
  exact cancel domains.

Rejected authorization, scope, identity, cursor, conflict, migration and
transition paths assert zero unauthorized Task/Attempt/Event/outbox/Executor,
file, Agent, Tool, presentation, history or other-scope effect where applicable.
Physical audio/device/TTS behavior is outside this Core/Store package.

## 5. Final current-source verification

| Boundary | Exact result |
|---|---|
| Migration, multi-Task, query/control, shared contract and authenticated composition | `.\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_formal_task_policy.py tests/unit_tests/common/test_live_voice_contract_v2.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py` — **376 passed**, one external Authlib deprecation warning |
| Product route, authority, subscription/projection, Executor and compatibility | `.\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/live_voice/test_product_p3_text_adapter.py tests/unit_tests/live_voice/test_product_authority.py tests/unit_tests/live_voice/test_task_event_subscription.py tests/unit_tests/live_voice/test_task_progress_return.py tests/unit_tests/live_voice/test_project_code_executor.py tests/unit_tests/live_voice/test_task_core.py tests/unit_tests/live_voice/test_voice_task_bridge.py tests/unit_tests/live_voice/test_observability.py` — **544 passed, 2 skipped**; the skips are the existing Windows symlink-platform cases and Windows junction cases pass |
| AgentServer and formal integration compatibility | `.\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q tests/unit_tests/agentserver/test_live_voice_p3_route.py tests/integration/live_voice/test_d90_formal_task_vertical.py tests/integration/live_voice/test_formal_task_executor_adapter.py tests/integration/live_voice/test_fake_verticals.py` — **62 passed** |
| TypeScript contract parity | `npm run test:live-voice-contract-v2` — **34 passed** |
| Live Voice product build | `npm run build:live-voice` — **PASS**, 4,643 modules transformed; only existing Vite dynamic-import/chunk-size warnings |
| Python static | Ruff check over all **21** changed Python files — **PASS**; Ruff format check — **19 files already formatted** plus all changed ranges in the two pre-existing globally unformatted AgentServer files; `python -m compileall -q` — **PASS** |
| Git whitespace | `git diff HEAD --check` — **PASS** |
| Independent Tier-3 complete-diff review | **PASS — no remaining P1/P2**; the reviewer also selected and reran **10 passed** authority/lease regressions |

One broader diagnostic is intentionally not converted into P3-1 credit: a
fresh `npm run test:live-voice-integrated-web` reported **406 passed, 1 failed**
in the existing mounted Exit/immediate-re-enable presentation-ACK timing test,
and the focused test reproduced it. P3-1 changes only
`liveVoiceContractV2.ts` and its contract test on the frontend; the failing
panel/test and their `liveVoiceContractV2` dependency path are unchanged from
`5787eda9`. This is recorded as an existing P1/P2 Runtime/Web continuation
residual and is not repaired or hidden by this Core/Store package. The
candidate therefore claims the affected compatibility groups above, not a new
407/407 full-Web result.

## 6. Review disposition and residual risk

The complete candidate diff rooted at `5787eda9` received an independent
Tier-3 **PASS — no blocking findings** after all review repairs. P3-1 is accepted
within its recorded Task Core/Store boundary and P3-2 may begin.

The v4 initializer currently performs a complete authority replay. Correctness
and bounded fixtures pass, but startup time on a production-sized Task database
has not been benchmarked. This is a non-blocking P3 performance/hardening item;
it must be measured before a productized/Production readiness claim.

## 7. Explicit exclusions

No deferred P1/P2 post-TTS/Exit continuation repair, microphone/TTS journey,
P3-2 successor command, P3-3 admission expansion, P3-4 D1/D2 implementation,
P3-5 unread/presentation ACK, P3-6 natural-language target disambiguation,
P3-7 multi-Task UI, P3-9 cumulative physical acceptance, Production work,
`develop` merge, remote update or push is included or claimed.
