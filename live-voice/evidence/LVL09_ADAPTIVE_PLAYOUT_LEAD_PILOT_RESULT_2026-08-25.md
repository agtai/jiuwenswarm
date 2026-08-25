# LVL-09 adaptive WebAudio startup-lead pilot result

**Date:** 2026-08-25
**Source:** `latency/adaptive-playout-lead-experiment` at
`5b37103a25d72302dd778681374b5a284c6886b4`
**Decision:** **TARGET MATERIALITY PASS; PHYSICAL ACCEPTANCE INCOMPLETE**
**Product default:** unchanged at 1000 ms

## 1. Question and rationale

The formal Browser already schedules each PCM frame as it arrives. Its first
source nevertheless starts behind a fixed 1000 ms lead. LVL-09 asks whether a
bounded 250 ms diagnostic lead removes material first-audio wait without
changing Agent, Speech, media, presentation or receipt authority.

The causal target is the same-clock Browser segment
`browser.playout_first_frame_scheduled` to
`browser.playout_first_frame_started_estimate`. It is a digital scheduling
estimate with explicit uncertainty, not physical first audible. End-to-end
`browser.eot_received` to that endpoint is diagnostic because STT, Agent and
TTS Provider variation may hide or amplify the WebAudio change.

## 2. Implementation and preparation

Product code remains at 1000 ms. The isolated experiment branch retains the
clamped diagnostic hook `VITE_LIVE_VOICE_PLAYOUT_STARTUP_LEAD_MS` in
`[160,1000]`; the private driver restarts only Vite between A1/B/A2 so the
backend remains warm.

The private preparer was repaired before this run to:

- emit `live-voice.latency-run.v1` with controlled Browser fixture labels;
- use only public-safe descriptors accepted by the official run validator;
- freeze a short no-Tool workload below the 30-second successor-capture
  rotation boundary;
- bind A1/B/A2 to round indices 0/1/2 and leads 1000/250/1000;
- warn the operator to reuse one Chrome tab because the allocator lives in
  `sessionStorage`.

Frozen spoken input:

> In two short sentences, explain why the sky appears blue.

The affected Browser Audio suite passed 111/111 before the pilot. The private
preparer, identity/process-group driver and corpus checks also passed. These
checks prove setup mechanics only.

## 3. Retained run

Run ID:

```text
lvl09-webaudio-short-20260825T123132Z-5b37103a2
```

Private artifact root:

```text
/home/renan/openJiuwen-ai/live-voice-latency-runs/
  lvl09-webaudio-short-20260825T123132Z-5b37103a2/
```

| Arm | Lead | Round | Terminal outcome | Target marks available |
|---|---:|---:|---|---|
| A1 | 1000 ms | 0 | `completed` | yes |
| B | 250 ms | 1 | `completed` | yes |
| A2 | 1000 ms | 2 | `cancelled` | yes, before cancellation |

A2 reached first-frame scheduling and estimated start, then an explicit
`live_voice.composition.p2.barge_in` cancelled the response before
`browser.playout_completed`, playout ACK and next-turn completion. Its target
pair is retained as a partial diagnostic; A2 receives no complete-round,
audible-output, underrun/rebuffer or acceptance credit.

## 4. Target result

| Metric | A1 1000 | B 250 | A2 1000 partial |
|---|---:|---:|---:|
| Schedule to start estimate | 718.549 ms | 48.432 ms | 721.306 ms |
| B improvement | — | 670.117 ms vs A1 | 672.874 ms vs A2 |
| B relative improvement | — | 93.260% vs A1 | 93.286% vs A2 |

The controls differed by only **2.757 ms / 0.383%**. The observed removable
WebAudio wait is approximately **670–673 ms** for this short workload. This is
measured at the declared Browser segment rather than borrowed from the 750 ms
configuration difference.

## 5. Stage-by-stage waterfall

All values below share the Browser clock. A2 values stop at first-start because
the round later cancelled.

