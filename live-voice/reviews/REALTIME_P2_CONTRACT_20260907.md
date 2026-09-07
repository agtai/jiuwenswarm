# Realtime P2: bounded continuation and receipt observation

Main accepted this Tier-3 module on 2026-09-07, against baseline
`ebeb5aa4db828b69489ce205de85ebd1d3a1c5a5`. The worker owns only the separate P2
worktree and does not commit, integrate, push, change models or call Providers.
Main performs complete-diff review, integration and the one P2 commit.

## Intended behavior and owned boundary

Native canonical business receipts use deterministic sorted-key serialization
on both first completion and journal replay. Saved operation facts and their
execution identity remain immutable. Historical first-send key order was not
stored and cannot be reconstructed; this repair does not rewrite old rows.

A versioned Provider receipt projection may remove only redundant embedded
context after validating the complete canonical receipt. Operation/result/error
facts remain complete. The original canonical text owns Runtime and replay
digests. A complete current context is supplied before every business successor;
initial activation and reconnection always bootstrap complete context. Existing
context, work and Task reads retain their full data. Unsupported projection input
falls back to the original complete receipt.

A closed, explicitly versioned observation request travels over the existing
authenticated Gateway-to-AgentServer native.propose RPC. Its owner epoch and
per-scope sequence are observations, not authority. Work changes wake a bounded
wait; timeout still refreshes context so external Task/history writers are not
assumed to emit signals. The waiter cannot hold Registry/admission locks or miss
a transition between cursor inspection and installation. Activation/scope are
revalidated before release. Closing/restarting an owner wakes or cancels waiters;
an epoch change requires a full snapshot. Gateway coalesces concurrent immediate
context reads and rejects stale activation completions.

Only the Engine may prepare one unadmitted business successor while the exact
predecessor's completed Provider audio drains. Runtime admission, audio/history
ACK and its single presentation owner stay unchanged. Preparation requires a
current accepted turn, complete sibling receipts, no pending user input and no
competing preparation. Provider generation and actual playback identities stay
separate. Prepared audio, transcript, function arguments and terminal observations
are validated and bounded; none grants SPEAK, DELEGATE, display, audio, history or
completion authority. The exact predecessor's real ACK permits revalidation and
ordinary ordered SPEAK admission, followed by lazy ordered output release.

Speech/new-turn/STOP/revision/activation retirement fences the prepared successor
without cancelling admitted Agent work or Tasks. Overflow cancels that exact
Provider response, drops unpublished output and preserves predecessor playback
and its real ACK. A continuation may retry only after exact Provider cleanup has
been confirmed and its original identity remains current. This module will not
guess unsupported item-deletion/truncation confirmation: if cleanup cannot be
proved it blocks further Provider generation, reports a specific continuation
failure and preserves work/results. No partial generation is a completed result.

## Ownership, dependencies and exclusions

Owned source: Native Router/work observation and receipt helper; Native Engine;
Gateway Native client/media coordinator; the Registry's observation dispatch
seam. Their focused tests and affected Native Runtime regressions are included.
Native Runtime/ConversationRuntime admission, P1 business-tool schemas, Provider
or Agent model configuration and canonical Task policy are excluded. Main's P0
Engine edits will be reconciled during adoption. The complete optimization packet
and STATUS remain Main-owned.

## Applicable acceptance

