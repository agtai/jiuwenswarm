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

Implementation and scoped verification in progress. No physical acceptance is
claimed by deterministic or module checks.
