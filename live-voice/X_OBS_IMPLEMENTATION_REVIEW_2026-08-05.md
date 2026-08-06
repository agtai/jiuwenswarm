# X-OBS correlated observability implementation review — 2026-08-05

> This is the bounded implementation and review record for the X-OBS Worker
> package. It does not own current branch status, package scheduling, Replacement
> Ledger credit, or a Week 2/Web Alpha Gate result; those remain with `STATUS.md`,
> the delivery matrix, and the applicable acceptance contract.

## 1. Original request and bounded result

X-OBS extends the committed W1-X1 route vocabulary into a reproducible,
correlated trace/metric foundation without changing Speech, Conversation Runtime,
Agent, Task, presentation, cancel, fence, queue, or fallback authority. The
implementation is an unproduct-wired foundation: it can consume current public
route, browser observer, snapshot, TaskEvent, and durable-outbox facts, but it does
not make the cumulative Integrated route runnable and is not Gate evidence by
itself.

The package is Tier 2 under the Web Alpha delivery matrix. D-053 therefore applies
the three-pass review process. The implementation uses no external telemetry
backend, no credential, and no real service.

## 2. Frozen contract

### Schema and identity

- Schema version is `live-voice.observability.v1`; it is an X-OBS evidence schema,
  not an extension of the accepted ACG v2 authority/wire schema.
- Stable, closed vocabularies cover Speech, Runtime, Agent, Task, route fallback,
  cancel, stale fence, queue pressure, failure, degradation, TaskEvent, and Task
  outbox observations.
- A shared per-event and per-metric semantic matrix defines legal segments,
  required/allowed facts or dimensions, stable values, identity targets, source
  kind, and conditional failure/cancel target mappings. Fields that are globally
  valid but invalid for that event or metric fail closed before collector/sink
  acceptance.
- Every trace and metric carries a required `correlation_id`. Optional exact
  bindings cover `interaction_id`, `turn_id`, `response_id`,
  `response_generation`, `round_id`, `task_id`, and `attempt_id`.
- Turn requires interaction; response requires the complete
  `{interaction_id,response_id,response_generation}` tuple; attempt requires task.
  No identity is inferred from display text, timestamps, another ID, or recency.
- Identity slots use a 128-character ASCII opaque envelope and reject whitespace,
  URL syntax, and obvious credential/content markers. This does not change ACG
  identity authority and is not a content classifier: callers must project only
  authoritative public ID fields. An arbitrary opaque token cannot be proven
  non-secret by this schema, so unsupported identities are dropped from the
  evidence plane without affecting the product path.
- Cancel evidence carries exactly one of `playback.stop`, `response.cancel`,
  `round.cancel`, or `task.cancel` and requires its exact response, round, or task
  target. Stale-generation evidence requires the exact response tuple.
- `observed_at` is caller-supplied RFC3339 UTC evidence time. `monotonic_ms` and
  explicit durations are caller-supplied monotonic facts. A source Event's
  `occurred_at` remains separate as `source_occurred_at`; wall-clock time is never
  used as lifecycle ordering authority.
- A TaskEvent ID remains `source_event_id`; a durable outbox row ID remains
  `source_record_id`. Neither is relabelled as the other kind of source fact.

### Route truth, privacy, and cardinality

- `formal`, `fallback`, `demo_substitute`, `unsupported`, and `unknown` remain
  distinct. Formal requires exact owner/provider/v2 provenance; non-formal routes
  use one closed redacted reason code.
- W1-X1 `safe_reason` free text is never exported. It maps only to
  `ROUTE_FALLBACK`, `DEMO_SUBSTITUTE`, `UNSUPPORTED_CAPABILITY`, or
  `UNKNOWN_PROVENANCE`.
- Trace records have no content, raw-audio, device-label, credential, URL, or
  arbitrary-attribute field. Public route/AIO/Task/outbox mappers deliberately do
  not copy those values. Opaque identity content safety is the trusted-source
  boundary described above, not a claim that the schema can recognize every
  possible secret token.
- Metric dimensions are limited to validated route provenance, stable segment,
  implementation class, terminal outcome, cancel scope, safe reason code, and ACG
  error code.
  Metric implementation class must match its route. Exact identities remain trace
  bindings and are not exposed as an arbitrary metric-label map.
- Metric names, kinds, and units are fixed for segment latency, queue depth/wait,
  cancel, stale fence, task, failure, and degradation. Counters are non-negative
  cross-language safe integers.

### Collector and observation seams

- Python and TypeScript collectors are explicit, bounded in-memory components.
  Each fact type defaults to a 2,048-record limit; a full collector rejects new
  identities without evicting accepted evidence or redelivering duplicates. The
  collectors create no timer, task, network request, external storage,
  Agent/Tool/Task action, Chat/history mutation, audio effect, or lifecycle
  transition.
