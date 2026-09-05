# Live Voice product-readiness human showcase

> Current candidate/blockers: [STATUS](../STATUS.md)
> Pass/fail: [acceptance contract](../validation/PRODUCT_READINESS_ACCEPTANCE.md)
> Startup/diagnosis: [runbook §7.5](../runbooks/E2E_RUNBOOK.md#75-当前受控-live-voice-启动与预演)
> Verification/review: root [TESTING](../../TESTING.md)

For a rehearsal, run the requested scenarios and record their actual results.
For candidate acceptance, first complete applicable automation/cumulative review
on one clean source, then run this complete journey once, including the accepted
current extension in §4 and applicable platform/failure checks. A narrow rehearsal
does not require the whole candidate suite and cannot grant candidate credit.
Historical PASS remains bound to its source and scope.

## 1. Preflight and candidate identity

Record exact source/comparison base and Git status; browser/OS/origin, microphone/
output and network labels; real Speech/Media/Agent/Tool/Task/Executor routes,
fallbacks, isolated data/project, persistent Session and enabled flags. Retain
applicable automated/review results and accepted deviations without secrets.

For generation-time interruption, verify the actual deployed assets and
`formal-web-validation` route, which defaults this feature on. Explicit
`-DisableGenerationInterruption` turns it off; `hands-free-demo` remains off.
Playback-time interruption is a separate sample. A local
headset pause profile is also separate; use only the declared device/profile.

If a required route/environment differs from the reviewed candidate, record the
affected acceptance as BLOCKED and prepare a new identified run. Rehearsal may
still gather scoped defect evidence, but cannot silently inherit candidate PASS.
Do not change source/routes mid-journey or manufacture Task timing with fake waits.

## 2. Platform lifecycle

For the applicable candidate scope, verify microphone grant/denial/revocation,
device loss/change/recovery, user activation/autoplay, hidden/background/resume
and refresh/reconnect. Text Chat remains usable; there must be no duplicate
dispatch, retained unauthorized microphone, stale capture/playout revival or
foreign target. Non-localhost deployment also requires the applicable
HTTPS/WSS/proxy/CSP/CORS checks; record localhost as a bounded exception.

## 3. Real voice conversation

Use the physical microphone, including a relevant technical/critical token.
Verify committed final text reaches the real JiuwenSwarm Agent and safe real
tools, and hear the response through the declared TTS route. Partial/uncommitted
input must cause zero Agent/Tool/Task mutation. Test exact-response playout stop
without stale chunks or cancellation of another Task.

Explicit current local create/adjust speech supplies consent under D-109/D-112.
Verify the server's exact binding and one-time durable confirmation internally;
do not demand a second spoken yes solely to satisfy a test script. Ambiguous,
stale, unsupported or otherwise unauthorized actions retain their real
clarification/rejection requirements; other mutation policies are unchanged.

Record measured latency from the actual trace/corpus. One presentation cannot
supply a reliable p50/p95 or prove physical stability.

## 4. Current A/B/A2 journey

The current extension exercises two independent real background Tasks and a
preserved successor revision. These scenario requirements are owned here;
STATUS records whether they have passed. The travel utterances below are the
user's rehearsal fixture, not product routing rules. Use the registered project's
actual input file and its fixed scenario date/time, not a guessed machine date.

| Step | Voice/action | Required observation |
|---|---|---|
| 1. Read then delegate A | “我刚收到通知，今晚北京去上海的航班取消了。我明天上午十点有个客户会议，你先看一下项目里的订单和会议资料，帮我判断怎么调整最稳妥。” After the source-backed analysis: “那行程方案你在后台帮我整理吧。准时到达最重要，新增交通和接驳支出尽量不超过一千五，原机票退款单独列，酒店先不要动。” | Analysis reads real project inputs; explicit delegation creates one Task A. Record its name/ID and exact constraints; accepted/queued is not completed. |
| 2. Delegate B | “另外帮我准备一段给客户的说明，万一明早赶不到可以用。放到后台做，只生成草稿，不发送。” | B has a distinct ID. Queueing is valid; simultaneous execution is not required. No message is sent. |
| 3. Interrupt generation | Ask “坐飞机、高铁和租车自驾，你觉得哪个更省心？” After submission while generating, before any speech: “等等，自驾就不聊了，先说飞机和高铁吧。” | Enabled generation-time capture accepts the correction, fences the old response, speaks the replacement and resumes listening. No late old audio or A/B mutation. If audio already began, record a playback sample instead and repeat this scenario separately. |
| 4. Adjust running A | “行程方案里也别安排自驾了，尽量今天晚上就出发。” Then “现在行程已经按这个要求调整了吗？” | A is still legally adjustable. Distinguish received/pending/applied/rejected with authoritative events; eventual A document reflects an applied adjustment. A dialogue receipt alone cannot prove application. |
| 5. Query separately | “行程方案做得怎么样了？” Then “给客户的那份说明呢，写得怎么样了？” If B truly has not started: “那份说明为什么还没开始？” | Each answer matches that Task's detail. Unknown queue reasons remain unknown; no invented progress or cross-target reply. |
| 6. Cancel only B | While B is unfinished, optionally say without a unique target: “刚才让你做的两件事，有一件不用做了，帮我取消掉。” After clarification: “给客户的说明不用写了，我直接跟他联系。行程继续帮我查。” | Ambiguity produces no mutation. Explicit B cancellation reaches a real cancelled terminal state; A is unchanged and remains active. |
| 7. Foreground work beside A | While A runs: “帮我看看订单，原来的机票现在能退吗，还是只能改签？” | The reply uses actual order terms; it neither creates a duplicate Task nor applies for refund/change. |
| 8. Interrupt speech | During audible refund explanation: “等等，我就想确认一下：现在不打电话，会不会影响退款？” | Old sound stops; new question receives a grounded spoken answer; listening resumes. Use actual voice overlap, not a button or waiting until the answer ends. A is unaffected. |
| 9. Leave while A runs | “我先去收拾东西，你继续帮我查，我回来再看。” Click Exit and leave/close the page. | Verify A was unfinished before leaving. Keep dedicated services running. Confirm completion during disconnect only via read-only backend state/logs; do not open frontend results or consume notifications early. |
| 10. Return | Return to the same user/project/Session, enable Cascade and wait for the completion notification to actually present. Then “我回来了，给我看看你整理好的行程。” | It is the original A, no duplicate creation. Open its real result file. Distinguish unread, presented and acknowledged notification states. |
| 11. Use and retain result | Ask final route/new tickets + taxi cost, expected old-ticket refund, hotel treatment and latest hotel departure. After notification acknowledgement, refresh once and re-enable voice if needed. | Verify actual document arithmetic/times, not only chat. The same result persists; the same acknowledged notice does not replay. |
| 12. Preserve A, create A2 | After A completed: “我还得提前布置一下材料，会前再多给我留二十分钟。其他安排不变，你在后台帮我另做一版，原来那版也留着，别覆盖，我想对照着看。” After A2 completes ask what changed, new hotel departure and to show the original too. | Independent successor A2 is linked to A's result. Open both documents; recalculate the affected schedule, retain other constraints, and prove A was not overwritten. |

Do not force a continuous take when the state window is missed: adjustment needs
a legally adjustable A, cancellation an unfinished B, leaving an unfinished A,
and successor creation a completed A. Split the rehearsal and report the missed
window. No artificial sleep, task-name rule or manual state patch may create a pass.

For a wider declared acceptance boundary, also exercise bounded negative input,
another domain and both declared voice routes as required by STATUS. Passing the
travel/Cascade sample alone does not establish that wider coverage.

## 5. Result and notification checks

For the user's fixed flight-cancellation input, independently derive the oracle
from that actual file: expected refund 1180, not received cash; prepaid hotel 620
is separate from the new transport budget. For a plan that arrives in Shanghai
that night and stays at that hotel, the original latest departure is 09:00
(10:00 meeting minus 30-minute preparation minus 30-minute transfer); A2 with
20 more preparation minutes is 08:40. These values do not apply to arbitrary
projects or substitute for inspecting both real result files.

Record exact command/Task/Attempt/result identities and adjustment event order.
ACK/queued/timeout/unknown cannot masquerade as applied, completed or presented.
Missing/truncated result context must be explicit. Duplicate/stale/wrong-generation
notifications, forbidden cross-scope mutation, silent rerun and old-audio revival
must be zero.

## 6. Degradation, privacy and recovery

For the applicable candidate scope, exercise a selected safe Speech/Media/Provider
failure and an Executor failure/recovery case. Expect bounded visible failure
with usable fallback and exact failed/interrupted/pending/unknown truth, no
duplicate effects. Inspect storage/URLs/logs/Context/TaskEvent/WorkProgress for
credentials, unauthorized content or default raw-audio persistence. These
controlled cases may run separately from the business rehearsal.

## 7. Closeout and decision

After the offline completion/return scenarios finish, Exit and verify microphone,
capture/playout, timers and reconnect loops stop. Settle or truthfully record all
Task/Attempt/outbox/lease state. Preserve result files and any user-owned active
work. Stop only the dedicated services within this run's authorized cleanup scope
and verify the source did not change.

Record each required scenario PASS/FAIL/BLOCKED/NOT APPLICABLE with reasons,
exact source/environment and evidence. A complete candidate uses one outcome
from the acceptance contract; a scoped rehearsal reports its own limited result.
Neither grants feature completeness, production/platform/SLO claims or
`develop` integration.
