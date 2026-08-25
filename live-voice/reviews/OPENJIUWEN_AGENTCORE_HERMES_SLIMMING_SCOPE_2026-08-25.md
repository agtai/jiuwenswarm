# OpenJiuwen AgentCore reuse and Hermes comparison scope — 2026-08-25

Status: accepted scope for the preparation-only LiveVoice slimming analysis.
This record defines what the isolated preparation branch may produce and what
must not flow into the moving LiveVoice feature branch without a later,
separately accepted implementation decision.

Execution follows the
[slimming preparation implementation plan](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_EXECUTION_PLAN_2026-08-25.md),
which closes inventory and classification before prototype adjudication or
AgentCore PR preparation.

## 1. Goal

Reduce LiveVoice's long-term ownership and code volume by determining, without
performing the migration now:

1. which LiveVoice capabilities duplicate AgentCore and can call its public
   boundary directly;
2. which capabilities can reuse AgentCore through a thin LiveVoice Adapter;
3. which generic capabilities are missing from AgentCore and should be prepared
   as AgentCore PR candidates rather than remain in JiuwenSwarm; and
4. why every current LiveVoice module exists, whether its responsibility is
   necessary, and whether it should be retained, consolidated, refactored,
   replaced or removed.

LiveVoice is still changing. Long-lived conclusions therefore identify
capabilities, contracts, symbols and module responsibilities, not source line
numbers.

## 2. AgentCore classification

Every relevant LiveVoice capability receives exactly one current disposition:

- **Direct reuse:** AgentCore already exposes a suitable public contract and
  LiveVoice needs no competing authority or durable state.
- **Adapter reuse:** AgentCore owns the generic capability; LiveVoice retains
  only the minimum product-specific translation, validation or fault fence.
  The Adapter must not become another generic state machine.
- **AgentCore PR candidate:** AgentCore lacks a generally useful capability
  that should be implemented and reviewed in the AgentCore repository. The
  work product is a locally prepared PR candidate; this task does not submit or
  push the PR.
- **LiveVoice-owned:** the responsibility is genuinely voice-product-specific
  and remains in LiveVoice, subject to consolidation or refactoring analysis.

The classification must state the public contract, authority owner, required
Adapter responsibility, unsupported gaps, dependencies and evidence. A
successful prototype is evidence for a decision, not proof that the prototype
itself should be integrated.

## 3. Hermes comparison

Hermes Voice is an architecture reference, not a target implementation or a
feature-parity requirement. The comparison is used to explain LiveVoice:

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
4. locally prepared AgentCore PR candidates for the generic gaps selected for
   downstream ownership, kept in the AgentCore repository; and
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
- submit or push an AgentCore PR or update any remote ref;
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
| `9c820fe1` | OpenJiuwen Task facade | rewrite as a thin public-`TeamTaskAuthority` scope/mapping boundary; retain tests as oracles |
| `1a84b541` | asynchronous product query owner | retain only the optional async seam design; rewrite the adapter without mirror authority/models |
| `0228b738` | D1 checkpoint Adapter | rewrite as codec/payload-policy mapping into `ExecutionCheckpointCoordinator`; retain durability oracles |
| `b0575038` | project/file effect Adapter | discard implementation; extract a public product `ProjectEffectPort` before writing any thin continuation adapter |
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

Generic downstream implementation belongs in the AgentCore PR candidate.
Unselected prototypes, duplicate validation scaffolding and superseded
implementation packets do not flow into LiveVoice. The isolated preparation
branch remains an analysis and recovery source; it is not merged wholesale.

## 8. Isolation and ownership

The preparation work is isolated on branch
`codex/livevoice-agentcore-hermes-prep`. The product feature branch
`hx/0812_live_voice_w3` must remain free of these candidate commits and local
analysis files. Main remains the sole Integration Owner. No remote update is
authorized by this scope.
