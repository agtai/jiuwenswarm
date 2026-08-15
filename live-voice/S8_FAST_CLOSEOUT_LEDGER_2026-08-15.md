# S8 fast closeout ledger

> Date: 2026-08-15
> Mode authority: D-079
> Execution contract:
> [S8 fast closeout packet](roadmap/S8_FAST_CLOSEOUT_PACKET_2026-08-15.md)
> Mutable project state: [STATUS.md](STATUS.md)

This ledger records D-079 closeout findings, dispositions and the final-host
decision. It is not acceptance evidence and does not replace the external S7
report, `live-voice.s7-a3-handoff.v1` or the S8 observation record.

## C0 final-host decision

| Decision | Result | Consequence | Authority |
|---|---|---|---|
| Final acceptance host | Current host | Keep Phase C, D and E on this host; skip Phase D′ destination transfer. Reconfirm the exact environment through checks rather than assuming reuse. | User confirmation, 2026-08-15 |

## Finding ledger

| ID | Finding | Class | Disposition | Evidence reference |
|---|---|---|---|---|
| F-001 | Product-generated scope-correlation mismatch | Non-blocking accepted deviation | Accepted deviation; retain for final human judgment and do not repair in this window. | `STATUS.md` resume capsule; prior explicit user direction |
| F-002 | Known P2 context test may fail intermittently only under the complete backend load | D-079 test-evidence deviation | If it fails once during C2 after the accepted isolated/file-level proof remains valid and product source is unchanged, record the occurrence and proceed; do not return to Phase B. | D-079 flaky rule; fast-closeout packet §1.4 and §4 C2 |
| F-003 | Integrated Web mounted on a not-yet-persisted `new` Session retried P2 activation 718 times, received fail-closed errors and showed `Request timed out` | Non-blocking product finding | Ledger only; do not repair in this closeout window. No Task or fixture mutation occurred, the persisted-Session P2/Tool path passed, and the exact S8 journey binds a real product Session before its first action. | Phase B private runtime delta and browser observation |
| F-004 | One fixed-corpus whole-route round completed while the streaming Speech transport logged one retained-socket cleanup-incomplete event | Non-blocking runtime finding | Ledger only; do not repair in this closeout window. The round completed with all 302 media frames acknowledged, STT/Agent/TTS/playout success, zero credential hit and zero forbidden effect; services remained healthy and Store/Executor settlement was clean. | Phase B private whole-route result and runtime log delta |
| F-005 | P2 partial-activation open-failure rollback test failed once only inside the 1,673-case C2 backend load | D-079 test-evidence deviation | Accepted deviation; do not repair. The exact case passed in isolation, its complete 45-case owner file passed, and a wrapper invoking the unchanged original test function passed 100/100 repetitions. Product source did not change, the other 1,670 backend cases passed with two platform skips, the related 789-case regression matrix passed, and all five real probes reached `VERIFY`. | Failed external C2 report for `c04033380`; affected Phase B re-entry checks |

## Phase A review

| Boundary | Result | Verification | Review limitation |
|---|---|---|---|
| `52aaa5ec` + `370ee9b8`: test-only P2 acknowledged-context oracle | `APPROVE` — no open Critical, High or P2 finding | Target regression `1/1`; complete owning file `95/95`; Ruff, format, frozen dependency and installed-package checks passed. Cold review confirmed that the test waits for a real presentation unit, leaves it unacknowledged, proves zero assistant-history persistence, and submits the successor turn with empty context. | Independent `codex review` was attempted but the installed `codex-cli 0.111.0` cannot run the current `gpt-5.6-sol` model. Main performed the recorded equivalent cold review; this tooling limitation remains explicit. |

## Phase B sweep

The breadth-first sweep finished before findings were classified or reported.
It found zero D-079 blocker and consumed zero repair batch. F-003 and F-004 are
the only new non-blocking findings; they remain ledger-only and were not fixed.

