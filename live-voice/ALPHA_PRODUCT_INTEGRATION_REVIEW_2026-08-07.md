# Alpha product integration review — 2026-08-07

> Frozen review and verification record for local integration HEAD `0ef0f86219df7177e9027604310712dc5577749c`. Mutable route, Git and next-action facts belong only in [STATUS.md](STATUS.md).

## Candidate identity and integration method

The candidate is on local branch `codex/lv-alpha-integration`, which has no configured upstream. It starts after the D-060 governance commit `b0ecd0215eef4eefe5907fe6a39235145817823c`. At this review snapshot, the latest pushed implementation was `f742fac0`; later Git state belongs only in STATUS. No commit from this integration batch was pushed during the reviewed integration operation.

Main integrated the reviewed commits in dependency order with no cherry-pick conflict:

| Lane | Source branch and reviewed source commit | Commit on integration branch | Scope |
|---|---|---|---|
| Main | `codex/lv-alpha-integration` | `ebb4f432b7fec7580bd7c58384ceafdc1727dd2e` | stock-Web activation, bounded Gateway credential owner, AgentServer/Gateway/Web delivery acknowledgement and shared registry/UI ownership |
| P2 | `codex/lv-alpha-t2-p2-runtime` at `ea5d1b3edac00a71afd3d597faa5ebba604b8990` | `8aa59906f4af8a5343e803eea24461deeb2c2bae` | retained runtime startup/shutdown ownership |
| P3alpha | `codex/lv-alpha-t3-p3` at `86a076f0726e05ba679a08a3fd35e57396d42eb7` | `cb88f5bb3d36072723af5edc10fc5069497e1acd` | durable task-outbox binding validation and reconciliation hardening |
| P1 | `codex/lv-alpha-t1-p1-media` at `2c586f75309d237956eeaddbb2e2131f709992c0` | `9724149b0662e6fc2db292f4618851a92b7d9bfc` | bounded in-memory Media frame/payload ownership and close semantics |
| X-OBS | `codex/lv-alpha-t4-xobs-lifecycle` at `9a05ce232bff4b2b24e18a115918bbee5838f379` | `0ef0f86219df7177e9027604310712dc5577749c` | retained observability worker-lease ownership |

D-061 was applied: Main did not run the cumulative smoke after each conflict-free cherry-pick. It ran one cumulative matrix after all four reviewed Task commits had landed.

## Exact implementation scope

The cumulative code/test diff from D-060 governance commit `b0ecd021` to tested HEAD `0ef0f862` contains these files:

- Web: `package.json`, `LiveVoiceIntegratedRoutePanel.tsx`, `ChatPanel/index.tsx`, `productTextProgress.ts`, new `productWebActivation.ts`, English/Chinese locale JSON, and the three adjacent Integrated Web test files.
- Gateway/shared/server registration: `message.py`, `app_gateway.py`, `app_web_handlers.py`, `web_connect.py`, `agent_ws_server.py`, and `product_composition_registry.py`.
- Owned leaf packages: `agent_conversation_runtime.py`, `task_store.py`, `realtime_media.py`, and `product_observability_adapter.py`.
- Backend tests: affected AgentServer, Gateway, WebChannel, product registry, conversation runtime, persistent Task Core, Media and observability suites.

No legacy `useLiveVoiceDemo`, frontend TaskBridge, legacy `schedule.*` authority or provider credential file was promoted into the formal route.

## Actual product paths integrated

### Default-off stock-Web owner and bounded Alpha Authority

- Existing Integrated Web feature selection creates one stable panel owner across the first-message transition. Disabled mode does not allocate the new activation owners.
- Gateway removes any browser-supplied `auth_token`. Only when `JIUWENSWARM_LIVE_VOICE_WEB_ALPHA_CREDENTIAL_ENABLED` is enabled does it inject the server-held `JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN`, and only for the bounded read-only query, P2 lifecycle, P3 progress lifecycle and progress-ACK method set. Create/cancel mutation is excluded.
- AgentServer and the central registry remain independently default-off behind `JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED`; P2 and P3 text have their own segment flags. Authority is revalidated before protected downstream work.
- The authority source remains the existing Alpha bearer plus server Session/Project registry. Browser identity fields remain comparison claims. This is not production user identity or Provider authority.

### P2 activation and retained cleanup

- Stock Web owns exact `session_id`, `correlation_id`, `interaction_id`, `activation_id` and `activation_generation` activation/close bindings.
- Successful activation reaches the existing Authority-first central registry and real AgentManager/runtime/interaction allocation path.
- Ambiguous transport outcomes retain cleanup ownership and expose `cleanup_pending`; bounded close retry observes one retained result. Authoritative denied, disabled or unavailable outcomes remain `unavailable` and do not fabricate a cleanup lease.
- Runtime startup rollback and shutdown are retained against caller cancellation/timeout. These changes harden lifecycle truth but do not add the missing TurnCommit or PresentationAck caller.

