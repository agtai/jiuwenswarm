# Terminal Task notification recognition/recovery repair — 2026-09-02

This is an immutable scoped source/test record, not physical acceptance.
Current credit and next work remain in [STATUS](../STATUS.md#reopened-terminal-task-notification-presentation-repair).
Risk/review authority is root [TESTING](../../TESTING.md).

## Source and scope

Baseline: `0ef3cfff67ed3f4b6db228736e0afd64d395b424` on the existing
`tmp_p3-9_acceptance` worktree. The separate W3 worktree was not changed.
Tier 3: the owned boundary is Integrated Web P1/P2/P3 notification arbitration,
exact media authorization and visible terminal TEXT presentation before ACK.
Backend contracts, Task mutation, provider configuration, timeout values,
deployment and remote refs are excluded.

Tested Git blobs (under `jiuwenswarm/channels/web/frontend/`):

| File | Blob |
|---|---|
| `src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx` | `6875f3090dff64a107d38193cff88f452a409228` |
| `tests/liveVoiceIntegratedRoutePanel.test.mjs` | `0b0324de1c2dab86c22261ac005e70eed6c02239` |
| `tests/liveVoiceIntegratedRoutePanelMounted.test.mjs` | `50754a9f2630fe62dc920a0a99cb88dc52d395bf` |

## Reproduced facts and cause

The inspected private log is `swarm-20260902-161818.log`; raw logs/audio are not
included. Correlated session: `web_1a062a2eafe_4d7fe704591a`; Task:
`task-2093b1d91d9a439b9f37b9ebf013d2b5`; Attempt:
`attempt-3626ebe5f71848ab9cbaf4b87d480d9b`.

- Created at 17:36:57, running at 17:37:01, completed at 17:37:21. The durable
  completed event is sequence 5, `event-b84913bb5172461785754516ad58bd25`;
  its result/file exists. This is a presentation failure, not an unfinished Task.
- The terminal AUDIO response is
  `response-task-progress-55c2fba74492a686f08f3263b4f9dde58dfb2443`, generation 13.
  At 17:37:49.552 recognition logged `STREAMING_SPEECH_PROVIDER_UNAVAILABLE`;
  at 17:38:03.811 it logged `STREAMING_SPEECH_PROVIDER_TIMEOUT` and degraded.
  At 17:38:05.270 Web reported `task_audio_playout_failed` for that exact response.
- TEXT progress ACKs followed at 17:38:06.090 / 08.389 / 09.003 for sequences
  0 / 3 / 5. The AUDIO cursor remained at running (3), while TEXT reached
  completed (5). Terminal TEXT used the canonical fallback response
  `response-task-progress-3f9c072ba59d5706aa1a6ce960af4dd45e8e26fe`.

Source inspection plus deterministic mounted reproduction establishes the race:
the first 15-second acquisition deadline requested capture settlement and
immediately started another 15-second deadline, although recognition/batch
fallback still owned a longer, separately bounded operation. The second deadline
therefore declared Task AUDIO failed too early. Natural EOT could enter the same
recognizing state before the first deadline. Physical acoustic/noise causation
is not claimed by these logs.

The fallback had a separate visibility defect: the technical P3 progress node
was sufficient to trigger ACK but did not add the terminal sentence to formal
chat. Merely changing the diagnostic `productOutput` would not fix normal chat.

## Repair and verification contract

- Join the exact pending recognition/submit operation, whether started by EOT
  or the notification deadline. Start the second acquisition window only after
  it settles. Do not discard a possible user utterance or extend timeout values.
- If the existing arbiter replaces the failed P1 owner, replay the retained P2
  observation with the same request/response/unit to restore media authority.
  Concurrent effect continuations share one replay and one captured-delivery
  compare-and-clear. Exit/generation/owner fences reject late continuation.
- On actual AUDIO failure, keep Registry's TEXT fallback. Project the reconciled
  canonical terminal sentence through the existing formal chat callback before
  progress can be ACKed. Its deterministic ID matches the existing backend
  `SessionFormalHistoryWriter` TEXT cursor-0/unit-0/SHA-256 identity, so history
  reload does not create a second message. No new history schema/writer or TTS
  retry was introduced.

Applicable `P/B/S/T/C/R` coverage: delayed empty transcript and provider timeout,
deadline and natural-EOT ordering, media-owner recovery, exact replay coalescing,
one completed playout/ACK, resumed capture and cleanup. `N/I/F` coverage: invalid
outcome/missing response, duplicate/foreign Task/Session/generation fallback,
failed reauthorization, Exit during recognition and Exit during replay; no late
TTS, Task mutation, second Agent submission or foreign presentation ACK.
`K/X`: production component/P1 owner are mounted against deterministic browser
and provider seams; real Registry tests cover canonical result/fallback/ACK.
These are automation-owned seams, not real microphone, provider or acoustic
evidence. No schema migration, new capability/flag, Executor or cross-project
mutation path is introduced; those broader dimensions are out of scope.

## Commands and outcomes

Frontend commands run in `jiuwenswarm/channels/web/frontend`:

```text
npm ci
npm run test:live-voice-integrated-web
node --test --test-reporter=tap --test-name-pattern="mounted captured terminal AUDIO|mounted Task AUDIO failure adopts|terminal fallback chat|only the exact visible terminal" tests/liveVoiceIntegratedRoutePanel.test.mjs tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
npm run build:live-voice
git diff --check
```

- RED: against unchanged baseline product code, held recognition produced an
  early `presentation.failed` (both empty/timeout cases), and terminal fallback
  left the primary output at running. The added assertions failed as intended.
- Final focused suite: **10 passed, 0 failed**. Successful recovery performs one
  terminal synthesis and one post-playout ACK; failure/Exit checks assert zero
  forbidden terminal audio/chat/ACK and zero duplicate Task/Agent effects.
- Full affected suite: **503 passed, 5 failed, 1 skipped (509 total)**. It was
  also rerun directly with TAP against the exact file list in the package script.
- Production build: **PASS**, TypeScript plus Vite, 4651 modules, final Vite
  build 32.43 seconds. Existing duplicate i18n key/import/chunk warnings remain.
  `npm ci` reports 16 lockfile audit vulnerabilities (5 moderate/11 high);
  dependency remediation is excluded, and the lockfile was not changed.
- Backend, from repository root using the existing Python environment:
  `python -m pytest tests/unit_tests/live_voice/test_product_composition_registry.py -k "terminal_notification or audio_playout_failure or later_audio_failure or text_progress_web_ack" --no-cov -q`
  → **8 passed, 190 deselected**. This exercises actual Registry terminal result,
  exact replay/authorization, AUDIO-to-TEXT fallback and class-isolated ACK.

The same five full-suite failures were observed on the unmodified baseline
product source before this repair and are not credited as passing:

1. `mounted P3 origin panel reconciles and ACKs authoritative completed and failed progress` — accepted delivery ACK is not attempted.
2. `mounted stale Task TEXT replays after foreground ACK and presents before its only ACK` — fixture expects TTS for server TEXT.
3. `mounted terminal notification replays its exact P2 observation after Live Voice creates a media owner` — fixture expects TEXT retained while voice is off.
4. `mounted Exit retires a deferred stale Task AUDIO owner before same-Session successor capture` — terminal-without-final capture restart expectation times out.
5. `mounted foreground status query restarts an idle P2 poll after background terminal settlement` — background terminal announcement does not play after foreground ACK in the existing fixture.

These remain Integrated Web owner follow-up; this batch does not rewrite their
oracles or claim a passing cumulative candidate Gate.

## Scoped review and remaining evidence

The complete scoped diff was cold-reviewed for pending-stop settlement, exact
response replay, effect races, Exit/scope fencing, canonical text/history identity
and ACK ordering. Findings during implementation were corrected: primary output
alone was hidden in normal chat, and effect replacement could duplicate a media
reauthorization. The final source uses formal chat and shared single-flight replay.
No remaining repair-scope defect was found in this self-review.

An independent local reviewer was unavailable; cold self-review is a disclosed
substitute, not an independent Tier-3 PASS. No fresh deployed human listening
test was run. Independent review and controlled real-voice reacceptance remain
required; historical P3-9 human credit does not transfer to this source.
