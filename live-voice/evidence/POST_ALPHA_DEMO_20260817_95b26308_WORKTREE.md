# Post-Alpha hands-free Live Voice Demo record: 2026-08-17

## Conclusion

- Execution status: `COMPLETED — DEFECTS RECORDED` by user confirmation.
- Acceptance result: **not PASS** for the complete Post-Alpha D119-derived
  Journey. The run completed as a product exercise and defect-discovery run,
  but authoritative Task/Executor/result/notification requirements failed.
- Application source: deployed uncommitted working tree on baseline
  `95b26308717b896d820f011defa691243cad58f8`, branch
  `hx/0812_live_voice_w3`. Because the tested source was dirty, this record
  grants no immutable-candidate, release or replacement credit.
- Milestone relation: D-081 keeps `PASS — INTEGRATED WEB ALPHA` bound only to
  accepted source `d33b520e0d21ae0829d30814d77a01cc18256f09`. This
  Post-Alpha result does not reopen S7/S8 and gives no S9 credit.
- Privacy: Provider credentials, bearer values, browser profile/device details
  and raw frames remain outside Git. The active runtime log is referenced by
  basename only and contains no credential copied into this record.

## Environment and scope

| Item | Sanitized fact |
|---|---|
| runtime | Windows localhost; Web `6173`, Gateway `18092`, Agent `19000`, Media `19001` |
| Web bundle | `index-Ci1LeMJT.js` |
| model label | `deepseek-v4-flash` through the configured private Provider |
| Speech path | real microphone/STT and TTS hands-free loop |
| application baseline | `95b26308717b896d820f011defa691243cad58f8` plus uncommitted candidate changes |
| project | clean no-remote Git fixture `order-test` |
| project HEAD | `6fcfa18e91cbab817e1865283e4a7d25da3e34fe` |
| runtime log | `logs/swarm-20260817-180239.log` |

The exercised Sessions covered ordinary order inspection/dialogue,
`background.create`, running adjustment, adjustment-status and result queries,
foreground question/TTS behavior and playout interruption. This record does
not claim that every step met its oracle merely because the spoken Journey was
completed.

## Authoritative observations

1. A prior Direct Executor attempt
   `attempt-26f170d35739445a9a4e3699de50c26f` entered `running`. Its real Agent
   wrote the bounded `itinerary.md` in the isolated checkout and reported
   internal completion, but Executor orchestration did not persist an expected
   tree, result/artifact facts or a terminal event. It continued to renew its
   owner/lease.
2. Session `web_1a010900b4a_2854bf302720` created
   `task-4cf2948ba1834472b304551f5481a5a9`. Task Core admitted the Task and an
   adjustment command, but its Attempt remained unbound because dispatch saw
   the same project as busy. At the 18:48 local snapshot, dispatch had retried
   35 deliveries with `selected project already has an active formal mutation
   attempt`; the adjustment outbox remained pending and no TaskResult existed.
3. No `task.terminal` existed for that Task, so no truthful completion
   notification could be constructed. The visible absence of a completion
   announcement was a consequence of the missing terminal/result, not evidence
   that a constructed terminal notification was dropped.
4. “可以了,刚才的修改加进去了吗?” did not full-match the bounded
   adjustment-status grammar and fell through to `dialogue`. The foreground
   Agent reread the seven order files and produced a plausible itinerary while
   incorrectly claiming that the adjustment was already applied and the answer
   was final. This was not a TaskResult-backed response.
5. A separate completed-Task query exposed the eight-entry context boundary:
   a legal available TaskResult was converted to “当前任务结果不可用” when the
   dialogue snapshot already contained eight entries.
6. The natural adjustment sentence without “把/将” remained capable of
   resolving as `background.query`, producing no `task.adjust` side effect.
7. Repeated visible recovery states coincided with P2/barge and Speech transport
   cleanup errors. The retained diagnostics are insufficient to close one
   exact recovery root cause, so this remains a focused follow-up rather than a
   claimed repair.

## Required repairs

| Boundary | Required outcome |
|---|---|
| Executor terminalization | Agent return always reaches bounded validation/application and one terminal outcome, or a bounded truthful failure; no indefinite owner/lease renewal |
| admission truth | `accepted`/queued is distinct from Attempt `running`; “已开始处理” requires authoritative running evidence |
| semantic routing | bounded no-“把/将” update and conversational-prefix status forms route correctly; ambiguity/negation retain zero mutation |
| Task truth isolation | DIALOGUE cannot claim adjustment application, Task completion or final Task result without Task Core facts |
| result context | a legal TaskResult receives bounded context capacity even when four dialogue pairs are selected |
| recovery diagnostics | stable activation/response/generation/ACK/TTS reasons distinguish retryable recovery from terminal failure |

The duplicate empty-key i18n warning is retained as low-priority engineering
hygiene. It becomes a product defect only if a visible translation is shown to
be lost or overwritten; it is not a root cause of the failures above.

## Verification disposition and limits

- The previously recorded automated checks remain historical credit for their
  exact source. No new automated suite or independent review was run merely to
  document this completed physical exercise.
- The dirty deployed source prevents an immutable PASS claim. The observed
  non-terminal tasks and undelivered outbox also prevent Task/result/terminal
  acceptance regardless of the plausibility of the foreground itinerary text.
- P2 notification sequence numbers include foreground stream notifications and
  keepalives. A high sequence alone is not duplicate terminal-delivery evidence.
- This run did not authorize manual database deletion, project-worktree
  deletion, remote updates, public deployment, credential movement or S9 work.
- A future PASS requires the repaired clean immutable candidate, applicable
  automated/Tier-3 review credit and one complete successful real Journey with
  authoritative adjustment-before-terminal, result/artifact SHA, exactly-once
  terminal presentation/ACK and settled Task/attempt/outbox/owner/lease facts.

Current mutable state and repair order remain in [STATUS.md](../STATUS.md).
