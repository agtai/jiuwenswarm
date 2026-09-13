# L0 warm steady-state closure evidence — 2026-08-25

## Source, runtime and accepted scope

- Behaviour source: `ba06d9825c92602066756118dd5cac9572c22827` on
  `hx/0812_live_voice_w3`, clean at deployment. A later documentation-only
  amend changes no product, test or deployed bundle source.
- Runtime: `formal-web-validation`, fixed ports 5173/18092/19000/19001,
  disposable no-remote project, configured OpenAI-compatible Speech and the
  real JiuwenSwarm Agent path. Launcher TTS→STT, critical-receipt,
  identity-mismatch and forged-claim probes passed with zero business side
  effect.
- Browser: one ordinary installed Google Chrome page, not an isolated profile;
  managed isolated Chrome process count was `0`. One user gesture unlocked the
  in-memory prerecorded WebAudio fixtures and normal product playout.
- Measurement identity: environment
  `ordinary-chrome-machine-current`, fixed corpus SHA-256
  `a51a17289edf1dbcd83da66526d2175e2f84c516240d585e9a78b814551e99d6`
  and exact source/configuration/epoch labels. Raw audio, recognized text,
  prompts, credentials and device identity were not retained.
- Accepted closure: [D-097](../decisions/DECISIONS.md) makes this warm
  steady-state result, together with the earlier ordinary-Chrome 8/8 basic
  journey and authoritative post-repair terminal barge evidence, sufficient
  for bounded D-095 L0 closure. Cold and cold-minus-warm are explicitly later
  performance work.

The ignored local runtime directory and logs remain machine-local. This record
contains only sanitized counts, timings, classifications and stable reason
tokens.

## Warm automatic result

The run completed one non-counted warm-up, then 20 first-audio and 20 dedicated
barge-in attempts:

| Metric | Attempts | Eligible | Failure | Drop | Classification |
|---|---:|---:|---:|---:|---|
| First audio | 20 | 20 | 0 | 0 | `success=20` |
| Dedicated barge-in | 20 | 20 | 0 | 0 | `cancelled=20` |

`cancelled` is the successful expected outcome for the interrupted-response
rounds. Browser evidence contains 380 records with zero dropped records. The
cross-layer aggregate declares 40 exact rounds and accepts 860 correlated
Browser/Gateway/Runtime/Agent records with zero capacity rejection, conflicting
record or identity-isolation contamination. It observes 40 stale-generation
discard events, 20 barge requests and 20 exact fence-cancel terminals.

## Sanitized latency baseline

All percentiles below have 20 eligible samples:

| Span | p50 | p95 |
|---|---:|---:|
| Speech end → STT final | 411.521 ms | 783.687 ms |
| Speech end → committed Agent submit | 584.913 ms | 941.540 ms |
| Agent request → first delta | 2070.228 ms | 2691.110 ms |
| Agent request → first stable speakable sentence | 2116.683 ms | 2723.019 ms |
| Agent request → chat final | 2121.683 ms | 2728.014 ms |
| TTS request → Provider first audio | 761.151 ms | 1014.314 ms |
| Speech end → WebAudio actually started | 4834.362 ms | 5603.215 ms |
| Speech end → playout completed | 8587.362 ms | 9557.729 ms |
| Barge request → Browser fence-cancel terminal | 0.0 ms | 0.0 ms |

The last report values are rounded from millisecond-resolution wall-clock
timestamps. The same exact Browser records' monotonic clock gives p50 about
`0.1 ms`, p95 about `0.3 ms` and maximum about `0.3 ms`. This is local digital
fence completion, not physical speaker silence or Provider cancel ACK.

No latency threshold was frozen before the run. These percentiles are an
accepted warm baseline and diagnostic decomposition, not a claim that a
feature-complete or release SLO passed.

## Cancel repair and runtime log review

The warm runtime log contains:

- `STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED`: `0`;
- `live_voice_speech_transport_cleanup_incomplete`: `0`;
- `live_voice_speech_transport_cleanup_deferred`: `13` INFO observations;
- one `recognition.stream` degradation with stable reason
  `STREAMING_SPEECH_PROVIDER_UNAVAILABLE`.

The deferred cleanup observations retain owned SSE/socket cleanup after the
local fence has completed and are not ERROR or visible degradation. The one STT
Provider-unavailable event was not correlated to an eligible sample; a new
media connection opened about 0.18 seconds after the degradation record and the
final measured round later completed. It therefore remains a separately
recorded reliability anomaly and prevents a zero-anomaly claim, but does not
invalidate the 40 exact eligible samples.

The initial warm launcher log also contains three
`PRODUCT_P2_ROUTE_NOT_FOUND` results from a pre-existing page attempting to
close its stale P2 activation during the hot deployment window. The new
activation subsequently returned `e2a.complete`; these startup close attempts
are not measured-round failures.

## Cold attempt and honest report boundary

After warm completion the supervisor created one cold coordinator epoch, but
the Browser controller had already interpreted the warm profile's
`batch_complete` as whole-series completion. The cold session remained
`epoch_attempted=false`, produced zero Browser records and no epoch completion
marker. The operator stopped the sequence; no cold sample receives credit.

The raw `live-voice.l0-d095-report.v1` consequently remains `complete=false`
under the superseded D-095/D-096 two-temperature contract. It was not edited or
renamed. D-097 explicitly closes only the warm steady-state L0 boundary and
records cold orchestration/performance as deferred work.

## Verification inherited by the behaviour source

- OpenAI Speech Adapter, Gateway synthesis route and Product synthesis:
  `129 passed`.
- L0 coordinator, Conversation Runtime and focused Product P2: `52 passed`.
- Integrated Web strict TypeScript plus `479/479 passed`.
- Ordinary-Chrome batch and Browser L0: `5/5 + 5/5 passed`.
- Browser Audio I/O/processor: `105/105 passed`.
- Production Live Voice build, Ruff, compileall and Git whitespace checks:
  PASS.

## Disposition

**PASS — BOUNDED D-095 L0 WARM STEADY-STATE CLOSURE UNDER D-097.** The result
proves the ordinary-Chrome warm digital path, exact first-audio correlation and
playout-time fence cancellation at the declared sample size. Combined with the
existing 8/8 ordinary-Chrome basic journey and the authoritative
button/voice/Stop+Exit rerun, the L0 closeout is complete at this bounded scope.

It grants no cold-start or cold-minus-warm result, per-round physical
audibility/silence, acoustic p95, AEC/double-talk, formal background-Task or
recovery repair, generation-time interruption, feature-complete,
product-readiness, release or Production credit.
