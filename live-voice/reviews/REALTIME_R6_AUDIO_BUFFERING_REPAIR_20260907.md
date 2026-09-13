# R6 actual PCM reserve and exact drain contract — 2026-09-07

Status: browser module committed as `9d46db79` and independently reviewed by
Main without a module blocker. The subsequent Gateway scheduling extension is
implemented and independently reviewed by Main; product EOF bridge and integrated
acceptance remain pending. Main execution
packet: `REALTIME_ACCEPTANCE_REPAIRS_20260907.md` in the integration worktree.
User authorized implementation with “开始”. This worker owns the browser audio
adapter, AudioPort, applicable media leaf validation, their tests and this record,
plus the narrowly authorized Gateway extension below. Main owns integration;
the lifecycle worker owns product-route/Panel
bridges, fault handling and backend receipt semantics. No service, configuration,
Provider, model or real-session changes belong to this worker.

## Intended behavior and limits

The previous 250 ms value was future scheduling silence, not received PCM.
After starvation it also added 250–750 ms to an already late source. R6 keeps
that bounded build setting as a **received PCM duration threshold**. It retains
an unscheduled FIFO until the threshold is met, then schedules that real prefix
contiguously with only a 20 ms graph scheduling margin. While scheduled audio
remains ahead of the clock, new PCM extends its exact endpoint. Starvation
starts a new reserve from unscheduled PCM; no already scheduled source is moved,
stopped or recreated for recovery. Arbitrary future supply gaps remain possible.

The outstanding accepted prefix is bounded by 256 chunks and 5,120 ms of PCM.
A reserve wait is bounded to 4,000 ms from the first unscheduled chunk, not
extended by each small arrival. Timeout/overflow fences the exact response,
cleans its resources and reports failure; it never pretends that silence or a
partial prefix is a completed stream. Frozen drains have a separate deadline
of outstanding PCM duration plus 2,000 ms, including time spent paused.

## Exact completion and fault-prefix seam (Tier 3)

`AudioPort` freezes a response-wide manifest of every accepted unit and its
last contiguous sequence. Frozen input rejects all further enqueue calls, while
actual contiguous acknowledgements remain valid. A verified seal must match the
entire current accepted manifest exactly; missing/extra/duplicate units, wrong
identity, invalid cursor and conflicting second completion are rejected without
changing the live owner. The snapshot is independent of already rendered data.

`BrowserAudioIOAdapter.sealPlayoutExact(response, acceptedCutoff)` accepts only
an already verified EOF manifest supplied by the product route. It flushes a
short final FIFO and returns an immutable drain handle. The route verifies
batch frame count or the dedicated media leaf's exact expected-completion
detach before calling it. Socket close, elapsed time and partial arrival cannot
supply this authority. `freezePlayoutPrefixExact(response)` instead snapshots
only the browser's current accepted prefix, immediately closes append authority
and drains that bounded prefix. It cannot be upgraded to verified EOF.

Both handles retain exact response identity, completion kind, accepted cutoff
and a completion promise. A receipt additionally includes the actual contiguous
rendered cursor. Only actual `source.onended` advances rendered acknowledgement.
The terminal outcomes are `render_completed` for verified EOF, `prefix_settled`
for unknown-EOF fault prefix, or `stopped`/`timeout`/`failed`. A prefix receipt
does not authorize successful generation, complete history or final business
presentation. Backend generation status remains independently authoritative.

STOP, replacement, close, hidden page and context loss retire queued PCM,
timers and drain waiters synchronously before any delayed callback can revive
them. Tentative pause retains the current exact sample offsets and unscheduled
FIFO separately; resume never treats an unstarted partial FIFO as a reserve.
The existing explicit pause/resume source handling is not rebuffer recovery.

Transport ACK continues to mean the bounded browser queue accepted the exact
chunk. Product-route `#scheduleDownlinkAck` already releases it after successful
enqueue, independently of `render_completed` and the rendered receipt RPC.
Thus the 8 × 20 ms transport window can refill the 250 ms reserve. No transport
ACK schema or backend EOF protocol expansion is currently required. Lifecycle
worker owns both product-route EOF bridges and the fault-prefix caller.

