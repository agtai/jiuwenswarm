# Streaming Speech authority and resource lifetime repair

Baseline: `bfef2b3adac1d5d0147eeaa0cf1aa46ff6f0643c`.

## Design checkpoint

The user authorizes a structural repair of cumulative capture exhaustion. This
packet owns the streaming Speech port/conformance, OpenAI adapter, recognition
and synthesis Gateway routes, their Media Registry admission seam and focused
tests. The local in-process admission contract is Tier 3; transport cleanup and
diagnostic changes are Tier 2. No browser wire schema, Store migration, Task
policy, Provider/account configuration, deployment or remote update is included.

The existing Media/Runtime authority remains the issuer. Each admitted stream
carries a content/exact-reference-bound, revocable, one-use permit with a current
authority check. Replaying a retained request cannot consume it again, including
after all Provider history is reclaimed. An absent historical ID never grants
permission. Permits are retained by the current request/resource, not by a
process-lifetime history. A response's unit ordering belongs to its authorized
response lifetime. Provider resources and unfinished cleanup retain independent
bounded accounting; cancelling output does not prove transport closure.

Recognition, synthesis and response history must cease acting as cumulative
usage counters. Gateway synthesis handles must likewise retire without losing
exact-owner checks or reviving old requests. No threshold-triggered reset,
larger cap, periodic clear, unauthenticated LRU or TTL admission is permitted.

## Applicable verification

- P/B: substantially more than 64 sequential authorized captures and responses;
  bounded retained state; genuine concurrent saturation and recovery.
- N/I: missing, revoked, consumed, mismatched and cross-owner permits reject
  before transport allocation; no Agent/Tool/Task/history effects.
- S/T/C/R: close, cancel, interrupt, failed/late open, old callbacks, concurrent
  duplicate open and deferred cleanup retain exact ownership and cannot revive.
- F/K: feature-off and existing event/timeout/fallback contracts; preserve typed
  local capacity/authority/cleanup reasons instead of Provider protocol blame.
- X: actual Gateway → adapter → conformance integration with controlled wire
  faults. This is automated seam evidence, not real microphone/Provider or full
  Demo acceptance. No persistent data migration or business classifier applies.

## Implementation boundary

The shared conformance no longer retains recognition/synthesis generation or
response-ID ledgers. It retains current resources and response authorities.
Media records issue capture permits once; existing synthesis content transfers
retain a consumed permit without retaining spoken text. The live activation
retains one current response authority and preserves it across renewal.
Gateway request/Provider claims are one-use. Request content and exact references
are bound; the current owner's validity check fences a revoked lifetime.

Terminal Provider queues retain capacity until their exact consumer retires
them. Adapter retirement does not reap other terminal streams. Transport/worker
cleanup retains its existing bounded budget until actual completion; delayed
route cleanup releases tracking from completion callbacks. Retired handles use
exact owner/scope/reference plus a weak reference to the original instance, so
idempotent terminal reads need no process-lifetime handle map. Current response
authority also guards already queued audio before a frame is returned.

Local resource capacity, unfinished cleanup and expired authority have separate
typed degradation reasons. Both synthesis and recognition product fallback
exclude expired authority, including a capture whose batch digest already exists.
The old cumulative-capacity test oracles have been replaced with lifetime tests.
Existing consumer tests use an explicit test-only Media/Runtime issuer; it is
not imported into product code.

## Scoped source verification

The scoped command is `.venv/Scripts/python.exe -X utf8 -m pytest --no-cov -q
--tb=short --show-capture=no -o log_cli=false` followed by these seven modules:

- `tests/unit_tests/live_voice/test_streaming_speech.py`
- `tests/unit_tests/live_voice/test_openai_streaming_speech.py`
- `tests/unit_tests/live_voice/test_speech_lifecycle.py`
- `tests/unit_tests/gateway/test_streaming_speech_route.py`
- `tests/unit_tests/gateway/test_streaming_synthesis_route.py`
- `tests/unit_tests/gateway/test_product_streaming_synthesis.py`
- `tests/unit_tests/gateway/test_dedicated_media_registration.py`

Final scoped run: **376 passed in 11.66 s**
(`logs/speech-lifecycle-final-gate.log`). Earlier overlapping reruns are not
added to this total. Ruff checks on the five product modules and two new test
modules, AST parsing of all 12 changed/new Python files, scoped Markdown links
and `git diff --check` pass. No full repository suite or frontend build was run;
there is no frontend source change.

Normalized-LF source digest:
`250bb3d393422c39f18bdc0c41352f891ea477dc0c8d29207299ca0063f39d76`.
It covers the five product modules, five changed existing test modules and two
new test/helper modules. For sorted repository paths, hash each UTF-8 source
after newline normalization, concatenate `path + NUL + hex SHA256 + LF`, then
SHA256 that UTF-8 manifest. The local per-file manifest is
`logs/speech-lifecycle-source-manifest.json`; documentation is excluded to avoid
self-reference. Independent review is recorded below.

| Dimension | Owned evidence |
|---|---|
| P/B/S | 512 sequential conformance capture and response lifetimes; 300 retired Gateway synthesis handles; one persistent real Registry/route/OpenAI Adapter for 160 capture lifetimes and one Adapter for 160 synthesized responses; weak-reference reclamation and bounded retained counts |
| N/I | Missing/expired/replayed or mismatched grants; concurrent duplicate admission opens once; copied/foreign-scope handles cause zero cancellation; no business authority surfaces; revoked capture with sealed audio advertises no batch replay |
| T/C/R | Revocation during connect closes the late socket without wire delivery; old callbacks cannot retire a successor; queued audio is fenced after response revocation; deferred cleanup completion releases route capacity; activation renewal cannot remint a consumed request |
| B/F | Eight occupied recognition resources reject the ninth before wire allocation and recover after release; unconsumed terminal queues continue occupying synthesis capacity; existing noncooperative transport/worker cleanup and feature-off/timeout/event validation regressions |
| K/X | Actual local Gateway/Registry/Adapter/conformance with simulated wire, including existing product downlink/fallback and Media Registry regressions; no network Provider, microphone, speaker or full Demo claim |

Main completed the scoped diff review. Independent read-only review used
`codex review`, then a bounded continuation of the same retained review context
(`01a06b2d-8aa7-7083-b95e-20a6e59b6597`) after stopping repetitive reads. The final
product hashes match those captured by the reviewer. Its conclusion was **no
actionable introduced or acceptance-violating defects** in this Tier-3 local
authority / Tier-2 lifecycle boundary. The local final report is
`logs/speech-lifecycle-independent-final.txt`.

This repair has scoped source closure. The overall project remains **PARTIAL**:
no real remote Provider, physical microphone/speaker, full Demo, private-config
or deployment validation was performed. Services stay on their existing source;
no deployment or push is authorized by this packet. Other Task, artifact,
offline/ACK/refresh, Native and cumulative product gates remain open as recorded
in STATUS.
