# Live Voice Web Alpha Delivery and Replacement Matrix

> Frozen plan date: 2026-08-05
>
> Product carrier decision: [D-055](../decisions/DECISIONS.md)
>
> Milestones, scoring and risk tiers: [POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md)
>
> Current implementation state, blockers, tested facts and next action: [STATUS.md](../STATUS.md)
>
> Week 2 pass/fail: [INTEGRATED_DEMO_ACCEPTANCE.md](../validation/INTEGRATED_DEMO_ACCEPTANCE.md)
>
> Week 3–4 pass/fail: [ALPHA_ACCEPTANCE.md](../validation/ALPHA_ACCEPTANCE.md)

## 1. Purpose and reading contract

This dated matrix gives people one readable view of what the current Demo routes do, which formal module must replace each route, and how the 28 core-module packages plus three cross-cutting packages fit into Web Alpha. It gives an Agent stable IDs, ownership, dependencies, target windows, package timeboxes, risk tiers and acceptance authorities from which to prepare the next bounded implementation plan.

This file is **not** a second status page or an implementation-ready queue:

- `STATUS.md` alone says whether a package is not started, partial, blocked, committed or verified. Every row here therefore uses `see STATUS` rather than copying live state, HEAD, test counts, scores, blockers or next actions.
- A target window is an ordering goal (`W2`, `W3`, `W4`, `Later`), not a promised calendar date. A package timebox preserves the original one-engineer/available-dependency estimate and cannot be added mechanically under the current single GPT/Sol lane.
- Risk tiers are the default classification for the package boundary shown here. The actual diff may raise the tier when it introduces authority, security, concurrency, durability or release risk; a row never lowers D-046/D-053 requirements.
- The immutable [2026-07-30 full solution](../architecture/FULL_SOLUTION_2026-07-30.md) remains the historical architecture snapshot. D-055 changes its Windows carrier interpretation; the [ACG](../architecture/ARCHITECTURE_CONTRACT_GATE_V1.md) remains the normative shared contract.
- A package may start only after STATUS says its dependencies are satisfied and a bounded plan identifies exact source/tests, allowed and forbidden effects, evidence and exclusions. A row in this matrix never means `READY` or `PASS` by itself.

## 2. Web Alpha scope shared by every package

- Carrier: JiuwenSwarm desktop Web frontend. X-WEB must freeze the exact single-Chromium or Chrome+Edge dual-Chromium baseline before its real Gate; current Chrome evidence does not silently promise Chrome+Edge coverage.
- Deployment: `localhost` is a development/controlled-test exception; non-localhost Alpha evidence requires a secure context and a declared Browser↔Gateway deployment/proxy path.
- Security: Speech/model Provider credentials stay behind Gateway/AgentServer; raw audio is not persisted by default.
- Web behavior: permission grant/deny/revoke, device change/loss, autoplay/user activation, page hidden/background/resume, refresh/reconnect, CSP/CORS/proxy diagnostics and text fallback are explicit evidence, never silent assumptions.
- Deferred compatibility: mobile Web, PWA, browsers outside the later accepted Alpha baseline and a public cross-platform matrix are Later unless a newer accepted decision changes scope.
- Deferred implementation choices: AudioWorklet/MediaRecorder, media encoding/rate/frame, WebSocket/WebTransport and selected real Speech Provider must be frozen by their consuming B/C package before real integration.
- Shared invariants: committed-only side effects, exact identity/scope, four non-escalating cancel scopes, generation fencing, presentation truth, Task/Core/Executor authority and flag-off text compatibility remain unchanged by the Web carrier.

## 3. Classification and package notation

Current implementation class uses only the project vocabulary:

- `formal`: the target module owns the route and required evidence exists;
- `fallback`: a declared compatible route behind the formal Port;
- `demo_substitute`: demonstrates value but does not own the target authority;
- `unsupported`: the route/capability is not implemented or not promised;
- `unknown`: evidence cannot establish which implementation or fact applies.

`demo_substitute` is the serialized telemetry value; “Demo substitute” is only its human-readable label. Classification is relative to the formal Live Voice route being replaced: the existing text Chat/E2A path remains a valid product path while acting as a Live Voice fallback until AB owns the formal mapping.

