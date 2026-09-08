# September 8 human Live Voice acceptance diagnosis

## Scope and evidence

This is a frozen diagnosis of Session `web_1a0805b849c_94530f3599ab`, requested
after the user paused the broad repair task. It records measurements and causes;
it does not restart implementation or authorize a new deployment. Owned surfaces
are this report, the current STATUS interpretation and the acceptance evidence
route. This is a Tier 0 documentation change under root TESTING. No product code,
configuration, Task state or deployed process was changed by this investigation.

- Actual deployment: clean `0c89d8b940`; analysis checkout started at
  `489c17334fb86e5b34d7789461c0549936938b01` (later changes were documentation).
- Provider confirmation: `gpt-realtime-2.1`, speed `1.25`, minimal reasoning,
  server VAD `450 ms`. Selected Jiuwen Agent: `deepseek-v4-flash#0`.
  The browser's `native_model_confirmed` event refers to that selected Agent;
  it must not be mistaken for Realtime Provider confirmation.
- User acceptance: “全程没有再听到音频撕裂，算通过。” **Audible tearing PASS
  for this actual session.** This does not pass missed speech, dropped sessions,
  semantic correctness, all devices or the original complete media matrix.
- Browser export: `live-voice-diagnostics-2026-09-08T09-47-41-157Z.json`,
  exported at `2026-09-08T09:47:41.142Z`; SHA-256
  `29666cc673feda7cc34d84b5e33c86972c52a2e7d68dced6a1bb9b515384bee3`.
  It contains 4,120 records, 2,929 routine memory overwrites, 28 overwritten pages,
  zero milestone overwrites and zero storage failures. It is not a complete
  per-frame trace. The original file remains in the user's Downloads directory.
- Server log: `logs/swarm-20260908-105503.log`. The retained exact-session
  snapshot contains 5,711 diagnostic rows through original line 51809, plus
  selected ordinary logs, history and Work output. Server diagnostics report
  zero dropped records in this snapshot.
- Private/raw evidence and reproducible stdlib scripts remain outside Git under
  `logs/acceptance-web_1a0805b849c_94530f3599ab/`: `analyze.py`, `analysis.json`,
  `turn-timings.csv`, `analyze_browser.py`, `browser-analysis.json` and
  `browser-turn-timings.csv`. The tracked report contains sanitized findings.

All wall-clock labels below are **UTC**; add two hours for Paris local time.
Durations use one monotonic clock per measurement. Browser EOTs join the exact
Session/interaction and unique Provider input-end offset; audio joins exact
response identity/generation. No browser/server or Gateway/AgentServer monotonic
timestamps are subtracted from each other.

## Every input and its measured first response

**Browser time** means browser receives Provider end-of-turn → AudioContext is
running and its clock reaches the first scheduled audio start. It includes the
remaining service/browser wait, but excludes the preceding acoustic tail,
upstream/VAD detection and device output latency. The passive start observer
polls every 16 ms; it is not a microphone recording of speaker output.

**Server time** means Gateway observes Provider `speech_stopped` → the Gateway
sends the exact response's first PCM frame. A frame sent is not proof of playback.
The two columns have different start/end boundaries and are not interchangeable.

| # | Gateway EOT UTC | Committed input / operation | Server time | Browser time | Actual outcome |
|---|---|---|---:|---:|---|
| 1 | 09:31:25.135 | 一句话介绍深圳 | 1.151 s | 1.186 s | Audio started |
| 2 | 09:31:35.848 | 深圳靠海吗 | 1.071 s | 1.134 s | Audio started |
| 3 | 09:31:45.855 | 介绍看海地点 | 1.077 s | 1.128 s | Audio started |
| 4 | 09:32:04.932 | 下午大鹏，上午做什么 | 1.022 s | 1.075 s | Audio started |
| 5 | 09:32:27.614 | 当前项目工作区是否干净 → `work.start` | 3.861 s | 3.928 s | Spoken acknowledgment; delegated instruction diverged from transcript |
| 6 | 09:32:40.172 | 等一下，回答我只收到 | 1.105 s | 1.213 s | Audio started; reply expanded into task-query commentary instead of the requested short format |
| 7 | 09:32:57.653 | 确认上午人才公园、下午大鹏 | 1.161 s | 1.212 s | Audio started; later interrupted |
| 8 | 09:33:05.938 | Transcript fragment `Updates` | — | — | Response retired; this transcription is not proof of what was physically spoken |
| 9 | 09:33:08.404 | No committed transcript | — | — | Another response retired around the speech split |
| 10 | 09:33:19.216 | 后台做人才公园/大鹏行程并保存 → `task.create`, then `context.get` | No confirmation PCM | No start | Real Task accepted; media session failed 7.117 s after EOT |
| 11 | 09:33:46.358 | 当前后台任务状态如何 → `task.status` | 14.517 s | **15.547 s** | Audio started, then session/receipt failed |
| 12 | 09:34:14.821 | 中午增加一份早茶 → `task.adjust` | 16.945 s | **No start recorded** | Adjustment rejected; media session failed 19.155 s after EOT |
| 13 | 09:34:49.729 | 三句话介绍深圳 | 1.442 s | 1.555 s | Audio started |
| 14 | 09:35:17.541 | 请只回复一收到 | 1.211 s | 1.255 s | Audio started; committed reply “收到。” |

