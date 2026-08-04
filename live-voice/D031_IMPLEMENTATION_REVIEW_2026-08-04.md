# D-031 minimal task monitor implementation review

> Review period: 2026-08-04 through 2026-08-05
>
> Candidate base: `ad02fa6ff5f81d5726b484ab3a33ba93651affc8`
>
> Final local implementation commit: `617fe256db05b07a07b6d457b15f07c02d17d9bf` (`d031-05` real-service evidence below ran against its pre-amend candidate `d84fd388`)
>
> Acceptance state: `PARTIAL`; monitor and fail-closed behavior are verified, but a successful project-bound AutoHarness delivery is not
>
> Risk tier: D-046 Tier 2

Current progress and next actions remain authoritative only in [STATUS.md](STATUS.md). This record owns the D-031 implementation boundary, scenario evidence, review findings, automated verification, and remaining real-service gap for this candidate.

## Implemented boundary

- One page-memory current task is monitored through `schedule.status`; a replace keeps only its direct predecessor ID and current successor record.
- A disconnect aborts and fences the current read. Reconnection waits for that read to settle, then uses only the original session, project, namespace, and command ID with `schedule.list` before status polling resumes.
- Status adoption requires the exact task, command, target, owner scope, authorized non-legacy provenance, and a non-empty backend status. Malformed, foreign, missing, unavailable, or business-error responses preserve the last trusted task and stop as the applicable visible state.
- The monitor can call only `status` and exact-key `listByCommand`. It has no Chat callbacks and cannot run, cancel, send, interrupt, write messages, change processing state, create TaskEvents, scan tasks, or recover across page/process boundaries.
- Valid observations update the existing `LiveVoiceTaskBridge` before task-card projection. A Bridge rejection stops the monitor, preventing UI-only truth.
- Terminal notification remains outside Chat history, is available at most once, and is attempted only while Live Voice is active, capture is closed, Agent work and speech are idle, and Live Voice still owns TTS output. Otherwise the terminal card remains visible without later surprise speech.
- The existing task feature flag remains the only opt-in switch. Flag-off keeps task commands on the prior Chat path and creates no monitor.
- The exact Chinese command grammar uses “后台代码优化任务” as its primary spoken name, retains “后台演进任务” as a compatibility alias, and accepts explicit spoken target markers without treating ordinary code-optimization discussion as a task command.

## Timing and visible states

- A connected accepted task reads status immediately.
- Queued tasks use 1 second; running tasks use 2 seconds for the first 30 seconds and 5 seconds afterward; unknown non-terminal states use 5 seconds.
- Explicitly retriable reads use 1, 2, 5, then 10 seconds capped. A successful read resets the retry count.
- Visible monitor states are polling, paused-disconnected, reconciling, backoff, terminal, missing, adapter-error, and stopped. The card preserves backend raw status, optional progress summary, optional last error, target, and source.

## Scenario evidence

| Dimension | Automated evidence | Remaining gap |
|---|---|---|
| Positive/state | immediate read, queued/running/unknown cadence, valid terminal, Bridge synchronization, visible projection, and one real task observed through terminal | a real task has not yet produced a correct requested target change |
| Negative/boundary | invalid envelope, task/status/target/provenance mismatch, malformed optional facts, business error, missing, unavailable, and Bridge rejection stop without adoption | real server error envelopes not yet observed through WebSocket |
| Timing/concurrency | fake clock covers cadence/backoff; deferred reads cover one in-flight read, abort, no reconnect overlap, and late-result fencing | real disconnect timing and browser reconnect not yet observed |
| Recovery/isolation | exact-key same-page list accepts one exact record; empty/multiple records stop; stop and error states do not revive | full refresh/restart remains explicitly unsupported |
| Compatibility | primary and legacy command names, spoken target markers, task flag-off routing, Bridge/client/adapter suites, default-off build, and task-flag-on build pass | corrected primary command still needs a manual task flag-on microphone/speaker rerun |
| Forbidden effects | monitor gateway exposes only status/list; test gateways omit mutation methods; hook monitor callbacks do not receive Chat send/interrupt/store setters | browser-level store spies remain a real-path validation gap |

