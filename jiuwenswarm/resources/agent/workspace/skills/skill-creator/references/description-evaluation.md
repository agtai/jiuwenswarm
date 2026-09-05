# Description triggering evaluation

Use for an explicit trigger benchmark or when validating a material routing
change. A short description should attract the intended task and reject nearby
lookalikes, not maximize invocation frequency.

Build realistic positive and negative queries. Include ambiguous near-matches,
not only obviously unrelated negatives. Preserve the user's examples and model
choice. A small qualitative routing probe can support a prose edit without a
full optimization loop.

## Bundled Claude CLI loop

`scripts/run_eval.py` and `scripts/run_loop.py` invoke `claude -p` and create
temporary commands in a `.claude/commands/` tree. They measure that harness, not
JiuwenSwarm or an arbitrary model API. Run only when Claude CLI is available and
that evaluation is requested/authorized. Use an isolated evaluation project and
an actual Claude-supported model; do not pass another host's current model ID
and claim it evaluates the user experience.

The eval-set JSON contains objects with `query` and boolean `should_trigger`.
If user editing of a large set is useful, `assets/eval_review.html` provides the
existing review/export UI. Otherwise use the already agreed cases directly.

From the skill directory:

```text
python -m scripts.run_loop --eval-set <trigger-eval.json> --skill-path <target-skill> --model <supported-Claude-model> --max-iterations 5 --verbose
```

Check current `--help` before using optional controls. The loop performs repeated
queries and train/held-out comparisons and may use substantial provider calls;
choose a run size within authorization. Track the process and inspect actual
results before claiming improvement.

Review the returned `best_description` for scope, exclusions and accidental
workflow instructions before applying it. Report measured results with the
harness/model/conditions; a higher trigger score does not waive human intent or
safety boundaries. If this CLI cannot evaluate the target host, state that limit
and use a host-appropriate authorized probe, or deliver the qualitative revision
without a fabricated benchmark.
