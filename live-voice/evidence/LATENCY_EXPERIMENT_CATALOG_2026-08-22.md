# Live Voice latency experiment catalog

> Catalog date: 2026-08-22
>
> This is the canonical English reading route for the latency experiments run
> on 2026-08-20 and 2026-08-21. It is a dated evidence catalog, not the mutable
> product-status authority. [STATUS](../STATUS.md) owns current product
> judgement; the
> [optimization inventory](../roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md)
> owns headroom and execution order; exact-source result documents own their
> detailed branch-bound evidence.

## 1. How to read the numbers

The experiments intentionally use different lanes. Their values cannot be
pooled or added unless they share the same clock, workload and start/end
contract.

### 1.1 Truth labels

| Label | Meaning |
|---|---|
| `MEASURED` | Direct timestamp subtraction inside one compatible clock domain |
| `DERIVED` | Deterministic calculation from measured or controlled values |
| `CONTROLLED` | A fixture delay intentionally supplied by the experiment |
| `ESTIMATED` | Planning projection or counterfactual not directly exercised |
| `UNKNOWN` | The boundary was not observed and receives no numeric credit |
| `REPORTED_EXTERNAL` | Reported by Hongxing without a locally bound raw artifact |

### 1.2 Total-latency classes

| Class | Start → end | What it proves |
|---|---|---|
| Physical full experience | Browser capture ready → confirmed playout ACK | Real Browser/device path for that exact diagnostic turn |
| Browser-clock code E2E | Browser-observed EOT → confirmed ACK | Code path after endpointing on one Browser clock |
| Controlled round total | Fixture speech end/EOT → controlled confirmed ACK and next-turn ready | Causal owner-path composition under injected waits; not physical E2E |
| Component total | One exact component boundary → another | Only the named owner/mechanism |
| Projected perceived latency | Counterfactual or algebraic combination | Materiality estimate; not measured E2E |

The phrase “end-to-end” is therefore qualified everywhere below. Only
`LVL-00` exercised the Windows Browser, microphone and playout path. `LVL-05`
has complete-round totals, but those totals are deterministic and controlled.

### 1.3 Validation ladder

| Gate | Path | Credit |
|---|---|---|
| A — deterministic causal | Same source, controlled input, one changed variable, A/B/A when applicable, exact integrity accounting | Component mechanism and causal headroom only |
| B — real Agent/Provider | Real current dependency for the changed boundary, with fixed source/model/config | Real dependency component timing and semantic integrity |
| C — deployed Live Voice | JiuwenSwarm deployed, Live Voice enabled, optimization off/on, same environment/config/input, successful affected product output | Product-path acceptance for the declared environment |

A faster failed workflow is a regression, not an accepted optimization. Direct
audio/transcript injection is valid for Gates A/B but never substitutes for
Gate C when product wiring, Browser audio or human-perceived output is affected.

## 2. Branch map

These branches remain separate because each owns a different candidate or
measurement boundary.

| Branch | Head at catalog construction | Role |
|---|---|---|
| `0812_live_voice_w3_renan` | `c0f249d4363912c23835d3e133c7093459d2a25b` | Documentation hub, probe lineage and physical diagnostic origin |
| `latency/p2-bounded-pull-b` | `465a21625bf253729f00b7c84e6cc08e9bd746a2` | P2 bounded-pull implementation/result owner |
| `latency/vad-eot-causal-benchmark` | `d8686afc2f22462751ee2b46e6c885654fcaec7d` | Fixed-threshold VAD result owner |
| `latency/tts-provider-connection-reuse` | `5b87a59927f866c9a63c0bb774e4a9e2650628b9` | Rejected Provider connection-reuse result owner |
| `latency_checkpoint_accepted_optimizations` | `6843a4c233f926b73e1b4d972170409f9834c17e` | Controlled combined checkpoint and Semantic VAD spec owner |
| `latency/eot-stt-settlement-overlap` | `9b4034cd9d7123cdfe8880b2a06c368a6f375f7b` | EOT/STT materiality and TTS first-audio evidence carrier |
| `latency/stable-sentence-agent-tts` | `0c92b26264076d875a1247a0585dd8334898904f` | Stable-sentence screen/result owner |

The exact A/reference commits, detached benchmark worktrees and remote-tracking
refs are immutable evidence inputs. They are not documentation targets and do
not receive credit from later documentation commits.

## 3. Experiment index