## ASR command correction

The first manual attempt did not enter the task route: one transcript changed “演进” to another word, and the replacement phrase “后台代码优化任务” was not yet recognized. Both attempts went to the ordinary Agent path; the second created disposable-worktree code while producing no `schedule.run`, real `sch_*` ID, or D-031 monitor. It is not counted as D-031 validation evidence.

The correction adds the complete exact “后台代码优化任务” create, status, replace, and cancel grammar; retains the old name; and accepts “任务内容是/为” and “目标是/为” with optional punctuation. Unconfirmed primary commands produce zero task gateway calls, confirmed commands reuse the existing fixed pipeline and controls, and ordinary mentions such as “请分析代码优化方案” remain Chat input. The correction's repeat reviews are complete; real-service validation must restart with a candidate containing the corrected primary command.

## Review passes

### Pass 1 — implementation self-review

- A stopped `missing` or `adapter-error` state could originally be converted to disconnected and then resume on reconnect. These phases now ignore connection transitions and remain stopped.
- A task command could finish after connection state changed and start a monitor using the callback's old render value. Monitor startup now reads the current connection ref.
- Optional facts are strict: a present non-object progress or present non-string last error is rejected rather than silently converted.
- Task progress/error fields are rendered only for monitor projections, avoiding unrelated changes to existing one-shot task feedback.

### Pass 2 — cold complete-diff review

The review ignored implementation rationale and compared the original request, repository rules, existing behavior and APIs, the complete code/test/documentation diff, and the actual results.

- A replace command initially retained the predecessor ID but the first monitor projection relabeled B as a generic current record and removed the explicit successor field. Monitor projection now keeps A as predecessor, B as successor, and marks B's record role as successor.
- Error and missing phases remain stopped across later connection changes, deferred pre-disconnect results cannot update Bridge/UI, and exact-list reconciliation cannot select among multiple records.
- The new monitor has no mutation or Chat API, and a status or confirmed cancel/replace command fences the old monitor before existing Bridge control begins.
- The initial cold review found no additional actionable defect after the relationship correction. The required later complete-diff repeat is recorded after Pass 3 because it reviewed the independent-review fix as well.

### Pass 3 — independent review

The independent entry used `codex review --uncommitted` through the verified private Codex executable because the bare command still resolved through the protected WindowsApps path. It completed independently from the implementation conversation and reported two findings.

- The suggestion to stop after four retries was not accepted. D-031 specifies 1, 2, 5, then 10-second delays capped at 10 seconds, not a maximum of four attempts. Stopping permanently after about 18 seconds would make a transient outage unrecoverable; the monitor test proves recovery after more than four failures without changing task identity.
- The report correctly found that reconnect reconciliation could mislabel an unavailable task store as a missing task because backend `schedule.list` returned an empty list for both cases. The service now returns stable `TASK_STORE_UNAVAILABLE`, the WebSocket response preserves that envelope, and the monitor presents `adapter-error` rather than `missing`. Service, WebSocket, and monitor regressions cover the distinction.

The accepted fix changed response semantics, so the complete diff received another cold review. That repeat found three additional concrete boundary defects:

- unconfirmed cancel/replace speech stopped the active monitor before the Bridge rejected the unconfirmed control;
- a session, target, request, or Bridge change could occur during the render-to-effect window and allow an old callback to reach the prior Bridge/UI;
- provenance accepted any string `app_id`, and matching forged target/provenance channel values were not also bound to the current Web owner.

Monitor fencing now applies only to status and confirmed controls. Every monitor observation/snapshot callback rechecks the current session, target, request, Bridge, and monitor identities before it can update state. The gateway captures exact Web channel and app facts, and strict parsing rejects mismatches. Regression tests cover the control boundary plus foreign app/channel facts. After those fixes, affected tests and both production builds passed, and the final complete-diff review found no further actionable defect within the approved D-031 boundary.

### ASR command correction repeat