- Event and measurement identities are idempotent. Same ID/same canonical record
  is one accepted fact; same ID/different record fails closed.
- Optional sinks receive immutable validated records. Synchronous exceptions and
  TypeScript rejected Promise-like results are contained and counted; acceptance
  of the fact and the business path are not rewritten.
- Sink callbacks are invoked after local acceptance and are integration-owned;
  they must be lightweight non-blocking enqueue callbacks. Slow-exporter
  buffering/backpressure is deliberately not claimed by this foundation.
- Disabled collectors return before inspecting input and create no record or sink
  call.
- TypeScript maps the existing W1-X1 route record and AIO-B `BrowserAudioObserver`
  seam. Raw AIO reasons, capture IDs, unit IDs, samples, device counts, and device
  identities are deliberately not copied.
- Python maps exact public `PersistentTaskEvent` and `PersistentOutboxItem` facts.
  TaskEvent details and outbox `FormalTaskSpec`/instruction are deliberately not
  read or copied. Queue gauges accept caller-selected public CR/AB/Task snapshot
  depths plus an exact trace binding.

## 3. D-032 scenario matrix

| ID | Dimension | Required result | Forbidden effect / result |
|---|---|---|---|
| P-01 | Correlated journey | Speech → Runtime → Agent → Task records share correlation while preserving exact turn/response/round/task/attempt bindings | identity inference or rewritten parentage |
| P-02 | Route truth | all five implementation classes remain distinguishable | fallback/substitute/unknown upgraded to formal |
| P-03 | Metrics | latency, queue, cancel, fence, task, failure and degradation definitions validate with fixed kind/unit | arbitrary names, units or label maps |
| N-01 | Invalid identity/time/schema | bounded opaque carrier, complete tuples, valid UTC, closed fields and safe numbers are required | partial record or sink delivery |
| N-02 | Misleading evidence facts | every event and metric enforces its segment, facts/dimensions, values, identity/source target and conditional combinations | contradictory or cross-event evidence accepted |
| B-01 | Privacy/redaction | public mappers omit free route/AIO/Task/outbox content; identities come only from authoritative public ID fields | transcript, instruction, raw audio, credential, URL or device identity copied into a content field or synthesized ID |
| B-02 | Cardinality | only closed metric dimensions and safe tokens exist | user/task/response IDs promoted into arbitrary labels |
| S-01 | Source truth | TaskEvent source time/ID/seq remain separate from observation time; outbox state is observation only | projection mutates Task lifecycle or invents completion |
| T-01 | Duplicate/conflict | concurrent same-ID replay emits one sink fact; conflicts reject | duplicate sink export or last-write-wins truth |
| C-01 | Reentrant sink | accepted inner observation remains deterministic | deadlock, reducer call or authority transfer |
| F-01 | Sink failure | synchronous/Promise failure increments local diagnostic count and product call returns | propagated exception or business-result rewrite |
| F-02 | Queue/failure/degradation | full queue, cancel unknown, stale fence and Provider/Agent/Task failures are explicit | silent drop or success inference |
| F-03 | Flag off | no input inspection, record or sink effect | timer/network/storage/business side effect |
| I-01 | Existing seams | W1-X1, AIO-B, CR-B/AB-B snapshot, P3 TaskEvent/outbox shapes remain unchanged | edits to another package reducer/Core/Adapter |
| R-01 | Restart/durability | collector makes no durability or replay claim; durable task facts retain source provenance | log existence presented as durable or Gate evidence |

Agent, Tool, Task mutation, Chat/history mutation, TTS/audio control, business
cancel, presentation ACK, reducer transition, and external network/storage effects
are zero for every X-OBS factory/collector/helper path.

## 4. Files and ownership

Product/source surface:

- `jiuwenswarm/server/live_voice/observability.py`
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts`
- `tests/fixtures/live_voice_observability_v1/contract.json`

Verification and review surface:

- `tests/unit_tests/live_voice/test_observability.py`
- `jiuwenswarm/channels/web/frontend/tests/liveVoiceObservability.test.mjs`
- this review record

No shared ACG/schema, reducer, Core, Adapter, product entry, feature flag,
`README.md`, `STATUS.md`, decision, roadmap, validation, runbook, showcase, or
Replacement Ledger file is modified.

## 5. Verification evidence

The following deterministic checks have run in the independent X-OBS worktree:

| Check | Result |
|---|---|
| Python X-OBS focused pytest | `33 passed` |
| TypeScript X-OBS strict compile and Node tests | `19 passed` |
| Shared Python/TypeScript fixture and vocabulary parity | `PASS` in both focused suites |
| Existing Python Live Voice unit + fake vertical + formal ED integration | `215 passed` |
| Existing W1-X1 route telemetry | `17 passed` |
| Existing fake P1 + route telemetry | `23 passed` |
| Existing AIO-B + capture processor | `39 passed` |
| Full frontend `tsc` + Vite production build | `PASS`; existing Browserslist-age and large-chunk warnings only |
| Ruff format/check | `PASS` |
| Scoped mypy for Python X-OBS source | `PASS` |
| Prettier for TypeScript/test/fixture | `PASS` |
| Strict standalone TypeScript (`strict`, unused checks) | `PASS` |
| Complete six-file `git diff --check` | `PASS`; expected worktree LF-to-CRLF notices only |

The Python regression command adds `-W ignore::SyntaxWarning` only to permit
collection through the installed third-party `pysbd` package under Python 3.12;
without that command-line override, repository `filterwarnings = error` converts
the dependency's invalid-regex-escape warning into a collection error before any
business test runs. Test selection and assertions are unchanged. A default mypy
invocation also expanded into unrelated repository modules and reported the
existing whole-repository type baseline; the recorded scoped result uses
`--follow-imports=skip` and checks the owned Python source itself.

One preliminary regression invocation used the default Conda interpreter and
stopped during collection because that environment lacks `yaml`; no business
test result was claimed from it. The exact selection was rerun with the prepared
worktree `.venv` and completed with `215 passed`.

The frontend full production build is an affected confidence check, not evidence
that X-OBS is product-wired. No browser/device, Provider, Agent service, Executor,
deployment, or cumulative Integrated route run is claimed.

## 6. Review passes

| Pass | State | Findings, fixes, and limitations |
|---|---|---|
| Integration review of `9c7cdf1d` | `CHANGES REQUIRED` (supersedes prior closure) | Additional adversarial validation showed that globally valid vocabulary values could be combined into semantically false event/metric records and that the privacy text overstated what unbounded opaque identity slots could prove. Specifically, missing audio state, contradictory completed/failure facts, incomplete/wrong Task outbox facts, failure dimensions on latency, and free identity text were accepted. The earlier closure conclusion is withdrawn and is not evidence for this remediation. |
| Remediation implementation self-review | `PASS AFTER FIXES` | Rechecked every event/metric matrix entry and its runtime enforcement, the five reproduced adversarial classes, exact TaskEvent/outbox and cancel/fence/failure targets, bounded identity use at every identity slot, collector-before-sink rejection, flag-off, and the six-file ownership boundary. No remaining self-review finding. |
| Remediation cold complete-diff review | `PASS AFTER FIXES` | Reread the complete final six-file diff from `9c7cdf1d` against the CHANGES REQUIRED request, root `AGENTS.md`, current public seams, forbidden side effects, actual tests, and documentation claims. The old closure remains withdrawn; this is a new post-remediation pass and produced no actionable finding. |
| Remediation independent review | `PASS — equivalent independent review` | Literal product `/review` was unavailable. A separate read-only reviewer agent independently inspected all six files and full matrices/fixture, confirmed `NO ACTIONABLE FINDINGS`, and reran Python `33 passed`, TypeScript Node `19 passed`, status/HEAD/scope, JSON inspection, and `git diff --check`. It did not edit or perform Git writes. Limitations: it used the existing compiled TS focused cache and did not independently rerun strict TS compilation, full regressions/build, real browser/device/Provider/Agent/Executor services, exporter stress, or the cumulative Integrated route; those checks are covered only where separately listed above or remain integration evidence. |

## 7. Integration seam and open evidence

X-E2E/product composition can inject one collector per frontend/backend process and
pass the same authoritative `correlation_id` across the product carrier. It should
map W1-X1 route records with `observationFromRouteRecord`, attach the returned AIO
observer to the existing Adapter option, map public TaskEvent/outbox facts, and
derive queue gauges from CR-B/AB-B/Task snapshots with caller-owned measurement
IDs and clocks. No other Worker needs a reducer change or a new authority hook.

If a future real route cannot expose a public post-commit event/snapshot/outbox
fact, the minimal requested hook is a non-blocking observer callback invoked only
after authoritative acceptance; observer failure must be swallowed and must not
change the authoritative return value.

Still open and owned by integration/release work:

- authenticated product composition and one cumulative Integrated route;
- exporter buffering/backpressure, retention/deletion policy, operational backend,
  deployment configuration, and SLOs;
- immutable candidate trace/benchmark artifacts and real Provider/Agent/Task/Web
  evidence;
- Week 2/Web Alpha scoring and Gate acceptance.

This foundation earns no Replacement Ledger credit and must not be described as a
formal real journey merely because records, metrics, logs, or tests exist.