### P3 authenticated query, UI progress and exact acknowledgement

- Stock Web uses the authenticated formal task-list route and activates progress only when exactly one nonterminal task can be selected. P3 close waits for an in-flight selection before deciding cleanup.
- AgentServer→Gateway→Web preserves the full progress payload and exact session/task/correlation/origin/generation/delivery/scope binding.
- The Web consumer fences stale owner/session deliveries, projects monotonic progress and sends one exact delivery acknowledgement with retry. Server acknowledgement requires the retained delivery identity and binding; acknowledged tombstones survive route cleanup long enough for safe replay.
- Durable Task Core outbox reads/reconciliation now validate the exact stored binding and fail closed on mismatch.
- This acknowledgement proves that the bounded Web software owner accepted the exact delivery. It does not prove human observation, task mutation, voice presentation or a real browser/service journey.

### P1 Media and X-OBS lifecycle hardening only

- Realtime Media now bounds in-memory frame/payload ownership, validates exact track/epoch bindings, serializes close against an in-flight enqueue, exposes payload-free counters and closes synchronously and idempotently. It does not implement activation/startup, partial-start rollback or time-bounded asynchronous cleanup. The Composition Root still returns Media `unavailable` because no registered route-to-disk test proves zero raw-audio persistence.
- X-OBS retains its worker lease and teardown truth under cancellation/timeout. It remains unregistered: nonformal route truth has not yet been reconciled with Composition registration, and no exporter consumer/transport, retention policy or SLO backend exists.

## D-046/D-053 review closure

- Each Task lane completed its owned implementation review and returned one final local commit only after review pass. Main inspected source branch, exact commit, file scope, tests and retained unavailable hooks before granting each integration lease.
- Main implementation self-review and repeated complete-diff cold review covered the original request, default-off allocation, Authority-first effects, exact binding/generation/correlation, cleanup/retry, fallback/Demo isolation and truthful route states.
- The independent Main review found and drove fixes for full progress payload preservation, P3 Web ownership, lost close-response reconciliation, ACK retry/tombstones, exact event binding, panel-owner stability, stale-session fencing, bounded generation retention, in-flight task selection, retained close retry and ambiguous-versus-authoritative activation classification. Affected tests were rerun after fixes.
- After those fixes, the independent reviewer returned exact `PASS`. No `/review` availability was fabricated; the repository session's independent review agent was the recorded equivalent.
- Cherry-picks were conflict-free and introduced no integration glue. The cumulative post-integration smoke below passed at exact HEAD `0ef0f862`.

## Post-integration cumulative verification

| Verification | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q tests/unit_tests/live_voice tests/unit_tests/gateway/test_app_gateway_acp.py tests/unit_tests/channel/test_web_channel_symphony_status.py tests/unit_tests/agentserver/test_live_voice_p3_route.py` | `845 passed in 96.38s` |
| `npm run test:live-voice-integrated-web` | `63/63 PASS` |
| `npm run test:live-voice-task-bridge` | `49/49 PASS` |
| `npm run test:live-voice-task-client` | `17/17 PASS` |
| `npm run test:live-voice-task-adapter` | `19/19 PASS` |
| `npm run test:live-voice-task-monitor` | `23/23 PASS` |
| `npm run test:live-voice-core` | `9/9 PASS` |
| `npm run build` | PASS (`tsc && vite build`) |

Before the Main commit, the affected registry/static checks also passed: scoped Ruff, isolated registry Mypy and `git diff --check`. The production build retained existing non-blocking warnings for stale Browserslist data and large Vite chunks. Test counts describe automated coverage only; they do not constitute a real browser/device/Provider/service E2E or an acceptance Gate.

The applicable suites cover positive package routing, authority denied/unavailable, correlation/binding mismatch, cleanup/retry and cancellation races, feature-off zero side effects, and fallback/Demo/legacy non-regression. No real Provider cost, microphone/audio device, deployed service, human UI observation or production identity was exercised.

## Unavailable boundaries and next dependency order

1. P2 TurnCommit and PresentationAck/history need a real stock-Web/Agent product caller. Until then there is no complete Agent/Tool vertical.
2. P3 mutation requires a trusted confirmation issuer and bounded create/cancel reconciliation owner. Formal voice additionally requires an atomic TaskEvent/projection authority handoff.
3. Media requires a real activation/startup owner, registered route-to-disk zero-persistence evidence, selected Provider and realtime transport/codec before P1 can become formal.
4. X-OBS registration requires Composition-compatible route truth plus a real exporter consumer/transport, retention policy and SLO backend.
5. Real P1/P2/P3alpha verticals, one joint desktop-Chrome/service E2E and the Immutable Alpha Gate remain open.

Media remains `unavailable`; X-OBS remains unregistered; mutation and formal voice remain fail-closed. The Integrated Demo is not runnable, no production-ready claim is made, and the Replacement Ledger remains `0/100`.
