# JiuwenSwarm Live Voice router

Root `AGENTS.md` owns Git authority. **Default Live Voice reading is this router
and the concise [STATUS](STATUS.md).** Then select one route below. Read linked
material only when needed for that task; do not recursively open every link.

## Task routing

| Task | Read after STATUS |
|---|---|
| Current implementation packet | STATUS `Current execution packet`; affected source/tests; only the implicated contract/evidence and applicable root `TESTING.md` risk sections |
| Another capability/module | That capability row and dependency route in STATUS; affected source/tests; only the relevant accepted design/ACG/decision sections |
| Complete-project planning | STATUS completion boundaries, full capability matrix and dependency route; heading `D-084` in [decisions](decisions/DECISIONS.md); stable capability/contract sections (§§2, 4–5) of the [design snapshot](architecture/FULL_SOLUTION_2026-07-30.md) |
| Candidate/product acceptance | Applicable acceptance contract; complete human journey; only required environment/start/cleanup sections of the runbook |
| Documentation change | [Documentation rules](DOCUMENTATION_RULES.md), root `TESTING.md` documentation-only section and only the authorities changed by the edit |
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
- Read a complete historical packet/review only for a concrete regression,
  disputed invariant or forensic question.
- Closed work, old run counts and superseded instructions belong in conditional
  history/evidence. They are not a resume checklist or a current backlog.
- If Git/source/tests and prose disagree, Git is implementation fact. Repair
  STATUS or the owning authority instead of copying the conflict elsewhere.

Credentials, Provider/model configuration, project registration, browser/device
state, runtime data and network availability are machine-private and are not
restored by Git.
