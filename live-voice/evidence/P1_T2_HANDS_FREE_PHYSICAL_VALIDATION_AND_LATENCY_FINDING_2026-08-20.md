# P1/P2-T2 hands-free physical validation and latency finding — 2026-08-20

## Scope and tested source

- Exact source: clean `hx/0819_live_voice_p1p2` at
  `e1df8b4529b073beed21affffda952bdb8262fc8`, locally three commits ahead of
  its configured upstream during the run.
- Source under test composed the successor-capture ACK decoupling
  (`874cf327c`), post-playout receipt decoupling (`35cae3d9a`) and formal
  hands-free control exposure (`e1df8b452`).
- Real boundary: desktop Windows Chrome on `localhost`, with a real microphone
  and speaker/headset. The user, not a browser receipt alone, confirmed
  audibility. Machine-private runtime data and the raw local log remain outside
  Git; the sanitized log label is `swarm-20260820-215741.log`.
- This is scoped P1/P2 physical evidence. It does not rerun the combined P3
  Task journey, close the feature-complete latency targets, supply an
  independent Tier-3 source review or upgrade the immutable failed
  `f24dd17d` controlled-candidate result.

## Human journey and functional result

The user completed the prepared short, repeated, long and multi-turn prompts,
then explicitly confirmed the formal hands-free controls:

- short and long Agent responses were physically audible and completed without
  `AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED`, `PRODUCT_TTS_PLAYBACK_FAILED` or a
  visible recovery failure;
- listening resumed after playout and admitted subsequent questions;
- the explicit Stop control stopped the foreground response;
- the explicit interrupt-and-speak control worked;
- speech during playout automatically interrupted without using the button;
- the tested rapid/repeated turns did not visibly replay an old response; and
- the user-visible Exit journey stopped the active Live Voice experience.

The scoped functional result is **PASS** for audible playout, automatic
post-playout listening, foreground Stop and playout-time button/automatic
barge-in. Hands-free speech while the Agent is still generating cannot yet
interrupt or replace that response and remains separately recorded follow-up
work. Low-level Exit resource closure and broader device/network coverage retain
their existing automated/cumulative acceptance owners.

## Measured latency finding

One automatic-barge-in turn for a short capital-city question produced this
sanitized timeline:

```text
22:16:53.328  playback-time barge-in observed; predecessor playout stopped
22:16:56.551  Provider EOT observed
22:16:57.220  formal unified Agent submit sent
22:16:57.900  main streaming model request started
~22:17:00.899 main model response completed
22:17:06.457  browser presented the final Agent text
22:17:07.912  successor capture media connection opened
22:17:08.140  TTS downlink media connection opened
```

The page-visible submit-to-final interval was 9.237 seconds: about 0.680 seconds
of admission/setup, about 2.999 seconds in the main model and about 5.558
seconds after model completion before final presentation. The text-to-TTS
downlink interval was another 1.683 seconds and is outside the page's Agent
duration.

### Input finalization

Both ordinary hands-free capture and playback-time barge-in use server VAD with
`silence_duration_ms=1_200`. Barge-in retains 800 ms of speech prefix instead
of the ordinary 300 ms; prefix retention is not an additional fixed wait. The
observed EOT-to-submit interval was 0.669 seconds. That recognition/Gateway
finalization interval is not proven to be barge-in-specific and requires a
fixed-corpus ordinary-versus-barge-in p50/p95 comparison before optimization
credit.

### P2 notification head-of-line delay

The formal Web owner issues one `live_voice.composition.p2.notification.next`
operation at a time, and the product-composition server returns one canonical
notification per operation. During the measured turn:

- notification sequence advanced from 596 to 685 between submit and final;
- the median local serial notification round trip was about 85 ms;
- model completion coincided with sequence 621, leaving 64 subsequent sequence
  intervals before the final presentation notification; and
- those intervals consumed about 5.52 seconds, accounting for the otherwise
  unexplained post-model delay.

This is a variable backlog, not a fixed 5.5-second timeout. Notifications can
be consumed while the model is generating; only the notifications still ahead
of the retained final contribute tail delay. Other turns in the same run issued
82–156 notification operations and showed page-visible durations of 8.17–15.09
seconds. A pre-control-exposure physical turn had already taken 8.59 seconds
while advancing sequence 9 to 84 with the same approximately 85 ms median
round trip. The P2 head-of-line mechanism therefore predates and is not caused
by automatic barge-in.

The previously observed 1.26-second turn has no retained matching server trace.
Fewer/coalesced events or consumption that kept pace with generation is a
mechanically consistent explanation, but no exact notification count or causal
credit is claimed for that turn.

## Disposition and next owner

- **Functional P1/P2 physical scope:** PASS on the exact source and environment
  above.
- **Latency/product completion:** PARTIAL. The run is not a fixed-corpus p50/p95
  benchmark and does not meet a declared feature-complete latency target.
- **Priority:** first remove the P2 one-notification-per-round-trip bottleneck;
  then evaluate VAD finalization with pause/truncation oracles; then reduce
  text-to-first-audio startup.
- A P2 batch, push or non-critical event-coalescing change crosses the shared
  product protocol/runtime boundary. Before implementation it requires an
  explicit Tier-3 scope/risk checkpoint, preservation of retained final/error/
  Task truth and ordering, and zero duplicate Agent/Tool/Task/audio/history or
  stale-generation effects.
- VAD tuning must compare ordinary and barge-in captures over a frozen corpus
  with natural pauses, background noise and p50/p95/failure counts. A lower
  threshold cannot receive credit if it clips or splits valid speech.
