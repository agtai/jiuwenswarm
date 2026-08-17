# Live Voice current status

> Updated: 2026-08-17
> This is the only mutable source for current branch expectations, stage/task,
> blockers and next actions. Git is the implementation fact; detailed S7 facts
> are in the linked review record.

## Resume capsule

- Expected branch/upstream: `codex/live-voice-s8-5-incubator` /
  `origin/codex/live-voice-s8-5-incubator`. This isolated worktree was created
  from clean S8 handoff `a53856de`; its nine S8.5 incubation commits through
  `c9e7aba6` are pushed and synchronized. Any later remote update still requires
  separate exact approval.
- `S6 - Alpha Module Closure` / `A1` remains `CLOSED`. All S6-01 through
  S6-06 rows remain `SATISFIED` and the last physical closure is recorded by
  [D116](D116_S6_02_PHYSICAL_CLOSURE_2026-08-13.md).
- `S7 - Candidate Assembly, Verification and Review` / `A2` is `CLOSED`.
  Product source `c209e4a6cb88779277254751aa52354050a813a2` passed the complete
  automation, five candidate/runtime-bound real probes and cumulative Tier-3
  review. The exact clean documentation-handoff HEAD is recorded by the
  external sanitized `s7-final-report.json` generated after the S7 closeout
  commit.
- Alpha `S8 - Product Acceptance` / `A3` passed on exact source `d33b520e` on
  2026-08-15. The current main branch later advanced to `507c124b` with a
  separate post-Alpha running-adjustment/terminal-notification batch whose own
  physical acceptance remains pending. This incubation branch has not been
  migrated onto that newer main source.
- Incubation task: `S8.5-07 candidate integration and Tier 3 closure`,
  `IN PROGRESS / REVIEW PARTIAL`.
  D-079 permits isolated post-Alpha development but does not close, modify or
  replace S8/A3. The bounded committed-voice write path, durable recovery loop
  and Web controls are implemented locally through `8be8398a`; D-080 and the
  corrected one-revision showcase are at `fc7348f2`. Independent review,
  migration, rehearsals and human acceptance remain open.

The active execution contract is the
[S5-S8 plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md), the completed S7
packet is
[S7_EXECUTION_PACKET_2026-08-13.md](roadmap/S7_EXECUTION_PACKET_2026-08-13.md),
and the detailed result is
[S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md](S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md).
The isolated follow-on contract is the
[S8.5 execution plan](roadmap/S8_5_COMPETITIVE_SHOWCASE_EXECUTION_PLAN_2026-08-13.md);
its code may migrate only after S8 PASS and a fresh Tier 3 integration review.

## S8.5 incubation dashboard

| Task | Status | Current fact |
|---|---|---|
| S8.5-01 decision and contract | `SATISFIED` | D-079 freezes the narrow post-Alpha boundary; the contract, plan, acceptance, showcase and claim matrix are committed at `bc53e75d`. |
| S8.5-02 Core and Store | `IMPLEMENTED / REVIEW PARTIAL` | `caed0ff2` adds immutable `1 -> 2` revision authority, atomic sidecar persistence, replay/concurrency/restart behavior and failpoints. |
| S8.5-03 Bridge and Policy | `IMPLEMENTED / REVIEW PARTIAL` | `f13cfe8d` accepts only committed exact bilingual forms, derives target authority from Store and binds confirmation without generic steering. |
| S8.5-04/05 Executor and verifier | `IMPLEMENTED / REVIEW PARTIAL` | `0c994b1b` fences the predecessor, requires exact cleanup, uses a trusted clean no-remote fixture and persists a registered verifier ACK. |
| S8.5-06 Web projection | `IMPLEMENTED / REVIEW PARTIAL` | `ab200d2c` adds default-off backend/frontend gates, authenticated Store-truth read projection, strict replica and non-inferred Task UI. |
| S8.5-07 candidate integration and Tier 3 closure | `IN PROGRESS / REVIEW PARTIAL` | `8be8398a` composes exact committed Voice, confirmation, Store revision/fence, successor dispatch, terminal reconcile, verifier ACK and Web control/recovery. Local affected automation/static/build checks pass; independent review and migrated-candidate verification remain open. |
| S8.5-08 human product acceptance | `BLOCKED ON S8.5-07 + MIGRATION` | Alpha S8 passed, but migration onto the newer main source, two unchanged rehearsals and the complete user-run showcase have not run. |

The grouped primary review and exact limitations are recorded in
[S8.5 incubation implementation review](S8_5_INCUBATION_IMPLEMENTATION_REVIEW_2026-08-13.md).

## S7 dashboard

| Task | Status | Current fact |
|---|---|---|
| S7-01 selective port and candidate freeze | `SATISFIED` | The S7-owned runner, five probes, tests, documentation and frontend script registrations were selectively adapted from `d2727f20`; broad formatting, stale D113 and stale Streaming Speech copies were dropped. The repaired product source is `c209e4a6`. |
| S7-02 automation | `SATISFIED` | The final product-source run completed all 40 automatic checks: backend Alpha 1,564 passed / 2 skipped, related regressions 788 passed, 27 frontend commands 847/847 passed, production build 4,640 modules, exact Ruff debt, format/compile, diff/link/hygiene and post-run identity all passed. |
| S7-02 real path | `SATISFIED` | All five probes returned `VERIFY` on one private-only HTTPS/WSS runtime declaration: Speech/Media 5 samples, Agent/Executor 2, Benchmark/Fault 65, Secure Deployment 3 and Privacy 19; failures and forbidden side effects were zero. Speech/Media p50 was 18,188.395 ms and p95/max 19,001.572 ms. |
| S7-03 cumulative Tier-3 review | `SATISFIED` | Cumulative main review and independent read-only review found no open Critical/High/P2 source issue. The exact Ruff, PCM16/f32le privacy, bounded socket-close and Provider server-VAD early-final repairs all received affected verification; the final independent affected suite passed 119 tests. |
| S7-04 A3 handoff freeze | `SATISFIED` | The private-only candidate profile, runtime declaration, Provider/Executor, disposable project, flags, warnings/deviations and sanitized final report are bound to the A3 showcase. No public deployment or real-user project was used. |

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

1. Re-evaluate D-079/D-080 against the newer main branch's separately developed
   in-attempt `task.adjust` and terminal-notification behavior; do not blindly
   migrate an overlapping Task authority.
2. From the exact selected main source, selectively port only the still-required
   reviewed S8.5 commits, then obtain an independent Tier 3 review and rerun the
   complete applicable matrix plus the disposable real Executor path. Exclude
   branch-local STATUS/review-only commits.
3. Freeze the machine-private fixture manifest/environment, run two unchanged
   rehearsals, then ask the user to run the complete S8.5 showcase once.