| Dimension | Required evidence |
|---|---|
| P | Complete real receipt facts, identical first/replay canonical bytes; immediate terminal wake over serialized RPC; prepared successor speaks only after exact predecessor ACK. |
| N/B | Wrong scope/capability/cursor, malformed projection, oversized prepared output and unsupported cleanup have zero forbidden business/audio/history effects. |
| S/T | Provider done is distinct from played ACK; done-before-promotion, delayed predecessor events, new turn, cancelled/superseded work and activation replacement cannot revive output. |
| C | One prepared successor and one actual audio owner; all sibling receipts settle; cursor wait installation has no lost wake; concurrent refreshes cannot overwrite newer ownership. |
| R | Duplicate/restart receipt replay never reexecutes; epoch change restores full observations; wait cancellation removes resources; unknown cleanup never authorizes retry. |
| I | Exact activation/turn/Provider/Runtime/work revision and context bindings are retained throughout preparation, promotion, cancellation and ACK. |
| F/K | Legacy/Cascade and extension-off behavior remain; full queries and original canonical receipts remain available; failure is distinct from work outcome. |
| X | Serialized Gateway/Registry and real SQLite tests; Main-owned current-Provider conformance and physical uninterrupted/interrupted handoff remain required for runtime acceptance. |

Tests use the root Python 3.11 environment, PYTHONUTF8=1, isolated temporary data,
`--no-cov -o addopts='' -o log_cli=false` and a unique worktree-local basetemp.
Scoped static checks and complete-diff/independent review are required. No
unmeasured latency improvement or complete physical/product acceptance is claimed.

## Implementation and evidence

The candidate is implemented. Main owns independent review, integration with
P0/P1/P3, exact Git status/diff inspection, the single P2 commit and current
Provider/physical acceptance. The worker performed no Git operation or Provider
call. Source/tests are frozen after the final affected checks below.

Modified source:

- `jiuwenswarm/server/live_voice/native_work_runtime.py`
- `jiuwenswarm/server/live_voice/native_business_router.py`
- `jiuwenswarm/server/live_voice/product_composition_registry.py`
- `jiuwenswarm/server/live_voice/openai_realtime_native_engine.py`
- `jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py`
- `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`

New source/tests, to include explicitly during Main's adoption:

- `jiuwenswarm/server/live_voice/native_business_observation.py`
- `jiuwenswarm/server/live_voice/native_continuation_preparation.py`
- `tests/unit_tests/live_voice/test_native_business_observation.py`
- `tests/unit_tests/live_voice/test_native_continuation_preparation.py`
- `tests/unit_tests/gateway/test_native_business_observation_gateway.py`
- This contract document.

### Recorded verification

All commands use
`C:/Users/admin/Desktop/live voice hx/.venv/Scripts/python.exe`,
`PYTHONUTF8=1`, a worktree-local `JIUWENSWARM_DATA_DIR` and a unique
`--basetemp`. The common pytest options are
`-q -o addopts='' --no-cov -o log_cli=false --show-capture=no`.

The ten-module affected command ran these paths and passed **473 tests in
82.37s**; its output is `.p2-pytest-final.txt` in the P2 worktree:

```text
tests/unit_tests/live_voice/test_native_business_observation.py
tests/unit_tests/live_voice/test_native_continuation_preparation.py
tests/unit_tests/gateway/test_native_business_observation_gateway.py
tests/unit_tests/live_voice/test_native_business_registry.py
tests/unit_tests/live_voice/test_native_work_runtime.py
tests/unit_tests/live_voice/test_native_work_journal.py
tests/unit_tests/live_voice/test_openai_realtime_native_engine.py
tests/unit_tests/live_voice/test_native_interaction_runtime.py
tests/unit_tests/gateway/test_native_interaction_runtime_client.py
tests/unit_tests/gateway/test_dedicated_media_registration.py
```

After that command, cold review tightened terminal-item representation, prevented
prepared items from reusing predecessor audio/function identities, and retained
the exact socket receive task across concurrent close. The affected follow-ups
passed **27 tests in 28.40s** (preparation + real business Registry;
`.p2-pytest-last-edges.txt`) and **183 tests in 66.51s** (preparation + Engine;
`.p2-pytest-control-final.txt`). Ruff passed for all eight owned source files and
all three new test files after the final source changes.

