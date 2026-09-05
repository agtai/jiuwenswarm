---
name: skvm-jit
description: Generate a SkVM JIT optimization proposal from task evidence when the user requests or has authorized that optimization run.
---

# SkVM JIT optimization

Create a reviewable proposal for a skill whose instructions caused a concrete
failure, partial result or unnecessary detour. A problem during another task
alone does not authorize a paid optimizer run or disclosure to another provider.
Without an optimization request or existing authorization, finish the original
task and report the useful observation without launching SkVM.

## Inputs and execution

Identify the actual skill directory, relevant sanitized task evidence and target
model/provider from trusted context. Use the path supplied by the host or user;
only if unavailable consult [adapter-skill-paths.md](adapter-skill-paths.md).
Do not ask for a path or model that is already known.

Read [optimization-run.md](references/optimization-run.md) when preparing an
approved run. Use its existing report/log schema and `--task-source=log` contract.
Use the authorized optimizer/model configuration, checking required credential
presence without revealing values. If SkVM or a required credential is missing,
report the precise local prerequisite; do not install it or request secrets in
chat. Independent environment/network failures are not skill defects.

## Completion and boundaries

Track the owned proposal through completion/failure when the request is to
produce a proposal; a launch-only request can finish with a verified pending ID.
Do not start duplicate runs or imply that detached work has completed.

Deliver the actual proposal ID, execution status and review command. Keep the
original skill unchanged. Deploy only when the user explicitly asks to accept
that proposal; inspect its round/target before the authorized overwrite.
SkVM-orchestrated benchmarks own their own optimization loop, so do not submit
a second post-task run from inside that flow.
