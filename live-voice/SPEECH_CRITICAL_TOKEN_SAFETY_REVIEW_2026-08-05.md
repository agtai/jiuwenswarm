# Speech Critical-Token Safety Implementation Review — 2026-08-05

## Record status and truth boundary

- Task: `SPEECH-CRITICAL-TOKEN-SAFETY`.
- Base: `1e76dbd6aa0ebb011842f31beb98ca2cb11d2496` on `codex/lv-speech-critical-token-safety`.
- Risk: Tier 3 for a committed-input safety boundary shared by Agent, Tool, Task, Chat mutation, and speech-response routes.
- Pre-consolidation reviewed candidate chain: implementation `c96382a8404574dbacac9fceb5a504c18215bcbb`; strict-generation correction `becee263b5ac5f2fc798b713c99b931b9b7e05f0`, whose parent was the implementation commit. These SHAs preserve the identities actually reviewed; after the approved history consolidation they are not the final branch ancestry. The consolidated commit SHA is reported in the Worker handoff because a commit cannot embed its own identity.
- Delivery state: implemented, locally reviewed, and deterministically tested as a foundation package. It is not runtime-wired, product-composed, real-service verified, Gate accepted, or eligible for Replacement Ledger credit.
- Current mutable project state remains exclusively owned by [STATUS.md](STATUS.md); this record does not update or override it.

The controlling inputs were the task packet, D-039/D-044, the ACG Speech hypothesis/final, InputCommit, TurnCommit, Error, Interaction, and Action boundaries, the current Demo commit/dispatch/confirmation paths, and the P1 Speech review matrix. The newer task packet explicitly owns the committed-input guard and once-only dispatch seam; it does not transfer Task authority from VB-B/TC-B.

## Delivered package

- [critical_token_safety.py](../jiuwenswarm/server/live_voice/critical_token_safety.py) adds an explainable lexical `CriticalTokenPolicy`. It recognizes negation, Arabic/Chinese/English numbers, numeric and spoken dates/times, SHA values, quoted/unquoted paths, contextual branches, identifiers, commands, side-effect verbs, and trusted configured domain terms.
- The policy compares raw and display evidence plus all supplied alternatives. Critical comparison preserves case and token order, so case-sensitive identifiers and changed negation/number associations do not collapse.
- Unknown or low confidence on speech critical tokens, critical alternative disagreement, or explicit upstream critical uncertainty yields a typed clarification requirement. Low-risk natural language with no critical evidence still passes.
- Baseline committed-final integrity is separate from the switchable clarification policy. Feature-off bypasses critical-token policy and its limits, but never bypasses finality, `TurnCommit.text`/selected-final equality, or trusted input-generation provenance.
- `CriticalTokenSafetyGate` owns pending/resolved/cancelled/replaced clarification state, active/consumed/cancelled/replaced authorization state, monotonic per-interaction input generation, blocked-input tombstones, and permanent closed-interaction tombstones.
- A corrected confirmation must use a new commit and turn, the same interaction and scope, a higher trusted generation, the exact source commit, and immutable clarification provenance. A successful correction produces one authorization; the protected callback is consumed before invocation and cannot be retried after an unknown downstream failure.
- `dispatch()` is the single package seam for `agent`, `tool`, `task`, and `other` protected routes. The composition layer must wrap the complete route choice and all downstream mutation in this callback.

The implementation is deterministic and does not call an LLM. Configured domain terms are additive trusted context, not a replacement for the built-in lexical policy and not client-controlled authorization.

## Integration seam requiring owner acceptance

This package does not modify the shared ACG schema. Integration must explicitly accept and supply these package inputs:

1. A server/Adapter-owned monotonic `input_generation` for each interaction. Client assertions are not authoritative.
2. Matching immutable `TurnCommit.hypothesis_provenance.critical_token_input.input_generation`.
3. For a correction, `critical_token_clarification` containing the exact `clarification_id`, `supersedes_commit_id`, and corrected `input_generation`.
4. Full selected raw/display evidence and alternatives; silently supplying only a polished display string weakens the oracle and is not conformant.
5. Server-owned `EvidenceSource`. A browser/client must not relabel speech as `explicit_text` to avoid confidence handling.
6. One gate instance for the authoritative interaction lifetime. `close_interaction()` is terminal for that identity; reopening requires a new interaction identity.
7. Gate placement immediately after authoritative committed-final construction and immediately before any Agent/Tool/Task/Chat/speech-response route choice. No protected path may bypass the once-only callback when the feature is on.
8. Existing destructive-action and Task confirmation remains downstream and authoritative. `requires_downstream_confirmation` does not execute, approve, or reinterpret a Task command.