| ID | Experiment or episode | Lane and total class | Headline result | Decision / next gate |
|---|---|---|---|---|
| `LVL-00` | Windows Chrome/WSL physical diagnostic A–G | Physical Browser; full experience and Browser-clock code E2E | EOT→ACK **9,832–25,234 ms**; capture-ready→ACK **15,352–32,512 ms**, `MEASURED` | Preliminary diagnostic only; incompatible manifest, dirty source and no formal population |
| `LVL-01` | P2 one-notification-per-RPC → bounded pull 16 | Deterministic Gate A; component total | p50 **864→86 / 4,348→344 / 8,658→615 ms** for 10/50/100 notifications, `MEASURED` | Causal candidate accepted; product acceptance open |
| `LVL-01C` | Hongxing deployed P2 validation | Deployed product episode; affected output failed | About **46%** faster response completion, `REPORTED_EXTERNAL`; TTS failed | Failed Gate C; repair atomic Media batch observation and rerun |
| `LVL-02` | Fixed VAD 1200→900/800 ms | Real Provider Gate B screen; component total | Successful cases saved roughly **285–412 ms**, `MEASURED`; candidates completed only 15/20 | Rejected: every 1000 ms natural-pause case split |
| `LVL-03` | TTS successor-capture ACK decoupling | Deterministic Gate A; first-source component total | First-source p50 saved **5.8 / 255.1 / 756.1 ms** at 0/250/750 ms ACK delay, `MEASURED` | Accepted for causal first-audio scope; settlement and physical output open |
| `LVL-04` | TTS Provider HTTPX client reuse | Real Provider Gate B; component total | Warm first PCM **832.0→889.9 ms**, a **57.8 ms / 7.0% regression**, `MEASURED` | Rejected and reverted; 0/3 warm connections reused |
| `LVL-05` | Combined P2 + TTS checkpoint | Deterministic Gate A; controlled round total | W1 **8,000→6,985**, W2 **14,900→10,240**, W3 **17,150→8,580 ms**, `CONTROLLED` + `DERIVED` | Controlled checkpoint improved; raw product observer was not covered |
| `LVL-06` | EOT/STT early-result waiter materiality | Deterministic Gate A; component total | Largest removable-gap p50 **0.885 ms**, fraction **0.015**, `MEASURED` + `DERIVED` | Stop: no material serial tail; no candidate B |
| `LVL-07` | Stable-sentence Agent→TTS overlap | Real Agent + real Provider screen; projected perceived latency | Projected gain p50 **177.2 ms**, p95 **425.3 ms**, `DERIVED`; final-gated baseline `ESTIMATED` | Stop for tested workloads; failed all three latency materiality gates |
| `LVL-08` | Provider-native Semantic VAD | Specified no-Browser Provider screen | Numeric result `UNKNOWN`; no run has executed | Next causal screen; retain 1200 ms fallback |

## 4. LVL-00 — physical Windows Chrome/WSL diagnostic

### 4.1 Question and rationale

This development exercise first asked whether the real Windows Chrome → WSL
deployment could capture, recognize, submit, answer, synthesize and play one
hands-free turn while exposing coarse stage timing. It also diagnosed the
`AUDIO_INPUT_GAP_EXCEEDED` failures that initially prevented any useful run.

The branch separated diagnostic instrumentation (`50c85bc41`) from the capture
repair (`ec78c3d55`). The repair stopped treating discontinuous AudioWorklet
render-frame scheduling as proof that non-empty microphone samples were lost.

### 4.2 Provenance and method

| Field | Value |
|---|---|
| Owner evidence | [LATENCY_EXPERIMENTS_2026-08-20.md](LATENCY_EXPERIMENTS_2026-08-20.md) |
| Branch | `0812_live_voice_w3_renan` |
| Observed product HEAD | `38d09aefec117f16fbeaafa7d47244d67acf644d` |
| Recorded run ID | `lv-diag-wsl-en-v1-20260820T140927Z-38d09aefe` |
| Source state | `product_code_dirty` |
| Browser/input | Windows Chrome; human speech through the real microphone path |
| Backend | WSL2; Python 3.11.15 |
| STT | OpenAI `gpt-4o-mini-transcribe-2025-12-15`; server VAD 1200 ms |
| TTS | OpenAI `gpt-4o-mini-tts-2025-12-15`, voice `marin` |
| Playout | WebAudio with declared 1000 ms lead |

The retained `run.json` declared Linux Chrome/WSLg and fixed WAV input, which
did not match the actual Windows Chrome/human-microphone method. The recorded
run directory also lacked a formal Browser/Gateway/Agent probe population.
Values were reconstructed from Browser-observed RPC/notification timestamps
and are diagnostic, not a compatible warm/cold baseline.

### 4.3 Inputs and stage-by-stage latency

