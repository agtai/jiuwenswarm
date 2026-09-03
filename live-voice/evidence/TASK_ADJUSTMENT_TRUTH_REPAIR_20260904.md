# Direct adjustment and truthful status — 2026-09-04

## Accepted scope before implementation

Baseline: `bb91d5f766c1631b05f5c4555d6be91e86d24a0b`.
The user explicitly authorizes the following repair. The subsequent instruction
excludes restarting or redeploying services after this repair.
An exact, current modification request is consent; a second user confirmation
is not required. Ambiguous targets still require clarification.

The direct-adjustment consent boundary is Tier 3 (extending D-109); semantic
continuity and truthful presentation are Tier 2. Existing Core
authorization, bound confirmation consumption, final reread, replay and terminal
immutability remain in force; there is no public schema or Store migration.

Owned behavior and surfaces:

- `task_semantics.py`: one semantic decision preserves the resolved adjustment;
  do not replace it with an earlier foreground-conversation transcript. Explicit
  Task status/application queries select the existing read-only operations.
- `product_composition_registry.py` and authenticated composition: a current
  scoped adjustment consumes the normal exact authorization without an extra
  utterance; truthful control/status presentation reads canonical Task/Attempt
  and adjustment events. Dialogue receives bounded scoped Task facts so past
  assistant claims cannot serve as execution evidence.
- Formal Agent context/answer instructions and a private presentation helper:
  distinguish requested, pending, applied, rejected and terminal; fixed protocol
  states may produce generic localized wording, with Task metadata as data.
  No travel/name/price/filename classifier or fixed business answer is permitted.
- Focused semantic, Registry/Store and presentation tests; minimal configured
  model probes with no business side effects. Cold complete-diff review and an
  independent CLI review at this coherent boundary.

Acceptance: clear running modification submits once without another prompt;
correct target/requirements survive, requested and applied states differ; status
queries read real facts; ambiguous/unauthorized/stale/terminal/cross-scope paths
have zero forbidden effects. Cover replay/concurrency, feature-off and existing
creation/confirmation compatibility. Real semantic checks are distinct from
physical microphone/speaker or complete Demo acceptance.

Excluded: A2 (user reports successful creation), cancellation policy, 64-identity
capacity repair, other speech degradation, artifact arithmetic, full regression,
Provider/account configuration changes, project cleanup and remote-ref updates.
The fixed Demo project, running services and their runtime data remain untouched.

## Verification

Source baseline is the commit above; this report ships in the coherent repair
commit. Raw reports and captured Session inputs are private under `logs/`.

### Reproduced cause

In Session `web_1a0695445de_fa148e10f850`, the 00:15:15 modification was first
resolved to the correct running Task and a complete new requirement. The second
adjustment review selected the earlier foreground discussion correction instead.
The Registry retained an unconsumed confirmation; the Store had no requested or
applied adjustment event. The following application and progress questions were
routed to dialogue, which narrated successful modification from conversation.
This was not an exact task-name mismatch.

The repair removes that rewrite, consumes current exact consent through the
existing durable boundary, and uses canonical state for control/status wording.
Dialogue receives fresh scoped facts; grounding alone is not a guarantee against
all future model mistakes. An applied event confirms the Executor's modification
acknowledgement, not independent verification of every resulting document detail.

### Bounded checks

All pytest commands use `.venv/Scripts/python.exe -X utf8 -m pytest --no-cov -q
--tb=short --show-capture=no -o log_cli=false`:

- `tests/unit_tests/live_voice/test_task_semantics.py` and
  `tests/unit_tests/live_voice/test_semantic_registry.py`: **152 passed**.
  After the final prompt-order adjustment, the semantic file alone was rerun:
  **78 passed**. Private logs: `adjustment-semantic-closure-20260904.log` and
  `adjustment-semantic-order-20260904.log`.
- `tests/unit_tests/agentserver/test_formal_live_voice_adapter.py`:
  **26 passed**, one existing dependency deprecation warning.
- `tests/unit_tests/live_voice/test_p3_authenticated_composition.py -k
  'task_adjust_requires_exact_origin or authenticated_addressed_adjust or
  confirmation_forgery_cross_binding or confirmation_is_single_use or
  cross_task_confirmation_rejected or
  production_create_confirmation_rejects_context_or_model_drift'`:
  **8 passed**.
- Final query compatibility checks: **5 passed** in
  `adjustment-query-compat-20260904.log`, including one new task.get case.
  Self-review narrowed fixed wording to task.status/task.adjust so a detailed
  task.get retains its complete canonical specification in the grounded Agent
  path; it is not reduced to a progress sentence.
