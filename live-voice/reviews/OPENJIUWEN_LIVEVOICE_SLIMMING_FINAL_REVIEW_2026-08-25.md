# OpenJiuwen LiveVoice slimming preparation convergence review — 2026-08-25

Status (corrected 2026-08-31): this is a preparation decision index. The earlier
Hermes explanation and the claim that every old disposition was converged are
superseded by the
[zero-baseline audit](OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md).
The current exclusive decisions are recorded in the
[228-row atomic responsibility manifest](OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md);
the older path register remains supporting source/caller/Hermes evidence rather
than an alternative disposition authority.
The AgentCore PR **design and replay packets** exist, but complete accepted PR
source/test/docs packages do not: PR 01–03 have local technical candidates,
PR 04–10 have preflight only, and historical PR09/PR10 facade implementations
must be reimplemented. This document grants no migration, deletion,
product-readiness or PR submission approval. `STATUS.md` remains the authority
for mutable project state.

Risk: Tier 0 documentation under root `TESTING.md`. Every later code boundary
retains its independently assigned risk and evidence requirements.

Current-baseline reconciliation (2026-08-31): the frozen product commit is
`59998e2c5724257bd410885b35e59e1b37027030`. The 152-path manifest still has
zero missing/duplicate/extra rows, but multiple Hermes and AgentCore
classifications required correction. Current dedicated production is 128 paths
and 159,210 physical LOC; 24 shared hosts add 4,054 attributable LiveVoice
symbol/segment lines and exclude 53,534 host-remainder lines, giving a current
attributable production footprint of 163,264 LOC. The `7bf704d7..39f4efa3`
delta changes four existing Channel paths and their tests for successor-capture
ACK/first-frame diagnostics; `39f4efa3..5b4d3e69` changes only
`live-voice/STATUS.md`; `5b4d3e69..59998e2c` changes one already inventoried
composition-registry path by net -1 physical LOC plus tests/status/plan. No
committed delta adds a production path, stable symbol or disposition class. The
corrected architecture is reflected in the
[Chinese module architecture view](OPENJIUWEN_LIVEVOICE_HERMES_MODULE_ARCHITECTURE_ZH_2026-08-31.md).
Atomic validation covers all 152 paths with 228 unique responsibility keys,
48 multi-responsibility paths, one canonical code per key, zero invalid stable
symbols and zero source-line locators. Independent mixed-boundary review is
`Critical 0 / Important 0 / Minor 10`; the ten remaining findings are disclosed
same-owner internal split debts, not completed refactors or LOC-removal credit.

## 1. Converged answer

The slimming target is not “merge the preparation branch” and is not “make
LiveVoice look like Hermes.” The selected result is:

1. call the existing public AgentCore Agent/Tool/Runner/DeepAgent/Harness
   boundary directly where it
   already owns the generic operation;
2. keep only thin JiuwenSwarm/LiveVoice translation and policy Adapters where
   AgentCore owns, or will own, the generic truth;
3. prepare ten dependency-ordered, separately reviewable AgentCore capability
   PRs for generic gaps instead of keeping those state machines in LiveVoice;
4. retain genuinely voice-, browser-, product- and Jiuwen-specific owners,
   while consolidating, splitting, re-homing or retiring their internal
   duplication after explicit Gates; and
5. keep every experimental implementation and the preparation branch itself
   out of the moving product branch unless a later packet selects and rewrites
   one minimal seam.

The detailed, stable decisions live in the
[Chinese module architecture view](OPENJIUWEN_LIVEVOICE_HERMES_MODULE_ARCHITECTURE_ZH_2026-08-31.md),
the
[symbol migration map](OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md),
the
[152-path module disposition](OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md),
the
[prototype adjudication](OPENJIUWEN_LIVEVOICE_PROTOTYPE_ADJUDICATION_2026-08-25.md)
and the
[AgentCore PR preparation review](OPENJIUWEN_AGENTCORE_PR_PREPARATION_REVIEW_2026-08-25.md).

## 2. AgentCore outcome by capability

### 2.1 Direct reuse available now

The current direct AgentCore reuse is the public Agent/Tool/Runner/DeepAgent/
Harness invocation boundary: `Runner.run_agent[_streaming]`, public Agent/Tool
contracts, `create_deep_agent`, and DeepAgent interaction methods. The dominant
Jiuwen foreground path uses `attach_output`/`send_input`, so the target is not
Runner-only. `AgentBridgePort` itself is instantiated only by
`fake_verticals.py`; the real formal bridge consumes committed Harness handles.
JiuwenSwarm still authenticates the product scope, chooses the project/session/
model Agent and translates committed context and observations.

No local Scope, execution, Task, event, cursor, checkpoint, effect or bound
facade candidate is reported as direct reuse. Those contracts are not present
in the locked/base dependency and require the AgentCore candidates below.

### 2.2 Thin downstream Adapters after the owning API exists

The allowed Adapter responsibilities are deliberately smaller than the current
LiveVoice authorities:

