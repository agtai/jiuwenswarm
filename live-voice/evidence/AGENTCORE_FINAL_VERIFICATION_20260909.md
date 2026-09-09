# Unified AgentCore final verification

The agreed unified-execution implementation and its required automated/scoped
real verification are complete. Independent evidence review approved the bounded
Task, terminal playback and Work scenario. Earlier failed runs and the
continuous-connection limitation stay recorded below; this is not full product
or uninterrupted long-call acceptance.

## Installed SDK breadth

Verified source: `ffeb1abcc5cc0bc72b5c813a3316d4334d39e15f`, tree
`6f3826983ea8c15eb182ec7761705fd5058c1235`, twelve ordered patches.
Actual editable import resolves to the retained `.deps/agent-core` source.
The SDK has no upstream tracking branch. Local `core.autocrlf=false` preserves
the reviewed checkout bytes; refreshed index metadata did not change its tree.

One broad run covered complete affected owner unit directories: Harness (except
unchanged tools), agent_teams, React Agent, core/session, core/workflow,
core/common and core/foundation/llm. Result: **5492 passed, 16 failed, 38 skipped,
3 xfailed, 4 collection errors**, 3 integration-marked cases deselected (211.42 s).
The four errors require missing optional `prompt_toolkit` for the CLI; the
configured in-process Team boundary does not use that CLI.

Only the 16 failures were investigated/replayed with shorter isolated Windows
TEMP paths. Current source and pinned original `94e10cb6` each produced **10
passed and the same 6 failures**. Those six are one Windows path-length case,
one separator assertion and four unchanged NO_PROXY/CIDR assertions. Other broad
failures involved combined-run timing/state or the temporary write-isolation
guard. Original failed evidence remains; this is not an all-green SDK claim.
No new patch regression was demonstrated by this comparison. No broad rerun
was performed, and this environment result does not establish physical behavior.

Detailed commands, actual import origins, original output, report and exact
baseline comparison remain at
`%TEMP%/agentcore-final-breadth-f4b0db14dd9b4c28948f1aaa721666ba/REPORT.md`.

## Host breadth and scoped repair

The final Host selection contains **11,199 unique nodes**. All selected nodes
have outcomes; no completed node was duplicated by continuation. System/device
suites and the system marker are excluded for separate controlled acceptance.
The original accumulated result remains **11,038 passed, 117 call failures,
14 setup errors and 30 skipped**, plus **3 collection errors** for missing
optional desktop `webview`. This is not an all-green result.

All breadth partitions use frozen Host `c5137f2d` and installed SDK `ffeb1abc`:

| Partition | Passed | Call failures | Setup errors | Skipped | Completion |
|---|---:|---:|---:|---:|---|
| Initial | 2614 | 31 | 14 | 13 | 2672 reported nodes; cold Team teardown hung |
| First continuation | 1749 | 4 | 0 | 1 | 1754 nodes; test-side logger internal error |
| Binary-write fixture | 1 | 0 | 0 | 0 | Its previously unfinished node completed |
| Remaining continuation | 6674 | 82 | 0 | 16 | All 6772 nodes completed teardown |

The first owned process was terminated with an identity/cleanup receipt. The
second interruption came from a test monkeypatching JSON/file functions used by
the progress logger; freezing the logger's original functions repaired that
observer. The binary fixture then passed unchanged. The last process exited
normally with code 1 in 2088.70 s; no hung consumer remained. Initial interrupted
nodes do not receive a fabricated successful teardown result. Original output,
exact node IDs and phase ledger are retained in `%TEMP%/jhf-537n4x2k/`,
`%TEMP%/jhfr-dmlz8tln/`, `%TEMP%/jhfr2-binary-v8i66r11/` and
`%TEMP%/jhfr2-remaining-01zpi46w/`. Merged ledger and all failure details:
`%TEMP%/jhfr-review-bt_8r34k/REPORT.md` and `partition-summary.json`.

