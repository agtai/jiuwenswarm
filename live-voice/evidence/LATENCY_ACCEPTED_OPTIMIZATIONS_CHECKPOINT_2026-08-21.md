# Accepted Optimizations Latency Checkpoint

Decision: **IMPROVED**

## Headline end-to-end totals

| Workload | A1 p50/p95 ms | B p50/p95 ms | A2 p50/p95 ms | Absolute gain vs A1 | Relative gain | Baseline drift |
|---|---:|---:|---:|---:|---:|---:|
| W1 short dialogue | 8000/8000 | 6985/6985 | 8000/8000 | 1015 ms | 12.688% | 0 ms |
| W2 long dialogue | 14900/14900 | 10240/10240 | 14900/14900 | 4660 ms | 31.275% | 0 ms |
| W3 Tool-style | 17150/17150 | 8580/8580 | 17150/17150 | 8570 ms | 49.971% | 0 ms |

These are deterministic no-Chrome owner-checkpoint totals from `speech_end` to
`confirmed_ack_and_next_turn_ready`. They measure real P1/P2 owner execution on
one injected monotonic scheduler with controlled external waits; they are not
real Provider, network, Browser-device, Agent-model, or human-perception
latencies.

## Exact inputs

| Population | Run | Source commit | Raw report SHA-256 |
|---|---|---|---|
| A1 | accepted-checkpoint-v2-a1-20260821 | 1b0802cae9a6718c0d3326c1292f7475fdefe08c | 3629ebe1048365d139f07e8f3bad3421ab89584986da5d256b1ea14f12416063 |
| B | accepted-checkpoint-v2-b-20260821 | 52f7bc54353fc2c212aab1246941674feb821a9e | 6ee6a34766aac5e2b1277203a3064af2fc653612a2e7e2f01f0baeff9c588f04 |
| A2 | accepted-checkpoint-v2-a2-20260821 | 1b0802cae9a6718c0d3326c1292f7475fdefe08c | 792c7bd087fafa4de9d52c595086e72f26f120e3ab782792f2aa6ea4a5257dd8 |

## Measured stages and derived deltas

| Workload | Stage | A1 p50/p95 ms | B p50/p95 ms | A2 p50/p95 ms | B−A1 p50 ms | B−A2 p50 ms | B−A1 p95 ms | B−A2 p95 ms | B−A1 % | B−A2 % | A drift % | Result | Truth |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| W1 | stt_settlement | 400.000/400.000 | 400.000/400.000 | 400.000/400.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W1 | admission | 500.000/500.000 | 500.000/500.000 | 500.000/500.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W1 | agent_model | 2000.000/2000.000 | 2000.000/2000.000 | 2000.000/2000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W1 | p2_final_delivery | 850.000/850.000 | 85.000/85.000 | 850.000/850.000 | -765.000 | -765.000 | -765.000 | -765.000 | -90.000 | -90.000 | 0.000 | IMPROVED | MEASURED + DERIVED |
| W1 | tts_generation | 1000.000/1000.000 | 1000.000/1000.000 | 1000.000/1000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W1 | tts_ready_to_downlink | 250.000/250.000 | 0.000/0.000 | 250.000/250.000 | -250.000 | -250.000 | -250.000 | -250.000 | -100.000 | -100.000 | 0.000 | IMPROVED | MEASURED + DERIVED |
| W1 | downlink_to_first_source | 0.000/0.000 | 0.000/0.000 | 0.000/0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a | UNCHANGED | MEASURED + DERIVED |
| W1 | first_source_to_playout | 3000.000/3000.000 | 3000.000/3000.000 | 3000.000/3000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W1 | playout_to_confirmed_ack | 0.000/0.000 | 0.000/0.000 | 0.000/0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a | UNCHANGED | MEASURED + DERIVED |
| W1 | round_total | 8000.000/8000.000 | 6985.000/6985.000 | 8000.000/8000.000 | -1015.000 | -1015.000 | -1015.000 | -1015.000 | -12.688 | -12.688 | 0.000 | IMPROVED | MEASURED + DERIVED |
| W2 | stt_settlement | 400.000/400.000 | 400.000/400.000 | 400.000/400.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W2 | admission | 500.000/500.000 | 500.000/500.000 | 500.000/500.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W2 | agent_model | 2000.000/2000.000 | 2000.000/2000.000 | 2000.000/2000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W2 | p2_final_delivery | 4250.000/4250.000 | 340.000/340.000 | 4250.000/4250.000 | -3910.000 | -3910.000 | -3910.000 | -3910.000 | -92.000 | -92.000 | 0.000 | IMPROVED | MEASURED + DERIVED |
| W2 | tts_generation | 1000.000/1000.000 | 1000.000/1000.000 | 1000.000/1000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W2 | tts_ready_to_downlink | 750.000/750.000 | 0.000/0.000 | 750.000/750.000 | -750.000 | -750.000 | -750.000 | -750.000 | -100.000 | -100.000 | 0.000 | IMPROVED | MEASURED + DERIVED |
| W2 | downlink_to_first_source | 0.000/0.000 | 0.000/0.000 | 0.000/0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a | UNCHANGED | MEASURED + DERIVED |
| W2 | first_source_to_playout | 6000.000/6000.000 | 6000.000/6000.000 | 6000.000/6000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W2 | playout_to_confirmed_ack | 0.000/0.000 | 0.000/0.000 | 0.000/0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a | UNCHANGED | MEASURED + DERIVED |
| W2 | round_total | 14900.000/14900.000 | 10240.000/10240.000 | 14900.000/14900.000 | -4660.000 | -4660.000 | -4660.000 | -4660.000 | -31.275 | -31.275 | 0.000 | IMPROVED | MEASURED + DERIVED |
| W3 | stt_settlement | 400.000/400.000 | 400.000/400.000 | 400.000/400.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W3 | admission | 500.000/500.000 | 500.000/500.000 | 500.000/500.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W3 | agent_model | 2000.000/2000.000 | 2000.000/2000.000 | 2000.000/2000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W3 | p2_final_delivery | 8500.000/8500.000 | 680.000/680.000 | 8500.000/8500.000 | -7820.000 | -7820.000 | -7820.000 | -7820.000 | -92.000 | -92.000 | 0.000 | IMPROVED | MEASURED + DERIVED |
| W3 | tts_generation | 1000.000/1000.000 | 1000.000/1000.000 | 1000.000/1000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W3 | tts_ready_to_downlink | 750.000/750.000 | 0.000/0.000 | 750.000/750.000 | -750.000 | -750.000 | -750.000 | -750.000 | -100.000 | -100.000 | 0.000 | IMPROVED | MEASURED + DERIVED |
| W3 | downlink_to_first_source | 0.000/0.000 | 0.000/0.000 | 0.000/0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a | UNCHANGED | MEASURED + DERIVED |
| W3 | first_source_to_playout | 4000.000/4000.000 | 4000.000/4000.000 | 4000.000/4000.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | UNCHANGED | MEASURED + DERIVED |
| W3 | playout_to_confirmed_ack | 0.000/0.000 | 0.000/0.000 | 0.000/0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a | UNCHANGED | MEASURED + DERIVED |
| W3 | round_total | 17150.000/17150.000 | 8580.000/8580.000 | 17150.000/17150.000 | -8570.000 | -8570.000 | -8570.000 | -8570.000 | -49.971 | -49.971 | 0.000 | IMPROVED | MEASURED + DERIVED |