- Self-review found that punctuation followed by a spoken marker could leave the marker inside the task query. The parser now normalizes punctuation, “冒号”, “任务内容是/为”, and “目标是/为” combinations while keeping ordinary code-optimization discussion outside the task route.
- One custom cold-review command timed out without output and is not counted. A completed independent `codex review --uncommitted` then found that the client expected an empty Web app ID while the server defaults to `default`, and that a failed explicit control could leave the prior monitor stopped. Both defects were fixed with focused regressions.
- A complete-diff repeat found that terminal task speech could reopen capture, terminal announcement ignored a blocked interaction, the inactive task card omitted the safety disclosure, and the recorded adapter count was stale. The fixes keep terminal speech from owning microphone resume, require an unblocked safe gap, preserve the disclosure, and correct the evidence.
- The final independent complete-diff review found that restarting monitoring for the same successor task discarded its direct predecessor. The restart now preserves that relationship only for the same task, does not copy it to a different task, and lets an explicit new relationship win. The new regression brings the adapter suite to `19 passed`.
- At the user's request, no additional automated `/review` was started after that final fix. A manual final cold check of the complete diff, repository rules, existing APIs, actual test results, and the narrow post-review change found no further actionable defect. The remaining validation gap is the corrected real-service browser run.

## First corrected real-service attempt

- The saved-session unconfirmed primary command was recognized and requested confirmation with zero `schedule.run`, zero new task ID, and zero target changes. The earlier unsaved-session attempt also failed closed as designed.
- Two later confirmed captures were sent from different Sessions with different command IDs and different recognized queries, creating `sch_aeb200c2` and `sch_13932555`. This was not a duplicate dispatch of one capture. Both tasks targeted the same disposable `d031-02` worktree, so the backend was stopped and that target is retained only as evidence.
- The first `schedule.status` for `sch_13932555` matched task, command, namespace, project, Session, channel, and authorization facts but returned the real server-derived Web `owner_scope.app_id` as `""`. The frontend had been changed to expect `"default"`, so it correctly failed closed with `task-scope-mismatch` but could not monitor the valid task.
- The client now expects the server's actual empty Web app scope. Session and channel remain required and exact, the app value remains an exact comparison, and a foreign non-empty app still fails closed. Existing AgentServer tests independently prove that an absent Web app ID is derived as empty rather than `default`.
- Client `17`, monitor `21`, Bridge `47`, adapter `19`, and backend schedule/WebSocket `107` tests pass after the correction; default-off and task-flag-on production builds also pass. Per the user's direction, no further automated `/review` was started; implementation self-review and a manual cold diff review found no additional actionable defect in this narrow correction. A clean `d031-03` real-service rerun remains required.

## Clean d031-03 real-service attempt and runtime hardening

- One confirmed primary command produced exactly one `schedule.run`, task `sch_aa13f695`, command `lv-ed306d3b-43b5-42d3-a552-1f6b981b5209`, and execution `exec_b2cc2014` for the saved Web Session and disposable `d031-03` target. Status polling accepted the exact task, target, command, Session, channel, project, and empty Web app scope. The prior `task-scope-mismatch` defect did not recur.
- The task started at `21:15:01` local time and reached assess, plan, and build/verify work. It failed at `21:34:59`, after about 20 minutes, when one append open for its 4.2 MB `log.json` raised Windows `PermissionError`. The task store truth was `failed`; no cancellation was required. The prior progress summary remained `2/4` because the run never produced a successful terminal pipeline event.
- A post-run hash comparison found zero changes among all 2,665 baseline files that the pre-run manifest had hashed. The manifest generator had recorded 140 Chinese-name image paths as `MISSING` because of its own PowerShell encoding error, so those entries are not claimed as hash evidence; Git status remained at the copied candidate baseline and no task-generated path appeared.
- The append path now retries only transient `PermissionError` failures while opening the log, with a bounded total delay below one second. It does not retry a write after the stream opens, avoiding duplicate event lines. Exhausted failures still terminate truthfully.
- Reverse progress reads now use binary chunks, so a 4,096-byte boundary cannot begin in the middle of a UTF-8 character. An incomplete trailing UTF-8 event is ignored without discarding earlier complete stage facts. The repaired reader successfully extracted key events from the real 4.2 MB log without the former decode warning.
- One-time execution failures now persist the actual exception text as `last_error`, allowing a valid failed status response and task card to show the backend reason rather than `unknown`. A frontend regression proves a `failed` observation with stale `2/4` progress becomes terminal, preserves the real failure text, and schedules no further polls.
- This hardening received implementation self-review and a small cold review of the changed runtime, monitor regression, tests, and evidence record. Per the user's instruction, no `/review` was invoked. A restarted clean `d031-04` run is still required to prove successful terminal status and at-most-once terminal speech.