| Capability IDs | AgentCore or Jiuwen owner | Only responsibility retained downstream |
|---|---|---|
| `EXE-02`, `SCOPE-01` mapping | scoped execution admission and TeamTask authority | translate verified principal/project/session and product configuration into an immutable scope/profile; no Task settlement |
| `EXE-04`, `TASK-03` | command replay, terminal outcome and immutable result | extract product chat/patch artifacts and adjustment policy; no result ledger |
| `EXE-05`, `BRIDGE-02`, `BRIDGE-04` | existing Agent/Tool/Runner/DeepAgent/Harness plus future accepted execution fencing | choose the Jiuwen Agent, freeze committed product context and translate stream observations; no second launch lifecycle |
| `TASK-05` | PR 06 checkpoint publication exposed through PR 09 | checkpoint codec, compatibility, retention and payload Port; no raw locator, finalizer or resume authority |
| `EVT-02`, `EVT-04` | canonical event reader/head | cancellation-aware transport polling and a pure event-to-product progress projection; no event sequence or durable subscription owner |
| `EVT-06` | PR 08 cursor exposed through PR 09 | verify authentic DOM adoption or voice playout, then issue exactly one generic cursor CAS; no second cursor |
| `D2-02`, `D2-03` | PR 07 effect journal exposed through PR 10 | public product `ProjectEffectPort`, provider credentials/request body, project/file probe and compensation policy; no token or evidence writer |
| `COMP-01`, `WEB-01` | bound Task/effect authorities | authentication, product envelope mapping and discardable browser projection; no canonical Task/Event/Result cache |

These are future boundary shapes, not selected implementations. The moving
feature branch must revalidate each seam against the accepted AgentCore public
contract before code is written or ported.

### 2.3 AgentCore PR candidates

The ten candidates are dependency-ordered, separately reviewable generic
AgentCore changes, not one LiveVoice PR:

| PR | Capability | Current preparation state |
|---:|---|---|
| 01 | mandatory TeamTask scope (`SCOPE-01`) | local technical replay; real issue metadata and reviewable history package pending |
| 02 | monotonic AsyncTool cancellation (`A1`) | isolated local technical candidate; issue metadata/package pending |
| 03 | durable execution ownership (`A2`) | Tier-3 technical-ready on its recorded evidence (`573` affected tests, `130` race repeats, `C0/I0`); the worktree remains dirty/uncommitted and the issue metadata/package are not submission-ready |
| 04 | command replay and immutable result (`ADD-01`) | preflight complete; formal replay waits for the packaged PR 03 base |
| 05 | canonical Task events and transactional dispatch (`ADD-02`) | preflight complete; formal replay waits for accepted PR 04 semantics |
| 06 | execution-checkpoint publication (`ADD-05`) | preflight complete with `4 Critical / 2 Important` historical findings; topology/dependency freeze and accepted prerequisites required |
| 07 | external-effect journal (`ADD-04`) | preflight complete with `5 Critical / 6 Important` historical findings; accepted PR 03/05 and continuation/public-boundary freeze required |
| 08 | Task-event consumer cursor (`ADD-03`) | preflight complete with `2 Critical / 4 Important` historical findings; accepted event identity/baseline semantics required |
| 09 | lifecycle-bound TeamTask/checkpoint authority | preflight complete with `5 Critical / 4 Important` historical findings; reimplement opaque lease and structural capability grants after dependencies |
| 10 | lifecycle-bound external-effect authority | preflight complete with `5 Critical / 4 Important` historical findings; reimplement trusted registration and token-free typed coordination after PR 07/09 |

All ten have dedicated test-first replay packets in the
[packet index](agentcore-pr-preparation/README.md). “Preflight complete” means
the historical candidate was inspected and the safe target contract was
recorded; it does not mean the defect is fixed or the PR is ready. No candidate
has been pushed or submitted.

### 2.4 LiveVoice/JiuwenSwarm ownership that remains

AgentCore does not absorb:

- audio capture/playout, VAD, STT/TTS providers, media transport and echo or
  interruption safety;
- committed turn/response/generation state and foreground Agent delivery;
- product principal/project/session authority, intent/target/confirmation,
  model/route policy and telemetry;
- project worktree, patch/artifact, unsafe-link and resource cleanup policy;
- authentic DOM/playout presentation proof, text/voice coordination and
  committed-history policy;
- browser experience, transport recovery, privacy, deployment composition and
  product diagnostics.

These are positive ownership decisions. Their code may still be consolidated,
split or re-homed, but a lower line count does not justify moving product or
voice policy into AgentCore.

## 3. What the Hermes comparison established

The module register classifies all **152 of 152** observed production paths,
with zero missing or extra rows. Each row records responsibility, necessity,
authority, AgentCore relation, Hermes relation, size driver and proposed
disposition by module path, public symbol, contract and capability ID—never by
source line number.

