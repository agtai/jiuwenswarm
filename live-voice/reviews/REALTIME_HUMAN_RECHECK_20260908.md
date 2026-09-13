# September 8 human recheck after the three repairs

> September 8 supplement: the [bilingual per-operation timing breakdown](REALTIME_OPERATION_TIMING_BREAKDOWN_20260908.md)
> expands this same run into first-audio, tool/receipt, execution and notification
> stages. It adds no new product or physical acceptance claim.

## Scope and evidence

Read-only diagnosis requested by the user for Session
`web_1a080c762a5_7ff4e1f0095d`. Intended outcome: correlate the actual browser
journey, Gateway/AgentServer logs and durable Task facts, measure initial spoken
feedback separately from actual receipts/results, and report remaining errors.
No product code, configuration, runtime state or service restart is part of this
recheck. Broader acceptance and item 4 (Task intent/result semantics) stay outside
the repair scope; observed content issues are recorded without starting repairs.

The supplied `09-47-41-157Z.json` is the previous Session's export. The matching
file was found at
`C:/Users/admin/Downloads/live-voice-diagnostics-2026-09-08T11-36-01-252Z.json`:

- Exported at `2026-09-08T11:36:01.232Z`; SHA-256
  `bc757d1d78ae4da7949081b1745bdf64cb829e31ae735d23f4cabdb9a1eb3f5b`.
- Browser clock `browser-mtsl6rbv-ci3jar65d7`. Filter by this clock, exact Session /
  interaction / response IDs and the 11:29:05–11:36:01 UTC window. Old-session
  errors retained in the export are excluded. In particular, its 14 earlier
  `browser_unhandled_rejection` records are not failures in this new journey.
  The export reports routine record/page overwrites but zero milestone-memory
  and milestone-page overwrites, and zero storage failures. Retained EOT/start
  milestones support these timings; a complete frame-by-frame trace is not claimed.
- Main log `logs/swarm-20260908-130233.log`; 7,641 exact-session server diagnostic
  events in the bounded window. Raw error lines and related Task IDs are also
  checked. The log uses Paris local time, two hours ahead of UTC.
- Runtime manifest binds clean code `fff2fe15b7`, gpt-realtime-2.1, speed 1.25,
  minimal reasoning and server-vad-450. The selected Jiuwen Agent is
  deepseek-v4-flash#0. Recheck started on clean documentation HEAD
  `6feb02b1e728e85ab911fe1bb70c6b7e1eaf06c1`, branch `hx/0812_live_voice_w3`,
  with upstream comparison 0 ahead / 0 behind.
- Private snapshots, the reproducible analysis script, CSV and HTML profile are
  retained in `logs/acceptance-web_1a080c762a5_7ff4e1f0095d/` (ignored by Git).
  Task SQLite is opened read-only. No model or tool execution is initiated.

## Measured conversation and operations

The first-sound metric is browser receipt of Provider end-of-turn (EOT) to
`playout_clock_reached_start`, on the **same browser monotonic clock**, with
AudioContext running. It excludes acoustic tail/VAD and hardware output delay.
Tool receipt timings use the Gateway clock. History timestamps indicate
completion/history persistence, not first sound. UTC is used only to describe
cross-process ordering and the approximate Task-completion-to-announcement gap.

| Input / operation | First spoken feedback after EOT | Later result / receipt |
| --- | ---: | --- |
| Introduce Shenzhen in one sentence | 2.430 s | Ordinary response |
| Is Shenzhen coastal? | 1.287 s | User interrupts this answer to continue |
| Where can I see the sea? | 2.251 s | User interrupts this answer to continue |
| Where to go on Saturday afternoon? | 1.304 s | Ordinary response |
| Create a weekend itinerary + add “generate a file” | 1.763 s after the final addendum | Real create receipt at 6.053 s; confirmation response R7 never starts playback |
| What is good to eat in Shenzhen? | 1.755 s | Ordinary response after recovery; subsequently interrupted |
| Change Saturday noon to morning tea | 1.545 s | Pending-receipt speech starts at 9.985 s; actual application recorded separately |
| Query this weekend's weather | 1.287 s | Accepted/in-progress speech at 6.717 s; actual forecast starts at 28.037 s |

There are nine Provider EOTs and eight semantic inputs above. The create request
was followed 1.718 s later by “并生成文件”; the earlier response did not play.
The create latency starts at that final addendum, not before the user finished.
Using the first segment's EOT would give 3.481 s to the same first feedback.

