# S6 Alpha integration and review record - 2026-08-12

This dated record captures the completed source/automation integration and its
review evidence. It does not override [STATUS](STATUS.md), D-078, D107 or the
[S5-S8 execution plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md).

## 1. Scope and source identity

- Stage/node: S6 / A1.
- Tracks: Shared-X, P1 AIO/SR/SS, P2 RM/CR/II/AB, P3alpha TC/ED/VB and X-E2E.
- Risk: Tier 2/3; authority, privacy, concurrency, cancellation, durability and
  provider boundaries use the applicable D-032 matrices and D-074 reviews.
- Comparison base: `2a69c2b87d0ee080a4a30421cbcbcdf93183f340` on
  `hx/0812_live_voice_w3`.
- Integrated source/automation commit:
  `d659c2c8667d67e79d581acacd1fb53256f194f7`.
- Diff: 87 files, 44,438 insertions and 1,084 deletions.
- Exclusions: no W3 migration rerun; no old branch-tip merge; no whole
  `81842731` baseline import; no 3A/3B, full P3, D1/D2, Production, public
  deployment, credentials, raw audio, private run data or remote update.

The current W3/develop source was the conflict-resolution authority. D107's Task
Store WAL concurrency fix, Runtime/Executor, agent-core and workspace API
corrections were preserved. Deleted/migrated objects and APIs were not restored.

## 2. S5 entry result

The minimum S5 entry audit was sufficient to activate S6:

- S5-01 mapped the relevant Alpha rows to current source/tests and explicit
  `SATISFIED`, `IMPLEMENT`, `VERIFY` or `ENVIRONMENT` work; historical package
  labels and old test counts were not used as closure proof.
- S5-02 used D-078 as the product boundary. Missing real credentials, hardware
  and private deployment facts remained environment work.
- S5-03 assigned integration/semantic ownership to Main, grouped coherent
  module changes, applied affected checks during development and reserved an
  independent read-only review for the Tier 2/3 cumulative diff.

## 3. Semantic forward-port ledger

| Historical input | Effective S6 result |
|---|---|
| `25e97316` | OpenAI Streaming Speech adapter was ported on the current contracts and restricted to the official OpenAI origin. |
| `776d977b` | Formal Voice-Task Bridge was adapted to the current Task authority/origin model. |
| `5ce265bc` | Bounded streaming TTS route was integrated with current Gateway media and cleanup behavior. |
| `e6a336ea` | Product method dispatch was integrated without reviving removed APIs. |
| `1c2ff48d` | Task observability truth was integrated through the current formal Core/outbox path. |
| `e824d164` | Streaming STT product wiring was adapted to current fixed media route/auth and privacy semantics. |
| `d028b906` | Streaming TTS product wiring was adapted to current fallback and presentation fencing. |
| `3e8125f4` | Deployment observer was ported, then corrected from the old public-only assumption to D-078 private same-origin HTTPS/WSS policy. |
| `1aece06f` | Desktop input/output selection and lifecycle handling were integrated. |
| `2d2f4015` | Server VAD and automatic EOT were integrated on the current media contract. |
| `f391f455` | Device/EOT test glue was adapted to the current product route. |
| `35f29b0b` | Review input only. Its old documentation was not cherry-picked or copied as current evidence. |

The missing Streaming Speech contract was audited from the historical parent and
ported selectively. `alpha_benchmark.py`, `alpha_privacy_conformance.py` and
`webLifecycleObservationRecorder.ts` were also reused only after adapting them
to current S6-05 authority, privacy and private-topology requirements. Neither
the parent baseline nor the Alpha-prep branch was merged.

## 4. Implemented closure

### S6-01 - committed-input safety