The pinned comparison is the separate
`bielcarpi/hermes-live-voice@3dd8af386b845a1486b05b088bbc2b5a642a5b28`,
not a 16-file selection from official Hermes Agent. It exposes Browser SDK/audio,
Web demo, Dashboard relay, inbound HTTP/WebSocket, `LiveGatewaySession`,
Provider adapters, `TaskSupervisor`, Task Store, Hermes Runs adapter and
terminal. It does not define Jiuwen product ownership and is not a deletion
oracle. LiveVoice is larger for two different reasons:

- **justified complexity:** Jiuwen multi-Channel/host trust boundaries,
  committed-input/product authority, richer scope/execution/effect semantics,
  project/worktree policy, authentic presentation ACK, privacy and default-off
  deployment controls; and
- **convergence opportunities:** historical Web/AutoHarness carriers, v1/v2 or
  Python/TypeScript contract repetition, large shared-host integration
  segments, runtime validation mixed into composition, unused reference
  implementations and generic state duplicated below AgentCore.

The module-level decisions therefore include `RETAIN`, `RETAIN AS THIN
BRIDGE/ENTRY`, `CONSOLIDATE`, `SPLIT`, `EXTRACT`, `RE-HOME`, `REPLACE` and
`REMOVE AFTER GATE`. Absence of a Hermes analogue never selects removal by
itself.

## 4. Minimal future LiveVoice allowlist

Only the following code shapes may be proposed to the feature branch after
their AgentCore dependencies are accepted and installed:

1. authenticated product scope/project/session binding into public Runner and
   lifecycle-bound Task/effect capabilities;
2. one read-only product query translation, with an asynchronous injection
   seam only if the then-current carrier still requires it;
3. one D1 codec/payload-policy Adapter into the bound checkpoint coordinator;
4. one public JiuwenSwarm `ProjectEffectPort` plus a token-free registered
   Adapter into the bound effect coordinator;
5. product presentation-receipt verification followed by one cursor advance;
   and
6. a pure event/progress projector plus the minimum existing transport polling
   wrapper, with no alternate event sequence or subscription state machine.

This allowlist is not an implementation order and does not approve current
prototype code. Every item requires a separate current-source packet, explicit
dependencies, risk tier, positive scenarios, negative zero-side-effect
evidence and review.

## 5. Integration and exclusion boundary

The following stable preparation records may later be selectively ported as
documentation after comparison with the then-current product source:

- the accepted
  [scope](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md);
- this convergence review;
- the symbol migration map and complete module/Hermes disposition;
- the prototype adjudication; and
- only the user-relevant summary of the AgentCore PR preparation review.

The AgentCore replay packets belong with the AgentCore preparation work. They
are not LiveVoice product documentation or product implementation.

The following are explicitly excluded from wholesale integration into
`hx/0812_live_voice_w3`:

- the five candidate commits `9c820fe1`, `1a84b541`, `0228b738`, `b0575038`
  and `561e5e5f`, including their current production modules and large mirror
  model/validation layers;
- the ignored EVT-02 implementation, tests and packet;
- duplicate Task/Event/Execution/Result/Cursor models, generic validation,
  payload stores, subscription authority and private project-mutation helpers;
- the historical `codex/ac-pr01-*` through `codex/ac-pr10-*` stacked review
  refs as a single AgentCore merge unit;
- the aggregate `codex/oj-g2-local-base@50c065dc` candidate workspace as a
  33-commit, 73-file, 31,828-insertion merge unit; its accepted capability
  fragments must be replayed into their owning PRs;
- experimental implementation packets and tests merely because they pass; and
- the `codex/livevoice-agentcore-hermes-prep` branch or its history as a whole.

No composition activation, dual write, authority/data migration, default-on,
canary, Store retirement, source deletion, remote-ref update or PR submission
is selected by this review.

## 6. Closure evidence and remaining boundary

The original final documentation checks confirmed on their historical baseline:

- the product branch remained clean at observed HEAD `acd873d0`, equal to its
  upstream, so the reviewed source baseline had not advanced;
- the manifest and semantic disposition sets each contained 152 unique paths,
  with zero missing and zero extra;
- the four AgentCore classifications remained exclusive in the capability map
  and linked to their owning or consuming modules;
- all 564 local Markdown targets under `live-voice` resolved;
- `git diff --check` passed;
- `git ls-files -- docs/zh/live-voice/**` returned zero tracked duplicates; and
- an independent cross-document review found no blocker under the then-current
  methodology. The zero-baseline re-audit later found that methodology and the
  Hermes source baseline were insufficient; its results supersede that closure.

No runtime test is required for this final Tier 0 document because it selects
no production code. Existing technical test counts remain attached to their
exact candidate sources in the PR review and packet index; they do not transfer
submission readiness to another base.

After the zero-baseline correction, unfinished preparation work includes
replaying/accepting PR dependencies, reimplementing PR09/10 public grants,
preparing per-PR source/test/docs packages, and later designing thin Channel,
Agent and Task facades against the then-current product source. LiveVoice
Adapter implementation and all migration/cutover work remain intentionally
outside this preparation task.
