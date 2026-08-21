# TTS Provider Connection Reuse Result

> **Status:** A-reference pilot and formal A1 complete; the connection-reuse
> candidate and first Tier-2 remediation are implemented on 2026-08-21. The
> independent re-review, B, A2 and final decision remain open.
>
> **Measured boundary:** direct real
> `OpenAIStreamingSpeechProvider`, no Gateway, Agent, Chrome, WebAudio, downlink
> or playout receipt.

## 1. Exact reference

- A reference commit:
  `e614a0d3bd431e8ee1a6cf55a7ea6d3ff7ccf3c2`;
- source state: clean for pilot and A1;
- Python: 3.11.15;
- HTTPX: 0.28.1;
- HTTPCore: 1.0.9;
- model: `gpt-4o-mini-tts-2025-12-15`;
- voice: `marin`;
- output: mono PCM at 24 kHz;
- fixed short English input, retained only in process memory and absent from
  reports.

Credentials and API base remained in the pre-existing private mode-0600 runtime
environment. They were loaded into the benchmark child process without being
copied into this worktree or printed.

## 2. Private evidence

| Population | Calls | Decision | Private report | SHA-256 |
|---|---:|---|---|---|
| uncredited pilot | 2 | `PILOT_VALID` | `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/pilot.json` | `0bd4bc65726ab73f31e87d1fb3235d31e598359f0dddcebef4e4ee26839025c5` |
| formal A1 | 6 | `CONTROL_VALID` | `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/a1.json` | `0700ce15c2ad304ff04e08f63537e1a07ed5794f7d5a307f04769f8000050741` |

Both reports were exclusive-created with mode `0600`, deeply reparsed through
the closed schema, and contain no credential, URL, header, input text, PCM, SSE
payload, exception text or session/user identity.

## 3. Pilot gate

The pilot completed 2/2 attempts. Both the first and second request created a
new TCP and TLS connection, matching the current request-scoped HTTPX client
lifecycle. Provider cleanup completed 1/1 and all forbidden-effect counters
were zero.

| Position | Response headers | First Provider audio | First PCM | Completed |
|---|---:|---:|---:|---:|
| cold | 2153.3 ms | 2154.5 ms | 2159.5 ms | 2914.5 ms |
| warm | 609.8 ms | 611.4 ms | 616.5 ms | 1244.8 ms |

This large within-pair difference is not optimization credit. The current
source opened a fresh connection for both attempts, so Provider/network
variability remains present.

## 4. Formal A1 result

A1 completed all six declared attempts with no failed, invalid or unknown
outcome. All six attempts proved a fresh TCP and TLS path; no connection reuse
was guessed. All three Provider instances closed cleanly and every forbidden
counter remained zero.

### 4.1 Aggregate latency

| Position | Metric | p50 | p95 |
|---|---|---:|---:|
| cold | response headers | 1374.2 ms | 1393.4 ms |
| cold | first Provider audio | 1375.7 ms | 1394.5 ms |
| cold | first PCM | 1381.0 ms | 1400.1 ms |
| cold | completed | 2093.7 ms | 2165.4 ms |
| warm | response headers | 980.0 ms | 1259.6 ms |
| warm | first Provider audio | 981.1 ms | 1260.8 ms |
| warm | first PCM | 986.3 ms | 1265.7 ms |
| warm | completed | 1589.9 ms | 2311.0 ms |

### 4.2 Per-attempt causal boundaries

