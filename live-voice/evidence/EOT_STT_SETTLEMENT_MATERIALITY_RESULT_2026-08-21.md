# EOT/STT Settlement Materiality — A1 Result

Date: 2026-08-21

## Closed decision

**`NO_MATERIAL_SERIAL_GAP`** — no product protocol, wait RPC, B candidate or
A2 was implemented. Tasks 4–6 of the
[implementation plan](../roadmap/EOT_STT_SETTLEMENT_OVERLAP_IMPLEMENTATION_PLAN_2026-08-21.md)
are skipped.

The eligible metric is the removable serial tail, not the diagnostic route
wait:

```text
removable_serial_gap_ms = streaming_result_returned
                          - max(uplink_closed, provider_final_ready)
removable_serial_gap_fraction = removable_serial_gap_ms
                                / (stt_final_received - eot_received)
```

A fixture is material only when both its removable-gap p50 is at least
80 ms and its removable-gap-fraction p50 is at least 0.10. All four fixtures
are below both gates. `route_settled_to_result_returned` remains diagnostic
only and cannot authorize B.

## Exact source and execution

| Field | Value |
|---|---|
| Candidate | `A1` |
| Exact source | `bdd57bb6dd2418fcbbfb87ed2df7c27e08de9a0f` |
| Source state before run | clean |
| Run ID | `eot-stt-a1-materiality-bdd57bb6d` |
| Attempts | 5 per fixture; 20 total |
| Runner boundary | deterministic no-Chrome Node causal runner; real Product P1 owner and registry seam |
| Raw report handling | external mode-600 JSON report; not copied into Git |

Credential-free command:

```bash
cd jiuwenswarm/channels/web/frontend
npm run benchmark:live-voice-eot-stt -- --candidate A1 --attempts 5 --git-commit bdd57bb6dd2418fcbbfb87ed2df7c27e08de9a0f --run-id eot-stt-a1-materiality-bdd57bb6d --output /home/renan/openJiuwen-ai/live-voice-latency-runs/eot-stt-a1-materiality-bdd57bb6d.json --python-executable /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-eot-stt-overlap/.venv/bin/python3
```

Machine/runtime labels: Linux `6.18.33.2-microsoft-standard-WSL2` on `x86_64`;
Node `v24.18.0`; npm `12.0.1`; Python `3.11.15` from the named virtual
environment.

## Integrity and safety summary

| Check | Result |
|---|---:|
| Attempted / completed | 20 / 20 |
| Failed / invalid | 0 / 0 |
| Exact recognized result | 20 / 20 |
| Cleanup complete | 20 / 20 |
| Total result RPCs | 20 (one per attempt) |
| Source/control consistency | clean exact commit; fixed A1 fixtures and attempt count |
| Forbidden effects | 0 Agent submit, Tool call, Task mutation, TTS request, Browser, WebAudio, microphone, audio-history, and product submission |

All p95 values below use the runner's nearest-rank reduction. The diagnostic
metric is retained to show the non-removable Provider wait; the last two rows
in each table are the decision metrics.

### Fixture: local-fast/provider-fast

Injected local settlement: 50 ms. Injected Provider final readiness: 50 ms.

| Metric | p50 | p95 |
|---|---:|---:|
| EOT → recognized final | 53.052 ms | 54.765 ms |
| Diagnostic route settled → result returned | 0.944 ms | 1.453 ms |
| Removable serial gap | 0.944 ms | 1.453 ms |
| Removable serial-gap fraction | 0.018 | 0.027 |
| Result RPCs | 5 | 5 |

### Fixture: local-slow/provider-fast

Injected local settlement: 500 ms. Injected Provider final readiness: 50 ms.

| Metric | p50 | p95 |
|---|---:|---:|
| EOT → recognized final | 503.047 ms | 503.586 ms |
| Diagnostic route settled → result returned | 0.785 ms | 0.928 ms |
| Removable serial gap | 0.785 ms | 0.928 ms |
| Removable serial-gap fraction | 0.002 | 0.002 |
| Result RPCs | 5 | 5 |

### Fixture: local-fast/provider-slow

Injected local settlement: 50 ms. Injected Provider final readiness: 500 ms.

| Metric | p50 | p95 |
|---|---:|---:|
| EOT → recognized final | 503.097 ms | 503.294 ms |
| Diagnostic route settled → result returned | 450.924 ms | 451.473 ms |
| Removable serial gap | 0.865 ms | 1.444 ms |
| Removable serial-gap fraction | 0.002 | 0.003 |
| Result RPCs | 5 | 5 |

The large diagnostic value is remaining Provider-final readiness after local
uplink settlement, not removable local/result serialization.

### Fixture: both-slow

Injected local settlement: 500 ms. Injected Provider final readiness: 500 ms.

| Metric | p50 | p95 |
|---|---:|---:|
| EOT → recognized final | 503.590 ms | 504.943 ms |
| Diagnostic route settled → result returned | 0.815 ms | 0.998 ms |
| Removable serial gap | 0.815 ms | 0.998 ms |
| Removable serial-gap fraction | 0.002 | 0.002 |
| Result RPCs | 5 | 5 |

## Exclusions

This is causal, deterministic, no-Chrome evidence only. It does not measure or
credit a real Provider/network, Browser/device, microphone, WebAudio,
first-audible, Agent/model, Tool, Task, human-perception, product-readiness or
Production path. It does not make the current route faster; it closes this
conditional early-wait hypothesis without a product change.
