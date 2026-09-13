# Shared runtime and voice ownership integration

## Accepted scope

User-authorized execution on `hx/0912_livevoice`, baseline
`cedb4e1b3f18c7dfe2f290de10bcfec9d06aaa38`. Use the twelve commits
`537c5d2..9e91f326` as implementation material, preserving the current official
develop runtime and ASGI media repair. Produce one new local commit only after
verification and review; no remote update is authorized by this packet.

Live Voice owns audio capture/transport, speech providers, speech turns,
playback and presentation acknowledgments. JiuwenSwarm owns business tasks,
work execution, permissions, history, persistence and shared result facts.
AgentCore owns reusable low-level Agent/Tool execution primitives. Host core
must not depend on voice implementations. Moving files alone does not close
this scope.

## Implementation and acceptance

- [x] Move conformance/fake/retired executors to explicit test support.
- [x] Move durable and formal-task services to Host; remove voice contract and
  source-identity reverse dependencies while preserving serialized data.
- [x] Separate frontend controller/view; put shared task operations under
  shared ownership and retain audio-specific operations in the voice feature.
- [x] Route real voice Agent work through the existing AgentRuntime, preserving
  Plan, admission, permissions, session generation, model configuration and
  cancellation settlement. Reuse the existing Runtime stream, admission and session coordinator.
- [x] Resolve required SDK contracts against the current official SDK baseline;
  never substitute no-op guards or regress the dependency graph.
- [x] Give shared work, task results/history and diagnostics their actual Host
  owner; reduce the voice composition to transport and projection adapters.
- [x] Move remaining production voice modules to channels/live_voice; remove
  the old server/live_voice implementation directory and update consumers.
- [x] Run affected tests, package build, dependency-direction/import checks and
  independent integration review; repair findings and record evidence.
- [x] Review final diff/status and create one new local integration commit.

## Risk and verification

Mechanical moves and unchanged extractions are Tier 0. Voice integration and
frontend operations are Tier 1/2. Shared execution, permission/source identity
and persisted contracts are Tier 3. Existing Task IDs, revisions, serialized
records, scopes and result facts remain compatible; no runtime-data rewrite.
For the Tier 3 seams, exercise positive execution, rejected/stale/cross-scope
zero effects, cancellation/order/concurrency, recovery and existing Runtime
consumers. Preserve ASGI media origin/subprotocol checks, Plan and permission
continuation. Use focused existing suites plus tests for new integration seams.

Private configuration, provider selection, production data and existing
processes are excluded from mutation. This is code integration acceptance,
not a new physical audio/user-perception or latency acceptance claim.

## Evidence

Code integration verified and independently reviewed. Inherited baseline failures
remain explicit below; this is not full-product or physical audio acceptance.

## Source selection and ownership

Adopted the behavior-preserving parts of `f437557c`, `f3b17e13`, `2abc2338`,
`e093b12d`, `3857b626`, `e0b52ed9`, `73fa3839` and `ea449432` without individual
commits. Reimplemented the useful `bfef5060` execution integration against the
current AgentRuntime. Replaced `f5d2bf39` dependency preservation with frozen,
inexact sync of the current official lock, without replacing the SDK. Historical
planning/final-report commits are evidence, not current execution authority.

- `server/runtime/formal_tasks`, `work`, `authority`, `presentation`,
  `agent_adapter` and the existing durability module own shared services.
- `common/schema` owns stable interaction/source contracts; `common/telemetry`
  has no Host dependency. Task telemetry projection lives in Host.
- `channels/live_voice` owns Native/cascade speech, transport, activation,
  presentation acknowledgments and channel composition. It borrows one Host
  Work service per canonical database; stopping speech does not cancel accepted
  Work. Only AgentRuntime settles/closes its Work service.
- Formal Agent execution uses the same Runtime admission and session coordinator
  through a trusted producer seam. The exact isolated SDK session, source,
  model and tool policy remain bound; public Chat mode/Plan/history are not
  overwritten. Wire metadata cannot select this seam.
- `features/tasks`, `stores/formalTaskStore` and `types/interactionContractV2`
  own shared frontend Task state, control and projection. Voice presentation
  uses these owners. Fake replicas and retired executors live in test support.

No serialized keys, public RPC names, SQLite schema or private data were migrated.
There is no compatibility production copy at `server/live_voice` and no Python
production code in the top-level `live-voice` documentation directory.

## Review findings and resolution

Independent review identified activation wrappers adopting a later generation,
wrong tool-session gate access, Host work cleanup ownership, creation/close
races and generation-cache exhaustion. Repairs bind the activation generation,
prepare exact tool sessions, retain unsettled cleanup/pins, serialize creation
and close on one lock, and reclaim only settled idle predecessors. Positive,
wrong-source/scope, tombstone, in-flight generation change, cleanup failure and
35 consecutive reopens are covered. Final independent re-review closed the
Work race and cache findings and found no additional duplicate business owner.

