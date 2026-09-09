# Configured Team execution — 2026-09-09 checkpoint

Status: scoped Host/public execution and independent review passed. The guarded
SDK input and NativeHarness compatibility extensions are source-paired. The
real original-SDK execution chain is verified with a controlled Model client;
final clean-candidate deployment and real Provider acceptance remain pending.

The [execution plan](../reviews/AGENTCORE_UNIFIED_EXECUTION_20260909.md) records
file ownership and Tier 3 admission/acceptance. Main owns Native
`team.list/get/start/cancel` and `workflow.start`. The Team worker owns the shared
Host and the isolated SDK Team input seam.

Main ran the following together using the repository's default asyncio mode:

```text
tests/unit_tests/agentserver/test_team_execution_public_entries.py
tests/unit_tests/agentserver/test_team_execution_capabilities.py
47 passed in 13.30s
```

The shared async fixture was corrected to `pytest_asyncio.fixture`; the first
public run stopped at setup and gave no behavioral credit. The successful rerun
uses real SDK Team/runtime/pool/static configuration and actual metadata files.
It proves exact, secret-free observation without preparing a Team, fresh
authority even for an empty directory, project/mode isolation, old-epoch rejection
and invalid SwarmFlow intent rejection before delivery. Native `executions` is a
list from the shared service; a directory entry is not execution admission.

The separate real leader probe demonstrated the original ReAct/AbilityManager/
TeamPermissionRail/SwarmflowTool/AsyncToolRuntime/script-engine chain (two cases).
This removes the need for a second tool executor. Its controlled model seam does
not count as a real Provider journey.

The demonstrated SDK extension is now implemented: a trusted optional input guard
at the original supervisor's final sequence/round/steer/follow-up admission boundary.
Main's strict-mode `test_guarded_team_input.py` check passed **20 cases in 10.72s**,
including real Runner-to-supervisor delivery, legacy compatibility, queued
revocation/replacement/closure rejection, exact session checks, steer reuse and
observer cancellation without cancellation of an already admitted round.
These checks do not establish the unfinished Host execution integration.

Team input commit `a88224703284912511abaca7d972c1ec107da899` is installed together
with Agent input commit `e833aa42f466a48b14ef2794d581ebd3206678d2`. The paired tree
`f9b2ae8047714035122121a1a6da82566f9c70c9`, successful 11-patch manifest check and
exact reconstruction are recorded in the
[Agent input source-pairing checkpoint](AGENTCORE_AGENT_INPUT_PUBLIC_20260909.md#source-pairing-and-real-execution-checks).

This boundary supports the application's configured in-process Team mode.
Cross-process/distributed/external CLI execution cannot carry the current trusted
in-process authority and rejects; the adapter does not silently change the mode.
An input ACK or producer exit never proves the Team's business task completed.
Main's Task 2/3 commits and cumulative automated/real acceptance remain unfinished
at this checkpoint.

## Host execution and cumulative SDK compatibility closure

The shared adapter uses the original TeamManager producer, Runner, configured
leader/member harnesses, ReAct, AbilityManager, SwarmflowTool and AsyncToolRuntime.
It keeps original model/configuration and role-specific permission semantics.
Cold admission and warm control use current scope/authority; a transient workflow
intent travels through the original leader tool loop. It creates no second Team
scheduler, tool executor or business-completion authority. Managed iterators close
within the original physical producer; explicit cancellation targets that exact
producer, including when the caller supplies an observed control execution ID.

The worker's dedicated Host/rail run passed 21 cases in 40.42s, and affected
existing assembly compatibility passed 25 cases in 26.24s. Those runs used the
isolated Team-input SDK candidate, so they did not establish compatibility with
the later cumulative Agent-input patch. Main's installed-source public test
exposed a real failure: the shared task executor read `ActiveRound.work`, but
NativeHarness has a different round type. The positive path made zero Model calls.

The minimal SDK repair uses the canonical Deep `ActiveInteractionRound` only for
its matching request identity and otherwise preserves actual task metadata. Red
checks failed twice; after repair, 13 scoped SDK checks passed in 9.57s, including
real NativeHarness cold/next rounds, actual Native source projection, matching and
nonmatching Deep tasks, and exact User/queued User/Goal input regressions. Main
cold-reviewed the complete two-file diff. SDK `ffeb1abcc5cc0bc72b5c813a3316d4334d39e15f`
(isolated `dbe46e9d`) and the twelfth patch pin tree
`6f3826983ea8c15eb182ec7761705fd5058c1235`; editable import was verified.

On this actual installed cumulative SDK, without weakening assertions:

- `test_team_execution_public_execution.py`: 1 passed in 56.97s. Closed Native
  schema/router to cold Team start/get/list/replay, actual Model invocation, warm
  SwarmFlow start through original input/rails/tool, real script launch and
  settlement/result, duplicate suppression, and exact cancellation/physical exit.
- Two affected `test_team_execution.py` cases: 2 passed in 41.10s. An observed
  control ID cancels its original producer; replacement identities affect neither
  the old nor replacement producer. Warm input still invokes actual ReAct twice.

Full scoped Host cold review and independent review completed. The observed
control-ID repair and final source-type correction received limited cold review;
all reported findings are closed. Scoped Ruff passed. Local detailed Host evidence
is under `.codex_tmp/team-execution-design/`; the public SDK12 report is
`%TEMP%/jiuwen-team-execution-worker/native-public-sdk12.html`.

These tests control the raw Model client and stored template lookup; they do not
claim a physical Provider, audible response or a human's business-task acceptance.
Neither input acceptance, producer exit nor `team.completed` is reported as proof
of business completion; legacy SDK finalization limitations stay explicit.

The twelve ordered patches were independently reconstructed with the actual
source installer from the pinned upstream base using the local Git mirror:
`.codex_tmp/agentcore-twelve-patch-replay-e327uuwm/.deps/agent-core`, reconstruction
commit `2daf8ed`, exact tree `6f3826983ea8c15eb182ec7761705fd5058c1235`.
The reconstruction changes no installed environment and preserves the source checkout.
