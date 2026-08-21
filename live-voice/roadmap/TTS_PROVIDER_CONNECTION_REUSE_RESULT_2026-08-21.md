# TTS Provider Connection Reuse Result

> **Status:** closed as `REJECTED` on 2026-08-21.
>
> **Measured boundary:** direct real
> `OpenAIStreamingSpeechProvider`, no Gateway, Agent, Chrome, WebAudio, downlink
> or playout receipt.
>
> **Product state:** request-scoped HTTPX client lifecycle restored in
> `ddd845e561145cdb1aa2eb37d6ea9c57633494f6`. The diagnostic seam and hardened
> runner remain.

## 1. Decision

The Provider-owned HTTPX client candidate did not produce connection reuse.
All three B warm attempts emitted new TCP and TLS trace boundaries. B warm
first-PCM p50 was also slower than the exact A1-v2 control:

```text
A1-v2 warm first PCM p50: 832.0 ms
B warm first PCM p50:     889.9 ms
delta:                    +57.8 ms / +7.0%
```

The final decision is therefore:

```text
TTS_PROVIDER_CONNECTION_REUSE_REJECTED
reason = B_WARM_CONNECTION_NOT_REUSED
```

This is a causal rejection, not an absence-of-data result. Trace support was
complete, all declared A1-v2 and B attempts completed, and cleanup was clean.
The B report's closed per-run decision is `INCONCLUSIVE` because its schema
correctly refuses candidate credit when warm reuse is absent; the higher-level
experiment decision is `REJECTED` because that absence was positively proven.

A2 was not run. Once B failed the mandatory reuse predicate and was slower than
A1-v2, A2 could not make the candidate acceptable. Avoiding A2 preserved six
authorized calls and did not hide a potentially successful candidate.

## 2. Exact sources and configuration

- historical pilot/A1 reference: `e614a0d3bd431e8ee1a6cf55a7ea6d3ff7ccf3c2`;
- exact final A1-v2/A2 reference: `e915e8dc0b414fafccf78a46d450a0b8d0633f5e`;
- reviewed B candidate: `72f0b15795018a770ed61d0e3f589ed1b8a942cd`;
- product restoration: `ddd845e561145cdb1aa2eb37d6ea9c57633494f6`;
- Python 3.11.15, HTTPX 0.28.1, HTTPCore 1.0.9;
- model `gpt-4o-mini-tts-2025-12-15`, voice `marin`, mono 24 kHz PCM;
- fixed short English input retained only in process memory.

The runner and runner-test blobs at A1-v2 and B were byte-identical:

```text
runner SHA-256 = 5d879f07d449f57cac8a9140aac357e9c6d4b905e27514aa0deec4e9af1e065b
runner-test SHA-256 = cb00dd6d269371e264e47553b95b6ecebd6ff38a0eeb61453824c6ff5921d073
```

Credentials and API base stayed in the pre-existing private mode-0600 runtime
environment. They were never copied into Git, printed or stored in a report.

## 3. Private evidence and call accounting

| Population | Source | Calls | Report decision | SHA-256 |
|---|---|---:|---|---|
| pilot, historical | `e614a0d3` | 2 | `PILOT_VALID` | `0bd4bc65726ab73f31e87d1fb3235d31e598359f0dddcebef4e4ee26839025c5` |
| A1, historical | `e614a0d3` | 6 | `CONTROL_VALID` | `0700ce15c2ad304ff04e08f63537e1a07ed5794f7d5a307f04769f8000050741` |
| A1-v2, credited control | `e915e8dc` | 6 | `CONTROL_VALID` | `f87be3ec59af56e8786f0988157dcd889ecd9a8134f751d7ff8bb35de1231db3` |
| B, credited candidate | `72f0b157` | 6 | `INCONCLUSIVE` | `393e8bbbdc233b284c205ce9db95f0e7b16b31f3a86e37ae9b1058b5935ed187` |
| A2 | not run | 0 | not applicable | not applicable |

Private paths:

- `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/pilot.json`;
- `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/a1.json`;
- `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/a1-v2.json`;
- `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/b.json`.

