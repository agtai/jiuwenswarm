# Semantic retirement prerequisite: model, context and replay data

This records a bounded engineering prerequisite, not completion of production
hardcode retirement. User-confirmed activation baseline:
`hx/0812_live_voice_w3@59401beb06ecb78e31dfb9c6ed5486141463768c`.
The Core prerequisite is separately committed as `cab5338e` and retains its own
[evidence](SEMANTIC_RETIREMENT_CORE_BOUNDARY_20260902.md). No service was redeployed,
no remote ref was updated, and no real business Task was run for this boundary.

## Owned behaviour, risk and limits

Tier 3: strict model-only proposals, exact semantic origin provenance, bounded
pre-command context persistence and authenticated read-only model context. These
are prerequisites for Registry cutover, **not yet connected to its production
microphone/Native delegate handlers**. The old paths remain reachable.

- `task_semantics.py` uses the existing configured model resolver, closed JSON
  schema and existing formal operation/argument vocabulary. It supplies no tools
  and has no Task/Agent/history/audio writer. Provider failure, tool requests,
  malformed JSON, unknown fields and invalid references fail closed; no keyword
  fallback exists in this module. Mocked model tests establish boundaries only,
  not actual model language accuracy.
- Input/context, model/config identity, schema/instructions and source spans are
  frozen. The optional `semantic_context_binding` augments the existing formal
  origin/confirmation fingerprint; old bindings without it keep their original
  digest semantics. Structured input cannot inject this natural-input field.
- The existing committed-input journal has an additive pending-context table:
  exact authenticated scope/source/version/time, bounded payload, whole-record
  corruption digest and transactional one-commit consumption. Expired source
  anchors cannot mint a fresh context/expiry. Eight active records per scope and
  4096 total records including anchors are explicit fail-closed bounds.
- An admitted, unexpired execution owner can freeze one semantic record in the
  existing semantic-binding column. Exact replay is allowed; substitution is
  rejected. Frozen restoration validates the original input, context, digest and
  strict output without calling the model or accepting a commit into its ledger.
  It restores data, never an origin receipt or confirmation grant. Current
  ingress provenance and final authorization remain necessary. Crash before
  freeze may repeat parsing, but must not precede a protected effect.
- Authenticated composition reuses bearer or server-retained Native principal
  validation. The exact Task facts sent to the model are checked using the
  existing task.list context rules, both before model preparation and immediately
  before Provider invocation. URI remap, scope change, expiry and redaction fail;
  a normal same-project revision advance remains readable.

No new Executor, natural speech route, Task operation, permission policy or
background workflow is introduced by this module. No old test or assertion was
removed to obtain a pass. Actual Agent recommendations, durable proposal creation
from presented Agent output, both Registry entry points and confirmation recovery
are still integration work, not implementation credit of these helpers.

## Applicable matrix

| Dimension | Observed module evidence |
| --- | --- |
| P | Strict task/dialogue/proposal data, exact pending acceptance and confirmation; legal project revision reads; bearer and Native exact Core cancel with one consumed confirmation. |
| N/I | Wrong scope/expiry/permission/remap/redaction rejected before model invocation; malformed output/tool requests rejected; no additional Task, Executor or confirmation effects where forbidden. |
| B | Input/context/output/pending limits; bounded Provider timeout; active/global pending capacities and expiry. |
| S/T | Frozen caller-owned nested data; not-before/expiry; exact source/version; duplicate and changed consumption; model-build context remap. |
| C | SQLite source uniqueness/consumption CAS; exact live execution owner; reclaimed owner cannot replace frozen semantics. No claim of full Registry race coverage yet. |
| R | Reopened pending/frozen data, original source anchors and corrupted metadata detection; no serialized authorization grants. |
| F | Timeout/failure, malformed/duplicate/nonfinite output, lost/expired/foreign execution lease. No new old-parser feature flag. |
| K | Optional provenance preserves old binding digest when absent; existing formal queries/mutations and journal tests retained. |
| X | Real SQLite and formal Core/confirmation owners with controlled model/Executor doubles. Not real Provider/Agent-Tool or browser/audio evidence. |

