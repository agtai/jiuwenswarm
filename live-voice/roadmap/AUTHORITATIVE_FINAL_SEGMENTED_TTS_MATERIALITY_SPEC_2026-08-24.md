# LVL-10 authoritative-final chunked-TTS materiality specification

> Date: 2026-08-24
>
> Status: **PROSPECTIVE SPECIFICATION — NO IMPLEMENTATION OR NUMERIC CREDIT.**
> This specification freezes the Provider-only causal screen that must pass
> before any product wiring. Current product judgement remains in
> [STATUS](../STATUS.md); historical experiment state remains in the
> [latency catalog](../evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md).

## 1. Decision question

Does bounded segmentation of one already committed, immutable `chat.final`
make usable ordered PCM available materially earlier than the current
one-request full-final SSE route, without adding unacceptable completion,
continuity, request-count, failure or authority regressions?

LVL-10 is not the rejected LVL-07 stable-sentence experiment. LVL-07 attempted
to find speakable text before the Agent final. LVL-10 receives the complete
authoritative final first and changes only the Provider request grouping used
by a benchmark-only runner.

### 1.1 What “chunked TTS” means in LVL-10

The candidate **divides the authoritative final text into multiple text
chunks and sends one independent streaming TTS Provider request per chunk**.
It does not merely divide the PCM returned by one request into smaller audio
frames; the current SSE path already does that.

The before/after distinction is:

```text
A1/A2 — current full-final TTS

committed chat.final
        -> one complete spoken_text
        -> one /audio/speech SSE request
        -> Provider audio deltas
        -> one ordered PCM stream

B — chunked TTS candidate

committed chat.final
        -> exact text chunk 0 + chunk 1 + ... + chunk n
        -> one /audio/speech SSE request for each text chunk
        -> per-chunk Provider audio deltas and bounded PCM buffers
        -> chunk 0 PCM, then chunk 1 PCM, ... released as one logical utterance
```

Chunk 0 synthesis starts without waiting for later chunks to finish. While
chunk 0 is being produced or released, the runner may prefetch exactly one
successor request. PCM from a successor can be buffered early but cannot cross
the ordered-release boundary. All chunks are derived only after the complete
`chat.final`; LVL-10 never speaks a provisional Agent prefix.

Terminology in this specification is exact:

- **text chunk:** one immutable slice of the committed `spoken_text` and one
  Provider TTS request;
- **Provider audio delta:** an SSE `speech.audio.delta` belonging to exactly
  one text chunk;
- **ordered PCM stream:** the concatenated chunk outputs exposed to the
  downstream consumer in original text order;
- **segment:** synonym for text chunk only where existing LVL-10 documents use
  the earlier “segmented TTS” name.

## 2. Current implementation fact and rationale

`OpenAIStreamingSpeechProvider` already submits the complete `spoken_text` to
`/audio/speech` with `stream_format=sse`, converts every
`speech.audio.delta` to ordered PCM frames and exposes those frames before the
whole utterance completes. A shorter first request might reduce Provider text
preprocessing and first-PCM delay. Conversely, segmentation can add Provider
requests, concurrency, rate-limit exposure and prosody or continuity defects.

The 2026-08-24 muted pilot measured a diagnostic median of 1,518.3 ms from TTS
request to first downlink. Its two completed dialogue rounds located 1,151.8 /
1,216.9 ms from request to first Provider PCM. Those values establish
materiality for a screen, not expected gain. Neither 400–800 ms nor `>600 ms`
is an accepted estimate or gate.

## 3. Phase-1 scope and exclusions

### Included

- one no-Browser, real-Provider A1/B/A2 runner;
- the existing `OpenAIStreamingSpeechProvider` public synthesis contract;
- frozen short, medium and long English final-text fixtures;
- manifest-declared exact segment offsets for B;
- bounded concurrent prefetch and ordered PCM release inside validation code;
- deterministic unit tests for segmentation manifests, ordering, bounds,
  cancellation, Provider failure and zero post-fence release;
- source-bound JSON result and sanitized Markdown summary generation.

### Excluded

- production Runtime, P2, Gateway media, Browser or UI wiring;
- provisional Agent deltas or any synthesis before authoritative final;
- a general sentence/clause classifier or production segmentation policy;
- Batch/fallback `LVL-10-R0` as causal evidence;
- microphone capture, physical first audible word, playout ACK, barge-in or
  human prosody acceptance;
- changing the TTS model, voice, output format, WebAudio lead, VAD, Provider
  connection policy or production defaults;
- Agent, Tool, Task, chat/history or Presentation truth mutation;
- claims of product, Gate C, p50/p95 E2E or Production readiness.

