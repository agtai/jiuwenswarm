# LVL-08 Semantic VAD AUTO pilot result — 2026-08-25

## Result

**CONTROL PASSED / SEMANTIC AUTO REACHED / PROVIDER PROTOCOL REJECTED.** This
run grants no Semantic VAD timing, optimization, default or product credit.
Semantic HIGH was not run, and the production fallback remains Server-VAD at
1200 ms.

The evidence-runner repair is isolated on
`latency/semantic-vad-experiment` at clean source
`5811aeb7f0bd9f10161589cd59be732051d600be`. Its deterministic runner Gate
passed `44/44`, Ruff and diff-check, followed by independent Tier-2 review
`C0/I0/M0`.

## Method and binding

- mode/experiment: `pilot / semantic-auto`;
- corpus: `vad-en-v1-reconciled-20260825`;
- corpus manifest SHA-256:
  `78537d7efe398d8bf39719353b042d8b6409130daea50a3d21a5dda6f9d57508`;
- Provider class/model: `OpenAIStreamingSpeechProvider` /
  `gpt-4o-mini-transcribe-2025-12-15`;
- run ID: `lvl08-semantic-auto-pilot-20260825t154600z`;
- private report SHA-256:
  `b40a3fb669756ef6d9bf05f521453375609489abc0718d8e8891c39377d7bced`;
- private report mode/size: `0600 / 6108 bytes`;
- forbidden Agent, Tool, Task, P2, TTS, history and Browser effects: all zero.

The runner used one attempt per corpus case and stopped immediately on the
first `UNKNOWN`/`INVALID`, retaining the exact ordered prefix. The report is
sanitized and contains no credential, exception payload, transcript content or
raw audio.

## Retained waterfall

| Arm / case | Outcome | Final voiced frame → EOT | EOT → final | Final voiced frame → final | Cleanup |
|---|---|---:|---:|---:|---|
| A1_1200 / no internal pause | completed | 1522.885 ms | 641.698 ms | 2164.583 ms | clean |
| A1_1200 / 300 ms pause | completed | 1533.706 ms | 632.978 ms | 2166.684 ms | clean |
| A1_1200 / 600 ms pause | completed | 1550.215 ms | 561.601 ms | 2111.816 ms | clean |
| A1_1200 / 1000 ms pause | completed | 1522.325 ms | 452.824 ms | 1975.149 ms | clean |
| B_AUTO / no internal pause | unknown — `PROVIDER_PROTOCOL` | — | — | — | clean |

The four Server-VAD controls each observed exactly one speech start, speech
stop, commit and final with exact identity, complete transcript, valid pacing
and clean cleanup. The first Semantic AUTO attempt observed none of those
events and retained no latency. The final decision is therefore
`SEMANTIC_VAD_INTEGRITY_REJECTED`, not a false control failure and not an
optimization result.

## Interpretation and next action

The former control-precondition blocker is closed. The remaining blocker is
now localized to the Provider-native Semantic AUTO protocol path. Diagnose its
session-configuration/echo/event contract without opening another population;
only a new bounded AUTO attempt after that diagnosis may determine whether the
Provider/model supports this semantic configuration. Do not run HIGH, formal,
Browser validation or change the 1200 ms fallback from this result.