## Clean d031-04 zero-effect outcome and result validation

- One confirmed primary command produced exactly one scoped task, `sch_20b6ac69`, command `lv-dde750f4-cd61-409e-a28c-345ff7849ba4`, and execution `exec_d2cba54c` for the disposable `d031-04` target. The first transient status timeout entered read-only backoff and then recovered without creating, cancelling, or replacing a task. Monitoring continued to the terminal state.
- The execution ran from `22:17:48` to `22:41:57` local time. The `d031-03` Windows log-open and UTF-8 reverse-read failures did not recur. AutoHarness emitted a terminal `harness.session_finished` with `status=success` and the scheduler persisted `success`.
- The requested package and tests were not delivered. A complete manifest comparison found 2,805 files before and after with zero hash differences. Therefore the pipeline completed technically but the business request had no effect; this run is not accepted as a successful task outcome.
- New one-time tasks in the `live_voice` namespace now carry `target_tree_change_required`. The scheduler snapshots Git-visible tracked and untracked target files before and after execution. A pipeline result can remain successful only when that target fingerprint changes; an unchanged target becomes `failed` with `NO_EFFECTIVE_TARGET_CHANGE`, and an unreadable or invalid target fails closed. Git-ignored caches and `.git` metadata do not satisfy the result requirement.
- The result requirement detects a zero-effect run; it does not prove that changed code is correct, relevant, tested, or safe. Those remain AutoHarness and review responsibilities. Other namespaces and recurring tasks retain their existing completion behavior.
- The shorter verification uses an isolated temporary Git target and a bounded fake execution. A missing target, no change, and ignored-cache-only change all end `failed`; a new Git-visible source file ends `success`. This validates the result gate without another 20-minute model run.

### Result-gate review repeat

- Implementation self-review found that an initial all-files fingerprint would allow `.pytest_cache`, build output, or other ignored runtime artifacts to satisfy the result requirement. The fingerprint now uses only Git tracked and non-ignored untracked paths, and the ignored-cache regression must fail.
- The cold focused diff review checked the original zero-effect failure, namespace isolation, invalid target handling, terminal error persistence, idempotent task storage, cancellation behavior, and the complete changed diff. It added the explicit invalid-target/no-Agent-start regression and the assertion that ordinary internal tasks do not receive the Live Voice result requirement.
- No further actionable defect was found after those corrections. Per the user's instruction, no `/review` was invoked; the actual substitute was implementation self-review plus a cold focused complete-diff review, so this is not represented as an independent review pass.

## Clean d031-05 target-binding failure

The `d031-05` run used committed candidate `d84fd388`, a fresh JiuwenSwarm data directory, disposable target `D:\XGG AI\openjiuwen\jiuwenswarm-target-20260804-d031-05`, project `proj_152cbe9f`, and a saved Web Session. The target began at `d84fd388` with a clean Git status.

### Negative confirmation and exact dispatch evidence

