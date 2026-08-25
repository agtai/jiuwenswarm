# OpenJiuwen LiveVoice slimming preparation convergence review — 2026-08-25

Status: the line-number-independent inventory, ownership classification,
Hermes explanation and prototype adjudication are complete for the observed
LiveVoice product baseline. The AgentCore PR **design and replay packets** are
complete, but the complete PR source/test/docs packages are not: PR 01–03 have
local technical candidates and PR 04–10 have preflight only. This document is
a preparation decision index, not migration, deletion, product-readiness or PR
submission approval. `STATUS.md` remains the authority for mutable project
state.

Risk: Tier 0 documentation under root `TESTING.md`. Every later code boundary
retains its independently assigned risk and evidence requirements.

## 1. Converged answer

The slimming target is not “merge the preparation branch” and is not “make
LiveVoice look like Hermes.” The selected result is:

1. call the existing public AgentCore Runner/Agent boundary directly where it
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
[symbol migration map](OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md),
the
[152-path module disposition](OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md),
the
[prototype adjudication](OPENJIUWEN_LIVEVOICE_PROTOTYPE_ADJUDICATION_2026-08-25.md)
and the
[AgentCore PR preparation review](OPENJIUWEN_AGENTCORE_PR_PREPARATION_REVIEW_2026-08-25.md).

## 2. AgentCore outcome by capability

### 2.1 Direct reuse available now

The only current direct AgentCore reuse selected by this review is the public
Agent/Runner invocation boundary: `Runner.run_agent`,
`Runner.run_agent_streaming` and compatible public Agent construction. This
replaces the generic invocation role of `BRIDGE-01` and is the target under
`EXE-05`; JiuwenSwarm still authenticates the product scope, chooses the
project/session/model Agent and translates committed context and observations.

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
| `EXE-05`, `BRIDGE-02`, `BRIDGE-04` | existing Runner plus accepted runtime/execution fencing | choose the Jiuwen Agent, freeze committed product context and translate stream observations; no second launch lifecycle |
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
| 03 | durable execution ownership (`A2`) | technical-ready on the recorded evidence; issue metadata and three-commit package pending |
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

Hermes is useful because it exposes recognizable responsibility clusters:
audio/platform edge, speech-provider boundaries, generation/playout,
interruption, echo protection and Agent/session connection. It does not define
Jiuwen product ownership and is not a deletion oracle. LiveVoice is larger for
two different reasons:

- **justified complexity:** Browser/Gateway/AgentServer trust boundaries,
  committed-input authority, durable Task/execution/event/effect/cursor truth,
  fail-closed recovery, authentic presentation ACK, privacy and default-off
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

The final documentation checks confirmed:

- the product branch remained clean at observed HEAD `acd873d0`, equal to its
  upstream, so the reviewed source baseline had not advanced;
- the manifest and semantic disposition sets each contained 152 unique paths,
  with zero missing and zero extra;
- the four AgentCore classifications remained exclusive in the capability map
  and linked to their owning or consuming modules;
- all 564 local Markdown targets under `live-voice` resolved;
- `git diff --check` passed;
- `git ls-files -- docs/zh/live-voice/**` returned zero tracked duplicates; and
- an independent cross-document review found no remaining architecture or
  classification blocker after the stale ordering/status/exclusion findings
  were corrected.

No runtime test is required for this final Tier 0 document because it selects
no production code. Existing technical test counts remain attached to their
exact candidate sources in the PR review and packet index; they do not transfer
submission readiness to another base.

After this convergence review, the only unfinished work inside the accepted
preparation scope is the actual AgentCore PR packaging: obtain a real issue
reference, package/reword and independently review PR 01–03, then replay and
verify PR 04–10 on accepted dependency tips and prepare per-PR title/body,
evidence, risk and exclusions. The later LiveVoice Adapter implementations and
all migration/cutover work remain intentionally outside this preparation task.
