# S8 fast closeout execution packet

> Frozen contract: 2026-08-15. Mode authority: D-079 in
> [DECISIONS.md](../decisions/DECISIONS.md). Mutable state:
> [STATUS.md](../STATUS.md) — read it before every phase. Pass/fail authority:
> [ALPHA_ACCEPTANCE.md](../validation/ALPHA_ACCEPTANCE.md). Human journey:
> [ALPHA_SHOWCASE.md](../demo/ALPHA_SHOWCASE.md). Runner/probes:
> `scripts/live_voice/S7_AUTOMATION.md`; S8 helper:
> `scripts/live_voice/S8_READINESS.md`. Environment:
> [E2E_RUNBOOK.md](../runbooks/E2E_RUNBOOK.md).
>
> This packet operationalizes the remaining S7/S8 window under the
> user-approved D-079 fast-closeout mode. Within this window it supersedes the
> per-repair re-freeze cadence; it does not change Alpha acceptance content,
> D-032 invariants or the external fail-closed freeze rule, and it ends at the
> S8-03 decision.

## 0. Cold-start capsule

Read this section and §1 first; they are sufficient to begin Phase A.

- **Goal:** finish Integrated Web Alpha efficiently: converge remaining defects
  in one bounded discovery/repair phase, perform ONE contract-grade freeze
  (complete runner + five real probes + external handoff), produce the
  machine-eligible S8 evidence, then hand the short physical acceptance and the
  final decision to the user.
- **Starting source:** branch `hx/0812_live_voice_w3` at exact
  `bb11530ce` (`docs(live-voice): freeze D-079 fast S8 closeout mode`), the
  docs-only successor of `370ee9b89`; verify with `git log -1` and a clean
  worktree. All fourteen S8-discovered product repairs and the P2 context
  test-oracle rework are already committed. The tip has NOT yet received:
  review credit for the final test-oracle boundary, the final complete runner,
  or an external `FROZEN_FOR_A3` handoff. Formal S8 is paused until Phase C
  completes.
- **Why this packet exists:** the prior cadence (each repair → complete S7
  re-verification → re-freeze → fresh diagnostic → next repair) consumed ~25 h
  and six freeze cycles without reaching the human journey. D-079 replaces it
  for this window with batch repair + a single final freeze.
- **Mechanisms that already exist and must be reused, not rebuilt:** the
  external sanitized report + `live-voice.s7-a3-handoff.v1` external-only
  freeze; the complete S7 runner and five real probes; the S8 readiness helper
  and entry audit; the private same-origin HTTPS/WSS runtime.
- **Known environment trap:** after a runtime recreation the isolated data-root
  `config/.env` can reload a stale localhost-only Origin allowlist; P1 then
  fails `MEDIA_ORIGIN_REJECTED` while P2/P3 still work. Verify the private-FQDN
  Origin binding after every runtime recreation. This is environment-only; no
  product source change is authorized for it.
- **Known flaky case:** one P2 context test passes in isolation (hundreds of
  repetitions) and in its complete 95-case file, but has failed intermittently
  only under the full 1,673-case backend load. Apply the D-079 flaky rule
  (§1.4); do not rewrite it again in this window.

## 1. Mode rules (D-079 operational summary)

1. **Fast phase verification:** each repair lands with affected-scope tests and
   one ledger line (§7). No per-repair complete runner, candidate freeze,
   external report or handoff.
2. **Blocking triage.** Fix now only findings in these classes:
   (a) unsafe/partial/duplicate mutation or data loss; (b) privacy, credential
   or raw-audio exposure; (c) dead-end UX — the core journey cannot continue
   without reload/restart; (d) a mandatory showcase section cannot be completed
   at all. Everything else — wording, diagnostics, polish, rare-path
   recovery — goes to the deviation ledger and is NOT fixed in this window.
3. **Convergence:** sweep breadth-first and report ALL findings before fixing
   anything. Phase B ends when one complete sweep yields zero new blocking
   findings. Hard cap: if blocking findings still appear after three fix
   batches, stop and report to the user with the ledger instead of iterating.
4. **Flaky rule:** a test that passes ≥100 isolated repetitions and its
   complete owning file, with product source unchanged, failing only
   intermittently under full-suite load, is recorded as an accepted
   test-evidence deviation. It does not block the final runner and is not
   rewritten again.
5. **Docs-then-freeze order (final phase only):** settle ALL documentation on
   the final source first, then run the single complete runner + probes on that
   exact clean HEAD, then produce the external report/handoff. Zero tracked
   edits after the freeze.
6. **Machine/human split:** automation performs and records every
   machine-eligible check (clicks, queries, refresh/reconnect, restart
   reconciliation, degradation, privacy/log scans, Store/Executor settlement)
   as section evidence labeled `machine-verified`. The user performs only:
   physical microphone speech, heard playout quality, voice barge-in, physical
   device/permission behavior, one continuous joint journey, and the final
   decision. Machine events are never relabeled as human observations.

## 2. Phase A — settle the tip

