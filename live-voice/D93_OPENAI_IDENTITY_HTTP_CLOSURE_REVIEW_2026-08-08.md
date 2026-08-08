# OpenAI identity HTTP closure review

> Frozen source/review record for implementation commit `35d0c25074340c56ea0f9fddbb25b2227bd44d93` (`fix(live-voice): require identity speech responses`).
>
> This record does not award Replacement Ledger credit. Current progress and next action remain authoritative only in [STATUS](STATUS.md).

## Trigger and corrected contract

The second shortest real OpenAI probe used hidden local key input on the D92 candidate. It crossed the raw-PCM conversion boundary but failed before STT with HTTPX `DecodingError: Error -3 while decompressing data: incorrect header check`. The Adapter consumed `aiter_bytes()`, which had already decoded an encoded response, then rebuilt an `httpx.Response` with the stale `Content-Encoding` header and triggered a second decode. No key value was written to Git, evidence, logs or this record.

The initial correction retained decoded streaming and stripped stale headers. Independent D-053 review rejected that version: HTTPX decodes one raw chunk without an application-supplied output cap before `aiter_bytes()` can count it, leaving a decompression peak-memory risk, and corrupt compressed entities would be mapped as retriable network failures. That version was never committed.

## Implementation closure

- Every selected Provider request sends `Accept-Encoding: identity`.
- A successful response permits only a missing `Content-Encoding` header or one that normalizes exactly to `identity`.
- gzip, deflate, unknown and malformed encoded responses fail before body iteration as non-retriable `PROTOCOL_VIOLATION / SPEECH_PROVIDER_UNSUPPORTED_CONTENT_ENCODING`.
- The Adapter consumes `aiter_raw()` and enforces STT/TTS limits against actual identity response bytes, so HTTPX never invokes a content decoder.
- Rebuilt responses discard stale encoding, framing, length and representation-digest headers, retain safe metadata such as `Content-Type` and Provider request ID, and generate the correct new `Content-Length`.

Bounded compression support is intentionally not implemented for W2. A future production Adapter may add explicit incremental decoding only with an output cap, encoding whitelist, corrupt-stream error contract and resource tests.

## D-053 review closure

The implementation worker completed self-review. Main cold-reviewed the complete two-file diff against both real probe results, HTTPX 0.28.1 decoder/chunker behavior, the existing Provider error map and W2 fail-closed requirements. The first independent review reported one P1 and one P2, both fixed as described above. Final independent read-only review returned `PASS` with no P0-P3 finding.

Final verification:

- affected Batch Speech, Gateway Speech RPC and dedicated-media regression: `89 passed`;
- final Batch Speech suite: `47 passed`;
- identity/encoding/limit focused tests: `17 passed`;
- Ruff check and format check: pass;
- `git diff --check`: pass.

Tests cover identity STT/TTS, the outgoing identity request header, every stale rebuilt-body header, raw response limits, and gzip/deflate/corrupt-gzip rejection with zero body reads. Existing credentials, authorization, PCM canonicalization, rate conversion and Gateway media regressions remain green.

## Remaining real boundary

The first two probes are diagnostic only. A third hidden-key TTS→STT probe must pass against a new clean candidate containing this commit and its documentation closure. Real Chrome device capture/playout, physical-heard witness, DeepSeek Agent/Tool, direct P3alpha mutation, controlled faults, restart, consecutive showcases, signed artifact closure and strict Gate import remain open.
