# OpenAI PCM Provider-boundary closure review

> Frozen source/review record for implementation commit `5e460589c6e448fd4153fb01731cd5967c80178d` (`fix(live-voice): canonicalize OpenAI PCM speech`).
>
> This record does not award Replacement Ledger credit. Current progress and next action remain authoritative only in [STATUS](STATUS.md).

## Trigger and corrected contract

The first shortest real OpenAI probe used hidden local key input and reached `/audio/speech` with the D-064 model and voice. The Provider returned audio, but the pre-fix Adapter rejected it as `SPEECH_PROVIDER_INVALID_WAV` because it expected one complete RIFF/WAVE payload. STT did not run after that fail-closed TTS result. No key value was written to Git, evidence, logs or this record.

The probe invalidated only D91's assumption about the selected Provider response shape. OpenAI documents `response_format=pcm` as raw 24 kHz, 16-bit signed little-endian samples without a header. D91 remains an immutable historical review of its own commit; this record supersedes its Provider-WAV and same-rate-byte wording for the current OpenAI Adapter. The governing external contract is the [OpenAI Text-to-Speech output-format documentation](https://developers.openai.com/api/docs/guides/text-to-speech#supported-output-formats).

## Implementation closure

- The selected Adapter requests `response_format=pcm` and interprets only the documented raw 24 kHz mono PCM16 little-endian contract.
- It rejects empty, odd-byte and oversized Provider responses before they cross the Adapter boundary.
- It writes one deterministic 44-byte canonical RIFF/WAVE header, retaining the 8 MiB final package bound.
- Same-rate output preserves PCM samples in canonical WAV form. Different-rate output uses the already declared deterministic integer `server_linear_pcm16_mono` conversion and is re-inspected before return.
- Target output capacity is checked before resampling allocation. Provider HTTP streaming stops once the raw response bound is exceeded.
- Other Speech Providers do not inherit the OpenAI format assumption; they require their own reviewed Adapter contract.

## D-053 review closure

The implementation worker completed self-review. Main then cold-reviewed the complete two-file diff against the real probe, the official PCM contract, existing response/error behavior, capacity arithmetic and the original W2 request. An independent read-only review returned `PASS` with no P0-P2 findings. Its P3 suggestion to retain downsampling and true one-sample boundary coverage was added before commit; this test-only fix did not change semantics.

Verification after the implementation change:

- affected Batch Speech, Gateway Speech RPC and dedicated-media regression: `82 passed`;
- final Batch Speech suite after review fixes: `42 passed`;
- independent focused run before the P3 additions: `40 passed`;
- Ruff check and format check: pass;
- `git diff --check`: pass.

The positive Adapter route, raw-to-canonical conversion, 24→48 kHz upsampling, 24→16 kHz downsampling, one-sample input, exact raw limit, resampled-output limit, empty/odd/oversized negative cases and existing Gateway authorization regressions are covered. No unresolved P0-P3 review finding remains.

## Remaining real boundary

The failed first probe is diagnostic evidence only. A new shortest hidden-key TTS→STT probe must pass against a clean candidate containing this commit and its documentation closure. The cumulative Chrome device journey, physical-heard witness, real DeepSeek Agent/Tool, direct P3alpha mutation, faults, restart, closed signed artifacts and strict Gate import remain open; none can be inferred from this code or the first probe.
