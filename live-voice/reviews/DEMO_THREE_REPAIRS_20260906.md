# Demo timing, notification ownership and playout repair

Baseline: `9a1813463349e21d7de811a235e2998abf90b1e6`.
Accepted scope: the local `NEXT_SESSION_DEMO_REPAIR_PROMPT.md` and its
`three-bugs-diagnosis.md` evidence in `logs/rehearsal-web_1a073b73faf_4aa26872de98`.
Original logs/video remain unchanged. This is a bounded module repair, not
performance or full candidate acceptance.

## Intended behaviour and owned boundaries

- Web timeline (Tier 1): each user boundary resets elapsed-time ownership,
  including empty cancelled/replaced requests. Goal badges do not prove a common
  request. The existing Goal history has its own request ID and defers behind an
  active user round; the frontend badge/text matching supplies no causal link to
  the preceding request. Therefore no timestamp inheritance is retained on that
  evidence. Keep response waiting and final completion times; invalid timestamps
  must not move a user boundary behind its answer or invent elapsed time.
  Source/tests: shared `buildTurnTimeline.ts` and timeline/history tests.
- Task notifications (Tier 2): select exact scope/work before limiting; make
  Bridge retention versus Registry takeover explicit. Internal scheduling
  transfer never advances the durable heard watermark. Preserve authorization,
  terminal replay, quiet running/cancelled policy and exact Runtime ACK fences.
  Source/tests: Arbiter, task progress Bridge, Registry and their module tests.
  Fresh explicit subscription recovery uses existing authorization/lease rules;
  no generic automatic retry or FAILED-to-ACTIVE transition is introduced.
- Audio (Tier 2): establish the 250 ms lead on accepted PCM, retain ordered
  samples across bounded buffering/recovery, and preserve immediate cancellation,
  tentative pause, response/generation identity and actual playback ACK.
  Source/tests: browser audio/media adapters, Gateway media path and their tests.
  Add bounded metadata to distinguish source/send/receive/ACK and scheduling gaps.

Dependencies: existing durable Task store, Registry presentation owner, Runtime
ACK, WebAudio clock and dedicated media transport. No protocol/schema migration,
new classifier, Agent/model/Provider change, VAD change, source output rewriting,
historical data deletion or remote ref update. Actual headset continuity and
full A/B/A2 acceptance remain human rehearsal boundaries.

## Verification

Checks follow the applicable [TESTING](../../TESTING.md) module boundaries.

### Web timeline

`npm run test:task-notification-timeline`: 13 passed. Original-source reproduction
failed with 20153 ms rather than 12360 ms; corrected shared timeline passes the
recorded timestamps, pending timer, consecutive users, Goal/display-only marker,
notification, tool/reasoning, final timestamp and invalid-time cases. Tests use
the actual history/FileViewer parser, not only JSON cloning. `tsc --noEmit` passes.
Existing duplicate `empty` locale-key build warnings are outside this scope.

Complete scoped diff review and independent read-only review found invalid-time
work attribution and history sorting issues, including adjacent undated records;
all were repaired with specific regressions. Unknown timestamps retain source
message boundaries and use only known work times; no timestamp is synthesized.

### Task notification ownership

The shared Arbiter previously limited by scope before a Bridge checked its Task.
Selecting another Task's pending candidate failed the requesting subscription;
it did not consume the other Task's ACK. The isolated reproduction proves that
defect; the original rehearsal did not log the subscription failure code.

Drain now filters authenticated scope plus exact work kind/id before applying
the limit. The Bridge still verifies returned scope, work and retained projection.
Deferred delivery explicitly returns Bridge, Registry or silent-policy ownership.
Bridge-only consumer terminals keep their cursor until drained or closed; a
successful Registry/silent handoff clears only the exact scheduler entry, after
fresh generation/authorization/close checks. The cleanup wrapper preserves this
result. Durable heard watermarks still require exact Runtime ACK and fresh
`task.ack_events` authority. A failed Bridge remains failed; existing explicit
authorized reopening creates a fresh lease from durable unread state.

Source/test coverage (Tier 2, including the actual Store/Bridge/Arbiter seam):

| Dimensions | Evidence |
|---|---|
| P, S, C, I | A-empty/B-quiet and both-pending, either drain order; quiet prefix followed by terminal; busy-to-idle; Bridge cursor retention and Registry takeover. |
| N, T, I | Wrong scope/work/kind, stale generation, expired authority, close during handoff; zero scheduling/durable ACK and no extra delivery or protected Task-history mutation on fenced paths. |
| B, K | Work filtering before limit; protected `decision_required` survives a later quiet projection; legacy sinks returning None retain Bridge ownership. |
| R, F | Failed sink remains failed; fresh authorized lease replays unread terminal; playout failure/successor replay; unavailable Registry consumption retains Bridge ownership. Existing flag-off/adapter rejection checks remain. |
| X | Registry Agent ACK drain, activation/reopen, exact P2 Runtime ACK, progress-close race and duplicate/generation ordering checks. No real user-heard claim. |

Commands/evidence in ignored `logs/three-repairs-tests`:

- Ownership regression file: **15 passed**, including six post-await fence cases
  (`handoff-fence-final.txt`).
- Ownership + Arbiter + P3 text adapter: **90 passed** before the final six fence
  additions (`ownership-final.txt`). The text adapter's 26 tests also passed
  after its return annotation was restored (`diag-wrapper-final.txt`).
