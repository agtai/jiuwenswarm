# Live Voice Latency Experiment Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one complete, source-bound English catalog of all current
Live Voice latency experiments, verify the private run archive, and synchronize
the canonical documentation across every writable experiment branch.

**Architecture:** A dated repository catalog owns the cross-experiment reading
route, the existing optimization inventory owns headroom and next decisions,
and immutable branch-bound result documents retain detailed exact-source
evidence. A standard record template governs future experiments, while the
outside-Git archive README binds raw artifacts without exposing private
configuration.

**Tech Stack:** Markdown, Git worktrees, `rg`, `find`, `sha256sum`, shell
validation, existing JiuwenSwarm latency JSON/JSONL reports.

**Spec:**
`live-voice/roadmap/LATENCY_EXPERIMENT_DOCUMENTATION_SYSTEM_DESIGN_2026-08-22.md`

## Global Constraints

- Write canonical documentation in English; do not rewrite frozen historical
  evidence solely for formatting.
- Label every numeric claim `MEASURED`, `DERIVED`, `ESTIMATED`, `CONTROLLED`,
  `UNKNOWN` or `REPORTED_EXTERNAL`.
- Classify every total as physical full experience, Browser-clock code E2E,
  controlled round total, component total or projected perceived latency.
- Never call deterministic, Provider-only or component timings physical E2E.
- Keep invalid, failed, superseded and lost runs visible.
- Do not copy credentials, endpoints, device identifiers, raw audio or
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/current.env` into Git.
- Preserve the pre-existing dirty files in `0812_live_voice_w3_renan`.
- Do not modify detached/reference worktrees or remote-tracking refs.
- No merge, rebase, cherry-pick, push or other remote-ref update belongs to this
  plan.

---

### Task 1: Freeze the evidence and branch worksheet

**Files:**

- Read:
  `live-voice/roadmap/LATENCY_EXPERIMENT_DOCUMENTATION_SYSTEM_DESIGN_2026-08-22.md`
- Read: branch-bound evidence named in Task 2
- Read: `/home/renan/openJiuwen-ai/live-voice-latency-runs/README.md`
- Read: `/mnt/c/Users/admin/Documents/hongxing optimization/WRAP_UP_HONGXING_LATENCY_FINDINGS_2026-08-21.md`
- Modify: none

**Interfaces:**

- Consumes: live branches, exact-source result documents and private artifact
  tree.
- Produces: a verified in-memory worksheet used by Tasks 2 and 4; no new
  authority file.

- [x] **Step 1: Confirm all writable branch heads and dirty state**

Run `git status --short --branch` and `git rev-parse HEAD` in:

```text
/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-w3
/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-p2-bounded-pull
/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-vad-eot-causal
/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/tts-provider-connection-reuse
/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/latency-checkpoint-accepted-optimizations
/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-eot-stt-overlap
/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-stable-sentence-agent-tts
```

Expected: only the main worktree has the already-recorded unrelated dirty
files; all experiment-owner worktrees are clean.

- [x] **Step 2: Reconcile the exact experiment source records**

Read these complete owner records:

```text
0812_live_voice_w3_renan:live-voice/evidence/LATENCY_EXPERIMENTS_2026-08-20.md
latency/p2-bounded-pull-b:live-voice/evidence/P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md
latency/vad-eot-causal-benchmark:live-voice/evidence/VAD_EOT_CAUSAL_RESULT_2026-08-21.md
latency/eot-stt-settlement-overlap:live-voice/evidence/TTS_FIRST_AUDIO_CAUSAL_RESULT_2026-08-21.md
latency/tts-provider-connection-reuse:live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md
latency_checkpoint_accepted_optimizations:live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md
latency/eot-stt-settlement-overlap:live-voice/evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md
latency/stable-sentence-agent-tts:live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_CAUSAL_RESULT_2026-08-21.md
```

Expected: exact branches, commits, run IDs, attempt counts, result tables,
boundaries, limitations and decisions are extracted without pooling clocks.

- [x] **Step 3: Inventory every private run artifact**

Run:

```bash
find /home/renan/openJiuwen-ai/live-voice-latency-runs \
  -type f ! -name current.env -printf '%p|%s\n' | sort