Five ordinary-chat observations: median **1.755 s**, mean 1.805 s, range
1.287–2.430 s. Three were subsequently interrupted, but their first starts were
observed. Do not describe this run as “consistently 1.2 s”: the previous human
run's eight-sample median was 1.199 s. Different utterances and concurrent Task
activity prevent attributing the difference to a regression from these samples
alone. The old 3.3 s diagnostic baseline still lacks aligned endpoints/sample
selection for a strict improvement percentage.

| Business operation | Complete arguments → real receipt | EOT → real receipt | Notes |
| --- | ---: | ---: | --- |
| task.create | 1.317 s | 6.053 s | Task accepted once and executes successfully |
| task.adjust | 2.300 s | 5.671 s | Receipt says pending, not applied |
| work.start (weather) | 0.810 s | 2.829 s | Real Agent round takes 12.674 s; speech delivery adds further waiting |

Early speech is functioning. It varies with the action: the create says it will
create a task and save a file; the adjustment says it will change the itinerary;
weather says it will check the weather. It is not a fixed “我来查一下” response.
For create, receipt arrival at 11:30:22.519 waits until the preamble playback ACK
at 11:30:25.732 before the successor is sent. Thus a longer preamble itself can
delay spoken confirmation even though the actual operation has already returned.

This run contains **no voice `task.status` call**. The right-panel query RPCs do
run: list 17 samples / median 0.311 s / maximum 1.547 s; status 24 / 1.035 s /
2.056 s; events 19 / 0.264 s / 1.580 s; result 15 / 0.327 s / 1.323 s. They cannot
be substituted for voice command → spoken status-result acceptance.

The shared `product_composition` lock remains an observed source of delay:
`handle_p3_query` holds it up to 1.928 s, blocking Native admission and notification
work. Task latency has room to improve beyond the successful early feedback.
No lock repair is performed in this read-only scope.

## Task completion and notification

Actual Task `task-1ee40aabbe5e48aa8932525696057dd2` has the following durable events:

| Event | UTC time | Elapsed |
| --- | --- | ---: |
| Task accepted | 11:30:21.816550 | Start |
| Task running | 11:30:23.141388 | 1.325 s after acceptance |
| Adjustment requested | 11:31:04.256173 | — |
| Adjustment applied | 11:31:10.580689 | 6.325 s after request |
| Task completed | 11:31:48.644660 | 86.828 s after acceptance |
| Weather result begins playback | 11:31:59.311 | — |
| Weather playback settles; capturing resumes | 11:32:29.595 | — |
| Completion notification begins playback | 11:32:33.511 | 3.916 s after foreground playback settles |
| Browser presentation acknowledged | 11:32:40.578 | 7.067 s after notification starts |

The completion-to-notification-start wall-clock gap is about **44.866 s**. The
foreground weather operation, its in-progress speech, result delivery and
30-second forecast playback occupy most of that interval. Notification prepare
starts at 11:32:29.715 and takes 1.337 s. This is a delayed announcement that
eventually plays, not a missing announcement or a 45-second TTS request.

Response R14 is
`response-task-progress-b9b366a792dc5e9fe9388e9a35f31b6e2352d6d3`.
The browser start and ACK match this exact tuple. Durable `task_event_consumption`
contains presentation class **voice**, acknowledged through terminal event 7,
updated at 11:32:40.453822 UTC. No text-consumption row substitutes for it.
The local artifact exists and its SHA-256 matches the recorded result:
`深圳周末两日行程-大小梅沙大鹏新城.md`,
`087a9c0e7d9192e505e43f731e423e0710d7c1380b099d82041d5edef60fd428`.
This verifies delivery/identity, not the itinerary's factual or semantic quality.

Together with the user's report that the overall journey felt normal, this gives
scoped human credit to completion announcement after foreground work becomes
idle. Only one notification preparation is observed: this run does not exercise
every pre-play failure/cancel/re-prepare branch from the
[three-fix repair](REALTIME_THREE_FIXES_20260908.md).

## Errors and remaining limits

### One interruption/delivery race closes the media session

At Paris **13:30:28** (UTC 11:30:28), create-confirmation response R7 fails with
`STALE_RESPONSE_OUTPUT`. The real Task was already accepted and remains running.
R7 has no `playout_clock_reached_start`, so it cannot be credited as heard.