The phase-1 runner is validation tooling. Product adoption, including a real
segment classifier and lifecycle wiring, is a separate conditional packet.

## 4. Compared routes

| Role | Identifier | Exact route |
|---|---|---|
| Reference before | `LVL-10-A1` | One request containing the complete final text; current SSE Provider stream |
| Candidate | `LVL-10-B` | Same final text divided into manifest-bound text chunks; one SSE TTS request per chunk, at most four, released as one ordered PCM stream |
| Reference after | `LVL-10-A2` | Same route and complete final text as A1 |
| Optional diagnostic | `LVL-10-R0` | Batch/fallback inspection only; excluded from all causal calculations |

A1, B and A2 use the same source commit, API base/region, model, voice, PCM
format, requested sample rate, credentials class, process, network policy and
fixture bytes. Secrets never enter result artifacts or Git.

## 5. Frozen candidate mechanics

### 5.1 Text-chunk source

Phase 1 does not infer sentence boundaries. Each fixture declares an ordered
list of Unicode code-point offsets. Every exact slice is one text chunk and one
Provider request in B. The runner rejects the manifest unless:

- every segment is non-empty and contiguous;
- offsets start at zero, strictly increase and end at `len(final_text)`;
- concatenating exact slices reproduces `final_text` byte-for-byte in UTF-8;
- the segment count is between one and four;
- no trimming, whitespace normalization or punctuation rewriting occurs.

The short fixture contains one segment and is a parity/control case. The medium
fixture contains three segments. The long fixture contains four segments and
includes an abbreviation plus a decimal so the manifest demonstrates that
punctuation is preserved rather than classified heuristically.

### 5.2 Chunk request and prefetch bounds

- maximum segments and Provider requests per B attempt: **4**;
- maximum simultaneous Provider requests: **2**;
- prefetch depth: **1 successor** beyond the segment being released;
- automatic Provider retries: **0**;
- each segment receives a distinct stream/unit identity under one attempt and
  monotonically increasing unit order;
- attempts are serialized; only B's bounded pair of segment requests may
  overlap;
- ordered release never exposes segment `n+1` PCM before segment `n` reaches
  its Provider terminal event;
- buffered but unreleased successor PCM remains bounded by the existing event
  queues plus one runner-owned segment buffer.

### 5.3 Failure and fence disposition

Malformed manifests fail before any Provider call. If any segment fails,
times out or is cancelled, the group becomes failed, every live successor is
cancelled, buffered unreleased PCM is discarded and no group-complete marker is
emitted. Replacement or explicit group cancellation establishes one fence;
all later Provider events may be drained for cleanup but release zero PCM.

PCM already released before a later failure cannot be retracted. Phase 1
records that prefix and the failure truth; it never relabels the group as
complete. Product fallback behaviour is deliberately not decided here.

## 6. Corpus and execution population

The committed corpus manifest contains exactly three immutable final texts.
The arrays below are normative UTF-8 segment slices; concatenating each array
without a separator produces its `final_text` and exact offsets:

```json
{
  "short": [
    "Paris is the capital of France."
  ],
  "medium": [
    "The water cycle moves water continuously between Earth's surface and atmosphere.",
    " Evaporation and transpiration lift water vapor, which cools and condenses into clouds.",
    " Precipitation returns water as rain or snow, and runoff or infiltration carries it back to rivers, soil, and oceans."
  ],
  "long": [
    "Planning a three-day visit to Washington, D.C., works best when each day focuses on one area, because the U.S. capital has major sites spread across several neighborhoods.",
    " On the first day, walk from the Capitol and Library of Congress toward the museums of the National Mall, allowing enough time for security lines and indoor exhibits.",
    " On the second day, explore the memorials and the Tidal Basin; a 3.14-mile walking loop gives you a useful planning estimate without forcing a rushed pace.",
    " On the final day, visit Georgetown and Rock Creek Park, then leave a flexible evening window for weather changes, restaurant waits, or one museum you wanted to revisit."
  ]
}
```

The manifest stores `final_text`, code-point offsets and a SHA-256 binding; the
normative slices above are not regenerated by punctuation logic.

The primary causal population is one warmed process:

- one uncredited connectivity/configuration preflight per route;
- A1: five attempts per fixture, rotating short → medium → long;
- B: five attempts per fixture in the same rotation;
- A2: five attempts per fixture in the same rotation;
- total credited attempts: **45**;
- no silent replacement of a failed attempt and no discarded outlier;
- a rerun uses a new run ID and retains the failed run.

One cold attempt per fixture/route may run before the primary population but is
labelled diagnostic and excluded from the causal decision. The formal run is
invalid if source, Provider configuration, network class or fixture hash
changes between A1, B and A2.