- A1. Obtain the affected review credit (independent read-only review or the
  recorded equivalent) for the final test-oracle boundary
  (`52aaa5ec` + `370ee9b8`; test-only, no product source).
- A2. Confirm exact branch/commit, clean worktree and dependency lock. Do not
  start any freeze yet.

## 3. Phase B — bounded discovery sweep

- B1. Recreate or verify the isolated private runtime per the runbook; check
  the §0 Origin-allowlist trap; record sanitized environment labels.
- B2. Run the automated S8 sweep breadth-first and to completion — platform
  lifecycle (machine-checkable parts), P1 fixed-corpus route, P2 text/Tool plus
  slow round plus interruption, P3 structured plus committed natural-language
  plus restart reconciliation, the joint P2/P3 scenario, degradation profiles,
  privacy/log scans, Store/Executor settlement. Collect all findings first; do
  not stop at the first defect and do not fix mid-sweep.
- B3. Triage every finding per §1.2: blocking → fix batch; non-blocking →
  ledger entry with disposition.
- B4. One fix batch = coherent commits with affected tests passing and one
  ledger line each. After a batch, rerun only the affected sweep sections.
- B5. Exit per §1.3 convergence, or stop and escalate at the three-batch cap.

## 4. Phase C — the single contract-grade freeze

- C0. **Host confirmation (ask the user once, then never switch):** does the
  final acceptance run on this host or on the designated destination server?
  Staying on the current host skips §6 entirely; choosing the destination adds
  §6 before Phase D.
- C1. Documentation settles first: one coherent STATUS update, the ledger
  record, any dated record — committed. The freeze targets the resulting exact
  clean HEAD.
- C2. Run the complete S7 runner plus all five real probes on that exact HEAD.
  Expected: 40 automatic `PASS`, five `VERIFY`, nonzero samples, zero failures
  and zero forbidden effects. If the only failure is the known flaky case
  tripping once, record the §1.4 deviation and proceed. Any other failure is a
  blocking finding: return to Phase B and count it against the batch cap.
- C3. Produce the external sanitized report and `live-voice.s7-a3-handoff.v1`
  binding the exact HEAD and runtime digest; record S7-03 `PASS` and S7-04
  `FROZEN_FOR_A3`. Zero tracked edits afterward.

## 5. Phase D — machine-eligible S8 evidence on the frozen candidate

- D1. Fresh S8 entry audit against the new handoff (candidate identity must
  match; a mismatch is `BLOCKED`, not an invitation to patch). Create the fresh
  disposable fixture, product Session and scope correlations.
- D2. Execute and record every machine-eligible showcase section, each tagged
  `machine-verified` with its evidence reference.
- D3. Confirm the remaining set for the user is exactly the physical set in
  §1.6, and prepare the preflight facts for Phase E.

## 6. Phase D' — destination transfer (only if C0 chose the destination)

Checkout the exact frozen commit on the destination server without any later
tracked edit; recreate the isolated private runtime there (§0 trap applies);
rerun the complete runner plus five probes; produce a destination-owned
external report/handoff for that exact candidate/runtime; then run Phase D
there. Nothing transfers from the source host except source commits: not the
report, runtime digest, fixture, product Session, scope correlations or any
human observation.

## 7. Ledger

Create `live-voice/S8_FAST_CLOSEOUT_LEDGER_2026-08-15.md` on first use. One
line per entry: finding — class — disposition (`fixed in batch N` /
`accepted deviation` / `deferred post-Alpha`) — evidence reference. Seed
entries:

- Product-generated scope-correlation mismatch — accepted non-blocking by
  explicit prior user direction.
- Load-flaky P2 context test — accepted test-evidence deviation per §1.4 if it
  trips during C2.

The Phase C cumulative review consumes this ledger; keep it current.

## 8. Phase E — human acceptance and decision (the user, one sitting)

- E1. Preflight (~30 min): candidate identity, environment, devices, flags.
  Mismatch is `BLOCKED`.
- E2. One continuous physical journey (~30–60 min) per the showcase: P1 real
  speech and heard playout, P2 slow-work interruption by voice, P3 committed
  natural-language control, the joint scenario, plus physical
  permission/device checks. Machine-verified sections are referenced, not
  re-executed by hand.
- E3. S8-03 decision under Alpha acceptance: `PASS`, `PARTIAL`, `BLOCKED` or
  `FAIL`. Ledger deviations are recorded with the decision, not fixed. Cleanup
  per showcase §8; one final STATUS update closes the packet.

## 9. Forbidden in this window

- Any per-repair complete runner, freeze or handoff.
- Rewriting the known flaky case again.
- Relabeling machine evidence as human observation, or provisional discovery as
  formal acceptance evidence.
- Scope growth: the S5–S8 plan §7 exclusions stay in force.
- Reviving retired signed Gate machinery.
- Any remote push without separate explicit approval for the exact
  remote/ref/commits/update mode.

## 10. Reporting

End each phase with one concise report: what ran, findings, ledger delta, next
step. Do not pad reports with unchanged historical narrative; STATUS carries
state, this packet carries the contract, the ledger carries dispositions.
