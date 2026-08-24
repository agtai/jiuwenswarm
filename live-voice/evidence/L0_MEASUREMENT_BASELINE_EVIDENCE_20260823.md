# L0 correlated measurement and baseline evidence — 2026-08-23

## Scope, source and disposition

- Capability: Observability, benchmark and latency; first measurement layer of
  the [latency optimization plan](../roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md).
- Baseline: `c31e85ade1a69e934d05bfb9c277568a1238663c` on
  `hx/0812_live_voice_w3`.
- Current repaired product/test/corpus source:
  `3421f919192e56ebfa9107efffe5a7846326225f`.
  The deterministic injected baseline was regenerated on that exact source.
  The last real-Provider component result remains source-bound to
  `7f2b0b7ab9b9dc363cec21f83ac6e04ad53d221c`; no Provider was called for the
  review-only repair batch.
  The later evidence-only commit changes documentation, not the measured
  product, test, corpus or runner trees.
- Risk: Tier 3. The production hooks cross Browser, Gateway, Runtime and Agent
  response ownership, although the evidence sink is local, opt-in and has no
  lifecycle or mutation authority.
- Overall disposition: **PARTIAL**. Correlated production instrumentation,
  fixed corpus, injected baseline and real-Provider digital-loopback component
  baseline are implemented and automated. Three earlier independent review
  rounds found three, then two, then two bounded issues; all seven were repaired.
  A subsequent owner consolidation made the actual HTTP and WebSocket
  connections, rather than adjacent listener probes, the common CDP ownership
  invariant. The resulting broad review disclosed all six remaining actionable
  findings in one batch; commit `3421f9191` repairs them. One focused independent
  closure review and
  the required physical microphone, speaker and room cold/warm profiles remain
  open, so no module-Gate PASS, current physical p50/p95, audibility, AEC,
  stop-to-silence or feature-complete latency credit is claimed.

## Intended behaviour and exclusions

The owned path records a content-free exact timeline from Provider EOT through
Browser receipt/capture settlement, Gateway STT final, committed submit, Agent
request/delta/stable-sentence/final, TTS request/first Provider audio/downlink,
Browser first frame, WebAudio schedule/actual start and render completion. It
also records authoritative Tool-call/Tool-success boundaries, failure, fallback,
barge-in/fence completion and discarded work. An early response-less declaration
is pinned to the first exact response/turn/round identity; a later response
cannot widen or rebind the sample.

Success percentiles admit only a complete, correctly ordered, operator-accepted
round classified as success after failure/fallback/cancel precedence. Tool cases
also require an authoritative call and successful result. Missing milestones
remain absent/unknown, never zero. Failure, fallback, cancelled, duplicate,
reordered, future-sample, wrong-scope, wrong-generation, wrong-response,
wrong-Task and capacity-rejected facts are reported or isolated and never enter
success percentiles. Cancel-only stop-to-silence percentiles remain separate.

The implementation deliberately does not:

- change the shared Live Voice schema, protocol, Task/Agent/Tool/history/audio
  authority, P2 batch contract, Provider/model/billing or ordinary production
  feature flags;
- retain raw audio, recognized/final text, prompts in measurement records,
  credentials, device identity, URLs, project content or private configuration;
- treat WebAudio scheduling/render completion as proof that sound was physically
  audible, silent after cancel, echo-free or subjectively acceptable;
- tune VAD, replace the fixed playout lead, enable generation-time interruption
  or activate any later latency optimization layer.

## Fixed corpus and runners

The committed closed-shape corpus is
`scripts/live_voice/l0_fixed_corpus.json`, SHA-256
`888fdcba848037c1feba6c8c31a15641d721507b57e0985ba2d14446e7d4b563`.
It contains seven profiles and thirteen cases: short/long dialogue, real Tool,
Task create/status/cancel, Chinese breath pause, barge-in, silence,
mid-pause truncation, Provider slow/failure and degraded network. Every formal
profile requires at least 20 successful rounds. Provider failure is classified
separately as fallback; silence remains failure.

- `l0_measurement_baseline.py` validates the corpus, runs deterministic injected
  profiles, runs real Provider batch synthesis plus in-memory digital loopback
  recognition, and aggregates sanitized process JSONL only when each input
  directory's closed metadata binds the same exact source, environment and
  configuration. Physical aggregation also requires explicit accepted sample
  keys and remains incomplete until the dedicated Browser runner validates its
  acceptance log and full scenario target; the generic CLI cannot bypass that
  Gate.