Real Provider execution is single-owner and protected with:

```text
/tmp/jiuwenswarm-lvl10-provider.lock
```

No other Live Voice Provider benchmark may overlap that lock interval.

## 7. Measurement contract

All primary boundaries use one process-local `time.monotonic_ns()` clock.
Durations are stored in integer nanoseconds and rendered in milliseconds.

| Metric | Definition | Label |
|---|---|---|
| `request_to_first_pcm_ms` | Immediately before `open_synthesis` for the first request → acceptance of its first non-empty PCM event | `MEASURED` |
| `request_to_reserve_ms` | Same start → ordered releasable PCM first reaches 250 ms | `MEASURED` |
| `request_to_complete_ms` | Same start → every request completes and all ordered PCM is releasable | `MEASURED` |
| `ordered_release_stall_ms` | Real-time 48 kHz drain model's starvation between adjacent segment sources after playback eligibility | `DERIVED` |
| `audio_duration_ms` | Released samples / 48,000 Hz | `DERIVED` |
| `provider_request_count` | Requests actually opened for the attempt | `MEASURED` |
| `provider_error_count` | Provider failures/timeouts observed for the attempt | `MEASURED` |

The requested output is mono signed 16-bit PCM at **48,000 Hz**. Source
playable reserve is exactly **12,000 ordered samples / 250 ms**. It is a
Gateway/source-side readiness proxy, not Browser scheduling or audible credit.
If an utterance completes before 12,000 samples, reserve time equals successful
completion and the result records `short_of_reserve=true`.

Summaries report every attempt plus per-fixture p50 and nearest-rank p95. With
five attempts, p95 is descriptive only; the decision gate uses p50 and exact
integrity counts.

## 8. Prospective decision gates

### 8.1 Run validity

The decision is `INCONCLUSIVE` unless all of the following hold:

- A1, B and A2 each retain 15/15 declared attempts and complete provenance;
- A1, B and A2 each complete 15/15 attempts with zero Provider errors;
- A1 and A2 have zero configuration, fixture or source drift;
- for medium and long separately, A1 vs A2
  `request_to_reserve_ms` p50 drift is at most both **250 ms** and **20%**;
- all result rows and raw/sanitized hashes are retained;
- no overlapping process holds the Provider benchmark lock.

Provider failures remain in the denominator. A later retry cannot delete or
overwrite the inconclusive run.

### 8.2 Candidate PASS

LVL-10-B passes phase 1 only when every condition below holds:

1. For **medium and long separately**, B reduces
   `request_to_reserve_ms` p50 by at least **100 ms and 10%** against both A1
   and A2.
2. B `request_to_first_pcm_ms` p50 is lower than both references for medium and
   long; this direction check has no separate credited magnitude.
3. B `request_to_complete_ms` p50 is no more than **10% slower** than the slower
   A1/A2 reference for each fixture.
4. Short/control B uses exactly one request and its reserve/completion p50 does
   not regress more than **10%** against the slower reference.
5. B has 15/15 successful attempts, zero Provider errors, exact text coverage,
   exact segment order, no duplicate/omitted segment and no request-bound
   violation.
6. The real-time drain model reports `ordered_release_stall_ms` p95 at or below
   **100 ms** for medium and long.
7. Deterministic negative tests observe zero PCM after fence, zero false group
   completion and zero Agent/Tool/Task/chat/history effects.

Any integrity, authority, bound or failure-truth violation is `REJECTED`, not a
latency trade-off. A valid run that misses a numeric materiality/continuity gate
is `NO_MATERIAL_GAIN`. Only `PASS` authorizes a product-wiring design packet.

## 9. Risk, scenarios and verification

Phase-1 validation tooling is **Tier 2** because it owns concurrent Provider
requests, ordered release, cancellation and failure fences even though it is
outside product wiring. Root `TESTING.md` remains the complete testing and
review authority.

| Dimension | Phase-1 requirement |
|---|---|
| `P` | A1/B/A2 complete with exact text coverage and declared measurements |
| `N` | malformed offsets, empty segments and Provider errors fail closed before unauthorized release |
| `B` | one/four segments, 250 ms reserve, queue/request/concurrency limits |
| `S` | terminal groups cannot revive or emit a second terminal result |
| `T` | delayed/reordered successor events never cross ordered release or fence |
| `C` | at most two Provider requests overlap; simultaneous failure/cancel linearizes once |
| `R` | no hidden retry; partial failure is retained and all successors clean up |
| `I` | exact run/attempt/response/stream/unit identity; no cross-attempt PCM |
| `F` | A uses the untouched full-final route; B failure never masquerades as A fallback |
| `K` | existing Provider/conformance tests remain unchanged and pass |
| `X` | the credited screen calls the configured real Provider without Browser |