## Acceptance and risks

Required scoped evidence: replay the observed g1/g5/g17 first-eight arrival
timings, verify no early thin-prefix source starts, no additional 250–750 ms
per-frame reserve, contiguous sample order after reserve release, recovery
without old source stop/recreation; short verified EOF versus unknown EOF;
sequence/identity/duplicate/manifest negatives; queue and wait bounds; STOP at
buffering, scheduled, paused and draining stages; reentrant observers and stale
callbacks; transport credit ahead of actual rendering; actual cursor only from
contiguous render callbacks. Source-start/cleanup failures remain fail-closed.

The frontend scoped type checks and affected tests close deterministic software
claims only. Main owns cumulative integration and real browser/user acceptance.
Physical audio and unpredictable event-loop or upstream supply delays remain
unproven until that acceptance. This repair does not claim earlier Provider PCM,
eliminate arbitrary supply starvation or replace the browser graph with an
AudioWorklet. Cold diff and independent review are required before handoff.

## Implementation and coordinated seams

The implementation retains one FIFO of accepted, unscheduled PCM. Source
creation is delayed until that FIFO contains the reserve, a still-scheduled
prefix can be extended, or a verified EOF/frozen prefix closes append authority.
Buffer scheduling uses the existing Web Audio sources; recovery invokes no
`stop` and recreates no old source. Comparison at one-sample clock precision
prevents floating-point addition from inventing starvation at an exact endpoint.

The existing source setup/cleanup failure latch remains authoritative. Deferred
buffer waits have exact timer identity as well as response ownership: even a
cleared startup callback cannot terminate a later recovery wait on the same
response. STOP retires pending PCM and resolves drain waiters before any later
promise callback can run. Actual rendered cursors come only from the preexisting
contiguous `onended` acknowledgement path.

`queued_pcm_ms` is one new numeric diagnostic field. First-eight/late arrival
records report the real unscheduled duration. Scheduling diagnostics retain
actual arrival lateness separately from the final scheduled gap; they do not
attribute time spent buffering to the Provider. No PCM, text or private context
enters those records.

Main also approved the closed reason `MEDIA_NATIVE_PROVIDER_TRANSPORT_FAILED`
for the lifecycle worker's exact Provider fault classification. Browser codec
and dedicated leaf accept this reason without treating it as EOF. Python
classification/transport ownership and prefix-receipt handling belong to R3.
During R6 cold reading, the dedicated leaf's previous completion check was found
to omit the validated detach result and exact incoming lease/generation. R6
requires all three, so a foreign detach with a coincidentally matching cursor
cannot authorize `sealPlayoutExact`.

Main will combine the pure product EOF bridge and its short-tail route tests
with these modules into the final R6 commit. This module snapshot cannot be
deployed alone: the old product caller would keep a sub-reserve tail waiting
without calling `sealPlayoutExact`. Fault-prefix integration remains independently
owned and verified by R3. Main explicitly retains integration ownership.

## Scoped verification evidence

All commands ran in this worker's
`jiuwenswarm/channels/web/frontend`, using Node
`C:/Program Files/nodejs/node.exe`. TypeScript/esbuild came read-only from
`C:/Users/admin/Desktop/live voice hx/jiuwenswarm/channels/web/frontend/node_modules`.
Compiled output stayed in this worktree's `node_modules/.cache`; logs stayed in
the worker's `logs/r6`. No installation, network, Provider call, service or real
browser/session operation was performed. No root/integration branch was changed.