Package suffixes keep their original meaning:

- `A`: contract, Port/types, fake and conformance foundation;
- `B`: first real Adapter/runtime/store/integration path;
- `C`: completion, fault/race/performance or advanced integration required by the Alpha slice.

Stable IDs such as `AIO-B` and `RM-B` are not mechanically renamed with `-Web`. `X-WEB` is the only new platform package and explicitly supersedes historical `X-WIN`.

## 4. Current Demo to formal Web Alpha replacement

| Current implementation | Class | Current user value | Main limitation | Formal owner and package | Target window | Replacement condition | Disposition after replacement |
|---|---|---|---|---|---|---|---|
| Browser `SpeechRecognition` in the Live Voice Demo | `fallback` | Real microphone speech becomes committed text | No formal streaming cursor/session provenance; technical-term quality depends on browser service | AIO + SR: `AIO-B/C`, `SR-B/C` | W2–W3 | Real selected Speech route passes commit/cancel/permission/quality evidence through formal Ports | Keep as visible fallback |
| Browser `speechSynthesis` and Demo chunk queue | `fallback` | Truthful Agent responses are spoken | No Provider audio-byte provenance, reliable streaming chunk cursor or formal playout ACK | SS + AIO: `SS-B/C`, `AIO-C` | W2–W3 | Formal TTS and browser playout ACK/stop path passes stale/cancel evidence | Keep as visible fallback |
| Local `responseEpoch`, message selection and TTS ownership | `demo_substitute` | Reduces stale/duplicate local output | Browser-process protection is not canonical response/generation or presented-history authority | CR + AIO/SS: `CR-B/C`, `AIO-C`, `SS-C` | W2–W3 | Runtime generation fence and surface presentation ledger own all UI/audio application | Shrink to UI replica/compatibility shell |
| Supplement ACK quarantine | `demo_substitute` | Hides some late legacy frontend output after correction | Gateway ACK does not prove Agent, Tool or side effects stopped | CR + AB: `CR-B`, `AB-B` | W2–W3 | Exact response/round lifecycle and late-event fence replace ACK inference | Retain only bounded legacy compatibility, then remove |
| Existing text Chat/E2A direct Agent path | `fallback` | Real Agent/Tool execution and truthful text result | No real-time media or formal non-blocking WorkProgress mapping | AB: `AB-A/B` | W2 | Formal Agent Bridge maps committed Turns and source-backed progress without blocking media | Keep as text fallback |
| `schedule.*`, JSON task store and frontend TaskBridge | `demo_substitute` | Creates and observes one real background task | Not formal Task Core/Event Store/Executor authority; page-memory command state | TC + ED + VB: `TC-B/C`, `ED-B`, `VB-B/C` | W2–W3 | Formal Core owns command/task/event/attempt; legacy scheduler is only an Executor Adapter | Scheduler may remain behind ED; Bridge authority removed |
| D-031 single-task polling monitor | `demo_substitute` | Returns one task's real status/result without blocking voice | No event subscription, durable recovery or multi-task control; execution target currently unbound | TC + VB: `TC-C`, `VB-C` | W2–W3 | Source TaskEvent/WorkProgress route provides exact status/result and terminal notification | Remove or retain only as short fallback |
| Existing route labels and component logs | `demo_substitute` | Shows some route and failure facts | No complete correlated trace, metric or benchmark coverage | X-OBS | W2–W3 | Every scored segment and fault is correlated and reproducible | Evolve into formal observability |
| Historical Desktop/WebView2 productization plan | `unsupported` | No current product route | Carrier was superseded before Alpha implementation | X-WEB | W2–W4 | Web platform Gate passes on the declared candidate and deployment | Keep historical plan only; do not implement X-WIN |

Current source examples are [useLiveVoiceDemo.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts), [liveVoiceTaskBridge.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskBridge.ts), [agent_ws_server.py](../../jiuwenswarm/server/agent_ws_server.py) and [AutoHarness service.py](../../jiuwenswarm/agents/harness/common/auto_harness/service.py). These links identify predecessors, not future ownership.

