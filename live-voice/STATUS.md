# Live Voice current status

> Updated: 2026-08-13
> This is the only mutable source for current branch expectations, stage/task,
> blockers and next actions. Git is the implementation fact; detailed S7 facts
> are in the linked review record.

## Resume capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `origin/hx/0812_live_voice_w3`. The branch was pushed through `a53856de`; the
  current S8-readiness integration is local and no additional push is authorized.
- `S6 - Alpha Module Closure` / `A1` remains `CLOSED`. All S6-01 through
  S6-06 rows remain `SATISFIED` and the last physical closure is recorded by
  [D116](D116_S6_02_PHYSICAL_CLOSURE_2026-08-13.md).
- The prior `S7 - Candidate Assembly, Verification and Review` / `A2` product
  closure remains valid at product source
  `c209e4a6cb88779277254751aa52354050a813a2` and documentation-handoff HEAD
  `a53856de0af12e2c1b11e6cc8f2dc0a18150a99a`.
- Current stage/node: `S7-04` / `A2`, `REFREEZE IN PROGRESS`. The S8 readiness
  workflow from `b7efa14f` is being integrated without product-source changes.
  Review found that the external proxy's Git-ignored `frontend/dist` also needs
  an exact S7 build digest plus S8 disk/served-content binding; that runner and
  readiness automation repair is in the current candidate scope.
  Because this changes candidate bytes, the previous S7 report is historical
  until a new exact clean HEAD receives complete automation, five real probes,
  cumulative review and a frozen A3 handoff.
- `S8 - Product Acceptance` / `A3` is `BLOCKED / NOT STARTED` during the
  re-freeze. The complete human Alpha journey has not run, so there is no
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
| S7-02 automation | `SATISFIED` | The final product-source run completed all 40 automatic checks: backend Alpha 1,564 passed / 2 skipped, related regressions 788 passed, 27 frontend commands 847/847 passed, production build 4,640 modules, exact Ruff debt, format/compile, diff/link/hygiene and post-run identity all passed. |
| S7-02 real path | `SATISFIED` | All five probes returned `VERIFY` on one private-only HTTPS/WSS runtime declaration: Speech/Media 5 samples, Agent/Executor 2, Benchmark/Fault 65, Secure Deployment 3 and Privacy 19; failures and forbidden side effects were zero. Speech/Media p50 was 18,188.395 ms and p95/max 19,001.572 ms. |
| S7-03 cumulative Tier-3 review | `SATISFIED` | Cumulative main review and independent read-only review found no open Critical/High/P2 source issue. The exact Ruff, PCM16/f32le privacy, bounded socket-close and Provider server-VAD early-final repairs all received affected verification; the final independent affected suite passed 119 tests. |
| S7-04 A3 handoff freeze | `IN PROGRESS` | The `a53856de` handoff is preserved as completed history. S8 readiness tooling plus exact ignored-`dist`/private-443 content binding is being integrated onto that line; a new exact-candidate report and external `live-voice.s7-a3-handoff.v1` must be frozen before S8 entry. No public deployment or real-user project is permitted. |

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

1. Finish the S8 readiness and S7 production-build identity integration plus
   affected checks without changing the reviewed product source, private
   profile, flags or runtime topology.
2. Commit one coherent local candidate, rerun the complete S7 runner and five
   real probes, complete cumulative review and freeze a new external A3 handoff.
3. Only after the exact S8 entry audit passes, run
   [ALPHA_SHOWCASE.md](demo/ALPHA_SHOWCASE.md) once. The user physically verifies
   microphone capture, heard playout, interruption, device/permission/lifecycle
   behavior and the complete P1/P2/P3alpha joint journey.
4. Record S8 closeout and only then decide `PASS`, `PARTIAL`, `BLOCKED` or `FAIL`
   under [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md).