| Surface | Result | Checked facts |
|---|---|---|
| Candidate and reused environment | `PASS` | Exact starting tip `bb11530ce`; branch/upstream 0/0; current-host AgentServer/WebChannel/Gateway/private HTTPS listeners healthy; the active processes continued to use the prior isolated runtime rather than the default user data root; a fresh diagnostic no-remote fixture was clean and authorized only `notes.txt`. |
| Backend Alpha matrix | `PASS` | 1,671 passed, 2 platform skips, zero failure across 1,673 collected cases. The known P2 acknowledged-context test passed in this full load. |
| Backend related regressions | `PASS` | 789 passed, zero failure across AgentServer, WebChannel, Gateway, AutoHarness, shared contracts and Web privacy/raw-file seams. |
| Frontend and production build | `PASS` | 27 formal Live Voice scripts completed with 878 passing assertions and zero failure; the production build transformed 4,641 modules; the private proxy served the exact rebuilt entry asset. |
| P1/P2 real route | `PASS` with F-003/F-004 retained | One fixed-corpus same-origin route acknowledged 302/302 media frames and completed STT, committed P2 dispatch, real Agent final, streaming TTS and playout receipt with zero credential hit and zero forbidden effect. A separate private HTTPS/WSS and Agent round-trip passed, and a persisted product Session completed a read-only P2/Tool turn without changing its fixture. |
| P2 slow/interruption and joint P2/P3 | `PASS` | The exact automated slow-conversation/detached-task/cancel-domain integration and response-interruption fences passed. No synchronous slow-Harness wait or cross-domain cancellation was observed. |
| P3 structured/natural/restart | `PASS` | Structured confirmation, committed natural-language authority, negative zero-mutation cases, restart reconciliation and joint-domain matrices passed. The reused real Store contained three terminal Tasks/Attempts (one completed, two cancelled), five delivered outbox rows and zero active Executor owner/lease. |
| Degradation, privacy and cleanup | `PASS` with F-004 retained | Feature-off, permission/device/media/provider/degradation and cleanup matrices passed; scan found zero secret literal, zero raw audio file/header, zero traceback and zero unhandled exception in the Phase B delta. Historical reused-runtime errors remained outside the current delta and were classified separately. |

The first C2 freeze attempt on exact `c04033380` completed the full runner but
did not freeze: 39 automatic checks passed, all five real probes reached
`VERIFY`, and the backend Alpha matrix alone reported F-005. Per the packet, C2
returned to Phase B rather than treating that new case as the pre-authorized
F-002 exception. The affected re-entry checks then established the D-079
load-flaky conditions recorded above. F-005 is non-blocking, consumes no repair
batch, and is ledger-only; the failed report remains diagnostic and cannot
authorize S8. A docs-only C1 re-settlement precedes the next exact-candidate
runner.

## Final Alpha decision

| Item | Result | Record |
|---|---|---|
| Exact tested source | `d33b520e0d21ae0829d30814d77a01cc18256f09` | Current-host C2/C3 handoff and fresh S8 session |
| Machine-eligible S8 scope | `PASS` | P2 real route and joint run; structured/natural P3alpha; restart/fail-closed/settlement; expected fixture effect; privacy and log checks |
| Physical human scope | `PASS` | User confirmation on 2026-08-15 covers physical microphone/critical committed text, heard playout, voice barge-in, device/permission behavior and one continuous joint journey |
| Accepted deviations | Retained | F-001 through F-005 remain non-blocking and are not repaired or relabeled |
| Strict S8 helper | No PASS claimed | F-001 prevents truthful pre-generated product-correlation binding; the fail-closed template remains preserved, while the explicit user decision and separately hashed machine evidence form the decision record |
| S8-03 decision | `PASS — INTEGRATED WEB ALPHA` | Explicit user decision, 2026-08-15; external decision record SHA-256 `e34dea559c3829f7624b3c340fdeab83f1f6a744ae118ca9bf1dd5f45f90ac16` |

## Cleanup

- Five product-session Tasks, Attempts and Direct Executor rows were terminal;
  seven outbox rows were settled; owner and lease state were released.
- Dedicated AgentServer, WebChannel, Gateway and private proxy processes were
  stopped. Ports `18092`, `19000`, `19001` and `443` were released.
- The no-remote disposable fixture contained only the predeclared `notes.txt`
  effect and was moved to the Windows Recycle Bin. Private external evidence is
  preserved.
- The tested source remained clean at exact `d33b520e` through A3 and cleanup.
  This final tracked documentation update is a post-A3 closeout record, not a
  new tested product candidate. The final external cleanup record SHA-256 is
  `e79c130a4b145ccbb0f21a04cf6ce78c85bd2a7c297789368e156f11297aee03`.