These are integration requirements proposed by this package, not an accepted ACG/schema change. Integration Owner must reject the seam or accept it explicitly before product composition.

## Scenario-to-evidence matrix

| Dimension | Package scenario and oracle | Evidence |
|---|---|---|
| P | Clear committed-final critical input passes; a bound corrected confirmation dispatches the whole route exactly once | `test_clear_critical_input_passes_without_replacing_action_confirmation`; `test_corrected_confirmation_dispatches_whole_protected_route_exactly_once` |
| N | Unknown/low confidence, changed critical alternatives, non-final input, commit mismatch, missing explicit confirmation, bad binding, forged authorization, and invalid limits fail closed | focused policy/gate negative tests; every rejected mutation-capable path has no authorization or zero effect counters |
| B | Raw/display differences; punctuation/code/path/SHA/date boundaries; Chinese-adjacent and spoken numbers; case/order differences; quoted paths; zero/unknown confidence; evidence/token maxima | critical classification, disagreement, integrity, and limit tests |
| S | Clarification and authorization transitions are explicit; cancel/replace/resolve/consume are terminal; closed interaction never revives | cancel, replacement, interaction-close, and state query tests |
| T | Lower generation, same-generation conflict, delayed clarification, newer blocked generation, and late post-close input cannot apply | stale/replace/generation tests |
| C | Sixteen concurrent dispatch attempts produce exactly one callback; route failure consumes before the uncertain effect boundary | concurrency and route-failure tests |
| R | Callback failure cannot be retried unknowingly. Process restart recovery is not implemented and receives no durability claim | `test_route_failure_consumes_authorization_and_cannot_retry_unknown_effect`; exclusion below |
| I | Interaction, scope, source commit, turn, clarification, and generation provenance must match; forged or cross-scope data cannot fence trusted current state | binding, provenance, conflict, and forged-authorization tests |
| F | Enabled policy clarifies uncertain critical speech. Disabled policy emits an explicit `safety_bypassed` authorization while retaining committed-final integrity and ignoring policy-only limits | feature-on/off tests |
| K | No existing Demo, Agent, TaskBridge, scheduler, shared schema, or frontend file is changed; affected existing Live Voice and v2 contract tests pass | file scope plus affected regression run |
| X | Pure package seam is exercised with all five protected-effect spies and all protected route enums; real product composition is intentionally absent | once-only/zero-effect tests; integration remains a later Gate |

## Forbidden-effects accounting

The test effect spy independently counts `agent`, `tool`, `task`, `chat_mutation`, and `speech_response`. Before clarification succeeds, and for cancel, stale, replace, forged, closed, scope-mismatched, and unprovenanced paths, all five counters remain zero. `dispatch()` is the only test path that receives a mutating callback, and it requires an exact issued active authorization.

The package itself does not call Agent, Tool, Task, Chat, TTS, browser, microphone, Provider, filesystem mutation, or a real external service.

## Integration correction: strict generation provenance

Integration review of `c96382a8404574dbacac9fceb5a504c18215bcbb` found that both generation-provenance matchers used Python's loose equality. Because `True == 1` and `False == 0`, a JSON boolean could satisfy an integer generation comparison and, for generation 1, authorize a protected route.

The correction requires the stored `critical_token_input.input_generation` and `critical_token_clarification.input_generation` value to have exact runtime type `int` before comparing its value. Python `bool`, floats, strings, missing values, and all other types fail closed. Parameterized evaluate tests cover JSON `true` against generation 1 and JSON `false` against generation 0. Parameterized clarification tests cover both booleans while retaining a valid integer input-generation binding. Every rejected result has no authorization; clarification state remains pending on resolve; Agent, Tool, Task, Chat mutation, and speech-response counters remain zero.

Integration Owner re-review of `becee263b5ac5f2fc798b713c99b931b9b7e05f0` closed the original source/test finding. It confirmed Ruff format/check, mypy, 53 focused tests, and 272 affected tests as PASS. This re-review changes no product-wiring, Gate, Replacement Ledger, or shared-status claim.

## Verification on pre-consolidation correction `becee263`

