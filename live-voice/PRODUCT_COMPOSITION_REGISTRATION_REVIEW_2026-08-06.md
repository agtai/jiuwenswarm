# Product composition registration review — 2026-08-06

## Status and scope

This record covers the uncommitted Tier 3 product-registration candidate on `hx/0803_live_voice`, based on committed and pushed foundation HEAD `9adcc4ccdcf1f922f01dcf9c16aa8bdcf3c3035c`. Git reports the branch upstream as `agtai/hx/0803_live_voice`; the candidate is not staged, committed or pushed.

The implementation changes are limited to the AgentServer-owned registry, the existing authenticated P3 owner, the Web/Gateway RPC boundary, the text-progress Web consumer and their affected tests:

- `jiuwenswarm/server/live_voice/product_composition_registry.py`
- `jiuwenswarm/server/live_voice/p3_authenticated_composition.py`
- `jiuwenswarm/server/live_voice/task_progress_return.py`
- `jiuwenswarm/server/agent_ws_server.py`
- `jiuwenswarm/common/schema/message.py`
- `jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py`
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts`
- `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.css`
- `jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json`
- `jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json`
- `jiuwenswarm/channels/web/frontend/package.json`
- `tests/unit_tests/live_voice/test_product_composition_registry.py`
- `tests/unit_tests/live_voice/test_p3_authenticated_composition.py`
- `tests/unit_tests/live_voice/test_task_progress_return.py`
- `tests/unit_tests/agentserver/test_live_voice_p3_route.py`
- `tests/unit_tests/agentserver/test_ws_send.py`
- `jiuwenswarm/channels/web/frontend/tests/productTextProgress.test.mjs`
- `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs`

## Actual registered product paths

- `JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED` is the default-off process gate. AgentServer tests this gate before importing the registry factory. When it is off, no registry, package Adapter, registration or worker is constructed or called.
- When the master gate is on, the existing P3 Alpha static bearer authenticator and server-owned Session/Project registry are the only trusted Authority source. Request user/project fields are comparison claims only. This is an Alpha authority bridge, not production identity.
- AppGateway forwards four new lifecycle methods without a local fallback handler: P2 activate/close and P3 text-progress activate/close. AgentServer owns their dispatch, retained leases and disconnect/stop cleanup.
- P2 activation, behind its own default-off flag, resolves Authority before AgentManager allocation, pins the real JiuwenSwarm facade, opens `AgentConversationRuntime` plus the Interaction Engine, and retains exact interaction/activation/generation cleanup ownership. Replay, close, denied authority and binding mismatch revalidate Authority first.
- Existing authenticated read-only `live_voice.task.get/list/status/events` requests use the central P3 query registration when the P3 text segment flag is on. The real authenticated composition revalidates the server Session/Project context before entering the persistent Task Core. Existing create/cancel mutation handling is deliberately not promoted into the central read-only Adapter.
- P3 text progress opens an exact live `TaskEventSubscription`, preserves scope/task/correlation/origin/generation bindings, projects only canonical events and pushes `live_voice.task.progress` through AgentServer to Gateway. The Integrated Web panel consumes only an exact four-field authenticated ScopeRef and a monotonic retained binding. A settled/failed worker cannot replay as active; cleanup remains retryable.
- The root continues to report Media as `unavailable` with `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN`, P3 control as `unavailable` with `P3_CONFIRMATION_ISSUER_UNAVAILABLE`, and X-OBS as `ADAPTER_NOT_REGISTERED`. Existing fallback and D-047 Demo substitutes are not selected, mutated or reclassified.

## Verification

- Final cumulative focused Python suite: **422 passed**, with one dependency deprecation warning. It covers Gate-0/Authority/root, P2 runtime and interaction, P3 query/progress, cleanup/retry/races, X-OBS package behavior, dedicated Media unavailable behavior, AgentServer/Gateway forwarding and feature-off zero effects.
- Shared contract and deterministic fake verticals: **95 passed**.
- Integrated Web parser/panel: **37 passed**. Existing Live Voice core and Demo/TaskBridge regressions: **117 passed** (`9 + 49 + 17 + 19 + 23`).
- Scoped Mypy passed for the three changed Live Voice backend owners. Ruff passed for the changed Python scope; `agent_ws_server.py` was checked with its pre-existing `E402` import-placement finding ignored. Frontend `tsc --noEmit` and `git diff --check` passed.
- No real browser, device, Provider, deployed service, production identity, route-to-disk or aggregate Integrated journey was run.

## D-053 review

- Implementation self-review fixed Authority bypass on replay/close, lower-owner shutdown after failed product cleanup, per-operation P3 field closure, and P2 runtime identity collision risk. Affected tests were rerun after each fix.
- The complete-diff cold review was repeated after semantic changes. It found no remaining local issue after the final fixes and cumulative rerun.
- The independent review equivalent initially found two issues: settled/failed progress workers could replay as active, and the Web consumer did not retain the complete authenticated scope/binding. Both were fixed. A focused independent recheck confirmed both findings closed and reported no regression.

## Exact limits and next boundary

This batch creates source-integrated, default-off product routes, not a production-ready voice flow or an accepted Integrated Demo. The stock Web frontend has no safe bearer-token provisioning or product activation owner. P2 has no committed `TurnCommit`/PresentationAck caller, so no real Agent/Tool journey was demonstrated. AgentServer socket-write success is not a Gateway/Web UI delivery acknowledgement, and no single test traverses AgentServer → Gateway MessageHandler → WebChannel → `webClient` → panel.

P3 mutation/confirmation and formal voice remain unavailable. X-OBS remains unregistered until its nonformal-route/worker-lease lifetime is compatible with the root. Media remains unavailable until a registered real route-to-disk regression proves zero raw-audio persistence. Speech Provider, credentials, browser/device evidence, deployment and Release Gate work are not included. This candidate earns no Replacement Ledger credit.