The observed sequence and matching source explain the failure chain:

1. R7 audio arrives at 11:30:27.317. Admission of its first frame waits 1.332 s on
   the Registry lock while `handle_p3_query` is holding it (log lines 11263–11264).
2. Provider `input_audio_buffer.speech_started` arrives at 11:30:27.345 (line
   11213), while those frames are queued. Whether this sound was intentional
   speech or background sound is not recoverable from content-free diagnostics.
3. The response is interrupted and Provider cancellation sent at 11:30:28.664–.667.
   The queued batch for R7 is refused as stale at .668 (11277).
4. Gateway `_deliver_native_audio_batch` has an exact interrupted-response
   exception for `NATIVE_AUDIO_RESPONSE_STALE`; this runtime instead returns
   `STALE_RESPONSE_OUTPUT`. The error escapes and `_consume_native_task` closes
   the media session (11286–11303). See
   [batch admission](../../jiuwenswarm/gateway/live_voice/dedicated_media_registration.py)
   and [output fence](../../jiuwenswarm/server/live_voice/conversation_runtime_loop.py).
5. Subsequent microphone frames hit `session_closed`, producing
   `MEDIA_NATIVE_INPUT_FENCE_REJECTED` and the browser's
   `ADAPTER_UPLINK_PEER_DETACH_MEDIA_CONSUMER_FAILED`. These are consequences of
   the one race, not independent Task failures.

Browser error state begins at 11:30:28.715. Activation 2 is confirmed at
11:30:35.390; capture resumes at 11:30:39.655, about **10.94 s** later. The next
ordinary question succeeds. The diagnostics do not reliably establish whether
recovery was initiated by a user action, so this is not an automatic-recovery
claim. The remaining route/capability rejections around that restart are stale
requests during teardown. The later notification-consumer detach at 11:32:42
occurs after successful notification ACK, followed by activation 3; it did not
lose the notification. No `NATIVE_RUNTIME_TIMEOUT` is observed in this run.

### Four scheduling gaps, without a reported tearing recurrence

| Response | Browser frame sequence | Scheduling gap | Matching Registry frame-admission lock wait |
| --- | ---: | ---: | ---: |
| R9 adjustment preamble | 76 | 0.328 s | 1.282 s |
| R10 adjustment receipt | 28 | 0.829 s | 1.266 s |
| R10 adjustment receipt | 44 | 0.680 s | 0.943 s |
| R10 adjustment receipt | 60 | 0.059 s | 0.336 s |

The exact response/frame joins show local supply stalls and the resulting
schedule gaps. They do not prove crackling, tearing, or how the pauses were
perceived. Preserve the user's positive listening feedback and previous
no-tearing acceptance; do not broaden it into “no underruns or pauses anywhere.”

### Other observed errors/content issues

- The weather Agent's context setup attempts to read missing AGENT.md, SOUL.md,
  HEARTBEAT.md, USER.md and IDENTITY.md: five files across three rounds, **15**
  `read_file` error records (code 199003). The actual Agent round and weather
  answer complete. These are context-file lookup errors, not failures to create
  the itinerary artifact. No files are fabricated to silence them.
- Startup logs warn about unavailable `web_paid_search`, `skill_retrieval` and
  skipped optional rails/processors. The observed Task/Work journey still
  completes; their broader capability implications are outside this recheck.
- R10 speaks an English pending receipt containing the internal `task.adjust`
  term and Task ID. It is genuinely played and persisted in heard history. This
  remains a language/presentation-quality issue even though the adjustment
  applies. It does not justify claiming adjustment failure or expanding item 4.

## Assessment and verification

The current journey substantiates working early feedback, successful Task
creation/application/completion and a played, durably acknowledged completion
notification. It is **not an error-free run**: the create-confirmation interruption
race, lock-related pauses/delay and English receipt remain observed. Voice status
latency and all notification failure/replay variants lack human evidence here.

The offline analyzer enforces same-clock timing and unique EOT identity joins,
retains exact IDs and source hashes, and creates a CSV plus the existing HTML
profile. Generic profile failure counts include expected stops/cancellations;
they are not the number of independent bugs. Documentation verification follows
root TESTING.md: scoped diff review, local link resolution and `git diff --check`.
No product tests, new Provider calls, service restart or deployment are required
for this read-only evidence update. The broader paused backlog stays paused.
