# D118 — Unified hands-free Live Voice implementation review

Date: 2026-08-16

> **Historical pre-D119 candidate snapshot.** This record intentionally
> describes the unified hands-free implementation while its reviewed diff was
> still uncommitted. It is not the current branch/candidate status and does not
> include the later running-adjustment and terminal-notification batch. Read
> [STATUS](STATUS.md) for current facts and [D119](D119_RUNNING_TASK_ADJUSTMENT_AND_TERMINAL_NOTIFICATION_REVIEW_2026-08-16.md)
> for the successor candidate-specific review.

Stage / target node: S8 / A3 implementation candidate

Tracks / modules: Shared-X, P1, P2, P3alpha; Web integrated owner, Gateway,
AgentServer, Task Bridge/Core/Store and Direct Executor

Risk tier: Tier 3 — protocol, authority, mutation, concurrency and durability

## Scope and non-scope

This review covers the uncommitted diff based on
`14d5529d75e9228af8d2e306dcb20f3ac8180aa5` on
`hx/0812_live_voice_w3`. It replaces the visible Agent/Task command center with
one continuously listening entry and one internally managed current background
Task. It introduces an independent committed-input protocol and journal, Task
Store schema v3 current/result state, authoritative Task-result publication,
the existing P2 presentation bridge, and the mounted itinerary journey.

The batch does not add parallel background-Task management, change the existing
`p2.submit(agent|task)` or `task.status/events` protocols, remove the default
production confirmation boundary, add production authentication, deploy a
public service, or move/store provider credentials. Route Facts are not a
product dependency.

## Closed contract matrix

| Boundary | Required evidence | Result |
|---|---|---|
| Committed speech | Only authoritative ASR final may enter unified submit; partial/interim has zero Agent/Task/presentation effects | Automated pass |
| Pre-parse authority | Current P2 activation, Session and Gateway voice claim/receipt validated before semantic routing; stale/wrong identities have zero business effects | Automated pass |
| Replay/conflict | Same voice identity replays the original result; same request or voice identity with different content conflicts; pending work is leased and recoverable | Automated pass |
| Semantic routing | Closed `dialogue`, `background.create/query/status/cancel`; negated cancellation has zero cancellation/mutation; itinerary planning maps to create | Automated pass |
| One current Task | Pointer bound to subject + project + Session and restored from Store; active current Task blocks replacement; two concurrent creates yield one Task/attempt/outbox | Automated pass |
| Demo policy | Explicit trusted backend flag authorizes create/cancel confirmation bypass and exact-final critical-speech clarification bypass only in the isolated Demo; neither is a user confirmation or fake receipt; scope/idempotency/target/mutation authority remain enforced and the default remains confirmation-required | Automated pass |
| Flag/permission failure | Background intent returns explicit unavailable; no Full Access Agent fallback and no Task side effect | Automated pass |
| Result states | Closed `available/not_ready/unavailable`; only current, exact-scope result is readable; not-ready/unavailable never enter Agent | Automated pass |
| Result durability | Executor journals bounded `chat.final` and candidate artifact facts before apply; successful apply seals path/SHA; completed source event is idempotently replayed into terminal TaskEvent + immutable result | Automated pass |
| Result safety | UTF-8 and size/count/path bounds; absolute, drive, UNC, traversal, NUL and escaping symlink rejection; no result/path/content in ordinary logs; Agent receives untrusted reference context only | Automated pass |
| Presentation | Dialogue/query delegate to the existing P2 Agent facade; create/status/cancel/not-ready/unavailable use the same response/notification/presentation-ACK/TTS owner; Task Bridge does not call TTS | Automated pass |
| Spoken truth | create accepted says started; cancel accepted says stop requested; only terminal cancelled says stopped; status comes from Task Store | Automated pass |
| Continuous loop | One capture coordinator; Agent/Task presentation completion resumes capture; background execution does not block the next turn; Exit fences late callbacks; re-enable starts a new generation | Automated pass |
| Barge-in | Real server speech-start/EOT while playing stops the current P2 response/TTS and produces zero Task cancel/mutation | Automated pass |
| Visible UI | Enable/status/transcript/Exit retained; Send, Agent/Task, operation and Task-ID controls absent; bilingual mounted checks | Automated pass |
| Real itinerary artifact | Isolated Git fixture writes `itinerary.md`; Store result, applied bytes/SHA and Agent answer agree on the real 08:30 fact | Automated pass |
| Compatibility | Existing P2 submit modes, P2 journal/recovery and Task status/events remain compatible; v2-to-v3 migration does not guess a current Task | Automated pass |