| Boundary | Result | Worker evidence |
| --- | --- | --- |
| Adapter + AudioPort + capture processor affected suite | 147 passed, 0 failed; 2.80 s | `logs/r6/adapter-port-fourth.log` |
| After final arrival-diagnostic precision and exact wait-timer identity repair | 21 affected tests passed, 0 failed; 0.54 s | `logs/r6/adapter-final-affected.log` |
| Gateway media codec + dedicated leaf | 74 passed, 0 failed; 0.58 s | `logs/r6/media-first.log` |
| Diagnostic field, bounds and privacy behavior | 8 passed, 0 failed; 2.03 s | `logs/r6/diagnostics-first.log` |
| Strict adapter/media TypeScript checks, no unused locals/parameters | passed | Tool output; commands below |
| Complete changed source and companion-test cold diff; `git diff --check` | passed; independent review pending | This record |

The final 21-test selection includes the additional same-response stale timer
regression. It overlaps the 147-test suite; counts must not be added as unique
cases. Initial logs retain the development failures: 38 old immediate-schedule
fixture expectations, then a real floating-point endpoint false starvation,
and one deadline test that omitted the existing required explicit unlock after
failure. These were corrected and their affected checks passed. They were not
labelled baseline failures. Lifecycle tests now supply a real 260 ms PCM chunk
when their purpose requires a scheduled source. Transport/timing tests use
explicit 20 ms chunks; there is no test-only threshold override.

The g1, g5 and g17 tests use the observed first-eight arrival timings from the
retained September 7 acceptance exports. All eight chunks (160 ms total) remain
unstarted despite taking about 639–1,020 ms to arrive. A clearly identified
controlled sustain burst then releases 260 ms at once. This establishes sample
order, no thin-prefix onset and no synthetic 250–750 ms per-frame delay; it does
not predict real first-audio latency. The delayed source-stop oracle verifies
32,640 distinct supplied samples remain 32,640 scheduled-render samples without
any recovery source stop or repeat. Verified short EOF (including a partial
last adapter chunk), mismatched and duplicate manifests, unknown EOF, reordered
and duplicate `onended`, missing first `onended`, pause, replacement, hidden page,
buffer/drain timeout, overflow and reentrant STOP are covered.

Representative exact commands (each CLI path prefixed with the read-only
dependency directory above):

```powershell
node <deps>/typescript/bin/tsc src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts --target ES2020 --module ES2020 --moduleResolution Bundler --skipLibCheck --noEmit --strict --noUnusedLocals --noUnusedParameters
node <deps>/esbuild/bin/esbuild src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts --bundle --platform=node --format=esm --outfile=node_modules/.cache/live-voice-browser-audio-io/browserAudioIOAdapter.mjs
node <deps>/typescript/bin/tsc src/features/live-voice/formal/audioPort.ts --target ES2020 --module ES2020 --moduleResolution Bundler --skipLibCheck --strict --rootDir src --outDir node_modules/.cache/live-voice-audio-port
node --test --test-reporter=tap tests/liveVoiceBrowserAudioIOAdapter.test.mjs tests/liveVoiceAudioPort.test.mjs tests/liveVoiceCaptureProcessor.test.mjs
node --test --test-reporter=tap --test-name-pattern='reserve|deadline|diagnostics|EOF|frozen|freeze|reentrant STOP|duplicate or gap|chunk and PCM duration' tests/liveVoiceBrowserAudioIOAdapter.test.mjs
node <deps>/typescript/bin/tsc src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts --target ES2020 --module ES2020 --moduleResolution Bundler --lib ES2020,DOM --skipLibCheck --noEmit --strict --noUnusedLocals --noUnusedParameters
node <deps>/esbuild/bin/esbuild src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts --bundle --platform=node --format=esm --outfile=node_modules/.cache/live-voice-browser-gateway-media/browserGatewayMediaTransport.mjs
node <deps>/esbuild/bin/esbuild src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts --bundle --platform=node --format=esm --outfile=node_modules/.cache/live-voice-browser-dedicated-media/browserDedicatedMediaRoute.mjs
node --test --test-reporter=tap tests/liveVoiceBrowserGatewayMediaTransport.test.mjs tests/liveVoiceBrowserDedicatedMediaRoute.test.mjs
node <deps>/esbuild/bin/esbuild src/features/live-voice/formal/audioDiagnostics.ts --bundle --platform=node --format=esm --outfile=node_modules/.cache/live-voice-audio-diagnostics/audioDiagnostics.mjs
node --test --test-reporter=tap tests/liveVoiceAudioDiagnostics.test.mjs
```

