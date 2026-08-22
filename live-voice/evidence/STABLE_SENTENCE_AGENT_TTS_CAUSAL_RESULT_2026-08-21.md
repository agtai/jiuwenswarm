# Stable-Sentence Agent-to-TTS Causal Screen Result

Date: 2026-08-21

## Decision

`STOP` — do not implement the conditional Runtime/P2/Browser product
candidate in Tasks 6–12 of the implementation plan.

The credited real-Provider pilot completed all three public cases with exact
candidate-prefix reconciliation and zero forbidden effects, but the removable
Agent-final wait was not material enough:

| Gate | Required | Observed | Result |
|---|---:|---:|---|
| candidate → `chat.final` p50 | at least 500 ms | 177.2 ms | fail |
| projected first-PCM gain p50 | at least 400 ms | 177.2 ms | fail |
| projected relative gain p50 | at least 10% | 7.43% | fail |
| useful trace classes | at least 2 | 3 | pass |
| Provider-pilot prefix mismatch | 0 | 0 | pass |
| forbidden effects | 0 | 0 | pass |

This is a causal no-Chrome screen, not an end-to-end product benchmark. It
does not authorize stable-sentence product wiring and grants no Browser,
first-audible, playout, ACK, next-turn, Tool or Task credit.

## Exact source and environment

- JiuwenSwarm source: `81903777f8dccb40ba2cb70fbe9b28d28d86c7f5`.
- Agent-Core source installed in the tested venv:
  `94e10cb6102c36fe78a64547957c0def97299273`, matching local branch
  `hx/0812_live_voice_w3`.
- Python 3.11.15 on Linux WSL2 x86_64.
- Agent route: real formal Agent facade, `agent` mode, memory disabled,
  `allow_tools=false`; configured primary model `Gemma4-26B`.
- TTS route: real `OpenAIStreamingSpeechProvider`, model
  `gpt-4o-mini-tts-2025-12-15`, voice `marin`, mono 24 kHz PCM.
- Runtime profile: `real-agent-real-tts-no-chrome`, warm, direct Provider
  client on the current uncontrolled network.
- Browser, microphone, Gateway media, product P1/P2 composition, WebAudio,
  downlink and playout were not exercised.
- The disposable project had no Git remote. Its path and contents are not
  recorded here.

Credentials and API base remained in the pre-existing private mode-0600
runtime configuration. They were not copied to Git or serialized in the run
artifacts.

## Method and truth boundaries

The runner submitted each public prompt through the real formal Agent facade.
It fed sequenced `chat.delta` events to the generic conservative-lookahead
policy and started one benchmark-only real TTS request at the first eligible
sentence. It continued consuming the Agent stream through exactly one
`chat.final`, then required exact byte-prefix reconciliation. No synthesized
PCM was persisted or sent to product media.

The values have these meanings:

| Value | Truth label | Meaning |
|---|---|---|
| Agent start → first delta/candidate/final | **MEASURED** | Same-process monotonic observations on the real formal Agent stream |
| Candidate → final | **MEASURED** | Real remaining Agent stream time after candidate detection |
| TTS request → first PCM | **MEASURED** | Real benchmark-only Provider request on the candidate sentence |
| Candidate-path first PCM | **DERIVED** | Candidate observation plus the measured candidate TTS interval |
| Final-gated baseline first PCM | **ESTIMATED** | Counterfactual final time plus that same measured TTS interval; no second TTS request was made at final |
| Projected gain | **DERIVED** | Estimated final-gated first PCM minus derived candidate-path first PCM; algebraically the candidate→final interval |
| Browser first audible / playout complete | **UNKNOWN** | Browser and physical audio were not exercised |

The comparison therefore answers whether enough Agent-final wait exists to
justify building a high-risk product candidate. It does not prove the exact
audible gain such a candidate would achieve.

## Credited Provider-real pilot

All values are milliseconds. Candidate-path and baseline first PCM use the
truth labels above.

| Public case | First delta | Candidate | Final | Candidate→final | TTS request→first PCM | Candidate-path first PCM | Final-gated baseline first PCM | Projected gain |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| two-sentence explanation | 1701.3 | 1896.5 | 2073.7 | 177.2 | 1777.4 | 3673.9 | 3851.1 | 177.2 |
| three-sentence comparison | 499.0 | 683.3 | 1108.5 | 425.3 | 1125.5 | 1808.8 | 2234.0 | 425.3 |
| short technical summary | 502.9 | 698.7 | 826.8 | 128.1 | 896.6 | 1595.3 | 1723.4 | 128.1 |
| **p50** | **502.9** | **698.7** | **1108.5** | **177.2** | **1125.5** | **1808.8** | **2234.0** | **177.2** |
| **p95 nearest-rank** | **1701.3** | **1896.5** | **2073.7** | **425.3** | **1777.4** | **3673.9** | **3851.1** | **425.3** |

