# LVL-08 Semantic VAD AUTO retry result — 2026-08-25

## Result

**PROTOCOL REPAIR PASS / AUTO INTEGRITY REJECTED.** The repaired OpenAI
streaming boundary completed the full 12-slot A1/B/A2 pilot, proving that
Semantic AUTO now opens, emits ordered Provider boundaries, commits and
finalizes. The candidate nevertheless fails the natural-pause Gate: the
600 ms and 1000 ms internal-pause cases ended early. No default, HIGH,
formal-population or product credit follows; Server-VAD remains 1200 ms.

The source is clean `latency/semantic-vad-experiment` commit
`222582618f7d7a680e55dbcef66bb8f96419f32c`. The protocol repair and fault
matrix passed `189` affected tests, Ruff, compile and diff-check, followed by
two independent Tier-3 re-reviews at `C0/I0/M0`.

## Binding

- run ID: `lvl08-semantic-auto-pilot-20260825t162000z`;
- mode/experiment: `pilot / semantic-auto`;
- corpus: `vad-en-v1-reconciled-20260825`;
- corpus manifest SHA-256:
  `78537d7efe398d8bf39719353b042d8b6409130daea50a3d21a5dda6f9d57508`;
- Provider/model: `OpenAIStreamingSpeechProvider` /
  `gpt-4o-mini-transcribe-2025-12-15`;
- private report SHA-256:
  `64bfcbd8d5601ae4e924b715e7833188bdf4ae26a4ec8e78f3b51bd85c94981c`;
- private report mode/size: `0600 / 13577 bytes`;
- retained attempts: `12/12` in exact A1 → B → A2 order;
- forbidden Agent, Tool, Task, P2, TTS, history and Browser effects: all zero.

## Measurements

| Case | A1 Server EOT | B AUTO EOT | A2 Server EOT | B gain vs A1 / A2 | B total vs A1 / A2 | Integrity |
|---|---:|---:|---:|---:|---:|---|
| no internal pause | 1516.227 ms | 832.185 ms | 1518.638 ms | 684.043 / 686.453 ms | 785.913 / 1000.531 ms faster | pass |
| 300 ms pause | 1520.048 ms | 791.585 ms | 1525.571 ms | 728.463 / 733.986 ms | 1082.416 / 756.698 ms faster | pass |
| 600 ms pause | 1540.986 ms | — | 1542.761 ms | no credit | no credit | `EARLY_EOT` |
| 1000 ms pause | 1523.568 ms | — | 1616.856 ms | no credit | no credit | `EARLY_EOT` |

All eight Server-VAD controls completed with exact identity, complete
transcript, valid pacing and clean cleanup. Their EOT A1/A2 drift remained
within the 10% pilot bound. B_AUTO completed the first two cases with one exact
start/stop/commit/final and clean cleanup, but the two longer natural pauses
also produced one complete Provider turn too early, so their timing is
correctly null rather than attractive latency.

## Interpretation

The original `PROVIDER_PROTOCOL` blocker was an Adapter/conformance defect:
Semantic VAD boundaries were rejected as Server-VAD-only, Semantic capability
was not declared native, and a Provider-owned Semantic final was incorrectly
routed through the manual exact-cursor path. Commits `3817aaaea` and
`222582618` repair and harden those boundaries without granting Agent/Task
authority or sending a client commit.

The remaining result is not a protocol failure. It is a measured product
trade-off: AUTO saves roughly 684–734 ms of endpointing on the two cases it
completes, but violates the required 600/1000 ms continuation safety. Therefore
AUTO is rejected for the current corpus. HIGH must not run because it is at
least as eager and cannot rescue this failed continuation Gate under the
declared ordering. Any future attempt requires a new, predeclared arbitration
or continuation-safety hypothesis rather than another population of the same
configuration.

