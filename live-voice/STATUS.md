# Live Voice current status

> Updated: 2026-08-13
> This is the only mutable source for current branch expectations, stage/task,
> blockers and next actions. Git is the implementation fact; detailed S7 facts
> are in the linked review record.

## Resume capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `origin/hx/0812_live_voice_w3`. The branch was pushed through `a53856de`; the
  S8-readiness integration and S7 re-freeze are local and no additional push is
  authorized.
- `S6 - Alpha Module Closure` / `A1` remains `CLOSED`. All S6-01 through
  S6-06 rows remain `SATISFIED` and the last physical closure is recorded by
  [D116](D116_S6_02_PHYSICAL_CLOSURE_2026-08-13.md).
- `S7 - Candidate Assembly, Verification and Review` / `A2` uses a fail-closed
  exact-handoff rule on the S8-readiness line. Product source remains
  `c209e4a6cb88779277254751aa52354050a813a2`; readiness/build-identity source is
  `e58df618d3ee00776e004e8dfacd8d4d88b744dc`; the final test-only candidate also
  removes a wall-clock-sensitive recognition-deadline assertion. S7/A2 is
  `CLOSED` and S8/A3 is `READY / NOT STARTED` only when the external sanitized
  report and `live-voice.s7-a3-handoff.v1` both validate the exact clean current
  HEAD, the required `b7efa14f` lineage, 40 automatic `PASS`, five real
  `VERIFY`, S7-03 `PASS` and `FROZEN_FOR_A3`. If any validation is absent or
  fails, S7-04 remains `REFREEZE IN PROGRESS` and S8 is `BLOCKED / NOT STARTED`.
- No S8 human journey has run under either branch of that rule, so there is no
  `PASS - INTEGRATED WEB ALPHA` result.

The active execution contract is the
[S5-S8 plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md), the completed S7
packet is
[S7_EXECUTION_PACKET_2026-08-13.md](roadmap/S7_EXECUTION_PACKET_2026-08-13.md),
and the detailed result is
[S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md](S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md).

## S7 dashboard

| Task | Status | Current fact |
|---|---|---|
| S7-01 selective port and candidate freeze | `SATISFIED` | The S7-owned runner, five probes, tests, documentation and frontend script registrations were selectively adapted from `d2727f20`; broad formatting, stale D113 and stale Streaming Speech copies were dropped. The repaired product source is `c209e4a6`. |
| S7-02 automation | `SATISFIED` | The readiness candidate and exact documentation handoff each receive all 40 automatic checks. The source-candidate run completed backend Alpha 1,635 passed / 2 skipped, related regressions 788 passed, 27 frontend commands 847/847 passed and production build 4,640 modules; exact Ruff debt, format/compile, diff/link/hygiene and post-run identity passed. The ignored build froze 180 files / 16,275,167 bytes and private 443 served all 180 exact contents. |
| S7-02 real path | `SATISFIED` | All five probes returned `VERIFY` on one private-only HTTPS/WSS runtime declaration: Speech/Media 5 samples, Agent/Executor 2, Benchmark/Fault 65, Secure Deployment 3 and Privacy 19; failures and forbidden side effects were zero. Speech/Media p50 was 18,188.395 ms and p95/max 19,001.572 ms. |
| S7-03 cumulative Tier-3 review | `SATISFIED` | Cumulative main review and independent read-only review found no open Critical/High/P2 source issue. The S8 readiness boundary closed strict topology/port, S7 report, Task Store/Direct settlement, trace, human-observer and ignored-build/served-content findings; independent exact-`e58df618` verification passed 112 tests. |
| S7-04 A3 handoff freeze | `CONDITIONAL` | The `a53856de` handoff remains history. This row is `SATISFIED` only when a new external report/handoff validates the exact clean current HEAD, runtime digest, 40 automatic PASS, five real VERIFY, S7-03 PASS and `FROZEN_FOR_A3`; otherwise it is `IN PROGRESS` and S8 entry is blocked. No public deployment or real-user project is permitted. |

## S7 accepted limitations

- The controlled Browser bridge could not read origin storage APIs. The privacy
  probe scanned all 19 supplied external capture surfaces against credential,
  PCM16 and authoritative f32le raw/base64 sentinels and found zero forbidden
  persistence, but A3 must still inspect the user-visible browser storage and
  lifecycle behavior rather than treating bridge unavailability as a broad
  browser-forensics guarantee.
- A duplicate unary request ID at the Web transport boundary failed closed with
  a bounded no-response result and zero repeated mutation, rather than returning
  an explicit conflict envelope. Product-layer automated tests retain explicit
  replay/conflict coverage. A3 must continue to judge visible product behavior,
  not transport diagnostic wording.
- The deployment is a private-address-only FQDN with trusted same-origin
  HTTPS/WSS. S7 makes no public-deployment, Production-authentication, wider
  browser/mobile/PWA, RC or audit-grade claim.

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

1. Complete the exact-clean-current-HEAD S7 runner, five real probes and final
   independent identity/provenance review, then freeze the external report and
   handoff. Any failure keeps S8 blocked.
2. Only if the fail-closed S7-04 rule validates, run the read-only S8 preflight
   and create the isolated S8 runtime/Task Store, disposable no-remote fixture,
   effect plan and product-session/scope-correlation binding outside Git.
3. Only after the exact S8 entry audit passes, run
   [ALPHA_SHOWCASE.md](demo/ALPHA_SHOWCASE.md) once. The user physically verifies
   microphone capture, heard playout, interruption, device/permission/lifecycle
   behavior and the complete P1/P2/P3alpha joint journey.
4. Record S8 closeout and only then decide `PASS`, `PARTIAL`, `BLOCKED` or `FAIL`
   under [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md).
