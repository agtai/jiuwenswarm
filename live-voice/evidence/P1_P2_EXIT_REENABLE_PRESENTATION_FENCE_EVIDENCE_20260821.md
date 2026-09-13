# P1/P2 mounted Exit/immediate-re-enable presentation-fence evidence

> **Superseded intermediate record.** The seven local repair/evidence commits
> were later consolidated on top of `451599b43`. This file preserves why the
> first presentation-fence attempt was made, but its cross-generation response
> transfer is not the current invariant and its source/automated closure claim
> is withdrawn. In particular, the “delayed retained ACK” test below passed by
> waiting for the old ACK before activating the successor; that is the remaining
> defect, not proof of ACK independence. Current judgement and required oracles
> are in
> [P1_P2_EXIT_REENABLE_GENERATION_RETIREMENT_EVIDENCE_20260822.md](P1_P2_EXIT_REENABLE_GENERATION_RETIREMENT_EVIDENCE_20260822.md).

## Boundary and source

- Date: 2026-08-21
- Baseline: `c8aea1dc86aeb7f6934352d0c548aed28153bb2d`
- Pre-rebaseline intermediate object: `200f7b891`
  (`fix(live-voice): fence exit re-enable presentation race`); it is no longer a
  branch commit after consolidation and is retained here only as provenance
- Risk: Tier 3 under root `TESTING.md`
- Owner: Formal Integrated Web Conversation Runtime replica and its
  capture/presentation arbitration
- Changed product surface:
  `LiveVoiceIntegratedRoutePanel.tsx`
- Changed automated surfaces:
  `liveVoiceIntegratedRoutePanel.test.mjs` and
  `liveVoiceIntegratedRoutePanelMounted.test.mjs`

No shared protocol/schema, Gateway/Provider implementation, Agent/Tool/Task
policy, P2 latency mechanism or generation-time interruption policy changed.

## Reproduced failure and implemented invariant

The clean baseline reproduced one Formal Web failure. Exit followed by immediate
re-enable replaced P2 activation while a committed unified submit was still
settling. A successor capture timer could be scheduled before the old submit
published its foreground-presentation flag. That timer entered P1 `starting`,
cancelled the successor notification effect, and caused an already-returned
notification to be discarded before presentation adoption or ACK.

The repair replaces the coarse flag with an exact pending-presentation fence
carrying Session, correlation, interaction, submission activation, turn, commit,
canonical response and originating voice-loop generation. Pending submit and
pending presentation now form a continuous capture-admission barrier. Admission
is checked before scheduling, inside the single capture timer, after asynchronous
media-authority refresh and immediately before P1 allocation. Exit, Session
replacement and unmount explicitly cancel the scheduled timer.

The predecessor activation remains submission provenance. A successor P2
activation may deliver the same canonical response through its unchanged
Session/correlation/interaction binding, text-present it and ACK it once. If the
response crosses an Exit voice-loop generation, TTS/playout is explicitly
forbidden. A current post-re-enable response retains normal TTS/playout.

## D-032 scenario evidence

- `P`: after immediate re-enable, a new microphone capture reaches first-frame
  readiness, commits one final, submits once, plays one current TTS/browser
  source, sends one playout receipt and presentation ACK, then resumes capture.
- `N/I`: the predecessor activation notification has zero ACK, TTS and source
  effect; successor delivery is bound to the exact canonical response; the
  existing Session-switch regression proves predecessor TTS settlement cannot
  retain an ACK or block the successor.
- `B/S`: immediate Exit/re-enable, definitive unified rejection,
  terminal-without-final, final Exit and closed P1 state are covered.
- `T/C`: old submit success races P2 successor activation and zero-delay capture
  scheduling; delayed predecessor notification and delayed retained ACK remain
  fenced; one capture timer is retained and explicitly cleared.
- `R/F`: retained ACK recovery, definitive rejection recovery, text-only old
  response fallback and feature-off/current formal regressions stay green.
- `K/X`: mounted React, real formal owners, browser audio and dedicated media
  adapters, affected Gateway/Speech regressions and the production build pass.

The mounted oracle also asserts four unique committed-submit request identities,
only the predecessor text response and current audible response are ACKed, one
current synthesis/playout receipt/source, zero Task mutations, unique projected
history IDs, and balanced final cleanup for microphone tracks, AudioContexts,
AudioWorklet ports and dedicated media sockets.

## Commands and results

From `jiuwenswarm/channels/web/frontend` unless noted:

```text
node --test --test-name-pattern="mounted Exit and immediate re-enable recover after old unified success or rejection without replaying TTS" tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
1 passed, 0 failed

node --test --test-name-pattern="mounted (stale TTS settlement after Session switch|Exit fences a blocked start|Exit during a retained presentation ACK)" tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
3 passed, 0 failed

npm run test:live-voice-integrated-web
440 passed, 0 failed

npm run test:live-voice-browser-audio-io
103 passed, 0 failed

npm run test:live-voice-browser-dedicated-media
27 passed, 0 failed

npm run build:live-voice
PASS
```

From the repository root:

```text
.venv\Scripts\python.exe -m pytest \
  tests/unit_tests/gateway/test_dedicated_media_registration.py \
  tests/unit_tests/gateway/test_product_streaming_synthesis.py \
  tests/unit_tests/gateway/test_live_voice_speech_rpc.py \
  tests/unit_tests/gateway/test_streaming_speech_route.py \
  tests/unit_tests/live_voice/test_openai_streaming_speech.py \
  -q --no-cov
195 passed, 0 failed
```

`git diff --check` passed before the implementation commit. The build retained
the pre-existing Vite chunking and duplicate locale-key warnings; neither was
introduced by this packet. An initial broad run exposed one source-structure
assertion still naming the retired boolean; the assertion was updated to the
exact fence and the final full run is the `440/440` result above.

## Non-claims and remaining acceptance

This superseded record grants no current source, automated or physical closure.
It does not claim a new
physical microphone/speaker result, independent Tier-3 review, latency closure,
generation-time interruption, complete P1/P2, P3-9, product readiness or
Production readiness. A later clean current-source Chrome journey must still
observe Exit during a pending response, immediate re-enable, no predecessor
audio, one audible current answer, resumed listening and final device/media
cleanup before physical credit is granted. The separate delayed-ACK oracle must
also prove successor capture before the old ACK settles; an ordinary physical
run without injected ACK latency cannot close that seam.
