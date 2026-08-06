# Live Voice Alpha parallel execution plan

> Accepted 2026-08-06 under D-060. This is a stable execution and ownership contract, not a mutable progress report. Current branch, HEAD, completed work, blockers and next actions remain exclusively in [STATUS](../STATUS.md).

## Outcome and guardrails

The current Main Integration Session coordinates four implementation Sessions against one dynamically resolved local baseline. Work may proceed in parallel only inside the ownership below. Main owns shared dependencies, semantic conflict decisions, cumulative integration, release evidence and the immutable Alpha candidate.

The target remains Integrated Web Alpha, not production readiness. Missing identity, credentials, Provider, secure deployment, browser/device state or real service hooks must remain fail-closed and be reported precisely. Formal, fallback, demo_substitute, unavailable and disabled route truth must not be collapsed. Browser Speech, Demo/TaskBridge and legacy JSON authority do not become formal merely because a vertical test passes. Media remains unavailable until the registered product path proves route-to-disk zero persistence. X-OBS cannot be registered until nonformal routes and worker-lease lifecycle satisfy the Composition Root invariants. Replacement credit is governed only by the acceptance contracts and current STATUS.

## Sessions and waves

| Session | Persistent ownership | First wave | Later wave after declared dependencies |
|---|---|---|---|
| Main Integration/Review | Web auth/activation owner, shared Authority/contracts, Composition, Gateway/AgentServer acknowledgement, cumulative tests/evidence/Gates | freeze this plan; create task baselines; implement shared auth/activation and delivery ACK | integrate real P1/P2/P3alpha paths, register eligible X-OBS, run joint E2E and immutable Alpha Gate |
| T1 P1 Speech/Media | browser audio, realtime media and Provider leaf Adapters | real Audio/Media/RM boundary and zero-persistence proof hooks | selected SR/SS Provider and P1 vertical after private dependencies exist |
| T2 P2 Runtime/Interaction | CR/II/AB internals and formal history/presentation ledgers | TurnCommit/PresentationAck-ready internal seam and interaction behavior | real Agent/Harness route closure and P2 vertical through Main-owned entrypoints |
| T3 P3alpha Task | Task Core/Store/Executor and confirmation/voice-policy leaf code | formal Core/Executor readiness | confirmation/mutation and text UI leaf controls after Main supplies auth/composition hooks |
| T4 Cross-cutting | X-OBS, X-WEB diagnostics and X-E2E leaf harnesses | nonformal-route and worker-lease-compatible observability | deployment/diagnostics and cumulative fault harness after integrated routes exist |

The first wave maximizes work without a shared-file dependency. Main may advance dependencies while all four Tasks implement their first wave. Later waves are released only when the named real dependency exists; a Task must not manufacture it.

## Main-only ownership

Unless Main grants a temporary explicit lease, Task Sessions must not edit:

- `AGENTS.md`, Live Voice router/status/decisions/roadmaps/reviews/evidence or acceptance/runbook documents;
- central product Composition Root, registry, contract or Authority implementations and their top-level tests;
- AgentServer/Gateway routing and shared wire message dispatch, including `agent_ws_server.py`, `message.py` and `app_web_handlers.py`;
- the top-level integrated Web panel/route, `ChatPanel`, package manifests and i18n catalogs;
- shared TypeScript composition contracts and the integrated P1 route;
- cumulative smoke/E2E/Gate evidence and the integration branch history.

Main alone decides activation order: Trusted Authority, P2 runtime/interaction, P3 authenticated query/text progress, eligible P1 Media/Provider, P3 mutation/confirmation, and finally compatible X-OBS. Authority unavailable or denied must produce zero downstream Adapter calls. Feature-off must allocate, register and call zero new objects.

## T1 P1 Speech/Media file boundary

T1 may modify the existing leaf implementations and matching focused tests for:

- Web formal audio: `audioPort.ts`, `adapters/browserAudioIOAdapter.ts`, `liveVoiceCaptureProcessor.js`, `browserGatewayMediaTransport.ts`;
- server Media: `realtime_media.py` and its leaf tests;
- after Provider selection/dependency release: `speech_ports.py`, `batch_speech.py`, dedicated Provider leaf modules, browser speech Adapters and the Gateway batch-Speech client.

T1 must not edit Main-only registry/Gateway/AgentServer/integrated-route files. The first return must identify actual transport, codec/sample facts, capture/playout lifecycle, cleanup/retry, correlation/binding behavior and every possible persistence sink. Absence of a real registered route or Provider is an `unavailable` result, not permission to add a fake product owner.

## T2 P2 Runtime/Interaction file boundary

T2 may modify matching focused tests and these leaf/runtime implementations:

- `interaction_engine.py`, `conversation_runtime.py`, `conversation_runtime_loop.py`;
- `agent_bridge.py`, `agent_bridge_runtime.py`, `agent_conversation_runtime.py`;
- `jiuwenswarm_agent_adapter.py`, `jiuwenswarm_round_harness.py`;
- `formal_history_writer.py`, `presentation_ledger.py`, `progress_notification_arbiter.py`;
- Web `conversationRuntimeReplica.ts` and its leaf tests.

