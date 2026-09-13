# Demo profiling deployment and synthetic speech verification

## Scope recorded for this verification

The user requests deployment, one synthetic-speech run through the real Agent,
and inspection of whether the diagnostic evidence is sufficient before human
VAD validation. The deployed baseline is `5652e4c3bb9a7ce2f4fc3649d725c11762fd5c07`.
This is a bounded Observability verification, not product-candidate acceptance.

The first browser run exposed two passive-diagnostic gaps. The repair owns
`common/live_voice_audio_diagnostics.py`, `common/live_voice_profiling.py` and
`tests/unit_tests/live_voice/test_demo_profiling.py`: keep numeric JSON valid
through the existing log redactor, and carry typed Synthesis `ref.response`
identities into spans so exact Session filtering retains TTS. Tier 2 applies to
the observation/isolation boundary. Acceptance requires real-path re-verification,
parseable records, exact response joins, no foreign-session inclusion or content
export, unchanged tool/Task/file effects, and focused regression plus independent
review. No VAD, segmentation, buffering, model/provider, Task authority, logging
security policy or protocol changes are included.

Before the retest, inspection also found an HTTP observer ordering defect:
response-close start overwrote the response-body start, reporting 94 ms for a
body lifetime of about 1,172 ms. The same passive Tier 2 repair additionally owns
`server/live_voice/speech_http_diagnostics.py` and its existing
`test_speech_precision_diagnostics.py` oracles. Each bounded HTTP phase must keep
its own start time across nested/late completion, preserve missing-start truth,
ignore duplicate/unknown hooks and never inspect raw HTTP trace payloads.

Independent review required whole-number/long-uptime coverage as well as decimal
tails. Numeric serialization therefore also uses exact scientific JSON notation
when needed to split long digit runs; strings and the existing redactor remain
unchanged. The offline analyzer owns the corresponding normalization of integral
JSON numbers for sequence/drop counters. This adds only diagnostic encoding and
import to the same observation scope, with no business protocol/schema change.

## Initial run (baseline source)

The controlled `formal-web-validation` launcher passed preflight and deployment;
frontend port 6175 and the saved isolated project/configuration were retained.
The project's one existing untracked script was accepted as the preserved
baseline with `-AllowDirtyProject`; all 56 existing Tasks were terminal before
deployment. Generation-interruption configuration matched the previous runtime
contract. Provider/model credentials remained in place.

The launcher passed real TTS-to-STT, normal receipt, identity-mismatch rejection
and forged-claim rejection probes with zero business effects. The browser
harness injected Windows-synthesized PCM through getUserMedia into the formal
pipeline. The recognized first sentence requested an actual file-list tool;
the real Agent called `list_files`, answered and completed digital playback,
then returned to listening. This does not establish physical audibility or VAD
acceptance. Later sentences of the synthetic input did not become committed
speech; the existing segmentation boundary remains open.

The initial Session-filtered report retained 856 records and 132 spans but
discarded four malformed numeric records and omitted TTS coverage. Decimal
tails matched the existing log phone-number redactor, yielding invalid numeric
JSON. Synthesis identities lived under `ref.response`, which the observer did
not traverse. The initial evidence is retained in the ignored
`logs/profile-speech-20260904/` directory; it is not overwritten as a PASS.

## Repair and second-run verification

- The first run left all Task/command/event/result table counts unchanged and
  the complete project snapshot unchanged. The report had zero backend queue
  drops and zero browser memory/storage overwrite/failure counts. Its real
  error breadcrumbs included `SPEECH_PROVIDER_TURN_ORDER`, whole-capture
  fallback and the exact missing-stream cleanup source locations; these are
  retained as failure evidence, not relabeled as a clean recognition PASS.
- The initial two-fix regression selection passed 88 tests. The HTTP phase
  selection passed 16 tests. After the numeric-review finding, the combined
  diagnostic/HTTP selection passed 45 tests. The actual standard log filter,
  long-uptime and safe-integer bounds, same-unit/different-response isolation,
  interleaved HTTP close/body events, duplicate and unknown hooks, privacy,
  failure/cancel/fallback and real local HTTP hooks are covered. Fast synthetic
  unit stress can overflow the bounded observer and emits pytest teardown
  logger noise; this is distinct from the zero-drop real runtime sample.
