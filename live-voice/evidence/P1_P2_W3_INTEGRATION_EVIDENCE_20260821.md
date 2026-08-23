# P1/P2 repair integration into W3

## Scope and source

- Integration branch: `hx/0812_live_voice_w3`.
- Tested integration source: `8846862f009d332761763f887c38ce6486f3ee90`.
- Integration baseline: `68e2d6e93215b451c31de051a4797d3225c8bce0`.
- Imported source range: `7814c1473769ece62006b56b933c6860649c1502`
  through `046ecac054449af1451d3a95521f627a25f93b05` from
  `hx/0819_live_voice_p1p2`.

The integration owns transparent post-TTS capture rotation, successor-capture
ACK decoupling, post-playout receipt truth and the hands-free playout controls.
It preserves the W3 schema-v6 Task, presentation-consumption and authenticated
intent authorities. It adds no Task schema, ledger, presentation ACK or intent
policy.

## Commit mapping and conflict disposition

| Original | W3 commit | Disposition |
|---|---|---|
| `7814c147` | `a9cae723` | Activation prose adapted to the already-closed Wave-3 baseline |
| `6cd8840d` | `397ceb1e` | Source/test payload applied unchanged |
| `874cf327` | `f59b7f4c` | Source/test payload applied unchanged |
| `35cae3d9` | `8df8f12f` | Source/test payload applied unchanged |
| `e1df8b45` | `01d8b527` | Source/test payload applied unchanged; STATUS date kept at 2026-08-21 |
| `046ecac0` | `8846862f` | Physical result retained at its original tested source; W3 P3 rows preserved |

Only `live-voice/STATUS.md` required manual conflict resolution. The old
schema-v4/P3-2-active text was not allowed to replace W3 schema-v6 and the
closed P3-4/P3-5B/P3-6 facts. Stable patch IDs for each of the four source/test
commits match their originals exactly:

```text
6cd8840d / 397ceb1e  963965c9f8de52d12b286f76bec09bebd134fd3e
874cf327 / f59b7f4c  8ad11e877d1547deb2d0306aed3236f7cb138dcb
35cae3d9 / 8df8f12f  433e3a585d35ea7d7abcb4f58f08d49729decae8
e1df8b45 / 01d8b527  196a0180b1a90068d77c7f03cf479c51bbe3a1a4
```

## Integrated verification

Commands were run from the tested source above unless a working directory is
shown explicitly.

```text
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-browser-audio-io
103 passed, 0 failed

cd ../../../..
.venv\Scripts\python.exe -m pytest \
  tests/unit_tests/gateway/test_dedicated_media_registration.py \
  tests/unit_tests/gateway/test_product_streaming_synthesis.py \
  tests/unit_tests/gateway/test_live_voice_speech_rpc.py \
  tests/unit_tests/gateway/test_streaming_speech_route.py \
  tests/unit_tests/live_voice/test_openai_streaming_speech.py \
  -q --no-cov
194 passed, 0 failed

cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-integrated-web
422 passed, 1 failed of 423

npm run build:live-voice
PASS; 4643 modules transformed

cd ../../../..
git diff --check 68e2d6e9..8846862f
PASS
```

The sole Formal Web failure is the previously disclosed mounted
Exit/immediate-re-enable case:

```text
mounted Exit and immediate re-enable recover after old unified success or
rejection without replaying TTS
```

It was the sole Formal Web failure on the W3 baseline and on the imported
P1/P2 line. The integration does not claim it as repaired. Existing non-failing
build warnings about locale duplicate keys, mixed static/dynamic imports and
large chunks remain outside this bounded integration.

## Closeout interpretation

The integration/core repair batch is closed, but formal P1/P2 overall is not
`COMPLETE`. `422/423` means there is exactly one reproduced failing Formal Web
regression in this run; it does not mean that only validation remains.

Remaining code closure consists of:

- repairing mounted Exit/immediate-re-enable convergence;
- integrating and verifying the assigned P2 notification batch/push/coalescing
  latency work;
- closing hands-free interruption during Agent generation as required by the
  formal P1/P2 feature-complete boundary.

Only after those code boundaries close does the final P1/P2 validation run the
complete affected automation/build, fixed-corpus ordinary/barge-in p50/p95,
broader device/network matrix, exact W3 real microphone/TTS Journey and
independent T2 review. Accordingly, “P1/P2 core functional development is
substantially closed” is valid for this bounded batch; “P1/P2 is complete and
only needs validation” is not.

## Evidence boundary and remaining work

The real Windows Chrome microphone/speaker result remains bound to exact source
`e1df8b4529b073beed21affffda952bdb8262fc8`; it was not rerun on the integrated
W3 source. That run grants scoped functional credit for audible short/long TTS,
automatic post-playout listening, foreground Stop and button/automatic
playout-time barge-in only.

The following remain open:

- mounted Exit/immediate-re-enable and low-level Exit resource closure;
- hands-free interruption while the Agent is still generating;
- P2 one-notification-per-RPC head-of-line latency repair;
- frozen-corpus ordinary/barge-in p50/p95 and broader device/network evidence;
- independent T2 review, the combined P3 Task physical journey and a new
  controlled-product candidate.

The original failed `f24dd17d` controlled-candidate result remains immutable.
This integration is source/automation/build evidence and does not upgrade it.