`CriticalTokenSafetyGate` now precedes Agent/Tool/Task allocation on formal
committed text and voice paths. It enforces final/provenance rules even with new
capabilities default-off, uses monotonic generations, applies exact voice
confirmation policy, has bounded state/capacity and releases terminal or closed
interactions. Evaluate and clarification-resolve paths both fail closed at
capacity. Negative tests assert zero Agent, Tool, Task, audio, history and Store
effects for partial, stale, low-confidence, wrong-scope and invalid commits.

### S6-02 - Streaming Speech, Web, device and EOT

The formal Streaming Speech contract, official OpenAI STT/TTS providers, Gateway
routes, product synthesis, fixed dedicated media route, one-use media auth,
browser device selection, Server VAD/EOT and product Web wiring are integrated.
Defaults exactly follow D-078. One Gateway environment can select official
Streaming and keep W2 Batch available; legacy `openai-compatible` remains only a
Batch compatibility label. Fallback is explicit Streaming -> Batch ->
Browser/text and never reports a degraded path as Streaming success.

### S6-03 - realtime conversation

Automation covers slow/failing Agent behavior, non-blocking turns, load and
network faults, notification/backpressure/reconnect/final drain, generation and
presentation fences, stop/revise/delegate behavior, four cancellation scopes,
late/stale arrivals, latency observations and zero cross-turn/task/playback
effects. Real Agent/network/device measurements remain environment evidence.

### S6-04 - formal Task vertical

Structured methods and committed natural-language create/status/cancel resolve
through the product registry and `VoiceTaskBridge`, then the current
`P3AuthenticatedComposition`, persistent Task Core/SQLite Store/outbox and
`DirectProjectCodeExecutorAdapter`. `task.cancel` is target-bearing and exact
task identity is revalidated before granting a Task resource. Progress and
terminal results retain their original voice origin. No schedule surface or
parallel parser became a second Task authority.

### S6-05 - observability, privacy and deployment

The default-off benchmark runner emits bounded case/sample/execution records,
p50/p95/failure/sample summaries and content-free failures. Privacy automation
checks whole-stack projections and zero persistence. The deployment observer
requires private non-loopback addresses, same-origin HTTPS/WSS, pinned DNS/TLS
hostname, no redirects and no rebinding; public, loopback, link-local,
multicast/reserved endpoints fail closed. Web diagnostics redact valid and
malformed nested transcript, raw-audio, credential and media-ticket aliases.

### S6-06 - deterministic joint scenario

The cumulative test traverses the real `AgentServerProductCompositionRegistry`,
an enabled safety gate, `P3AuthenticatedComposition`, persistent SQLite Task
Core and a real Direct executor over a disposable Git fixture. It registers the
voice origin before creation, drives natural-language create/status/cancel,
runs multiple slow P2 turns, isolates response interruption/revision from Task
cancel, observes progress and terminal return, verifies explicit text fallback,
and asserts zero Store or project mutation for stale, partial and wrong-scope
inputs. External speech claims, slow Jiuwen behavior and Web push are controlled
fakes; this test is not physical Provider/device/private-Web evidence.

## 5. Review record

Main performed affected-diff self-review throughout and a cold review of the
complete integration seams. An independent read-only reviewer examined the
Tier 2/3 cumulative diff, reran focused checks and made no Git changes. Findings
were repaired and affected tests rerun:

| Finding | Resolution |
|---|---|
| Safety-gate state could grow without release; clarification resolve bypassed capacity. | Added bounded capacity checks to evaluate/resolve plus release/reset and product cleanup coverage. |
| Streaming could accept arbitrary HTTPS hosts. | Locked Streaming to the canonical official OpenAI API origin and added negative host/provider coverage. |
| The shared provider environment could not enable Streaming and required Batch fallback together. | Allowed the official `openai` label for Batch only at the official base while retaining legacy compatible Batch behavior. |
| Web malformed nested JSON could expose media-ticket/raw-audio aliases in logs. | Added fail-closed alias detection and malformed nested regression cases. |
| Historical deployment observer enforced public endpoints, opposite D-078. | Reworked it to private-only same-origin HTTPS/WSS with DNS/TLS/rebinding defenses. |
| Initial S6-06 test proved component coexistence rather than the product route. | Replaced it with the registry/gate/P3/Core/Direct-executor joint scenario and registered the original origin before create. |
| Product `task.cancel` was incorrectly treated as untargeted. | Made cancel target-bearing and enforced exact-task validation before resource grant. |

