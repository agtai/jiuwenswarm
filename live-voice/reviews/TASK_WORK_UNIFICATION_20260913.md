# Task / Work unification execution record

## Accepted scope and baseline

User approved Task first, Work second, then architecture and comparative code
accounting. One commit per affected repository per stage; no remote update.
Baseline Host: `88a2228ab5d4075059a84e57fb0b94612b4f325e`.
Baseline SDK: `13493418b275bbdb812303f2c2375bfece0778e3` (no upstream tracking).
The user's session `web_1a09ba51ef2_c737a98beaa0` accepted Task creation,
cancellation, adjustment, querying, result confirmation and Work execution.
This is the behavior to preserve, not a claim about every recovery scenario.

## Ownership and implementation plan

- [ ] Task: inventory remaining Host task mechanisms; reuse existing SDK owners.
  Extract reusable project attempt execution, journal, file-effect application,
  checkpoint and recovery mechanisms behind an explicit application adapter.
  Host resolves project/configuration/Agent requests and runtime support paths;
  SDK must not import Host or require a voice channel to execute.
- [ ] Check task projections and residual contracts individually. Voice intent,
  confirmation, dialogue and playback policy stay at the channel/application
  boundary; generic task/artifact facts have one SDK owner.
- [ ] Verify Task with current temporary SQLite, real local Git/file and SDK
  Agent adapter tests; cover exact identity, cancellation, adjustments, terminal
  state, restart, unknown effects and unchanged user files. Review both diffs,
  build/install compatibility, commit each repository once and record counts.
- [ ] Work: map journal/runtime/context/producer responsibilities against SDK
  execution and persistent tasks. Unify reusable execution ownership and facts;
  preserve immediate analysis vs durable project delivery semantics and existing
  serialized identities. Do not force every query into a UI Task card.
- [ ] Verify Work positive/negative execution, cancellation settlement, restore
  without replay, source isolation and unchanged Task behavior. Review both
  diffs; include final documentation in this stage's Host commit.
- [ ] Record reproducible production-code counts after each stage: Voice,
  application additions, SDK additions; separate tests/docs and baseline edits.
- [ ] Update architecture: merge M4+M5 and M7+M9, identify AgentServer as the
  application process and AgentCore as its SDK; trace actual call/data routes.
  Recheck Hermes and the two full-duplex PR source snapshots at module level;
  distinguish equivalent, shared responsibility/different behavior, and absent
  modules. Keep historical design records explicitly historical.
- [ ] Deploy correct paired commits, verify SDK import/version and runtime
  contract, report remaining human acceptance and any unresolved evidence.

## Risk, acceptance and exclusions

Task/Work persistence, cancellation and execution ownership are Tier 3 integration
seams. Preserve existing database schemas, identifiers, project permissions,
file-effect declarations, unknown-outcome semantics and real execution settlement.
Do not manufacture completion or recovery, or silently rerun accepted work.
Use focused existing scenario groups; independent review at each stage, rerun
only affected checks after findings. No blanket full-suite or per-function tests.

No provider/model/timeout/buffer changes, transport workaround, production data
rewrite or unrelated task-framework rewrite. Existing Controller/Team Task APIs
must retain their consumers; consolidation does not mean replacing semantically
different public SDK APIs with one table. The stale prepared voice announcement
issue remains separately tracked, not silently included in this migration.

## Initial audit

The first migration already moved persistent Task core, store, adjustment queue,
source contract and durability facts into SDK. Host still contains a 6,000+ line
project executor combining generic journal/recovery/Git protection and a small
number of application dependencies. This is the main remaining Task extraction
boundary. Work still has its own Host journal/runtime with explicit UNKNOWN
restoration and exact cancellation; its state cannot be naively equated to a
project-mutation Task. Application adapters must be separated before moving it.

## Task stage implementation and verification

SDK now owns project executor, attempt journal, file application/recovery,
execution checkpoint/tool binding and result artifact reader. Host supplies an
explicit application adapter for AgentRequest, shell guard, workspace and support
paths; callers import SDK types directly. Task/Attempt enums reuse SDK identity.
Legacy TaskCommand/TaskSpec and event projections remain only for compatible
voice mapping/test consumers; they own no production executor or state machine.

Preserved SQLite schemas, persisted profile IDs and source strings. Package pin
advances to `0.1.17+livevoice.2`; Work and Provider settings remain untouched.
Optional SDK observation forwards the Host telemetry within execution context.

- Checkpoint/file-plan focused tests: 50 passed.
- Final project execution/file-plan/durability group: 195 passed, 2 environment
  skips. First run found one obsolete subprocess test import, fixed before rerun.
- Project authority, source, adjustment, handoff, intent and result integration:
  102 passed.
- SDK application-task group, including independent real Git execution and
  reopen/no-Agent-replay test: 103 passed.
- Independent static review found no actionable regression or missing generic
  Task execution owner. AST comparison verified unchanged journal/recovery/file
  algorithms, checkpoints and result readers. Review did not rerun tests.

Four inherited synchronous Path authority checks retain explicit ASYNC240
exceptions; this migration does not alter their scheduling. The new immutable
invocation moves Host request protocol construction out of SDK. No live Task
was rerun and no physical speech acceptance is claimed by these tests.

