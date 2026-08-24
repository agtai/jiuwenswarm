# LVL-10L long-form authoritative-final chunked-TTS completion specification

> Date: 2026-08-24
>
> Status: **PROSPECTIVE REVISION 2 — pilot boundary evidence only; no
> materiality, Browser credit or product wiring**
>
> Capability: Observability, benchmark and latency / authoritative-final TTS
>
> Risk: **Tier 2** validation concurrency, ordering, cancellation and fence
> boundary. This packet does not change the product route.

## 1. Decision sought

LVL-10L asks whether bounded parallel TTS requests materially shorten
**source-side synthesis completion for long authoritative finals**, and whether
two or four chunks provide the best latency/request trade-off.

The completed LVL-10 experiment remains immutable and `INCONCLUSIVE`. Its two
real-Provider populations found a repeated 20–24% long-completion improvement
and a 10–24% medium-completion regression. LVL-10L is a new prospective
hypothesis; it does not change LVL-10's primary metric or thresholds after the
fact.

The selected implementation, if any, still requires a later design for a
product-owned long-form eligibility rule and a separate physical Browser Gate.
This experiment cannot authorize either.

### 1.1 Revision-2 pilot disposition

The original v1 corpus remains immutable. Its `long_2400` fixture actually
contained 2,938 characters. The first pilot was rejected before PCM because
the configured OpenAI project returned `429 credit_balance_exhausted`. After
credit restoration, a second pilot opened all 24 requests and completed 11/12
attempts. The one-request A2 long arm reached approximately 8 MiB of Provider
PCM and failed at the existing `MAX_STREAM_AUDIO_BYTES` safety boundary; A1
had completed only about 80 KiB below that boundary. B2/B4 distribute audio
across requests, so retaining that fixture would structurally favour them.

Revision 2 therefore changes no Provider cap and grants neither pilot latency
credit. It freezes a separate v2 corpus whose largest fixture is the first 12
units / 2,150 characters of the same text, leaving materially more headroom
below the cap. The user also approved a five-round formal population to bound
external calls. All gain, drift, authority and reliability thresholds remain
unchanged except round-count predicates stated below.

## 2. Intended behaviour and invariant

Every route receives one complete immutable authoritative final before TTS.
The reference submits that final in one Provider request. The candidates split
the same final at offsets frozen in the corpus manifest, open at most two
Provider requests concurrently and release PCM in original text order.

For all routes:

- concatenated request text equals the authoritative final byte-for-byte;
- each text range is covered exactly once and in order;
- successor PCM is never released before its predecessor;
- cancellation, replacement or partial failure fences the whole group;
- no stale or post-fence PCM is released;
- no Agent, Tool, Task, chat or history mutation occurs;
- automatic retries are zero, and failures remain in the denominator.

This is post-final presentation optimization. It never speaks provisional
Agent text and does not reopen LVL-07 stable-sentence overlap.

## 3. Scope and exclusions

### 3.1 Included

- a frozen English long-form corpus with three nested output sizes;
- one-request reference plus exact two- and four-chunk candidates;
- real configured streaming Speech Provider, same model, voice, format,
  network policy and environment profile;
- first PCM, 250 ms source reserve, total source synthesis completion,
  whole-chunk availability diagnostics, request count, error count and
  integrity evidence;
- interleaved `A1/B2/B4/A2` pilot and formal populations;
- deterministic validation of malformed corpus, order, partial failure,
  cancellation and artifact reduction.

### 3.2 Excluded

- Browser, WebAudio, device, first audible word, playout and receipt ACK;
- STT, EOT/VAD, Agent/model execution and Task behaviour;
- product-route changes, feature flags or a runtime output-length classifier;
- sentence detection, semantic chunking or a new shared protocol;
- changing Provider/model/voice/format between arms;
- retries, connection pooling claims, prosody credit or cost/billing claims;
- Production, controlled-product or end-to-end latency credit.

If implementation requires a new product classifier, shared protocol or
authority rule, work stops and that expansion receives a separate scope and
risk decision.

## 4. Alternatives considered