The new regressions cover actual serialized Gateway/AgentWebSocketServer work
terminal wake; exact scope/capability and activation retirement; lost-wake-free
cursor installation, bounded waiter cancellation/close and epoch replacement;
coalesced context reads and out-of-order snapshot rejection; actual SQLite
first/replay byte identity without Task reexecution; complete result projection
and canonical digest preservation; both terminal/played-ACK orders; local wake;
unadmitted function isolation; paced PCM/control priority; stale work revision;
pre-created retirement; timeout/overflow; multiple-item cleanup; unsupported
function cleanup; and rejected predecessor-item reuse with zero old-audio
truncation or successor audio/history authority.

A broader earlier run including the complete
`test_product_composition_registry.py` produced 632 passes and 69 failures. One
was a P2 direct-turn duplicate context injection, fixed and covered by the final
183-test run. The other 68 Registry failures are not silently waived. Three
isolated representatives were run on both this candidate and the existing
`C:/Users/admin/Desktop/live voice hx-realtime-p5-20260907` baseline, whose
Registry/Runtime remain at `ebeb5aa4`:

```text
test_native_available_result_uses_toolless_agent_delegate
test_unified_default_cancel_keeps_confirmation_boundary_and_zero_mutation
test_text_intent_create_requires_later_exact_committed_confirmation
```

Both commands failed the same three assertions: `dialogue` instead of
`background.query`, one Agent call instead of zero on the default-cancel path,
and `PRODUCTION_TASK_INTENT_UNAVAILABLE` on natural-language Task creation.
Candidate/baseline durations were 25.98s/34.58s; logs are
`.p2-candidate-legacy-representative.txt` and
`.p2-baseline-legacy-representative.txt`. This establishes only those exact
baseline comparisons. Full Registry candidate/baseline comparisons were already
started before writer freeze, with output files
`.p2-candidate-registry-comparison.txt` and
`.p2-baseline-registry-comparison.txt`; Main will record their completed verdicts.
These command outputs, temporary test data, caches and logs are excluded from
the P2 commit.

Current Provider event-shape/truncation-ACK conformance, measured latency and
physical uninterrupted/interrupted playback remain Main-owned and unclaimed.
Generation-in-progress promotion is explicitly excluded below. Unknown cleanup
requires a new Provider session; no function-item delete protocol is invented.

### Accepted bounded-v1 release refinement (before implementation)

Main accepted this refinement on 2026-09-07 after inspection found that a burst
of fully buffered PCM could saturate Gateway's existing delivery queue and delay
Provider interruption controls. Promotion requires **both** a closed completed
Provider terminal and the exact predecessor played ACK, in either arrival order.
Generation-in-progress promotion is excluded from this version. A prepared audio
response must contain one audio item; mixed audio/function or multiple audio
items fail closed so interruption retains one exact truncation identity.

Prepared PCM releases at its actual sample cadence. One retained socket receive
continues throughout release, and newly received speech/STOP controls take
priority over unreleased prepared audio. The existing Gateway/Runtime admission
and playback owners are unchanged. A 15-second preparation deadline discards
the unadmitted output and cancels its exact known Provider response. Missing
response identity, terminal or cleanup confirmation quarantines further
generation with an explicit continuation failure; elapsed time never proves
cleanup or completion. Overflow retries once without preparation only after
confirmed context cleanup and the predecessor ACK. Accepted work remains owned
by the independent Native work runtime. Actual latency benefit requires Main's
real Provider and physical acceptance probes.
# Independent-review repair checkpoint (2026-09-07)

Main transferred the same twelve-file P2 writer lease to
`live voice hx-realtime-p2-review-repair-20260907`, based on `81aae293`.
The previous frozen candidate remains review evidence. Its passing tests did not
cover four reproduced defects: fresh post-terminal authority, promotion revival
after close, incomplete terminal preflight, and promotion RPC blocking the sole
Provider reader. This checkpoint supersedes any previous closure claim for those
four boundaries. P0/P1/P3 integration is retained; Runtime admission is unchanged.

The repair has these explicit contracts:

- Fresh socket events for a prepared response after its observed terminal cannot
  acquire audio, transcript, function or completion authority. Only the already
  verified buffer can be replayed. Exact cleanup receipts and input controls are
  still routed by their own identities.
