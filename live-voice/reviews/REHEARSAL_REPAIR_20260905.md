# Rehearsal repair — 2026-09-05

## Accepted scope and baseline

The user authorized implementation after reviewing the rehearsal findings, then
explicitly accepted adjustment delivery between tools/work stages: the next model
call must use newly accepted constraints, without waiting for the whole plan.
Baseline: `7c7aad7b8`; private rehearsal evidence is retained under ignored logs.
This packet does not claim physical microphone/speaker or full candidate acceptance.

| Boundary / owner | Intended behaviour and risk | Owned verification |
|---|---|---|
| Controlled build configuration | Direct and launcher Live Voice builds share generation-interruption default on; explicit off wins. Preserve Cascade, VAD 800 ms, startup 250 ms and explicit device profiles. Tier 2. | Actual Vite environment precedence, launcher preflight, build and deployed asset identity; ordinary production off. |
| Local Task consent / Voice–Task bridge | Exact committed create/adjust/cancel consent may traverse the existing confirmation consumer without another spoken question. Ambiguous targets clarify. Preserve binding, capability, authorization, CAS and replay fences. Tier 3. | Typed semantic positive/ambiguous/wrong-scope/stale/replay paths through real composition/store; zero forbidden mutations. |
| Adjustment / Executor & Agent bridge | Admit pending constraints at tool/work-stage boundaries and use them on the next model invocation. Applied means adopted by the execution owner; received is not applied. No interruption of an in-flight tool. Tier 3. | Real Agent-loop seam with controlled model/tools, multiple updates, cancel/terminal races, retry/idempotency and exact Attempt isolation. |
| Task result UI | Distinguish scoped task list from selected result detail; clear selection and existing Markdown result navigation. Tier 1. | Mounted selection, correct result and cross-scope exclusion; frontend build. |
| Notification / Conversation Runtime & Integrated Web | Unread completion survives remount and voice activation; deferred notification retries after foreground releases ownership. Preserve exact activation/task/generation, ordering and durable ACK. Tier 2 (re-tier if shared protocol changes become necessary). | Reproduce both faults; mounted and real registry/store reconnect, busy/recovery, duplicate/stale ACK, Exit and scope isolation. |
| Creation receipt / Agent bridge | Immutable creation acceptance is historical evidence, not current queue/running state. Current claims use authenticated current facts. No output rewriting. Tier 2. | Agent input facts, authoritative read failure, replay/no second create, scope isolation. |
| Private demo material | Self-drive total becomes 1400 with consistent components; retain time/fatigue/deposit facts and existing result files. Data-only. | Exact fixture arithmetic and preserved A/A2 files; private material stays outside Git. |

Dependencies: existing durable command/adjustment delivery, selected-task projection,
P2 activation and return-lease owners. No model/provider/credential changes, new
classifier, global confirmation bypass, forced delay, answer quota or postprocessing.
“Packing” intent, A2 arithmetic and performance tuning remain excluded; performance
is to be profiled again after the user changes AgentModel. Active in-flight model
requests need not be forcibly aborted; a boundary must adopt updates before the
next invocation and terminal sealing must not silently discard accepted updates.

## Verification and review

Implementation and bounded module verification completed against the baseline
plus this packet's diff. Independent read-only review covered the complete
notification, Executor/SDK, cancellation, receipt and build boundaries; findings
about canonical adjustment events, retry ownership, real timeout codes and atomic
admission reads were repaired and rechecked. No remaining blocking finding was
reported. The UI scoped diff was reviewed by the integration owner.

| Verification command / boundary | Observed result |
|---|---|
| `node --test tests/liveVoiceBuildProfiles.test.mjs` | 4 passed; real Vite `loadEnv` precedence and explicit false. |
| Portable launcher generation-interruption tests | 8 passed with real PowerShell AST; sandbox AST access initially failed, rerun with authorized host access passed. |
| `node --test tests/recentBackgroundTasks.test.mjs` | 2 passed; list/selected detail and scope. |
| `node --test tests/formalTaskControlLeaf.test.mjs` | 22 passed; adjusted completion plus malformed producer/state/identity rejection. |
| `pytest tests/unit_tests/live_voice/test_semantic_registry.py` | 88 passed; exact cancel, ambiguity, replay, isolation and fresh creation facts. |
| Registry subset: `agent_ack_drains_deferred_voice_task_presentation`, `current_p2_poll_retries_terminal`, `text_progress_web_ack`, reconnect skip | 5 passed; actual Registry/Store voice/text routes and ACK, controlled transports. |
| `pytest tests/unit_tests/live_voice/test_project_code_executor.py tests/unit_tests/live_voice/test_background_task_checkpoint.py` | 144 passed; real Core/Store/Direct worktrees and actual SDK model-call callbacks with controlled Agent/LLM. |
| Subsequent facade assertions / cancellation checkpoint tests | Facade passed; 2 cancellation cases passed after asserting final async status rather than treating cancel receipt as completion. |
| Mounted `recovered voice Tasks` / `foreground status query restarts` | 3 + 3 passed, including adjusted terminal history, Exit, independent A/B, code-only timeouts and 4 failed reads before recovery. |
| `tsc --noEmit`; `npm run build:live-voice` | Passed; Vite build completed (existing large-chunk warning). |

