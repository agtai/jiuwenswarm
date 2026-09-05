# Background execution and stopping

The script backgrounds by default when `--foreground` is absent. Run from the
skill directory so `PID.info` is written where this workflow expects it.

```text
uv run scripts/main.py --mode query --query "research topic"
```

Read `PID.info`, verify that the PID command line belongs to this skill's
`scripts/main.py`, and retain that exact process identity for follow-up. A live
PID proves running, not completion. Track the owned run with available host
capabilities; verify its new files in `output/reports/` and report failure or
completion truthfully. Do not start a second run merely because output is slow.
An approximate runtime is context, never a completion criterion.

## Stop the owned research

A stop request takes precedence over environment or `.env` setup checks.

1. Parse `PID.info`. If absent/invalid or the process no longer exists, report no
   identifiable running task; do not claim this stop killed it.
2. Verify the PID command line includes the current skill directory's
   `scripts/main.py`. Refuse termination when identity is unknown or reused.
3. Stop the entire owned process tree. Windows: `taskkill /PID <PID> /T /F`.
   Unix/macOS: the background process uses a separate session; send
   `kill -TERM -<PID>` to that process group, then `kill -KILL -<PID>` if it
   remains alive after allowing termination.
4. After a successful termination command, wait at least one second and check
   exit twice, with at least one second between checks. Verify the root and
   identifiable owned children have exited. Windows root check:
   `Get-Process -Id <PID> -ErrorAction SilentlyContinue`; Unix: `kill -0 <PID>`
   or `ps -p <PID>`.
5. Only after verified exit remove this run's `PID.info` and any monitoring/todo
   entries owned by this run. Otherwise retain the evidence, state that stopping
   is unconfirmed, and continue safe diagnosis or report the necessary user action.

Do not equate a sent kill command with a stopped task. Preserve unrelated
processes, files and monitoring tasks.
