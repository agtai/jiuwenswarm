# Contextual delegation review repair — 2026-09-03

## Finding and scope

Baseline: `a0995b46178de2ce10e49adbcc79c92f9a7c5016`, formal Web Cascade.
The first spoken analysis request successfully listed the fixed project and read
its input Markdown file. The next committed utterance explicitly delegated the
same work and added constraints. The main semantic model proposed `task.create`
with the original requirement source; the separate short Boolean review returned
`authorized=false`. The resolver synthesized `dialogue`, so the Agent analyzed
again. The authoritative Store contained zero Tasks for that Session.

Neither file discovery nor a missing Task-list refresh caused this failure.
The assistant had not offered further work, but the original user objective and
presented analysis were in semantic context. A pending offer is not required for
this kind of explicit contextual delegation. The precise reason for the model's
Boolean denial was not recorded; punctuation alone was not a sufficient diagnosis.

Owned boundary: Task semantic resolution and its Registry integration tests,
Tier 2 under root TESTING. Intended behavior is contextual local delegation with
current consent, exact original requirements and normal downstream authority.
Artifact calculations/quality, unrelated Agent behavior, Provider configuration,
new classifiers/keywords, shared schema/migrations and full Demo closure are out
of scope. The verification project and its input were not modified.

## Implemented change and scope checkpoint

Short-review prompt variants did not satisfy both positive and negative cases;
their private reports remain failed development evidence, not acceptance runs.
The coherent repair instead reuses the existing full semantic contract and
decoder for the bounded pre-create review. Both passes receive the same original
committed input and frozen context, including pending references and authoritative
Task facts. The first candidate is not supplied as consent evidence.

The review returns an already-supported semantic decision. Valid local creation
continues through normal Registry authority; actual foreground conversation keeps
its dialogue route; unresolved work retains an explicit clarification instead of
being converted from a Boolean denial into dialogue. Conflicting operations,
malformed output and model tool calls fail closed. Review retries are structural,
bounded and share the original deadline; authority/cancel checks run before each
model call. Existing frozen decisions keep their exact replay behavior.

This replaces a private model-response format, not the public protocol or stored
decision schema. It keeps two model calls for approved local creation; the review
now has more context/schema tokens. No latency improvement is claimed.

Tested product file SHA-256:
`599bd5ce6a0a532c988bddad1cc48602559de8d6c7c7f548e085c6be3b00daa5`.

## Verification and limitations

- **89 passed, 61 deselected**: `python -m pytest -o addopts='' -o log_cli=false
  tests/unit_tests/live_voice/test_task_semantics.py
  tests/unit_tests/live_voice/test_semantic_registry.py -q -k
  'not test_semantic_registry or explicit_local_delegation_creates_once_with_normal_authority
  or local_delegation_requires_current_supported_executor
  or persistent_invalid_continuation_has_zero_effects_and_replays_rejection'`.
- **2 passed, 65 deselected**: the same Registry module with
  `-k local_delegation_review_has_zero_task_effects_and_replays`.
- These checks include one exact Task creation and replay, rejected/unresolved
  zero Task/Agent effects, frozen context/provenance, malformed review, forbidden
  tool output, operation conflict, shared timeout and pre-review cancellation.
  No state/concurrency owner was changed; existing identity/replay boundaries are
  reused. No physical media, restart-durability or platform claim is made.
- Before repairing the two old positive Registry test-model cases, both failed
  with `SEMANTIC_PROVIDER_UNAVAILABLE`. Replacing only the changed prompt constant
  with its exact baseline value reproduced both failures. The old test model did
  not implement the existing Boolean review input. Tests now model the shared
  semantic review and account for both calls; this is not a product bypass.
- Real configured `deepseek-v4-flash#0`, unchanged private configuration: the
  original recorded utterance and a non-travel follow-up both completed the full
  resolver as local `task.create`, preserving prior and current user text.
- Eight additional real-review probes deliberately supplied an incorrect initial
  create proposal. Six foreground/quoted/constraints-only/missing-objective/
  hypothetical/old-delegation cases returned the intended dialogue or clarification;
  modification of a missing Task failed closed. A direct external purchase request
  returned dialogue with no Task operation, compatible with the previous denied-
  review fallback, rather than the probe's stricter expected clarification/rejection.
  Preserve that discrepancy: **9/10 expected-route checks, all 8 negative probes
  produced no Task operation**. The foreground Agent's handling of external
  transactions was not run and is not accepted by this record.
- Real-model probes had no Registry dispatch, Agent, file, audio or Task writers.
  They prove the semantic seam, not a completed spoken Task or physical playback.
  Raw inputs/reports remain machine-private outside the verification project.
- Main reviewed the complete scoped diff. No callable independent code-review
  tool was available; self-review is not independent review. That gate remains open.

Overall remains **PARTIAL**. Deployment and the user's new spoken commit must
still demonstrate Task A in the authoritative Store. Complete A/B/A2, offline,
notification ACK/refresh and physical acceptance are not covered here.
