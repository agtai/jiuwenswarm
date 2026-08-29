# OpenAI Realtime Native post-review ordinary-Chrome evidence — 2026-08-29

## Disposition

Scope marker `306894062` passes the bounded ordinary installed-Chrome,
prerecorded foreground Gate on exact implementation commit
`268c806340f8a64418fdf2ab8946d7f73a681014`.

The run completed one non-counted warm-up, `20/20` first-audio scenarios and
`20/20` barge-in scenarios through `openai-realtime-native` with
`gpt-realtime-2.1-mini`. It exercised the reviewed Provider item-local
truncate-cursor repair through the real Gateway, Runtime, dedicated media and
Browser Audio I/O path. It invoked no Agent, Tool or background Task journey.

This is a scoped digital Gate, not physical-device, human-acoustic,
Production, deployment or complete-product evidence. A fixed prerecorded
Chinese corpus was injected into the real Browser capture stream; microphone
selection, speaker audibility, AEC, room acoustics and human semantic
acceptance remain unclaimed.

## Run identity and result

- Source: `268c806340f8a64418fdf2ab8946d7f73a681014`.
- Branch: `codex/openai-realtime-native-interaction-engine`.
- Private run ID: `09b1f8fc35f44ff3aae02e561d224066`.
- Browser: ordinary installed Chrome at `http://127.0.0.1:15174`.
- Session: `web_1a0399e691e_30659d6c1fcd`.
- Project: `proj_6c08b47d`, a registered isolated Code project.
- Stimulus: prerecorded Web Audio injected into the real capture stream.
- Background Task validation: excluded.

| Gate | Result |
| --- | ---: |
| Non-counted warm-up | complete |
| Eligible first-audio scenarios | 20/20 |
| Eligible barge-in scenarios | 20/20 |
| Browser-complete attempts | 40 |
| Fail-closed retried attempts | 1 |
| Browser dropped records | 0 |
| Accepted correlated Browser records | 259 |

All 40 eligible attempts were Browser-complete. One additional barge-in
attempt failed before retaining a Browser record, was not credited, and was
retried through the same coordinator truth. The completed evidence therefore
does not claim a zero-anomaly run.

## Browser latency

First-audio uses the Browser monotonic interval from `browser_eot_receipt` to
`webaudio_actually_started`. Percentiles use the same nearest-rank calculation
as the accepted Cascade warm baseline.

| Path | n | p50 | p95 | min | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| OpenAI Realtime Native | 20 | 2468.167 ms | 3057.833 ms | 2228.867 ms | 3412.333 ms |
| Cascade accepted warm baseline | 20 | 4834.362 ms | 5603.215 ms | — | — |
| Realtime minus Cascade | — | -2366.195 ms | -2545.382 ms | — | — |
| Reduction | — | 48.95% | 45.43% | — | — |

The Browser `barge_in` to `fence_cancel_completion` monotonic interval was
`n=20`, p50/p95 `0.100/0.100 ms`, min `0.000 ms` and max `0.400 ms`.
These Browser facts do not claim the instant at which sound became physically
audible or inaudible.

## Disclosed recovered anomaly

After the fourteenth credited barge-in, one stochastic successor response
continued beyond the Runtime's explicit 4,096-record active-response audio
ledger, equivalent to about 81.92 seconds at one 20 ms observation per record.
The Runtime rejected the next batch as `NATIVE_AUDIO_LEDGER_FULL`; dedicated
media then closed the old session and a trailing uplink frame was rejected as
`MEDIA_NATIVE_INPUT_FENCE_REJECTED (session_closed)`. The Browser attempt
timed out after 120 seconds with zero retained records and received no credit.

The product then acquired activation generation 3, resumed from coordinator
truth and completed the remaining six barge-in scenarios. There were zero
`NATIVE_CANCEL_CURSOR_AHEAD`, zero `NATIVE_BARGE_CURSOR_AHEAD`, zero
`MEDIA_CONSUMER_FAILED` and zero
`MEDIA_NATIVE_STREAM_BACKPRESSURE_TIMEOUT` occurrences. The 4,096-record
limit is an intentional bounded replay/conflict-detection policy. Increasing
it or adding a new response-length policy would exceed this repair packet, so
the recovered event is disclosed instead of being hidden by another clean
run.

A separate activation-response conflict occurred while the validation page
was deliberately reloaded to add the missing measurement query flag. It
failed closed, preceded the counted batch and is harness navigation evidence,
not a counted foreground scenario.

## Authority and isolation checks

The isolated formal Task database retained zero rows in `tasks`, `attempts`,
`commands`, `task_events`, `task_results`, `outbox`,
`current_background_tasks`, executor-event and durability tables. Unified
committed-input and foreground-effect tables also remained empty. Only the
expected P2 response-generation high-water sidecar advanced; no Task or
background authority was exercised.

After cleanup, validation ports `9235`, `15174`, `28093`, `29002` and `29003`
were closed. The separate W3 listeners stayed unchanged: `18092` remained on
PID `21960`, and `19000` plus `19001` remained on PID `14308`.

Raw Browser records, service logs, fixtures, runtime databases and launcher
state remain ignored private artifacts. No credential, transcript or raw audio
is committed in this evidence.