### 4.1 Recommended: A1/B2/B4/A2 break-even screen

Compare the one-request route with both two and four exact manifest chunks.
This isolates fixed per-request overhead and reveals whether four requests earn
enough incremental completion gain to justify their amplification.

### 4.2 One candidate with four chunks only

This is cheaper to implement but cannot distinguish the benefit of parallelism
from excessive request fan-out. The prior LVL-10 result already showed that
shorter work can lose to request overhead, so this alternative is rejected.

### 4.3 Wire a long-form product threshold and test end to end

This would confound causal materiality with Browser behaviour and introduce a
new runtime policy before a break-even point exists. It is explicitly deferred.

## 5. Frozen corpus contract

The implementation commits a separate v2 manifest before the next Provider
call. It contains exactly 12 natural English sentence units on one coherent
explanatory topic. The three fixtures are nested prefixes of those units:

| Fixture | Units | Accepted UTF-8 character range | Purpose |
|---|---:|---:|---|
| `long_600` | 4 | 550–750 | lower boundary near the earlier 661-character signal |
| `long_1200` | 8 | 1,100–1,500 | long-form materiality |
| `long_2100` | 12 | 2,000–2,250 | request-overhead amortization with 8 MiB safety margin |

Each fixture freezes:

- full final text and its SHA-256;
- unit offsets and unit-text hashes;
- two-chunk offsets formed from equal contiguous unit groups;
- four-chunk offsets formed from equal contiguous unit groups;
- exact character and UTF-8 byte counts.

No runtime punctuation classifier is part of the experiment. The corpus
validator rejects missing/extra fields, hash mismatch, empty or overlapping
ranges, non-contiguous coverage, non-nested fixtures, boundaries inside a unit,
or text outside the declared ranges. Once any Provider call starts, corpus and
gates are immutable for that run series.

## 6. Routes and request budget

| Role | Route | Requests per attempt |
|---|---|---:|
| `LVL-10L-A1` | complete final in one request, reference before | 1 |
| `LVL-10L-B2` | same final in two manifest chunks | 2 |
| `LVL-10L-B4` | same final in four manifest chunks | 4 |
| `LVL-10L-A2` | complete final in one request, reference after | 1 |

Both candidates use `max_active_requests=2`, ordered release and one bounded
successor beyond the release frontier. B2 therefore opens both requests; B4
opens two and replenishes only as the ordered frontier advances.

The pilot has one attempt per role/fixture cell: **12 attempts and 24 Provider
requests**. The formal population has five attempts per cell: **60 attempts and
120 Provider requests**. Formal role totals are A1=15, B2=30, B4=60 and A2=15.
There are no Provider preflight calls, unrecorded
warm-ups, retries or replacement calls.

The runner creates four Provider adapters before credited attempts, one for
each role, keeps all four live during the interleaved population and closes all
four at the end. Each adapter retains exactly 15 response identities in the
formal population, below the Provider conformance ledger's exact 64-identity
cap. Every identity binds interaction to `run+role+fixture`, response
generation to the round index, and unique response/stream/unit IDs to the exact
role, fixture, round and chunk. This avoids the stale-generation assumption in
LVL-10's fixed fixture ordering. Adapter lifetime does not establish network
connection reuse or warm/cold transport credit; every actual request remains
counted.

## 7. Interleaving and clocks

One formal round covers all fixtures and all four roles. For round index `r`:

1. rotate fixture order among
   `600→1200→2100`, `1200→2100→600`, and `2100→600→1200`;
2. for each fixture run A1 first and A2 last;
3. alternate candidate order: even rounds use `A1→B2→B4→A2`; odd rounds use
   `A1→B4→B2→A2`;
4. acquire the existing shared non-blocking Provider benchmark lock at
   `/tmp/jiuwenswarm-lvl10-provider.lock`; a LVL-10L-only lock would not prevent
   overlap with LVL-10 or another real-Provider screen.

All timings use `time.monotonic_ns()` in one process. A paired reference for a
candidate is linearly interpolated between the surrounding A1 and A2 metric
using the candidate's monotonic start position between their start positions.
This prevents alternating B2/B4 order from sharing a falsely identical
reference. Wall time is provenance only.

