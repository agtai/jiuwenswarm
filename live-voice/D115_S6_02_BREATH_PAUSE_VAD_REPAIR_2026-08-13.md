# D115 S6-02 breath-pause VAD repair

> Frozen implementation and verification record for source commit `e6ccb3e9`
> on 2026-08-13. Current state and next actions remain authoritative in
> [STATUS.md](STATUS.md).

## 1. Packet and result

- Stage/node: `S6 - Alpha Module Closure` / `A1`.
- Task: `S6-02`.
- Track/modules: P1 Streaming Recognition and Shared-X Gateway composition.
- Risk: Tier 2 because server-VAD timing determines the committed Turn boundary.
- Base: `0a495620`; tested source: `e6ccb3e9`.
- Scope: the default server-VAD silence duration and its affected contract,
  Adapter and Gateway tests.
- Exclusions: VAD type, Provider/model/voice selection, credentials, microphone
  device choice, browser lifecycle policy, P2 semantics, Task authority, public
  deployment and production scope.
- Result: the physically exposed breath-pause false stop is repaired and
  deployed. One targeted physical retest remains before this row can pass.

## 2. Physical observations received

The user completed the repaired physical route and reported:

- the cold first utterance “你好” stopped automatically and was recognized;
- the supplied long three-paragraph request also stopped automatically and was
  recognized;
- the reply played to completion with the intended voice and acceptable audio
  quality;
- a sentence-internal breath pause could still be mistaken for end of turn;
- minimizing the window interrupted active playout.

The first three observations close the D114 cold-EOT, 30-second cutoff and
browser-audio-quality regressions. The breath-pause observation is a distinct
turn-segmentation defect and is not hidden by those PASS results.

## 3. Cause and repair

The formal route used `server_vad` with a 500 ms silence duration. That is the
Provider default and treats a normal sentence-internal breath as a completed
turn. The [official OpenAI VAD guide](https://developers.openai.com/api/docs/guides/realtime-vad)
defines `silence_duration_ms` as the silence required to detect speech stop and
states that shorter values detect turns faster. It also documents semantic VAD,
but this repository has no accepted semantic-VAD type, Provider echo validation
or real-path evidence.

The repair therefore preserves the already-proven `server_vad` event and
authority contract and changes only the default silence duration from 500 ms to
1,200 ms. This adds 700 ms to final end-of-turn latency while tolerating a
natural breath pause. The separate 15-second open bound, 70-second recognition
session budget, manual stop path, `create_response=false`,
`interrupt_response=false`, Provider-time EOT truth and zero business authority
remain unchanged.

## 4. Verification

- Counterfactual: the new default-contract test on parent `0a495620` failed
  with `500 != 1200`.
- Repaired source: the same test passed.
- Streaming Speech contract, OpenAI Adapter and Gateway streaming-route suites:
  `177 passed`.
- Ruff on the affected source/tests and `git diff --check`: PASS.
- B environment restarted from the repaired source; Agent, Gateway, Web, Caddy,
  HTTPS 443 and all declared service ports reported ready.
- Post-restart dedicated-media control probe: activation, ticket, fixed WSS
  path, privacy, subprotocol, first-frame authentication, attach/detach,
  authority close and P2 close all PASS.
- Main performed the D-074 affected-diff cold review. No independent reviewer
  was assigned for this bounded follow-up, so the focused counterfactual and
  affected regression suites are the recorded substitute and limitation; this
  is not represented as an independent review.

The exact remaining physical check is one utterance containing a deliberate
sentence-internal pause shorter than 1.2 seconds, followed by a final silence
longer than 1.2 seconds. It must remain listening across the internal pause and
then stop exactly once after the final silence.

## 5. Minimize/background behavior

Window minimization makes the document hidden. The accepted browser lifecycle
is intentionally fail closed: active capture/playout is fenced, playout reports
`PAGE_HIDDEN_PLAYOUT_FENCED`, no playout receipt or business cancel is forged,
and returning to visible does not resurrect stale audio. The user's observed
interruption is therefore expected. O6 closes only after the physical return to
the page confirms an explicit stopped/failed state and no automatic replay,
duplicate audio or stale tail.

No remote ref was updated. No credential, raw audio, browser profile or private
runtime artifact is committed.
