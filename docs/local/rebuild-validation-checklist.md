# Rebuild validation checklist

Everything that lands in the next venv rebuild and restart, and what proves each
one works. Written 2026-08-18, when the queue grew past what anyone would
remember.

**Why this file exists.** The queue for this rebuild is larger than anyone would
hold in mind, and a regression in any of it lands at the same moment.

**Follow the existing provenance procedure.** Every venv under `~/venvs/` carries
a `PROVENANCE.txt`, and it is more thorough than a bare record of refs: it names
both repositories' SHAs and baselines, the composition commit by commit, the
constraints file that pins the package set to the previous build, a package-set
diff proven identical in both directions, byte-identity of the installed trees
against their sources, the `dist/` file count, test results, a smoke test on
throwaway ports and data dir, and a one-command revert. Read the current one
before building; it already documents the install-order trap, the gitignored
`dist/`, and the byte-compile step.

## Before building

- [ ] Build agent-core **from our branch**, never from the `pyproject.toml` pin.
      The pin form toggles between a PyPI version and `@develop` at upstream
      release boundaries, and `@develop` is a moving branch.
- [ ] Record both SHAs — jiuwenswarm and agent-core — in the venv directory.
- [ ] `npm run build` for `dist/`; it is gitignored, and a venv built from a
      fresh worktree ships no web UI.
- [ ] Byte-compile before running pytest. `openjiuwen/harness/tools/worktree/git.py:376`
      has an invalid escape sequence in a non-raw docstring; with
      `filterwarnings = error` it becomes a compile-time `SyntaxError` that kills
      collection in ~69 modules on a cold venv, and disappears once bytecode is
      cached.
- [ ] `systemctl --user daemon-reload` if the systemd unit changed.

## What is NOT a risk, contrary to an earlier draft

Our 29 agent-core commits are **already deployed** and have been running since
2026-08-12. `PROVENANCE.txt` records agent-core built from `80a53799`, which is
our `local/deployed` tip, and the installed `task_tool.py` matches our branch
byte for byte. So `a8eda153` is live, and a paused subagent does **not** collapse
to an empty success in production.

Building agent-core from `local/deployed` for this rebuild is therefore a no-op
on the SDK side, not the arrival of 29 untested commits.

## Per-change: what to watch

### Session working directory (`fix/per-session-cwd-propagation`)

The clearest proof signal of the whole rebuild.

- [ ] `slack_*` and `cron_*` directories under `agent/workspace/projects/` start
      **receiving files**. Before: 1,495 such directories, every one empty, while
      41 loose files sat at the shared root.
- [ ] The shared root stops growing.
- [ ] Warm Slack sessions keep the old cwd until their adapter is rebuilt — not a
      fault, expected.
- [ ] Argument-less `Glob`/`Grep` stop seeing the old root's accumulated entries.
      They return empty rather than erroring, so this is silent; a skill that
      searched without a path will quietly find nothing.

### Cron caps and logging (`fix/cron-and-log-hardening`)

- [ ] Cron name cap 64→128, description 500→4096.
- [ ] **The frontend must be rebuilt** or the UI keeps enforcing 64/500 against a
      backend that accepts more.
- [ ] AgentServer payload log lines are clamped.
- [ ] `list_jobs` reports entries it drops instead of losing them silently.

### Cron status record + gateway defects (agent C)

- [ ] Placeholder posts as a `task_card` at `in_progress` and is **edited** to
      `complete`/`error` — not followed by a separate message.
- [ ] A failed run no longer vanishes: `str(exc)` is `''` for bare exceptions,
      which previously meant no text was synthesised and `push_update` was never
      scheduled.
- [ ] `timeout_seconds` reaches the transport. Previously a module constant
      capped everything at 600 s, so a job declaring 900 or 3600 was inert config
      — and the transport raised `RuntimeError`, not `asyncio.TimeoutError`, so
      the friendly notice was dead code.
- [ ] After a gateway restart an orphaned placeholder is **never** superseded
      (`crash_recovery_skip`). Expected, unfixable here.

### Block Kit inputs (`feat/slack-date-time-pickers` + agent B's pass-through)

