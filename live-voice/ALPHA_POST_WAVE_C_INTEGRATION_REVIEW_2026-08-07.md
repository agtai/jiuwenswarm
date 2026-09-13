# Alpha post-Wave-C integration review — 2026-08-07

> Frozen implementation, review and automated-verification record for tested local code `83aace72462cd15bd6e13e6eb0221204b5b4c623`. Mutable route, Git and next-action facts belong only in [STATUS.md](STATUS.md).

## Candidate identity and integration method

This continuation recovered Git before trusting the earlier Wave C prose. Local `hx/0803_live_voice` and `codex/lv-alpha-wave-c-integration` were already at Wave C documentation closure `41a05d79a482c4e2660ff18854c58975d9eb0479`; `origin/hx/0803_live_voice` remained `107104bb22b9cfc705b02634a4eaf86d1d64f3bf`. Main created `codex/lv-alpha-next-integration` from the actual local baseline and did not update `hx/0803_live_voice` during this batch.

Main used declared single-writer leases and cherry-picked three reviewed local Task commits. No branch was pushed and no remote ref was created, changed or deleted.

| Scope | Source branch and commit | Integrated commit | Risk | Exact files |
|---|---|---|---|---|
| P2 dependency readiness | `codex/lv-alpha-next-p2-readiness` at `809bb773f43077c4ce4e136fc715a9cb1cf6fbc7` | `dd8ae3c7ca075f03e5a06636c6949f8704509c51` | Tier 1 | `product_p2_readiness.py` and its unit test |
| Web deployment preflight | `codex/lv-alpha-next-deployment-preflight` at `9d0a919164e2773a8c2b69cd97d89239db7295de` | `6987c8ee20a8ec92bf5a91dd0323577896749c9f` | Tier 1 | `live_voice_deployment_preflight.py` and its unit test |
| P3 Task progress sequence closure | `codex/lv-alpha-next-p3-sequence` at `02bca9450f594d4601c7bdb59ebea0be4a31fcca` | `83aace72462cd15bd6e13e6eb0221204b5b4c623` | Tier 3 | arbiter, Task progress bridge and two adjacent tests |

The tested code range is `41a05d79..83aace72`: eight files, 2,554 insertions and nine deletions. The eventual documentation commit is intentionally outside that tested-code identity.

## Implementation result

### P2 dependency readiness

The new evaluator consumes a closed set of explicit `SATISFIED`, `UNSATISFIED` or `UNKNOWN` facts for product flags, authority, project/session/model/Agent-Tool carriers, service listeners and `connection.ack`. It returns one stable prioritized reason without discovering configuration or reflecting values. Even a positive result is limited to declared dependencies: `real_e2e_observed` is fixed false and `gate_claim` is fixed `NONE`.

This is a diagnostic leaf only. It is not wired into product Composition, does not read credentials or configuration, does not start services and does not prove a browser Agent/Tool journey.

### Deployment configuration preflight

The new pure evaluator checks explicit public-origin, WebSocket, allowed-origin, CORS credential, CSP `connect-src`, proxy Upgrade, TLS termination and bounded owner-label facts. Non-local public traffic requires HTTPS/WSS. A controlled localhost HTTP/WS exception must be explicit. Duplicate or overbroad origins, wildcard-with-credentials, origin mismatch, unknown proxy/TLS ownership and invalid carrier types fail closed.

`configuration_ready` means only that caller-supplied configuration facts are mutually consistent. `real_deployment_observed` and `formal_deployment_ready` remain false. The evaluator performs no environment, socket, file or log discovery and grants no Composition authority.

### P3 no-projection sequence closure

The exact SQLite TaskEvent authority bridge can now account for canonical attempt/control events that intentionally produce no `WorkProgress`. Under one arbiter lock, an internally minted, event-and-binding-bound capability validates the complete `PersistentTaskEvent` and then advances source, progress-envelope and work-projection sequence ledgers together. It creates no pending notification, delivery decision, lifecycle transition, acknowledgement candidate or sink effect.

The capability constructor, mint and advance method are package-private and absent from `__all__`. Only the exact `TaskEventAuthorityProgressSource` production bridge path calls them after close/state, authorization and generation checks. Package-test sources and ordinary callers cannot claim the formal no-projection path.

Projected Task source envelopes now use stable component `task_core` for the shared authoritative sequence. The original Store producer, including `task_core.delivery` or `task_core.reconciliation`, remains preserved in the typed extension as provenance. A real temporary-SQLite reconciliation journey verified TaskEvent sequence `0..5`: projected voice intents `[0, 3, 5]`, no-projection advances for attempt events `1`, `2` and `4`, terminal closure, and no observer-side Store mutation.

This closes the package sequence gap identified by Wave C. It does not register formal P3 voice in product Composition and does not supply CR/Media, a real Code project/model/Executor or a browser journey.

## Review closure

The P2 and deployment Tier 1 leaves completed implementation self-review and Main cold complete-diff review. Main findings on the deployment evaluator required exact boolean/result carriers, duplicate-origin rejection and exact-type-first validation; the final focused suites passed after correction.

The P3 Tier 3 batch completed all three D-053 passes: implementation self-review, repeated Main cold complete-diff review and an independent read-only equivalent. Findings fixed before commit included:

- caller-supplied opaque bytes did not prove a complete canonical TaskEvent;
- a public constructible advance could bypass the exact authority bridge;
- delivery/reconciliation terminal producers could create a false new source stream and sequence gap;
- the stable no-projection source component needed exact `task_core` validation;
- the final four files initially needed Ruff formatting after the last semantic fix.

The independent final review used diff hash `fba5cf5019c36cfc1700bfac3d11a37c4a47d2aa`, returned PASS with no P0–P3 finding, ran the two-file focused suite and the full backend `tests/unit_tests/live_voice` selection, and made no repository change. Literal `/review` was unavailable, so this is recorded as an independent equivalent rather than a claim that `/review` ran.

## Automated verification

| Verification | Result |
|---|---|
| P2 readiness focused suite | `42/42 PASS` |
| deployment preflight focused suite | `22/22 PASS` |
| P3 final focused arbiter/bridge suite | `89/89 PASS` |
| independent full backend `tests/unit_tests/live_voice` | `912/912 PASS` on the P3 Task branch |
| integrated backend Live Voice/Gateway/Web/AgentServer selection | `1069/1069 PASS` |
| `npm.cmd run test:live-voice-integrated-web` | `83/83 PASS` |
| `npm.cmd run test:live-voice-task-bridge` | `49/49 PASS` |
| `npm.cmd run test:live-voice-task-client` | `17/17 PASS` |
| `npm.cmd run test:live-voice-task-adapter` | `19/19 PASS` |
| `npm.cmd run test:live-voice-task-monitor` | `23/23 PASS` |
| `npm.cmd run test:live-voice-core` | `9/9 PASS` |
| frontend production build | PASS: TypeScript + Vite, 4,507 modules transformed |
| Ruff check/format, `py_compile`, `git diff --check` | PASS |

The six frontend suites total `200/200 PASS`. The build retained the known non-blocking stale-Browserslist and large-chunk warnings. The first parallel backend invocation's terminal result was not retained by the orchestration output window; with no code change and the same `83aace72` HEAD, the exact backend selection was rerun with live logging disabled and returned exit code zero. A collection-only check recorded 1,069 selected tests.

Automated verification is software evidence only. No real Provider, physical browser/device, Agent/Tool service, Task Executor, secure deployment or observability backend journey ran.

## Forbidden-effect assertions

- Both readiness evaluators perform no file, environment, process, network, credential, service, Provider, model, Tool, registration or log discovery.
- Feature-off returns before inspecting downstream facts; invalid and unknown inputs return closed, content-free reasons.
- Invalid no-projection event, scope, task, correlation, producer, lifecycle, binding, gap, conflict, capacity, terminal, close or generation paths advance no sequence ledger partially and create no pending, decision, lifecycle, ACK, sink or Store mutation.
- A no-projection event cannot create accepted work, extend a terminal lifecycle or be reclassified later as a projected source event.
- Product Media, formal P3 voice and X-OBS registrations remain unchanged and unavailable where their real dependencies are absent.

## Read-only dependency preflight and retained blockers

| Area | Current classification |
|---|---|
| Speech Provider choice | `PRODUCT_DECISION_REQUIRED`: the concrete Adapter is batch STT/TTS; no streaming Provider target is selected |
| Provider runtime configuration | `MACHINE_PRIVATE_INPUT_REQUIRED`: credentials, API base and model configuration must remain server-side and were not read |
| registered Media route | `IMPLEMENTATION_HOOK_MISSING`: central registry remains `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN` |
| P2 real Agent/Tool browser journey | `MACHINE_PRIVATE_INPUT_REQUIRED`: no registered project-bound session, model runtime or running services were available |
| P3 real mutation/Executor journey | `MACHINE_PRIVATE_INPUT_REQUIRED`: a disposable registered Code project, model/configuration and runnable Executor are absent |
| Code Agent support-path policy | `PRODUCT_DECISION_REQUIRED`: relocate or explicitly govern `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` |
| deployment policy/owner | `PRODUCT_DECISION_REQUIRED`: select the HTTPS/WSS proxy and allowed-origin owner |
| deployment runtime configuration | `MACHINE_PRIVATE_INPUT_REQUIRED`: provide TLS, proxy, CSP/CORS, Upgrade and origin facts; the evaluator did not discover them |
| X-OBS backend | `PRODUCT_DECISION_REQUIRED` plus `MACHINE_PRIVATE_INPUT_REQUIRED`: select backend/transport, retention/redaction, retry/shutdown and SLO policy, then configure it |
| desktop Chrome/device journey | `PHYSICAL_USER_ACTION_REQUIRED`: microphone/output selection, permission/revoke, autoplay, device-loss, background/resume and reconnect require a human-run session |

The read-only preflight observed no registered Code project, no project-bound persisted session, no declared model runtime, no relevant product flags in the shell and no listening services on the checked local ports. Configuration files may exist, but their secret values were not read. A listening port alone would not prove health; the product `connection.ack` remains the relevant application-level truth.

## Gate and release truth

This candidate completes all dependency-independent work identified in this continuation and keeps every missing external path fail-closed. It does not make Integrated Demo runnable, does not pass Web Alpha, does not establish production readiness and earns no Replacement Ledger credit. The ledger remains `0/100`; no immutable Alpha Gate was run.

The reviewed candidate stops locally. No push or remote-ref update occurred. Any later integration of this reviewed branch into another local branch, and any later remote update, remains a separate user decision under the current Git governance.
