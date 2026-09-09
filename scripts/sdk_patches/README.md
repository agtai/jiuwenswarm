# AgentCore source dependency

The accepted installation policy is source-first for subsequent development and
deployment. `agentcore-source.json` pins the upstream commit, reviewed Git content
tree, version and ordered patches. `.deps/agent-core` is an independent local Git
checkout; `pyproject.toml` and `uv.lock` use that editable source. Do not replace it
with an AgentCore package downloaded from a package index or a detached wheel.

The installed upstream SDK at `94e10cb6102c36fe78a64547957c0def97299273`
discarded `AssistantMessage.metadata` during stream aggregation and two ReAct
message copies. Responses reasoning/tool continuation needs that metadata in
the same Agent context. Execution rails also mutated ToolCall objects shared
with saved history. This generic fix snapshots metadata and tool calls by deep copy; it
does not rewrite answers, tool arguments, prompts, or reasoning content.

`openjiuwen-responses-metadata.patch` is the complete source delta against that
exact upstream commit, including a local package version for deployment identity.
No runtime monkey patch or site-packages edit is used. Remove this carry when an
upstream SDK with the equivalent fix is verified, and update the adapter's SDK
requirement together with its Agent/context regression tests.

Prepare source before the initial dependency sync (Python 3.11+ and Git required):

```powershell
python scripts/install_agentcore_source.py --prepare-only
uv sync --frozen
.\.venv\Scripts\python.exe scripts/install_agentcore_source.py --check
```

For an existing environment, run its Python with
`scripts/install_agentcore_source.py`; this verifies the source, explicitly
uninstalls the existing AgentCore distribution, then installs directly with
`uv pip install --no-deps --editable`. The build backend may internally produce
installation metadata/a wheel; the retained source checkout is the dependency
origin. `--repository <Git mirror>` can obtain the same pinned base offline.

Preparation refuses to overwrite an existing checkout. On a partial failure it
retains the checkout for inspection. Preserve `.deps/agent-core` and its local
commits when cleaning build artifacts. Source changes require their own review,
tests, local commit and an updated manifest/patch set in JiuwenSwarm. The content
tree permits reconstruction without depending on a local commit timestamp.

The ordered Goal control, task settlement and Goal output patches extend the same
SDK owners. `agentcore-goal-output.patch` pairs with SDK commit `fc12e445` and
adds admitted `set_goal`/`resume_goal` output acquisition, finishing-reader
handoff and cancellation-resistant lease release. The manifest pins their
combined content tree; replay all listed patches in order. Boundary evidence is
in [the Goal output record](../../live-voice/evidence/AGENTCORE_GOAL_OUTPUT_20260909.md).

`agentcore-output-lifetime.patch` then pairs with SDK commit `a3a1aee0`.
It adds the synchronous output-ready hook that lets a host retain the actual
shared reader before Goal work is scheduled. A missing/finishing reader cannot
bypass this check. The [output lifetime record](../../live-voice/evidence/AGENTCORE_OUTPUT_LIFETIME_20260909.md)
owns the cross-entry and transport-disconnect evidence for this patch.

`agentcore-swarmflow-reply.patch` pairs with SDK commit `f5039e60` and adds exact
pending human-input consumption through the existing Team/SwarmFlow owner.
Leader Harnesses hold one default background controller; pause/stop/finalize
fence both direct and already-in-flight legacy replies at the original Future.
The [shared Workflow input record](../../live-voice/evidence/AGENTCORE_SHARED_WORKFLOW_INPUT_20260909.md)
owns the scoped checks and independent review. Input receipt is not Workflow
completion. This source is editable; integrating a reviewed source change does
not require replacing it with a package installation.

`agentcore-work-context.patch` pairs with SDK commit `e8a1ea88`. It carries
bounded private Goal run contexts and explicit public per-work output provenance
through the existing Goal and Session owners, preserving the public GoalStore
protocol. Its seven-patch checkpoint reconstructs the corresponding tree. The
[work-context record](../../live-voice/evidence/AGENTCORE_WORK_CONTEXT_20260909.md)
owns the source pairing, scoped tests and closed independent findings.

`agentcore-model-call-guard.patch` pairs with SDK commit `1aac45ec`. The generic
`model_call_guard_scope` checks the exact Model/client after asynchronous SDK
input callbacks and before its original client invocation. The Host adapter
uses this for its retained work policy without replacing the configured client.
The eighth-patch source import was verified before the continuation extension.
See the [host binding checkpoint](../../live-voice/evidence/AGENTCORE_HOST_WORK_BINDING_20260909.md)
for the focused SDK/Host checks and remaining integration boundaries.

`agentcore-workflow-resume.patch` pairs with SDK commit `e3a1f875`, reviewed as
isolated commit `eb8e1e09`. `WorkflowResumeGuard` opts into exact root-interruption
recovery using a paired workflow/state/graph checkpoint. The existing in-memory
and SQLite checkpointers validate before restoration, and Pregel consumes that
snapshot without a second read or start-node fallback. That nine-patch checkpoint
has a verified editable import. See the
[Core Workflow record](../../live-voice/evidence/AGENTCORE_CORE_WORKFLOW_20260909.md)
for source reconstruction, tests, entry authority and supported recovery scope.

`agentcore-agent-input.patch` pairs with SDK `e833aa42` (isolated `f6b1e1ef`).
It binds a human reply to the exact pending generation and original User/Goal
work, preserving its reader, context and attempt. The existing ReAct handler
claims only after preparation and current authority checks. SDK and Host receipts
report claim, never completed tools or business work. See the
[Agent input record](../../live-voice/evidence/AGENTCORE_AGENT_INPUT_PUBLIC_20260909.md).

`agentcore-team-input.patch` pairs with SDK `a8822470` (isolated `1d021b09`).
It carries an optional trusted guard along the original single-leader input
chain and checks it in the existing NativeHarness supervisor before input
effects. Legacy routing remains available without the guard. See the
[Team execution record](../../live-voice/evidence/AGENTCORE_TEAM_EXECUTION_20260909.md).
`agentcore-native-taskloop-compat.patch` pairs with SDK `ffeb1abc` (isolated
`dbe46e9d`). The shared task executor reads `work.request_id` only from a matching
Deep `ActiveInteractionRound`; Team NativeHarness retains the actual task's
metadata/run context. The combined Agent-input and Team-input patches exposed
this subtype difference in real Team execution. The current twelve-patch manifest
pins tree `6f3826983ea8c15eb182ec7761705fd5058c1235`; actual editable import is
verified. The Team record covers the failing integration and affected reruns.

The debug launcher requires the project environment, verifies clean source before
build/sync, uses the frozen lock, and verifies editable installation origin before
starting a service. Ordinary `uv sync` now uses the same source; it cannot silently
restore an unpatched VCS package. The Responses adapter's version check remains a
compatibility check, separate from deployment provenance. Other configured
providers keep their existing path.

Regression ownership: `tests/unit_tests/common/test_openai_agentmodel_compatibility.py`
covers actual SDK ReAct invoke/stream, tool execution and continuation, message
serialization, isolation, incomplete responses, and stream event integrity.
Keep private API keys in environment/private configuration, never here.