| ID | Browser-recognized input | Semantic disposition |
|---|---|---|
| A | In two short sentences, please introduce Paris. | Valid no-Tool dialogue |
| B | What's the weather today in Paris? | Valid external-information dialogue |
| C | Can you search the best restaurants in Paris? | Valid longer external-information dialogue |
| D | Please check today's weather in London and answer in exactly two short sentences. | Valid bounded weather response |
| E | Please search for two exhibitions currently open in Paris and summarize them in exactly two short sentences. | Valid bounded external-information response |
| F | An exactly true short synthesis explaining why the sky appears blue. | Pipeline completed; intended wording not preserved by STT |
| G | Please search for two highly hated museums in Paris and answer with only their names. | Semantic STT failure: intended “highly rated” became “highly hated” |

All numbers are `MEASURED` milliseconds on one Browser clock.

| Stage | A | B | C | D | E | F | G |
|---|---:|---:|---:|---:|---:|---:|---:|
| Capture ready → EOT/STT requested | 5,520 | 8,437 | 5,616 | 10,656 | 11,928 | 7,151 | 11,470 |
| STT finalization RPC | 516 | 829 | 415 | 826 | 726 | 411 | 442 |
| STT final → `unified.submit` | 44 | 42 | 0 | 0 | 44 | 0 | -41 |
| Commit and round admission | 508 | 520 | 849 | 444 | 436 | 610 | 529 |
| Round accepted → first Agent text | 1,812 | 5,566 | 5,527 | 1,319 | 6,504 | 532 | 5,188 |
| First Agent text → final response | 3,348 | 4,549 | 9,055 | 2,017 | 3,696 | 4,056 | 5,340 |
| Final response → TTS request | 16 | 16 | 68 | 20 | 16 | 16 | 16 |
| Batch TTS generation | 1,672 | 935 | 1,200 | 912 | 1,241 | 964 | 1,120 |
| TTS ready → playout completion/ACK | 1,672 | 1,581 | 8,028 | 8,877 | 1,780 | 13,137 | 8,319 |
| ACK processing | 244 | 132 | 92 | 43 | 164 | 80 | 129 |
| **EOT → confirmed ACK** | **9,832** | **14,170** | **25,234** | **14,458** | **14,607** | **19,806** | **21,042** |
| **Capture ready → confirmed ACK** | **15,352** | **22,607** | **30,850** | **25,114** | **26,535** | **26,957** | **32,512** |

The -41 ms value is asynchronous overlap, not negative processing. Capture
includes speech duration, pauses and idle-ready time. TTS-ready→ACK includes
the full response audio duration and is not time-to-first-audio.

### 4.4 Outcome and artifact state

The seven timelines are useful hypothesis evidence. They receive no baseline
credit because the source was dirty, input identity differed across prompts,
the manifest was incompatible and the run-bound formal probe shards were
missing. F/G also demonstrate that lower latency cannot compensate for
semantic failure.

The private archive retains numerous `edbee4d3d/` and `38d09aefe/` diagnostic
directories. One older `edbee4d3d/...T104805Z...` directory contains a reduced
report, but it is not the A–G population and cannot replace the documented
Browser reconstruction. All such artifacts remain `DIAGNOSTIC` or
`FAILED_WORKFLOW`.

## 5. LVL-01/LVL-01C — P2 bounded notification pull

### 5.1 Mechanism and rationale

The legacy Web owner consumed one retained P2 notification per serialized RPC.
At about 85 ms per cycle, the post-model portion of a 64-item backlog can add
about 5.44 seconds. Bounded pull was chosen because it attacks the measured
transport cause without dropping deltas, adding concurrent polls or introducing
server-push replay/backpressure authority.

The candidate drains at most 16 already queued notifications, preserves publish
order, stops after an authoritative barrier and validates the complete batch
before exposing its first item.

### 5.2 Causal A1/B/A2 method

| Population | Source | Run ID | Private report SHA-256 |
|---|---|---|---|
| A1 | `31f9209d66682d19745acd1d2c15a16b59fc75e2` | `p2-a1-r-batch16-20260821T001711Z-31f9209d6` | `70230bd63fe9f9befc39d7cfc4297873c1e862b3bf9b07c5e8ed3fe2d98f5bba` |
| B | `c1b4a47f51b0b200b12e2e544617577d7f307c69` | `p2-b-batch16-20260821T002105Z-c1b4a47f5` | `3d5a03437f134cd8d99a518cc6ad3bd51303843c4dbca804381c15f6b4016250` |
| A2 | `31f9209d66682d19745acd1d2c15a16b59fc75e2` | `p2-a2-r-batch16-20260821T002121Z-31f9209d6` | `0f89309dd4434019aea3d9bc888840bdc2c7cef328705bbb67b441cfa335d4f5` |

The real compiled Web P2 owner consumed deterministic 10/50/100-notification
backlogs through a fake transport with a controlled 85 ms delay per RPC. Five
attempts ran per workload and population. The measured component total was
model-complete → authoritative final consumed.

