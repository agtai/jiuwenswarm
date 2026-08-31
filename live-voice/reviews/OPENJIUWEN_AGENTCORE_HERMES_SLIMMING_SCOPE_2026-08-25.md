# OpenJiuwen AgentCore reuse and Hermes comparison scope — 2026-08-25

Status: accepted scope for the preparation-only LiveVoice slimming handoff,
clarified by D-096 on 2026-09-01. This record defines what the isolated
preparation branch may produce and what must not flow into the moving LiveVoice
feature branch without a later, separately accepted implementation decision.

Execution follows the
[slimming preparation implementation plan](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_EXECUTION_PLAN_2026-08-25.md),
which closes inventory, classification, prototype adjudication and the future
activation handoff without requiring AgentCore PR implementation or packaging.

The resulting classifications, integration allowlist, exclusions and honest
downstream-capability boundary are indexed by the
[convergence review](OPENJIUWEN_LIVEVOICE_SLIMMING_FINAL_REVIEW_2026-08-25.md).

## 1. Goal

Reduce LiveVoice's long-term ownership and code volume by determining, without
performing the migration now:

1. which LiveVoice capabilities duplicate AgentCore and can call its public
   boundary directly;
2. which capabilities can reuse AgentCore through a thin LiveVoice Adapter;
3. which generic capabilities are missing from AgentCore and should be recorded
   for eventual AgentCore ownership rather than remain in JiuwenSwarm; and
4. why every current LiveVoice module exists, whether its responsibility is
   necessary, and whether it should be retained, consolidated, refactored,
   replaced or removed.

LiveVoice is still changing. Long-lived conclusions therefore identify
capabilities, contracts, symbols and module responsibilities, not source line
numbers.

## 2. AgentCore classification

For the AgentCore-specific decision, every relevant LiveVoice capability first
receives exactly one of the following ownership answers:

- **Direct reuse:** AgentCore already exposes a suitable public contract and
  LiveVoice needs no competing authority or durable state.
- **Adapter reuse:** AgentCore owns the generic capability; LiveVoice retains
  only the minimum product-specific translation, validation or fault fence.
  The Adapter must not become another generic state machine.
- **AgentCore downshift requirement (`AGENTCORE_PR`):** AgentCore lacks a
  generally useful capability that should eventually be implemented and
  reviewed in the AgentCore repository. This branch records the required
  public contract, owner, dependency, failing oracle and acceptance boundary;
  it does not implement, package, submit or push that future change. The
  historical code name remains stable so the 228-row register does not churn.
- **LiveVoice-owned:** the responsibility is genuinely voice-product-specific
  and remains in LiveVoice, subject to consolidation or refactoring analysis.

The later eight-code atomic register generalizes `DIRECT_REUSE` and
`ADAPT_REUSE` across both allowed providers: an installed AgentCore public
boundary **or** an existing JiuwenSwarm shared host. Each atomic row must name
which provider remains authoritative. Therefore a `DIRECT_REUSE` row for
`WebChannel`, `AgentManager` or Session History does not claim that host belongs
to AgentCore; it proves LiveVoice must call the existing JiuwenSwarm owner
instead of rebuilding it.

The classification must state the public contract, authority owner, required
Adapter responsibility, unsupported gaps, dependencies and evidence. A
successful prototype is evidence for a decision, not proof that the prototype
itself should be integrated.

## 3. Hermes comparison

The primary architecture reference is the independent community integration
`bielcarpi/hermes-live-voice@3dd8af386b845a1486b05b088bbc2b5a642a5b28`.
Official `NousResearch/hermes-agent@fc9cbc872d8050c22f1192b16bc5ff4aed471e10`
is a secondary reference for Agent/Session and official Voice seams only; the
two repositories and their LOC must not be combined. Hermes Voice is not a
target implementation or a feature-parity requirement. The comparison is used
to explain LiveVoice:

- what each module owns and why that responsibility exists;
- which dependency or product invariant makes it necessary;
- whether the responsibility is voice-specific, JiuwenSwarm-specific or a
  generic AgentCore concern;
- why the current implementation is large; and
- whether the module should be retained, consolidated, split, refactored,
  replaced or removed.

No Hermes source is copied and no Hermes dependency is introduced. A design
difference is acceptable when LiveVoice's product contract explains it.

## 4. Required outputs

The preparation task closes only after it produces:

1. a line-number-independent AgentCore capability map covering direct reuse,
   Adapter reuse, AgentCore PR candidates and LiveVoice-owned responsibilities;
2. a module disposition register that explains every LiveVoice module's role,
   necessity, complexity and proposed outcome;
3. a Hermes-based architectural comparison supporting those explanations;
4. an AgentCore downshift requirement map for generic gaps, including public
   contract, owner, dependencies, risks and acceptance evidence, without local
   PR implementation or packaging; and
5. a minimal future LiveVoice integration list containing only the selected
   thin Adapters or seams, with their dependencies and acceptance requirements.

These outputs are preparation artifacts. They do not grant product capability,
migration, deletion or readiness credit.

## 5. Explicit non-goals

This task does not:

- activate a new default composition or production path;
- migrate data or authority, introduce dual writes, run a canary, retire a
  Store, or delete the current canonical implementation;
- perform feature-branch integration while LiveVoice is still moving;
- implement, replay, package, submit or push an AgentCore PR, or update any
  remote ref;
- reproduce Hermes behaviour merely for parity;
- preserve source line numbers as durable migration truth; or
- merge experimental candidate code wholesale into the LiveVoice feature
  branch.

Any future composition, migration, cutover, deletion or product-behaviour
change requires a separately scoped and risk-tiered implementation packet.

## 6. Treatment of the current preparation commits

The following commits are retained only on the isolated preparation branch as
candidate implementations and evidence. Their final keep/minimize/discard
decision is detailed in the
[prototype adjudication](OPENJIUWEN_LIVEVOICE_PROTOTYPE_ADJUDICATION_2026-08-25.md):

| Commit | Candidate boundary | Final preparation decision |
|---|---|---|
| `9c820fe1` | OpenJiuwen Task facade | rewrite as a thin scope/mapping boundary over the future **reimplemented, re-reviewed and accepted** PR 09 lifecycle-bound reader/command/cursor/checkpoint grants; never adapt against the historical rejected facade; retain tests as oracles |
| `1a84b541` | asynchronous product query owner | retain only the optional async seam design; rewrite the adapter without mirror authority/models |
| `0228b738` | D1 checkpoint Adapter | rewrite as codec/payload-policy mapping into the future reimplemented, re-reviewed and accepted PR 09 checkpoint capability over accepted PR 06 safe preauthorization; never adapt against the historical facade; retain durability oracles |
| `b0575038` | project/file effect Adapter | discard implementation; first extract a public product `ProjectEffectPort`, then register only a token-free Adapter with the future reimplemented, re-reviewed and accepted trusted-host PR 10 coordinator; never adapt against the historical coordinator; no raw continuation/evidence writer |
| `561e5e5f` | presentation cursor Adapter | retain product receipt proof and optional async seam design; rewrite cursor mapping against final public types |

Together these commits add roughly ten thousand lines including tests and
implementation packets. Their presence on this branch does not make them a
LiveVoice integration candidate. The adjudication above explicitly prevents
those experimental lines from becoming a feature-branch merge unit.

The uncommitted EVT-02 raw event-subscription prototype is outside the active
implementation scope. It risks adding another LiveVoice polling/subscription
state machine above the existing AgentCore/facade event-read boundary. It is
kept only as a local, ignored recovery archive and is not a tracked deliverable.
Its implementation and packet are discarded; only bounded replay/auth/race
test ideas may be ported to the final event-reader/projector boundary.

## 7. Eventual integration boundary

