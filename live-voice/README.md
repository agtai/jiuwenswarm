# JiuwenSwarm Live Voice router

Root [AGENTS.md](../AGENTS.md) owns work and Git authority. For a Live Voice task,
read [Project judgement](STATUS.md#project-judgement) and
[Current execution packet](STATUS.md#current-execution-packet), then stop before
Completion boundaries unless wider scope is needed. Choose one route below;
linked history is conditional and does not activate work.

## Task routing

| Task | Read after STATUS |
|---|---|
| Local browser entry/link or environment reconstruction | [Local entry convention](runbooks/E2E_RUNBOOK.md#local-entry-origin), then the applicable startup section |
| SDK source and dependency preparation | [Pinned AgentCore source](runbooks/AGENTCORE_SOURCE.md) and the active execution record; source pinning is separate from deployment |
| Current repair or diagnosis | Affected source/tests and directory `AGENTS.md`; only the implicated contract/evidence and applicable root [TESTING.md](../TESTING.md) sections |
| Another capability/module | That capability row and dependency route in STATUS; affected source/tests; only the relevant accepted design/ACG/decision sections |
| Complete-project planning | STATUS completion boundaries, full capability matrix and dependency route; heading `D-084` in [decisions](decisions/DECISIONS.md); stable capability/contract sections (§§2, 4–5) of the [design snapshot](architecture/FULL_SOLUTION_2026-07-30.md) |
| Rehearsal or candidate/product acceptance | [Human journey](demo/PRODUCT_READINESS_SHOWCASE.md), which separates rehearsal from full candidate acceptance; only the required [runbook](runbooks/E2E_RUNBOOK.md) startup/diagnosis/cleanup sections and applicable acceptance contract |
| Documentation change | [Documentation rules](DOCUMENTATION_RULES.md), [documentation-only checks](../TESTING.md#documentation-only-verification) and only the authorities changed by the edit |
| Architecture/authority/protocol/security/durability change | Exact ACG and governing decision sections; full design only if the long-term boundary itself changes or is ambiguous |
| Git/review/parallel work | Root `AGENTS.md`, applicable root `TESTING.md` sections and only the active packet named by STATUS |
| Historical/migration/forensic work | One route from the conditional [reference index](REFERENCE_INDEX.md); never use historical priority/status as the current queue |

## Section rules

- In `DECISIONS.md`, read one required `## D-nnn` section through the next
  decision heading.
- Read complete acceptance only to decide a candidate/boundary. During
  implementation, read only bullets owned by the changed capability.
- Read showcase and physical runbook material only for runtime preparation or
  product acceptance.
- Read a historical packet/review only for a concrete regression, disputed
  invariant or forensic question; old run counts are not a resume checklist.
- If Git/source/tests and prose disagree, Git is implementation fact. Repair
  STATUS or the owning authority instead of copying the conflict elsewhere.
