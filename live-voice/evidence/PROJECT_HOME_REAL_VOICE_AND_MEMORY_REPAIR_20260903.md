# Project-home real voice and background memory lifecycle repair — 2026-09-03

## Scope recorded before implementation

Baseline: `69c82b656f5a56ea8e993d31355520f31ac78a0a`, initially clean.
The selected README route is the current production execution packet.

Intended behavior: the dedicated background project Code adapter must honor its
existing no-conversation-memory execution contract: detach CodingMemoryRail
before execution and never rebuild it during mode updates or configuration
rebuilds. Ordinary Code retains coding memory; project instruction loading stays
intact. Only the dedicated child's rail lifecycle and its existing adapter tests
are owned by this repair.

Tier 2 under root TESTING: state/teardown-sensitive adapter work. Applicable
P/N/B/S/T/C/R/I/F/K/X evidence covers fresh preparation, missing rails,
idempotent teardown, failed preparation/cleanup, concurrent reservation ownership,
ordinary-mode compatibility and the real core rail teardown seam. No protocol,
persisted format, Task command, replay or deadline change; those matrix aspects
are out of scope. Independent review availability must be recorded honestly.

Exclusions: no provider/account/configuration change, no new file permission
policy or sandbox, no semantic classifier, no arithmetic fixture, no changes to
sealed Task A, no Native/cumulative/full-Demo acceptance credit. Removing an
automatic memory rail does not establish filesystem confinement. Broader file
tool access outside the checkout remains a separately scoped authority/security
question.

## Verification record

### Baseline real browser/microphone journey

On baseline `69c82b656f5a56ea8e993d31355520f31ac78a0a`, Git was clean and
`HEAD...@{upstream}` was `0 0`. The actual configured upstream was
`agtai/hx/0812_live_voice_w3`; no fetch or remote update was performed. The old
private runtime named in earlier evidence was absent on this machine. The saved
authorized formal-Web project/runtime was used instead, with no provider/config
edits. It had 29 terminal Tasks and zero live Tasks before restart.

The current frontend was rebuilt with TypeScript/Vite checks and served as
`index-DeCxWld2.js` on port 6175; backend ports were 18092/19000/19001. The formal
launcher speech/receipt and identity/forged-claim probes passed with zero business
effects. These are startup checks, not whole-Demo acceptance.

Project-home Live Voice created one empty Session
`web_1a0687b7148_5382eb4680c4` in `proj_2b0bce69`. The browser reached
“正在听你说话”; media first-frame acceptance/ACK appeared at 20:15:33 CEST.
No synthetic microphone or transcript injection was used. Observed committed
transcripts and replies:

- 20:15:39: `你好`; reply at 20:15:43. UI duration 3.94 s.
- 20:16:14: `23点20分再过八十五分钟是几点?`; reply at 20:16:17 correctly
  said next-day 00:45. UI duration 3.29 s. Task count stayed 29, zero live Tasks.
- 20:17:16: `创建后台任务A,把刚才的时间计算加650加240加100的总和写入合算.md,左右书名号都是文件名的一部分,只写本地文件。`
  One Task was created without another confirmation, with a truthful queued
  receipt at 20:17:22 and later running/terminal Registry projection.

The analysis transcript did not contain the suggested explicit no-create prefix;
it proves this question created no Task, not every no-create formulation. The
delegation transcript said **加** and **合算**, whereas the suggested scenario
intended **和** and **核算**. Do not silently normalize those differences.

Task A: `task-232ae2aedcaf4400af602fe59aca2795`; attempt
`attempt-a95527d068db42018bef35f63c8a019b`. Authoritative state/outcome was
`terminal/completed`, event head 5. Creation 18:17:19.897118Z, running
18:17:20.685058Z, completion 18:19:35.754313Z. The actual sealed local file was
`《合算.md》`, with both literal book-title brackets, content `2475\n`, SHA-256
`b9c3fff6fbc2fc7172e2fae35bb70f4874d5634afa8dd6725d7156de4a278837`.
The file hash matched the stored artifact. It converted the clock time to 1485
minutes and added 990; this did not satisfy the intended two-independent-results
scenario. Given the actual ambiguous transcript, it is not isolated proof of an
addition error. Execution `completed` does not grant business PASS.

A cancellation through the authenticated production intent route arrived after
completion and was rejected `TERMINAL_TASK_IMMUTABLE`; A was not cancelled or
rewritten. The terminal notification/result became visible around 20:19:51.
Browser playback state and presentation-ACK evidence were observed, but the
human's actual heard output was not independently confirmed.

There were recognition-stream provider/protocol errors around 20:15:43 and
20:16:06 followed by later successful transcription. One successful listening
journey does not close capture/recovery stability. These UI timings are individual
observations, not a latency distribution or first-audible measurement.