- Focused Registry + ownership scenarios: **25 passed**, 208 deselected
  (`registry2.txt`); includes durable ACK/reopen and failed-generation cases.
- Initial Bridge/Arbiter/P3 text/ownership regression run: **139 passed, 5 failed**
  (`ownership-green1.txt`). All five fail unchanged at baseline `9a1813463`
  (`baseline-five.txt`): recovery-attempt-boundary text/voice, more-than-256
  presentable events, and unread replay across cancelled retry attempts text/voice
  in `test_task_progress_return.py`. These adjacent baseline failures remain open;
  this is not a passing whole-Bridge or full-project suite claim.

Complete cold scoped diff review and independent read-only review completed.
Review found that takeover must pass the retained protected projection, not the
newer quiet projection; repaired with a regression. Owner logs distinguish last
source event/seq from selected/retained projection, and include Task/attempt,
requested/returned work, origin, generation and state/reason.

### Audio

Previously `beginPlayout` spent the startup lead while waiting for the downlink
connection; the six recorded first enqueues therefore had zero buffer ahead.
The first accepted PCM now anchors the full 250 ms lead. Subsequent frames append
at the scheduled end. Only actual starvation starts a new reserve, using the
observed interarrival interval clamped to one through three startup leads
(250–750 ms at the unchanged default). This is a latency/continuity tradeoff:
it can add a longer recovery pause so a following burst plays continuously. It
does not eliminate arbitrary upstream stalls or promise physical word continuity.
No samples are dropped/replayed and stop/tentative pause retain the unplayed
cursor and exact response/generation fencing; render ACK remains on actual
source completion, not enqueue or scheduling.

Bounded metadata records initial frames and supply gaps at Gateway pull-ready,
successful send and validated enqueue ACK, and browser accepted receive,
successful ACK send and scheduling. Pull-ready is the Gateway observation, not
proof of when the Provider generated a frame. The async source remains serial
send → enqueue ACK → next pull. No flow-control or Provider optimization was made.
Scheduling gap includes the recovery reserve; `supply_late_ms` separates lateness
from the added reserve. Gap endpoints and buffer values survive offline import.
No PCM, speech text or private device contents are added to diagnostics.

Tier-2 checks cover immediate/330 ms/2 s first-PCM arrival, short seed then gap and
burst, repeated starvation with capped recovery, short tail, pre-first-PCM cancel,
stop and tentative pause during recovery, unplayed sample preservation, old
response rejection, reordered/duplicate source callbacks, feature-off and sink
failures. Delayed async-source tests prove the real Gateway adapter's pull/ACK
ordering. Malformed frames close exactly once with no audio/stop side effect;
passive diagnostic failure cannot change delivery or ACK authority.

- `npm run test:live-voice-browser-audio-io`: **120 passed**
  (`audio-diag-final.txt`), including numeric full-gap/reserve diagnostics.
- `npm run test:live-voice-browser-dedicated-media`: **32 passed**
  (`browser-media-final.txt`), including immediate/deferred failed-send ACK logs.
- `npm run test:live-voice-native-interaction`: **126 passed** (`route1.txt`),
  including the affected P1 route and exact generation/Exit integration. The
  later browser change only moves passive ACK logging after successful send and
  has its own final adapter regression above.
- `pytest -o addopts='' tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py tests/unit_tests/live_voice/test_demo_profiling.py`:
  **117 passed** (`media-final.txt`). After adding report-field preservation,
  the full profiling file has **28 passed** (`report-final.txt`). Tests use an
  isolated `JIUWENSWARM_DATA_DIR` and separate basetemp under ignored logs.
- The existing `probe_startup_lead.mjs` was reused in memory, with only fixture
  extraction made tolerant of the newly inserted test declarations. At immediate
  first PCM, starts remain 250/270 ms. At 330 ms first PCM, starts are now
  **580/600 ms**, with **250 ms actual lead and zero inter-frame gap**, versus
  baseline 330/460 ms, zero lead and 110 ms gap. Output: `startup-repaired.json`;
  adapter source SHA-256: `55bbf0c6d763e687f5cf49ee774248582010bbe4795371d8ffd6977a81ab0ef7`.

Complete cold scoped diff review and independent read-only review completed.
Review findings about pre-validation diagnostic exceptions and incomplete gap
accounting were repaired and verified, with delayed-source and tentative-pause
regressions added. The original six video/waveform observations are retained;
they have not been relabelled as repaired physical evidence. Per-gap upstream
causes and current-head headset continuity remain unproved.

## Controlled deployment boundary

Initial runtime check found no listeners on the four Demo ports and the old
service PID was gone. The registered private project was clean, all 89 retained
Tasks were terminal, and SDK `0.1.16+jiuwenswarm.responses2` was installed.
Deployment uses the existing [runbook §7.5](../runbooks/E2E_RUNBOOK.md#75-当前受控-live-voice-启动与预演)
launcher after local module commits, with formal-web-validation, Cascade,
verified-headset-aec-v1 and NoBrowser. The new ignored runtime contract and live
PID/ports, not this preparation record or old contract, establish actual startup.
Model/Provider/VAD, project files, historical results and heard watermarks are
preserved. Real Speech readiness does not close full Agent/Task/headset A/B/A2
acceptance; the user must perform the current rehearsal and export diagnostics.