The official SDK stays at 0.1.17 (`b5f189ba`); no custom 0.1.16 downgrade or
no-op guard was introduced. Its existing Responses/GPT compatibility guard is
retained: direct audit found actual tool-history/metadata compatibility gaps,
so removing the guard would be false compatibility. This refactor keeps the
existing DeepSeek execution route; a new GPT SDK repair is outside scope.

## Test maintenance

Updated moved imports/compiled test paths and injected a real Host Runtime into
execution fixtures. The send-file test now installs the real Runtime push host.
Quiet accepted/running Task facts still project into the shared arbiter while
remaining ineligible for spoken notifications; Store recovery oracles include
those facts. A UTF-8 BOM keeps the touched Windows launcher readable by
Windows PowerShell 5.1 as well as PowerShell 7.

Removed ten mounted checks for a natural Task form already absent in baseline
`cedb4e1b`; did not restore the retired UI. Current mounted unified typed
confirmation/recovery, historical Task selection and shared Task owner tests
retain exact-target, unknown-result, retry and stale-scope scenarios. Static
entry checks now cover the current stop control, including the fault audio tail.

## Size measurement

Tracked Python physical lines (including comments and blank lines), compared
with `cedb4e1b`: old `server/live_voice` 92 files / 123,051 lines; new
`channels/live_voice` 41 files / 55,164 lines. This is ownership reduction,
not a claim that 67,887 lines of capability were deleted: shared Host services
and test-only conformance implementations moved to their proper owners.

## Inherited regressions

The broad regression run exposed baseline failures outside the changed module
semantics. An external `git archive cedb4e1b` snapshot with its original source
and tests, the same `.venv`, isolated `PYTHONPATH` and no private configuration
reproduced the first 22 selected failures with matching first assertions.
They concern Native refresh, nested result formatting, endpoint defaults and
retired classification/entry fixtures. Current scope does not repair these
previous product/SDK semantics or claim a fully green pre-existing suite.

## Verified integration boundaries

- TypeScript `tsc --noEmit` and Vite `build --mode live-voice` passed; build
  output was external, leaving deployed assets untouched.
- Frontend contract tests passed. Final integrated web run: 706 passed, zero
  failures, one pre-existing skip. The separately registered home-start script
  passed 11; its button oracle selects accessible names instead of positions.
  Automated script discovery also passed after including that existing suite.
- Runtime/ASGI/lower formal integration: 345 passed plus an obsolete send-file
  host fixture failure. After updating it, the lower formal/launcher/import
  ownership/L0 group passed 110, with five existing platform skips.
- Final Host Work / RuntimeService: 88 passed; formal source/generation/tool
  ownership tests also passed. Independent review closed the lifecycle findings.
- Semantic/native business/audio fallback group: 111 passed plus a missing
  second-turn source ID in a legacy fixture; the corrected exact two-turn test
  and migration manifest then passed 12. Deferred voice/text ACK tests passed
  two after their explicit Host fixture injection.
- Shared Task progress/recovery tests passed in the repaired regression run;
  no schema or data conversion was needed.

Wide regressions and external baseline comparison are recorded separately from
these owned-boundary results; counts are not added across overlapping runs.

Registry wide check: 180 passed, 55 failed. All 55 failures were independently
reproduced with matching first assertions on the unmodified baseline snapshot
(11 in the initial batch, then 23 and 21). The only two baseline-pass/current-fail
Task ACK fixtures were fixed by injecting Host Runtime and passed separately.
External baseline comparison files remain outside Git; no failed checks were
silently skipped or marked xfail in the production test suite.

Final post-Registry regression group: 1,310 passed, two existing skips; the only
failure was discovery of the unregistered home-start suite, fixed and rerun
successfully. In total, 68 failure candidates received isolated baseline review:
66 reproduced identically on `cedb4e1b`, while two Runtime fixture regressions
were repaired and passed. No unexplained new regression remains in this scope.
The remaining inherited failures are retained as failing tests, not suppressed.

### Reproduction and handoff

Use the repository `.venv` and frontend `node_modules`. Python checks use
`python -m pytest <paths> -q --no-cov -o log_cli=false --tb=short --show-capture=no`.
Owned groups are `tests/unit_tests/runtime`, the formal adapter file in
`tests/unit_tests/agentserver`, the ASGI Live Voice channel file, launcher and
ownership checks, plus `tests/unit_tests/live_voice`. Broad Live Voice checks
were split around `test_product_composition_registry.py`; Task progress and
semantic/native business groups ran separately. Overlapping counts are not
summed. The baseline comparison uses the same commands and selected node IDs
against the external `cedb4e1b` archive, with no private config or SDK edits.
Frontend package scripts are `test:live-voice-contract-v2`,
`test:live-voice-integrated-web`, `test:live-voice-home-start`,
`test:task-notification-identity` and `test:task-notification-timeline`; the package
typecheck and production Live Voice build also passed.

Final source is the single integration commit containing this record. Private
configuration, runtime data, running services and deployed build artifacts were
not changed. The commit is local; no push is authorized by this packet.
