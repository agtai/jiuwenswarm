# TTS capture reconciliation review — 2026-08-21

## Scope and source

This cold, read-only reconciliation compares the current TTS first-audio owner
at source `517f0a0af19ca790572878063beab74528cb6c8b` with Hongxing's divergent
sequence:

- `6cd8840d5` — post-TTS capture-rotation reliability repair;
- `874cf327c` — successor-capture ACK decoupling;
- `35cae3d9a` — post-playout receipt correction;
- `e1df8b452` — later physical result that includes the sequence.

All four commits are available in the local object database and all four are
absent from the ancestry of the inspected source. Therefore none of their
behaviour may be credited to the current branch without an explicit port and
fresh verification.

This review owns only the reconciliation decision required by the
[TTS first-audio implementation plan](../roadmap/TTS_FIRST_AUDIO_RECONCILIATION_IMPLEMENTATION_PLAN_2026-08-21.md).
It does not grant benchmark, product, physical-browser or acceptance credit.

## Current blocking sequence

The current `ProductP1VoiceRouteOwner.playAgentText()` awaits
`#startConcurrentCapture()` after TTS descriptor resolution and before calling
`#openDownlinkRoute()`. `#startConcurrentCapture()` includes browser capture,
media activation, uplink attach, first frame and Gateway acknowledgement. A
slow or missing successor ACK can therefore delay or reject authoritative TTS
before its downlink is opened.

The current Gateway receipt contract also treats early uplink/downlink overlap
as a success requirement: `complete_downlink()` includes
`downlink_overlap_observed` in `complete`, and `acknowledge_playout()` requires
the stored overlap to be true. The Browser correspondingly requires
`duplex_media_observed` to equal the fact that a downlink route existed. This
conflates two independent facts:

1. the exact authorized audio was transported and rendered; and
2. successor microphone media was already observed during that downlink.

The second fact is useful duplex diagnostics, but is not proof of the first and
must not invalidate an otherwise exact render receipt.

## Reconciliation decision

| Source change | Relationship to TTS first audio | Decision | Required fresh proof |
|---|---|---|---|
| `874cf327c`: start bounded successor preparation and authoritative downlink concurrently; join readiness after render; degrade interruption when the successor fails | Directly removes capture readiness from the pre-downlink critical path while preserving initial-capture fail-closed semantics | **Port only if A1 passes the materiality gate** | Deterministic ACK-delay populations, downlink/first-source ordering, timeout degradation, stale/late ACK fencing, zero Agent/Tool/Task/history effects |
| `35cae3d9a`: make completed downlink depend on transport/render facts; retain `duplex_media_observed` as a boolean observation rather than a success precondition | Required semantic correction for the concurrent-start candidate; without it a correct short playout can still be rejected when successor media arrives late | **Port atomically with `874cf327c`** | Receipt acceptance with early, late and absent overlap; exact identity/content/render bindings and idempotency remain fail closed |
| `6cd8840d5`: 30-second capture lease rotation and bounded local-activity grace | Improves long-lived post-TTS capture reliability, not presentation-to-first-audio latency | **Exclude from this candidate** | Retain as separate reliability work; do not use it to explain first-audio gains |
| `e1df8b452`: physical evidence on the divergent history | Useful forensic evidence that motivated the candidate, but not transferable to this source | **Reference only** | Any product claim still requires a later exact-source physical Browser run |

The two selected changes form one contract: `874cf327c` makes overlap optional
in time, and `35cae3d9a` makes the authoritative receipt truthful under that
optional timing. Porting only the Web half would leave the Gateway capable of
rejecting the exact successful playout; porting only the receipt half would not
remove the pre-downlink wait.

## Test-oracle disposition

The historical tests are useful inputs but are not copied blindly because the
current route now also owns latency-probe N/N+1 rounds and completion joins.

| Historical oracle | Current applicability |
|---|---|
| Long answer opens downlink without waiting for successor readiness | Reuse the causal ordering, with current latency ownership asserted |
| No successor ACK degrades interruption but preserves rendered TTS | Reuse; additionally require one truthful terminal diagnostic outcome and no donated successor-ready mark |
| Delayed ACK inside the bound becomes ready | Reuse with deterministic clock/delay populations in A1 |
| Late ACK cannot cancel or revive scheduled TTS | Reuse and retain current generation/close fencing |
| Restart after degraded successor does not replay response | Reuse as recovery coverage if the product candidate is authorized |
| Gateway accepts completed downlink with early, late or absent overlap and reports the boolean fact | Reuse directly; retain every existing authority, content-hash, frame-count, queue-bound and idempotency negative oracle |
| Capture-rotation grace/lease tests from `6cd8840d5` | Do not include in the first-audio candidate or its benchmark |

The current test named “opens one bounded successor capture before a long
answer” encodes the existing serial gate and cannot be treated as proof of the
new contract. It must first fail for a controlled delayed ACK and then be
replaced or rewritten only if A1 authorizes product work.

## Materiality and stop condition

No product source is changed by this reconciliation. The next step is a
candidate-neutral Node benchmark that drives the real
`ProductP1VoiceRouteOwner` with deterministic fakes at successor-ACK delays of
0, 250, 750 and 1100 ms. Product work is eligible only when:

- the 250 and 750 ms populations are valid and complete;
- successor readiness is proven to be on the current critical path;
- the attributable p50 penalty is at least 200 ms and 15% versus 0 ms; and
- 1100 ms reproduces the bounded current failure with zero forbidden effects.

If this gate fails, stop the capture-decoupling candidate and move to the TTS
prewarm priority. Fake/Node evidence can establish component causality only; it
cannot establish audible, device, network or Browser product improvement.

## Review result

**RECONCILED — benchmark authorized; product port not yet authorized.** The
candidate is precisely the combined semantic change from `874cf327c` and
`35cae3d9a`. The `6cd8840d5` rotation change is deliberately outside this
latency experiment.