T2 must preserve D-059 round authority, exact cancel, two-phase admission, presented-only text history and retained shutdown. It must not create the Main-owned Web auth/activation caller or alter central Composition/Gateway/AgentServer dispatch. The return packet must distinguish internal readiness from an actually invoked product TurnCommit/PresentationAck path.

## T3 P3alpha Task file boundary

T3 may modify matching focused tests and:

- `formal_task_models.py`, `task_core.py`, `persistent_task_core.py`, `task_store.py`;
- `executor_port.py`, `project_code_executor.py`;
- after dependency release: `p3_confirmation.py`, `voice_task_bridge.py`, `voice_task_policy.py`, `task_event_subscription.py`, `task_progress_return.py`;
- new formal task-control Web leaf files and leaf tests that do not modify Main-only integrated panels, message dispatch, package or i18n files.

T3 must preserve authenticated query, confirmation-before-mutation, idempotency, durable outbox/reconciliation and exact scope/binding rules. Until the real confirmation and mutation owner is integrated, mutation/formal voice remains unavailable. Demo TaskBridge/legacy schedule routes remain nonformal.

## T4 Cross-cutting file boundary

T4 may modify matching focused tests and:

- `observability.py`, `observability_exporter.py`, `product_observability_adapter.py`;
- Web `liveVoiceObservability.ts`, `webPlatformDiagnostics.ts`, `integratedWebRouteShell.ts`;
- new leaf diagnostics, fault-injection and E2E harness files that do not edit Main-only product entrypoints or evidence documents.

The first return must solve or precisely fail closed on nonformal-route identity and worker-lease lifetime. No exporter backend, deployment or release-Gate claim may be invented. Main alone registers X-OBS after reviewing compatibility with the actual Composition lifecycle.

## Task lifecycle and return packet

Every Task starts from the same resolved integration baseline and first reads root `AGENTS.md`, `live-voice/README.md`, `live-voice/STATUS.md`, this plan, the relevant README-routed contracts/decisions, actual source and adjacent tests. It records its base SHA and verifies its branch/worktree before editing.

Each coherent batch follows this loop:

1. Implement only the owned scope and run D-046-proportional focused, negative, feature-off and affected regression tests.
2. Perform implementation self-review against the original packet, repository rules, existing behavior and complete local diff. Leave the candidate uncommitted and report it to Main with exact files, tests, remaining unavailable hooks and exclusions.
3. Main performs a cold complete-diff review. Tier 2/3 batches also receive an independent `/review` or recorded equivalent. Findings return to the owning Task; the Task fixes them and reruns affected tests. Semantic fixes repeat the final cold review.
4. When Main declares review pass, the Task may make one final local commit, including amend/squash/rebase as needed. No Task may push.
5. Main receives branch, base SHA, final commit SHA, exact file list, test commands/results, review closure, unavailable hooks and known risks. Main may then grant the integration lease.

Test counts, mocks and contract-only verticals never constitute product acceptance. Positive routes must succeed; denied/unavailable, correlation/binding mismatch, cleanup/retry, feature-off zero side effects and fallback/Demo/legacy regressions must be covered where applicable.

## Integration lease and conflict rules

Only one Session at a time may write the integration worktree or modify its local branch history. Main grants a lease naming source branch, commit, target branch and intended merge/cherry-pick/rebase method. The lease ends when integration and affected checks complete or Main revokes it.

Mechanical conflicts inside an owned leaf may be resolved under the lease. Any semantic conflict in shared authority, protocol, lifecycle, route truth, cleanup, generation, correlation or binding returns to Main and the owning Task. Integration glue is Main-owned, must be identified separately in the review summary and may invalidate prior review if it changes semantics. Local Git operations need no further user approval under D-060; any remote ref update still requires exact separate approval.

## Cumulative closure order

Main integrates reviewed commits in real dependency order. Under D-061, it does not rerun the cumulative smoke matrix after each individual cherry-pick; it runs the matrix once after the complete reviewed integration batch has landed. A semantic conflict or integration-glue change still requires its own affected checks before the final cumulative run:

1. stock-Web activation/auth owner and trusted Alpha Authority;
2. P2 TurnCommit/PresentationAck and real AgentServer→Gateway→Web acknowledgement;
3. P3 confirmation/mutation plus authenticated query/text-progress UI;
4. registered zero-persistence Media and selected Provider/Realtime route;
5. one real P1, one real P2 and one real P3alpha vertical;
6. X-OBS only after lifecycle compatibility;
7. joint E2E on one immutable candidate;
8. Immutable Alpha Gate and only then any accepted Replacement Ledger change.

Each cumulative run covers normal package routing, authority denied/unavailable, correlation/binding mismatch, cleanup/retry, feature-off zero side effects and fallback/Demo/legacy non-regression. Missing machine-private or external dependencies leave the corresponding item open and fail-closed; they do not prevent independent owned packages from returning reviewed code.
