# Live Voice current status

> Updated: 2026-08-13
> This is the only mutable source for current branch expectations, stage/task,
> module closure state, blockers and next actions. Detailed evidence lives in
> the linked review record; Git remains the implementation fact.

## Resume capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `agtai/hx/0812_live_voice_w3`. `origin` is the atomgit upstream and has no W3
  ref; an earlier `origin/...` claim here was wrong. Verify live Git before
  trusting prose.
- Current stage/node: `S6 - Alpha Module Closure` / `A1`, `ENVIRONMENT`.
- Current task: `S6-02` defect-11 real-path proof and physical observation, and
  nothing else. `S6-01`, `S6-03`, `S6-04`, `S6-05` and `S6-06` are
  `SATISFIED`; the previously declared automated S6 measurements have run on
  the real private topology. Physical rows O1-O4 (permission grant, deny,
  revoke and device loss) are also observed PASS. Defect 11 is source-fixed
  and automated-verified in `10062c3e`, but the private D: run environment was
  unavailable to this Session, so its real-path rollback proof, the O5
  greater-than-15-second re-listen and O6 hidden/background/resume have not run.
  Candidate defect 12 still needs real-path instrumentation before attribution.
  The user executes physical rows from [the S6-02 runbook](S6_02_PHYSICAL_OBSERVATION_RUNBOOK_2026-08-13.md);
  Main must not claim to have heard speaker output or to have answered a
  browser permission prompt.
- Next gate: the `S6-02` physical observation is the only row left before
  `S7-01` candidate assembly can start.
- Closed: S0 V0, S1 Shared Foundations, S2 D-031 bounded compatibility,
  S3 W2 Integrated Demo (`PRODUCT-ACCEPTED`), S4 develop rebaseline, S5 entry
  audit/ownership activation, and the S6 source/automated implementation scope.
- Open: the `S6-02` physical microphone/device/heard-playout evidence, the S6
  exit that depends on it, A2 and A3.

Terminology follows D-075. The active execution contract is the
[S5-S8 plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md); the complete
S6 implementation and review record is
[S6 Alpha integration review](S6_ALPHA_INTEGRATION_REVIEW_2026-08-12.md).

## S5 entry audit

- `S5-01`: SATISFIED for S6 entry. Git/source and tests were inspected against
  the Alpha rows; package names or historical completion claims were not used
  as proof.
- `S5-02`: D-078 choices are frozen in source. Machine-private/provider facts
  remain `ENVIRONMENT` and were not invented or committed.
- `S5-03`: SATISFIED. Main retained integration and semantic ownership; Tier 2/3
  boundaries received self-review, cumulative cold review and an independent
  read-only review. Each coherent S6 module group used affected tests before the
  broad verification pass.

## S6 closure dashboard

