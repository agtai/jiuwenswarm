# EOT/STT Settlement Materiality — Complete A1 Result

Date: 2026-08-21

## Closed decision

**`NO_MATERIAL_SERIAL_GAP`** — no product protocol, wait RPC, B candidate or
A2 is authorized. Tasks 4–6 of the
[implementation plan](../roadmap/EOT_STT_SETTLEMENT_OVERLAP_IMPLEMENTATION_PLAN_2026-08-21.md)
remain skipped.

The eligible metric is the removable serial tail, not the diagnostic route
wait:

```text
removable_serial_gap_ms = streaming_result_returned
                          - max(uplink_closed, provider_final_ready)
removable_serial_gap_fraction = removable_serial_gap_ms
                                / (stt_final_received - eot_received)
```

A fixture is material only when both removable-gap p50 is at least 80 ms and
removable-gap-fraction p50 is at least 0.10. The largest respective p50 values
across the table were 0.880 ms and 0.015, so no fixture qualifies. The 450.782 ms
`route_settled_to_result_returned` diagnostic in local-fast/provider-slow is
legitimate remaining Provider wait and cannot authorize B.

## Exact source and execution

| Field | Value |
|---|---|
| Candidate | `A1` |
| Exact source | `8e5dab8b8c6651b2be784cf103df9239a93814a0` |
| Source state before run | clean |
| Run ID | `eot-stt-complete-contract-final` |
| Attempts | 5 per fixture; 20 total |
| Runner boundary | deterministic no-Chrome Node causal runner; real Product P1 owner and real registry result seam |
| Raw report | `/tmp/live-voice-eot-stt-final-Up1qNe/eot-stt-a1-complete.json`, mode `0600`, retained outside Git |

Credential-free command:

```bash
cd jiuwenswarm/channels/web/frontend
npm run benchmark:live-voice-eot-stt -- --output /tmp/live-voice-eot-stt-final-Up1qNe/eot-stt-a1-complete.json --git-commit 8e5dab8b8c6651b2be784cf103df9239a93814a0 --run-id eot-stt-complete-contract-final --attempts 5 --candidate A1 --python-executable /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-eot-stt-overlap/.venv/bin/python3
```

Machine/runtime labels: Linux `6.18.33.2-microsoft-standard-WSL2` on `x86_64`;
Node `v24.18.0`; npm `12.0.1`; Python `3.11.15` from the named virtual
environment.

## Integrity and safety

| Check | Result |
|---|---:|
| Attempted / completed | 20 / 20 |
| Failed / invalid | 0 / 0 |
| Exact recognized result | 20 / 20 |
| Cleanup complete | 20 / 20 |
| Complete ten-mark records | 20 / 20 |
| Complete eight-segment records | 20 / 20 |
| Total result RPCs | 20 (one per attempt) |
| Atomic output | one final mode-600 file; no temporary residue |
| Forbidden effects | 0 Agent submit, Tool call, Task mutation, TTS request, Browser, WebAudio, microphone, audio-history and product submission |

The nine `browser.*` marks come from the real `ProductP1VoiceRouteOwner`
latency round. Only `benchmark.provider_final_ready` is fixture-local, recorded
on the same Node `performance.now()` clock immediately after the captured
helper operation settles. The fixed registry business envelope may cross only
captured in-memory child stdout for Product P1 consumption. Reports, stable
errors and terminal output remain content-free.

All p95 values below use nearest-rank reduction.

## Complete segment tables

### local-fast/provider-fast — injected 50 ms local / 50 ms Provider

| Segment / decision metric | p50 | p95 |
|---|---:|---:|
| EOT → capture stopped | 0.194 ms | 0.852 ms |
| Capture stopped → last ACK | 0.091 ms | 0.159 ms |
| Last ACK → route settled | 52.219 ms | 52.829 ms |
| EOT → Provider final ready | 51.594 ms | 51.974 ms |
| Route settled → result request started | 0.008 ms | 0.018 ms |
| Result request started → result returned | 0.770 ms | 1.237 ms |
| Diagnostic route settled → result returned | 0.779 ms | 1.255 ms |
| EOT → recognized final | 53.479 ms | 54.540 ms |
| **Removable serial gap** | **0.779 ms** | **1.255 ms** |
| **Removable serial-gap fraction** | **0.015** | **0.023** |

### local-slow/provider-fast — injected 500 ms local / 50 ms Provider

| Segment / decision metric | p50 | p95 |
|---|---:|---:|
| EOT → capture stopped | 0.120 ms | 0.158 ms |
| Capture stopped → last ACK | 0.025 ms | 0.035 ms |
| Last ACK → route settled | 502.165 ms | 503.001 ms |
| EOT → Provider final ready | 51.490 ms | 52.382 ms |
| Route settled → result request started | 0.011 ms | 0.013 ms |
| Result request started → result returned | 0.869 ms | 1.130 ms |
| Diagnostic route settled → result returned | 0.880 ms | 1.139 ms |
| EOT → recognized final | 503.173 ms | 504.176 ms |
| **Removable serial gap** | **0.880 ms** | **1.139 ms** |
| **Removable serial-gap fraction** | **0.002** | **0.002** |

### local-fast/provider-slow — injected 50 ms local / 500 ms Provider

| Segment / decision metric | p50 | p95 |
|---|---:|---:|
| EOT → capture stopped | 0.077 ms | 0.261 ms |
| Capture stopped → last ACK | 0.012 ms | 0.060 ms |
| Last ACK → route settled | 51.872 ms | 51.974 ms |
| EOT → Provider final ready | 501.883 ms | 502.501 ms |
| Route settled → result request started | 0.007 ms | 0.027 ms |
| Result request started → result returned | 450.775 ms | 451.544 ms |
| Diagnostic route settled → result returned | 450.782 ms | 451.571 ms |
| EOT → recognized final | 502.774 ms | 503.478 ms |
| **Removable serial gap** | **0.885 ms** | **0.969 ms** |
| **Removable serial-gap fraction** | **0.002** | **0.002** |

### both-slow — injected 500 ms local / 500 ms Provider

| Segment / decision metric | p50 | p95 |
|---|---:|---:|
| EOT → capture stopped | 0.089 ms | 0.111 ms |
| Capture stopped → last ACK | 0.012 ms | 0.016 ms |
| Last ACK → route settled | 502.442 ms | 502.860 ms |
| EOT → Provider final ready | 501.635 ms | 502.011 ms |
| Route settled → result request started | 0.006 ms | 0.026 ms |
| Result request started → result returned | 0.796 ms | 0.969 ms |
| Diagnostic route settled → result returned | 0.802 ms | 0.995 ms |
| EOT → recognized final | 503.564 ms | 503.717 ms |
| **Removable serial gap** | **0.802 ms** | **0.995 ms** |
| **Removable serial-gap fraction** | **0.002** | **0.002** |

## Consequence and exclusions

This is causal deterministic no-Chrome evidence only. It grants no real
Provider/network, Browser/device, microphone, WebAudio, first-audible,
Agent/model, Tool, Task, human-perception, product-readiness or Production
credit. It does not make the route faster. It closes the early-wait hypothesis
without a product candidate; the latency workstream routes next to the
[Provider-native Semantic VAD screen](../roadmap/SEMANTIC_VAD_CAUSAL_BENCHMARK_SPEC_2026-08-21.md)
with the 1200 ms fallback retained.
