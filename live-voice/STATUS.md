# Live Voice current status

> Updated: 2026-08-14
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
- `S7 - Candidate Assembly, Verification and Review` / `A2` closed for exact
  candidate `500700501f06dec9a27fda99fdaf73d5ac123d2c`: the external sanitized
  report and `live-voice.s7-a3-handoff.v1` validated the clean HEAD, required
  lineage, 40 automatic `PASS`, five real `VERIFY`, S7-03 `PASS` and
  `FROZEN_FOR_A3`.
- Formal S8 began on that frozen candidate. The human journey produced useful
  product truth but is now `PAUSED / SOURCE REPAIR`. Provisional discovery found
  the two earlier lifecycle defects plus nine additional product defects: ASR
  correction was locked during confirmation; ordinary text/Tool work serialized
  formal voice; P3 mutation failures hid their stable reason; a definitive
  natural-language intent rejection retained the form until reload; status did
  not project terminal task truth; retry eligibility ignored current checkout
  and Executor cleanup truth; the product P3 query Adapter dropped that
  authoritative retry admission; Web reconnect could sleep too long after
  runtime recovery; and a complete AgentServer restart reset one interaction's
  response generation.
- The cumulative repair keeps the Gateway stale-response fence intact,
  revalidates the exact active P2 binding before explicit media Start, separates
  the formal P2 Agent facade from ordinary Web work, and owns response generation
  in a bounded SQLite sidecar derived from the authoritative Task Store so it
  survives AgentServer restart without retaining raw product IDs. The UI keeps
  recognized text editable before commit, consumes authoritative retry admission
  and stable failure reasons, projects terminal Task truth, unlocks after an
  exact server rejection, and bounds reconnect delay to two seconds. The exact
  affected suites currently pass 332 integrated Web tests and 184 backend
  product/Task/durability tests; Python Ruff, format and diff checks pass, and
  the production frontend build completes 4,640 modules. The committed 16-path
  repair and the subsequent product-status Adapter and real-resolver
  stable-reason corrections each received affected Tier-3 `APPROVE`, with no
  open Critical, High or P2 finding. This working tree is not a frozen candidate:
  coherent commit, complete S7
  re-verification/re-freeze and a fresh formal S8 closeout remain mandatory
  before any `PASS - INTEGRATED WEB ALPHA` result.
- By explicit user direction, the already observed scope-correlation mismatch
  is retained as a non-blocking provisional S8 deviation for final human
  judgment. Continued S8 work before re-freeze is discovery only; its events
  cannot be relabeled as exact-candidate formal acceptance evidence.

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
| S7-04 A3 handoff freeze | `REFREEZE REQUIRED` | Exact `50070050` was frozen and admitted S8. The current lifecycle repairs change source, so that handoff is now historical and a final exact-clean-HEAD report/handoff must be regenerated after provisional discovery. No public deployment or real-user project is permitted. |

The table records the last closed S7 line. The current source-repair tree
supersedes that candidate for further product work and therefore returns S7-04
to `REFREEZE REQUIRED` until the final batched S8 findings are repaired and the
complete S7 verification/handoff is regenerated.

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

1. Commit the independently approved and broadly verified cumulative repair as
   one coherent local candidate.
2. Rebuild/restart the private runtime and continue user-directed S8 discovery
   with Chrome, Computer Use, sanitized logs, Store/Executor inspection and
   other automated observers. Record non-blocking findings through the pass,
   batch-fix them, and repeat until only physical audio/device and final human
   judgment remain; provisional events are never relabeled as formal proof.
3. Run the complete S7 runner, five real probes, cumulative Tier-3 review and
   external handoff freeze on the final exact clean HEAD after the last source
   repair.
4. Run a fresh exact-candidate S8 entry audit and all automated acceptance, then
   hand the remaining physical product journey to the user for the final
   `PASS`, `PARTIAL`, `BLOCKED` or `FAIL` decision under
   [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md).