## 8. Measurements

| Measurement | Definition | Class |
|---|---|---|
| `request_to_first_pcm_ms` | first request open start to first valid PCM from chunk 0, the first ordered-releasable source | `MEASURED` |
| `request_to_any_chunk_pcm_ms` | first request open start to earliest PCM from any chunk; diagnostic only and never credited as playable | `MEASURED` |
| `request_to_reserve_ms` | first request open start to 12,000 ordered chunk-0 samples at 48 kHz; successful completion if shorter | `MEASURED` source proxy |
| `request_to_complete_ms` | first request open start to successful completion of every chunk in the group | `MEASURED`, primary |
| `paired_complete_gain_ms` | interpolated paired reference minus candidate completion | `DERIVED`, primary |
| `paired_complete_gain_pct` | paired gain divided by the interpolated paired reference | `DERIVED`, primary |
| `whole_chunk_availability_gap_ms` | gap model based on whole-chunk terminal availability; diagnostic only, not streaming playout | `DERIVED`, non-gating |
| `audio_duration_ms` | released ordered samples divided by 48 kHz | `DERIVED` |
| per-chunk timeline | open, first PCM, complete and ordered-release deltas for each chunk | `MEASURED` |
| request/error/integrity counts | observed calls, terminal outcomes, reason codes and exact oracles | `MEASURED` |

These metrics do not estimate Browser scheduling or end-to-end latency. In
particular, whole-chunk availability is not a real PCM-delta drain or continuity
measurement and cannot decide materiality. The report labels Provider/source
timings as measured and every calculation as derived.

## 9. Pilot gate

The one-attempt-per-cell pilot may authorize the formal population only when:

- all 12 attempts complete, all 24 expected requests are observed and Provider
  errors are zero;
- every integrity, order, fence and zero-forbidden-effect oracle passes;
- for both `long_1200` and `long_2100`, at least one candidate completes faster
  than both its A1 and A2 control;
- on `long_1200` and `long_2100`, neither candidate is slower than its paired
  reference by both 1,000 ms and 50% on first PCM or reserve;
- configuration, source, corpus and environment provenance are complete.

Pilot timings are diagnostic and never enter the formal denominator.

## 10. Formal validity gate

The formal result is `INCONCLUSIVE` unless:

- each role/fixture cell retains exactly 5/5 attempts;
- all 60 attempts complete with zero Provider errors and exact request counts;
- source, Agent-Core, model, voice, format, environment and corpus hashes are
  identical across arms;
- every integrity, order, fence and zero-forbidden-effect oracle passes;
- for each fixture, A1/A2 completion p50 drift is no more than **10%** and
  **1,500 ms**;
- for each fixture, at least 4/5 A1/A2 completion brackets differ by no more
  than 20%;
- for each fixture, A1/A2 first-PCM and reserve p50 drift are each at most
  **250 ms** and at most **20%**, so their candidate non-regression gate remains
  interpretable;
- no overlapping benchmark holds the LVL-10L Provider lock;
- raw/sanitized artifacts and hashes are retained.

A run that violates validity cannot be rescued by deleting attempts, adding
retries, relaxing a threshold or selecting only favourable rounds.

## 11. Candidate materiality and selection

### 11.1 Per-bucket materiality

A candidate is materially positive for one bucket only when all of these hold:

- paired completion gain p50 is at least **750 ms** and **15%**;
- candidate completion p50 is directionally faster than both A1 and A2
  completion p50, so interpolation cannot turn control drift into a false win;
- at least 4 of 5 paired rounds have positive completion gain;
- candidate first-PCM and reserve p50 regressions from the paired reference are
  each at most **200 ms** and at most **10%**;
- generated audio duration and ordered sample-count p50 stay within **±10%**
  of the paired reference, preventing shorter speech from masquerading as
  synthesis parallelism;
- all reliability and integrity gates pass.

### 11.2 Hierarchical long-form decision