```

Then compute SHA-256 for every credited report and every artifact already bound
by an owner result. Never read or hash-print `current.env`.

- [x] **Step 4: Record discrepancies before writing**

The worksheet must explicitly retain:

- EOT final credited raw report lost from `/tmp`;
- stable-sentence credited `*-v2` artifacts and superseded unversioned pilots;
- P2 externally reported approximately 46% improvement without local raw
  binding and with failed TTS authorization;
- preliminary physical A–G run manifest/input mismatch;
- failed/superseded VAD, TTS ACK, connection-reuse and stable-sentence pilots.

Expected: no missing fact is silently converted into an estimate.

### Task 2: Create the canonical experiment catalog

**Files:**

- Create:
  `live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md`
- Read: Task 1 owner evidence
- Read:
  `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`

**Interfaces:**

- Consumes: the Task 1 worksheet and truth taxonomy from the design.
- Produces: the canonical `LVL-00` through `LVL-08` cross-experiment reading
  route used by STATUS, REFERENCE_INDEX, the inventory and future reviewers.

- [x] **Step 1: Write the global catalog header and comparison rules**

Include purpose, non-authority boundary, evidence hierarchy, truth-label table,
total-latency table and the Gate A/B/C completion ladder. State that failed
workflow latency receives no optimization credit.

- [x] **Step 2: Add the branch and experiment indexes**

The branch table must distinguish writable documentation branches from
immutable reference/detached worktrees. The experiment table must include
`LVL-00` through `LVL-08`, status, owner, lane, source, start/end boundary,
headline latency, total class, artifact state and next gate.

- [x] **Step 3: Add LVL-00 physical diagnostic details**

Preserve all A–G Browser-clock rows from
`LATENCY_EXPERIMENTS_2026-08-20.md`, including:

- `EOT → confirmed ACK`: 9,832 to 25,234 ms;
- `Capture ready → confirmed ACK`: 15,352 to 32,512 ms;
- actual Windows Chrome/WSL/human-microphone path;
- dirty source, incompatible manifest and missing formal population;
- semantic failures F/G and excluded turns.

Label these values `MEASURED` on one Browser clock and
`PRELIMINARY_DIAGNOSTIC`, not an accepted baseline.

- [x] **Step 4: Add LVL-01/LVL-01C P2 details**

Include the 10/50/100 A1/B/A2 RPC and p50/p95 tables, exact sources and run
IDs, 15/15 outcomes, zero forbidden effects and component-only boundary.
Separate the causal candidate result from Hongxing's product episode:
`REPORTED_EXTERNAL` approximately 46%, followed by
`SPEECH_OPERATION_NOT_AUTHORIZED`, failed retry and refresh. Explain the
unobserved final item inside `notification_batch` and the atomic ordered repair
gate.

- [x] **Step 5: Add LVL-02 through LVL-04 component experiments**

For fixed VAD, include 20/20 controls, 15/20 candidates, 285–412 ms successful
case headroom and all 1000 ms pause failures. For TTS ACK decoupling, include
0/250/750/1100 ms outcome accounting, first-source p50/p95 and settlement
limitation. For connection reuse, include cold/warm first-PCM and completion,
0/3 warm reuse and the +57.8 ms warm first-PCM regression.

- [x] **Step 6: Add LVL-05 through LVL-08**

Include:

- checkpoint W1/W2/W3 A1/B/A2 stage table and controlled totals
  8,000→6,985 ms, 14,900→10,240 ms and 17,150→8,580 ms;
- EOT/STT largest removable-gap p50 0.885 ms and fraction 0.015;
- stable-sentence 177.2 ms p50 / 425.3 ms p95 projected gain and failed
  materiality gates;
- Semantic VAD as specified but not run, with zero numeric credit.

The checkpoint totals must be labeled `CONTROLLED_ROUND_TOTAL`, never physical
E2E.

- [x] **Step 7: Add the artifact and next-decision routes**

For every experiment, name the exact owner evidence and private artifact state.
End with the current order: P2 observer repair and deployed Gate C alongside
the no-Chrome Semantic VAD screen, followed by a physical waterfall decision.

- [x] **Step 8: Verify the new catalog**

Run:

```bash
git diff --check -- live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md
rg -n 'MEASURED|DERIVED|ESTIMATED|UNKNOWN|CONTROLLED|REPORTED_EXTERNAL' \
  live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md