Eight responses without tools have browser EOT-to-start **P50 1.199 s, mean
1.220 s, range 1.075–1.555 s**. Nearest-rank sample P95 is 1.555 s; eight
observations do not establish a stable population P95. Ten responses total have
browser start evidence; eleven have server first-frame evidence. In particular,
the adjustment response must not be reported as successfully spoken.

Two actual interruptions are also visible. Response generations 6 and 8 stopped
246 and 121 scheduled sources respectively, with zero source-stop failures.
The local stop calls took 0.5 ms and 0.2 ms; Native stop acknowledgments followed.
These are local control measurements, not acoustic interruption latency.

## Where the background-operation time went

The following are consecutive **Gateway** segments. “Tool round trip” starts
when arguments finish and ends when the tool receipt is sent back to Realtime;
it includes server work and dispatch. Nested AgentServer spans below are
inclusive and must not be added again to these totals.

| Operation | Argument generation | Arguments done → tool receipt | Receipt → next response request | Request → raw audio | Raw audio → first frame sent |
|---|---:|---:|---:|---:|---:|
| `work.start` | 0.575 s | 1.397 s | 0.004 s | 0.951 s | 0.348 s |
| `task.create` | 1.171 s | 0.890 s | 0.003 s | No audio; model called `context.get` | — |
| `context.get` after create | 1.172 s | No receipt to the retired activation | — | — | — |
| `task.status` | 0.434 s | **7.651 s** | **1.546 s** | 2.057 s | **2.150 s** |
| `task.adjust` | 0.799 s | **7.099 s** | **4.853 s** | 1.546 s | **1.252 s** |

Time before the first argument is not included in this segment table. The full
EOT-to-response totals are in the preceding table and retained analysis.

Creation itself was comparatively quick in this session: `native.business`
took 0.868 s, including `native.task_intent` 0.299 s. The accepted receipt reached
Realtime **2.811 s after Gateway EOT**. Realtime then requested another context
read instead of speaking the receipt. That read took 2.139 s in AgentServer and
settled after the activation had already closed. Thus the creation acknowledgment
failed even though a Task really existed.

The status query spent **6.846 s inside AgentServer's business operation**.
Its nested spans include two context reads of 1.930 s and 1.031 s, plus Task
intent handling of 2.832 s (including a 2.070 s formal invocation). Repeated
fresh authority checks contribute inside those spans. The browser then spent
**1.106 s from accepting PCM frame 0 to AudioContext start** for this response.
That last interval includes buffering/scheduling; this export does not fully
separate those causes.

Adjustment spent **7.042 s inside the business operation**: context reads of
0.392 s and 1.837 s, and Task intent handling of 2.670 s. After the tool receipt,
another **4.853 s** elapsed before the next Realtime response request was sent.
This is locally observed continuation delay, not all Provider inference time.

The actual Task `task-5976999fad584e22bda8d672c38bbb8f` was accepted at
09:33:21.509731 and reached `completed` at 09:34:30.966634: **69.457 s** on the
Task store's clock. It generated `深圳人才公园大鹏半岛一日行程.md` (1,503 characters),
with SHA-256 `7e708fa9574f5234b9da0ad127a158fdcb06ee6e8b9ddedf509079902840b842`.
This is real Agent/Task/file execution, distinct from spoken acceptance latency.

The early-tea adjustment was requested at 09:34:19.614732 and rejected at
09:34:20.958606 with **`ADJUSTMENT_CHECKPOINT_CLOSED`**. The executor had passed
its editable checkpoint while Task finalization was still running. The saved
file contains no early-tea addition. A request receipt or a still-running Task
does not prove that this edit was applied.

## Errors and causes

### Three observation timeouts closed the voice connection

The original log records `NATIVE_RUNTIME_TIMEOUT` at 09:33:26.333, 09:34:03.708
and 09:34:33.978 (lines 42708, 44451, 45821). All three stacks originate in the
background business-observation loop, not TTS generation:

`_run_native_business_poll` → `_read_native_business_context` →
`observe_business_context` → `_request`.

The client applies a **5 s deadline** to the observation RPC. This read performs
observation waiting, context reconstruction, Task/history reads and fresh
authority checks. The Gateway loop does not handle this transient timeout
locally; `_consume_native_task` treats the observer failure as a Native-session
failure and schedules media closure. Relevant source:

- `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py:2102` and `:3730`.
- `jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py:867` and `:1213`.
- `jiuwenswarm/server/live_voice/native_business_router.py:214` and its context reader.

Browser failures match those closures: `MEDIA_CONSUMER_FAILED`,
`ADAPTER_UPLINK_PEER_DETACH_MEDIA_CONSUMER_FAILED`, and on the query response
`MEDIA_PLAYOUT_RECEIPT_UNTRUSTED`. Two later `MEDIA_NATIVE_INPUT_FENCE_REJECTED`
events report `session_closed`; those are downstream effects. Normal
`MEDIA_LOCAL_CLOSE` after completed playback is not counted as an independent
fault merely because it is a terminal event.

**Confirmed cause:** an expensive/late background observation can close an
otherwise usable voice session. The deepest split between filesystem/Git,
thread scheduling, store access and Registry contention is not fully measured
here. The earlier isolated Windows lock reproduction is not proof that the same
lock caused these three live failures.

### The workspace question launched unrelated Work

For the committed transcript “当前项目工作区是否干净？”, the actual persisted Work
instruction requested research into Shenzhen Bay Park and Talent Park cleanliness,
public facilities and recent sources. It did not request repository worktree status.

This is a demonstrated mismatch between retained transcription and delegated
instruction; without the original recording it does not establish the exact
physical utterance. Work `native-work-da06a631071ea0f2d7a59905fe1916ef` ran an
Agent round for **105.178 s**, with 23 model-stream settlements totaling 63.569 s
and 38 tool-call progress events. It also overlapped the itinerary Task. The
result's tourism claims have not been independently verified and receive no
correctness credit from this diagnosis.

The Work-completion response was prepared while the foreground answer was
playing, promoted at 09:35:10.356 and discarded at 09:35:10.886 with
`NATIVE_PREPARED_ADMISSION_RETIRED`. This is a separate missed Work continuation;
it is not the Task terminal TTS failure described below.

Repeated missing optional workspace-context Markdown files, unknown optional
search/skill tools and optional Rails warnings also appear. They explain noisy
logs and configuration gaps, but are not the originating stack for the three
media closures and do not by themselves explain all 105 seconds of Work.

## Why the completed Task was never spoken

The terminal event existed, and speech synthesis did begin. The observed chain:

| UTC | Evidence |
|---|---|
| 09:34:30.967 | Task store records completion |
| 09:35:05.689 | Foreground response presentation acknowledged; terminal notification can proceed |
| 09:35:05.802–06.482 | Server prepares AUDIO notification, response generation 16; 680 ms |
| 09:35:06.515 | Browser starts `task_preparation_prepare` |
| 09:35:07.854 | Capture reports one energy frame, RMS peak 0.01554; Provider speech-start remains false |
| 09:35:08.849–08.895 | TTS HTTP 200, first Provider chunk, then first prepared frame |
| 09:35:08.907 | Browser preparation RPC returns after **2.392 s** |
| 09:35:08.908 | Browser immediately calls `presentation.failed`; no claim RPC or playback start for this notification |
| 09:35:08.990–09.797 | Server creates TEXT fallback, response generation 17 |
| 09:35:11.836 | Task store records terminal event consumed through sequence 7 with presentation class **text** |

The source event is `event-285df56b3fac41e4ab2919c2bad5b086`. History contains
the text that the itinerary completed and its result was generated. There is
no audio acknowledgment for the failed generation-16 announcement.

**Directly established:** playback was abandoned after preparation, before
claim/start; the canonical fallback converted it to text; text acknowledgment
consumed the terminal event. Returning to idle could not discover an unconsumed
audio notification to replay. The TTS HTTP request succeeded; the later synthesis
cancellation is downstream of abandoning the notification, not proof of an
initial Provider outage.

**Strongly supported trigger, not a directly exported exception:**
`productP1VoiceRoute.ts:65` sets an energy floor of 0.015. At `:3544–3549`, one
idle capture frame above it sets a sticky notification `speechObserved` flag,
without requiring Provider speech-start. The browser goes from zero energy
frames at 09:35:06.853 to one at 09:35:07.854, inside the pending preparation;
no Provider speech-start is recorded until 09:35:15.636. Once preparation returns,
the stale/speech guard at `:1664–1667` prevents claim and the catch at `:1932–1935`
maps loss of notification ownership to `FORMAL_PLAYOUT_BARGED`.