## 5. P1 Speech I/O work packages

| WP | Module | Deliverable and user-visible result | Demo predecessor → formal target | Dependencies / parallel work | Window / timebox | Risk / acceptance | Current status |
|---|---|---|---|---|---|---|---|
| `AIO-A` | Audio Device & I/O | AudioFrame/PlaybackControl Port, clocked fake and conformance; later browser adapters share one contract | `unsupported` formal Audio Port → AIO authority | ACG Identity/Clock/Audio/Error; parallel SR-A/SS-A/RM-A | W1 / `0.5–1d` | T1; ACG + module conformance | see STATUS |
| `AIO-B` | Audio Device & I/O | Browser capture/playout, permission/device lifecycle and declared processing path | Browser Demo capture `fallback` → formal browser AIO Adapter | AIO-A; parallel SR-B/SS-B/RM-B/X-WEB | W2–W3 / `2–3d` | T2; P1 + Web Alpha Gate | see STATUS |
| `AIO-C` | Audio Device & I/O | Exact-response hard-stop, device/permission/page-lifecycle failures and measured Web baseline | Local TTS stop `demo_substitute` → AIO playback authority | AIO-B + fake/real Runtime control; parallel SS-C/CR-B | W3 / `0.5–1d` | T2; P1/P2 + Web Alpha Gate | see STATUS |
| `SR-A` | Speech Recognition | Provider-neutral batch/stream/cancel/capability/error Port and fake | Browser recognition `fallback` → formal SR Port | ACG Speech/Commit/Error; parallel SS-A/AIO-A | W1 / `0.5–1d` | T1; ACG + SR conformance | see STATUS |
| `SR-B` | Speech Recognition | P1 batch STT Adapter, Browser fallback and Gateway Speech RPC | Direct Browser final `fallback` → formal batch SR route | SR-A; parallel AIO-B/SS-B/text regression | W2 / `1–2d` | T1; P1 + Week 2 Gate | see STATUS |
| `SR-C` | Speech Recognition | First selected streaming STT Adapter with ordered partial/final/cancel and quality/latency baseline | Browser recognition `fallback` → formal streaming SR route | SR-A + Provider decision/capability; parallel II-B/RM-B | W3 / `2–3d` | T2; P2 + Web Alpha Gate | see STATUS |
| `SS-A` | Speech Synthesis | Provider-neutral batch/stream Port, audio-chunk provenance and fake | Browser synthesis `fallback` → formal SS Port | ACG Speech/Identity/Cancel; parallel SR-A/AIO-A | W1 / `0.5–1d` | T1; ACG + SS conformance | see STATUS |
| `SS-B` | Speech Synthesis | P1 batch TTS Adapter, Browser fallback and Gateway Speech RPC | Direct `speechSynthesis` `fallback` → formal batch SS route | SS-A; parallel AIO-B/SR-B/text regression | W2 / `1–2d` | T1; P1 + Week 2 Gate | see STATUS |
| `SS-C` | Speech Synthesis | First streaming TTS Adapter, chunk cancel/stale rejection and playout quality baseline | Demo chunk queue `demo_substitute` → formal streaming SS route | SS-A + Provider decision/capability; parallel II-B/RM-B/AIO-C | W3 / `2–3d` | T2; P2 + Web Alpha Gate | see STATUS |

## 6. P2 Realtime Conversation work packages

