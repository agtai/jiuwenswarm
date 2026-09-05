# Evidence-based JIT run

Use after the root skill establishes authorization for the optimizer/provider
and the scope of submitted evidence. Redact secrets and exclude private file
contents. Submit only the evidence needed to diagnose the skill's instructions.

## Input formats

Choose one. A short report is enough for a specific instruction defect:

```json
{
  "task": "brief description of the requested work",
  "outcome": "partial",
  "issues": ["specific instruction problem and observed effect"],
  "skill_feedback": "concrete improvement supported by the evidence"
}
```

`outcome` is `pass`, `fail` or `partial`. A pass can still document a concrete
instruction detour, but a clean successful run needs no automatic optimization.
Failures that clearer instructions could not avoid are not skill feedback.

For relevant turn-by-turn evidence, use JSONL:

```jsonl
{"type":"request","ts":"<iso8601>","text":"<sanitized request>"}
{"type":"response","ts":"<iso8601>","text":"<relevant response>"}
{"type":"tool","ts":"<iso8601>","text":"<tool summary>","toolCalls":[]}
```

Do not attach full conversation history merely because the format accepts it.
Use one report per task so its outcome and attribution remain clear.

## Launch

```text
skvm jit-optimize --detach --skill=<absolute-skill-directory> --task-source=log --logs=<absolute-report-path> --target-model=<provider/model> --optimizer-model=<authorized-provider/model>
```

- `--detach` starts a background worker and returns its proposal identity.
- `--task-source=log` analyzes supplied evidence without rerunning the task.
  Do not use `real` or `synthetic` sources in this post-task flow.
- `--target-model` is required even in log mode. It selects the storage/model
  grouping, not task execution. Use the actual original task model with a provider
  prefix matching configured routes; ask only if it cannot be determined.
- `--optimizer-model` performs the LLM work. Do not substitute a new provider or
  paid model solely because an old example recommends it.
- `--target-adapter` optionally records the original host (default `bare-agent`).
- `--failures` is optional for existing per-report failure files; counts must
  match logs. Omit it for an ordinary single report.

Log mode does not accept task rerun controls such as `--tasks`, `--test-tasks`,
`--synthetic-count`, `--synthetic-test-count`, `--runs-per-task`, `--convergence`
or `--baseline`. Use current command help if installed behavior differs.

## Track and deliver

Capture the ID from the line beginning `Proposal: `, not `Proposal dir:` or a
status sentence. Use `skvm proposals show <id>` to inspect execution state and
results. The worker records `run-status.json` (`queued/running/done/failed`) and
`run.log` separately from proposal acceptance metadata. A missing key can fail
inside the worker after the launcher returns; an allocated ID proves neither
completion nor a usable proposal.

Nonzero launch with no ID means no confirmed run. Read sanitized stderr and
resolve the cause; do not blindly retry, especially when another optimization
already owns that skill/model. If cancellation is requested, use the identified
`skvm proposals cancel <id>` and verify state.

The optimizer snapshots the original as `round-0/` and proposed changes as later
rounds under `$SKVM_PROPOSALS_DIR` (default `~/.skvm/proposals/`). Review the
proposal and report actual status. Do not edit/deploy the original through this
flow. `skvm proposals accept <id>` writes back only after explicit deployment
authorization; the available `skvm-general` skill covers proposal management.
