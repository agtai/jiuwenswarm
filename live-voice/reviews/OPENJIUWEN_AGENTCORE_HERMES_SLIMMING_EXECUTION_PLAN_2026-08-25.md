# LiveVoice AgentCore/Hermes slimming preparation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` to
> execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Produce a complete, line-number-independent decision package that
explains every LiveVoice module, classifies AgentCore reuse, prepares generic
AgentCore PR candidates, and identifies the minimal future LiveVoice change
set without performing migration.

**Architecture:** Treat the moving `hx/0812_live_voice_w3` worktree as read-only
product fact, the isolated preparation branch as the analysis/evidence owner,
the local AgentCore branch as the PR-candidate owner, and the pinned Hermes
checkout as an architecture-only reference. Close inventory first, then
classification, candidate adjudication, PR preparation and final convergence;
no candidate implementation is integrated merely because it exists.

**Tech stack:** Git worktrees, Python 3.11 via locked `uv` environment,
PowerShell, Python AST inspection, Markdown decision records, JiuwenSwarm
LiveVoice, OpenJiuwen AgentCore, and a read-only Hermes Agent checkout.

**Spec:**
[`OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md`](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md)

## Global constraints

- Main is the sole Integration Owner and Git-history writer for the preparation
  branch.
- `C:\Users\admin\Desktop\live voice hx` remains read-only and clean while
  this preparation task runs.
- All tracked JiuwenSwarm findings live on
  `codex/livevoice-agentcore-hermes-prep` in
  `C:\Users\admin\Desktop\live voice hx-agentcore-hermes-prep`.
- Generic AgentCore candidates live only in
  `C:\Users\admin\Desktop\openjiuwen\agent-core-oj-g2-local-base` or later
  explicitly created AgentCore worktrees.
- Hermes at `C:\Users\admin\Desktop\hermes-agent-analysis-20260821` is
  read-only; no source is copied and no dependency is introduced.
- Long-lived mappings use files, symbols, contracts, capability IDs and module
  responsibilities, never source line numbers.
- No composition activation, dual write, data migration, canary, Store
  retirement, product-path change, remote-ref update or PR submission is in
  scope.
- The five isolated LiveVoice candidate commits and the ignored EVT-02 archive
  are evidence, not automatic integration inputs.
- Documentation work is Tier 0 under root `TESTING.md`; any later authority,
  durability or product implementation keeps its independently assigned risk.

---

### Task 1: Freeze reproducible inventories without freezing moving source truth

**Files:**

- Create:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md`
- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md`
- Read only: current LiveVoice, AgentCore and Hermes worktrees named above

**Interfaces:**

- Consumes: accepted scope, D-084/D-085, current STATUS capability matrix,
  stable design §§2, 4–5, the existing module code-fact audit, and the existing
  OpenJiuwen/Hermes audit.
- Produces: exact semantic-surface manifests and a disposition-row schema used
  by every later task.

- [x] Record the current observed Git heads and clean/dirty state in the scoped
  review as reproducibility evidence, explicitly stating that later batches
  must re-read the moving LiveVoice branch.
- [x] Enumerate tracked production files from backend, gateway, shared schema,
  frontend LiveVoice, composition panels/hooks, production launch/config and
  validation-script surfaces using `git ls-files` plus explicit path filters.
- [x] Enumerate matching unit/integration/frontend test and support groups
  separately; tests are oracle assets and are not counted as production
  modules.
- [x] Define one disposition row per production file with these fields:
  `Module`, `Capability domain`, `Responsibility`, `Why necessary`, `State or
  authority`, `AgentCore relation`, `Hermes relation`, `Size driver`, `Proposed
  disposition`, `Dependencies/evidence`, and `Confidence/open question`.
- [x] Verify set equality between the machine manifest and documented rows;
  record zero missing and zero duplicate production paths before closing the
  task.

### Task 2: Explain every backend, gateway and shared-contract module

**Files:**

- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md`
- Read only: `jiuwenswarm/server/live_voice`, `jiuwenswarm/gateway/live_voice`,
  shared LiveVoice schema, formal Agent adapter and their tests

**Interfaces:**

- Consumes: Task 1 manifest and row schema.
- Produces: backend/gateway/shared rows whose responsibilities and ownership
  are understandable without reading implementation bodies.

- [x] Extract module docstrings, public classes/functions, internal imports and
  direct AgentCore/JiuwenSwarm dependencies with read-only Python AST queries.
- [x] Group rows by Audio Edge, Speech, Realtime Media, Conversation Runtime,
  Interaction Intelligence, Agent Bridge, Task/Store, Executor/Durability,
  Voice–Task Bridge, Presentation, Composition, Observability and support.
- [x] For every row, distinguish product policy from generic task/execution/
  event/effect truth; do not infer ownership from directory placement alone.
- [x] Explain large modules by independent responsibility clusters and record
  consolidation/split candidates without prescribing a source-line rewrite.
- [x] Reconcile every backend/gateway row against the existing 15-domain code
  fact audit and record any stale, missing or contradicted prior finding.

### Task 3: Explain every frontend, production entry and validation-support module

**Files:**

- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md`
- Read only: frontend `features/live-voice`, LiveVoice panels/hooks, production
  profiles, launchers and LiveVoice validation scripts

**Interfaces:**

- Consumes: Task 1 manifest and backend ownership established by Task 2.
- Produces: frontend/entry/support rows, including which files are product
  owners, carriers, test assets, legacy lanes or retirement candidates.

- [x] Extract TypeScript/TSX exports, local LiveVoice imports and composition
  entrypoints using `rg` and existing build manifests.
- [x] Separate Audio/Media edge, Runtime replica, Task client/projection,
  Presentation/ACK, composition panel, diagnostics and legacy/demo lanes.
- [x] Explain why UI state is a verified replica or presentation fact rather
  than canonical Task/Event/Effect truth.
- [x] Classify launch/config/scripts as production owner, acceptance tooling,
  reusable oracle, historical runner or retirement candidate.
- [x] Reconcile all rows with current STATUS capability ownership and the
  existing retirement ledger.

### Task 4: Apply Hermes as an explanatory architecture mirror

**Files:**

- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md`
- Read only: pinned Hermes Voice/STT/TTS/gateway/desktop modules and tests

**Interfaces:**

- Consumes: Tasks 2–3 LiveVoice responsibility rows and the pinned Hermes
  architecture manifest.
- Produces: a Hermes relation for every LiveVoice production row and a
  capability-domain explanation of justified and unjustified complexity.

- [x] Revalidate the pinned Hermes checkout and the existing 16-file
  production/test focus manifests without fetching or modifying it.
- [x] Map Audio Edge/VAD, STT registry, TTS registry/chunker/consumer,
  generation/playout interruption, echo guard, platform adapter and
  Agent/session connection to LiveVoice responsibility groups.
- [x] Mark `analogue`, `partial analogue`, `different owner` or `no analogue`
  for every LiveVoice row; absence in Hermes is not by itself a deletion reason.
- [x] Record which LiveVoice complexity is required by scoped authority,
  committed input, durable task/effect/cursor truth, Web ACK and fail-closed
  recovery, and which complexity is duplication or historical layering.
- [x] Confirm no conclusion requests Hermes parity, copied code or dependency.

### Task 5: Close the AgentCore disposition map

**Files:**

- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md`
- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md`
- Read only: locked dependency, AgentCore public source, local AgentCore
  candidate branch and conformance tests

**Interfaces:**

- Consumes: Tasks 2–4 ownership findings and existing symbol map capability IDs.
- Produces: exactly one current classification for every relevant generic or
  product capability: direct reuse, Adapter reuse, AgentCore PR candidate, or
  LiveVoice-owned.

- [x] Re-read public AgentCore APIs for scope, Task query/command/result,
  execution admission/settlement, Agent/Tool launch, events/cursors,
  checkpoint/recovery and effects; internal imports do not count as reuse.
- [x] For direct reuse, name the public contract and prove LiveVoice adds no
  competing authority.
- [x] For Adapter reuse, state the minimum translation/fence and prove the
  Adapter owns no generic durable state machine.
- [x] For AgentCore PR candidates, state the generic non-Voice value, smallest
  existing AgentCore owner, missing public contract and required failing oracle.
- [x] For LiveVoice-owned rows, state the voice/product invariant that prevents
  downstream ownership.
- [x] Verify every module row references one capability disposition and every
  capability disposition has at least one owning or consuming module row.

### Task 6: Adjudicate all current prototypes and tests

**Files:**

- Create:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_PROTOTYPE_ADJUDICATION_2026-08-25.md`
- Modify:
  `live-voice/reviews/OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md`
- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md`
- Modify only if factual classification changes:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md`

**Interfaces:**

- Consumes: closed AgentCore and module dispositions.
- Produces: keep/minimize/move/discard decisions for all five candidate commits,
  their tests/packets and the ignored EVT-02 archive.

- [x] Review each candidate commit as a complete diff against its parent and
  identify reusable evidence separately from production code.
- [x] Specify the smallest future LiveVoice seam, if any; existing passing tests
  do not force retention.
- [x] Identify code and tests that belong in an AgentCore PR candidate and code
  that encodes LiveVoice policy.
- [x] Decide whether the EVT-02 archive remains discarded or supplies only a
  test oracle after event/cursor classification.
- [x] Verify the preparation branch is still not a wholesale merge candidate.

### Task 7: Prepare coherent local AgentCore PR candidates

**Files:**

- Create or modify only inside the isolated AgentCore repository after Task 5
  selects an `AgentCore PR candidate` row.
- Create:
  `live-voice/reviews/OPENJIUWEN_AGENTCORE_PR_PREPARATION_REVIEW_2026-08-25.md`

**Interfaces:**

- Consumes: selected AgentCore PR candidate rows and the existing local
  AgentCore commit stack.
- Produces: locally reviewable AgentCore commit series, test evidence and PR
  descriptions with no remote update.

- [x] Audit the existing AgentCore commits against selected rows; mark each
  retain, revise, split, squash-with-owner, or discard in the review before
  rewriting local history.
- [x] Split candidates by the smallest coherent AgentCore owner and shared
  contract so one PR does not couple unrelated scope, execution, event, cursor,
  checkpoint or effect changes.
- [ ] For each candidate, create a dedicated implementation plan containing
  exact source/tests, public signatures, red/green commands and compatibility
  checks before changing code.
- [ ] Implement and verify each candidate in its AgentCore worktree; exclude
  LiveVoice imports, voice policy, product identity heuristics and migration.
- [ ] Prepare local PR title/body, dependency order, test evidence, risk and
  exclusions; do not push or submit.

### Task 8: Converge the final preparation package

**Files:**

- Create:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_SLIMMING_FINAL_REVIEW_2026-08-25.md`
- Modify: scope, module disposition and symbol map only to resolve factual
  contradictions discovered during convergence

**Interfaces:**

- Consumes: all closed module, Hermes, AgentCore and prototype decisions.
- Produces: a minimal future LiveVoice allowlist, AgentCore PR list and explicit
  discard list that can be reviewed without reading the experimental ten
  thousand lines.

- [ ] Summarize direct reuse, Adapter reuse, AgentCore PR and LiveVoice-owned
  outcomes by capability, linking rather than duplicating detailed tables.
- [ ] List the only LiveVoice documents and separately accepted minimal seams
  eligible for later feature-branch integration.
- [ ] List every preparation file/commit excluded from wholesale integration.
- [ ] Verify production-file manifest coverage is complete, dispositions are
  exclusive, all local Markdown links resolve, `git diff --check` passes and
  `docs/zh/live-voice` has no tracked duplicate.
- [ ] Run risk-proportional tests for any retained code candidate, record exact
  source and distinguish passes, skips and unavailable physical evidence.
- [ ] Perform scoped diff review, commit each coherent documentation or PR
  candidate batch locally, and report hashes/status without updating a remote
  ref.