## Verification record

- `npm.cmd run test:live-voice-integrated-web`: `372 / 372` passed. The command
  runs the complete integrated Live Voice Web test set, including the mounted
  five-turn itinerary script, visible-control assertions, final de-duplication,
  loop/Exit behavior and EOT-driven barge-in.
- Seven backend suites covering Task Core, Store/Executor, Bridge, unified
  owner, registry, authenticated P3 composition and real Gateway receipt
  issuance: `541 passed, 2 skipped` in 139.98 seconds. The two skips are
  existing conditional cases; one existing Authlib deprecation warning was
  emitted.
- Gateway and AgentServer routing suites: `222 / 222` passed.
- P2 runtime, Bridge, adapter and formal Agent regression suites: `158 / 158`
  passed.
- Focused unified journal rerun after the review hardening: `14 / 14` passed.
- All changed/untracked Python sources compiled successfully.
- Formal production build with `INTEGRATED_WEB`, `INTEGRATED_P1` and
  `PRODUCT_P3_MUTATION` enabled: passed, `4,642` modules transformed. Existing
  Vite chunk/dynamic-import warnings remain.
- `git diff --check`: passed for the complete implementation diff before the
  final review-record update and is rerun at handoff.

## Implementation self-review findings

The implementation review found and corrected material issues before this
record: applied artifact SHA under Git `autocrlf`; duplicate execution of an
unexpired same-process unified admission; non-durable post-admission definitive
failure results; direct access to a non-current Task result; missing
connection-level SQLite foreign-key enforcement; incomplete explicit evidence
for the default non-Demo confirmation boundary; mismatched frontend/backend
Unicode and UTF-8 submit limits; a missing `TerminalOutcome` import on terminal
status/cancel narration; and exception text that could expose a path in an
unified failure result. Each correction has a focused regression test or an
affected-suite rerun, including orphan-binding rejection, default cancel with
zero mutation, exact text-boundary cases, terminal cancelled narration, and
sanitized unexpected failures.

The final durability review also corrected the Agent handoff seam. A failed
post-dispatch SQLite checkpoint now synchronously revokes the exact still-
pending Bridge dispatch and still-unstarted Harness round before the event loop
can run Agent, Tool, history or notification effects. A recovered row that has
only the pre-dispatch marker is safe to dispatch once; a row with the exact
durable `round_accepted` result replays that result without a second dispatch.
`round_accepted` retains its existing P2 meaning: it proves accepted control
ownership, not eventual Agent completion after the entire process is lost.

No finding was waived. Any subsequent finding must be fixed and its affected
tests rerun before this candidate can be handed off.

## Cold review and independent review

Main completed a cold review of the complete scoped diff. The literal `/review`
command is unavailable in this environment, so a separate read-only review
agent performed the Tier-3 independent-review equivalent over the full
tracked and untracked implementation. Its findings covered untrusted-result
tool isolation, authority failure narration, foreground crash recovery, result
schema parity, capture lifecycle races, Gateway critical-token policy, Direct
Executor cancel/apply durability and documentation truth. The findings were
fixed and the affected checks rerun; the final independent result was **PASS**,
including acceptance of the Agent handoff correction, with no remaining code
blocker. This substitute is
not a physical browser/provider review and does not change the pending physical
acceptance below.

## Physical browser acceptance and cleanup

Physical browser/microphone acceptance is `BLOCKED BY LOCAL PRIVATE RUNTIME
CONFIGURATION`, not passed. A read-only check found no Speech provider or
product/Demo variables in the current process and no listeners on the expected
ports. Credentials are machine-private and must not be requested in chat,
logged, copied, committed or moved.

When a protected terminal has restored the provider settings, use a disposable,
clean Git fixture and an isolated `JIUWENSWARM_DATA_DIR`, explicitly enable the
formal flags plus the trusted backend Demo policy, and run the exact itinerary
journey documented in the runbook. Acceptance must compare the Task Store
result, Agent-spoken fact and final `itinerary.md` bytes/SHA. Stop all services,
verify leases/outbox settlement, then remove only the resolved disposable
fixture and isolated data directory (or move them to the Recycle Bin). Never
clean the source worktree or an unresolved path recursively.
