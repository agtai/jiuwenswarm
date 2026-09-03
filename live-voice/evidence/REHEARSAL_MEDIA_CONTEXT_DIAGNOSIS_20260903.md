# Rehearsal media and Task-context diagnosis — 2026-09-03

Diagnosis only; **open defects, not a repair or acceptance pass**. No product
code, test, runtime configuration, Task or browser page content was changed.
The existing Chrome tab was claimed only to read console logs, without reload,
microphone activation or result-notification consumption.

Source: HEAD `87248911fde2220be6a97f72f8c0210ac67d5b67`, branch
`hx/0812_live_voice_w3`, ahead 7 / behind 0 at observation. The inherited dirty
candidate remains intact. The browser loaded `index-DYhlX49e.js`, matching the
previous frontend overlay with product-map SHA-256
`4bcbfe3fa8f85c894f7248d30ff3360e663431473a0f4f6c72846ffa8a21d125`.
No commit, push, build or full test run was performed.

Session: `web_1a06779d66f_3cc112920518`. Runtime evidence comes from the retained
`live-voice-functional-runtime-20260903-f3` directory: Agent/Gateway logs,
`runtime/agent/.logs/ws-dev.log`, chat history, the read-only unified input
journal, Task store and confirmation store. Condensed snapshots and the
browser voice console log are under
`C:\Users\admin\AppData\Local\Temp\live-voice-media-context-diagnosis-20260903`.
Times below are server local time, Europe/Paris (UTC+02). Browser console
timestamps reflect later collection; its embedded monotonic clock is aligned
approximately through matching first-frame scope/generation records.

## 1. Contact-airline answer: text arrives; audio/listening stall

- 15:54:23.009: the preceding refund answer attaches a downlink.
- 15:54:26.304–26.366: `p2.barge_in` succeeds. This recorded interruption is
  playback interruption, not `interrupt_generation`, despite the perceived
  generation phase.
- 15:54:34.945: the replacement question is committed. The semantic decision is
  dialogue; the round is accepted by 15:54:38.798.
- 15:54:35.821: generation-listening capture 17 has its first-frame ACK.
- 15:54:40.957: the exact answer text is projected to history, 6.012 seconds
  after committed text. This is not physical first-audio latency.
- No new successful audio downlink attach or proxy handshake follows for this
  answer before Exit. At 15:54:43.954 Gateway logs synthesis queue exhaustion.
  Its `first_audio_emitted=true` means an internal synthesis chunk was pulled;
  it does not prove delivery to the browser or speaker. The log's hashed
  binding alone does not definitively identify the response that exhausted.
- Browser console reports successor capture readiness failure,
  `AUDIO_CAPTURE_MEDIA_ROUTE_NOT_ATTACHED`, after 3126 ms. Its monotonic clock
  places this around 15:54:44.7 using capture 17's first-frame ACK as anchor.
- 15:55:00.743: the new close-origin marker identifies **user_exit**. Successful
  capture resumes after the later explicit start at 15:55:02.

The source explains how this becomes a persistent misleading state:
`presentProductNotification` sets text status to `presented` before audio.
`ProductP1VoiceRouteOwner.playAgentText` opens the downlink and waits for the
render promise without an initial attach/first-frame deadline. The media
adapter relies on socket open/error/close callbacks and has no connect timer.
P1 becomes `playing` only after a chunk is enqueued. With no chunk and no socket
terminal event, the pending presentation prevents fresh capture while
`presented` plus `recognized` projects to idle/ready. The separate three-second
successor-capture failure degrades interruption but does not settle this
foreground playback waiter.

Thus the missing bounded failure/settlement and incorrect ready projection are
confirmed code defects consistent with the logs. **The initial socket failure
cause is not proven**: the Web proxy has no connect/handshake failure record
in this interval, and no retained browser network trace identifies where the
new socket stalled. Do not label this an Agent failure, missing answer, or a
confirmed proxy/network root cause. The previous reconnect repair did not cover
this initial audio-connection wait.

## 2. Adjustment error: interrupted-context contract mismatch

- 15:55:19.429–19.603: generation interruption succeeds for the comparison turn.
- 15:55:24.587: the correction excluding rental cars is committed; its text is
  presented at 15:55:49.453, with downlink attach at 15:55:51.3 and audible output
  reported by the user.
- 15:56:03.306–03.519: button playback interruption succeeds.
- 15:56:15.855: the separate instruction to adjust the itinerary Task is
  submitted as `live-voice-unified-1788443775855-7`.