rg -n 'LVL-0[0-8]|LVL-01C' \
  live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md
```

Expected: all IDs and truth classes are present and `git diff --check` exits 0.

### Task 3: Add the uniform future experiment template

**Files:**

- Create: `live-voice/evidence/LATENCY_EXPERIMENT_RECORD_TEMPLATE.md`

**Interfaces:**

- Consumes: catalog taxonomy and repository evidence rules.
- Produces: one copyable contract for every future latency experiment.

- [x] **Step 1: Write required metadata and credit fields**

Require experiment ID, date, status, optimization flag, branch, exact source,
Agent-Core source, dirty state, environment, Provider/model, run IDs, corpus,
input path, sample count, warm/cold policy, start/end boundary, truth label,
total class and artifact state.

- [x] **Step 2: Write method, results and integrity sections**

Require hypothesis, mechanism, one changed variable, lane, A1/B/A2 role,
stage-by-stage p50/p95, total table, success/failure denominator, semantic
integrity, forbidden effects, regressions and downstream wait displacement.

- [x] **Step 3: Write artifact, decision and reproduction sections**

Require private artifact path, SHA-256, retention state, exact command,
decision rationale, limitations, next gate and reviewer evidence. Include
explicit `NOT APPLICABLE`, `UNKNOWN` and `NOT RETAINED` rules.

- [x] **Step 4: Check the template for placeholders masquerading as facts**

The template may use bracketed instructional fields, but it must not contain
unqualified claims, default acceptance or implied physical E2E credit.

### Task 4: Rebuild the private artifact ledger

**Files:**

- Modify: `/home/renan/openJiuwen-ai/live-voice-latency-runs/README.md`

**Interfaces:**

- Consumes: Task 1 file inventory and Task 2 experiment IDs.
- Produces: private artifact-to-experiment binding used for re-reduction and
  forensic review.

- [x] **Step 1: Preserve archive privacy and retention rules**

Keep the prohibition on `/tmp`, Git inclusion and `current.env` disclosure.
Define every artifact state from the design.

- [x] **Step 2: Add one ledger section per experiment**

Map all existing groups:

```text
38d09aefe/
edbee4d3d/
ca07a8dd5/
p2-causal/
vad-eot/
tts-first-audio/
tts-provider-connection/
accepted-checkpoint-20260821/
accepted-checkpoint-20260821-v2/
eot-stt-a1-materiality-bdd57bb6d.json
stable-sentence-screen-20260821/
```

Every group gets experiment ID, source/run IDs, credited/superseded role,
artifact completeness and owning evidence.

- [x] **Step 3: Add fresh hashes for credited surviving artifacts**

Use `sha256sum` on the exact paths and copy only digest, relative private path
and size. Mark the credited EOT final report `LOST`; do not substitute its
earlier diagnostic raw file.

- [x] **Step 4: Cross-check archive coverage**

Run a sorted `find` excluding `current.env` and compare every top-level group
against a README heading or table row. Expected: no artifact group is silently
uncataloged.

### Task 5: Synchronize current documentation authorities

**Files:**

- Modify: `live-voice/STATUS.md`
- Modify: `live-voice/REFERENCE_INDEX.md`
- Modify: `live-voice/runbooks/E2E_RUNBOOK.md`
- Modify:
  `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`

**Interfaces:**

- Consumes: canonical catalog and current documentation authority map.
- Produces: one stable reading route without duplicating mutable current state.

- [x] **Step 1: Update STATUS latency facts without changing product priority**

In the Observability/latency capability row and tracked-latency paragraph,
record:

- P2 causal component success but failed deployed TTS authorization gate;
- TTS ACK first-audio component acceptance;
- rejected fixed VAD and connection reuse;
- stopped EOT/STT and stable-sentence screens;
- next latency dependency: P2 observer repair/deployed Gate C and Semantic VAD
  screen.

Keep the product-truth repair packet as the current highest product priority.

- [x] **Step 2: Add the conditional reference route**

Add one `REFERENCE_INDEX.md` row directing latency history, reproduction and
forensics to the catalog first, then only the implicated branch-bound evidence
and runbook section.

- [x] **Step 3: Link the runbook recording contract**

In sections 7.6 and 7.7, link to the catalog/template for evidence recording.
Do not move commands or duplicate result tables into the runbook.

- [x] **Step 4: Narrow the optimization inventory to its owning role**

Add the catalog as the complete experiment-history source. Retain decision,
headroom and execution tables; remove only duplicated prose that would create
two competing run ledgers.

- [x] **Step 5: Validate documentation structure and links**

Run `git diff --check`, verify every changed local Markdown link resolves and
confirm `git ls-files docs/zh/live-voice` is empty.

### Task 6: Review and commit the canonical main-branch documentation

**Files:**

- All files created or modified by Tasks 2, 3 and 5
- Exclude: every pre-existing dirty/untracked main-worktree file not named by
  this plan

**Interfaces:**

- Consumes: completed canonical documents.
- Produces: one reviewable local documentation commit on
  `0812_live_voice_w3_renan`.

- [x] **Step 1: Inspect the exact scoped diff**

Run `git status --short`, `git diff --check`, `git diff --stat` and:

```bash
git diff -- \
  live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md \
  live-voice/evidence/LATENCY_EXPERIMENT_RECORD_TEMPLATE.md \
  live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md \
  live-voice/STATUS.md \
  live-voice/REFERENCE_INDEX.md \
  live-voice/runbooks/E2E_RUNBOOK.md
