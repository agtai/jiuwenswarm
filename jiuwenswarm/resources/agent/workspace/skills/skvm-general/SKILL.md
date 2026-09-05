---
name: skvm-general
description: Use the SkVM CLI for requested model profiling, skill AOT compilation, task runs, benchmarks or proposal management.
---

# SkVM

Use for SkVM operations, not generic requests to profile application performance
or improve skill wording. Requested evidence-based JIT optimization uses the
available `skvm-jit` skill.

## Execute the requested operation

Check `skvm --help` and the relevant command help for the installed CLI. Read
[cli-reference.md](references/cli-reference.md) for command shapes, proposal IDs
and environment contracts; do not load every command route for a single query.
Reuse the user's model, task, skill and output choices. Resolve missing inputs
from known context before asking.

Local commands such as `profile --list`, `proposals list/show/reject`, `logs`
and `clean-jit` do not require an API key. Model-calling operations do. Check
required credential presence without printing values; if absent, ask the user
to configure the named environment variable locally, never to send the key.
If SkVM is missing, report the prerequisite; this skill does not install it.

## Boundaries and completion

- Multi-model profiling or a large benchmark needs explicit scope/cost
  authorization. State model/task counts before an authorized run; do not ask
  again when those bounds were already approved. Use supported concurrency for
  independent work within those bounds.
- Listing or inspecting proposals does not authorize acceptance. Run
  `skvm proposals accept` only when the user explicitly requested deployment of
  that proposal/round/target; it overwrites skill files. Preserve existing
  authorization and do not silently choose a different target.
- Track requested work to its actual result. For detached runs, inspect the
  owned proposal status; report pending/failed states accurately and do not
  confuse an allocated proposal ID with completion.
- Deliver the requested result, file/proposal identity and relevant validation or
  limits. An instruction edit alone is not evidence of a performance gain.