- A completed preparation must have a nonempty, bidirectionally exact terminal
  manifest: output index, item ID, audio content index or function call identity,
  completed item status and raw final transcript/arguments all agree. Audio and
  transcript done are required once; metadata cannot hide an additional item.
  Transcript canonical-text limits and each audio event's expansion into the
  configured Runtime queue are checked before any SPEAK or Runtime admission.
  Incomplete/cancelled cleanup conservatively retains every known audio target;
  it does not infer a complete output or an unsupported function-delete receipt.
- With preparation enabled, exactly one coalescing Engine scheduler task performs
  context RPC and generation scheduling independently of the sole socket reader.
  Reader-triggered scheduling never waits for that RPC. Other callers may await
  the same owned task. Scheduling has a 15-second deadline, owns and consumes its
  exceptions, wakes the local reader on failure, and fences further generation.
  Close cancels the task and waits only the configured close timeout; an
  uncooperative callback leaves close incomplete, with the task retained until
  it settles. No replacement scheduler starts in a closing or failed engine.
- Every asynchronous scheduler/promotion boundary revalidates operational state,
  the exact prepared/inflight slot, source turn, pending user input, predecessor
  and current work membership before mutating authority or sending another
  Provider event. A retired request stays retired even if the callback returns a
  previously valid context. Close clears unpublished actions/audio and cannot be
  undone by a late callback. Accepted business work is never cancelled here.

Affected acceptance includes both ACK/terminal orders; late fresh audio, function,
transcript and terminal events; blocked promotion refresh with one production
reader consuming speech; close, timeout, source/work retirement during refresh;
no-successor legacy behavior; exact cleanup receipt routing; malformed manifest,
duplicate done, transcript control/size and frame-expansion rejection with zero
successor effects; valid named P1 and legacy tools; and P0 receive-time profiling
before admission without duplicate replay measurements. Provider conformance,
physical latency benefit and unified user acceptance remain Main-owned evidence.

### Repair verification and handoff

#### Early control-receipt repair checkpoint

The final independent review reproduced two further scheduling races in
`logs/p2-independent-early-truncate-ack-probe.log` and
`logs/p2-independent-early-cancel-error-probe.log`: the socket had written a
truncate/cancel, but `send_event` had not returned, so the sole reader consumed
the exact ACK/error before the Engine had registered the returned client ID.
Main authorized this additional four-file repair; the earlier freeze is reopened
only for these control receipt boundaries.

Before awaiting a prepared zero-played truncate, the helper records one exact
pending audio target. It may retain one early exact zero-ms receipt flag, bounded
by that pending target, but does not add it to confirmed ACKs. Only a successful
`send_event` return, for the same live prepared slot, confirms the send and moves
that flag into the ACK ledger. Unsolicited, foreign, wrong-index and nonzero-ms
receipts cannot fill the latch. Failure, cancellation, close or unknown send
outcome clears the pending latch and grants no cleanup, retry or new generation.

The existing Session owns client event IDs inside its private send lock and has
no caller-supplied event-ID API. This repair neither predicts the counter nor
changes that API. Instead, each exact in-flight truncate/cancel has at most one
bounded canonical early error correlation ID. A truncate error matching the
actual returned ID marks cleanup unsupported and clears any early ACK; a foreign
or conflicting error remains fatal and cannot authorize fallback. Only the
already recognized `response_cancel_not_active` exception may use the cancel
latch, serialized by the existing cancel lock, and is accepted after the returned
ID matches the exact locally fenced cancelled response. This is not terminal
evidence: actual `response.done` remains required before cleanup or another
generation. Missing/malformed correlation, conflicting latch, failed send and
unknown outcome remain fenced and wake the reader on failure. Prepared truncate
sends share the existing cancel lock, so only one pending control-send owner can
exist; already confirmed cancel/truncate receipts take precedence over that
pending owner. Closed error fields are validated before latching. Early errors
are reconciled before an early ACK may be transferred into cleanup proof.
Every latch is
cleared on completion/cancellation/close, without a second socket reader or a new
Runtime admission owner.
Cancellation during the send is an unknown outcome even if the socket had
already written: when the Engine is still operational, the control-send owner
itself marks failure and wakes/fences the Engine before propagating cancellation.
This also applies to STOP/cursor callers outside the scheduler. Closing/failed
owners are never revived by the failure path.

