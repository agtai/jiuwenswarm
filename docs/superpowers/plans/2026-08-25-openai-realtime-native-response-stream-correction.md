# OpenAI Realtime Native Response Stream Correction Plan

> **Execution:** Follow `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:systematic-debugging`, and `superpowers:verification-before-completion`.
> The current session owns implementation and local integration; no remote ref update is authorized.

**Goal:** Correct the failed `0a1a5d36` Native candidate so sustained Realtime audio,
barge-in, history settlement, delegate transport, close ownership, per-turn response
authority, and activation compensation satisfy D-103 without changing the public
Browser protocol or creating a second business authority.

**Risk:** Tier 3. The changed boundary crosses dedicated media, Runtime generation and
presentation authority, internal Gateway→AgentServer carrier, canonical history,
Provider lifecycle, and browser playback fencing.

**Dependencies:** Existing Native v1 contract, D-102's three internal methods and
`native.audio` variant, Runtime presentation ledger, dedicated-media async source,
Agent/Task bridges, authenticated P2 activation, and the shared Realtime session kernel.

## Intended behaviour

1. One Provider response creates one P2 notification, one media ticket, one WebSocket,
   and one bounded async source. Every normalized 20 ms frame remains independently
   Runtime-admitted and maps one-to-one to a browser media sequence.
2. The descriptor uses existing fields with `streaming=true` and `frame_count=null`.
   The final browser receipt maps to the last played Runtime unit and one ACK completes
   the contiguous prefix.
3. Speech-start is retained before the first frame and between frames. A real played
   cursor permits Runtime fence → Provider cancel → exact truncate; no cursor permits
   only Browser/Runtime/Gateway/Engine local fencing and late-output discard.
4. Provider done and presentation ACK reconcile in either order. Once eligible, an
   AgentServer-owned bounded writer task retries without requiring another Browser call.
5. Delegate uses a 30 s method-specific internal deadline. Timeout-after-effect,
   cancellation and replay remain exact and idempotent.
6. Incomplete Provider close retains one bounded owner and capacity until truthful
   finalization. One turn admits only one direct response; a delegate successor requires
   explicit pending binding. Activation failure performs idempotent exact-scope
   compensation through the existing close method.

## Owned surfaces

- Gateway Native session composition, downlink source/queue/receipt mapping and retained close owner.
- AgentServer Native internal carrier, Runtime adapter, history reconciliation and activation compensation.
- Native Engine response consumption and stale-output fences.
- Integrated Web `native.audio` parsing and playback fences using the existing notification/media schema.
- Focused Python/TypeScript tests and affected cumulative Cascade regressions.
- D-103 decision, architecture overlay, STATUS and final sanitized evidence.

## Explicit exclusions

- No new Browser RPC, notification kind, media frame/control, WebSocket subprotocol or public schema.
- No fourth internal Native method; only closed variants inside `native.presentation_ack` and `native.close`.
- No `TurnCommit`, SQLite, P3 command, media-v1, Task or canonical history schema migration.
- No second Runtime, classifier, session, Task, history or presentation authority.
- No Provider-direct Jiuwen Tool/MCP/Task mutation and no silent fallback to Cascade.
- No full-response buffering before first audio, per-frame ticket fan-out, public deployment,
  remote ref update, or real Provider/device/human claim before `C0/I0` source review.

## Tier-3 test matrix

| Dimension | Required evidence |
|---|---|
| P — positive | 3 s/150 frames: one notification/ticket/socket, ordered playback, final prefix ACK; delegate >5 s and <25 s succeeds. |
| N — negative | malformed/stale/cross-scope frame, receipt, response, close and activation facts fail closed with zero forbidden effects. |
| B — boundary | queue capacity, first/last/zero cursor, 149/150/151 frames, deadline edge, final ACK edge. |
| S — state | response NEW→STREAMING→SEALED/FENCED/CLOSED; history done/ACK both orders; close owner lifecycle. |
| T — temporal | speech-start before-first/between/after-last, concurrent done/created, timeout-after-effect, close during retry. |
| C — concurrency | producer/consumer backpressure, duplicate speech-start, activation/revocation, repeated close and shutdown races. |
| R — replay | unchanged request/receipt/cancel/close retries are idempotent; changed replay is rejected with zero effects. |
| I — integration | real Runtime ledger + internal carrier + dedicated-media async leaf + Integrated Web playback; no synthetic owner substitution. |
| F — failure | media observer/socket/writer/Provider close failures preserve primary failure and perform bounded cleanup. |
| K — capacity | bounded source queue, response registry, history retry and close owner; no per-frame notification/socket growth. |
| X — cross-scope | foreign activation/response/generation/unit/cursor/capability cannot mutate current or other routes. |

## TDD task and commit boundaries

### Task 1 — Response-scoped async source and sustained playback

- Write RED tests for 150 Provider frames, one route allocation, ordered async emission,
  bounded backpressure, final receipt→last Runtime unit mapping, stale/overflow zero effects,
  and zero Cascade STT/TTS calls.
- Implement the smallest response source and generalize the existing downlink async-source
  protocol without changing media v1.
- Update Native notification parsing/playback to accept the existing streaming descriptor.
- Run focused Gateway/media/Integrated Web tests and commit one reviewable boundary.

### Task 2 — Barge-in and response consumption fences

- Write RED tests for speech-start before-first, between frames, duplicate, missing/zero/last
  cursor, unsolicited second direct response, concurrent done/created and delegate successor.
- Retain pending speech-start until exact response fencing; implement cursor and no-cursor
  paths, source close and Engine stale-output discard.
- Enforce one direct response per turn and explicit delegate successor binding.
- Run focused Runtime/Engine/Web tests and commit.

### Task 3 — History, delegate deadline and lifecycle closure

- Write RED tests for done-first/ACK-second, ACK-first/done-second, transient writer failure,
  close during retry, delegate >5 s, timeout-after-effect, cancellation/replay, never-completing
  Provider close, repeated shutdown and bounded capacity.
- Factor one reconciliation path, add AgentServer-owned bounded retry/drain, configure 30 s
  delegate carrier deadline and retain incomplete close ownership.
- Run focused carrier/Runtime/Gateway lifecycle tests and commit.

### Task 4 — Transactional activation compensation

- Write RED tests for missing exact socket, Native observer failure, media observer failure,
  revocation races and repeated compensation, asserting zero leaked route/capability/media/
  Provider/other-activation effects.
- Add the closed `activation_aborted` disposition within existing `native.close`, then make
  activation commit-or-compensate.
- Run focused activation/product composition tests and commit.

### Task 5 — Candidate verification and cold review

- Run all affected Python tests, cumulative backend regression with coverage, all Native and
  dedicated-media frontend tests, production build, changed-file Ruff, applicable mypy,
  compileall, `git diff --check`, documentation invariants and Cascade-default regressions.
- Inspect status/diff and freeze one exact local candidate commit. Do not push.
- Perform an independent fix-only Tier-3 cold review against D-101/D-102/D-103. Any Critical
  or Important finding returns to the relevant RED task; only `C0/I0` opens the real-path Gate.

## Verification commands

Use the workspace virtual environment at
`C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe` and the repository's
existing node scripts. Exact focused nodeids and build commands are selected from the
changed test owners after each RED is written; the final evidence records every command,
exit code, count and scoped exclusion rather than relying on this plan as proof.
