# TTS first-audio causal A1/B/A2 result — 2026-08-21

## Decision

**`SUCCESSOR_ACK_DECOUPLING_ACCEPTED` for the no-Chrome causal component
boundary.** The candidate removes successor-capture ACK delay from the TTS
downlink and first-source critical path. It does not remove that delay from
authoritative playout settlement, and it does not grant physical Browser,
audible-output, Provider, network or end-to-end product credit.

The accepted source is
`cd4d1b7d34a529839ecf219f7f2eb567fedce4d2`. Independent Tier-3 review closed
with no remaining Critical or Important finding after the truthful non-duplex
receipt remediation in `cd4d1b7d3`.

## Exact experiment

| Population | Source | Run ID | Role |
|---|---|---|---|
| A1 | `2651b0dd8ae594f342fe3262ca1b89d44456f2e8` | `tts-a1-20260821T093944Z-2651b0dd8a` | original sequential reference |
| B2 | `cd4d1b7d34a529839ecf219f7f2eb567fedce4d2` | `tts-b2-20260821T101119Z-cd4d1b7d34` | reviewed successor-ACK-decoupled candidate |
| A2 | `2651b0dd8ae594f342fe3262ca1b89d44456f2e8` | `tts-a2-20260821T100346Z-2651b0dd8a` | unchanged-source return control |

All three runs used Node `v24.18.0`, the same runner and four injected
successor-ACK delays (0, 250, 750 and 1100 ms), with five attempts per delay.
Raw reports are private, external to Git, exclusive mode `0600`, and use schema
`live-voice.tts-first-audio-causal-report.v0`. An earlier B report on
`56a1fc4eb` was superseded after review remediation and receives no final
source credit.

The deterministic runner drives the real `ProductP1VoiceRouteOwner` using
content-free Speech/media/audio fakes. It performs no Chrome, device, network,
Provider, Agent, Tool, Task or history operation. Its measured boundaries are:

- TTS descriptor ready: the exact synthesis descriptor returned;
- successor capture requested and first ACK: interruption readiness branch;
- downlink opened and first frame received: authoritative audio transport;
- first source scheduled: first Browser-audio source accepted for scheduling;
- playout receipt accepted: final authoritative render settlement.

## Outcome counts

| ACK delay | A1 | B2 | A2 |
|---:|---:|---:|---:|
| 0 ms | 5 completed | 5 completed | 5 completed |
| 250 ms | 5 completed | 5 completed | 5 completed |
| 750 ms | 5 completed | 5 completed | 5 completed |
| 1100 ms | 5 failed before downlink | 5 `degraded_interruption` after one render | 5 failed before downlink |

There were zero invalid or unknown attempts and zero Agent, Tool, Task or
history effects in every report. The B2 1100 ms population retained one exact
render and receipt, stopped/revoked only the failed successor capture, and did
not let the late ACK revive state or replay TTS.

## First-source comparison

Milliseconds from TTS request; nearest-rank over five attempts.

| ACK delay | A1 p50 / p95 | B2 p50 / p95 | A2 p50 / p95 | B2 gain vs A1 p50 |
|---:|---:|---:|---:|---:|
| 0 ms | 6.746 / 10.344 | 0.965 / 2.949 | 6.858 / 10.254 | 5.781 ms (85.7%) |
| 250 ms | 255.597 / 256.608 | 0.486 / 0.783 | 254.980 / 256.037 | 255.111 ms (99.81%) |
| 750 ms | 756.542 / 756.958 | 0.476 / 0.540 | 754.721 / 755.690 | 756.066 ms (99.94%) |
| 1100 ms | — | 0.494 / 0.649 | — | reference never opened downlink |

A1 and A2 p50 varied by 1.66% at 0 ms and approximately 0.24% at 250/750
ms, within the 10% return-control gate with identical outcome counts. B2
exceeded both the 200 ms and 15% delayed-population materiality gates against
both A1 and A2. The immediate-ACK population improved rather than regressed.

## Stage-by-stage p50

### 250 ms injected successor ACK

| Boundary | A1 | B2 | A2 |
|---|---:|---:|---:|
| TTS descriptor ready | 0.001 | 0.001 | 0.001 |
| Successor capture requested | 0.039 | 0.031 | 0.037 |
| Successor first ACK | 251.138 | 252.292 | 251.031 |
| Downlink opened | 255.215 | 0.107 | 254.573 |
| Downlink first frame | 255.511 | 0.404 | 254.882 |
| First source scheduled | 255.597 | 0.486 | 254.980 |
| Playout receipt accepted | 266.612 | 254.023 | 265.533 |

### 750 ms injected successor ACK

| Boundary | A1 | B2 | A2 |
|---|---:|---:|---:|
| TTS descriptor ready | 0.001 | 0.001 | 0.001 |
| Successor capture requested | 0.024 | 0.037 | 0.025 |
| Successor first ACK | 751.212 | 751.498 | 751.201 |
| Downlink opened | 756.054 | 0.125 | 753.980 |
| Downlink first frame | 756.458 | 0.413 | 754.668 |
| First source scheduled | 756.542 | 0.476 | 754.721 |
| Playout receipt accepted | 767.439 | 753.939 | 766.050 |

The descriptor and capture-request boundaries remain stable. Downlink,
first-frame and first-source move before the ACK in B2, proving true overlap
rather than a smaller injected delay.

## Settlement limitation

The ACK wait is not eliminated from the entire response lifecycle. B2 still
awaits bounded successor readiness before accepting the playout receipt:

| ACK delay | B2 receipt p50 / p95 |
|---:|---:|
| 0 ms | 11.645 / 14.663 |
| 250 ms | 254.023 / 256.286 |
| 750 ms | 753.939 / 756.151 |
| 1100 ms | 1006.918 / 1011.738 |

Therefore this is a first-audio/perceived-latency optimization, not an
equivalent improvement in authoritative round settlement or next-turn
readiness. Future settlement overlap must be evaluated as a separate authority
change and cannot inherit this result.

## Contract and review closure

The implementation ports only the reconciled pair:

1. TTS downlink and bounded successor-capture preparation start concurrently;
2. `duplex_media_observed` remains a truthful boolean observation and cannot
   reject an otherwise exact completed playout.

Initial capture remains fail closed. Successor no-frame/no-ACK/mute failures
degrade interruption only, revoke the exact successor authority, retain the
predecessor TTS receipt and permit explicit restart. Cancel/session-switch,
late-ACK, runtime capture failure, render-clock failure, latency-round identity,
receipt idempotency and zero forbidden effects remain covered.

Independent Tier-3 review verified the applicable P/N/B/S/T/C/R/I/F/K matrix.
The X dimension is closed only at deterministic component/seam level; physical
Chrome, WebAudio/device, Provider, network and human-audible confirmation remain
deferred by explicit user scope.