`LiveVoiceIntegratedRoutePanel.tsx:3971–3973` handles that reason as a Task
presentation failure, without emitting the recovery diagnostic used by its
other error branches. The retained-resume branches at `:7543` and `:7656` have
the same treatment. This explains both the observed immediate failure and the
missing raw reason in the export. The single-frame energy observation does not
prove the user spoke; it may represent brief sound or noise. The exact original
exception and lease transition were not recorded, so they cannot be claimed as
directly observed values.

The product consequence is definite: **an unplayed announcement that yields
before start can be permanently consumed as text**. A future repair needs to
distinguish temporary speaker priority from terminal audio failure, retain the
unplayed event for an idle retry, and still prevent duplicate audio/history/ACK
effects. Merely changing the idle timer will not restore an already consumed
event. These are proposed changes, not implemented repairs in this report.

## Optimization effect and bounded next discussion

1. **Tearing:** the user's real-session acceptance is PASS. Do not invalidate
   that result because separate latency/lifecycle failures remain.
2. **Ordinary response:** current browser EOT-to-start P50 is 1.199 s. The old
   approximately 3.3 s was diagnostic-confirmed, not a subjective hearing guess.
   Its reported 3.348 s median / 3.3896 s mean mixed eight ordinary responses
   and two tool preambles and used a broader end-to-end boundary. The prior
   current-build CLI P50 1.915 s was acoustic-input-end to received PCM. None
   of these three metrics is an exact like-for-like substitute for the others.
   This session still lacks an aligned acoustic-end/speaker-output recording,
   so it does not prove the original physical P50/P95 target.
3. **Comparable transport stage:** ordinary raw-PCM-to-first-send mean is
   0.387 s versus the old reported 1.0575 s, about 63% lower as an observed trend.
   The batches differ in input mix/configuration/load, so this is not a controlled
   causal A/B claim. Current ordinary sample P95 is 0.539 s; across all eleven
   sent responses it is 2.150 s. The **≤200 ms P95 target fails** in this session.
4. **Task waiting:** the prior “about 9 seconds” does not describe this session.
   Create has no spoken confirmation, query takes 15.547 s to browser start,
   adjustment never starts, and completion is text-only. This scope fails.

There is concrete optimization room in repeated full context/authority reads,
post-tool continuation scheduling and audio admission under business load.
The first-frame Gateway admission alone reached 1.330 s for the status response
and 0.748 s for adjustment. Expensive business observation should not share a
fatal lifecycle with the voice stream merely because a read timed out. Any
reduced read/validation path must retain exact authority and freshness semantics;
this report does not authorize bypassing them.

Immediate truthful acknowledgment is feasible. The current `_BUSINESS_INSTRUCTIONS`
in `openai_realtime_native_engine.py:459` explicitly requires only the function
call first, bans spoken preambles, and waits for the tool result before speech.
That policy deliberately creates silence while tools run. OpenAI's official
[Realtime prompting guide](https://developers.openai.com/api/docs/guides/realtime-models-prompting)
describes short tool preambles and speech alongside tool calls. Suitable examples
are “我来查一下当前任务状态” or “我来创建这个行程任务”; neither claims durable
acceptance or completion before the tool result.

Changing the prompt alone is insufficient evidence: the current route creates
the spoken continuation after receipt, so simultaneous tool/audio scheduling,
interruption, duplicate prevention and later truthful result speech must be
verified. A preamble reduces silent waiting; it does not by itself make the
underlying query finish sooner.

Recommended discussion order: (1) prevent observation timeout from taking down
voice and prevent unplayed Task announcements from being consumed on temporary
yield; (2) enable truthful short preambles with valid concurrent tool execution;
(3) remove measured repeated-query/continuation cost; (4) correct delegated-intent
and adjustment-result communication. The broad task remains paused pending that
discussion; this list is not an automatically active implementation packet.

## Verification of this diagnosis

The retained scripts successfully joined all 14 EOTs uniquely and 10 exact
browser starts, reproduced the eight no-tool summary values, and asserted
same-clock/nonnegative intervals. Exact Task events, presentation consumption,
history and the generated file were read without changing runtime state.
The browser first-frame samples missing from the rolling buffer were left blank,
not reconstructed as observed values. Documentation verification uses scoped
link checks, source-reference review and `git diff --check`; it grants no new
product test or deployment credit.
