# Live Voice current status

> Updated: 2026-08-13
> This is the only mutable source for current branch expectations, stage/task,
> blockers and next actions. Git is the implementation fact; detailed S7 facts
> are in the linked review record.

## Resume capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `origin/hx/0812_live_voice_w3`. The work is local-only; no push is authorized.
- `S6 - Alpha Module Closure` / `A1` remains `CLOSED`. All S6-01 through
  S6-06 rows remain `SATISFIED` and the last physical closure is recorded by
  [D116](D116_S6_02_PHYSICAL_CLOSURE_2026-08-13.md).
- Current stage/node: `S7 - Candidate Assembly, Verification and Review` /
  `A2`, `ENVIRONMENT / NOT CLOSED`.
- Comparison base: `2a69c2b87d0ee080a4a30421cbcbcdf93183f340`.
- S7 implementation source through `4cb834cf969e9b419c72cb75ff108426775dcd08`;
  the exact clean documentation-handoff HEAD is recorded by the external
  sanitized `s7-final-automation.json` report generated after the S7-04 commit.
- Automation and cumulative source review are complete. Five canonical real
  probes were invoked but each has zero valid samples because the formal S7
  private runtime/observation inputs are unavailable. Historical S6 evidence
  has not been relabelled or rebound to the new candidate.
- `S8/A3` has not started. The Alpha human acceptance result remains unavailable.

The active execution contract is the
[S5-S8 plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md), the S7 packet is
[S7_EXECUTION_PACKET_2026-08-13.md](roadmap/S7_EXECUTION_PACKET_2026-08-13.md),
and the detailed result is
[S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md](S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md).

## S7 dashboard

| Task | Status | Current fact |
|---|---|---|
| S7-01 selective port and candidate freeze | `SATISFIED` | The S7-owned runner, five probes, tests, documentation and frontend script registrations were selectively adapted from `d2727f20`; broad formatting, stale D113 and stale Streaming Speech copies were dropped. Latest S6 source remains authoritative. |
| S7-02 automation | `SATISFIED` | The full committed-candidate runner covers backend/regression suites, every tracked Live Voice frontend test, compatibility tests, TypeScript/build, Ruff exact-debt fingerprint, format/compile, diff/link/hygiene and post-run identity. The authoritative final run is the external sanitized report named above. |
| S7-02 real path | `ENVIRONMENT` | `speech-media`, `agent-executor`, `benchmark-fault`, `secure-deployment` and `privacy` each have 0 valid S7 samples. The first, second, third and fifth lack fresh candidate-bound observations/captures; the current controlled origin is localhost while the formal S7 deployment probe requires a non-loopback private FQDN with trusted TLS. |
| S7-03 cumulative Tier-3 review | `SATISFIED` | Self-review, cumulative cold review and an independent read-only review found no Critical/High product-source issue. The Ruff and PCM16 privacy P2s were fixed in `c2d3b2c4`; affected review found the formal f32le representation gap, which was fixed in `4cb834cf`. The stale-status P2 documentation finding is also fixed. Real-path evidence remains an explicit environment gap, not a source PASS. |
| S7-04 A3 handoff freeze | `ENVIRONMENT` | The handoff documents and user-run showcase are prepared, but A3 is not ready to execute because A2 real-path verification is incomplete. |

## Active blocker and shortest remaining path

No known product-source or automated-verification defect is open. Closure needs
one controlled environment on the exact final candidate that provides:

1. a non-loopback private DNS name resolving only to private addresses, trusted
   same-origin HTTPS/WSS, and the declared proxy/CSP/CORS/media route;
2. fresh candidate/runtime-bound Speech/Media, Agent/Executor and
   Benchmark/Fault observations plus a complete 19-surface privacy capture;
3. all five canonical probes rerun through `--require-real`, followed by an
   affected evidence review of the actual producer invocations and sanitized
   results.

The environment owner must supply or authorize the private DNS/certificate
trust and observation-producer run. Do not manufacture artifacts, copy old S6
aggregates, use a real user project, create a Provider key/project, change
billing, or deploy publicly. After all five results reach `VERIFY` on one exact
candidate, update this dashboard and only then start the user-owned S8/A3
journey.

## Frozen product boundary

- Gateway-only key: `LIVE_VOICE_SPEECH_API_KEY`.
- Speech: official OpenAI origin,
  `gpt-4o-mini-transcribe-2025-12-15`,
  `gpt-4o-mini-tts-2025-12-15`, voice `marin`.
- Degradation: Streaming -> W2 Batch -> Browser/text, explicitly identified.
- Agent: JiuwenSwarm Agent Provider. P3alpha: formal Task Core,
  `DirectProjectCodeExecutorAdapter`, disposable no-remote local Git fixtures.
- Deployment: private same-origin HTTPS/WSS; no public deployment.
- The D107 migration corrections remain authoritative. Do not restore signed
  Gate tooling, Replacement Ledger, fixed manifests, migrated APIs or
  `schedule.*` as P3alpha Task authority.

## Next actions

1. Environment owner supplies the bounded private DNS/TLS route and runs the
   four missing observation/capture producers without exposing credentials or
   private paths.
2. Main reruns the five canonical probes and the complete `--require-real`
   candidate verification, then reviews the exact real evidence.
3. If and only if S7/A2 closes, the user runs
   [ALPHA_SHOWCASE.md](demo/ALPHA_SHOWCASE.md) for S8/A3. Do not claim
   `PASS - INTEGRATED WEB ALPHA` before that human journey passes.