Paired wheel builds/import passed using a fresh install target and verified SDK
`0.1.17+livevoice.2`. A first wheel exposed a stale setuptools build copy of the
deleted Host checkpoint; the old build directory was preserved outside the
repository, and the clean rebuilt wheel excludes that module. No compatibility
production copy was restored. SDK Task commit:
`ae5494e167ad8ff13e1b503697e85335dabbf550`.

### Task-stage production code accounting

Physical lines include comments/blanks; tests, docs, config and binary assets are
excluded. Baselines are official Host develop `8c7bfecd` and compatible SDK
`b5f189ba`. Full existing modified modules are not counted as wholly new code.

| Owner | Current lines in newly introduced files | Net addition including existing-file edits | Current lines across affected files |
| --- | ---: | ---: | ---: |
| Voice-specific modules | 113,424 | 113,424 | 113,424 |
| JiuwenSwarm application/shared additions | 41,499 | 49,741 | 152,256 |
| AgentCore additions | 32,504 | 32,504 | 32,504 |

[Per-file manifest](../evidence/TASK_UNIFIED_CODE_COUNTS_20260913.json) records
classification, baseline/current counts, additions/removals and source SHA-256.
The [counting script](../../scripts/live_voice/code_ownership_counts.py) documents
the stable ownership rules. The Host affected-file total includes 102,515
baseline lines; it must not be presented as 152,256 lines introduced by Voice.

## Work stage boundary

Task-stage Host commit is `a8e681f1588ca9b8de184bf733ab79f5c9d4db05`.
Work stage starts from this paired source and SDK `ae5494e16`.

Move general Work admission/revision/settlement/UNKNOWN restoration and its
checkpoint CAS into SDK application/tasks. Reuse SDK scope/context contracts and
an interaction-cancellation primitive; detached accepted execution must not
inherit transient speech cancellation. Host retains AgentRuntime producer pins,
model/Agent configuration and input-journal/source/presentation integration.
Split those application journal tables from generic Work checkpoint storage,
preserving one transaction and all existing schema validation hooks.

Existing SDK AsyncToolRuntime is a per-harness background-tool registry with
immediate cancellation reporting and no durable revision/CAS/UNKNOWN restoration.
Replacing Work with that API would lose physical-settlement and restart truth.
Existing project Tasks require project_mutation authority; routing all queries
through them would add incorrect write/Task-card semantics. Unification therefore
means a single SDK owner and shared primitives with explicit execution modes,
not merging distinct state meanings or rewriting existing Controller/Team APIs.
Retain serialized work IDs/states/reasons, queue bounds and model timeouts.

### Work implementation and verification

SDK now owns WorkRuntime/SqliteWorkStore, shared read-only settlement and bounded
observation cursors. Host runtime implementation is deleted; Host journal keeps
only input/source/presentation integration using atomic SDK schema hooks. Local
NativeWork aliases reference SDK classes, not compatibility copies. Package pins
advance together to `0.1.17+livevoice.3`.

- Work/journal/service/business/ownership/policy regression: 145 passed.
- SDK application group with independent Task+Work SQLite and observation waits:
  106 passed; SDK boundary test scans all imports including deferred imports.
- Observation/presentation regression after cursor correction: 33 passed.
- Ruff for SDK boundary and changed Host service/schema/count scripts passes.
- Independent static review confirmed unchanged execution/cancellation/CAS and
  journal semantics. Its one P1 reverse Host import in SDK observation waits was
  fixed by a shared SDK cursor contract and independent scope/wait tests.

Two test invocations were stopped after inherited repository-wide coverage
generation kept the process running; the affected tests completed with
`-o addopts=` (no broad coverage), 33 passed in 13.11 seconds. A first combined
cross-repository pytest invocation had conftest import-name collision; SDK and
Host runs are correctly separate. Neither required a production workaround.

Architecture now uses M4+M5 and M7+M9 and identifies AgentServer as application
container, AgentCore as SDK. Work/Task remain distinct execution modes with one
SDK owner. Fixed-source Hermes and unchanged combined duplex plugin code were
rechecked; their execution/voice state machines were not modified. Counts are
in architecture/UNIFIED_CODE_ACCOUNTING.md with per-file hashes and exclusive
module buckets. Retained Native/Cascade/diagnostic code is included explicitly.

Incremental independent review closed the P1 and found no new architecture/SDK
ownership issue. Both wheels build and import together from a fresh target;
SDK `.3` observation runs before Host import, Host Work is the same SDK class,
and the Host project adapter subclasses the packaged SDK executor. The clean
Host wheel excludes both retired runtime/checkpoint modules. The old build cache
was preserved outside the repository before building. Current manifest source
hashes, module-total reconciliation and local documentation links pass.
Changed Host tests collect successfully (104); collection is not execution.
Work-stage SDK commit: `2d87926c0903fb9b130c8ca6fa8129d978168200`.

Deployment preflight found SDK initialization logs on stdout before the Speech
capability JSON. Startup now parses one explicit capability-result prefix (same
pattern as its existing runtime probe), retaining nonzero exit and unavailable
capability failures. This is included in the Work Host commit, not a model delay
workaround. Existing untracked Demo output is preserved using the supported
AllowDirtyProject startup baseline; no user artifact is cleaned or committed.