Required verification, in order:

1. focused unit tests written before implementation and demonstrated failing
   for the missing runner/segment-group behaviour;
2. complete new runner/test module;
3. existing `test_openai_streaming_speech.py` and
   `test_streaming_speech.py` affected regressions;
4. Ruff/type checks applicable to changed Python files;
5. one independent Tier-2 cold diff review;
6. connectivity preflight, then the exact real-Provider A1/B/A2 population;
7. result reduction and artifact-hash verification on the clean tested commit.

## 10. Output and evidence schema

Private raw artifacts live below:

```text
/home/renan/openJiuwen-ai/live-voice-latency-runs/lvl10/<commit>/<run-id>/
```

Each run retains `run.json`, the immutable corpus manifest copy,
`attempts.jsonl`, `report.json`, `report.md`, process-safe logs and SHA-256
bindings. `run.json` records source commit/state, Agent-Core commit label,
Python/runtime class, Provider/model/voice labels, fixture hash, reserve/sample
contract, segment/request/prefetch bounds, population order and environment
labels without secrets.

Repository evidence is added only after a valid result and contains sanitized
aggregate tables, exact commands, commit binding, denominators, failures,
non-claims and raw artifact hashes. Failed and inconclusive runs are retained
and catalogued rather than overwritten.

## 11. Parallel execution and filesystem ownership

No pane may write the current integration worktree while the packet is active.
After this specification is approved, Main creates two branches/worktrees from
the same clean specification commit:

| Pane | Branch/worktree | Authority and exclusive files |
|---|---|---|
| `1:0.0` | `latency/lvl10-provider-screen` / `/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-provider-screen` | Writer A: only `scripts/live_voice/lvl10_segmented_tts_screen.py` |
| `1:1.0` | `latency/lvl10-validation` / `/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-validation` | Writer B: only `tests/fixtures/live_voice_lvl10_tts_v1/manifest.json` and `tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py` |
| `0:0.0` | current reference tree | Read-only reviewer A: Provider/TTS/conformance inspection; return under `/tmp/lvl10-reviews/provider/` |
| `0:1.0` | current reference tree | Read-only reviewer B: ordering/cancel/oracle inspection; return under `/tmp/lvl10-reviews/oracles/` |

Main is the sole Integration Owner and the only writer of
`latency/hx-optimizations`. Workers do not switch branches, merge, rebase,
cherry-pick, push or edit STATUS/inventory/evidence. Each writer stages and
commits only its exclusive files and returns the commit hash, diff summary and
test output. An ownership collision produces `OWNERSHIP_REQUEST` and a stop;
it never authorizes an overlapping edit.

Real Provider execution occurs only after Main integrates and verifies both
returns on a clean candidate. Thus no writer produces competing run artifacts.

## 12. Pane communication protocol

Communication is pairwise and request-addressed:

- `1:0.0` ↔ `0:0.0` for Provider/runner review;
- `1:1.0` ↔ `0:1.0` for fixture/oracle review;
- cross-pair requests route through Main.

Messages use exactly one of:

```text
REQUEST <id> owner=<pane> question=<bounded question> return=<unique /tmp path>
RESULT <id> status=<PASS|FINDINGS|BLOCKED> artifact=<path> commit=<hash-or-none>
BLOCKED <id> reason=<exact blocker> needed=<exact action>
OWNERSHIP_REQUEST <id> file=<path> reason=<why current owner is insufficient>
ACK <id>
```

Each request owns a unique `/tmp` return path. Reviewers never modify repository
files. Writers send only when the paired pane is at an input boundary; messages
are not broadcast or concurrently injected into one pane. Git commits and
artifact hashes, not shared unstaged patches, are the handoff mechanism.

## 13. Deliverables and terminal conditions

Phase 1 is complete only with:

- the approved spec and implementation plan;
- isolated worktrees and recorded ownership;
- runner, frozen fixture, deterministic Tier-2 tests and documentation;
- independent review with findings resolved or explicitly routed;
- clean integrated source and focused/affected verification;
- retained real-Provider A1/B/A2 artifacts and one of `PASS`,
  `NO_MATERIAL_GAIN`, `REJECTED` or `INCONCLUSIVE`;
- STATUS/catalog/inventory updated truthfully after the result.

`PASS` opens a separate product-wiring specification covering the production
splitter, Runtime/Gateway ownership, cancellation/replacement, Browser Lane C
and audible prosody. Every other terminal result stops LVL-10 product work
unless a new reviewed mechanism or workload hypothesis is accepted.
