# D109 — Stage, module and acceptance-document synchronization

> Date: 2026-08-12
> Record type: frozen Tier-0 documentation/governance audit
> Decision: D-075
> Mutable current state: [STATUS.md](STATUS.md)

## 1. Request and result

The user asked for one unambiguous view of project stages, completed and incomplete modules, future critical nodes, and a synchronization of all current Live Voice documents so later work does not inherit conflicting rules.

The documentation model is now:

- `S0`–`S9`: sequential project stages;
- `A0`–`A3`: Alpha critical nodes;
- P1/P2/P3alpha/Shared-X: persistent capability tracks;
- AIO/SR/SS, RM/CR/II/AB, TC/ED/VB: modules;
- `*-A/*-B/*-C`: module work packages;
- `W1/W2/W3/W4`: historical delivery/order windows only.

This change does not alter implementation, roll back W2 acceptance, repeat the W3 migration or claim Alpha completion. Current results and gaps remain in STATUS.

## 2. Conflicts found

1. P1/P2/P3alpha were sometimes called architecture phases and sometimes treated as sequential delivery stages.
2. `W3` referred both to the develop rebaseline and to the first historical Alpha window; `W3/W4` was easy to misread as a current calendar promise or active queue.
3. W2 and Alpha shared `INTEGRATED_SHOWCASE.md`, although Alpha acceptance contains additional platform lifecycle, structured Task API, privacy, measurement and joint-load requirements.
4. The runbook always routed cumulative validation through the W2 acceptance/showcase and still required separate approval for both commit and push, conflicting with D-074.
5. STATUS contained a long Gate-era attempt timeline and evidence list that obscured the current stage, while the retired evidence Gate could be confused with the still-valid Architecture Contract Gate and Product Composition Gate 0.
6. Several current headers/routes cited D-053 or the historical fixed parallel window as the active process even though D-074 had superseded the review cadence and made D-060/D-062 conditional on an active packet.

## 3. Resolution

- D-075 freezes the four-layer vocabulary, S0–S9 stage sequence and A0–A3 Alpha entry/exit nodes.
- STATUS was reduced to a current resume capsule, stage dashboard, module dashboard, Alpha node exits, current constraints, policy and grouped history routes. Detailed failed attempts remain intact in D90–D108 and Git history.
- W2 remains bound to `INTEGRATED_DEMO_ACCEPTANCE.md + INTEGRATED_SHOWCASE.md`.
- Alpha is now bound to `ALPHA_ACCEPTANCE.md + ALPHA_SHOWCASE.md`; the new script covers platform lifecycle, P1 measurement reference, P2 slow-load behavior, structured and natural-language P3alpha, joint concurrency, privacy/trace and cleanup.
- The roadmap now owns stable stage/node exits and explicitly distinguishes tracks/modules/work packages/windows.
- The runbook requires selecting exactly one milestone contract, routes Alpha through A2/A3 and reflects coherent local commits plus separately approved remote updates.
- The ACG and frozen package matrix received interpretation notes only; their technical contract/package content was not rewritten.
- Frozen solution, execution packets, review records and evidence were not rewritten. Their old terminology is historical and is interpreted through D-075/current routes.

## 4. Synchronized current documents

| Document | Synchronized responsibility |
|---|---|
| root `AGENTS.md` | Bootstrap execution vocabulary and packet fields |
| `README.md` | Routes stage/module work and milestone-specific showcase reading |
| `DOCUMENTATION_RULES.md` | Authority/anti-duplication rules and exact terminology |
| `STATUS.md` | Sole mutable stage, node, module coverage, constraints and next actions |
| `decisions/DECISIONS.md` | D-075 accepted rationale and re-evaluation conditions |
| `architecture/ARCHITECTURE_CONTRACT_GATE_V1.md` | Non-semantic terminology note for historical Phase/Week references |
| `roadmap/POST_V0_DELIVERY_ROADMAP.md` | Stable S0–S9/A0–A3 definitions and exit criteria |
| `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md` | Historical-window-to-current-stage interpretation only |
| `validation/INTEGRATED_DEMO_ACCEPTANCE.md` | Explicit S3/W2-only scope and D-074 review authority |
| `validation/ALPHA_ACCEPTANCE.md` | S5–S8 entry/exit and Alpha-specific A3 route |
| `demo/INTEGRATED_SHOWCASE.md` | W2-only human journey |
| `demo/ALPHA_SHOWCASE.md` | Alpha-only A3 human journey |
| `runbooks/E2E_RUNBOOK.md` | Exact milestone selection, A2/A3 sequencing and current Git policy |
| `scripts/live_voice/w2_rehearsal/README.md` | W2-only diagnostic boundary; no Alpha closure credit |

## 5. Completion and non-completion judgment

- Completed and preserved: S0 V0, S1 foundations, S2 bounded D-031, S3 W2 product acceptance and S4 develop rebaseline.
- Current: S5/A0 Alpha baseline and source-level gap freeze.
- Not complete: every Alpha module remains `PARTIAL`; S6/A1, S7/A2 and S8/A3 remain open.
- Outside current scope: S9 full P3/D1/D2, production authentication, broad browser/mobile/PWA, public release and operational hardening.

The module dashboard deliberately records both the highest proven milestone and the remaining Alpha delta. This prevents “implemented”, “W2 passed” or “foundation closed” from being interpreted as “Alpha closed”.

## 6. Verification

The documentation batch passed:

- `git diff --check`;
- local-link resolution across 70 Markdown files under `live-voice/` plus the W2 diagnostics README;
- `git ls-files -- docs/zh/live-voice/**` returned no tracked duplicate;
- W2/Alpha route scans found no Alpha→W2 showcase or W2→Alpha acceptance crossover;
- the active runbook/status/acceptance scan found no obsolete combined commit/push approval wording;
- cold review of the complete documentation diff against the user request, root rules, D-071–D-075 and the documentation authority map.

The only diagnostic output was Git's existing Windows LF→CRLF working-copy warning; it is not a diff-check failure and no bulk line-ending rewrite was performed.

This record is documentation evidence only. No code suite, Provider, browser, device, Executor, Alpha automated matrix or human product acceptance is claimed.