- `start_hands_free_demo.ps1 -L0Measurement` is an isolated
  `formal-web-validation` launcher path with a separate Chrome profile/debug
  endpoint and dynamic closed labels. Session v6 rejects a pre-existing debug
  listener, binds the exact launched Chrome executable/profile/PID lineage,
  requires a per-launch page nonce, and requires one verified preconnected IPv4
  socket for HTTP discovery and another for WebSocket CDP. HTTP uses an exact
  `/json` request and accepts only status 200; WebSocket proxy selection and
  redirects are structurally unavailable with the supplied socket. Each peer
  and server-side established four-tuple must belong to the debugger PID. The
  ordinary launcher path is unchanged. Stale-Chrome cleanup parses Windows argv
  and selects only an exact managed `--user-data-dir`; unrelated command-line
  substrings have zero process-stop authority.
- `l0_browser_capture.py` takes no manual timestamps. It reads the browser CDP
  timeline automatically and asks the operator only for pass/fail/quit. A sample
  counts only when the operator passes, no browser record was dropped, all
  labels match, exactly one successful render terminal exists, and the final
  Browser/Gateway/Runtime/Agent aggregate is success-eligible for the same exact
  profile/scenario/sample key. A physical invocation below 20 successes is
  rejected.

## Automated injected baseline

This runner proves aggregation, classification, identity filtering and
percentile calculation over known injected timings. It is not performance
evidence for a physical or real end-to-end product route.

| Profile | Eligible / success | Failure / fallback / cancel | Speech end → WebAudio start p50 / p95 | Complete round p50 / p95 |
|---|---:|---:|---:|---:|
| degraded warm | `20 / 20` | `1 / 1 / 1` | `4730.2 / 5085.4 ms` | `6148.5 / 6537.0 ms` |
| nominal cold | `20 / 20` | `1 / 1 / 1` | `4765.2 / 5120.4 ms` | `6183.5 / 6572.0 ms` |
| nominal warm | `20 / 20` | `1 / 1 / 1` | `3890.2 / 4245.4 ms` | `5308.5 / 5697.0 ms` |

Across those profiles, Agent request → final is `1572.0 / 1794.0 ms`.
Warm/degraded TTS request → first Provider audio is `262.2 / 284.4 ms`; cold
is `437.2 / 459.4 ms`. Each injected profile has one separately classified
cancel sample with stop-to-silence `80.0 / 80.0 ms`; this validates the cancel
aggregator only and is not physical silence evidence.

The production collector accepted all `1,228` injected observations with zero
duplicates, rejected observations or sink failures; the bounded collector also
reported zero capacity, conflict or isolation rejections. The degraded profile
contains two injected underruns and two rebuffers. Nominal profiles leave those
facts unknown rather than zero; false-EOT, frame-loss and discarded-work facts
also remain unknown where no authoritative event was observed.

## Real Provider digital-loopback component baseline

This result remains bound to `7f2b0b7ab`; it was not rerun after the six-item
review repair because doing so would call the external Provider. The configured
machine completed 20/20 real Provider rounds without retaining
synthesized audio or recognized text. The Provider wrapper creates a new client
per request and exposes no authoritative model-residency lifecycle; this run is
therefore recorded as `unknown`/`uncontrolled`, not cold or warm:

| Profile | Success | Batch synthesis completion p50 / p95 | Recognition p50 / p95 | In-memory loopback p50 / p95 |
|---|---:|---:|---:|---:|
| unknown / uncontrolled | `20/20` | `1672.0 / 4125.0 ms` | `390.0 / 594.0 ms` | `2062.0 / 4719.0 ms` |

These numbers measure batch synthesis completion, not streaming first audio.
Digital loopback is neither a physical microphone/speaker route nor the full
Browser → Gateway → Agent → TTS route. They also grant no Provider cold/warm
comparison because the lifecycle was not controlled. Provider failure and
fallback counts were both zero. The sanitized configuration digest is
`49b05d78b11a31c7577523def2c24d51bc551293b191cd03df264246eba78a1d`;
it identifies the configured field set without retaining values or credentials.

## Risk-matrix closure

