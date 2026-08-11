# D-031 project-bound real-service evidence: 2026-08-05

## Conclusion

- Acceptance: `CLOSED` for the D-031 single-task Compatibility Adapter boundary accepted in D-057.
- Source identity: branch `hx/0803_live_voice`, base HEAD `56b45480d8ef05199a00cbcb100d499557871035`, project-bound correction still uncommitted at validation time.
- Result: one logical confirmed command produced one durable task and one execution in the selected project, made the requested semantic README change, preserved target HEAD, reached truthful `success/success`, and stopped polling after terminal adoption.
- Scope warning: this is not commit/push evidence, formal Task Core/Event Store/Executor evidence, guaranteed terminal-audio evidence, or an assertion that the target contained no Agent Runtime support paths.

Raw browser frames, service logs, task JSON and execution logs remain in the retained local validation directories. This file contains no Provider key, API base, browser profile or user credential.

## Environment and identities

| Item | Sanitized fact |
|---|---|
| OS / carrier | Windows / JiuwenSwarm desktop Web frontend in Chrome |
| model | `deepseek-v4-pro` |
| isolated data directory | basename `d031-data-clean-20260805-143547` |
| disposable target | basename `d031-target-clean-20260805-143547` |
| target baseline/after HEAD | `dca9f142ccf73efd5f92a3b6e2b22c6cf6f44a9d` / unchanged |
| project | `proj_561839da` |
| source Session / channel | `sess_19fd20876ea_16d966285357` / `web` |
| command / task / execution | `lv-3635c613-d033-4834-bb41-e275c171ca91` / `sch_592b8579` / `exec_4a99d01d` |

The frontend and backend services were stopped after capture. Ports `8000`, `5173` and `5174` were not listening during the closure check. The isolated data and disposable target directories were retained as local evidence rather than deleted.

## Committed input and execution contract

The final ASR text accepted by the task parser was:

```text
确认启动后台代码优化任务目标是修改项目根目录中的说明文件在末尾新增一行验证通过不要修改其他文件
```

The durable task query was:

```text
修改项目根目录中的说明文件在末尾新增一行验证通过不要修改其他文件
```

The task record persisted one coherent backend-owned contract:

```text
effective_execution_root = selected disposable target
artifact_kind            = git_visible_project_change
executor                 = jiuwenswarm_code_agent
pipeline                 = project_code_pipeline
git_commit               = forbidden
git_push                 = forbidden
tests                    = forbidden
shell                    = forbidden
result_contract          = target_tree_change_required
```

The selected persisted project directory, Code Agent root, effective execution root and Git top-level were the same target.

## Logical idempotency and monitoring

- The first `schedule.run` was sent at about `15:11:37` local time and exceeded the frontend's 15-second wait.
- At about `15:11:52`, the frontend performed exact-key `schedule.list` reconciliation and retried `schedule.run` with the same command/idempotency key.
- The wire therefore contains two `schedule.run` requests. The store contains one create-command row, task `sch_592b8579`, and one execution `exec_4a99d01d`; there was no duplicate task or model execution.
- The task began at `13:12:00.804710+00:00` and completed at `13:12:37.602947+00:00`. Both the stored task and execution status are `success` with no stored error.
- Status reads remained bound to `sch_592b8579`. The browser performed its final terminal read at about `15:12:42` local time, then made no later status request before shutdown.

D-057 defines this as one logical mutation with idempotent recovery. The evidence does not claim exactly one wire request or cross-process exactly-once semantics.

## Semantic result

The Code Agent read and edited the selected target's `README.md`. The post-run Git diff is:

```diff
 # D031 clean verification project
+
+验证通过
```

The target HEAD remained unchanged. The task did not commit or push. The model execution log contains file read/edit operations and no shell/test/Git/remote command execution. The requested semantic result therefore passed independently of the scheduler's terminal status.

## Audio observation

- Startup task information, including task/command identity, was spoken.
- Terminal completion speech count was `0`.
- The implemented contract is safe **at most once**: terminal speech is attempted only in an immediately safe gap and is not queued for later surprise playback. Zero terminal announcements therefore passes this contract; it does not prove guaranteed or eventual notification delivery.

## Explicit limitations and ownership

The target was not absolutely clean after the run. In addition to the requested `README.md` change, inspection found:

```text
.gitignore
coding_memory/d031-target-clean-20260805-143547/memory.db
coding_memory/d031-target-clean-20260805-143547/memory.db-shm
coding_memory/d031-target-clean-20260805-143547/memory.db-wal
prompt_attachment/README.md
.agent_history/...
```

The support directories were visible to the Code Agent before its requested README edit and are associated with shared Agent/runtime setup. The user explicitly assigned their placement to an Agent Runtime/workspace-isolation follow-up rather than the D-031 monitor/project-binding defect. This record therefore claims zero D-031-forbidden shell/test/Git/remote effects and no duplicate task; it does **not** claim zero unrequested filesystem paths.

An earlier run whose committed ASR query referred to `radi.nd` correctly created `radi.nd`; it is excluded from this positive sample because the executor followed the committed text. That transcript is retained as a Speech/ASR fidelity follow-up, not rewritten as D-031 success or failure.

## Acceptance matrix

| Dimension | Result | Evidence/limit |
|---|---|---|
| exact selected-project binding | `PASS` | persisted project/effective root/Git root agree |
| semantic requested artifact | `PASS` | `README.md` ends with `验证通过` |
| one logical command/task/execution | `PASS` | two same-key wire attempts, one durable create/task/execution |
| truthful terminal state | `PASS` | task and execution are `success`, empty error |
| same-task polling and stop | `PASS` | only the accepted task was polled; no request after terminal adoption |
| HEAD / Git / remote effects | `PASS` | target HEAD unchanged; commit and push forbidden |
| shell/tests | `PASS` | forbidden contract; no such execution in the task log |
| terminal speech at most once | `PASS` | observed `0`; no guaranteed-delivery claim |
| absolute zero unrequested paths | `NOT CLAIMED` | shared Agent Runtime artifacts are recorded and remain follow-up |

By the accepted ownership boundary in D-057, the open runtime-artifact and Speech-quality items do not block D-031 closure. D-031 remains a bounded Demo/Compatibility carrier and receives no formal replacement credit.
