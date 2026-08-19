# P3-8A observability assets review — 2026-08-19

> Status: **PASS — SCOPED P3-8A ADDITIVE ASSETS ACCEPTED.** The content-free
> SLI calculator, declaration-only telemetry privacy profile and source-bound
> OTel backend codec pass current-source Tier-3 review with no remaining P1/P2.
> They are not composed into the product and grant no P3-8, product-readiness,
> exporter, SLO or Production operations credit.

## 1. Baseline, dependency and scope

- Git baseline: `376798c8333610d8785d2b2fdd4e19df06c9a270` on
  `hx/0812_live_voice_w3`.
- Dependency: accepted P3-1 canonical Task source
  `d40e0ee391fdf162faa9d9938eb9b9610020c1a7` is already in the current branch.
- Historical extraction input: `ca3d7780` was inspected but **not
  cherry-picked**. Its SLI/privacy ideas were re-extracted; its OTel projection,
  old review disposition and old test counts were not accepted as evidence.
- Capability owner: existing Live Voice observability record boundary. Risk:
  Tier 3 under root `TESTING.md` because telemetry privacy and backend-visible
  fact integrity are security/diagnostic trust boundaries.
- Intended commit: `feat(live-voice): prepare P3-8A observability assets`. The
  candidate is the exact coherent delta over the baseline above that contains
  this review.

## 2. Review findings closed

| Rejected `ca3d7780` condition | Current-source closure |
|---|---|
| An OTel record could be changed and still pass validation | The codec emits canonical ASCII JSON plus a payload digest, exact attribute-key metadata and a canonical source fingerprint. Validation reconstructs the record from the exact current `LiveVoiceObservation` or `LiveVoiceMetric` and trace context; coherent and incoherent record mutations fail. |
| Required attributes were not closed | Span/metric base requirements and the immutable route-class-specific required sets are explicit; the global allowlist, signal-specific exclusions, exact top-level fields and exact stored attribute-key tuple all fail closed. Missing, cross-class and unknown attributes are rejected even when an attacker recomputes canonical bytes and the payload digest. |
| Timestamps received shape-only validation | The codec reuses the current observability owner's UTC validator, including real calendar construction. Non-leap February 29, month 13, hour 24 and year 0000 are rejected. |
| Private-carrier detection was weaker than the current product owner | The product adapter's existing URL, non-hierarchical scheme, query/delimiter, secret, transcript/raw-audio and device-identity rules now live once in the observability owner. The unchanged adapter and the new codec consume that same function. |
| The old review contained incorrect test counts | No old count is inherited. The exact final candidate command below reports **207 passed**. |

## 3. Implemented facts

### OTel backend codec

- Accepts only exact current public observation/metric records and revalidates
  them through their existing constructors before encoding.
- Emits one closed span-event or metric-point payload. It does not accept
  arbitrary attribute dictionaries and does not expose prompt, transcript,
  TaskResult, artifact, credential, raw-audio or device content.
- Binds an observation to exact non-zero lowercase OTel trace/span identities
  and the observation correlation identity. Metrics cannot carry trace fields.
- Returns immutable canonical bytes for a later injected backend. It does not
  collect, enqueue, export, persist, call a network, mutate lifecycle state or
  change a business result.
- Feature-off returns before touching the supplied fact or trace object.

### SLI and privacy assets

- The SLI calculator accepts only bounded, content-free numeric/boolean samples,
  validates window identity/time/sequence/kind, treats identical replay as
  idempotent and rejects conflict, gaps and out-of-window data. It claims no
  threshold, alert, exporter or SLO authority.
- The telemetry privacy profile has one explicit disposition for every closed
  data class. Command input, result content, blocking input, artifact detail,
  credentials, raw audio and device identity are prohibited; the evaluator is
  declaration-only and claims no runtime scanning or enforcement.

## 4. D-032 and zero-effect evidence

- `P/N/B`: valid observation, metric, latency and ratio cases succeed; malformed,
  over-bound, missing, conflicting, unknown, private or wrong-kind inputs fail
  closed.
- `S/T`: the pure functions own no lifecycle state or scheduler time. Stored
  timestamps use calendar-valid UTC facts, SLI sample windows use explicit
  bounded integer times, and no wall-clock lookup is performed.
- `C`: no shared mutable state, lease, queue or transaction is introduced; the
  concurrency dimension is scoped out for these immutable pure functions.
- `R/I`: record and SLI-result replay is recomputed from exact inputs. Source,
  trace, record, schema, attribute, digest and window/sequence identities are
  bound; forged or mismatched inputs fail.
- `F/K`: feature-off is zero-touch. Existing product adapter, exporter,
  observability, fault-harness and backend/Web privacy regressions pass after
  the private-carrier owner consolidation.
- `X`: no runtime composition or exporter exists in this tranche, so a real
  external OTel/backend path is explicitly scoped out and cannot receive
  product credit.

Rejected paths assert or structurally guarantee zero exporter, network,
persistence, lifecycle, business-result, audio, Agent, Tool or Task effect.

## 5. Exact current-source verification

| Boundary | Exact result |
|---|---|
| TDD RED | `.\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q tests/unit_tests/live_voice/test_observability_otel_codec.py tests/unit_tests/live_voice/test_p3_8a_sli_privacy_contracts.py` before implementation — **35 failed** because all three new production modules were absent; no collection or environment error |
| Required-set TDD RED/GREEN | Before the route-class closure, the targeted omission cases reported **4 failed, 5 passed, 21 deselected**; after the fix, the expanded targeted set reported **11 passed, 21 deselected** |
| Final focused plus affected regression | `.\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q tests/unit_tests/live_voice/test_observability_otel_codec.py tests/unit_tests/live_voice/test_p3_8a_sli_privacy_contracts.py tests/unit_tests/live_voice/test_observability.py tests/unit_tests/live_voice/test_observability_exporter.py tests/unit_tests/live_voice/test_observability_fault_harness.py tests/unit_tests/live_voice/test_product_observability_adapter.py tests/unit_tests/live_voice/test_alpha_privacy_conformance.py tests/unit_tests/test_app_web_live_voice_privacy.py` — **207 passed** |
| Python static | Ruff check over the **7** changed Python source/test files — **PASS**; Ruff format check — **7 files already formatted**; `python -m compileall -q` over the same files — **PASS** |
| Git whitespace | `git diff HEAD --check` — **PASS** |
| Independent Tier-3 cold review | Read-only complete changed-code/test review via local Codex CLI — **PASS: `NO P1/P2`** |

No frontend, build-profile, runtime composition or deploy file changes in this
tranche. A product build or physical OTel journey would not exercise these
uncomposed Python assets and is therefore scoped out rather than claimed.

## 6. Disposition and remaining work

The P3-8A additive asset tranche is accepted within this exact pure-code
boundary. P3-2 remains the active primary execution package and may continue.

P3-8 remains `PARTIAL`: a later package must compose the codec behind the
existing product observability adapter/exporter, add validated backend
configuration and lifecycle/health behavior, instrument the required
Task/Attempt/Command/activation/generation/ACK/Executor seams, prove useful
diagnostics without private content, and complete P3-8B authority retirement
after P3-7. P3-9 owns cumulative automated and physical product acceptance.

## 7. Explicit exclusions

No OTel SDK/exporter, backend call, exporter retry/queue, runtime activation,
profile or environment configuration, persistence, SLO threshold/alert,
retention, production authentication/tenancy, P3-2 Task command work, P3-7
formal carrier composition, P3-8B retirement, P3-9 journey, P1/P2 continuation
repair, `develop` integration, remote update or push is included or claimed.