## Measured B residual and share of total

| Workload | Stage | B p50 ms | Share of B round total | Truth |
|---|---|---:|---:|---|
| W1 | stt_settlement | 400.000 | 5.727% | MEASURED + DERIVED |
| W1 | admission | 500.000 | 7.158% | MEASURED + DERIVED |
| W1 | agent_model | 2000.000 | 28.633% | MEASURED + DERIVED |
| W1 | p2_final_delivery | 85.000 | 1.217% | MEASURED + DERIVED |
| W1 | tts_generation | 1000.000 | 14.316% | MEASURED + DERIVED |
| W1 | tts_ready_to_downlink | 0.000 | 0.000% | MEASURED + DERIVED |
| W1 | downlink_to_first_source | 0.000 | 0.000% | MEASURED + DERIVED |
| W1 | first_source_to_playout | 3000.000 | 42.949% | MEASURED + DERIVED |
| W1 | playout_to_confirmed_ack | 0.000 | 0.000% | MEASURED + DERIVED |
| W1 | round_total | 6985.000 | 100.000% | MEASURED + DERIVED |
| W2 | stt_settlement | 400.000 | 3.906% | MEASURED + DERIVED |
| W2 | admission | 500.000 | 4.883% | MEASURED + DERIVED |
| W2 | agent_model | 2000.000 | 19.531% | MEASURED + DERIVED |
| W2 | p2_final_delivery | 340.000 | 3.320% | MEASURED + DERIVED |
| W2 | tts_generation | 1000.000 | 9.766% | MEASURED + DERIVED |
| W2 | tts_ready_to_downlink | 0.000 | 0.000% | MEASURED + DERIVED |
| W2 | downlink_to_first_source | 0.000 | 0.000% | MEASURED + DERIVED |
| W2 | first_source_to_playout | 6000.000 | 58.594% | MEASURED + DERIVED |
| W2 | playout_to_confirmed_ack | 0.000 | 0.000% | MEASURED + DERIVED |
| W2 | round_total | 10240.000 | 100.000% | MEASURED + DERIVED |
| W3 | stt_settlement | 400.000 | 4.662% | MEASURED + DERIVED |
| W3 | admission | 500.000 | 5.828% | MEASURED + DERIVED |
| W3 | agent_model | 2000.000 | 23.310% | MEASURED + DERIVED |
| W3 | p2_final_delivery | 680.000 | 7.925% | MEASURED + DERIVED |
| W3 | tts_generation | 1000.000 | 11.655% | MEASURED + DERIVED |
| W3 | tts_ready_to_downlink | 0.000 | 0.000% | MEASURED + DERIVED |
| W3 | downlink_to_first_source | 0.000 | 0.000% | MEASURED + DERIVED |
| W3 | first_source_to_playout | 4000.000 | 46.620% | MEASURED + DERIVED |
| W3 | playout_to_confirmed_ack | 0.000 | 0.000% | MEASURED + DERIVED |
| W3 | round_total | 8580.000 | 100.000% | MEASURED + DERIVED |

## Proven removable headroom

Only the compatible A1/B/A2 deltas above are proven removable. They cover bounded P2 pulls and successor-ACK/TTS overlap; no other optimization receives credit.

## Estimated future headroom

| Hypothesis | Truth | Status |
|---|---|---|
| EOT/STT settlement overlap | ESTIMATED | Not exercised |
| Semantic/adaptive VAD | ESTIMATED | Not exercised |
| Post-audio.done EOF draining | ESTIMATED | Not exercised |
| Sentence-level Agent→TTS overlap | ESTIMATED | Not exercised |

## Controlled fixture and out-of-scope boundaries

CONTROLLED: fixed prompts, STT/admission/Agent/Tool/TTS waits, P2 RPC delay, successor ACK, and PCM playout duration.

OUT_OF_SCOPE: microphone/device capture, real Provider/network latency, real Agent/Tool execution, physical Chrome/WebAudio scheduling, and human-perceived first audio.