| Matrix | Evidence |
|---|---|
| P — positive | Three injected profiles retain 20/20 successes each; the real-Provider unknown-lifecycle component retains 20/20; production Browser/Gateway/Runtime/Agent hooks are exercised by affected tests. |
| N — negative | Closed shapes reject private/extra/invalid fields; wrong identity, generation, sample and Task facts have zero aggregation authority. |
| B — boundary | At-least-20 formal samples, safe integers, bounded rounds/records/files/browser buffer, duplicate milestone and capacity rejection coverage. |
| S — state | Feature-off allocates no sink, Browser measurement state or control; disabled labels, route close, stale generation and later records cannot revive authority. |
| T — temporal | Duplicate/idempotent, conflict, reorder, missing, negative/regressive duration, future sample and cancel ordering fail closed or remain unknown. |
| C — concurrency | Locked collector, process-sink serialization, response registration with frozen run labels, pre-synthesis Browser/Gateway and pre-dispatch Runtime registration; delayed callbacks cannot cross samples, including when the conflict-tombstone budget is full. |
| R — restart/replay | Append-only fsync JSONL, deterministic reload/aggregate, dynamic labels, exact source/corpus hashes and Chrome session-v6 executable/profile/PID/nonce ownership; no replay creates product effects. |
| I — isolation | Exact Session/correlation/interaction/activation/response/turn/round and optional Task/Attempt binding; partial identity pins once and response labels cannot rebind. CDP binds both HTTP discovery and WebSocket traffic to verified preconnected IPv4 sockets owned by the exact executable/profile/PID lineage; exact page/nonce selection remains closed. |
| F — feature/fallback | Ordinary path remains flag-off; failure/fallback/cancel are distinct and excluded; physical runner accepts only nominal non-injected success cases. |
| K — compatibility | P2 production batch `16` and omitted single-pull compatibility remain covered; no shared schema or wire extension. |
| X — cross-module | Formal Web, Browser Audio, Dedicated Media, Agent Bridge, Registry, launcher and Python/TypeScript privacy/aggregation tests cover the actual owner chain. |

## Verification

- L0 collector/corpus/browser-capture plus affected Agent/Gateway/Registry/
  launcher Python run: `442 passed / 6 failed`. The six failures are the same
  pre-existing P3 fixture/projection set reproduced on baseline `c31e85ade`;
  the focused L0/launcher set is `62/62` and all new production-hook
  tests pass.
- The declared `websockets==12.0` floor imports the capture runner and displays
  `--help`; current-lock supplied-socket ownership regressions pass. PowerShell
  argv probes reject decoy, prefixed and duplicate profile options, and the
  launcher AST has zero errors.
- On the unchanged earlier source, Formal Integrated Web was `478/478`;
  Browser Audio I/O was `103/103`;
  Dedicated Media: `27/27`; Gateway Media: `38/38`; Browser L0: `5/5`.
- No TypeScript blob changed in this repair batch, so those frontend suites were
  not rerun. Changed-Python Ruff/compileall, PowerShell AST and
  `git diff --check`: PASS.
  Existing duplicate locale-key, mixed-import and chunk-size warnings remain
  unchanged.
- Direct runner smoke: both `l0_browser_capture.py --help` and corpus validation
  succeed when invoked by repository-supported direct script paths.
- PowerShell AST parsing passes. The unchanged controlled build-profile result
  was not rerun, and the L0 launcher was deliberately not used to start services
  or a physical browser session in this non-physical packet.

## Independent Tier-3 review

Iterative reviews before the prior measured source found ten, then seven, then
four actionable issues across optional-hook isolation, CDP loopback confinement,
cancellation/observability classification, aggregation, Tool authority,
Provider temperature claims, source binding and evidence-path confinement.
The next independent review returned `FAIL` with no P0 and three bounded
findings: P1 response callbacks could acquire the next sample's current labels;
P2 loopback CDP did not prove that the listener belonged to the newly launched
isolated Chrome; P3 ordinary Browser feature-off still allocated an empty
buffer and full control object. Commit `9a3a65fd0` freezes labels in exact
response registrations across Runtime/Gateway/Browser callbacks, moves Browser
registration before synthesis awaits, binds CDP to the launched profile/PID
lineage and page nonce, and lazily creates Browser measurement state/control
only when opted in. The focused cross-sample, owner-lineage and feature-off
regressions pass. The first follow-up review again returned `FAIL`, with no P0
or P3 and two bounded findings: at full conflict-tombstone capacity a rejected
Runtime owner could be removed and the response rebound to the next sample;
and CDP ownership had a discovery/connect TOCTOU window while executable
identity was inferred only from basename and arguments. Commit `4b96f9823`
keeps the first frozen owner when the tombstone budget is exhausted, records
and verifies the exact Chrome executable, and revalidates ownership before and
after page discovery and after WebSocket connection. The capacity, executable
and both race-window regressions pass. At that point both baseline artifacts
were regenerated on that exact source. A further independent Tier-3 review of `4b96f9823`
returned `FAIL`, with no P0/P1/P3 and two P2 findings. HTTP and WebSocket
connections could use environment proxies, WebSocket handshake redirects could
leave the validated port, and the post-connect checks did not bind the actual
stream. Launcher listener rows also omitted their local address and used a
profile substring, while Python ignored unknown/non-loopback rows and treated
`::1` as equivalent to the fixed IPv4 endpoint. Commit `655226e99` disables
both proxy paths, rejects every handshake redirect, verifies the direct peer and
Chrome-owned established four-tuple, requires one exact `127.0.0.1` listener,
and parses Windows command lines before exact single-value option comparison.
Proxy, redirect, peer/four-tuple, profile-prefix, wildcard, IPv6 and unknown-PID
regressions pass. At that point both baseline artifacts were regenerated on
that exact source. Another independent Tier-3 review remained required; no
repair round grants a review PASS.