| Notifications | A1 RPC / p50 / p95 | B RPC / p50 / p95 | A2 RPC / p50 / p95 | B p50 gain vs A1 |
|---:|---:|---:|---:|---:|
| 10 | 50 / 864.293 / 873.600 ms | 5 / 85.823 / 91.008 ms | 50 / 860.659 / 867.540 ms | 778.470 ms / 90.070% |
| 50 | 250 / 4,348.227 / 4,351.440 ms | 20 / 343.704 / 349.175 ms | 250 / 4,305.376 / 4,343.331 ms | 4,004.523 ms / 92.096% |
| 100 | 500 / 8,658.478 / 8,700.760 ms | 35 / 615.209 / 617.248 ms | 500 / 8,643.205 / 8,681.116 ms | 8,043.269 ms / 92.895% |

All three populations completed 15/15 attempts with exact ordering and zero
Agent, Tool, Task, history, audio, ACK or submission effects. This is
`MEASURED` component causality only.

The owner record is branch-bound at
`latency/p2-bounded-pull-b:live-voice/evidence/P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md`.
Two earlier A1 reports at `a9142dd2d` and `c8f24834b` remain diagnostic: the
first lacked the prospective batch-size input; the second exposed a
candidate-neutral runner oracle that still coupled operation count to delivered
item count.

### 5.3 Deployed validation failure

Hongxing later reported approximately 46% faster response completion in a
deployed run. That number is `REPORTED_EXTERNAL`: exact branch, source, logs and
raw report have not yet been bound locally.

The workflow nevertheless failed TTS with
`SPEECH_OPERATION_NOT_AUTHORIZED`; retry did not recover and the page required
refresh. Current source explains the defect: the Web parser validates the whole
`notification_batch`, but `DedicatedMediaProductRegistry.observe_agent_response()`
observes only a top-level single `notification`. It ignores the nested final
notification that establishes synthesis authorization.

The P2 change is therefore a causal candidate with failed Gate C, not a
complete optimization. Repair requires atomic whole-batch validation, zero
partial authorization for invalid batches, ordered processing of every valid
item and final-item TTS authorization. Then rerun the same deployed short,
medium and long workloads with optimization off/on and successful TTS/playout.

## 6. LVL-02 — fixed-threshold VAD/EOT screen

### 6.1 Method and rationale

The fixed 1200 ms server-VAD silence threshold was an obvious input-latency
hypothesis, but lowering it was permitted only if natural pauses remained one
complete turn. A private corpus replaced one frozen boundary with exact
0/300/600/1000 ms pauses and sent 48 kHz PCM through the real OpenAI streaming
Provider in paced 20 ms frames.

| Field | Value |
|---|---|
| Owner branch | `latency/vad-eot-causal-benchmark` |
| Runner source | `e2773bec2740e933721d1f598e06978b5b476860` |
| Product base | `465a21625bf253729f00b7c84e6cc08e9bd746a2` |
| Provider/model | `OpenAIStreamingSpeechProvider` / `gpt-4o-mini-transcribe-2025-12-15` |
| Formal run | `vad-eot-tier2-formal-20260821t032202` |
| Formal report SHA-256 | `2132af15626c4513428a025860d508312e922bd10e69fdca53181a58f7b7e6f9` |
| Pilot report SHA-256 | `89087d4f5347233750e9f74ba8be8aedfcf4a4aaf3bda4bf83ecb959ecafec75` |

The order was A1/1200 → E1/900 → E2/800 → A2/1200, five attempts per pause
case/configuration. A sample needed one exact started/stopped/committed/final
turn, complete transcript, valid pacing and clean Provider cleanup.

### 6.2 Result and decision

| Configuration | Completed | Aggregate final voiced frame→EOT p50 | Aggregate EOT→STT-final p50 | Aggregate voiced frame→STT-final p50 |
|---|---:|---:|---:|---:|
| A1 / 1200 ms | 20/20 | 1,508.675 ms | 388.360 ms | 1,907.360 ms |
| E1 / 900 ms | 15/20 | 1,216.858 ms | 410.643 ms | 1,631.459 ms |
| E2 / 800 ms | 15/20 | 1,096.765 ms | 389.902 ms | 1,503.506 ms |
| A2 / 1200 ms | 20/20 | 1,503.845 ms | 404.256 ms | 1,917.071 ms |

The successful candidate turns exposed roughly 285–412 ms of endpointing
headroom, but all five 1000 ms pause cases failed under both 900 and 800 ms with
`EARLY_EOT`. The fixed-threshold candidate is rejected and the 1200 ms default
remains. The ten failures stay in the denominator; a faster 15/20 is not an
optimization.

Earlier VAD pilots/formals under `vad-eot/` are `DIAGNOSTIC`, `INVALID` or
`SUPERSEDED`. They found low-energy-tail classification and additive-pause
corpus defects that were corrected before the credited Tier-2 pair.