The same review reproduced STOP waiting behind the prepared truncate socket
write (`logs/p2-independent-stop-control-lock-probe.log`). The shared lock owns
only actual Provider control sends: local response fencing has no await and
atomically discards old PCM and queued authority without acquiring that lock.
The complete `stop_foreground` path and its following LISTEN must finish before
an unrelated prepared-cleanup write returns. A delayed public cursor cancel
rechecks operational state and its exact admitted response after the cancel
send, before issuing truncate. After a completed truncate send, a closed/failed
owner may return its truthful sent IDs to the original caller, but cannot publish
new cancellation state or restore LISTENING. Unknown cursor-send outcomes fail
and wake their own owner; closure cannot be reversed by their settlement.

Acceptance adds early/late exact truncate ACK, pre-intention/foreign/wrong cursor
receipts, early matching/foreign/conflicting truncate error, send failure and
timeout after an early ACK, source close, and early exact cancel-completion race
plus foreign/conflicting errors. It also includes full STOP/LISTEN handling
under pending prepared truncate and close/failure between cursor control sends.
All negative cases must show zero confirmed
cleanup/retry/new generation and zero successor audio/delegate/history effects.

Main's subsequent real `gpt-realtime-2` capture reproduced an explicit Provider
shape gap in the frozen helper: message items in `response.output_item.done` and
`response.done.output` include `phase: "final_answer"` and audio content uses
`type: "output_audio"`, while content-part events still use `type: "audio"`.
The synthetic capture is Main's
`logs/p2-real-shape-capture/audio-synthetic-output-events.json`; the bounded
schema report is `audio-failure-shape.json` in that directory. Main authorized
unfreezing only for this observed compatibility. The helper admits exactly the
optional `phase="final_answer"` field and the observed terminal content alias;
raw transcript, output/content index and complete-manifest checks remain exact.
`phase="commentary"`, text content and unknown fields remain unsupported. This
also preserves the fail-closed result of Main's separate forced named-tool probe
that produced commentary/text before its function item; that mixed composition
does not establish supported function-only output or justify admitting text.

The repair changes only `openai_realtime_native_engine.py`,
`native_continuation_preparation.py`, `test_native_continuation_preparation.py`
and this contract. All other copied P2 files remained untouched in this worktree.
Main explicitly owns a subsequent observation-retention repair in
`native_work_runtime.py` and `test_native_business_observation.py`; neither file
may be copied back from this worktree during adoption.

All commands below used
`C:/Users/admin/Desktop/live voice hx/.venv/Scripts/python.exe`, working directory
`C:/Users/admin/Desktop/live voice hx-realtime-p2-review-repair-20260907`, with
`JIUWENSWARM_DATA_DIR=logs/p2-repair-data`,
`PYTHONPYCACHEPREFIX=logs/p2-repair-pycache`, and
`TEMP=TMP=logs/p2-repair-temp` resolved to absolute paths. Each pytest invocation
included `--no-cov -o addopts='' -o log_cli=false`,
`-o cache_dir=logs/p2-repair-pytest-cache` and its separate basetemp below.