- Independent review accepted the response traversal and HTTP repair. Its
  initial whole-number encoding finding is fixed. Numeric re-review found an
  oversized-integer import overflow; range validation now precedes conversion,
  with an actual oversized JSON-log import regression. The final diagnostic
  selection passed 26 tests after that guard correction; source/diff review
  confirms no change to business return/cancel paths. Review outputs are
  `logs/live-voice-profile-deployment-review.txt`,
  `logs/live-voice-profile-http-review.txt` and
  `logs/live-voice-profile-number-review.txt`; fixes are recorded here rather
  than rewriting their original findings. Final redeployment/retest is pending.

Verification commands and outputs are retained locally:

```text
python -m pytest tests/unit_tests/live_voice/test_demo_profiling.py tests/unit_tests/gateway/test_audio_diagnostics.py tests/unit_tests/gateway/test_streaming_synthesis_route.py tests/unit_tests/gateway/test_product_streaming_synthesis.py -q -o addopts='' -o log_cli=false -o asyncio_mode=auto
python -m pytest tests/unit_tests/live_voice/test_speech_precision_diagnostics.py -q -o addopts='' -o log_cli=false -o asyncio_mode=auto
python -m pytest tests/unit_tests/live_voice/test_demo_profiling.py tests/unit_tests/gateway/test_audio_diagnostics.py tests/unit_tests/live_voice/test_speech_precision_diagnostics.py -q -o addopts='' -o log_cli=false -o asyncio_mode=auto
```

Commands used the repository `.venv/Scripts/python.exe`; logs are
`logs/live-voice-profile-deployment-fix-tests.txt`,
`logs/live-voice-profile-http-phase-tests.txt` and
`logs/live-voice-profile-number-fix-tests.txt`. The last command resets pytest
defaults explicitly but preserves auto asyncio mode.

## Final deployed result

The repair commit `be6c91ce4014bd18436ebdbce52c27a5cbea5c0b` was cleanly
redeployed through the controlled launcher with the same saved project,
DeepSeek foreground/background model selection, OpenAI Speech configuration,
generation-interruption setting and four ports. The launcher again passed its
real TTS-to-STT and rejection probes with zero business effects. The managed
service remains available on `http://localhost:6175`; the owned headless test
browser was stopped.

A fresh 6.4-second Windows-synthesized utterance entered getUserMedia in a new
formal Session. The committed speech reached the real Agent, produced exact
`chat.tool_call` and `chat.tool_result` observations for `list_files`, generated
a spoken revision, produced non-silent TTS PCM, completed 375 digitally
scheduled/ended browser sources and returned to listening. There were 51
explicit silent output buffers and 324 non-silent output buffers. Task Store
counts, the complete project snapshot and both private configuration file hashes
remained identical to their pre-run values.

The exact Session report retains 551 records and 133 spans. All 13 coverage
categories are present except Task execution, which the read-only prompt did
not invoke. It contains 30 synthesis observations and paired first-audio,
Provider consumption and production spans. There are no import warnings,
malformed records, backend drops, browser memory overwrites, browser storage
overwrites or browser storage failures. The one open browser activation span
was exported while that final inactive-state request was still pending; the
report exposes it as `open_or_truncated` rather than inventing a duration.

Representative single-run durations are: recognition collection 6,517 ms
median / 7,093 ms maximum across rotating captures; semantic context and
resolution 1,160 ms; semantic model 908 ms; Agent round 3,854 ms; real
`list_files` 195 ms; synthesis first audio 951 ms; synthesis production 3,253
ms; TTS response headers 657 ms and body lifetime 1,109 ms; presentation ACK
118 ms. These are observations of one synthetic run, not SLO percentiles.

The report also retains the next-capture Provider transport failure and all
related cancellation/cleanup source locations, including
`SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE`, `RECOGNITION_STREAM_NOT_FOUND` and
`RECOGNITION_CANCEL_ALREADY_REQUESTED`. The product recovered to listening;
the evidence is sufficient to distinguish recognition/VAD, Agent/tool, TTS,
playout and cleanup timing during the user's next rehearsal. It does not resolve
the existing segmentation or physical-VAD questions and does not claim speaker
audibility.

Local evidence is retained in ignored directory
`logs/profile-speech-retest-20260904/`: `report/profile.html`, full
`report/profile.json`, Chrome `trace.json`, the browser export, safe
`verification.json`, synthetic input manifest and command/result screenshots.
No transcript, audio, credentials, Provider URL or private configuration was
added to Git.