| WP | Module | Deliverable and user-visible result | Demo predecessor → formal target | Dependencies / parallel work | Window / timebox | Risk / acceptance | Current status |
|---|---|---|---|---|---|---|---|
| `RM-A` | Realtime Media | MediaSession/AudioFrame/ACK/control types, fake transport and backpressure conformance | Chat JSON has no media route `unsupported` → RM transport contract | ACG Identity/Media/Cancel/Error; parallel AIO-A/CR-A | W1 / `0.5–1d` | T1; ACG + RM conformance | see STATUS |
| `RM-B` | Realtime Media | Browser↔Gateway bidirectional media, bounded queues and ACK/backpressure | No real media path `unsupported` → formal RM route | RM-A + AIO-A + transport/codec decision; parallel CR-B/SR-C/SS-C | W2–W3 / `2–3d` | T2; P2 + Web Alpha Gate | see STATUS |
| `RM-C` | Realtime Media | Drop/reorder/corruption/disconnect/close matrix and network-tier measurements | No real media fault path `unsupported` → hardened RM route | RM-B; parallel CR-B/II-B fault work | W3 / `0.5–1d` | T2; P2 fault + Web Alpha Gate | see STATUS |
| `CR-A` | Conversation Runtime | Canonical interaction/turn/response reducer, ID binding and cancel/effect routing | Local Demo states `demo_substitute` → CR authority | ACG Identity/State/Cancel; parallel RM-A/II-A/AB-A | W1 / `2–3d` | T2; CR conformance | see STATUS |
| `CR-B` | Conversation Runtime | Realtime event loop, barge-in, generation fence and presented ledger | `responseEpoch`/quarantine `demo_substitute` → CR authority | CR-A; fake upstreams first; parallel RM-B/II-B/AB-B | W2 / `3–4d` | T2; P2 + Week 2 Gate | see STATUS |
| `CR-C` | Conversation Runtime | WorkProgress notification arbitration and responsive interaction under background load | Demo direct task/status speech `demo_substitute` → CR notification authority | CR-A + WorkProgress; parallel AB-B/VB-C, then real integration | W3 / `2–3d` | T2; joint P2/P3alpha Gate | see STATUS |
| `II-A` | Interaction Intelligence | InteractionEngine/Action Port, fake Cascade and common golden evaluation | Demo timers/handlers `demo_substitute` → II policy Port | ACG Speech/Interaction/Fence/Capability; parallel CR-A/SR-C/SS-C | W1 / `1–2d` | T1; II conformance | see STATUS |
| `II-B` | Interaction Intelligence | Cascade orchestration, VAD/EOT and short-granularity turn policy | Browser end/silence heuristics `demo_substitute` → formal Cascade | II-A + fake Speech; real Gate SR-C/SS-C; parallel CR-B/RM-B | W2–W3 / `3–5d` | T2; P2 + Web Alpha Gate | see STATUS |
| `II-C` | Interaction Intelligence | Acknowledgement/working notice and stop/revise/delegate integration | Demo status text/TTS `demo_substitute` → fenced II actions | II-A; real Gate SS-C/CR-B/RM-B/AIO-C | W3 / `2–3d` | T2; P2 + joint Gate | see STATUS |
| `AB-A` | Agent Bridge | Committed Turn/Response↔E2A/Harness mapping with exact identity/error behavior | Direct Chat/E2A `fallback` → formal AB mapping | ACG Identity/Commit/Error; parallel CR-A/TC-A | W1 / `1–2d` | T1; AB conformance | see STATUS |
| `AB-B` | Agent Bridge | Non-blocking Agent dispatch, backpressure and source-backed round WorkProgress | Direct blocking/legacy Agent path `fallback` → formal AB runtime | AB-A + WorkProgress; parallel CR-C and Harness instrumentation | W2 / `2–3d` | T2; P2/Week 2 + text regression | see STATUS |

## 7. P3alpha Task Control work packages