- The unconfirmed primary command requested confirmation and produced zero `schedule.run`, zero `schedule.status`, zero `schedule.cancel`, zero task IDs, and zero target changes.
- The confirmed capture produced exactly one `schedule.run` at `2026-08-04T21:44:16.346Z`, command `lv-87a1a719-a40d-4665-8c83-e1751d209830`, task `sch_5ce6c7a6`, and execution `exec_627fcdb4`.
- The monitor issued `233` `schedule.status` requests, all for `sch_5ce6c7a6`. It adopted the final failed status at `2026-08-04T22:04:00.399Z` and issued no later status request.
- The final stored error was `NO_EFFECTIVE_TARGET_CHANGE: target project has no file changes`. No cancellation or duplicate run was sent.

### ASR comparison

The exact query carried by `schedule.run` was:

```text
在仓库跟目录新建一个文本文件文件名由你决定内容只能有一行任务验证成功不要修改其他文件不要运行测试不要提交测试不要推送
```

Compared with the spoken intent, ASR changed “根目录” to “跟目录”, removed punctuation and quotation marks, and joined “不要提交，不要推送” into “不要提交测试不要推送”. These deviations were not the causal failure. The assess stage explicitly reconstructed “根目录新建单行文本文件”, “内容仅一行”, and “不修改其他文件、不跑测试、不提交、不推送”. The parser and task route therefore preserved enough intent for the executor to understand the request.

### Actual execution path and root cause

- The `schedule.run` request contained the frozen project target but no `repo_url`.
- `AutoHarnessService.run()` does not use `execution_target.project_dir` as its repository. With no request `repo_url`, it selected the configured `https://gitcode.com/openJiuwen/agent-core.git`, prepared `...\auto-harness\repo\openJiuwen--agent-core`, and pinned the AutoHarness workspace to that checkout.
- `extended_evolve_pipeline` is an extension design/build/verify/activate pipeline. It converted the understood single-file request into five duplicate `runtime_extension` designs, implemented and tested one extension in `...\auto-harness\worktrees\1785880235-extension-runtime-extension`, ran six extension tests despite the user asking not to run tests, and promoted the artifact under `...\auto-harness\runtime_extensions\34ee54c76745\runtime_extension`.
- None of that work occurred in the selected `d031-05` project. The target remained at `d84fd388` with clean Git status, so the new target-tree result contract correctly changed the pipeline's internal success to task failure.

This is a mixed-contract defect, not an ASR defect: the selected project is used for owner/target authorization and final result validation, while execution still uses a separately configured Agent Core repository and an extension-only artifact model.

### Audit-manifest limitation

The manually captured `worktree-before.tsv` is not valid hash evidence. Its PowerShell Git pipeline recorded `2,665` rows and silently omitted `140` non-ASCII paths. A later UTF-8-safe enumeration found the real `2,805` files, so direct `Compare-Object` against that TSV falsely reports 140 additions. Do not reuse this file or its count. The zero-change conclusion instead rests on the scheduler's own Git-visible pre/post fingerprint, the stored `NO_EFFECTIVE_TARGET_CHANGE` result, unchanged `d84fd388`, and clean target Git status. A future manual manifest must use an explicitly UTF-8-safe implementation and prove its baseline count before task start.

## Required next slice before another real run

Do not repeat a positive real-service task until the execution/result contract is made coherent. A new Session must first choose and record one of these product meanings:

1. **Project-bound code task — recommended for the current “后台代码优化任务” wording.** The selected project is the actual execution repository, and success means the requested Git-visible project change exists. This requires a project-capable Executor/Harness Adapter; merely passing the path into `extended_evolve_pipeline` is insufficient because that pipeline creates and promotes runtime extensions in its own worktrees.
2. **Runtime-extension Demo.** The command is restricted and renamed to an explicit Harness extension operation, the runtime extension store is the declared artifact target, and success validates the promoted extension rather than the selected code project. This does not satisfy a generic project code-optimization promise and must remain visibly a Demo substitute.

The current mixed behavior—execute against Agent Core/runtime-extension storage while validating a different selected project—is forbidden.

### Minimum fail-closed correction, independent of the choice