`long_2100` is the sole prospectively declared long-form materiality gate. A
candidate that fails it is not material, even if a shorter bucket appears to
win. After `long_2100` passes, evaluate `long_1200` and then `long_600` using
the same per-bucket gate to identify the smallest demonstrated break-even
boundary. A shorter isolated win followed by a longer failure is non-monotonic
and does not establish an eligibility threshold.

### 11.3 B4 request-amplification gate

B2 and B4 are evaluated independently using the per-bucket and hierarchical
gates. If both pass `long_2100`, prefer B2 unless B4's paired completion p50 on
that bucket is at least **750 ms** and **10%** faster than B2 while satisfying
the same first-PCM, reserve, audio-duration and integrity gates. Thus two extra
requests require extra material gain.

### 11.4 Outcomes

| Outcome | Meaning |
|---|---|
| `B2_MATERIAL` | B2 passes the 2100 gate; B4 does not justify extra request amplification |
| `B4_MATERIAL` | B4 passes the 2100 gate and the incremental B2 gate |
| `B2_AND_B4_MATERIAL_PREFER_B2` | both pass 2100, but B4 lacks sufficient incremental value |
| `NO_MATERIAL_GAIN` | valid population, neither candidate passes completion gates |
| `REJECTED` | integrity, order, reliability, fence or cost/request contract fails |
| `INCONCLUSIVE` | run validity or provenance fails |

With five rounds, p90/p95 are descriptive only and cannot replace the frozen
p50/win-count decision. The report separately records the smallest
monotonically demonstrated bucket for the selected arm. This is evidence for a
later product-policy design, not a runtime classifier or activation rule.

## 12. Tier-2 scenario closure

| Dimension | Required evidence |
|---|---|
| `P` | A1/B2/B4/A2 complete exact text and ordered PCM for all three sizes |
| `N` | malformed manifest and Provider partial failure fail closed with zero forbidden effects |
| `B` | exact 2/4 chunk and max-active bounds; empty, overlapping and non-contiguous ranges rejected |
| `S` | completed/cancelled groups are terminal and cannot be revived |
| `T` | delayed/reordered successor PCM remains behind the ordered frontier; timeout is truthful; whole-chunk gap stays diagnostic |
| `C` | at most two requests active; replenishment and release remain ordered |
| `R` | no automatic retry; partial failure fails the whole group without duplicate speech |
| `I` | exact run/role/fixture/round/response/generation/stream/unit isolation plus text coverage and zero forbidden effects |
| `F` | the existing full-final reference is unchanged; candidate partial failure fences the group without fallback or false success |
| `K` | affected Provider/conformance regressions pass; no schema or existing consumer is changed |
| `X` | configured real Provider pilot/formal screen; Browser and product are explicitly excluded |

Before a result is declared, run affected tests, Ruff, `git diff --check`, a
complete cold diff review and one independent Tier-2 review.

## 13. Artifacts and provenance

Each immutable run directory contains:

- `run.json`: run ID, UTC start, exact source and Agent-Core commits, clean/
  dirty state, environment label, Provider route metadata without secrets,
  corpus hash, role schedule, request budget, clocks and frozen gates;
- `manifest.json`: exact copied corpus;
- `attempts.jsonl`: every attempt, including failures, reason codes, identities
  and sanitized per-chunk timelines;
- `report.json`: exact expected/observed request totals, denominators,
  p50/p90/p95, paired deltas, decision, ordered gate-reason list and hashes;
- `report.md`: concise human-readable tables and boundary labels.

The report binds SHA-256 values for `run.json`, `manifest.json`,
`attempts.jsonl` and its own canonical payload. LVL-10L uses a separate runner,
manifest, tests and schemas; completed LVL-10 artifacts and reducers are not
modified.

Raw artifacts stay in the private latency archive. Repository evidence binds
sanitized artifact hashes and contains no credentials.

## 14. Terminal boundary

A material Provider result authorizes only a later product-design packet. That
packet must define any long-form eligibility policy, integrate with the current
authoritative-final presentation owner, and pass Browser Lane C for first
audible output, underrun/rebuffer, prosody, barge-in, cancellation and receipt
truth. Until then the current one-request product route remains unchanged.
