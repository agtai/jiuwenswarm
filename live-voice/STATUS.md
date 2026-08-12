# Live Voice current status

> Updated: 2026-08-12
> This is the only mutable source for current branch expectations, stage/task,
> module closure state, blockers and next actions. Detailed evidence lives in
> the linked review record; Git remains the implementation fact.

## Resume capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `origin/hx/0812_live_voice_w3`. Verify live Git before trusting prose.
- Current stage/node: `S6 - Alpha Module Closure` / `A1`, `ENVIRONMENT`.
- Current task: complete the declared real Provider/device/private-topology
  acceptance for `S6-02`, `S6-03`, `S6-05` and the real-path portion of
  `S6-06`; source and deterministic automation are integrated and reviewed.
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
| S6-02 P1 speech/browser lifecycle | `ENVIRONMENT` | Streaming contract, official-OpenAI Gateway providers, explicit Streaming -> Batch -> Browser/text fallback, device selection, Server VAD/EOT and Web lifecycle automation are complete and default-off. A real key, Chrome, microphone/output and heard playout run are still required. |
| S6-03 P2 realtime conversation | `ENVIRONMENT` | Slow/failing harness, network fault/load, notification, stop/revise/delegate, cancel/fence and latency instrumentation are automated. Real Jiuwen Agent/network/device measurements remain. |
| S6-04 P3alpha Task vertical | `SATISFIED` | Structured and committed natural-language create/status/cancel traverse the current formal Task Core, exact authority checks, SQLite Store/outbox and `DirectProjectCodeExecutorAdapter` on a disposable Git fixture; no second Task authority exists. |
| S6-05 observability/privacy/Web | `ENVIRONMENT` | Benchmark p50/p95/failure/sample reporting, privacy/zero-persistence checks, private-only same-origin deployment observation and degradation automation are complete. A real private HTTPS/WSS candidate and whole-stack report remain. |
| S6-06 joint route | `ENVIRONMENT` | The deterministic product-composition scenario passes across the registry, safety gate, P2 turns, formal Task bridge/Core/Direct Executor, exact status/cancel, progress/terminal return, degradation and privacy seams. Fake external claims are not treated as proof of the required physical P1/P2 route. |

No known S6 source defect or deterministic-automation defect remains after the
final independent review. The open rows are environment evidence, not hidden
fallback success or accepted product deviations.

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

1. On an approved private candidate machine, configure the Gateway-only Speech
   key, current Jiuwen Agent, exact Chrome/device permissions, private
   same-origin HTTPS/WSS and isolated runtime/project roots.
2. Run the real P1/P2/whole-stack benchmark, fault, degradation, privacy and
   heard-playout acceptance; record only sanitized labels/results.
3. If those runs pass without source repair, mark the environment rows
   `SATISFIED` and start `S7-01`. If a run exposes a defect, repair it, rerun the
   affected checks and repeat the materially changed cold-review scope.

No push is authorized. Machine-private credentials, provider configuration,
browser profiles, raw audio and private run data must stay out of Git.
