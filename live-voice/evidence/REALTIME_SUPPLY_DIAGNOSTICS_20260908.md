# Prepared supply and diagnostic competition: scoped evidence

Baseline: `d8ee9e6d`. This is current-host mechanism and module evidence, not
acceptance of physical audio or the other C–H repairs.

Prepared delivery now spends real Provider samples against an accumulated
deadline, with 320 ms maximum credit after a stall. It does not add processing
time to every frame. Existing bounded downlink/transport credit remains binding.
The sole Provider reader runs before replayed PCM, with a current-task receive
timeout instead of per-event child-task handoffs. Actual-playout ACK, generation
fences, transport padding and foreground STOP keep their distinct semantics.

Logging retains all privacy filters and six handlers. Sensitive-key matching
starts at a key boundary rather than retrying each suffix of long identifiers.
An unchanged, already-sanitized immutable message/exception string is reused
only within its own LogRecord; msg/args/exception changes are sanitized again.
The diagnostic queue remains capped at 256, with explicit drop accounting.

## Reproduction and checks

Set `JIUWENSWARM_DATA_DIR` to an isolated path under `logs/repair-20260908/`
before imports. The initial new regressions failed for accumulated sample
deadline, unbounded stall credit and six repeated handler scans: 3 failed,
21 privacy cases passed. Raw command output: `ab-before-tests.txt`.

The first combined rerun found an actual ready-STOP regression after removing
the 20 ms wait, fixed through the single-task receive wrapper. A separate
inherited path assertion expected the literal `.jiuwenswarm` in the isolated
data path; the rerun used `.jiuwenswarm-test-data` without accessing real data.
Do not erase or treat those failures as physical evidence.

Verified commands (current Python, `-o addopts= -o log_cli=false -q --tb=short`):

- Native supply clock, log redaction, audio diagnostics, utils, continuation
  preparation and Realtime session: **186 passed**, `ab-focused-tests.txt`.
- Native Engine, transport diagnostics, demo profiling, dedicated media route
  and the new passive lock wrapper: **332 passed**, `ab-regression-tests.txt`.

`addopts` overrides the repository's whole-repository coverage report for these
scoped checks; no required scenario is excluded. The latter command includes
two passive lock tests belonging to the upcoming C observation boundary.

Independent read-only module review found no core implementation blocker.
The reviewer additionally compared 5,000 fixed-seed old/new redaction inputs
with zero differences. Two measurement findings were fixed: actual bytes and
expected-frame comparison replaced a decoded-sample text hash; a high-resolution
deadline guard handles Windows timer early wakeups. Follow-up review closed both.

## Production downlink mechanism comparison

Reproduce from the repository root:

```powershell
.\.venv\Scripts\python.exe -m tests.support.live_voice.supply_diagnostics_probe --baseline-redaction d8ee9e6d --output logs/repair-20260908/diagnostics-before-verified.json
.\.venv\Scripts\python.exe -m tests.support.live_voice.supply_diagnostics_probe --output logs/repair-20260908/diagnostics-after-verified.json
```

The probe reads the baseline's logging implementation without changing Git or
source. Both conditions run the current production downlink loop and real
logging handlers, 50 known PCM frames, long identities, a thread performing
1 ms socket-I/O simulation, actual ACK controls and optional controlled CPU
load. This load is not a real Agent/Task execution. Four alternating on/off
runs per load condition; CPU includes diagnostic drain. No production diagnostic
or redaction is disabled in the on condition.

Numbers below are medians over four runs per cell; loop-lag values are the
median of each short run's P95, including local Windows scheduling effects.

| Load / diagnostics | First 8 frames before → after (ms) | 50 frames before → after (ms) | Process CPU before → after (ms) | Loop-lag P95 before → after (ms) |
|---|---:|---:|---:|---:|
| Idle / off | 14.55 → 14.32 | 99.02 → 101.85 | 31.25 → 39.06 | 9.39 → 9.73 |
| Idle / on | 136.68 → 20.72 | 292.50 → 106.35 | 257.81 → 46.88 | 16.66 → 4.88 |
| CPU load / off | 14.68 → 14.14 | 103.34 → 99.77 | 85.94 → 125.00 | 8.05 → 5.04 |
| CPU load / on | 124.88 → 23.23 | 293.34 → 114.89 | 312.50 → 140.63 | 13.83 → 8.10 |

Each verified before/after file has 16 runs. Actual wire and PCM hashes match
across all runs, and each wire frame equals its source's expected encoding.
Missing, repeated, out-of-order frames and diagnostic drops: **zero**. The raw
JSON records all sample counts, timing values, CPU, queue peaks and hashes.
The queue bound is separately tested under deliberate sink overload.

Earlier `diagnostics-*.json`, `*-v2.json` and `*-final.json` remain local failure/
iteration evidence. Only `*-verified.json` has the high-resolution early-wakeup
guard and verified loop-lag interpretation. None proves long-run P95, real
network, browser render, headphones, human perception or all 15 historical marks.
The original September 8 video/PCM are unavailable on this host.