Outcomes were 3/3 completed, 3/3 exact prefix matches, zero prefix mismatches,
zero corrections and zero Agent/Tool/Task/history/product-audio/Browser effects
beyond the three explicitly authorized formal Agent submissions and three
benchmark-only TTS requests. The result schema's `agent_submissions=0` counter
means zero **product** Agent submissions: the benchmark driver invocation is
the declared measurement input, not a product side effect.

## Controlled screen and rejected diagnostic attempt

The controlled screen on the same source produced five positive candidates,
each with a controlled 750 ms candidate→final interval. The unclosed-code
fixture correctly produced no candidate, and the intentional prefix-mismatch
fixture correctly withheld latency credit. Those two negative oracles explain
the controlled reducer's local `STOP`; they are not Provider-pilot mismatches.
Every controlled case retained zero forbidden effects.

An earlier Provider pilot on `8a125a36fd1d2023e9af938d11d57cd4f1028994`
failed 0/3 before the first Agent event. A sanitized reproduction proved that
the benchmark session used `lv-stable-screen-*` while the real formal adapter
requires `lv-formal-*`. The contract was fixed with a failing boundary test in
`81903777f`; the failed run receives no timing or materiality credit.

Call accounting for the lane was eight formal Agent invocations and three TTS
requests: three Agent-only failed-pilot attempts, two Agent-only sanitized
diagnostics, and the credited three-Agent/three-TTS pilot. No retry was hidden
inside a credited attempt.

## Private artifact binding

The private artifacts remain outside Git. Their SHA-256 bindings are:

| Artifact | SHA-256 |
|---|---|
| controlled-v2 `run.json` | `007738aab02519a3f42d17a3f8fd1f6678c90e326383ee3fbc1d62ba98159745` |
| controlled-v2 `result.json` | `7c02325bf7e0d519def34bcc0afefcb524e6b2a7ac6f941f37045c3943705de4` |
| provider-pilot-v2 `run.json` | `deca847d58d076b1d074a750786573b88a7576e86358a7b38add68276a6220d3` |
| provider-pilot-v2 `result.json` | `a6a8a530e5fe8c6414da1e271e1d4cca0a3a7a7a3aba1c7ddc833ecfd1e37e8e` |
| `materiality-v2.json` | `51bfcaf9ac2d528cb5dc37f422ce73a365b0ea9319fe5c9c4532fbde94f841a2` |
| policy fixture | `99baa5ce5a842e7884a821b126a58698ec694838253e0dfdbbbd0f7a0959c33d` |
| Provider fixture | `ae459f8755d10c476ccbcbbeeb080899a313b10a2d7954d713f3d016d173068c` |
| runner | `87769cc162901f20576d6270895a97fdab3124434aeae315f16546519fa24242` |
| policy | `fb711c5f55a75ef5b93b37279dd9cad57541246d89cfaf8d61fd0b154534927f` |

Durable-location note (2026-08-22): the bound screen artifacts survive at
`/home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821/`
(`controlled-v2/`, `provider-pilot-v2/`, `materiality-v2.json`; the
unversioned `controlled/` and `provider-pilot/` directories hold the
superseded first pilot and receive no credit). All five SHA-256 bindings for
the credited v2 artifacts were re-computed against the surviving files on
2026-08-22 and match exactly. This near-project root is the durable archive;
volatile `/tmp` outputs must not be used for future runs.

## Interpretation and next action

The former 1.5–2.5 second ordinary-gain estimate is not supported by this
three-case real stream. One case exposed 425.3 ms, but the p50 was only
177.2 ms and the relative p50 only 7.43%. That headroom does not justify the
authority, cancellation, correction, P2 and Browser complexity of the planned
candidate.

The pure policy, probe points and no-Chrome runner remain useful diagnostic
assets. Product behavior remains unchanged. Reopening this lane requires a new
materiality hypothesis or a materially different representative workload; it
must not bypass the same exact-prefix and forbidden-effect gates. Exact word
timestamps/audio cursor support remains the explicit future prerequisite for
resume-without-repetition semantics, as recorded in the authority spec.
