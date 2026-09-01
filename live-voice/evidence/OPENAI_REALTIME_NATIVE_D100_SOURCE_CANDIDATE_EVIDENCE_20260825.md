# OpenAI Realtime Native D-103 source-candidate evidence — 2026-08-25

## Scope, source and disposition

- Capability: OpenAI Realtime Native Interaction Engine, including its
  response-scoped streaming correction and close/compensation lifecycle.
- Risk: Tier 3.
- Integration baseline:
  `1742c1b4e5fa5e7a25a7b41dad9c8eef8453e3cc`.
- Accepted D-103 correction base:
  `a4492089b0ea7c41e9867cfa2df052e5820477e4`.
- Frozen source candidate:
  `944a1e72addeca67dbb53ec06d7801d5ddf2d232` on
  `codex/openai-realtime-native-interaction-engine`.
- Disposition: **SOURCE/AUTOMATION GATE PASS `C0/I0/M0`; REAL OPENAI
  PROVIDER/DEVICE/HUMAN GATE `NOT_RUN`**.

This result closes only the D-103 source, deterministic automation and
independent Tier-3 review boundary. Cascade remains the ordinary default. No
remote ref was updated, and this evidence grants no physical audibility,
product-readiness, Production, public deployment, Provider/model/billing or
general latency credit.

## Candidate history and review convergence

The pre-correction candidate
`0a1a5d36e851998e5fe384c48302f7b446f52d12` remains an immutable
`C2/I5/M0 — FAIL`. After the user selected D-103 solution A, the correction was
kept as reviewable local commits:

| Candidate | Local commit | Independent result | Disposition |
|---|---|---|---|
| first correction | `5c2fa5dc` — `fix(live-voice): close native realtime lifecycle gaps` | `C0/I5/M0` | failed; all five Important findings repaired in the next candidate |
| second correction | `f8ca9b95` — `fix(live-voice): close native candidate review gaps` | `C0/I3/M0` | failed; three newly exposed teardown races remained |
| frozen candidate | `944a1e72` — `fix(live-voice): close native teardown races` | `C0/I0/M0` | source/automation PASS |

The final three repairs establish capacity reservation synchronously before a
revoke can admit a successor, retain separate truthful Runtime and Provider
close completion with one stable retry identity, and keep a failed Agent close
in a quiescing state where only the exact close retry can proceed. The final
cold review also rechecked that the earlier bounded downlink, activation CAS,
close-capacity deduplication, exact Agent close identity, and 149/150/151 frame
findings remained closed.

## Automated verification

All commands ran in the frozen candidate worktree. The main verification and
the independent reviewer both observed a clean worktree at exact HEAD
`944a1e72addeca67dbb53ec06d7801d5ddf2d232`.

| Boundary | Command/result |
|---|---|
| Directly changed backend boundaries | `pytest tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/live_voice/test_product_composition_registry.py` — **269 passed** |
| Cumulative affected backend | `pytest` over Web channel status, dedicated media registration, Native Runtime client, Native response downlink, Agent conversation Runtime, Native interaction Runtime, OpenAI Realtime Native Engine and Product Composition Registry — **445 passed** |
| Independent close/race focus | reviewer-selected first-round regressions plus the three final repairs — **9 passed** |
| Native frontend contract | `npm.cmd run test:live-voice-native-interaction` — **104/104 passed** |
| Browser dedicated media | `npm.cmd run test:live-voice-browser-dedicated-media` — **27/27 passed** |
| Build profiles | `npm.cmd run test:live-voice-build-profiles` — **2/2 passed** |
| Integrated Web | `npm.cmd run test:live-voice-integrated-web` — **486/486 passed**, including the actual 150-frame route |
| Production frontend build | `npm.cmd run build:live-voice` — **PASS**, 4,650 modules; only the pre-existing i18n/import/chunk warnings remained |
| Python lint | Ruff over the cumulative changed source/test surfaces — **PASS** |
| Applicable clean typing boundary | Mypy with skipped external imports over five Native source files — **0 issues**; no whole-repository typing claim is made |
| Python bytecode compilation | `python -m compileall -q jiuwenswarm/gateway/live_voice jiuwenswarm/server/live_voice` — **PASS** |
| Frozen diff integrity | `git diff --check a4492089..944a1e72` — **PASS** |

The cumulative backend and frontend totals are 445 Python tests and 619
frontend tests. Whole-repository line coverage was not used as closure credit;
the formal evidence is the applicable Tier-3 scenario matrix and exact
authority/effect assertions.

## Tier-3 evidence summary

- Positive and integration paths prove one response owns one bounded async
  source, notification, ticket and socket; 150 frames remain individually
  Runtime-admitted and settle one exact presentation prefix.
- Negative, cross-scope and replay paths reject malformed, stale, foreign,
  over-capacity and changed-identity input without Agent, Tool, Task, history,
  ledger or other-scope effects.
- Boundary and capacity tests cover 149/150/151 frames, full queue, first/last/
  zero/missing cursor and a capacity-one immediate successor before any event
  loop yield.
- State, temporal and concurrency tests cover both history settlement orders,
  speech-start timing, duplicate interruption, retained writer retry,
  Runtime-fail/Provider-success close, Provider-incomplete close and exact close
  replay.
- Fault and lifecycle tests cover activation observer failure, transactional
  compensation, bounded backpressure, late Provider events, autonomous history
  drain, quiescing after close failure and truthful retained capacity.

The independent cold review inspected the complete
`a4492089b0ea7c41e9867cfa2df052e5820477e4..944a1e72addeca67dbb53ec06d7801d5ddf2d232`
range, reran focused and cumulative checks, found no Critical, Important or
Minor issue, and concluded **`C0/I0/M0 — PASS`**.

## Remaining independent Gate

Real OpenAI credentials, Provider/model availability, project registration,
network state, browser permissions, microphone/speaker selection and human
audibility are machine-private and are not restored or proven by Git. A later
real-path run must bind its own exact source and sanitized evidence. Until that
run occurs, the following remain explicitly `NOT_RUN`:

- real OpenAI Realtime Provider session and degradation behaviour;
- real microphone capture, speaker playout, barge-in and stop-to-silence;
- human confirmation of committed Jiuwen Agent/Tool/Task behaviour and audible
  output.

Those items neither receive credit from this source Gate nor invalidate its
bounded `C0/I0/M0` result.
