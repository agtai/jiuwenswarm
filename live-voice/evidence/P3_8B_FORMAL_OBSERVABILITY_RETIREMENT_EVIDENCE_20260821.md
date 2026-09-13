# P3-8B formal observability and retirement evidence — 2026-08-21

> Evidence status: **VALIDATED — SCOPED P3-8B PACKAGE.** This record contains no
> credentials, prompts, Task/result content, raw audio, private runtime paths or
> raw production identities.

## 1. Source binding

- Branch: `hx/0812_live_voice_w3`.
- Original packet baseline:
  `29589734a0bb51a697bf7d594e3b1bb552ddcd34`.
- B2 activation baseline:
  `cc42098163bf6e9d7cec303f37551d3526997eb4`.
- Integrated B2 source:
  `c0de16b5eba7004381f314ee97cbc98b35fe4e87`.
- B2 integrated diff: 8 files, 4,667 insertions and 74 deletions.
- Retirement source is the ordered integrated trio `4e207faa`, `ddde7b87`,
  `7b283898`, with exact manifest freeze through `be2bd45f`.

## 2. Main-worktree verification

All commands were local/offline. They did not start the product server, access
credentials/providers/devices, deploy, push or update a remote ref.

### Correlation, privacy and B2 runtime

```powershell
.\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q `
  tests/unit_tests/live_voice/test_observability_correlation_contract.py `
  tests/unit_tests/live_voice/test_live_voice_configuration_declaration.py `
  tests/unit_tests/live_voice/test_live_voice_retirement_manifest.py `
  tests/unit_tests/live_voice/test_observability_otel_codec.py `
  tests/unit_tests/live_voice/test_p3_8a_sli_privacy_contracts.py `
  tests/unit_tests/live_voice/test_observability.py `
  tests/unit_tests/live_voice/test_observability_exporter.py `
  tests/unit_tests/live_voice/test_observability_fault_harness.py `
  tests/unit_tests/live_voice/test_product_observability_adapter.py `
  tests/unit_tests/live_voice/test_alpha_privacy_conformance.py `
  tests/unit_tests/test_app_web_live_voice_privacy.py
```

Result: **267 passed in 8.22 s**. This combines B1's 59 and P3-8A's 207 while
executing their shared manifest test once.

```powershell
.\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q `
  tests/unit_tests/live_voice/test_product_observability_runtime.py `
  tests/unit_tests/live_voice/test_p3_authenticated_composition.py `
  tests/unit_tests/agentserver/test_live_voice_p3_route.py
```

Result: **204 passed in 35.54 s**, with one pre-existing third-party Authlib
deprecation warning.

The independent review separately ran 29 focused config/runtime/Registry/
AgentServer cases and the full Registry file. Focused result: **29 passed**.
Full Registry result: **165 passed, 6 failed**. The six failing nodeids and each
test-function SHA-256 were identical on `cc420981` and B2; all fail at existing
fake-P3/adapter boundaries before the new diagnostic projection. They are:

- bounded list/events/result;
- status retry admission;
- retry-admission failure;
- disconnect cleanup;
- in-flight query shutdown;
- natural text status routing.

### Retirement, Web and build compatibility

```text
test_desktop_port_resolve.py                         11 passed
gateway dedicated-media + Web privacy               48 passed
test:live-voice-browser-dedicated-media              27/27
test:live-voice-browser-gateway-media                38/38 (additional)
test:live-voice-build-profiles                       2/2
test:live-voice-integrated-web                       439/440
build:live-voice                                     PASS, 4,644 modules
```

The one Formal Web failure is the previously reproduced baseline
`mounted Exit and immediate re-enable recover after old unified success or
rejection without replaying TTS` late presentation ACK. Existing duplicate
locale-key and chunk-size/dynamic-import build warnings are unchanged.

The retirement implementation review additionally records the complete
affected retirement gates run on the exact retirement branch before
integration: fixed media backend/route/privacy `122/122`, frontend media
`27/27`, dotenv/startup `24/24`, build profiles `2/2`, Formal Web `439/440`, and
491/491 local Markdown links. Independent retirement and final manifest reviews
both returned `0 Critical / 0 Important / 0 Minor`.

### Static and repository checks

- Scoped `ruff check`: PASS.
- Scoped Python compile: PASS.
- `git diff --check`: PASS.
- B2 whole-file `ruff format --check`: 7/8; `agent_ws_server.py` fails identically
  on baseline and B2 due to existing file-wide format debt, not this diff.
- Production build left the worktree clean.

## 3. Exact producer and privacy observations

The same Registry/runtime/backend/SQLite test instance executes confirmed
`task.create`, applies RUNNING then TERMINAL FAILED `ExecutorObservation` facts
to its real Store, reads status/events/result, reserves terminal progress and
ACKs the exact delivery. Backend facts link public HMAC Task/Attempt/create-
Command tokens across Command, initial outbox, Executor, Event, Generation and
ACK. Raw task/spec/path/command IDs and the sentinel private executor failure
detail are absent. A separate actual Store-result test proves result identity
and availability while raw result text and artifact paths remain absent.

The Executor observation is deliberately test-injected through the real Store;
this evidence does not claim actual Direct/Core dispatch. It proves the
Registry/Store producer projection into the accepted adapter/runtime/codec/
backend chain.

## 4. Review and disposition

- B1 independent review: `C0 / I0 / M0`.
- Retirement code review: `C0 / I0 / M0`.
- Retirement manifest review: `C0 / I0 / M0`.
- Combined B2 review after fixing its initial `3I/1M`: `C0 / I0 / M0`.
- Scoped P3-8B verdict: **PASS**.
- Overall Observability/configuration/cleanup capability: **PARTIAL**.

The remaining nonclaims are external/persistent telemetry; formal checkpoint,
effect, recovery, reconcile and current outbox-state producers; real Direct
dispatch for the failed Journey; and every retained manifest row. P3-9 and the
cumulative physical journey were not run. The controlled candidate remains
FAIL and P1/P2 remain PARTIAL.