- [ ] Each declaration renders and Slack accepts it.
- [ ] `state.values` shapes match the spec table — this is the one thing unit
      tests cannot settle.
- [ ] Withdrawal strips `input` blocks as well as `actions`.
- [ ] The existing option-button path is byte-identical.
- [ ] Questions are only emitted on a **streamed** turn; `enable_streaming` is
      `true` live, and the coupling is invisible in the config.

### Rich block rendering (agent A)

- [ ] Markdown tables render as `data_table` above the row threshold, plain
      `table` below.
- [ ] `page_size` default is 5 — a 12-row table that renders fully today would
      otherwise become 5 rows plus a pager.
- [ ] Charts under the marker; the allow-list admits only `data_table` and
      `data_visualization`, and rejects any block carrying an `action_id`.
- [ ] Streamed replies still chunk at 4,000 characters **before** blocks are
      built, so a table cut at a boundary loses its delimiter row and posts as
      raw pipes. The raised 20,000 budget does not apply on that path.

### Approval buttons (`feat/slack-approval-button-styles`)

- [ ] `reject` renders `danger`, `allow_once` renders `primary`, the two
      remember-options and everything unrecognised render unstyled.
- [ ] **Chinese labels work**: skill-evolution approval sends no `value` at all,
      only `{"label": "接收"}` / `{"label": "拒绝"}`.
- [ ] At most one `primary` per prompt.

### Interrupt classification backport (`1b070a206`)

- [ ] Tools with a bare `query` argument — `memory_search` and similar — are no
      longer misrouted as ask_user permission responses.

### Slack config surface

- [ ] One new key ships **bare**: `channels.slack.acknowledge_requests`. A key
      missing from the shipped template is deleted from the operator's file on
      upgrade.
- [ ] Deprecated `acknowledge_requests: false` maps to `off`.
- [ ] Per-channel behaviour overrides apply; the startup channel log appears.

### Skills

- [ ] **ai-news-monitor** enters git for the first time (21 commits + the
      `run_dir` fix). It is running in production and has been absent from the
      validated branch entirely.
- [ ] Its 3-hourly cron in its channel: gate refusals behave, `ledger.py start-run`
      derives the run directory, no `mktemp`.
- [ ] pr-tracker report polish: the coverage bullet is conditional, unknown-label
      bullets are aggregated, and that loop iterates reported rows rather than
      all active rows.
- [ ] `local_scripts/check_skill_drift.py` — note it currently reports a false positive
      for any skill shipping tests inside its own directory.

## Production surfaces to watch after restart

| Channel | Job | Schedule (Europe/Paris) |
|---|---|---|
| open-jiuwen-repo | pr-tracker report | 08:00 TUE–SUN |
| open-jiuwen-repo | roster | 07:00 MON |
| open-jiuwen-repo | author watch | 06:05:30 daily |
| jiuwenswarm-daily-intel | activity digest | 08:00 daily |
| knowledgeable-king | ai-news | every 3h at :45:30 |

**The host clock and all logs are UTC; cron expressions are Europe/Paris.** Never
compare the two directly — a `--since` bound in the wrong zone hides everything
and reads as a stalled scheduler.

**Check the journal, not just state files.** A run can complete, write its report
and update its state while the gateway has already abandoned it and discarded the
answer. Gateway lines appear **only** in `journalctl --user -u jiuwenswarm.service`.

## Known pre-existing failures — do not chase

- 3 in `test_message_handler_security_review_prompt.py` — `git remote set-head`
  fixture mismatch on this host.
- 8 in `test_debug_trace` — `openjiuwen.agent_teams.observability.callback_handler`
  absent since the merge base, on both sides.
- 4 `test_desktop_*` modules cannot collect — `No module named 'webview'`.
- 10 in `test_permission_prompt_wiring.py` and 2 symphony `FingerprintService`
  failures **should disappear** with our agent-core commits. If they persist,
  that is a finding.

## Rollback

Repoint `venvs/current` to `2026-08-12-full-v6` and restart. The old venv stays
intact, and `local/deployed` on both repositories is unmoved as the source
fallback.