| WP | Module | Deliverable and user-visible result | Demo predecessor → formal target | Dependencies / parallel work | Window / timebox | Risk / acceptance | Current status |
|---|---|---|---|---|---|---|---|
| `TC-A` | Task Control Core | TaskCommand/Event types, canonical reducer, stable task ID and fake Core | schedule JSON/task card `demo_substitute` → TC authority | ACG Identity/State/Task/Error; parallel CR-A/ED-A/VB-A | W1 / `1–2d` | T3; ACG + TC conformance | see STATUS |
| `TC-B` | Task Control Core | Persistent Task/Command/Event Store, P3alpha API, authorized Command Adapter and restart reconciliation | `schedule.*`/JSON store `demo_substitute` → formal Task Core | TC-A; Store/API parallel ED-B/VB-B; restart Gate ED-B | W2–W3 / `2–3d` | T3; P3alpha + Web Alpha Gate | see STATUS |
| `TC-C` | Task Control Core | Event query/subscription and duplicate/gap/reorder/concurrent-task fault suite | D-031 polling `demo_substitute` → TaskEvent route | TC-A; parallel TC-B/VB-C | W3 / `1–2d` | T3; P3alpha event/fault Gate | see STATUS |
| `ED-A` | Executor & Durability | Executor Port, event-script fake and capability/failure conformance | AutoHarness scheduler `demo_substitute` → ED Port | ACG Task/Error/Capability; parallel TC-A/VB-A | W1 / `1–2d` | T3; ACG + ED conformance | see STATUS |
| `ED-B` | Executor & Durability | Project-bound real Executor Adapter, D0 detached start/status/cancel and restart status resolution | AutoHarness fixed pipeline `demo_substitute` → formal ED Adapter | ED-A + TC-A + coherent execution/artifact contract; parallel TC-B/VB-B | W2–W3 / `2–3d` | T3; P3alpha real path + Web Alpha Gate | see STATUS |
| `VB-A` | Voice–Task Bridge | Committed text/voice intent, exact target resolution and TaskCommand mapping | Hard-coded task grammar `demo_substitute` → formal VB mapping | ACG Commit/Task/Identity; parallel TC-A/ED-A | W1 / `1–2d` | T2; VB conformance | see STATUS |
| `VB-B` | Voice–Task Bridge | Ambiguity, destructive confirmation, Context/capability/permission checks | Demo confirmation grammar `demo_substitute` → formal policy boundary | VB-A + Context/Auth decision; parallel TC-B/ED-B | W2 / `1–2d` | T3; P3alpha safety Gate | see STATUS |
| `VB-C` | Voice–Task Bridge | TaskEvent→WorkProgress→origin surface; voice through CR, text through Chat/UI | D-031/task card polling `demo_substitute` → formal event projection | VB-A + WorkProgress + fake Runtime/Core; parallel CR-C/AB-B/TC-C | W2–W3 / `1–2d` | T2; P3alpha + joint Gate | see STATUS |

## 8. Cross-cutting Web Alpha packages

| WP | Owner | Deliverable and user-visible result | Predecessor → formal target | Dependencies / parallel work | Window / timebox | Risk / acceptance | Current status |
|---|---|---|---|---|---|---|---|
| `X-OBS` | Observability & Benchmark | Correlated trace/metric schema, latency segments, queue/cancel/fence/task metrics and reproducible benchmarks | Route labels/logs `demo_substitute` → formal evidence plane | Event/metric definitions; parallel all tracks | W2–W3 / `2–3d` | T2; Week 2/Web Alpha evidence | see STATUS |
| `X-E2E` | Vertical Integration & Fault Injection | One cumulative P1/P2/P3alpha route, real/fallback switching, fault injection and flag-off regressions | Separate Demo modes `demo_substitute` → cumulative Integrated route | Fake slices first; real Gates depend on matching B/C packages | W2–W4 / `3–5d` | T3; Week 2 and Web Alpha release Gates | see STATUS |
| `X-WEB` | Web Productization | Desktop Web UI, browser-scope decision, permissions/privacy, secure deployment, diagnostics, route controls and exact P3alpha structured controls | Historical X-WIN `unsupported` → Web product carrier | AIO/Speech contracts for UI; real Gate AIO-B/C, SR/SS, RM/CR and TC-B | W2–W4 / `3–5d` | T3 at release; Web platform Gate | see STATUS |

`X-WEB` supersedes `X-WIN`; it does not rename or absorb the AIO, RM, Speech, CR or Task authorities. Platform UI may display and route their facts but cannot own their lifecycle.

## 9. Compatibility and historical packages