- Resolve and persist one `effective_execution_root` and artifact contract before scheduling model work.
- Reject before Agent/model/clone/extension side effects when the selected target, effective execution root, pipeline capability, and result contract do not agree. Use a stable explicit error such as `EXECUTION_TARGET_NOT_BOUND`; do not wait about 20 minutes to discover the mismatch at finalization.
- Return the effective execution root and artifact kind as trusted backend provenance so status/UI diagnostics can show what will actually be modified. Frontend text must not infer this from the selected project.
- Reject unsupported constraints before execution. A fixed pipeline must not silently run tests, create extension scaffolds, commit, or publish when the accepted request forbids those operations.
- Keep this work out of the monitor state machine. D-031 polling remains a thin Compatibility Adapter; project execution authority belongs in the P3alpha Executor/Harness Adapter route rather than expanding TaskBridge or `schedule.*` into another Task Core.

Likely investigation points are `liveVoiceTaskBridge.ts` for the fixed pipeline/disclosure, schedule request persistence in `agent_ws_server.py` and `service.py`, scheduler request construction in `scheduler.py`, and `AutoHarnessService.run()` repository selection/configuration. Do not implement a one-field `repo_url` patch until the project-bound versus runtime-extension contract is chosen.

### Required automated evidence

- Mismatched selected target/effective execution root fails before model creation, repository clone/update, runtime-extension creation, task mutation beyond the failed record, or target writes.
- A supported project-bound fake writes one expected Git-visible target file and succeeds; no change, ignored-cache-only change, foreign-root change, unreadable target, or invalid Git target fails.
- The task record, status response, monitor projection, and result validation all carry the same target, effective execution root, artifact kind, command, task, owner, Session, and channel facts.
- Unsupported “no tests/no commit/no push” constraints reject before execution unless the chosen executor can prove those effects remain zero.
- Existing idempotency, wrong-scope, reconnect, retry, terminal-stop, flag-off, cancel/replace, and text-path regressions remain green. Any state/concurrency/mutation change follows the applicable D-053 review passes.

### Required real-service evidence

- Use a fresh isolated data directory and disposable clean Git target with a UTF-8-safe baseline.
- Unconfirmed speech produces zero task requests and zero side effects.
- One confirmed committed-final capture produces exactly one `schedule.run`, one real task ID, and status reads only for that ID.
- Backend provenance proves the effective execution root equals the selected target before model work starts.
- The requested artifact appears only in the target, unexpected files remain zero, HEAD remains unchanged when commit/push are forbidden, and semantic content is checked rather than inferred from task status.
- The backend reaches truthful `success/success`; the monitor stops after terminal adoption and terminal speech is observed at most once. A changed but wrong artifact, runtime-data-only artifact, or zero target change is a failed run.

## Automated verification

- Frontend monitor: `22 passed`.
- Existing/extended task suites: Bridge `47 passed`, client `17 passed`, adapter `19 passed`.
- Adjacent lifecycle suites: core `9 passed`, turn lifecycle `16 passed`, TTS ownership `2 passed`.
- Backend schedule service and WebSocket handlers: `115 passed`.
- The repaired fingerprint read the preserved 2,805-file `d031-04` target twice with the same digest; each read took about 1.8 seconds and made no target change.
- TypeScript/Vite production build: default task flag and `VITE_FEATURE_LIVE_VOICE_TASK_DEMO=true` both passed.
- New monitor source/test Prettier check, changed-document relative links, and `git diff --check` passed.
- Targeted Ruff passes for the runtime log fix files and their backend tests. Targeted Ruff still reports pre-existing findings at `service.py:461` and `agent_ws_server.py:190`; whole-file Prettier also retains existing touched-file baseline warnings. Targeted ESLint cannot start because this frontend has no discoverable ESLint configuration. None is represented as a D-031 pass.

## Exclusions

- No formal Task Core/Event Store/Harness Adapter, TaskEvent push/replay, durable journal, multi-task monitor, cross-page/process recovery, or production authorization.
- No natural-language task result is invented; terminal speech states only task ID and raw backend status.
- No Week 2 replacement credit or semantically correct project-bound AutoHarness delivery is claimed by this record. Final local commit `617fe256` is implementation evidence, not D-031 acceptance closure or push evidence.