Main independently reviewed the browser module and exact EOF bridge. The bridge
seals both batch and streaming accepted manifests only after verified completion,
including 20 ms and 240 ms responses shorter than the startup reserve. The complete
product-route suite passed 138/138 after its nine old immediate-scheduling fixtures
were updated to observe the new received-PCM boundary. The integrated frontend
build passed. R3 fault-prefix integration and real browser listening remain
candidate-level acceptance; these checks do not claim physical hearing, complete
generation, successful history or a successful user journey.

The integrated Web script reported 689 tests / 664 passed / 24 failed / 1 skipped.
Independent comparison against the exact `af6a5bbb` frontend tree
`e8132f9027339b39ef7dde370ebf90de5b8b3e49` reported
680 / 655 / 24 / 1. All 24 failure names and first errors match, with no current-only
failure. The nine net additional cases passed. This is a baseline comparison,
not a full-green claim or a conclusion about the root causes of those old failures.
Full logs and the per-failure comparison are retained in Main's ignored `logs`.

## Gateway control scheduling extension — accepted implementation checkpoint

Main separately authorized this Tier 2 concurrency repair after the browser
module commit `9d46db79`. Its only additional owned surfaces are
`jiuwenswarm/gateway/live_voice/dedicated_media_route.py`, the existing
`tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py`, and this
record. Main independently reviews the complete control lifecycle diff and owns
integration. The prior browser modules, wire/schema, credit limits, admission,
logging/privacy policies, Provider/configuration and real services are excluded.

In the retained acceptance profile, Gateway clock
`python-27128-3fcd3f8a575e`, g17 frame 3 was ready by monotonic
274991550.885 ms. The leaf was still processing its third queued ACK at
274991694.284 ms: at least 143.4 ms of ready-PCM delay occurred before leaving
the ACK branches. The later source-ready diagnostic at 274991718.751 ms also
includes the following scheduling turn, binary encoding and diagnostic work;
it does not isolate their costs. Source pull 3 took 0.109 ms and the observed
window peak was 3/8. This proves one local delay boundary, not a complete cause
for the session's supply intervals or a predicted overall latency improvement.

Replace per-message receive tasks with one persistent control reader. It only
decodes closed control messages into an ordered mailbox; the leaf remains the
sole owner of `sender.acknowledge`, sent counts, STOP callbacks and termination.
The reader does not grant credit, send PCM or call product code. A mailbox holds
at most `max_pending_frames + 1` records, allowing a full credit-window ACK burst
followed by STOP. A further message fails closed with the existing protocol
error; duplicate floods cannot create an unbounded control scan. A non-ACK or
malformed control ends the scan immediately and blocks further PCM grants.

Every ACK is validated in original order, including duplicate, regressive,
wrong-scope and unsent checks. Taking only the highest cursor is forbidden.
After a batch the leaf gives its sole reader one lookahead turn, then checks
controls/termination before consuming a ready source. A full mailbox or terminal
observation cannot be skipped for audio fairness. Thus already queued
ACK-to-STOP/detach/error still prevents another PCM grant, while an ordinary
ready ACK burst no longer creates one receive task and scheduling turn per ACK.
There is no second socket reader or new cleanup-task slot. A local wake Future
is reset only after its mailbox is drained, and is cancelled on closure; hostile
late reads cannot refill it or invoke effects after retirement.

Receipts arriving while a socket write is still awaiting completion remain
observations. Only the existing leaf, after successful send return, may validate
them against sent authority. A failed/unknown write never receives false ACK
credit. Source and receive cancellation retain the existing two-slot cleanup
owner and deadlines. No already-started socket write is claimed reversible.

