# P1/P2 playout/capture decoupling Tier-3 review — 2026-08-23

## Result

**PASS — C0 / I0 / M0.** Review target was exact clean source
`42f537894a61e1ad0c5b5fe8033ecb9f3b1382f5`. This closes the previously
uncredited independent review for the two older production seams and freezes
them against aesthetic refactoring. It grants no new physical or product-
readiness credit.

## Bounded scope

- Successor capture readiness does not gate authoritative TTS downlink or
  browser playout.
- A completed authorized playout receipt does not require early duplex media;
  `duplex_media_observed` remains an observation rather than a success gate.
- Initial user capture remains first-frame-ACK gated and fail closed.
- Exact response, activation, Session and receipt identities continue to fence
  stale callbacks and cleanup.
- Agent/Tool/Task/history policy, Provider configuration, VAD, generation-time
  interruption and notification batching were excluded.

## Findings and production truth

Critical: none. Important: none. Minor: none.

Capture and downlink start independently. `playing` is published only after the
browser accepts and schedules the source. A successor-capture failure degrades
only interruption/listening and compensates the exact successor authority; it
does not discard or duplicate the authoritative response. Late or stale ACKs
cannot mutate current state. Gateway completion remains separate from
`duplex_media_observed`, and the receipt accepts an exact bounded closed boolean
`false` without weakening identity validation.

## Independent verification

- Formal Integrated Web: `466/466` PASS.
- Browser Audio I/O: `103/103` PASS.
- Dedicated Media registration: `45/45` PASS.
- Focused no/before/after early-duplex and exact receipt matrix: `4/4` PASS.
- Scoped Ruff and `git diff --check`: PASS.

## Matrix and non-claims

P/N/B/S/T/C/R/I/F/K/X all PASS within the declared production seam and
source/automation boundary. No new real-device run was performed. Existing
physical short/long TTS, post-playout listening and playout-time barge-in credit
predates this review; crash recovery, Provider degradation, cross-load,
fixed-corpus latency, P3-9 and complete product acceptance remain non-claims.
