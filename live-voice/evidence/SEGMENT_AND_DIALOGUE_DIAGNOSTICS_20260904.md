# Segmented Speech and dialogue mismatch repair — 2026-09-04

## Authorized scope and design checkpoint

Baseline: `c34ea4e007f4812c0306e7caa9428c181f09550f`. The user authorized
bounded repairs, correlated diagnostics, tests and local redeployment before
resuming VAD acceptance. Preserve private model/configuration/project/data,
VAD 800 ms and playout startup 250 ms. No remote update.

The 17:14 reproduction committed the correct weekend question but persisted a
new greeting answer. Semantic input/routing are correct; the actual dialogue
model messages were not recorded. Do not infer a confirmed model/context bug.
The 17:15 capture received stop, commit, then a different-item start. The
single-item adapter rejected that start; whole-capture batch fallback uploaded
successfully and exhausted its 15 s deadline waiting for response headers.

Owned initial increment: Agent adapter model-boundary diagnostics and Speech
batch request/response diagnostics (Tier 2: passive concurrent/cancel-sensitive
observation). Tests own payload preservation, bounded content-free correlation,
failure/cancel, restoration and isolation, plus affected adapter/Speech paths.
Record current committed-envelope presence at the actual model boundary and
whether generated output repeats selected historical assistant content. Never
log prompts, transcripts, raw audio, credentials, URLs or response headers.
Diagnostics cannot classify or authorize Agent/Tool/Task behavior.

The existing recognition contract is one capture/one final. Its browser stops
capture on the first provider EOT and retains the whole capture for batch
fallback. Merely ignoring a later item can silently lose a correction; merging
provider items or creating successor turns would change that contract. The
split-versus-merge product choice is requested before expanding this repair.
No speculative timeout increase, history reset, model change, extra model
invocation, transcript concatenation or ignored speech item is authorized by
this initial increment. Continue unblocked diagnostics while this is resolved.

Verification follows root TESTING.md: P/N/B/S/T/C/R/I/F/K and the actual model
call/HTTP adapter seam X. Persisted schema/migration and Task mutation are
excluded. Physical microphone, model-quality and Provider latency acceptance
remain open; independent review limitations must be recorded, not waived.

## Execution evidence

The coherent increment is diagnostic-only; it deliberately retains the old
failure/fallback behavior instead of losing later speech. No segmentation,
wrong-answer or timeout fix is claimed. The observer is installed on an
execution-private Model client; original cached settings/model are restored by
the existing formal lifetime. At most 16 calls and 256 messages/1,000,000 text
characters per observation are inspected; unknown shapes/bounds are marked
incomplete. Request IDs correlate with the existing formal execution. Only
counts, elapsed times and equality booleans are exported, not content hashes.
An exact serialized envelope match proves its presence; absence does not by
itself rule out a differently serialized equivalent request. History equality
does not prove why the model repeated an answer.

Final affected regression: **416 passed, 1 warning in 33.17 s**:

```text
.venv/Scripts/python.exe -m pytest
tests/unit_tests/agentserver/test_formal_model_diagnostics.py
tests/unit_tests/agentserver/test_formal_live_voice_adapter.py
tests/unit_tests/live_voice/test_speech_socket_diagnostics.py
tests/unit_tests/live_voice/test_speech_precision_diagnostics.py
tests/unit_tests/gateway/test_audio_diagnostics.py
tests/unit_tests/live_voice/test_openai_streaming_speech.py
tests/unit_tests/live_voice/test_openai_realtime_session.py
tests/unit_tests/live_voice/test_batch_speech.py
tests/unit_tests/gateway/test_streaming_speech_route.py
tests/unit_tests/gateway/test_dedicated_media_registration.py
tests/unit_tests/live_voice/test_speech_lifecycle.py
tests/unit_tests/live_voice/test_generation_time_interruption.py
-q -o addopts='' -o log_cli=false --disable-warnings --tb=short
```

Tests cover unchanged invocation/stream arguments and returned objects, output
chunks, failure/cancel/early-close, unsupported close interfaces, installed Model
invoke/stream seams with fake transport, per-execution isolation, bounded and
throwing diagnostics, multipart byte identity and exact WAV duration, plus the
post-commit different-item fail-closed/zero-business-effect boundary. No real
dialogue-model or microphone invocation is claimed. New-module Ruff, complete
manual scoped diff review and changed Markdown links pass; no tracked duplicate
exists under `docs/zh/live-voice/`.

Independent `codex -c service_tier=fast review --uncommitted` exits 1: CLI
0.111.0 cannot use the configured model and has incompatible model/state
metadata. No global tool/configuration change. Manual review is a substitute,
not independent review credit; Tier 2 review closure remains PARTIAL.

Before deployment: read-only Gateway/project query succeeds for `proj_ad135a77`,
six Sessions and two Tasks. SQLite has two terminal Tasks and two terminal
Attempts. Default remains `deepseek-v4-flash`; configuration SHA-256 remains
`7017784bbf44dcf1fc1432fb91df05dc004f0dd1dd08b2dd1fb2628f68a22c57`.

## Controlled local deployment

Runtime source: `f76fde5199` (`feat(live-voice): correlate dialogue input and
segmented speech diagnostics`), clean at launch. Existing private helper and
controlled `formal-web-validation` launcher ran preflight then restart with
process-only offline npm settings. TypeScript/Vite build passes (Vite 39.16 s);
existing mixed-import/chunk-size warnings remain. No frontend behavior changed.

New runtime log: `logs/swarm-20260904-174219.log`, parent PID 3448. The old
`swarm-20260904-164927.log` remains. All four fixed ports and formal backend
routes pass readiness. Required real TTS-to-STT, receipt, identity-mismatch and
forged-claim rejection checks pass with zero business effects. The short batch
readiness STT receives HTTP 200 in about 875 ms; this is not proof that the earlier
long-capture timeout or streaming segmentation failure is solved.

The original Session URL returns HTTP 200 and served
`/assets/index-DsZyj0lX.js` equals the rebuilt local bundle. Its effective bundled
`VITE_LIVE_VOICE_PLAYOUT_STARTUP_LEAD_MS` is `250`; runtime environments retain
VAD `800` and exact private data/configuration paths. The dialogue model and
configuration hash are unchanged. Read-only Gateway/project verification still
finds six Sessions and two Tasks; SQLite retains two terminal Tasks and two
terminal Attempts. No browser refresh, microphone operation, dialogue-model
probe, Task mutation, data cleanup or remote update was performed.

This deployment enables evidence collection, not VAD acceptance closure. The
lossless split-versus-merge choice/successor capture scope remains awaiting user
direction; wrong-answer causality and long-capture Provider timeout still need
new correlated evidence. Independent review remains unavailable as recorded.
