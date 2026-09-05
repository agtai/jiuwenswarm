# Behavioral evaluation and comparisons

Read when evaluation is requested or the changed behavior needs evidence beyond
structural checks. Scope cases to observable outcomes and meaningful failure
boundaries. Reuse known inputs and acceptance; do not require another interview
when they are already clear. Provider calls, side effects and substantial cost
must fit the existing authorization.

## Cases and runs

Use realistic prompts, including a nearby non-trigger or rejection case where
relevant. For objective outputs, define assertions that inspect the result;
subjective quality benefits from direct artifact review. Do not force numerical
assertions to stand in for design judgment.

Use `evals/evals.json` and [schemas.md](schemas.md) for the existing formats.
Outputs belong in a sibling `<skill-name>-workspace/iteration-N/` directory, with
one descriptive case directory and separate `with_skill/outputs/` and baseline
outputs. Keep user files and runtime-installed skills untouched.

For comparisons, use the same prompt/input on both sides:

- New skill: baseline without the skill.
- Revised skill: a snapshot of the original or a clearly identified earlier
  version, chosen to answer the comparison question.

Record the skill version, model, host and conditions. Use independent agents
when available and useful. Batch independent runs within actual capacity; do not
require every case and baseline to launch in the same turn. If independent runs
are unavailable, a serial self-check can still catch defects; label its bias and
do not represent it as an independent comparison.

Each case has `eval_metadata.json` with `eval_id`, descriptive `eval_name`,
`prompt` and `assertions`. Save timing/token measurements when the host provides
them. Do not invent `total_tokens` or `duration_ms` or assume every host emits
them; mark unavailable measurements explicitly.

## Grade and present

Read [grader.md](../agents/grader.md) when grading assertions. Save `grading.json`
using the existing `expectations` objects with `text`, `passed`, `evidence`.
Prefer reproducible checks for machine-verifiable properties.

For a benchmark, run from the skill directory:

```text
python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
```

Inspect the generated `benchmark.json` and `benchmark.md`, including variance,
non-discriminating assertions and time/token tradeoffs. Use the relevant section
of [analyzer.md](../agents/analyzer.md) when analyzing comparison patterns.
Missing measurements remain missing rather than zero.

For user review of multiple outputs, the bundled viewer can provide a static
report without a server:

```text
python <skill-dir>/eval-viewer/generate_review.py <workspace>/iteration-N --skill-name <name> --benchmark <workspace>/iteration-N/benchmark.json --static <output.html>
```

Pass `--previous-workspace <workspace>/iteration-N-1` for a comparison with the
preceding iteration. Omit the benchmark argument when no benchmark was produced.
Use tool `--help` for other supported options. If a viewer is not useful or
available, present the actual outputs and evidence directly. Do not claim a file
or browser was opened unless it was.

When collecting viewer feedback, use its submitted `feedback.json`; do not infer
approval from silence. Feedback is an input to an iteration, not a mandatory
pause after every small edit. User-requested review gates remain effective.

## Iterate to the requested result

Inspect failures and transcripts to locate unnecessary detours or missing
contracts. Generalize the repair instead of adding example-specific MUSTs.
Rerun affected cases and any comparisons needed for a claim; broaden when new
failures or material changes justify it. Stop the loop when the requested
acceptance is met, a real prerequisite blocks further work, or additional
experiments need scope/cost authorization. Report unresolved outcomes honestly.

A blind comparison is useful when the user asks whether one version is better:
read [comparator.md](../agents/comparator.md) and the comparison section of
[analyzer.md](../agents/analyzer.md). Keep versions hidden from the comparator
and preserve raw results. This is optional, not part of every skill edit.