| Segment | A1 1000 | B 250 | A2 1000 partial |
|---|---:|---:|---:|
| Capture device startup | 198.700 ms | 240.600 ms | 147.400 ms |
| Capture first-frame readiness | 542.400 ms | 585.900 ms | 498.800 ms |
| EOT to uplink closed | 14.200 ms | 17.100 ms | 15.300 ms |
| EOT to STT final | 528.000 ms | 499.300 ms | 781.300 ms |
| STT final to submit | 0.500 ms | 0.300 ms | 0.300 ms |
| Submit to presentation | 1,434.800 ms | 1,682.200 ms | 1,367.400 ms |
| Presentation to TTS request | 0.300 ms | 0.200 ms | 0.200 ms |
| TTS request to first downlink | 1,235.900 ms | 1,819.700 ms | 1,425.900 ms |
| Downlink attach | 331.300 ms | 329.100 ms | 321.700 ms |
| First downlink to schedule | 0.400 ms | 0.900 ms | 0.300 ms |
| Schedule to start estimate | **718.549 ms** | **48.432 ms** | **721.306 ms** |
| EOT to start estimate | **3,918.449 ms** | **4,051.032 ms** | **4,296.706 ms** |

The candidate did not improve total first-audio in this sequence. Against A1,
B lost 247.4 ms in submit-to-presentation and 583.8 ms in TTS-to-first-downlink,
more than consuming the 670.1 ms WebAudio gain. Against A2, B gained 282.0 ms
in STT but lost 314.8 ms in submit-to-presentation and 393.8 ms in
TTS-to-first-downlink. This is upstream drift, not failure of the target.

Gateway-local drill-down confirms Provider variation:

| Segment | A1 | B | A2 partial |
|---|---:|---:|---:|
| STT transport open | 609.191 ms | 729.568 ms | 561.901 ms |
| Provider EOT to STT final | 542.427 ms | 515.143 ms | 800.264 ms |
| TTS transport open | 895.769 ms | 1,500.286 ms | 1,103.850 ms |
| TTS request to first audio | 909.124 ms | 1,513.141 ms | 1,117.056 ms |
| TTS first audio to first send | 343.936 ms | 341.487 ms | 333.588 ms |

No Agent-local breakdown exists because the current source still lacks the
declared Agent start/first-delta producers.

## 6. Interpretation and headroom

The pilot establishes approximately **671 ms first-audio scheduling headroom**
in the fixed Browser lead. It does not establish a total-latency gain: Provider
and Agent variation can move more time than this optimization removes. A later
population must compare target and total separately.

The earlier unmatched diagnostic measured a 532.295 ms target reduction under
incompatible workloads. This same-workload sequence strengthens the direction
to 670–673 ms and provides near-zero control drift at the target, but cancelled
A2 prevents physical acceptance.

## 7. Decision and remaining gate

- Target materiality: **PASS directionally**.
- Measured target headroom: approximately 670–673 ms.
- A1/A2 target drift: 2.757 ms / 0.383%.
- Product default: remains 1000 ms.
- Physical A/B/A acceptance: **INCOMPLETE**.
- p50/p95, physical first audible and generalization: `UNKNOWN`.

A later acceptance population requires completed A1/B/A2 rounds, zero B
underrun/rebuffer, retained audible-output observation and full denominators.
It must not credit total differences contaminated by upstream drift or claim
that the approximately 671 ms target gain alone reaches the reported 3-second
product objective.

## 8. Artifact integrity

| Artifact | SHA-256 |
|---|---|
| `run.json` | `f61a24685c6063bc0e816eff09bfd0d94b847d82a072974602486fba2d2e87f1` |
| `lvl09-arms.json` | `a31ce590d4d6d09ef4e93caac6153658a73993ad1bee1e1c5e74f3db0d38bca4` |
| `browser.jsonl` | `69d24421257d237834247a85ff3bd4749e1619f40d0d437f354a0ffb7c0690e6` |
| `gateway.jsonl` | `0633b1869c3c12e281b07a3cbc11216d7c38499c87e7c819719157806e5baf51` |
| A1 snapshot | `89cf68563fc7c2be6947bf4978b51e84112f59070024971a956df1988c78447c` |
| B snapshot | `02959efdd5521e52996fdf497a1cba700bf08382bce04d9bbaa88d7b15ae3b2e` |
| A2 partial snapshot | `f8872ed92e957514f11ca8c1a5252206552654a7c3806927a97bd112af9bce02` |

Raw logs remain private because they may contain transcripts and local
configuration facts. The sanitized tables above are repository evidence.