- 15:56:18.372: semantic output correctly selects `task.adjust` and exact Task
  `task-e84652a5fbdd401ba1b527a5541baaa5`.
- 15:56:18.478: a confirmation is issued for that adjustment. It is not consumed.
- 15:56:18.675–18.693: the journal and RPC record
  `TASK_RESULT_CONTEXT_INVALID`, message
  `formal dialogue context cannot reserve a TaskResult slot`.

The persisted failing commit has exactly three context references:
`cr_committed_user`, `cr_committed_user`, `cr_presented_assistant`.
The Conversation Runtime intentionally retains an interrupted unanswered user
question without inventing an assistant answer. However,
`ProductCompositionRegistry._reserve_task_result_context_slot` still rejects
every odd entry count and every non-pair arrangement. The unified route calls
this helper for ordinary Task control/confirmation receipts as well as results.
This explains why an adjustment produces a misleading Task-result error.
The earlier context-preservation repair was not propagated to this consumer.

The error occurs after issuing confirmation but before narrating it. There are
**zero `task.adjust` or cancellation commands** in this Session. The original
Task later completes at 15:56:30.709 without that adjustment being applied.
This is not a failed button interruption or corrupt Task result file.

## Other observed defects and limits

1. **Unrequested second Task.** At 15:55:12.814, the foreground question asking
   to compare flights, rail and rental cars is committed (ASR says “福车”).
   Semantic output incorrectly labels it `task.create` with
   `requested_work=local_artifacts`. The direct-delegation path verifies the
   binding and consumes consent from that semantic decision; it does not
   independently correct this interpretation. Task
   `task-740ed2c12bb14356a1e69020e7eacd39`, named
   “比较交通方案选择最稳妥”, is actually created at 15:55:15.727 and completes at
   16:00:33.380. Generation interruption correctly does not cancel a detached
   Task, so it cannot undo this earlier mistaken creation. This is the highest
   priority business side-effect defect. No client-description Task B was
   created in this Session.
2. **Recognition changes constraint meaning.** Recorded transcripts include
   “福车” and “不坐车”. The latter is passed literally as the proposed adjustment.
   It could exclude more than rental cars; confirming/executing it as the
   intended narrow correction is not established. The raw audio is not retained,
   so the acoustic cause cannot be diagnosed from transcript alone.
3. **Answer quality remains failed.** Analysis and correction replies contain
   1558 and 2098 characters. The correction uses an internal-analysis style
   unsuitable for the spoken answer. It says an F01 19:10 departure requires
   leaving at 18:40; the supplied 90-minute airport margin plus 90-minute trip
   instead requires 16:10. It gives T01 departure from home as 16:25, omitting
   the 30-minute station margin; 15:55 is required and is already before the
   material's 16:00 reference time. The earlier generic guidance has not fixed
   this grounded arithmetic/feasibility problem.
4. **Media diagnostics still need classification.** In 15:52–16:01, Gateway
   records six recognition-unavailable degradations, four recognition timeouts,
   one synthesis queue-exhaustion event and one synthesis route abort near Exit.
   These are not all independent user failures or all proven network failures;
   some occur near expected capture shutdown. Do not count Exit abort as an
   additional business defect without evidence.
5. **Engineering warnings.** Two background executions cannot open an
   observability root span because the installed package lacks `get_tracer`.
   Optional tool/rail/processor skips also appear. Both Tasks nevertheless
   complete, so those warnings are not the demonstrated cause of these two
   foreground failures. They remain compatibility/observability gaps.

The read-only Task command count for this Session is two creates and three
event ACKs; there is no adjustment/cancellation. No claim is made that completed
results, original constraints, offline notification recovery or the complete
Demo have passed. A completes just after Exit, so this run alone does not prove
that its absent live completion announcement is a new notification bug.

## Recommended repair boundaries

First prevent mistaken foreground-to-background creation and make the Task
receipt builder accept the runtime's valid interrupted-user context without
dropping it or fabricating assistant text. Bound audio connection/first-frame
waits, retain exact response identity and truthful preparing/recovery state,
and settle failed playback so the page cannot silently remain ready. Add the
minimal missing socket-stage correlation to isolate the remaining initial
connection cause. Then address ASR constraint ambiguity and grounded concise
answer quality. These are proposed repairs, not changes performed by this
diagnostic turn.