### Defect and bounded implementation

Runtime log `swarm-20260903-201259.log` showed repeated missing CodingMemoryRail
reads outside the attempt checkout; list operations also reached the application
data directory and its `live_voice/p3alpha` directory. Initial relative file-tool
paths correctly resolved to the attempt checkout. No outside-project write was
established. Automatic memory reads and general file-tool directory access must
not be conflated into a proven single cause.

The dedicated adapter now unregisters CodingMemoryRail alongside the already
disabled LSP/subagent rails, skips rebuilding it on repeated mode updates, and
rejects memory construction on dedicated configuration rebuilds. The existing
project-instruction rail remains present. No calculation answer, task name,
filename or domain keyword was added to production decisions.

### Focused verification and review

Command (23 passed, 65 deselected, one existing Authlib deprecation warning):

```text
.venv/Scripts/python.exe -X utf8 -m pytest tests/unit_tests/agentserver/test_agentserver_modes.py tests/unit_tests/agentserver/test_code_adapter_acp_chat_tool.py tests/unit_tests/agentserver/memory/test_code_adapter_coding_memory.py -q --tb=short --show-capture=no -o log_cli=false -k "background or ordinary_code or late_prepare or cancelled_prepare or coding_memory or configure_code_team"
```

This covers preparation isolation/concurrency, late and cancelled cleanup,
ordinary memory construction, duplicate mode updates and dedicated builder
fencing. The added real DeepAgent/CodingMemoryRail test verifies removal of the
registered rail, owned memory tools and memory prompt, with no memory directory,
initialization task or prefetch task created. Project instructions remain owned
by their existing rail. The first test attempt used a misspelled core inspection
method; that test-only error was corrected before the passing run. Default pytest
coverage generated repository-wide reports, but only the selected tests ran.

The Python-only repair was loaded by restarting the same owned formal runtime
with `debug --skip-build`, after checking zero live Tasks. Existing frontend and
private process configuration were reused. `.env` and `config.yaml` hashes
remained identical to the pre-restart baseline. No remote refs changed.
Runtime log: `swarm-20260903-202936.log`. Tested product-file SHA-256:
`8a763fa81ca8b1831e8099ff6e3e7639047563fc2f9adba7ba01239d2e9dec7a`.

### One real executor follow-up (structured API, not speech)

After restart, the existing Session again reached the browser listening state.
No new spoken final arrived; capture was exited. The visible normal Code editor
is not the Live Voice unified-text entry, and hidden legacy forms were not used.
One authenticated `live_voice.composition.p3.intent` structured create and its
required confirmation exercised the production Task/Executor boundary. No speech
receipt, semantic model result or committed voice origin was manufactured.

Instruction: `把两项独立计算分别写进本地文件复核.md：第一项，23点20分经过85分钟后的时刻；第二项，650加240加100的总和。两项不要相加，只写本地文件。`

Task `task-50af46608b884c7da59796a7f1edee3c`, attempt
`attempt-095042a6e52843ee8fae3ace05996eb5`: both `terminal/completed`.
Created 18:33:42.488037Z; completed 18:34:09.174073Z, about 26.7 seconds.
This differs from the earlier speech instruction/provenance and is not a causal
latency comparison, a stable result-quality claim or A/B/A2 acceptance.

The actual project file `复核.md` contains separate next-day 00:45 and 990
results. Its SHA-256 matches the sealed result artifact:
`0e0f3ea8f45f708880b9ca1a4c076ca28e4324ffdb97d83194862078ffb1f958`.
Old `《合算.md》` retained its prior hash. The Task store ended with 31 Tasks,
zero live; browser Registry refresh showed exactly the two completed Tasks in
this Session and preserved the selected old result until the new Task was chosen.
This single list refresh does not prove offline unread/ACK or refresh replay.

The new log records CodingMemoryRail unregistration before execution. All nine
observed filesystem operation starts belonged to this attempt checkout; none
targeted coding memory or a path outside it. No claim of general filesystem
confinement follows from this positive sample. The model's result text still
names an absolute temporary checkout path which cleanup removed; the sealed file
exists in the registered project. User-facing result-location fidelity therefore
remains open alongside broader arithmetic/feasibility and speech ambiguity.

The full scoped source/test diff was cold-reviewed; no new business hardcode,
Task mutation semantics, shared protocol or configuration changes were found.
Changed Python AST checks passed. No independent review tool is exposed in this
session; self-review cannot satisfy that gate. The module/candidate remains
PARTIAL pending independent review and wider required evidence. Full A/B/A2,
offline/ACK/refresh, Native, cumulative regressions and human acceptance were not
run or inferred. Raw logs, request identities and file-operation evidence remain
in the machine-private rehearsal directory, outside Git.