| Evidence | Exact selection and result |
| --- | --- |
| `logs/p2-repair-preparation-01.txt` | `-m pytest tests/unit_tests/live_voice/test_native_continuation_preparation.py --basetemp=logs/p2-repair-basetemp-01 -q`: 21 passed in 82.14s. Prior fixtures were replaced with explicit audio/function terminal shapes. |
| `logs/p2-repair-preparation-02.txt` | Same module with new review regressions, basetemp `-02`: 44 passed, 9 failed. These were new test assumptions, not classified as baseline: four tests needed the retained socket-reader readiness barrier, four used the wrong proposal attribute, and one expected STOP after the predecessor was already acknowledged played. The corrected single reader now asserts immediate LISTEN/user input handling and cancellation of the unadmitted successor. |
| `logs/p2-repair-engine-preparation-03.txt` | Preparation + `tests/unit_tests/live_voice/test_openai_realtime_native_engine.py`, basetemp `-03`: 214 passed, 1 failed. This was a repair regression: a real completed socket send did not settle its original caller after STOP. Fixed by returning the true send receipt while retaining the cancelled presentation identity and forbidding state revival. |
| `logs/p2-repair-affected-04.txt` | Preparation + Engine + `tests/unit_tests/live_voice/test_native_business_encoding_engine.py` + `tests/unit_tests/live_voice/test_native_business_diagnostics.py` + `tests/unit_tests/gateway/test_native_business_observation_gateway.py`, basetemp `-04`: **249 passed in 45.48s**. |
| `logs/p2-repair-final-affected-05.txt` | Preparation + Engine, `-k 'scheduler or overflow or foreground_stop_settles or preparation_deadline or noncomplete or cancel_before_prepared'`, basetemp `-05`: **17 passed, 204 deselected in 3.96s**, after the last two fixes and two new socket-failure regressions. Confirms retry resets its confirmed Provider identity, and a scheduler whose send already marked Engine FAILED still wakes the sole reader and waiting callers. |
| `logs/p2-repair-real-shape-06.txt` | Complete preparation module, basetemp `-06`: **65 passed in 26.14s**, after the captured `final_answer`/`output_audio` compatibility change. Includes the real event ordering and 20-frame chunks, complete paced admitted playback, plus commentary, null phase, unknown field, text and conflicting transcript rejection. |
| `logs/p2-repair-real-corpus-replay.json` | `python logs/p2_repair_replay_captured_audio.py` replays Main's complete original synthetic capture offline through Engine closed-event/envelope validation and the helper: **21 source events, 16 verified replay events, 140036 retained bytes, one audio target, completed terminal verified**. No Provider call or Runtime/business/audio/history effect. Capture SHA256 `ca37408d1f8cde42b7496b2f9cfcef81756c2cf812b4ad502e912e6c983be535`. |
| `logs/p2-repair-ruff-final.txt` | Ruff check of the three changed Python files; cache under `logs/p2-repair-ruff-cache`. |

The final scenarios establish zero unverified successor PCM/delegate/completion
authority before admission, exact first-terminal/first-ACK promotion, current
source/work fencing, post-terminal fresh-event rejection with cleanup receipts
still usable, paced control priority, bounded close including a callback that
suppresses cancellation, scheduler fault/timeout wake, and ordinary flag-off
Engine compatibility. Named `context.get`, `work.get`, `task.create` and legacy
`jiuwen_business` proposals replay successfully only after Runtime admission;
actual Agent/Tool/Task execution is outside this Engine test and is not claimed.
P0 first-audio/arguments observations retain their earlier receive timestamp and
have no later Runtime identity inserted or duplicate observation on replay.

The observed-shape helper was frozen for Main's real Provider conformance probe
at SHA256 `522B3AA96E5BD4C6FE78AE3A65FE17E84FB236467EC2A1409D6AE0E34404E535`.
That historical freeze superseded `F098EB87...`; the control-receipt repair below
now supersedes it without changing the supported Provider output composition.
Full writer handoff remains uncommitted at `81aae293` with no upstream configured.
No Provider call, Git mutation, Runtime-admission change or new subagent was made
by this worker. Main retains independent max review, final integration, Provider
evidence, physical audio/latency measurements and the P2 commit.

#### Control-receipt verification and renewed freeze