## Commands and attempts

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_task_semantics.py tests/unit_tests/live_voice/test_semantic_pending_context.py tests/unit_tests/live_voice/test_unified_committed_input.py tests/unit_tests/live_voice/test_production_multi_task_resolver_trust.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py -q -o addopts='' -o log_cli=false --tb=short
.\.venv\Scripts\ruff.exe check jiuwenswarm/server/live_voice/task_semantics.py jiuwenswarm/server/live_voice/unified_committed_input.py jiuwenswarm/server/live_voice/production_task_intent.py jiuwenswarm/server/live_voice/p3_authenticated_composition.py tests/unit_tests/live_voice/test_task_semantics.py tests/unit_tests/live_voice/test_semantic_pending_context.py tests/unit_tests/live_voice/test_unified_committed_input.py tests/unit_tests/live_voice/test_production_multi_task_resolver_trust.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py
.\.venv\Scripts\python.exe -m compileall -q jiuwenswarm/server/live_voice/task_semantics.py jiuwenswarm/server/live_voice/unified_committed_input.py jiuwenswarm/server/live_voice/production_task_intent.py jiuwenswarm/server/live_voice/p3_authenticated_composition.py
git diff --check
```

- Early pending review found context-alias mutation, incomplete record digest,
  confirmation target-kind drift, missing not-before check and forgotten expired
  source anchors. All received focused fixes/tests; fix-only review returned
  C0/I0/M0 for that intermediate boundary.
- Provenance test insertion initially displaced three original assertions,
  causing three NameError failures. Original assertions were restored to their
  original test; the complete trust file then passed (34 tests).
- New Native invalid-scope test initially constructed an invalid authority before
  its expected failure block: 1 failed / 8 passed. Passing a wrong session to a
  valid authority exercises the intended boundary; rerun 9 passed.
- Frozen-journal test initially referenced nonexistent `_database`: 1 failed /
  111 passed. Corrected to the existing `database_path`; rerun 112 passed.
- Independent cumulative module review: C0/I1/M0. A normal same-scope project URI
  remap was rejected by formal task.list but leaked old Task facts to the new
  semantic model stub, for both bearer and a newly valid Native activation.
  The red probe reproduced the discrepancy with zero additional Task/Executor
  mutations. Its Windows temporary SQLite cleanup failed after the business
  assertions; this does not change the red finding.
- Fix: check each actual outgoing Task context, then recheck after model client
  construction. Added both authentication routes for remap-before-read,
  remap-in-builder, legal revision advance, expired persisted Task context and
  redacted current context. Also ran the existing exact formal cancel/confirmation
  consumption test through Native authority: 2 passed, no weakened assertions.
- Combined five-file run: **281 passed**, 60.47 s, no skips. After final scoped
  formatting the complete set ran again: **281 passed**, 52.84 s. One Authlib
  deprecation warning. Ruff, Python compilation and diff whitespace checks
  passed; all 137 local file links in the changed active documents exist (this
  check does not validate Markdown heading fragments).
- Independent fix-only review: **C0/I0/M0**, I1 closed. Reviewer independently
  ran the ten-case context matrix (10 passed, 159 deselected), verified exact
  outgoing records and post-builder checks, and accepted the bounded module for
  commit subject to Main's completed regression. This is not final integration
  review or a real speech-path claim.

## Required cutover decision and remaining work

Removing the current Demo bypass exposes an existing input-confirmation gap.
Gateway speech receipts currently require explicit UI `critical_confirmation`
for uncertain critical tokens (including numbers/negation). Registry's input
gate does not make an unconfirmed speech transcript authoritative. Merely
setting `confirmed=True` on CriticalTokenSafetyGate.resolve still reevaluates
SPEECH confidence, so saying yes cannot be relabelled as explicit text.

A pure-voice readback path requires an explicit minimal Tier-3 extension binding
the actually presented readback, original critical input, subsequent verified
final, authorized scope, expiry and valid generation. Its deterministic owner
must issue input confirmation; the model only proposes confirmation semantics.
It does not replace formal P3 operation confirmation. This expansion was raised
with the user and is **not yet authorized or implemented**. No substitute bypass
was added and the old bypass has not been silently removed while the positive
journey would fail.

Other remaining work: Registry single-parser cutover and continuously owned
admission/renewal; presented-Agent proposal creation/recovery; exact target and
normal confirmation integration; Direct fixture/checkpoint/profile retirement;
launcher/Web cleanup; all applicable old oracle migrations; real isolated tasks,
both digital audio routes, final cumulative review and operator physical Demo.

Environment discovery only: Chrome/Edge and installed Chinese/English system
speech synthesis are present. The repo virtual environment lacks Playwright.
The selected in-app browser exposes no test microphone injection capability;
existing isolated-browser capture tooling may be reused. No test audio entered
the production microphone path, and no output audio was observed in this packet.
No system driver, device setting, private credential location or existing service
was changed. The review left only its own isolated diagnostic directory at
`C:\Users\admin\AppData\Local\Temp\semantic-review-xzw8rg6r` after cleanup was
denied; no deletion workaround was attempted.

Overall: **PARTIAL**. HARDCODE_RETIREMENT and SEMANTIC_AND_EXECUTION are incomplete;
AUDIO_E2E_DIGITAL and HUMAN_PHYSICAL_ACCEPTANCE are NOT_RUN;
REGRESSION_AND_REVIEW is scoped only, not final-candidate closure. Historical
evidence is unchanged; no Production-ready conclusion is granted.