All four files are mode `0600`, deeply parse through the closed schema and have
zero forbidden effects. Total real calls were 20/26 authorized: 8 historical,
6 A1-v2 and 6 B. No retry occurred.

## 4. A1-v2 versus B

All A1-v2 attempts proved fresh TCP/TLS. B also completed 6/6 with clean
cleanup, but every B attempt—including all warm attempts—proved fresh TCP/TLS.

| Position | Metric | A1-v2 p50 | B p50 | Delta B−A | A1-v2 p95 | B p95 |
|---|---|---:|---:|---:|---:|---:|
| cold | response headers | 1023.1 ms | 1110.1 ms | +86.9 ms | 2318.3 ms | 1229.5 ms |
| cold | first Provider audio | 1025.0 ms | 1111.4 ms | +86.4 ms | 2319.8 ms | 1230.7 ms |
| cold | first PCM | 1039.6 ms | 1116.8 ms | +77.2 ms | 2324.9 ms | 1236.1 ms |
| cold | completed | 1808.3 ms | 1812.8 ms | +4.5 ms | 3067.3 ms | 1832.1 ms |
| warm | response headers | 825.4 ms | 883.6 ms | +58.1 ms | 1393.0 ms | 1335.4 ms |
| warm | first Provider audio | 826.7 ms | 884.8 ms | +58.0 ms | 1394.5 ms | 1336.4 ms |
| warm | first PCM | 832.0 ms | 889.9 ms | +57.8 ms | 1400.2 ms | 1342.1 ms |
| warm | completed | 1718.1 ms | 1732.6 ms | +14.5 ms | 2146.3 ms | 2045.0 ms |

B failed the acceptance contract before any statistical ambiguity:

- B warm reuse: required 3/3, observed 0/3;
- warm first-PCM improvement: required at least 100 ms and 10%, observed a
  57.8 ms / 7.0% regression versus A1-v2;
- no wait was removed from connection setup because setup still occurred;
- cleanup and forbidden-effect gates passed but cannot compensate for the
  failed causal predicate.

## 5. Why the pool did not reuse the connection

The experiment proves that retaining the application `AsyncClient` alone is
insufficient for this SSE lifecycle. Every immediate warm request still opened
TCP/TLS.

The leading code-level hypothesis is that the adapter returns as soon as it
accepts `speech.audio.done`, then closes the streaming response without reading
the HTTP body through EOF. HTTPX may therefore discard rather than pool the
connection. A Provider/server-side connection-close policy is another possible
cause. The current evidence does not distinguish those two mechanisms, so this
is recorded as a hypothesis rather than a fact.

A future experiment may test a separately specified bounded
`audio.done → EOF` drain. It must prove that EOF arrives under a hard deadline,
does not delay or change first PCM, does not accept extra audio/events, and
actually produces warm reuse before any product change is retained. It is not
part of this rejected candidate.

## 6. Review and verification

The independent Tier-2 review initially found five Important gaps. Remediation
closed observer inertness, event-loop ownership, process watchdog, dirty-run
evidence, concurrency, cancellation, isolation, custom/closed allocation,
broken-pool no-retry and Gateway Provider-cache coverage. Its final code verdict
at `72f0b157` was zero remaining Critical or Important findings.

After restoration, fresh focused verification passed 108/108 cases plus Ruff,
`py_compile` and diff-check. The final Provider implementation differs from the
A diagnostic baseline only by containing diagnostic `BaseException`; the
request-scoped HTTPX lifecycle is restored.

Two broader Gateway tests remain deterministic baseline failures in unchanged
code: one Windows-only traceback-path oracle running on Linux and one existing
fake-provider cancel-cleanup race. Neither exercises the OpenAI client.

## 7. Credit boundary and next step

This result grants only a no-Chrome real-Provider rejection of application-level
client reuse. It grants no Browser, audible output, downlink, P2 ACK,
end-to-end, Production-readiness or public SLO credit.

The next optimization should not reintroduce this pool unchanged. Candidate
options are:

1. specify and measure bounded post-`audio.done` EOF draining;
2. move to another independent Live Voice bottleneck with larger measured
   headroom;
3. retain the current request-scoped lifecycle until a candidate proves actual
   connection reuse and the full acceptance threshold.
