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

### Task notification and audio

Implementation and scoped verification in progress. No physical acceptance is
claimed by deterministic or module checks.