| Item | Stable role | Formal successor or rule | Target window | Current status |
|---|---|---|---|---|
| V0 `ee2896a4` | Immutable real microphone→Agent/Tool→speech evidence | Retain as regression and historical product proof; never rewrite as Web Alpha | Frozen | see STATUS |
| `W1-K1` | Shared v2 critical kernel | Consumed by every formal A/B/C package; ACG remains authority | W1 | see STATUS |
| `W1-X1` | Route vocabulary/telemetry foundation | Consumed and completed by X-OBS/X-E2E | W1→W2 | see STATUS |
| `W1-X2` | Deterministic fake verticals | Retain for conformance/fault injection; never showcase as real success | W1→W4 | see STATUS |
| `W1-P1B` | Browser Speech compatibility path | Remains explicit P1 fallback behind formal Ports | W1→Later | see STATUS |
| D-031 | Timeboxed single-task polling and fail-closed Demo Adapter | Replace by TC-C/VB-C event projection; do not expand into a second Task Core | Current→W3 | see STATUS |
| Historical `X-WIN` | Windows Desktop/WebView2 productization plan | Superseded by D-055 and `X-WEB`; retain only in dated history | Superseded | see STATUS |

## 10. Milestones and release Gates

| Window | Human-readable outcome | Required package relationship | Pass/fail authority | Current status |
|---|---|---|---|---|
| V0 | Real voice can drive real Agent/Tool and speak the truthful answer in one fixed environment | Frozen predecessor only | [V0_ACCEPTANCE.md](../validation/V0_ACCEPTANCE.md) | see STATUS |
| W1 | Shared kernel, formal A-package foundations, deterministic fake verticals and Browser fallback exist | ACG kernel + A packages + W1-X1/X2/P1B | D-046/D-053 and package reviews | see STATUS |
| W2 | One cumulative route reaches at least 90/100 with mandatory invariants | First real B routes + X-OBS/X-E2E; D-031 can only receive capped substitute credit | [INTEGRATED_DEMO_ACCEPTANCE.md](../validation/INTEGRATED_DEMO_ACCEPTANCE.md) | see STATUS |
| W3 | Major B/C packages form real Speech/Media/Agent/Executor verticals | Real SR/SS/RM/CR/II/AB/TC/ED/VB paths plus Web integration | Module and real-path Gates | see STATUS |
| W4 | One immutable candidate passes P1/P2/P3alpha, Web platform and joint Gates | Required B/C packages + X-OBS/X-E2E/X-WEB | [ALPHA_ACCEPTANCE.md](../validation/ALPHA_ACCEPTANCE.md) | see STATUS |
| Later | Full P3, D1/D2, production auth, broader browsers/devices, SLO/privacy/release hardening | Explicit later decisions and packages | Future acceptance contracts | see STATUS |

## 11. Dependency map

```text
ACG critical kernel / W1-K1
├─ P1: AIO-A + SR-A + SS-A
│  ├─ P1 batch: AIO-B + SR-B + SS-B
│  └─ P2 speech: AIO-C + SR-C + SS-C
├─ P2: RM-A + CR-A + II-A + AB-A
│  └─ RM-B/C + CR-B/C + II-B/C + AB-B
├─ P3alpha: TC-A + ED-A + VB-A
│  └─ TC-B/C + ED-B + VB-B/C
└─ Cross-cutting
   ├─ X-OBS starts after event/metric vocabulary
   ├─ X-E2E consumes each fake and real vertical incrementally
   └─ X-WEB consumes browser AIO/Speech, RM/CR and TC structured controls

Week 2 Gate: cumulative route + route evidence + >=90/100 + mandatory invariants
Week 4 Gate: real P1/P2/P3alpha verticals + Web platform Gate + joint Gate
```

## 12. Agent execution contract

When an Agent uses this matrix to plan or implement work, it must:

1. read `README.md` and `STATUS.md`, then select only a package whose real dependency state allows progress;
2. preserve the canonical WP ID and parent-module authority shown here;
3. read the package's consumed ACG/decision/roadmap sections, actual source/tests and current diff before proposing implementation;
4. write a bounded plan with exact files, positive journey, key negative/fault/flag-off cases, forbidden effects, verification commands, non-goals and acceptance authority;
5. keep fallback/substitute provenance visible and never award replacement credit from design, fake, test count or UI appearance alone;
6. update STATUS only after implementation or evidence changes current facts; update this matrix only when a stable package, dependency, replacement or target-window decision changes;
7. apply D-053 review depth and the repository's separate commit/push approval gates.

If the required implementation would change an identity, state, authority, cancel scope, durability promise, product compatibility claim or package ownership recorded here, stop and create an explicit decision/matrix revision before coding.