For the existing bounded frame diagnostic selection, `sent.queue_wait_ms` will
measure source-return to socket-send start on the same Gateway clock. It excludes
`socket_send_ms` and adds no content, field schema or logging policy. This permits
later actual-deployment comparison without conflating tiny source pull duration
with the wait to consume and send that ready frame.

Required acceptance: deterministic old/new ACK burst task/yield characterization;
positive full-window streaming; queued ACK(s) then STOP with simultaneous supply;
full-window STOP; invalid/regressive ACKs; bounded mailbox overflow; slow socket
send with an early exact ACK for both success and failure; truthful queue-wait
measurement; existing caller cancellation, hostile reads, delayed cleanup,
identity, feature-off and sync-source compatibility. Cold complete diff review
and Main independent review precede this backend worker commit. Actual latency,
real socket integration and browser hearing remain candidate-level evidence.

## Gateway extension verification

The original leaf at browser-module baseline `9d46db79` failed the new focused
characterization with exactly `(3 leaf yields, 4 reader owners)` for three ready
ACKs. The repaired leaf reports `(1, 1)` on the same oracle. This counts ownership
and scheduler turns; it is not a wall-clock latency benchmark. The existing
installed legacy WebSocket `recv` directly returns already queued messages, so
the permanent reader can consume that burst without private queue access.

| Boundary | Result | Worker evidence |
| --- | --- | --- |
| Old-leaf ACK burst characterization | Expected 1 failure; exact `(3, 4)` observation | `logs/r6/gateway-ack-baseline.log` |
| New ACK batching, STOP, bounds, early send receipt, timing cases | 8 passed; 3.83 s | `logs/r6/gateway-ack-second.log` |
| Complete existing dedicated media leaf suite, including the new cases | 124 passed; 4.99 s | `logs/r6/gateway-leaf-first.log` |
| Complete source/test cold diff and whitespace check | Passed | `git diff --check`; Main independent review accepted |

The first candidate run had two fixture failures: the test had waited for a
frame pull and injected its ACK before that frame was actually written. Both
fixtures now wait for the socket's observed write before building their intended
full-window scenario. Production send authority was not loosened. The slow-send
tests separately cover a real early observation while that write is unresolved.
Those tests prove no enqueue-ACK diagnostic before successful send return and
none after an unknown/failed outcome. The fake-clock test separates 125 ms
source-ready queue wait from a 20 ms socket-send interval.

Main independently reviewed the entire downlink leaf and all eight new checks
and reported no blocking finding. The review confirmed read-only receipt
collection, exclusive leaf ACK/STOP/send-result authority, terminal/overflow
checks before ready-PCM consumption, unchanged two-slot cleanup, and distinct
queue-wait/socket-send measurements. Main will combine this backend worker
commit with the browser module and pure product EOF bridge into one R6 point
commit; no integration branch or remote ref is changed by this worker.

Commands ran from this worker root with
`C:/Users/admin/Desktop/live voice hx/.venv/Scripts/python.exe`,
`JIUWENSWARM_DATA_DIR=<worker>/logs/r6/gateway-data` and
`PYTHONDONTWRITEBYTECODE=1`. All pytest invocations used the following options;
temporary directories and caches remained under this worker's `logs/r6`:

```powershell
python -m pytest tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py::test_async_downlink_ready_ack_burst_uses_one_reader_and_one_lookahead --no-cov -o addopts='' -o log_cli=false -o cache_dir=logs/r6/pytest-cache --basetemp=logs/r6/pytest-baseline-temp -q
python -m pytest tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py -k 'ready_ack_burst or control_batch or control_mailbox or early_ack or diagnostic_separates' --no-cov -o addopts='' -o log_cli=false -o cache_dir=logs/r6/pytest-cache --basetemp=logs/r6/pytest-focused-temp -q
python -m pytest tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py --no-cov -o addopts='' -o log_cli=false -o cache_dir=logs/r6/pytest-cache --basetemp=logs/r6/pytest-leaf-temp -q
```