- After review fixes, the Registry semantic module was rerun: **80 passed** in
  `adjustment-review-registry-final-20260904.log`. New cases force applied and
  rejected settlement before presentation, distinguish definite conflict from
  timeout/internal failure after durable acceptance, and replay without another
  effect. The dialogue test ACKs the augmented commit, verifies retained assistant
  history and checks that the origin entry is released.
- These comprise **192 distinct automated cases**; repeated runs do not count
  as additional coverage. No frontend source changed or build ran.
- The first module run exposed an inherited stale presentation oracle (400
  characters in the envelope; current source already owns a 200-character system
  rule). That assertion now checks the real owner. The conversation-isolation
  assertion now separately checks the newly added Task-truth context; original
  history and notification exclusion assertions remain.

Applicable root TESTING dimensions: P/S/X cover real Registry, confirmation,
SQLite, outbox, control presentation and P2 ACK with a controlled model/Executor;
pending and applied differ and Task B remains unchanged. N/B/I cover ambiguous,
unknown and unowned references, malformed output, unsupported capability,
cross-binding and forged authority with zero forbidden effects. T/C/R cover
duplicate unified submission, exact single-use durable claims, origin/context
drift and unknown outcomes. F includes mutation feature-off and capability
failure. K covers retained creation, two-turn cancellation and frozen semantic
replay. Public-schema migration, new transport/device behavior and host-crash
durability are not introduced and have no new claim in this batch.

### Configured model evidence

The generic read-only `scripts/live_voice/task_control_model_probe.py` loads the
existing local configuration with ordinary environment resolution. Its initial
raw-config loading omitted that resolution and got HTTP 401; correcting the
probe fixed access without editing configuration or credentials.

Initial real probes passed the three recorded positive turns but exposed an
ambiguous modification selecting a Task from recent context. General ambiguity
instructions alone did not reliably repair it; later output selected clarification
with invalid operation fields or fell back to dialogue/list. Those failures remain
in private diagnostic reports. The final repair aligns the output field guidance
with its existing instruction to choose route/target before operation arguments,
and explicitly states the existing null/empty clarification shape. This changes
prompt serialization, not the public schema or server validation.

Final command: the generic probe with existing `config/`, private cases
`logs/task-control-final-cases-20260904.json` and report
`logs/task-control-final-report-20260904.json`.
**8/8 pass, one model invocation each**: recorded explicit adjustment, application
query, progress query, foreground-only correction, ambiguous adjustment, equipment
adjustment, reversed Task ordering and a different ambiguous expression. The
three ambiguous cases return clarification with no operation/target/arguments.
Recorded queries select the exact Task; the equipment change preserves the other
Task. No Task, Tool, Executor or project-file operation is available in this probe.
This is a bounded sample, not a language-generalization or complete Demo claim.
The final probe's resolver SHA-256 matches the tested file:
`382b25d3653f9edd94cec73b319cd93f97ab350b5e5d4175126d9238e24e9ded`.

Static checks parse all eight changed Python files, resolve 35 local Markdown
links with zero missing targets, pass `git diff --check`, and find no tracked
`docs/zh/live-voice/` duplicate. Existing private `.env` and `config.yaml` hashes
match their pre-repair values.

### Review and remaining limits

Cold complete-diff self-review performed. Independent read-only `codex review`
completed and found three introduced issues, all addressed in this batch:

- P1: retain the exact augmented Agent commit after adding Task facts, so ACK
  finds its origin, retains analysis and frees the bounded entry. Capacity check
  and insertion now occur together after the awaited reads.
- P1: reread the exact adjustment ID from canonical current-Attempt events before
  speaking; do not announce admission-time pending when it has already settled.
  The snapshot head still fences concurrent later events; absence in the bounded
  window remains unknown, never inferred from another command.
- P2: handle formal failure before looking for Task metadata. Definite rejection
  codes and uncertain outcomes produce distinct wording; neither is narrated as
  target ambiguity. Timeout/internal failures remain unknown after durable work.

The scoped independent follow-up concludes **no remaining actionable issue**.
It independently ran the eight focused review cases: **8 passed in 15.35s**,
verified the final prompt source hash and `git diff --check HEAD`, and removed
its disposable test directory. Initial reviewer sandbox setup failures were
resolved with a workspace-local test directory; they did not execute failing
product tests. Raw review logs remain private
(`task-adjustment-independent-review-20260904.log`,
`task-adjustment-review-followup.log`, `task-adjustment-review-final.txt`).

No service restart/deployment, Provider/account change, project cleanup or remote
update was performed. A2, cancellation policy, the recorded cumulative capture
limit and artifact arithmetic remain excluded. Physical microphone/speaker,
actual output-document modification and the full A/B/A2/offline/ACK/refresh
journey have not been rerun on this source. Overall product remains **PARTIAL**.