```

Confirm no product source, lockfile or pre-existing untracked document is
staged.

- [x] **Step 2: Run an evidence consistency review**

Check every catalog headline number against its owner document and every
branch/source/run ID against Git or the retained report. Any mismatch is fixed
before commit.

- [x] **Step 3: Commit only the canonical documentation**

```bash
git add -- \
  live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md \
  live-voice/evidence/LATENCY_EXPERIMENT_RECORD_TEMPLATE.md \
  live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md \
  live-voice/STATUS.md \
  live-voice/REFERENCE_INDEX.md \
  live-voice/runbooks/E2E_RUNBOOK.md
git commit -m "docs(live-voice): catalog latency experiment evidence"
```

Expected: one documentation-only commit; unrelated dirty files remain unstaged.

### Task 7: Synchronize the canonical files across experiment branches

**Files:**

- Synchronize on six experiment-owner branches:
  `live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md`
- Synchronize on six experiment-owner branches:
  `live-voice/evidence/LATENCY_EXPERIMENT_RECORD_TEMPLATE.md`
- Synchronize on six experiment-owner branches:
  `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`
- Modify no branch-bound result document.

**Interfaces:**

- Consumes: exact canonical file bytes committed in Task 6.
- Produces: identical handoff route on all seven writable branches.

- [x] **Step 1: Recheck every target worktree before writing**

Run `git status --short --branch` and stop on an unexpected writer/change.

- [x] **Step 2: Apply the exact canonical content**

Use `apply_patch` for each target worktree. Do not cherry-pick because the main
commit also updates mutable authorities that must not overwrite branch-specific
STATUS state.

- [x] **Step 3: Verify each branch diff**

For every branch, require `git diff --check` and confirm the diff contains only
the catalog, template and inventory.

- [x] **Step 4: Commit each owner branch separately**

Use the same message:

```text
docs(live-voice): synchronize latency experiment catalog
```

No push is authorized.

### Task 8: Final cross-branch and archive verification

**Files:**

- Verify all canonical files and `/home/renan/openJiuwen-ai/live-voice-latency-runs/README.md`

**Interfaces:**

- Consumes: Tasks 4, 6 and 7 outputs.
- Produces: final exact hashes, commit map, status map and documented exclusions.

- [x] **Step 1: Compare canonical hashes**

Run `sha256sum` for the catalog, template and inventory in all seven writable
worktrees. Expected: one digest per filename across every branch.

- [x] **Step 2: Verify commits and changed files**

Run `git show --check --stat` and `git diff-tree --name-only` for every new
commit. Expected: documentation-only scope.

- [x] **Step 3: Verify final worktree states**

Expected: six experiment-owner branches clean; the main branch retains only the
same unrelated dirty/untracked files present before this plan.

- [x] **Step 4: Report the handoff**

Report:

- catalog, template, inventory and private archive paths;
- the canonical SHA-256 values;
- every local branch commit hash/message;
- verification performed;
- lost, external-only and unverified artifacts;
- explicit statement that no code, reference branch or remote ref changed.
