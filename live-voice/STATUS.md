# Live Voice current status

> Updated: 2026-08-12
> This is the only mutable source for current branch expectations, stage/task,
> module closure state, blockers and next actions. Detailed evidence lives in
> the linked review record; Git remains the implementation fact.

## Resume capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `agtai/hx/0812_live_voice_w3`. `origin` is the atomgit upstream and has no W3
  ref; an earlier `origin/...` claim here was wrong. Verify live Git before
  trusting prose.
- Current stage/node: `S6 - Alpha Module Closure` / `A1`, `ENVIRONMENT`.
- Current task: complete the declared real Provider/device/private-topology
  acceptance for `S6-02`, `S6-03`, `S6-05` and the real-path portion of
  `S6-06`. The private topology and real Speech path are now live and proven;
  what remains is the physical device/heard-playout observation plus the P2,
  whole-stack and joint real measurements.
- Next gate: close the environment rows below before starting `S7-01` candidate
  assembly.
- Closed: S0 V0, S1 Shared Foundations, S2 D-031 bounded compatibility,
  S3 W2 Integrated Demo (`PRODUCT-ACCEPTED`), S4 develop rebaseline, S5 entry
  audit/ownership activation, and the S6 source/automated implementation scope.
- Open: physical P1/P2/private-Web evidence, complete S6 exit, A2 and A3.

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
| S6-02 P1 speech/browser lifecycle | `ENVIRONMENT` | Real streaming STT/TTS now run against the official OpenAI origin: 5/5 recognitions and 5/5 syntheses with p50/p95 recorded. Two Adapter defects that broke every real recognition were found and fixed here. Physical microphone, device change/loss and heard playout still require the user. |
| S6-03 P2 realtime conversation | `ENVIRONMENT` | The real Agent/Tool text path is proven end to end on the private origin. Real P2 media, fault/load profiles and route latency measurements have not run. |
| S6-04 P3alpha Task vertical | `SATISFIED` | Structured and committed natural-language create/status/cancel traverse the current formal Task Core, exact authority checks, SQLite Store/outbox and `DirectProjectCodeExecutorAdapter` on a disposable Git fixture; no second Task authority exists. A real mutation run on the disposable fixture is still outstanding under S6-06. |
| S6-05 observability/privacy/Web | `ENVIRONMENT` | The private same-origin HTTPS/WSS topology is built and measured: real CA trust, CSP, WSS routing and zero browser-tier credentials. The whole-stack benchmark, raw-audio zero-persistence regression and degradation matrix have not run. |
| S6-06 joint route | `ENVIRONMENT` | Depends on the remaining real paths in S6-02/03/05. Fake external claims are not treated as proof of the required physical P1/P2 route. |

No known S6 source defect remains. The open rows are environment evidence, not
hidden fallback success or accepted product deviations.

Latest verification is bound to `31ee31abb` and recorded in
[D111](D111_ALPHA_REAL_PATH_ACTIVATION_2026-08-12.md); the automated baseline it
builds on is [D110](D110_ALPHA_AUTOMATED_VERIFICATION_AND_ENVIRONMENT_BLOCK_2026-08-12.md).

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
   exist in the pinned agent-core, which fails every `chat.send` at runtime.

(1) and (2) are Alpha-attributable and fixed in `31ee31abb` with regression tests
proven to fail when either fix is reverted. (3) is identical on the `3f3cdbb7f`
develop baseline and the `2a69c2b87` comparison base, so it is out of scope and
unmodified; the isolated run disables it through configuration only.

Verification commands must keep `--asyncio-mode=auto`: `pytest.ini` carries it in
`addopts`, and the common `-o addopts=''` silently drops it and manufactures
dozens of false async failures.

S6 remains open on environment evidence only. Under
[ALPHA_ACCEPTANCE.md](validation/ALPHA_ACCEPTANCE.md) §8 the current result is
`BLOCKED`: the physical microphone/device/heard-playout observations and the
remaining P2/whole-stack/joint real measurements have not run, so S7 has not been
entered and S8 has not run.

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

1. With the user on real Chrome at `https://live-voice.localhost`: grant, deny and
   revoke microphone permission, change/lose a device, and confirm heard playout
   of a complete answer. This is the only remaining S6-02 gap.
2. Run the remaining real measurements: P2 media/fault/load and route latency
   (S6-03), whole-stack benchmark plus raw-audio zero-persistence and degradation
   regression (S6-05), a real P3 mutation on the disposable fixture, and the joint
   slow-round + detached-task scenario (S6-06).
3. If those pass without source repair, mark the environment rows `SATISFIED` and
   start `S7-01`. If a run exposes a defect, repair it, rerun the affected checks
   and repeat the materially changed cold-review scope.
4. `S7-03` still owes the complete 45,044-line cumulative cold review and one
   independent review; neither has run.

No push is authorized. Machine-private credentials, provider configuration,
browser profiles, raw audio and private run data must stay out of Git.