Detailed evidence is branch-bound at
`latency/vad-eot-causal-benchmark:live-voice/evidence/VAD_EOT_CAUSAL_RESULT_2026-08-21.md`.

## 7. LVL-03 — TTS successor-capture ACK decoupling

### 7.1 Mechanism and method

The original route waited for successor-capture readiness before opening TTS
downlink. The candidate starts downlink and bounded successor preparation
concurrently. It does not make the ACK itself earlier and it still waits for
bounded successor readiness before terminal receipt settlement.

The deterministic runner drove the real `ProductP1VoiceRouteOwner` with
content-free fakes. It used 0/250/750/1100 ms controlled ACK delays and five
attempts per delay.

| Population | Source | Run ID | Private report SHA-256 |
|---|---|---|---|
| A1 | `2651b0dd8ae594f342fe3262ca1b89d44456f2e8` | `tts-a1-20260821T093944Z-2651b0dd8a` | `2a1dec9af1e89a3fdd2570c39031e1573d0353055207a89b22306c5a3e34f6eb` |
| B2 | `cd4d1b7d34a529839ecf219f7f2eb567fedce4d2` | `tts-b2-20260821T101119Z-cd4d1b7d34` | `59eb00c801a6745c946dfab2cb92443ff6819721fb85ebafd435a8a9c930c671` |
| A2 | `2651b0dd8ae594f342fe3262ca1b89d44456f2e8` | `tts-a2-20260821T100346Z-2651b0dd8a` | `87e67ebbeb3a6ea043361c25eb6e0cbd8d9c2dfc439bc83aab7e1e1822a67107` |

An earlier B at `56a1fc4eb` was superseded after truthful non-duplex receipt
review and receives no final source credit.

### 7.2 First-source result

| ACK delay | A1 p50 / p95 | B2 p50 / p95 | A2 p50 / p95 | B2 p50 gain vs A1 |
|---:|---:|---:|---:|---:|
| 0 ms | 6.746 / 10.344 ms | 0.965 / 2.949 ms | 6.858 / 10.254 ms | 5.781 ms / 85.7% |
| 250 ms | 255.597 / 256.608 ms | 0.486 / 0.783 ms | 254.980 / 256.037 ms | 255.111 ms / 99.81% |
| 750 ms | 756.542 / 756.958 ms | 0.476 / 0.540 ms | 754.721 / 755.690 ms | 756.066 ms / 99.94% |
| 1100 ms | failed before downlink | 0.494 / 0.649 ms | failed before downlink | outcome class changed |

At 1100 ms, B2 rendered once then reported truthful degraded interruption;
that is reliability/ordering evidence rather than a comparable successful-turn
delta. All reports had zero invalid/unknown attempts and zero Agent, Tool, Task
or history effects.

Terminal receipt still followed the ACK: B2 receipt p50 was 11.645/254.023/
753.939/1006.918 ms for 0/250/750/1100 ms. The change is accepted only for
first-source causal component scope. Physical Browser/audible output, Provider,
network and full-round credit remain open.

Detailed evidence is branch-bound at
`latency/eot-stt-settlement-overlap:live-voice/evidence/TTS_FIRST_AUDIO_CAUSAL_RESULT_2026-08-21.md`.

## 8. LVL-04 — TTS Provider connection reuse

### 8.1 Approach

The candidate retained one application-level HTTPX `AsyncClient` across
successive OpenAI streaming TTS requests. The hypothesis was that warm TCP/TLS
reuse would shorten Provider request→first PCM. A trace predicate required all
three warm B attempts to reuse a connection before any latency credit.

| Population | Source | Calls | Private report SHA-256 | Role |
|---|---|---:|---|---|
| pilot | `e614a0d3bd431e8ee1a6cf55a7ea6d3ff7ccf3c2` | 2 | `0bd4bc65726ab73f31e87d1fb3235d31e598359f0dddcebef4e4ee26839025c5` | Historical diagnostic |
| A1 | `e614a0d3bd431e8ee1a6cf55a7ea6d3ff7ccf3c2` | 6 | `0700ce15c2ad304ff04e08f63537e1a07ed5794f7d5a307f04769f8000050741` | Historical control |
| A1-v2 | `e915e8dc0b414fafccf78a46d450a0b8d0633f5e` | 6 | `f87be3ec59af56e8786f0988157dcd889ecd9a8134f751d7ff8bb35de1231db3` | Credited control |
| B | `72f0b15795018a770ed61d0e3f589ed1b8a942cd` | 6 | `393e8bbbdc233b284c205ce9db95f0e7b16b31f3a86e37ae9b1058b5935ed187` | Credited rejected candidate |
| A2 | not run | 0 | not applicable | B failed mandatory reuse predicate |

