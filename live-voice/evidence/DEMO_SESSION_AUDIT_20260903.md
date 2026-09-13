# Real Demo Session audit — 2026-09-03

## Scope and sources

Read-only diagnosis of Session `web_1a06907420d_0492a9d2556c` on deployed
`c4987f0286cd3a0cfdbc20cfd43536e60f759bd0`, formal Web Cascade at port 6175.
No model reruns, Task operations, file cleanup, Provider changes or service
restart. This is Tier-0 evidence/status synchronization, not a product repair
or independent code review. Times below are local UTC+02:00, converted from
SQLite UTC where needed.

Sources: `logs/swarm-20260903-224629.log`; scoped Tasks, Attempts, commands,
events, results and consumption in `formal_tasks.sqlite3`; frozen decisions and
pending contexts in its unified-input journal; this Session's `history.jsonl`;
actual files in the unchanged verification project. Private raw inputs, auth
material and full logs are not copied into this report.

## Authoritative outcome

| Task | Exact ID | Created | Running | Terminal |
|---|---|---|---|---|
| A: 航班取消行程调整 | `task-846033ff12e8454bbaf37672aa05e50f` | 22:49:01.956 | 22:49:02.683 | completed 22:52:19.330 |
| B: 客户说明草稿 | `task-8069d23b0d01434881a152dab068f4a4` | 22:49:28.789 | 22:53:02.791 | completed 22:55:17.096 |
| A2 | none | not created | — | — |

Both existing Tasks completed, but the Demo **did not pass**: B should have been
cancelled and A2 should have been created. Both Tasks have `cancel_requested=0`.
This Session has no Core cancel/adjust/successor command or executor adjustment
record. A ran for approximately 3m17s; B waited 3m34s then ran for 2m14s. B's
admission reason is `EXECUTOR_PROJECT_BUSY`, with six admission attempts.

## Control defects

1. **A included B's work before B was delegated.** The first Agent answer offered
   a customer explanation draft. A's following create specification incorporated
   that assistant suggestion along with the user's travel objective. This proves
   overlapping Task scope, not the model's internal reason for later misrouting.
2. **A's modification stayed pending.** At 22:50:34.716 the transcript said “能尽晚
   走就尽量尽晚走”, diverging from the intended “今晚”. The semantic adjustment
   chose latest departure and excluded self-drive. Its confirmation, issued at
   22:50:38.393, was never consumed. The assistant still said “已按你的要求调整”.
   No Core/executor mutation exists; the result retains a self-drive comparison.
3. **B's status conversation queried A.** At 22:51:15.362, the manager-draft
   question routed to dialogue. At 22:51:28.994, “为什么还没开始” selected A's
   `task.status`. Log line 7459 reports A running while B was queued. The answer
   incorrectly used A's progress for the question about B.
4. **Ambiguous cancellation guessed B.** At 22:51:46.660, “有一件不用做了” proposed
   B cancellation instead of semantic clarification. An unconsumed cancellation
   confirmation was issued at 22:51:49.219. The assistant asked which task, but
   that question did not express the exact server-side pending state.
5. **Explicit B cancellation became A adjustment.** At 22:52:04.124, “给林经理的
   说明不用写了…行程继续帮我查” proposed `task.adjust` on A with null continuation
   fields, despite visible B and its pending cancellation. The adjustment review
   also copied the earlier status question into its specification. Another
   unconsumed A confirmation was issued at 22:52:09.540. At 22:52:12.051 the
   assistant claimed B was cancelled. B actually started about 51 seconds later.
   This is wrong operation/target/continuation plus false narration; no dispatched
   cancellation failed inside the executor. Renaming B is not a general fix.
6. **A2 selected the wrong operation.** At 22:56:18.302, “再做一版…原版保留” proposed
   `task.adjust` on completed A. Frozen authority facts explicitly listed
   `task.create_successor` and excluded `task.adjust`. Existing policy rejects
   non-successor terminal mutation as `TERMINAL_TASK_IMMUTABLE`, while successor
   has a separate allowed branch. Narration incorrectly added that a completed
   Task cannot produce a new version and called the request accepted. No actual
   successor was attempted; its executor path is therefore untested by this run.

The Registry builds explicit `confirmation_required`, status, reason and
operation facts. The formal Agent answer contract already requires truthful
pending/applied narration, but the answers violated it. The three relevant
durable confirmation records all have `consumed_by=None`. The product must
present a required confirmation truthfully or implement an accepted authorization
policy through normal authority; the user should not have to guess hidden state.

## Notifications, files and follow-up defects

- Generic server narration at `product_composition_registry.py:2623–2654` omits
  the available Task name. Use authoritative name plus state, e.g. “客户说明草稿
  开始执行了” and “航班取消行程调整已完成”; align frontend fallback. Names remain
  data and same-name disambiguation must retain identity. No business matcher,
  fixed Demo alias or extra model call is needed.
- A generated `给林经理的说明草稿.md`, sealed hash
  `f63a09f06987f88b2bd3715a295a5a367000833fbf3f136be0b125436aa7eafe`.
  B wrote the same path with hash
  `6136abb72eecce395474a4dec83eb55d69eff9e35162b907d3792d3f6e8ebca7`, matching the
  current project file. That shared path now contains B's version. A's itinerary
  hash is `e7f2803e462d0500025fa67a795fdb4e09c2eca29fec94b397a794fa6857aae2`.
- Refund follow-ups claimed the already-read order terms still needed checking.
  The departure-time answer claimed travel duration was absent even though the
  actual itinerary contains 30 minutes. These are material/result grounding
  failures; this audit does not expand into the deferred arithmetic repair.
- During 22:48–22:57, logs contain ten synthesis-capacity fallbacks, twenty-two
  recognition-protocol fallbacks and nineteen missing embedding-config warnings.
  The first synthesis-capacity failure is 22:53:04.221, line 11378. Optional
  workspace-template reads also fail repeatedly. These warrant separate
  lifecycle/latency diagnosis; counts alone prove neither lost audio nor a leak
  nor causation for the semantic failures.

## Demo coverage

| Step | Evidence and limitation |
|---|---|
| Read, analyze without creation | Input Markdown read successfully at 22:48:22; first turn dialogue, no Task |
| Create A then distinct B | Actual Tasks/files; A scope wrongly included B's draft |
| Generation-phase correction | Two committed inputs and corrected answer; exact before-audio timing and no late playback unproved |
| Modify running A | Timing valid; tonight/latest ASR discrepancy; pending modification falsely narrated as applied |
| Separate task queries | A query worked; B query/follow-up lost the target |
| Cancel unfinished B | Timing valid; no cancellation execution; false success response |
| Refund and audible interruption | Grounding failed; barge-in requests exist, physical stopping/listening quality unproved |
| Leave while A unfinished | Timing failed: A completed 22:52:19; departure utterance 22:53:00; Exit 22:53:12 |
| Return, completion and result | Same-session A result read; A terminal ACK 22:54:09, B terminal ACK 22:55:48; A did not complete offline |
| Follow-up and refresh dedup | Some summary facts retained; departure grounding failed; deliberate post-ACK refresh dedup unproved |
| A2 and preservation | A was complete, but request became adjust; no A2 or two-version comparison |

Overall remains **PARTIAL / failed full Demo acceptance**. No physical playback,
Native, regression or independent-review credit is added. Prioritize receipt
truth and exact multi-Task continuation, successor selection, named notifications
and result-grounded follow-ups. This audit deploys none of those repairs.