- `D:\XGG AI\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe -m ruff format --check jiuwenswarm/server/live_voice/critical_token_safety.py tests/unit_tests/live_voice/test_critical_token_safety.py` — PASS.
- `D:\XGG AI\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe -m ruff check jiuwenswarm/server/live_voice/critical_token_safety.py tests/unit_tests/live_voice/test_critical_token_safety.py` — PASS.
- `D:\XGG AI\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe -m mypy jiuwenswarm/server/live_voice/critical_token_safety.py --follow-imports=skip --ignore-missing-imports` — PASS, `Success: no issues found in 1 source file`.
- `D:\XGG AI\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe -m pytest -q tests/unit_tests/live_voice/test_critical_token_safety.py --no-cov` — `53 passed`, including all original 49 cases and four boolean-provenance cases.
- `D:\XGG AI\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe -m pytest -q tests/unit_tests/live_voice tests/integration/live_voice/test_fake_verticals.py tests/unit_tests/common/test_live_voice_contract_v2.py --no-cov` — `272 passed`.

The complete affected pytest log is machine-local at `C:\Users\hongx\AppData\Local\Temp\jiuwenswarm-lv-speech-critical-token-safety-artifacts\affected-pytest-strict-generation-correction.log`; it is not acceptance evidence and is not added to Git.

## D-053 review record

### Pass 1 — implementation self-review

The implementation was checked against the task packet and package boundaries while being built. Findings fixed included strict flag truth, raw/display evidence retention, bounded input before fingerprint work, Chinese/version/identifier classification, blocked-input tombstones, immutable clarification provenance, commit collisions, interaction shutdown, and once-only failure semantics. Focused tests were rerun after every semantic correction.

### Pass 2 — cold complete-diff review

The complete source and test additions were reread from the original request, root `AGENTS.md`, D-039/D-044, ACG boundaries, current behavior, and actual test oracles rather than the implementation rationale. Findings fixed included preserving critical case and order, handling explicit unknown-kind critical uncertainty, keeping untrusted correction provenance from fencing a valid clarification, and separating baseline committed-final integrity from feature-controlled policy. The strict-generation integration correction received another complete cold diff review against the exact finding, both matchers, all four boolean cases, forbidden-effect oracles, file exclusions, and final test output. No open source/test finding remains in this package review.

### Pass 3 — independent review substitute

The interactive `/review` entry was not available. The exact independent substitute was the separate Codex review process:

`C:\Users\hongx\.codex\plugins\.plugin-appserver\codex.exe review --uncommitted -c 'model="gpt-5.6-sol"' -c 'model_reasoning_effort="low|medium"' -c 'approval_policy="never"' -c 'sandbox_mode="read-only"'`

Iterative independent runs found and caused fixes for: out-of-order generation replacing newer authorization; newer blocked input not fencing an older authorization; interaction close revival; all-letter hexadecimal SHA; feature-off committed-final bypass; Chinese-adjacent Arabic numbers; simple and command-argument branch names; feature-off policy limits; quoted paths with spaces; and spoken date alternatives. Every finding was fixed and the affected local suites were rerun.

Limitation: the independent read-only process could inspect the full diff but its own pytest attempt could not start because Python reported `FileNotFoundError: No usable temporary directory found`. It therefore did not independently execute tests. The PASS commands above were run separately with the repository venv in this clean task worktree. This record does not claim that interactive `/review` ran.

## Exclusions and remaining evidence

- No `useLiveVoiceDemo`, final Web route, Agent Adapter, Task command detector, confirmation owner, Task authority, scheduler, frontend, shared ACG/schema, `STATUS.md`, `README.md`, decisions, roadmap, validation, or Replacement Ledger change.
- No product route telemetry, Provider/browser/device/audio, real JiuwenSwarm Agent/Tool/Task, real-service, manual, or X-E2E evidence.
- No claim of comprehensive natural-language understanding. Built-in lexical categories cover deterministic common forms; product/repository-specific identifiers must arrive as trusted `domain_terms`, and explicit upstream critical uncertainty fails closed.
- State is same-process memory. Restart durability, distributed exactly-once, multi-process coordination, retention/cleanup policy, and cross-device recovery are not implemented.
- Feature-off behavior is proven only at the package seam; because this package is not wired, existing legacy behavior remains unchanged by construction. Integration must prove flag-off product regression again.
- The package remains `PARTIAL` relative to the product journey until the Integration Owner accepts the seam, wires every protected route, supplies authoritative evidence, and completes real X-E2E/Gate review.