### 8.2 Real-Provider result

| Position | Metric | A1-v2 p50 | B p50 | B−A |
|---|---|---:|---:|---:|
| cold | response headers | 1,023.1 ms | 1,110.1 ms | +86.9 ms |
| cold | first Provider audio | 1,025.0 ms | 1,111.4 ms | +86.4 ms |
| cold | first PCM | 1,039.6 ms | 1,116.8 ms | +77.2 ms |
| cold | completed | 1,808.3 ms | 1,812.8 ms | +4.5 ms |
| warm | response headers | 825.4 ms | 883.6 ms | +58.1 ms |
| warm | first Provider audio | 826.7 ms | 884.8 ms | +58.0 ms |
| warm | first PCM | 832.0 ms | 889.9 ms | **+57.8 ms / +7.0%** |
| warm | completed | 1,718.1 ms | 1,732.6 ms | +14.5 ms |

All B attempts opened fresh TCP/TLS connections; warm reuse was 0/3. The
candidate removed no connection stage and regressed the acceptance metric. It
was rejected and request-scoped client lifecycle restored at
`ddd845e561145cdb1aa2eb37d6ea9c57633494f6`.

Premature response close after `speech.audio.done` is only a hypothesis. A
future bounded EOF-drain experiment must first prove actual reuse; it inherits
no numeric credit from this failure.

Detailed evidence is branch-bound at
`latency/tts-provider-connection-reuse:live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md`.

## 9. LVL-05 — combined accepted-optimizations checkpoint

### 9.1 Purpose and controlled method

The checkpoint composes the P2 bounded-pull and TTS successor-ACK changes in
one deterministic scheduler to verify that their component gains coexist and
do not merely shift the wait within the controlled round. It drives real P1/P2
owners but injects STT, admission, Agent/model, TTS generation, RPC, ACK and PCM
playout durations.

| Population | Source | Run ID | Private report SHA-256 |
|---|---|---|---|
| A1 | `1b0802cae9a6718c0d3326c1292f7475fdefe08c` | `accepted-checkpoint-v2-a1-20260821` | `3629ebe1048365d139f07e8f3bad3421ab89584986da5d256b1ea14f12416063` |
| B | `52f7bc54353fc2c212aab1246941674feb821a9e` | `accepted-checkpoint-v2-b-20260821` | `6ee6a34766aac5e2b1277203a3064af2fc653612a2e7e2f01f0baeff9c588f04` |
| A2 | `1b0802cae9a6718c0d3326c1292f7475fdefe08c` | `accepted-checkpoint-v2-a2-20260821` | `792c7bd087fafa4de9d52c595086e72f26f120e3ab782792f2aa6ea4a5257dd8` |
| Comparison | A1/B/A2 above | checkpoint v2 comparison | `94b5916d915b1b0c60e76ca169ce2a19e32aa44ac8097456176dac556b1e5200` |

### 9.2 Stage-by-stage p50

All values are `CONTROLLED` measurements or `DERIVED` deltas in milliseconds.
A1 and A2 are identical.

| Stage | W1 A→B | W2 A→B | W3 A→B | Interpretation |
|---|---:|---:|---:|---|
| STT settlement | 400→400 | 400→400 | 400→400 | Unchanged external fixture |
| Admission | 500→500 | 500→500 | 500→500 | Unchanged external fixture |
| Agent/model | 2,000→2,000 | 2,000→2,000 | 2,000→2,000 | Unchanged external fixture |
| P2 final delivery | 850→85 | 4,250→340 | 8,500→680 | Gain 765/3,910/7,820 ms |
| TTS generation | 1,000→1,000 | 1,000→1,000 | 1,000→1,000 | Unchanged external fixture |
| TTS ready→downlink | 250→0 | 750→0 | 750→0 | Gain 250/750/750 ms |
| Downlink→first source | 0→0 | 0→0 | 0→0 | No injected residual |
| First source→playout | 3,000→3,000 | 6,000→6,000 | 4,000→4,000 | Controlled PCM duration |
| Playout→confirmed ACK | 0→0 | 0→0 | 0→0 | No injected residual |
| **Controlled round total** | **8,000→6,985** | **14,900→10,240** | **17,150→8,580** | Gain **1,015 / 4,660 / 8,570 ms** |

Each A1/B/A2 population completed 15/15 attempts; A1/A2 drift was zero. This
proves controlled composition only. It excluded real Provider/network,
Agent/model, Chrome/device and human-perceived first audio. Crucially, its Web
owner fixture did not exercise the raw Gateway Media observer that later caused
the deployed P2 TTS-authorization failure. The checkpoint cannot grant P2
product acceptance.