The final independent re-review reported no remaining actionable source
correctness or security finding. Its recorded limitation is the same environment
boundary below: fake external dependencies establish deterministic composition,
not real OpenAI media, physical Chrome/device or private HTTPS/WSS acceptance.

## 6. Verification actually run

All commands ran from the repository root on Windows. Results are current for
the integrated semantic diff; finding-specific tests were rerun after each later
repair.

| Check | Actual result |
|---|---|
| `.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice tests/integration/live_voice` | 1,492 passed, 2 skipped. |
| Selected AgentServer/Gateway/Web/Executor regression set (13 files) | 510 passed. |
| All frontend scripts matching `test:live-voice-*` | 16/16 script groups passed; an earlier aggregate in the same final frontend state reported 713/713 tests. |
| `npm.cmd run build` in the frontend | TypeScript and Vite production build passed; 4,640 modules transformed in 22.26 s. Existing dynamic/static import and large-chunk warnings remain warnings. |
| Changed-Python Ruff with `--ignore E402,F541,F841,F821` | Passed. A full unignored Ruff scan reports the same 21 pre-existing diagnostics as the comparison base; no new Ruff diagnostic was introduced. |
| Selected owned/new Python `ruff format --check` | 24 files already formatted. The pre-existing broad `app_web.py` formatting was not mechanically rewritten. |
| `.venv\Scripts\python.exe -m compileall` over changed Python packages/tests | Passed. |
| `git diff --check` | Passed before source commit and after every final repair. |
| Focused final privacy regression | 3 passed. |
| Focused final targeted-cancel plus rewritten joint scenario | 2 passed. |
| Focused official-OpenAI selector regression | 1 passed. |

The final frontend build left generated agent-data unchanged. Added-line scans
found no machine-private path, token-shaped secret or private-key block.

## 7. Accurate remaining work

### Source gaps

None known after the final independent review.

### Deterministic automated-validation gaps

None known in the implemented S6 scope. A real-run benchmark/acceptance report
cannot be produced by fake/fault fixtures and is classified as environment work.

### Real environment

- Gateway access to `LIVE_VOICE_SPEECH_API_KEY` and the official OpenAI Speech
  endpoint.
- The current configured JiuwenSwarm Agent Provider and controlled real
  slow/fault/load network behavior.
- An exact Chrome Stable/Windows build, user-approved microphone/output devices,
  permissions and audible playout.
- A private same-origin HTTPS/WSS candidate with trusted certificate/routing and
  isolated runtime/data/project roots.
- Sanitized real p50/p95/failure/sample, degradation, privacy and cleanup output.

### Must be performed by the user

The user (or an explicitly approved operator) must supply machine-private
credentials/configuration, authorize the physical browser/device run and execute
the real acceptance on the private candidate. This integration did not create an
OpenAI Project/key, change billing, expose a public deployment or push any ref.

## 8. S7 entry decision

`S7-01` is **not yet eligible** under the plan's dependency graph because the
physical/real-path exit of S6-02/S6-03, the declared-environment output of S6-05
and therefore the real-path portion of S6-06 remain `ENVIRONMENT`. The shortest
remaining path is:

1. provision only the approved private candidate facts above;
2. run the real P1/P2/whole-stack benchmark, fault, degradation, privacy and
   heard-playout acceptance without changing source;
3. if all pass, update STATUS and begin S7-01 candidate assembly/identity freeze;
4. if a defect appears, repair it, rerun affected checks and repeat the
   materially changed review scope before S7-01.