| Task | Status | Current fact |
|---|---|---|
| S6-01 critical-input safety | `SATISFIED` | The bounded `CriticalTokenSafetyGate` is on committed text/voice/Task product paths. Partial, stale, low-confidence and wrong-scope cases assert zero Agent, Tool, Task, audio, history and Store effects. |
| S6-02 P1 speech/browser lifecycle | `ENVIRONMENT` | Real streaming STT/TTS and four physical permission/device rows remain proven as recorded in D112. Defect 11, the fixed 15 s whole-stream synthesis budget, is repaired in `10062c3e`: streaming now uses a sliding next-event timeout across browser, Gateway, Adapter and conformance layers while batch keeps its whole-operation budget. Red/green regression, affected suites, production build and an independent Tier 2 review pass. The private D: run root and services were unavailable to this Session, so the required real-path revert-fail/restore-pass proof and physical re-listen of a greater-than-15-second answer remain `ENVIRONMENT`; heard playout therefore remains FAIL from the last observation. Candidate defect 12 (tearing/clicking) is still unmeasured and unchanged, and O6 is unobserved. |
| S6-03 P2 realtime conversation | `SATISFIED` | The complete real media route is proven on the private origin: first-frame media auth, 227 uplink frames with 227 ACKs, provider-time end of turn, streaming recognition `completed` with no degradation, real Agent final, a real streaming TTS downlink and an accepted playout receipt. Nine real fault/load profiles all fail closed as declared, including sequence gap, duplicate/out-of-order, cursor mismatch, stale generation, one-use ticket replay, audio before authentication, an unpaced burst with no drop, and reconnect after a terminal detach. The route latency report covers thirteen targets with p50/p95/max over 5/5 clean rounds. The slow-round profile and the real cancel fences are proven in one live run: cancelling the Task mid-response left 184 further deltas and a normal final, a barge-in on another response left the Task state and outcome unchanged, and a stale generation and an unknown response target were both refused with no new effect. No fake result stands in for a real path. |
| S6-04 P3alpha Task vertical | `SATISFIED` | Proven on the real path against the authoritative Store: confirmation issue/consume, command idempotency, TaskEvent-only lifecycle truth, outbox accounting, scope isolation, replay rejection and terminal-cancel rejection. Two Alpha defects blocked every real dispatch; with them fixed a real attempt now completes, the real Code Agent makes exactly the instructed change on the disposable fixture, and cross-project effects are 0. |
| S6-05 observability/privacy/Web | `SATISFIED` | The private same-origin HTTPS/WSS topology is built and measured: real CA trust, CSP, WSS routing and zero browser-tier credentials. The whole-stack benchmark reports p50/p95/failures/sample for every declared target with 5/5 rounds clean; the raw-audio zero-persistence regression scans 66 configured surfaces and 16.2 MB with zero hits; the degradation matrix proves Streaming -> W2 Batch -> Browser/text with each tier explicitly identified and the text path surviving both Speech-provider and media removal; and the sanitized trace reproduction rebuilds the route, cancel, queue and Task facts from logs and the authoritative Store alone, cross-checking state/outcome/cancel against the live run, with zero credentials and zero raw audio on those surfaces. |
| S6-06 joint route | `SATISFIED` | The automated joint scenario passes, including a race the real-path repair exposed, and the real joint run has now executed: one detached P3alpha Task on the disposable fixture, one committed voice Turn through the real media route, two slow conversational rounds, a barge-in, a cancel issued while a response was still streaming, and two cancel targets that had to be refused, all in one run with zero cross-domain effect and zero unauthorized fixture mutation. Fake external claims are still not treated as proof of the physical P1 route, which S6-02 owns. |

No located S6 source defect remains open. Defect 11 from D112 section 7c is
repaired and automated-verified in `10062c3e`; its real-path proof is still an
environment requirement. Candidate defect 12 remains unmeasured and has not
been attributed or modified. `S6-02` stays `ENVIRONMENT`; the other five rows do
not consume either observation.

Latest source verification is bound to `10062c3e` and recorded in
[D113](D113_S6_02_SYNTHESIS_EVENT_TIMEOUT_REPAIR_2026-08-13.md). Its real-path
predecessor is [D112](D112_ALPHA_REAL_MEDIA_ROUTE_2026-08-13.md), which follows
[D111](D111_ALPHA_REAL_PATH_ACTIVATION_2026-08-12.md); the automated baseline
both build on is [D110](D110_ALPHA_AUTOMATED_VERIFICATION_AND_ENVIRONMENT_BLOCK_2026-08-12.md).

D112 adds four more Alpha real-path defects, all behind declared fail-closed
gates and all invisible to the suites: P2 activation requested the Agent
profile that does not own the formal Live Voice seam; the WebChannel dispatcher
accepted only the legacy media path while activation returns the fixed one; the
real GA transcription echo drops the two response fields the Adapter compared
byte for byte, so every `server_vad` open was rejected; and end-of-turn
arbitration cancelled the Provider open it was waiting for. Each is fixed with
a regression test proven to fail when the fix is reverted. The dedicated media
route also requires the deployment to list the private origin host in
`JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS`; that is a deployment prerequisite, not a
defect, and no source was changed for it.

D110's two external blockers are cleared: the Gateway-only Speech credential and
a private `https://live-voice.localhost` HTTPS/WSS reverse proxy now exist, with
an isolated data dir, isolated P3 SQLite Store and a disposable no-remote Git
fixture. The first real run immediately exposed defects no fake-socket suite
could reach, which is the point of the real path:

1. the GA transcription session sends `conversation.item.added`/`.done` and no
   longer sends the beta `conversation.item.created`, so the Adapter aborted
   every real recognition right after commit;
2. a transport close slower than the 50 ms attempt budget was cancelled and
   permanently retained as failed, leaking one cleanup slot per stream and
   closing the STT route after roughly fifteen recognitions;