Detailed evidence is branch-bound at
`latency_checkpoint_accepted_optimizations:live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md`.
The unversioned checkpoint archive is superseded by `accepted-checkpoint-20260821-v2/`.

## 10. LVL-06 — EOT/STT settlement materiality

### 10.1 Question and method

The screen asked whether local route settlement serialized a material wait
before retrieval of the already-ready streaming STT final. The eligible
headroom begins only when both independent facts are ready:

```text
removable serial gap = result returned - max(route settled, Provider final ready)
```

The deterministic Node runner exercised the real Product P1 owner and registry
result seam with 50/500 ms local and Provider fixture combinations. Five
attempts ran per fixture.

| Field | Value |
|---|---|
| Source | `8e5dab8b8c6651b2be784cf103df9239a93814a0` |
| Run ID | `eot-stt-complete-contract-final` |
| Total attempts | 20/20 completed, exact and cleanup-complete |
| Forbidden effects | Zero Agent, Tool, Task, TTS, Browser, WebAudio, microphone, history or product submission |
| Credited raw report | `LOST`; it was written under `/tmp/live-voice-eot-stt-final-Up1qNe/` |
| Surviving earlier diagnostic | `eot-stt-a1-materiality-bdd57bb6d.json`, SHA-256 `ece322a06e199623e78cacb12cd89f2beed8c6bd44ca4fee5cc4c527726838c0` |

### 10.2 Result

| Fixture local/Provider | Diagnostic settled→return p50 | EOT→final p50 | Removable gap p50 | Fraction p50 |
|---|---:|---:|---:|---:|
| 50/50 ms | 0.779 ms | 53.479 ms | 0.779 ms | 0.015 |
| 500/50 ms | 0.880 ms | 503.173 ms | 0.880 ms | 0.002 |
| 50/500 ms | 450.782 ms | 502.774 ms | 0.885 ms | 0.002 |
| 500/500 ms | 0.802 ms | 503.564 ms | 0.802 ms | 0.002 |

The 450.782 ms diagnostic interval is legitimate remaining Provider wait, not
removable serialization: after both join inputs were ready, only 0.885 ms
remained. The predeclared gates were at least 80 ms and fraction 0.10. Neither
passed, so no B/A2 or product protocol change was authorized.

Detailed sanitized evidence is branch-bound at
`latency/eot-stt-settlement-overlap:live-voice/evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md`.
The missing final raw report weakens re-reduction availability, not the reviewed
`NO_MATERIAL_SERIAL_GAP` decision.

## 11. LVL-07 — stable-sentence Agent-to-TTS screen

### 11.1 Approach and truth boundary

The screen asked whether the real formal Agent emitted an exact-prefix complete
sentence early enough to justify high-risk Runtime/P2/Browser product wiring.
It ran the real Agent stream and one benchmark-only real TTS request on the
first eligible sentence, then required exact byte-prefix reconciliation against
`chat.final`.

Agent candidate/final and TTS request→first PCM are `MEASURED`. Candidate-path
first PCM and projected gain are `DERIVED`. The counterfactual final-gated first
PCM is `ESTIMATED`. Browser first audible and playout are `UNKNOWN`.

| Field | Value |
|---|---|
| JiuwenSwarm source | `81903777f8dccb40ba2cb70fbe9b28d28d86c7f5` |
| Agent-Core source | `94e10cb6102c36fe78a64547957c0def97299273` |
| Profile | real formal Agent + real OpenAI TTS, no Chrome |
| Agent model | configured `Gemma4-26B`, tools disabled |
| TTS | `gpt-4o-mini-tts-2025-12-15`, voice `marin` |
| Credited attempts | 3/3 completed; 3/3 exact prefix; zero forbidden effects |

### 11.2 Credited Provider-real pilot

| Public case | Candidate→final | TTS request→first PCM | Candidate-path first PCM | Estimated final-gated first PCM | Projected gain |
|---|---:|---:|---:|---:|---:|
| Two-sentence explanation | 177.2 ms | 1,777.4 ms | 3,673.9 ms | 3,851.1 ms | 177.2 ms |
| Three-sentence comparison | 425.3 ms | 1,125.5 ms | 1,808.8 ms | 2,234.0 ms | 425.3 ms |
| Short technical summary | 128.1 ms | 896.6 ms | 1,595.3 ms | 1,723.4 ms | 128.1 ms |
| **p50** | **177.2 ms** | **1,125.5 ms** | **1,808.8 ms** | **2,234.0 ms** | **177.2 ms / 7.43%** |
| **p95** | **425.3 ms** | **1,777.4 ms** | **3,673.9 ms** | **3,851.1 ms** | **425.3 ms** |

