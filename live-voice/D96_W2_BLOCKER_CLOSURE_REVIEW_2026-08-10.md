# D96 W2 blocker-closure review — 2026-08-10

## Decision

The four runtime/source findings from the discarded `a7de738d69` rehearsal are source-closed on local integration commit `b885af20`. The P2 and P3 production probes are also implemented and reviewed. This is implementation and mutable no-evidence diagnostic closure only: no signed rehearsal ran, no immutable evidence was imported, and the W2 Replacement Ledger remains `0/100`.

## Integrated scope

The linear local chain after remote baseline `b4abff6c` is:

1. `a6363ce2` — initial P2 activation-result reconciliation, later superseded by the durable design.
2. `8dabc336` — P3 create/cancel/retry lifecycle reconciliation in the real mounted product panel.
3. `6a352ade` — confirmation fencing plus disconnect/reconnect recovery.
4. `5141d86e` — server-owned progress ACK and canonical voice-origin binding.
5. `c626114f` — real P2/P3 production fault probes.
6. `780b4cdf` — authority follow-up: server-owned response identity, exact ACK/result binding, bounded origin lifecycle and Agent round binding.
7. `08d5e394` — durable operation-first P2 refresh recovery with Web Locks and CAS fencing.
8. `b885af20` — deterministic P3 fault-probe quiescence, entry counters and post-stop cleanup oracle.

No remote ref was updated.

## Closed findings

### Progress/UI ACK

- The attempt is derived from retained server delivery authority and returned to Web; the client does not self-report it.
- Web and the observer require the exact task/attempt/delivery binding and reject missing, foreign or old bindings without business/evidence effects.
- Closed-delivery replay remains deterministic.

### Voice task origin

- Conversation Runtime allocates the canonical response identity; the browser no longer declares a task response ID.
- The accepted origin binds request, session, activation, correlation, interaction, response generation, turn and commit.
- Close/replay/create races, partial-result tombstones, eviction and one-time P3 consumption are bounded and fail closed.

### P2 durable recovery

- The v2 same-tab journal checkpoints one bounded, exact, secret-free submit/ACK/barge-in envelope before transport.
- Recovery replays and adopts the exact business operation before activation reconciliation or close.
- Chrome Web Locks provide the liveness lease and journal owner/token/epoch provides the CAS fence; legacy generic `result_unknown` remains a zero-callback barrier.
- Foreign results, invalid envelopes, missing Web Locks and unknown/expired server state cannot open a successor.

### P3 UI lifecycle

- Accepted create selects cancel; cancelled A exposes retry B; completed/cancelled B can expose retry C on the same task.
- Status and complete event history are authority-derived and fenced by session, task, leaf identity and generation.
- Confirmation is locked during inspection; disconnect cancels truth and reconnects the exact leaf before inspection resumes.

### Production fault probes

- P2 obtains a real server-authored presentation, rejects a schema-valid `MAX_SAFE_INTEGER` cursor with `PROTOCOL_VIOLATION/ACK_BEYOND_PRODUCED_CURSOR`, exactly replays that error receipt and then accepts a fresh legal ACK.
- P3 holds the real Direct Executor path after session-child Agent initialization and before Provider/Tool execution. A nonterminal retry is rejected twice as `CONFLICT/TASK_RETRY_REQUIRES_TERMINAL` with Task/SQLite/Git/Executor/Agent/Tool/evidence state unchanged and `_p3_issue_operations +0`.
- Both A and B are explicitly driven to running with delivered dispatch and a frozen real Agent before legal cancellation. Success is printed only after stop and after exact A/B cancelled lineage, Direct journal release, delivered/unclaimed outbox, command set, worker cleanup, Agent release, Git cleanliness and no-evidence assertions pass.

## Verification

- Main integrated Web suite: `233/233` PASS.
- Frontend TypeScript: `tsc --noEmit` PASS.
- Main focused Python integration set: `192/192` PASS.
- Frontend contract v2: `32/32` PASS.
- Product composition registry: `67/67` PASS.
- Project Executor: `78 passed, 2 skipped`.
- Portable W2 rehearsal toolkit after the final probe fix: `45/45` PASS.
- Final D-069 focused diagnostic tests, including wrong-successor, residual-outbox-claim and residual-owner/lease counterexamples: `10/10` PASS.
- Ruff, `py_compile` and `git diff --check`: PASS.

The final disposable no-evidence run used registered project `proj_e7082c96`, Session `sess_noevidence_registered_90aaecb9527d` and a fresh SQLite database. It exited `0` with the P3 successor explicitly observed running before cancellation. Durable truth contained one task terminal/cancelled, attempts A and B both terminal/cancelled, two delivered dispatch plus two delivered cancel outbox rows with all claim fields null, and exactly create/cancel/retry/cancel commands. The disposable Git project remained clean at HEAD `80e5a11ae17ff87f9529c0b7b1e8767bdbe05dd2`; no JSONL evidence file was created. Provider variables were pointed at a local non-listening endpoint and the barrier stopped execution before Provider or Tool invocation.

## D-053 review closure

- Implementation self-review covered the complete integrated diff and the final two-file probe follow-up.
- Cold reviews found and closed authority, durable-journal, UI-race, active-worker, session-child Tool-observer, post-stop cleanup and successor-before-dispatch findings.
- Independent review substitutes were separate agents/worktrees. Their findings were repaired and affected tests rerun. The final authority, durable-journal, integration-glue and P3 probe reviews returned PASS with no remaining P0/P1/P2 finding.

## Remaining acceptance boundary

The next step is one cumulative automated no-evidence browser/service smoke on this reviewed descendant: P1 STT → committed Agent → real Tool → TTS, P2 refresh recovery, P3 UI lifecycle, and both production rejection probes. That run requires machine-private Speech/Agent model configuration and service/browser availability; it does not require signed evidence. Only after it passes may Main freeze a fresh immutable candidate and create new rehearsal roots and policy. The user then performs one final physical microphone, audible TTS, barge-in and UI-observation pass. Signed rehearsal/formal evidence and the 38-slot Gate remain separate and unstarted.
