# Shared host work binding checkpoint

This is an in-progress Task 2/3 checkpoint under the active unified execution
Goal. Main remains at `66833d5c`; these changes are uncommitted and not deployed.
Installed AgentCore is source commit `1aac45ec53229bc213fd012c5cb081dc319b94d8`,
tree `a14dab297969fdbfcc72f32cd9011751b0cab276`. The eighth patch is
`agentcore-model-call-guard.patch`, reviewed as isolated commit
`498cf1b9c7d429a0f50ecb1fe5380c63d3e99b26` and integrated locally by Main.
Source-manifest and actual editable-import checks passed. The previous seven-patch
reconstruction remains documented in [SDK work context](AGENTCORE_WORK_CONTEXT_20260909.md);
cumulative nine-patch reconstruction, including strict Workflow resume, is now
recorded in [Core Workflow evidence](AGENTCORE_CORE_WORKFLOW_20260909.md).

## Owned behavior

The existing session execution service retains immutable work configuration and
resolves actual SDK work/output identity. Text and Native may share an output
reader, but model, permission and generated-history decisions follow the work
that produced each event. Native output receives no heard-history credit.

Source-owned Goal answers settle the corresponding task's history while the
Goal reader stays open. The internal round boundary never reports business
completion. Unstamped EOF, errors or bubble boundaries cannot flush a managed
work's pending text. Native rounds preserve presentation without generated
history or memory effects. Finished managed buffers are released per task.

Native `goal.set` and `goal.resume` use the existing stored Agent, mode, project,
GoalManager and shared output owner. Exact CAS and the actual SDK control-lock
guard precede mutation. Repeated proposals reuse the original service entry's
observed admission; arbitrary snapshots cannot imply success. An ACTIVE resume
explicitly preserves its existing execution binding.

## Focused evidence

- Existing shared service and new execution context: 66 passed. Covers actual
  owner lifetime, wrong SDK/session rejection, policy and source isolation.
- Facade history and Goal adapter plus source-priority review cases: 65 passed
  in 30.97 s. Four facade cases traverse
  actual SDK Session source views, answer parsing and Goal adaptation into the
  facade; Text settles before reader EOF, while Native produces zero generated
  history/memory. Repeated/nonrepeated visible text stays single.
- Native contract, tools, context and shared Goal execution: 152 passed in
  13.67 s. An additional ACTIVE-resume assertion passed separately. These use
  actual Router/service/SDK GoalManager/Session persistence and output leases,
  with external authority/model resolution and lower facade projection controlled.
- Actual ReAct entry/tool snapshot: 56 passed in 14.30 s; the six delayed-client
  cases passed separately in 8.20 s after their fixture adopted a real SDK Model
  with a recording client. Includes actual Deep task scheduling, runtime adoption
  before other task rails/tool snapshots, per-step refresh, revocation and zero
  forbidden model effects. Main read the complete rail/helper diff.
- Independent source-priority and typed/dict per-binding/task round-memo checks:
  8 passed in 12.44 s. The two original counterexamples are repaired; these cases
  are now retained in the permanent source-metadata test module.
- SDK final call guard: 41 new and 17 existing model/timeout/header checks passed
  in 9.09 s. Main independently reviewed all four changed SDK files and ran 14
  relevant identity/concurrency/replacement/timeout checks, passing in 9.27 s.
  Host BoundAgentModel: 52 passed in 15.39 s against the same candidate source.
- Native Goal independent review found that an asynchronous authority read could
  outlive the grant or service. The final check now rereads time and service state
  after the wait. Root-mode permanent tests, including those counterexamples and
  carrier-independent execution, passed: 18 in 14.56 s. Reviewer statically
  confirmed the repaired boundary without repeating the larger Native group.
- Scoped Ruff and whitespace checks passed. The Goal adapter test no longer
  prepends an unrelated sibling checkout; actual import was verified as
  `.deps/agent-core/openjiuwen/__init__.py`.

Independent review found and prompted repairs for same-task model hot reload,
late tool registration, reader-based Text Goal history loss and discarded Goal
round boundaries. Those findings and the later input-callback/Responses-shape
findings are repaired and independently checked at their affected boundaries.

## Open boundaries

The model guard covers entry into the selected SDK raw client after its input
callbacks. It does not claim to guard waits/retries internal to a provider.
The existing SDK stream-wrapper chain does not immediately close the underlying
raw stream on early outer `aclose`; standalone probes reproduced this on both
the original and candidate SDK without BoundAgentModel. That inherited lifecycle
limitation is recorded, not credited as fixed by the call-guard patch.

Actual production Deep/Code binding, Core Workflow public execution/continuation,
remaining common interaction consumers, duplicate-code retirement and the final
browser/Provider/Agent candidate acceptance remain pending. Controlled SDK seam
tests do not substitute for those boundaries.
