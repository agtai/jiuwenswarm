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
