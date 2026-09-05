# SkVM CLI reference

Use only the section matching the operation. Verify flags against the installed
CLI when uncertain. Model IDs and adapters must match the user's configuration.

## Prerequisites

`skvm --help` establishes binary availability. `OPENROUTER_API_KEY` is required
for OpenRouter model calls, including the bare-agent profiler/compiler/optimizer.
`ANTHROPIC_API_KEY` optionally enables the Anthropic SDK backend. Check presence
without exposing values; missing credentials are configured by the user locally.
Do not install or change provider/account configuration through this skill.

Local `profile --list`, `proposals list/show/reject`, `logs` and `clean-jit` can run
without a key. `profile` without `--list`, `aot-compile`, `pipeline`, `run`, `bench`
and `jit-optimize` may call models.

## Profile and AOT compilation

```text
skvm profile --model=<id>
skvm profile --model=<id1>,<id2> --concurrency=4
skvm profile --list
skvm aot-compile --skill=<path> --model=<id>
skvm aot-compile --skill=<path> --model=<id> --pass=1 --dry-run
skvm pipeline --skill=<path> --model=<id>
```

Profiling produces a cached target capability profile. `--force` reruns it;
do not use it without a reason. Default adapter is `bare-agent`; supported
alternatives documented here are `opencode`, `openclaw`, `hermes`, `jiuwenswarm`.
Confirm installed CLI support before choosing one.

AOT passes: 1 extracts capabilities/gaps/substitutions; 2 adds dependency and
environment binding; 3 decomposes workflow/DAG. The default runs all three;
`--pass=1,3` selects a subset. Compiled variants land in `proposals/aot-compile/`.
Compilation is not runtime deployment.

## Single task and benchmarks

```text
skvm run --task=<task.json> --model=<id> --skill=<path/to/SKILL.md>
skvm bench --model=<id> --tasks=task_01,task_02 --runs-per-task=3
skvm bench --model=<id> --conditions=original,aot-compiled
skvm bench --resume=latest
skvm bench --list-sessions
```

`run` reproduces one task; `bench` compares tasks/conditions. Specify the intended
scope rather than relying on an unbounded “all tasks” example. Supported
conditions include `no-skill`, `original`, `aot-compiled`, selected-pass
`aot-compiled-p1/-p2/-p3/-p12/-p13/-p23`, `jit-optimized`, and `jit-boost`.
`--jit-runs` controls warmup for jit-boost. `--async-judge` defers judging.
Benchmark logs are `.skvm/log/bench/<sessionId>/`.

## Proposal management

```text
skvm proposals list --status=pending
skvm proposals list --skill=<name> --target-model=<id>
skvm proposals show <proposal-id>
skvm proposals accept <proposal-id> --round=2 --target=<dir>
skvm proposals reject <proposal-id>
skvm proposals cancel <proposal-id>
```

Accept only an explicitly authorized deployment. Omitting `--round` deploys the
engine-recommended round; omitting `--target` uses its default target. Confirm
those resolve to the user's authorized choice before acceptance.

IDs have the shape `<harness>/<safe-target-model>/<skill-name>/<timestamp>`.
Pass the returned ID verbatim; model slashes in this storage ID are slugified
as `--`. Do not reconstruct it from the optimizer model.

Detached JIT writes `run-status.json` with execution state separately from
`meta.json.status`. `show` displays that state and log tail. `cancel` stops the
identified detached run; synchronous commands remain owned by their original
execution handle. Inspect results before reporting cancellation/completion.

## Paths

- `SKVM_PROFILES_DIR`: profile cache (documented default `.skvm/profiles/`).
- `SKVM_DATA_DIR`: datasets (default `./skvm-data`).
- `SKVM_CACHE`: runtime cache (default `~/.skvm`).
- `SKVM_PROPOSALS_DIR`: proposals (default `~/.skvm/proposals/`).

Use actual CLI output/configuration as the path authority. Stderr progress lines
such as downloading profiles are not automatically errors; inspect exit status
and final state.