| Pair | Position | TCP complete | TLS complete | Response headers | First audio | First PCM | Completed |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | cold | 50.0 ms | 71.3 ms | 1374.2 ms | 1375.7 ms | 1381.0 ms | 2093.7 ms |
| 0 | warm | 49.8 ms | 94.2 ms | 1259.6 ms | 1260.8 ms | 1265.7 ms | 2311.0 ms |
| 1 | cold | 49.9 ms | 73.8 ms | 1393.4 ms | 1394.5 ms | 1400.1 ms | 2165.4 ms |
| 1 | warm | 45.9 ms | 71.5 ms | 628.0 ms | 629.1 ms | 634.3 ms | 1142.1 ms |
| 2 | cold | 39.7 ms | 60.6 ms | 953.5 ms | 954.7 ms | 960.0 ms | 1717.2 ms |
| 2 | warm | 39.7 ms | 59.9 ms | 980.0 ms | 981.1 ms | 986.3 ms | 1589.9 ms |

The time between response headers and first Provider audio was approximately
1–2 ms, and first Provider audio to first PCM was approximately 5 ms. Most
pre-audio time after TLS is therefore Provider/network response wait rather than
local decode/resampling.

## 5. Current interpretation

The A1 materiality gate is structurally satisfied: the existing code recreated
the application client and performed TCP/TLS setup for every request. The
candidate may now test whether keeping the Provider-owned pool removes that
setup from warm requests.

The likely removable setup in this sample was roughly 60–94 ms. Consequently,
the experiment may prove correct connection reuse while still failing the
predeclared acceptance threshold of at least 100 ms and 10% improvement in warm
first-PCM p50 against both A1 and A2. That threshold remains unchanged; the
candidate will not be retained merely because reuse is technically visible.

No end-to-end, Browser, audible output, downlink, P2 ACK or Production-readiness
credit follows from A1.

The report field `stream_closed_ms` is a conservative completion-time proxy:
the Provider closes the response before publishing `COMPLETED`, and the runner
records the time it receives that terminal event. It is not an independent
transport-close timestamp and must not support close-duration conclusions.

## 6. Candidate and Tier-2 remediation

The initial product candidate was commit
`022db8945af804e68cd91a2ca5a372263c9d38c4`. The first independent Tier-2
review found no Critical issue and five Important gaps. All five were
reproduced before remediation. The reviewed candidate is now
`b44c82636d6e81ea4ac488afe95613488bd6e92c`, pending cold re-review.

The candidate now provides:

- one lazy HTTPX client per Provider and owning event loop;
- pool bounds of 8 active connections, 8 keepalive connections and a 30-second
  keepalive expiry;
- response-only stream cleanup and Provider-owned client cleanup;
- exact client retention across failed or late cleanup without duplicate close;
- fail-closed cross-event-loop access and cleanup;
- a fully inert content-free diagnostic observer, including `BaseException`;
- a process-level benchmark watchdog capable of terminating a
  cancellation-hostile worker;
- immediate stop before another paid pair after dirty cleanup or an
  infrastructure-invalid attempt;
- causal coverage for simultaneous streams, one-stream cancellation, distinct
  responses, Provider isolation, closed/custom-factory zero allocation, broken
  pooled transport without retry, and repeated Gateway use of one selected
  Provider.

The watchdog and dirty-cleanup stop are control-plane/failure-path runner
hardening added after A1. The successful `_main` timing path, trace collection,
request population, report schema and metric calculation are unchanged. This
runner byte difference is recorded explicitly; the independent re-review must
decide whether it preserves A1 credit before B begins.

Fresh remediation verification completed 115/115 focused cases, plus Ruff,
`py_compile` and diff-check. Two broader Gateway tests still fail
deterministically on the unchanged A and B source: one Windows-path-only test
oracle running on Linux and one pre-existing fake-provider cancel cleanup race.
They do not exercise the OpenAI client change and are excluded rather than
silently credited.

## 7. Remaining sequence

1. close the independent Tier-2 re-review before further paid calls;
2. run B on the final reviewed candidate, six calls without retry;
3. run A2 from a detached clean worktree at the unchanged A reference, six
   calls without retry;
4. apply every causal, regression and drift gate from the specification;
5. record `ACCEPTED`, `REJECTED` or `INCONCLUSIVE` and synchronize current
   documentation.

Call accounting is currently 8/20: two pilot plus six formal A1 calls.