The deterministic Team cancellation repair and its 9 passing actual-SDK/Host
checks are recorded in the [Task 2 boundary](AGENTCORE_TASK2_COMMIT_20260909.md#final-verification-repairs).
The first snapshot also lacked its `.deps/agent-core` link: filling that required
environment binding allowed G0/G1-A to run against the actual installed source.
Three repaired SDK capabilities exposed obsolete strict-xfail annotations;
those assertions are now ordinary passing regressions. Catalog parity had one
missing re-export, now repaired. The affected catalog/G1-A group passed 14 tests,
with the two remaining gap characterizations xfailed.

The other 28 failed nodes were replayed against exact Task 1 Host source
`66833d5c`, with the same installed SDK and isolated data: all 28 reproduce the
same failures. They include old prompt-builder fixtures, a retired P2-submit
fixture, Windows shell/symlink assumptions, circuit-breaker expectations and
unchanged optional SDK observability interfaces. Full failures, original and
baseline import binding are retained at `%TEMP%/jhfretry-s6hw6aon/` and
`%TEMP%/jhbcheck-4r7hl3fm/`. This comparison does not relabel them as passing.
The two team_helpers static findings also reproduce unchanged on Task 1.

The first continuation's four failures also reproduce on exact Task 1 source
(`%TEMP%/host-four-baseline-u81tcy48/`). The remaining 82 are fully attributed:
80 have prior-baseline evidence and two were current test-oracle omissions,
corrected and reviewed as recorded in the Task 2 boundary. Of the 80, 18 were
reproduced on complete Task 1 exports this round; the 55 composition-registry and
7 semantic-registry failures match exact node IDs and first errors in the
existing September 8 two-module `a8afe0ca` baseline overlay. That historical
overlay is not presented as a new complete Task 1 execution. The other groups
cover existing path/shell/encoding/port/Windows atomic-write assumptions,
isolated data-directory expectations, old policy/retirement fixtures, Task
progress projections and the S7 script inventory gap. No production regression
was identified in that remaining partition. Full indexed comparisons:
`.codex_tmp/final-host-tail-attribution/REMAINING-82.md`.

Across the complete Host ledger, the 131 abnormal selected nodes decompose as
112 baseline failures (50 fresh complete Task 1 matches plus 62 historical
overlay matches), 15 initial source-link environment failures, two repaired
production defects and two corrected current test oracles. The three G1-A
strict XPASS observations after binding repair are part of those initial 15,
not three additional failed nodes. Collection errors remain outside this sum.

Only affected failures and repaired boundaries were rerun. The original breadth
ledger is preserved separately from passing repair checks and baseline
attribution; their overlapping counts are never added into a replacement green
suite total.

## Frontend build and entrypoint breadth

The full production TypeScript/Vite build passed. Subsequent changes do not
touch the frontend or its generator. The controlled deployment also passed its
distinct feature-enabled `build:live-voice` bundle (1 min 32 s). All 56 package test entrypoints
ran once: **54 passed, 2 failed**. Only those two were compared with Task 1:
upload-document-block has the same six failed cases; integrated-web has the same
11 failed cases and one skip. Key implementation/test/compiler files have exact
matching hashes. Existing upload `@path` behavior and absent old Task controls
disagree with the older test fixtures. These failures remain recorded and are
not evidence of a new unified-execution regression or an all-green frontend.
Details: `.codex_tmp/final-frontend-attribution/REPORT.md`, `comparison.json`
and `.codex_tmp/final-frontend-verification/results.json`.

## Controlled candidate and real journey

The clean isolated candidate `dc188fa0c5368f2b3ccf66496ae2f78e1862f7f9`
was launched with the installed editable SDK `ffeb1abc`. Both actual import
origins were verified from the candidate working directory. The source contract
reports zero dirty entries, native `gpt-realtime-2.1`, speed 1.25, minimal
reasoning and `server-vad-450`; its distinct Live Voice bundle/backend validation
and real TTS-to-STT deployment probe passed. The selected configured Agent is
`deepseek-v4-flash`. Candidate local entry is `http://127.0.0.1:6273`, using
same-origin API/media. The unrelated 5173 deployment was preserved.

The new disposable business project has no remotes and contains only an owned
JSON input baseline. The output must be created by the real Agent/Tools; neither
expected nonce nor sum is supplied in speech or written by the harness. Runtime
configuration hashes remain unchanged. Deployment source, runtime paths and
receipts are in `.codex_tmp/final-shared-acceptance/deployment-receipt.json`.

The first two browser preparations stopped before speech while the test-side
controller tried an unavailable startup control. The corrected controller waits
for actual UI configuration and an enabled start button, then clicks once. It
reuses the same digest-checked TTS samples. These attempts are not real scenario
passes. The third attempt passed ordinary real Provider/browser spoken output
and restored listening, but its next utterance ended in input queue backpressure
and media teardown. Task and independent Work utterances had not been sent.
The failed run and exact owned-browser cleanup are retained at
`%TEMP%/lv-unified-real-sorbyjl6/acceptance-ready/`. A continuation then completed
real interruption and a new answer with restored listening. Its original harness
froze 26 early 20 ms PCM blocks, all of which ended before VAD stopped later blocks
of the same response, causing a false-negative wait. The immutable browser/public
and server records establish exact old-response stop, new-response playback and
accepted receipt; the independent proof is
`.codex_tmp/native-backpressure-analysis/INTERRUPTION_PROOF.md`.

That continuation separately reproduced input backpressure at about 95 seconds.
Browser input remains 50 frames/s; average Gateway and AgentServer CPU do not
show saturation. The original Session with a fake socket sent 1000 frames in
0.0704 s, and a separate real-Provider 30-second silent probe sent all 1500 frames
with no sustained backlog. The latter's short protocol-close budget returned
`closing`, followed by normal exit of its owned process; it does not receive
complete protocol-close credit. Input hot-path files are unchanged from Task 1,
and the failure was investigated rather than dismissed as a baseline artifact.
That stage had no Task/artifact/terminal-audio acceptance credit.

Two bounded temporary observations then separated application lock time from
socket time. The first reproduced backpressure: 2,358 recorded append calls
spent 54.20 s in total, including 50.30 s inside the original socket send; sampled
queue reached 781/800, while sampled event-loop lag stayed below 24 ms. A second
115-second observation recorded 5,800 returned appends, every sampled input queue
at zero, and no backpressure. Neither observation is a business acceptance or a
proven network root cause. Details and limitations are retained in
`.codex_tmp/native-send-telemetry/REPORT.md`.

Main removed the temporary injection and restored the original candidate/runtime
environment (restart receipt `restart-3.json`). The next business attempt again
failed with `MEDIA_CONSUMER_FAILED` / `MEDIA_NATIVE_INPUT_BACKPRESSURE` before any
Task was admitted. The retained speech was split by Provider VAD, and the pending
response was retired on subsequent speech. The browser correctly surfaced a
connection failure; it did not fabricate Task completion or an artifact.
`%TEMP%/lv-unified-real-sorbyjl6/acceptance-business/` retains this separate failed
attempt. No production repair is claimed from the non-reproducing diagnostic.
The following investigation used an equivalent shorter spoken instruction and
bounded bidirectional transport observation, preserving all original failures.

The next observation captured both sides during the stall. Forty sampled slow
writes had `write_paused=true` with about 33 KiB pending, while every corresponding
receive queue was empty, unpaused and awaited normally by the original Session
reader. This establishes connection write-side transport backpressure for that
run, without identifying a network/Provider/TLS cause. It does not support a
speculative shared-service change. The exact trace and original-path comparison
are in `.codex_tmp/native-send-telemetry/RECEIVE_PATH_REVIEW.md`. Temporary
observation was removed again with `restart-5.json`; original runtime environment
and all four owned ports were verified, preserving the unrelated 5173 service.

That short spoken business request created one real Task and six successful
actual tool call/result pairs, including input reads and a file write. The Task
continued across media failure and reached authoritative `completed`; list,
status, events and result agree on its identity and artifact SHA256. However,
strict artifact validation failed: speech recognition changed the requested
field to `announce`, and the file included the input array on that line. The
untransmitted nonce and sum were present, but this is not the required two-line
format. Its exact terminal notification was observed without an accepted terminal
audio receipt. The original case remains PARTIAL; it is not replayed or relabelled
as passing. The subsequent explicitly corrective spoken Task used field-copy instructions;
its completed result and independent Work are recorded in the closure below.
The failed first file and identity evidence are preserved in
`.codex_tmp/final-shared-acceptance/task-proof.json`.

Core assembly and cumulative integration review are closed, including the
metadata ABA race and affected repair reviews. The user requires generic Core
Workflow integration with actual-SDK/startup evidence, with no named business
workflow installed by default. Those tests do not receive real-Provider credit.
The final real browser/Provider/Agent/tool continuation passed as recorded below. No remote ref
update is authorized or performed, and unrelated private workspace files remain
untouched.

## Final real continuation and exact credit

The corrective speech admitted Task
`task-ccaebd18a2b344b0af5ccfd5d550b4e1`, attempt
`attempt-1bb863cbb149474c9934d2500a7704fd`. It completed through the real configured
Agent/tools after another media failure. This was an explicit corrective request,
not a replay of an uncertain operation. Seven successful actual tool call/result
pairs include three reads and a write. The result has exactly two lines, the
original `nonce` and correct computed `total`; no expected value was supplied in
the new spoken request. Its SHA256 is
`ff849cbca669ebf153cdc5b5a81ca41c96bbf59cdcd54787384ea6b8f85dfd57`.
The first wrong-format artifact remains a failed case with its original hash and
contents retained in the independent proof; the correction does not erase it.

The final continuation read the already-admitted Task through the actual UI's
public list/status/events/result methods. It did not submit the file instruction
again. Exact Task/attempt/terminal source event, public result and actual file
hash agree. The completed-Task notification was played by the real browser and
acknowledged for its exact response generation and audio unit. Native uses the
media playout receipt; the test observer now checks that actual protocol as well
as P2. P2's initial sequence zero is valid. Wrong session, generation and unit
remain rejected by the helper checks. The older Task's separately recovered
300-block playback is retained in
`.codex_tmp/final-shared-acceptance/TERMINAL_RECOVERY_PROOF.md`.

Only after that completed-Task acknowledgement did the harness speak a new
independent read-only request. Work
`native-work-65c727396bc1bae02f735e8d8164f8f6` reached `completed` with
`execution_settled=true`, revision 1 / sequence 3, through the real configured
Agent. The input and corrected result hashes are unchanged after this Work.
The final owned browser exited normally and both private configuration hashes
were unchanged. The original runtime environment was used; temporary send
instrumentation was absent. The raw final result is **PASS** at
`%TEMP%/lv-unified-real-sorbyjl6/acceptance-existing-task-work/acceptance.json`.
Supporting runs include `acceptance-correction-final/`, original public wires,
actual browser PCM, server log `runtime-5-original.log` and the exact-input
`post-work-file-check.json` under `.codex_tmp/final-shared-acceptance/`.

This credit combines bounded continuations on the same source/session: ordinary
speech, actual interruption/recovery, real Agent/Task/tools/file effects, exact
public task queries and terminal playback, retained execution across media loss,
and independent settled read-only Work. It is not one uninterrupted successful
long connection. The reproduced connection write-side backpressure remains an
operational limitation, with no claimed transport repair or provider/network
reconfiguration. Human hearing, physical microphone/speaker and the historical
full device/product matrix remain outside this Goal's automatic acceptance.
Core Workflow has generic startup and actual-SDK/public execution evidence, not
a configured production business workflow or additional real-Provider claim.

## Final review and commit consolidation

Independent review approved `APPROVE_SCOPED_REAL_TASK_TERMINAL_PLAYBACK_AND_WORK`
after checking original speech/public admission, seven Task tool pairs, exact
artifact bytes, 291 nonzero terminal PCM chunks and both exact receipt protocols.
It also matched three actual Work tool pairs (`glob`, `list_files`, `read_file`),
three real formal model calls and original execution settlement. No new issue
was found within this bounded scope. Its complete positive/negative evidence and
limits are in `.codex_tmp/final-shared-acceptance/FINAL_REAL_REVIEW.md` and
`final-real-review.json`. The source check again passed; actual candidate imports
resolve to the candidate Host and retained `.deps/agent-core` SDK checkout.
All owned browsers, test consumers and diagnostic controllers have stopped. The
original four-port candidate remains available, with no temporary observation
injection; `final-runtime-receipt.json` records it. AgentCore has no upstream.

The two reviewed test-oracle corrections and their evidence belong to Task 2;
final verification, Task 3 record and current-status synchronization belong to
Task 3. They are folded into the existing numbered boundaries, retaining exactly
three local Host commits and a recovery checkpoint. The final delta from the
deployed `dc188fa0` candidate consists only of those tests and documents; Host
production/scripts/dependency bytes and SDK are identical. Therefore another
frontend build, runtime replacement, broad suite or identical real journey is
not needed for this consolidation. `.codex_tmp/final-shared-acceptance/final-commits.json`
records the resulting hashes and production-equivalence check. Scoped diff and
local documentation-link checks passed. No remote refs were updated. Tracked
changes are fully committed; unrelated private/untracked files are preserved.
