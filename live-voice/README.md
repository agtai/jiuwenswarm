# JiuwenSwarm Live Voice router

Root `AGENTS.md` owns work and Git authority. Start with this router and
[STATUS](STATUS.md)'s judgement/current packet; read other status sections only
for the relevant capability or planning scope. Choose a primary route below and
add only sections required by touched boundaries. Reuse unchanged guidance already
read in this session; links are conditional, not a recursive reading list.

## Task routing

| Task | Read after STATUS |
|---|---|
| Current implementation packet | STATUS `Current execution packet`; affected source/tests; only the implicated contract/evidence and applicable root `TESTING.md` risk sections |
| Another capability/module | That capability row and dependency route in STATUS; affected source/tests; only the relevant accepted design/ACG/decision sections |
| Complete-project planning | STATUS completion boundaries, full capability matrix and dependency route; heading `D-084` in [decisions](decisions/DECISIONS.md); stable capability/contract sections (§§2, 4–5) of the [design snapshot](architecture/FULL_SOLUTION_2026-07-30.md) |
| Rehearsal or candidate/product acceptance | [Human journey](demo/PRODUCT_READINESS_SHOWCASE.md), which separates rehearsal from full candidate acceptance; only the required [runbook](runbooks/E2E_RUNBOOK.md) startup/diagnosis/cleanup sections and applicable acceptance contract |
| Documentation change | [Documentation rules](DOCUMENTATION_RULES.md), root `TESTING.md` documentation-only section and only the authorities changed by the edit |
| Architecture/authority/protocol/security/durability change | Exact ACG and governing decision sections; full design only if the long-term boundary itself changes or is ambiguous |
| Git/review/parallel work | Root `AGENTS.md`, applicable root `TESTING.md` sections and only the active packet named by STATUS |
| LiveVoice slimming / AgentCore downshift | [Slimming master plan](roadmap/LIVEVOICE_SLIMMING_MASTER_PLAN.md) is the single entry; open its linked reviews only for the package being executed. Slimming is not activated until the trigger decision in its §1.3 is recorded. The behaviour-preserving floor is about 135–140K lines; the [design-simplification plan](LIVEVOICE_DESIGN_SIMPLIFICATION_PLAN_2026-09-07.md) is the semantic-change path to 60–65K and needs its own authorization. For "what does this LiveVoice module correspond to in Hermes" read the [official Hermes voice comparison](reviews/OPENJIUWEN_LIVEVOICE_OFFICIAL_HERMES_VOICE_COMPARISON_2026-09-06.md). Route decision D-121 (2026-09-08): rewrite behind the two seams per the [target architecture](LIVEVOICE_TARGET_ARCHITECTURE_2026-09-07.md), package sequence in its §10 |
| Historical/migration/forensic work | One route from the conditional [reference index](REFERENCE_INDEX.md); never use historical priority/status as the current queue |

## Section rules

- In `DECISIONS.md`, read one required `## D-nnn` section through the next
  decision heading.
- Read complete acceptance only to decide a candidate/boundary. During
  implementation, read only bullets owned by the changed capability.
- Read showcase and physical runbook material only for runtime preparation or
  product acceptance.
- Read a complete historical packet/review only for a concrete regression,
  disputed invariant or forensic question.
- Closed work, old run counts and superseded instructions belong in conditional
  history/evidence. They are not a resume checklist or a current backlog.
- If Git/source/tests and prose disagree, Git is implementation fact. Repair
  STATUS or the owning authority instead of copying the conflict elsewhere.

Credentials, Provider/model configuration, project registration, browser/device
state, runtime data and network availability are machine-private and are not
restored by Git.