The p50 gates required candidate→final at least 500 ms, projected gain at least
400 ms and relative gain at least 10%. All three failed. The screen stopped
before authority, cancellation, correction, P2 and Browser work. This is a stop
for the tested workloads, not proof that every possible long-form response has
no headroom.

An earlier real-Provider pilot failed 0/3 because its benchmark session prefix
did not satisfy the formal adapter. It receives no timing credit. The corrected
credited v2 artifacts survive under
`stable-sentence-screen-20260821/{controlled-v2,provider-pilot-v2}` with hashes
bound in the owner evidence; unversioned directories are superseded.

Detailed evidence is branch-bound at
`latency/stable-sentence-agent-tts:live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_CAUSAL_RESULT_2026-08-21.md`.

## 12. LVL-08 — Provider-native Semantic VAD

This candidate is specified but has not run. It asks whether Provider-native
semantic turn detection can recover part of the 285–412 ms fixed-VAD headroom
while a 1200 ms fallback preserves natural pauses, without an extra model RPC.

| Field | Current value |
|---|---|
| Owner | P1 Interaction Intelligence / streaming speech Provider adapter |
| Planned comparison | Separate `auto` and `high` A/B/A blocks |
| Browser requirement | None for the causal screen; Gate C remains later |
| Product default | Retains 1200 ms fallback |
| Numeric result | `UNKNOWN`; no attempt has executed |
| Credit | None |

The specification and plan remain branch-bound at
`latency_checkpoint_accepted_optimizations:live-voice/roadmap/SEMANTIC_VAD_CAUSAL_BENCHMARK_SPEC_2026-08-21.md`
and its adjacent implementation plan.

## 13. What has and has not been measured end to end

| Question | Current answer |
|---|---|
| Do we have real Browser/device capture-ready→ACK timings? | Yes, only the seven `LVL-00` development diagnostics: 15.352–32.512 s. They are not a compatible baseline. |
| Do we have real Browser-clock EOT→ACK timings? | Yes, only `LVL-00`: 9.832–25.234 s, with semantic/run-integrity limitations. |
| Do we have a clean physical A/B/A for any optimization? | No. |
| Do we have full-round causal composition timings? | Yes, `LVL-05`, but they are controlled 6.985–10.240 s B totals, not physical E2E. |
| Do we have accepted real-Provider component timings? | Yes for the VAD rejection, connection-reuse rejection and stable-sentence materiality stop; each excludes Browser/full E2E. |
| Is approximately 46% a locally verified product gain? | No. It is `REPORTED_EXTERNAL`, and that run failed TTS authorization. |

## 14. Artifact retention summary

The private archive is
`/home/renan/openJiuwen-ai/live-voice-latency-runs/`. Its README is the full
artifact ledger. The repository stores only sanitized evidence.

| Experiment | Artifact state |
|---|---|
| LVL-00 | Diagnostic/failed-workflow directories survive; no compatible A–G raw population |
| LVL-01 | Credited A1/B/A2 reports survive with freshly verified hashes; earlier A1 reports are diagnostic |
| LVL-01C | No locally bound raw artifact; external report only |
| LVL-02 | Credited Tier-2 pilot/formal reports and corpus survive; earlier attempts are diagnostic/invalid/superseded |
| LVL-03 | Credited A1/B2/A2 reports survive; earlier B is superseded |
| LVL-04 | Pilot/A1/A1-v2/B survive; A1-v2/B are credited to the rejection |
| LVL-05 | Credited `accepted-checkpoint-20260821-v2/` population survives; unversioned population is superseded |
| LVL-06 | Credited final raw report is lost; sanitized final evidence survives; earlier diagnostic raw survives |
| LVL-07 | Credited v2 artifacts survive with verified bindings; unversioned pilot directories are superseded |
| LVL-08 | No run artifact exists |

## 15. Current decision route

1. Repair P2 Media observation so an entire `notification_batch` is validated
   atomically and processed in order, including final TTS authorization.
2. Run deployed Live Voice off/on with the agreed short, medium and long
   prompts. Require successful response/task outcome and TTS/playout; record a
   stage and total waterfall.
3. In parallel, run the already specified Provider-native Semantic VAD causal
   screen with the 1200 ms fallback and natural-pause integrity gates.
4. Use the deployed waterfall to choose whether physical first-audible
   (Adaptive WebAudio startup) or terminal settlement/next-turn readiness owns
   the next material residual. Do not add their estimates.
5. Keep connection reuse, fixed-threshold VAD, EOT early-wait and the tested
   stable-sentence packet closed unless a new reviewed mechanism or workload
   hypothesis changes the materiality question.

Every future result uses
[LATENCY_EXPERIMENT_RECORD_TEMPLATE.md](LATENCY_EXPERIMENT_RECORD_TEMPLATE.md)
and writes raw artifacts to the durable private archive rather than `/tmp`.
