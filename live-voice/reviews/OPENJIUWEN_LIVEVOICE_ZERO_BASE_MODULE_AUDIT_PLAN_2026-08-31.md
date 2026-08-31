# LiveVoice zero-baseline module audit execution plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` for tracked deliverables and
> `superpowers:dispatching-parallel-agents` only for non-overlapping read-only
> evidence lanes. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the LiveVoice slimming conclusion from executable flows and
existing JiuwenSwarm/AgentCore capabilities, then produce a complete,
reproducible module and LOC disposition without migrating code.

**Architecture:** The moving product worktree is read-only implementation fact;
the isolated preparation branch owns only audit documents. Main is the sole
classification and Git owner. Parallel agents may inspect separate evidence
domains and write separate ignored reports, but may not edit tracked files,
commit, change branches or decide cross-domain ownership.

**Tech stack:** Git worktrees, PowerShell, Python AST inspection, TypeScript
export/import discovery, physical line accounting, Markdown, JiuwenSwarm,
OpenJiuwen AgentCore, and pinned Hermes Live Voice source.

**Spec:**
[`OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md`](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md)
§9.

## Global constraints

- Product worktree `C:\Users\admin\Desktop\live voice hx` remains read-only.
- Audit worktree
  `C:\Users\admin\Desktop\live voice hx-agentcore-hermes-prep` is the only
  tracked documentation writer.
- Main is the only Integration Owner and the only Git writer.
- Hermes is pinned architecture evidence; no Hermes code or dependency is
  copied.
- Installed AgentCore, local Scope/A1/A2 candidates and later local PR
  candidates are reported as distinct facts.
- A required capability is not evidence that LiveVoice must implement it.
- Directory placement and file size do not establish authority.
- Durable conclusions use capability, responsibility, contract and symbol
  names, not source line numbers.
- No migration, data write, product-path activation, deletion, push, PR or
  remote-ref update is in scope.
- Documentation is Tier 0 under root `TESTING.md`; findings do not grant product
  or migration credit.

---

### Task 1: Freeze the reproducible accounting boundary

**Files:**

- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md`
- Create ignored audit manifests under this plan's SDD workspace
- Read only: product worktree and its Git history

**Interfaces:**

- Consumes: exact product HEAD, tracked paths, current feature-branch history,
  existing 152-path manifest and prior LOC claims.
- Produces: an exclusive file/symbol accounting manifest and independently
  reproducible totals for production, tests, fixtures/support, scripts and
  documentation/evidence.

- [ ] Record exact product, preparation, Hermes and AgentCore baselines and
  distinguish moving product truth from dated audit evidence.
- [ ] Derive the LiveVoice footprint from both dedicated paths and attributable
  shared-file changes; do not rely on filename matching alone.
- [ ] Count physical LOC using one documented rule for text, blanks, generated
  files, dependencies and shared files.
- [ ] Prove zero missing and zero duplicate production paths; place genuinely
  mixed files in a symbol-attribution queue.
- [ ] Reconcile or retire every previous aggregate LOC claim.

### Task 2: Reconstruct the eight executable flows

**Files:**

- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_HERMES_MODULE_ARCHITECTURE_ZH_2026-08-31.md`
- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md`
- Read only: current product source and owned tests

**Interfaces:**

- Consumes: Task 1 accounting manifest.
- Produces: entrypoint-to-effect call chains and the actual owner of each state
  transition, authority check, persistence mutation and external effect.

- [ ] Trace startup/configuration/composition/channel attachment.
- [ ] Trace capture/recognition/commit and conversation/Agent/history.
- [ ] Trace synthesis/playout/ACK/interruption/presentation.
- [ ] Trace task intent/confirmation/command/admission and Agent/Tool execution.
- [ ] Trace progress/result/notification, durability/restart/reconnect/cursor,
  and authority/observability/failure/cleanup.
- [ ] Mark dead, fallback, default-off, validation-only and duplicate lanes
  separately from the active product route.

### Task 3: Re-audit Hermes by equivalent responsibility

**Files:**

- Modify the two Task 2 review documents
- Read only: pinned Hermes Live Voice source, tests and architecture documents

**Interfaces:**

- Consumes: Task 2 responsibility groups.
- Produces: `analogue`, `partial analogue`, `different owner` or `no analogue`
  for every current LiveVoice responsibility.

- [ ] Inventory Hermes browser SDK, Web demo, Dashboard plugin, inbound
  Adapters, gateway session, realtime Provider Adapters, task supervisor,
  Hermes Agent Adapter, stores, protocol and terminal surface.
- [ ] Trace Hermes browser and terminal flows instead of comparing names only.
- [ ] Compare like-for-like LOC layers: runtime/core, client/channel,
  host/plugin, task/durability, tests and documentation.
- [ ] Explain intentional JiuwenSwarm differences without treating parity or
  absence as a verdict.

### Task 4: Prove JiuwenSwarm and AgentCore reuse before allowing new code

**Files:**

- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md`
- Modify the two Task 2 review documents
- Read only: current JiuwenSwarm outside LiveVoice, installed AgentCore, local
  Scope/A1/A2 candidates, later AgentCore PR candidates and conformance tests