This final repair retains the same four-file scope. Tests use the same Main
Python, worktree, bytecode/cache/temp settings and mandatory pytest options
recorded above, except `JIUWENSWARM_DATA_DIR` is the absolute worktree path
`logs/p2-control-receipts-data`. Each basetemp is
`logs/p2-control-receipts-basetemp-NN`, where NN matches the log run number.

| Evidence | Exact selection and result |
| --- | --- |
| `logs/p2-control-receipts-01.txt` | Preparation module, `-k 'truncate or cancel_not_active or early_cancel_error'`: 24 failed, 64 deselected. All failed at the newly added fixture's incorrect `config` keyword, corrected to `session_config`; these were repair fixture failures, not baseline failures. |
| `logs/p2-control-receipts-02.txt` | Same selection after fixture correction: **24 passed, 64 deselected in 6.50s**. |
| `logs/p2-control-receipts-affected-03.txt` | Preparation + ordinary Engine modules, `-k 'truncate or cancel or cleanup or scheduler or close or overflow or noncomplete or foreground_stop_settles'`: **93 passed, 159 deselected in 15.34s**. |
| `logs/p2-control-receipts-final-04.txt` | Preparation module, `-k 'early_truncate_error or early_truncate_ack or early_exact_truncate'`: **10 passed, 80 deselected in 3.44s** after protecting intention registration with its finally cleanup. |
| `logs/p2-control-receipts-close-05.txt` | Preparation module, `-k 'close or early_truncate_ack or external_cancel'`: **17 passed, 74 deselected in 4.46s** after synchronous close retirement of external pending receipts. |
| `logs/p2-control-receipts-stop-06.txt` | Preparation module, `-k 'stop_and_following_listen or public_cursor_control'`: **7 passed, 91 deselected in 1.21s**. Full STOP/LISTEN completes while prepared truncate still owns the send lock; public cursor cancel/truncate each cover close, Provider failure and cancelled send. |
| `logs/p2-control-receipts-final-07.txt` | Preparation + ordinary Engine modules, `-k 'truncate or cancel or cleanup or scheduler or close or fence or overflow or noncomplete or foreground_stop or stop_and_following_listen or public_cursor_control'`: **112 passed, 148 deselected in 17.52s** on the final code. |
| `logs/p2-control-receipts-ruff-final.txt` | Ruff checks all three owned Python files with cache under `logs/p2-repair-ruff-cache`: clean. Tracked Engine `git diff --check` is clean; Git reports only its existing CRLF conversion advisory. |
| `logs/p2-independent-stop-control-lock-fixed-probe.log` | Independent max reviewer reran the original single-reader STOP probe: before send release, STOP completed, LISTEN returned, old response was cancelled, control lock remained owned and scheduler remained pending, with no played ACK. After exact cleanup ACK and send release, cleanup completed, retry stayed false, response.create count stayed two and released-audio count stayed one. |

The confirmed send ledger and early receipt latch stay distinct. Failure,
timeout, cancellation, close, malformed/foreign/conflicting correlation and
wrong/pre-intention ACKs never authorize cleanup or another response. Real
terminal confirmation remains required independently of the recognized cancel
completion race. A completed external cursor write can settle its caller while
retaining CLOSED/FAILED, with no later send or local state resurrection. Existing
cancel replay, cursorless fencing and ordinary foreground/delegate paths remain
covered by the affected ordinary Engine checks. No Registry/full-suite rerun or
new Provider evidence is claimed for this repair.

The helper is now frozen at SHA256
`6A1BAA97D1B4411BF531E6824E05F44950175C2F239FAFBC406C0414E320DA24`.
The exact renewed four-file manifest is
`logs/p2-control-receipts-final-manifest.json`. Main must adopt only those four
files; all other copied P2 files remain excluded, including Main's newer
observation retention and Gateway P7 changes. Main owns the subsequent independent
review, real Provider conformance with begin/confirm/ACK cleanup proof, integration
and final P2 commit. Physical latency benefit and generation-in-progress promotion
remain outside this deterministic repair's evidence.
