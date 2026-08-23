# P1/P2 Exit/immediate-re-enable lifecycle evidence

## Boundary and final disposition

- Date: 2026-08-22; consolidated 2026-08-23
- Baseline: `2e01965ecd89a33ca5917cdad1c1080018bb8b1b`
- Consolidated implementation:
  `1fec48027` (`fix(live-voice): decouple retained ACK from successor`)
- Risk: Tier 3 under root `TESTING.md`
- Gate: **PASS — `C0 / I0 / M0`**
- Scoped physical source:
  `8994489ba79db18ccdde16593dd44d61450697af`
- Physical credit: text/tool, ordinary voice, Exit/immediate re-enable,
  Session isolation and resource zero/re-establishment PASS; Exit/immediate
  re-enable repeated on the exact consolidated product/test tree

This boundary owns foreground presentation/capture fencing, exact P2
predecessor retirement and durable background settlement of old presentation
ACKs. It does not change Provider/media wire protocols, shared schema,
Agent/Tool/Task policy, P2 latency or generation-time Agent cancellation.

## Root cause and final lifecycle

Exit must withdraw all unpresented predecessor authority immediately. An
accepted predecessor Agent turn may finish once under retained Runtime cleanup,
but a successor generation may present only its own response.

The original foreground recovery path still treated an unresolved predecessor
presentation ACK as a blocking current operation. Exit/re-enable could
therefore wait for, retry through or be polluted by that old settlement. The
final lifecycle separates current-generation recovery from durable old-ACK
settlement:

- Exit synchronously increments/fences the voice-loop generation, clears
  predecessor presentation/capture authority and starts exact cleanup;
- generation 2 may activate, open media and capture before generation 1's ACK
  settles;
- before predecessor reconciliation, an unresolved presentation ACK moves from
  the blocking operation slot into a bounded v3 retired ledger;
- the retired record preserves exact Session/journal/route, method, request id
  and closed params;
- a background drainer replays the same request id and never owns current P2
  activation recovery;
- success, authoritative `accepted: false`, route-not-found or definitive
  rejection removes only that retired record;
- timeout/unknown keeps the record for exact replay and cannot publish old
  text/recovery state;
- a live original transport is marked in flight, preventing parallel replay;
  its `finally` releases only its exact owner/request and wakes the drainer;
- retirement is authorized by durable journal identity, not by the presence of
  a transient Promise;
- overlapping retirement transfers one same-identity retry wake to the current
  drainer epoch, preventing a lost wake while the previous epoch holds the Web
  Lock;
- Session, route, journal, connectivity and unmount changes remain fail-closed;
  and
- the retired ledger is bounded at 16 and never evicts unresolved authority.

Notification adoption captures the poll generation and exact foreground
response fence. Exit generation change, pending P2 refresh or cleanup rejects a
predecessor before UI, assistant history, TTS, audio or ACK. Text-only P2
presentation remains available when no foreground voice fence exists.

## Retained exact fences and removed residue

`PendingForegroundPresentationFence` retains exact Session, correlation,
interaction, activation id/generation and response id/generation. Capture
barriers, timers, P2 refresh fencing and complete resource cleanup remain.

The consolidated repair removes unread `turn_id`, `commit_id`,
`origin_voice_loop_generation` and the unreachable
`crossesExitedVoiceLoopGeneration` branch. Static and mounted oracles enforce
both the retained fields and removed residue.

## Review closure

| Review HEAD | Result | Finding | Closed at |
|---|---|---|---|
| `ee2e24249843669796de27bf1d74fd08a774658e` | FAIL `C0/I2/M0` | timeout left a false in-flight ACK owner; cleanup-window predecessor notification could reach UI/history/TTS/ACK | `8116cb5420c4ddce57b11ce6e26a222543e4a8fe` |
| `8116cb5420c4ddce57b11ce6e26a222543e4a8fe` | FAIL `C0/I1/M0` | ACK timeout before P1 cleanup completion could miss retirement and re-enter foreground settlement | `09df81a07a122a867389006fafd1d4303a94f0c6` |
| `09df81a07a122a867389006fafd1d4303a94f0c6` | FAIL `C0/I2/M0` | overlapping retirement could lose its wake; live original-transport branch lacked a mutation-sensitive oracle | `a640ce97e78173a7f7764ccec29efd4db014c892` |
| `a640ce97e78173a7f7764ccec29efd4db014c892` | PASS `C0/I0/M0` | no finding; durable wake transfer and live-transport singleflight accepted | — |

The final review froze this production boundary and required no further
review-driven refactor.

## Automated evidence

Mounted production Panel journeys cover:

- generation-2 activation/media/capture before old ACK release;
- ACK success, `accepted: false`, rejection, timeout and route-not-found;
- refresh and same-tab Session isolation;
- timeout inside held `AudioContext.close()`;
- original transport in flight across Exit with zero parallel replay;
- overlapping retired ACKs while the first drainer holds the Web Lock;
- same-request-id recovery, ledger zero and zero stale UI/reason/diagnostic;
- zero predecessor UI/history/TTS/audio/ACK inside the cleanup window; and
- balanced microphone, AudioContext, AudioWorklet and socket resources.

```text
npm run test:live-voice-integrated-web
466 passed, 0 failed on the rewritten consolidated product/test tree

npm run test:live-voice-browser-audio-io
103 passed, 0 failed

npm run test:live-voice-browser-dedicated-media
27 passed, 0 failed

node --test tests/liveVoiceBuildProfiles.test.mjs
2 passed, 0 failed

npx tsc --noEmit
PASS

npm run build:live-voice
PASS

ruff check (affected P2/Registry product/test files)
PASS
```

The independently rerun combined P2/Registry result is disclosed as `214/220`, not
called PASS. Its six failures remain unrelated P3 fixture/projection cases and
no Python product/test file changed in this consolidated frontend packet.
Existing duplicate-locale, mixed-import and chunk-size warnings remain
non-findings.

## Physical evidence and non-claims

On exact clean product source
`8994489ba79db18ccdde16593dd44d61450697af`, using the controlled
`formal-web-validation` profile, the user passed:

1. real text input through JiuwenSwarm Agent/tool execution;
2. one ordinary microphone recognition/answer/playout/listen cycle;
3. Exit during an active response followed by immediate re-enable, with an
   immediately usable successor and no old audio/response revival;
4. Session switching with zero late visible/audio/state contamination; and
5. Exit resource zero followed by one clean re-established cycle.

The physical run did not inject ACK transport outcomes. Delayed ACK
success/rejection/timeout/route-not-found, refresh and overlapping drainer
schedules remain automation-owned. The scoped PASS does not claim complete
P1/P2, P3-9, controlled-candidate, product-readiness or production readiness.

The 2026-08-23 final run on deployed docs HEAD `56290ba444` repeated an active
response Exit followed by immediate re-enable. The successor recognized and
played one fresh response without old response/audio revival. Across the full
journey the runtime recorded seven committed submissions and seven presentation
ACKs, with zero `REQUEST_TIMEOUT`, `REQUEST_ABORTED` or recovery-failure event.
The final evidence-only amend changes no deployed product/test file.