When the analysis is complete, the moving LiveVoice feature branch may receive
only:

- stable decision and module-disposition records; and
- separately accepted, minimal LiveVoice code that remains necessary after
  direct AgentCore reuse and AgentCore PR ownership are accounted for.

Generic downstream implementation belongs in a future AgentCore-owned change
only if activation-time evidence still selects that disposition.
Unselected prototypes, duplicate validation scaffolding and superseded
implementation packets do not flow into LiveVoice. The isolated preparation
branch remains an analysis and recovery source; it is not merged wholesale.

## 8. Isolation and ownership

The preparation work is isolated on branch
`codex/livevoice-agentcore-hermes-prep`. The product feature branch
`hx/0812_live_voice_w3` must remain free of these candidate commits and local
analysis files. Main remains the sole Integration Owner. No remote update is
authorized by this scope.

## 9. Zero-baseline flow audit correction — 2026-08-31

The earlier module-disposition pass is not sufficient as a final slimming
decision. It started from the modules already present in LiveVoice and then
explained their necessity. That method can confuse a required product
capability with a requirement for LiveVoice to implement that capability
itself. The existing disposition, comparison and LOC statements are therefore
**provisional** until the zero-baseline audit below closes.

The corrective audit starts from observable flows and existing platform
capabilities, in this order:

1. reconstruct the current executable flow and identify the symbol that owns
   each transition, state mutation and external effect;
2. identify the equivalent Hermes client, inbound Adapter, gateway,
   conversation, task and Agent responsibility on the pinned Hermes source;
3. prove what JiuwenSwarm and the installed AgentCore already provide through
   public contracts, while treating local candidates only as gap evidence;
4. only then decide whether LiveVoice needs a direct call, a thin Adapter, an
   AgentCore downshift requirement, a voice-specific implementation, a host/channel
   integration, a split or retirement.

The audit covers these complete flows rather than accepting directory names as
module boundaries:

- startup, configuration, composition and channel attachment;
- capture, recognition and committed input;
- Conversation Runtime, Agent invocation and history;
- synthesis, playback, acknowledgement, interruption and presentation;
- task intent, confirmation, command and admission;
- Agent/Tool execution, progress, result and notification;
- durability, restart recovery, reconnect and cursors; and
- authority, permission, observability, failure and cleanup.

Every tracked production path in the reproducible LiveVoice footprint must be
accounted for exactly once. A mixed file is classified by responsibility and
public symbol instead of being assigned wholesale to one layer. Every resulting
row receives exactly one current disposition:

- `DIRECT_REUSE`;
- `ADAPT_REUSE`;
- `AGENTCORE_PR`;
- `LIVEVOICE_CORE_KEEP`;
- `CHANNEL_ADAPTER_KEEP`;
- `JIUWENSWARM_HOST_KEEP`;
- `SPLIT_REQUIRED`; or
- `CONSOLIDATE_RETIRE`.

The LOC report must first verify the claimed aggregate rather than inherit it.
It separates production, tests, fixtures/support, scripts and
documentation/evidence, then partitions production into LiveVoice Core,
channel Adapters, JiuwenSwarm host integration, AgentCore duplicate/candidate,
legacy/transition and mixed-symbol responsibility. Generated output,
dependencies and unrelated shared-file content are excluded explicitly. The
production buckets must sum to the reported production total with zero missing
or duplicate paths.

Hermes does have browser/channel integration. Its `clients/browser`, Web demo,
Dashboard plugin and inbound HTTP/WebSocket Adapters are compared with the
JiuwenSwarm Web carrier as equivalent responsibility groups even though Hermes
does not use the single label `Channel Adapter`. Browser/channel code may be
part of the delivered LiveVoice product footprint while remaining outside
channel-neutral LiveVoice Core.

This correction changes the analysis standard, not product architecture or
runtime authority. It authorizes no migration, code deletion, composition
activation, AgentCore integration, remote update or feature-branch change.