Before requesting that final review, the owner performed one complete CDP
trust-chain and complexity audit. This was not a fourth independent review or a
new finding round. Commit `7f2b0b7ab` removes the custom WebSocket redirect
subclass and the adjacent-probe connection model. Both `/json` discovery and
the WebSocket handshake now consume preconnected direct sockets whose exact
peer and Chrome-owned server four-tuple were verified before use; the supplied
WebSocket socket bypasses proxy selection and cannot follow a redirect. Python
also requires exactly one profile, debugger-address and debugger-port option on
both frozen Chrome processes. Proxy, HTTP status, WebSocket redirect,
cross-port, unknown-owner, conflicting-option and same-socket regressions pass;
the browser-capture suite remains 24 cases. At that point both baseline
artifacts were regenerated on exact source `7f2b0b7ab`. One broad independent
Tier-3 review of that consolidated source followed.

That broad review returned `FAIL` with no P0 and declared
`ALL_ACTIONABLE_FINDINGS_DISCLOSED: YES`. Its two P1 findings were a generic
physical aggregation bypass and unknown failure/fallback/cancel markers losing
to explicit success. Its four P2 findings were a full-tombstone conflict that
left the old response resolvable, substring-based Chrome cleanup, a
`websockets` import newer than the declared dependency floor, and a missing
process-sink `fsync`. Commit `3421f9191` closes the batch without changing the
shared protocol or product policy: physical inputs require exact session
provenance plus explicit acceptance and stay incomplete outside the dedicated
runner; marker facts join the existing classification precedence; a full-budget
conflict becomes permanently unresolvable in-place; Chrome cleanup requires one
exact managed profile argument; the public WebSocket API supports the declared
12.0 floor; and a successful JSONL write is fsynced before close. Attack
regressions cover each path. One focused independent closure review of
`cc8d5c50c..3421f9191` remains required; this is not another open-ended finding
round.

## Physical acceptance still open

Both `physical-formal-web-cold` and `physical-formal-web-warm` remain **NOT
RUN**. Each needs at least 20 correlated successful rounds on one recorded
environment, with automatic Browser/Gateway/Agent timing and separate operator
confirmation. Until then, speech-end-to-physical-first-audible,
stop-to-physical-silence, AEC/double-talk, subjective quality and stable-design
30-run release thresholds remain open. No generated value, Provider component
probe or prior manual sample substitutes for that evidence.

The controlled launcher prints the exact content-free capture command after it
starts. The operator boundary is limited to granting/selecting the microphone,
speaking the displayed fixed prompt, listening, and entering pass/fail; the
collector supplies all timestamps and aggregation. Warm collection requires one
20-success session. Cold collection requires one scenario and one successful
sample per fresh launcher epoch, followed by `--aggregate-cold` over at least 20
unique epoch directories. The environment label, clean source, configuration
digest, corpus digest and sample identities are checked automatically.

## Diagnostic judgement and next packet

The injected oracle's largest modeled critical-path segment is Agent request to
`chat.final` (`1572.0 / 1794.0 ms`), while the real Provider component's batch
synthesis completion is `1672.0 / 4125.0 ms`. Neither is a physical end-to-end
bottleneck claim. The next required action is the focused independent closure
review of the disclosed repair batch; after it passes, the next packet is the
already-defined physical
cold/warm fixed-corpus collection, not a production optimization. Only that
evidence may choose among VAD finalization, browser startup buffering,
end-of-turn settlement or later sentence-level Agent→TTS overlap.

## Sanitization

No bearer token, Speech credential, raw audio, recognized/final text, device
identity, private project content or machine-private environment value is
retained in this record or the committed corpus. Runtime evidence files remain
local and ignored.