**Interfaces:**

- Consumes: Tasks 2–3 responsibility groups.
- Produces: public-contract evidence and one exclusive disposition for every
  responsibility and mixed-file symbol group.

- [ ] Audit JiuwenSwarm channels, Web/TUI/ACP/A2A/IM infrastructure, Chat/E2A,
  Agent/Harness, Session History, project and product services before accepting
  a LiveVoice implementation.
- [ ] Audit installed and local-candidate AgentCore Agent/Tool/Task/execution,
  command/result, event/outbox, checkpoint, effect and cursor contracts.
- [ ] For `DIRECT_REUSE`, name the callable public boundary and prove no second
  authority remains.
- [ ] For `ADAPT_REUSE`, bound the Adapter translation/fence and prove it owns
  no generic state machine.
- [ ] For `AGENTCORE_PR`, prove generic value, missing public contract, smallest
  upstream owner and required conformance oracle.
- [ ] For keep/split/retire outcomes, state the product invariant, target owner,
  dependencies, risk and retirement gate.

### Task 5: Converge the complete module and LOC disposition

**Files:**

- Modify:
  `live-voice/reviews/OPENJIUWEN_LIVEVOICE_SLIMMING_FINAL_REVIEW_2026-08-25.md`
- Modify all review documents named by Tasks 1–4 only where factual
  reconciliation requires it

**Interfaces:**

- Consumes: complete manifests and disposition evidence.
- Produces: the Chinese architecture view, exhaustive module matrix, verified
  LOC decomposition, minimal future LiveVoice allowlist, AgentCore PR list and
  explicit consolidation/retirement list.

- [ ] Ensure every production path is covered and every mixed file has
  responsibility-level attribution.
- [ ] Ensure production LOC buckets sum exactly to the production total and
  tests/docs/scripts are reported separately.
- [ ] Ensure every module row includes current role, covered flow, Hermes
  relation, JiuwenSwarm evidence, AgentCore evidence, disposition, target owner,
  dependency and confidence/open question.
- [ ] Replace earlier misleading Core/Web/channel and aggregate LOC statements.
- [ ] Keep current implementation fact separate from target architecture and
  future migration prerequisites.

### Task 6: Independent verification and local documentation commit

**Files:**

- Modify only the Task 1–5 documents to resolve verified findings
- Write review packages and reviewer reports only to the ignored SDD workspace

**Interfaces:**

- Consumes: Task 5 candidate documentation.
- Produces: independently reviewed, locally committed preparation evidence.

- [ ] Run manifest set equality, bucket-sum and cross-document contradiction
  checks.
- [ ] Run `git diff --check`, changed-local-link verification, duplicate-doc
  check and authority-map review.
- [ ] Perform an independent architecture/reuse review against the complete
  diff and supporting manifests.
- [ ] Resolve every Critical/Important finding or record an explicit ruling
  after the bounded review loop.
- [ ] Commit the coherent documentation batch locally and report exact commit,
  status, exclusions and every ruling; do not push.