Python tests used isolated `JIUWENSWARM_DATA_DIR=logs/rehearsal-repair-tests`
and unique `--basetemp` directories, `--no-cov -q --tb=short
--show-capture=no -o log_cli=false`. Executor filesystem tests required host
access for existing temporary ownership locks; no real user Task was a test target.
Raw local test logs are ignored under `logs/rehearsal-repair-tests/`.

### Broader regression limits

The full mounted file is **98 passed / 18 failed / 1 skipped**. Baseline panel
`7c7aad7b8` with the corresponding test fixtures is **95 passed / 20 failed /
1 skipped**. Independent comparison found every current failure in the baseline:
10 refer to retired Task-intent controls, 3 typed reconnect cases, and 5 existing
AUDIO/TEXT, TTS, Exit or generation-interruption cases. One existing duplicate
progress-ACK assertion is `3 != 2` in both versions. The two eliminated failures
are the repaired foreground handoff cases; one additional passing test covers
retry exhaustion. Full mounted-suite success is **not** claimed. A long React
`act` also blocked passive ACK effects; splitting at the foreground ACK repaired
the test scheduling without changing production arbitration.

### Scenario and real-boundary credit

- P/S/T/C/R/X: constraints accepted before outbox delivery fence the next model
  call; ordered updates use the same Agent stream; lost settlement prevents the
  next call and result. Cancellation before adoption and while settlement is
  pending has zero later model/file effects. Real facade checks same-session
  subagent exclusion, closed callback rejection and exact callback cleanup.
- N/B/I/F/K: existing semantic suite checks ambiguity, wrong scope, stale/replay
  and capability fences; malformed adjustment events have zero state effects;
  retry remains bounded and Exit closes exact owners. Ordinary builds remain off.
- No shared schema migration, new classifier or mid-tool abort was introduced.
  Provider and physical microphone/speaker acceptance are outside automated
  module credit. Private unread notifications were not consumed.

## Material, deferred work and deployment

Private `资料.md` now totals 1400 = 300 rental/insurance + 100 one-way return +
500 fuel + 400 tolls + 60 parking/return + 40 pickup transfer. The driving duration,
rest/fatigue and refundable deposit remain; hotel and expected airfare refund are
unchanged. Existing A/A2 result files were not edited.

Agent intent (“packing”), A2 arithmetic and response quality remain model-owned.
After changing AgentModel, run the original rehearsal with the existing diagnostic
export and compare ASR commit, foreground first response, tool/model stages,
adjust received/applied, Task terminal and presentation ACK durations. Select any
performance change from that fresh evidence; no artificial delay or answer
postprocessing is included here.

### Local deployment (2026-09-05)

Committed implementation: `1d48af8e9` (controlled build default), `aadd84253`
(Task/Executor/Agent/notification backend), `b30b8be2d` (frontend recovery/result UI
and packet documentation). The launcher built and started clean source
`b30b8be2dd` using the saved formal project and private data directory:

```powershell
.\scripts\live_voice\start_hands_free_demo.ps1 -RuntimeProfile formal-web-validation -AllowDirtyProject -PreflightOnly -NoBrowser
.\scripts\live_voice\start_hands_free_demo.ps1 -RuntimeProfile formal-web-validation -AllowDirtyProject -RestartExisting -NoBrowser
```

`AllowDirtyProject` preserves the existing private fixture/result changes; the
source repository was clean. Generation interruption was **true without an enable
argument**. Cascade and the saved verified-headset profile remained selected;
accepted VAD 800 ms / startup 250 ms defaults were unchanged. Ports 5173 / 18092 /
19000 / 19001 and authenticated routes were ready. Real Speech TTS→STT, legitimate
receipt and identity/forged-claim rejection probes passed with zero business
side effects. Startup log: ignored `logs/swarm-20260905-175107.log`.

HTTP `/assets/index-D7_vE1Sh.js` matched the deployed dist byte-for-byte:
SHA-256 `62da266619b1a74dcb46cc1fd26261a7d16796eb7bf509811c6a56a71520f7ee`.
Its generation-time capture function retained the actual listening body rather
than compiling to an empty function. Runtime contract records clean source,
generation interruption true and validated routes/bundle. The later evidence
commit changes documentation only; it needs no service restart.

Read-only pre/post checks found no nonterminal private Tasks and unchanged state
counts (39 completed, 7 cancelled, 13 failed, 4 interrupted). Private USER.md
SHA-256 was unchanged. No browser was opened, no private notification was ACKed,
and existing result documents were not altered. Full physical A/B/A2 rehearsal
acceptance remains open.