3. `ReasoningToolLoopCompactProcessor`, wired by develop `b06ff06d0`, does not
   exist in the pinned agent-core, which fails every `chat.send` at runtime;
4. the P3 model hook called `JiuWenSwarmDeepAdapter._build_model_from_entry`,
   which does not exist — the runtime exports `build_model_from_entry` as a
   module-level function — so every real attempt dispatch failed closed with a
   suppressed outbox and `P3_MODEL_UNAVAILABLE`;
5. formal dispatch read `get_instance`, a plain accessor that returns None
   until the chat path builds the root DeepAgent, instead of awaiting
   `ensure_instance`, so every attempt failed with
   `EXECUTOR_CAPABILITY_UNAVAILABLE` and zero project effect.

(1), (2), (4) and (5) are Alpha-attributable and fixed in `31ee31abb`,
`44b275d5d` and `3583c0fe2`, each with a regression test proven to fail when its
fix is reverted. (3) is
identical on the `3f3cdbb7f` develop baseline and the `2a69c2b87` comparison base,
so it is out of scope and unmodified; the isolated run disables it through
configuration only.

None of the four could be reached by the existing suites: the streaming sockets,
the P3 model resolver and the executor are all fakes that replay only shapes the
implementation already knows. A passing suite says nothing about the real path.
With (4) and (5) fixed, the formal P3alpha vertical now executes for real: a
task reaches `terminal/completed`, its outbox is `delivered`, and the real
project Code Agent makes exactly the instructed change on the disposable
fixture with HEAD unchanged and still no remote.

Verification commands must keep `--asyncio-mode=auto`: `pytest.ini` carries it in
`addopts`, and the common `-o addopts=''` silently drops it and manufactures
dozens of false async failures.

S6 remains open on defect-11 real-path proof, two physical observations and the
unmeasured defect-12 symptom. Under
[ALPHA_ACCEPTANCE.md](validation/ALPHA_ACCEPTANCE.md) §8 the current result is
still `BLOCKED`: the physical microphone/device/heard-playout observation has not
run, so S7 has not been entered and S8 has not run. Every other S6 measurement
has run on the real private topology.

## Frozen product boundary

- Gateway-only key: `LIVE_VOICE_SPEECH_API_KEY`.
- Streaming defaults: `gpt-4o-mini-transcribe-2025-12-15`,
  `gpt-4o-mini-tts-2025-12-15`, voice `marin`, official OpenAI origin only.
- Degradation: Streaming -> W2 Batch -> Browser/text, explicitly identified.
- Agent: current JiuwenSwarm Agent Provider. P3alpha: current formal Task Core,
  `DirectProjectCodeExecutorAdapter` and a disposable local Git fixture.
- New capabilities remain default-off until their environment is verified.

The branch preserves the D107 develop/W3 migration corrections, including Task
Store WAL concurrency, Runtime/Executor, agent-core and workspace API behavior.
It does not restore signed Gate tooling, Replacement Ledger, a fixed manifest,
old migrated APIs, or `schedule.*` as P3alpha Task authority. Full P3, 3A/3B,
D1/D2, Production and public deployment remain outside scope.

## Next actions

1. Restore the private D: run root, start the isolated services with its
   `services.py`, deploy source `10062c3e`, and run real-paced
   `s6_02_realtime_playout.py`; prove defect 11 with revert-fail/restore-pass on
   that real route.
2. On real Chrome at `https://live-voice.localhost`, re-listen to one complete
   answer longer than 15 seconds and exercise O6 hidden/background/resume using
   [the S6-02 runbook](S6_02_PHYSICAL_OBSERVATION_RUNBOOK_2026-08-13.md).
3. During that run, collect AudioWorklet underrun count, frame interarrival
   distribution and in-flight watermark before attributing or changing candidate
   defect 12. If the measurements prove an Alpha defect, repair and rerun only
   the materially changed review scope.
4. When those rows pass, mark `S6-02` and S6 exit, then start `S7-01` candidate
   assembly.
5. `S7-03` still owes the complete 45,044-line cumulative cold review and one
   independent review; neither has run.

No push is authorized. Machine-private credentials, provider configuration,
browser profiles, raw audio and private run data must stay out of Git.
