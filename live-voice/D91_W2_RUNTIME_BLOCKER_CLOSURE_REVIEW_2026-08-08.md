# W2 runtime-blocker closure review

> Review date: 2026-08-08
> Reviewed implementation commit: `8649a82195d939827dd629613db3bafa13f56933` (`fix(live-voice): close W2 runtime blockers`)
> Parent/current upstream at implementation start: `5ac969af8244094973ae1b7f1ced9d761199b921`
> Mutable state: [STATUS.md](STATUS.md)

This is the frozen source/review record for the blockers discovered while rehearsing the W2 cumulative route. It does not award Replacement Ledger credit. Real OpenAI Speech, Chrome device/heard truth, real Agent/Tool/P3 execution, faults, restart, consecutive showcases and signed Gate import still must run against one clean immutable candidate.

## Closed implementation scope

- P1 TTS output: the OpenAI-compatible Adapter now validates complete mono PCM16 WAV and deterministically linearly resamples it to the browser-requested rate under the explicit `server_linear_pcm16_mono` capability. Same-rate input preserves exact bytes; malformed, non-mono/non-PCM16 and size-overflow results fail closed.
- P1 media authority: stock Web no longer depends on an absent handshake `user_id`. Authority belongs to the exact server-minted physical WebSocket `connection_id`; a browser identity claim cannot mint, transfer or reuse media/Speech authority across connections.
- P3 product mutation adoption: the frontend consumes the actual outer `mutation_processed` authority fields and inner durable formal result instead of looking for `command_id` inside the formal result. Task/attempt/state/outbox replay bindings and misplaced-authority rejection are explicit.
- P3 cancel adoption: `cancel_acknowledged` must be true and `applied` must be boolean. Missing/null outbox is canonical null; repeated cancel accepts `applied=false` only without an outbox; applied non-terminal cancel requires an outbox; applied terminal cancel forbids one. Every invalid result is rejected before replica/UI success state.

## Rehearsal findings that caused the batch

- The browser AudioContext and capture graph were 48 kHz while typical Provider WAV output was 24 kHz. The previous Adapter rejected the mismatch and had no truthful conversion capability.
- Stock Web registered its physical socket with `user_id=None`; the old media registry treated a user label as authority and rejected a legitimate activation as `MEDIA_INVALID_ACTIVATION`.
- AgentServer returned product mutation authority in the outer response and durable task facts in `formal_task_result`; the frontend read the old inner shape, so a server-accepted task appeared failed and progress activation never started.
- The disposable Windows P3 fixture hit `PROJECT_WORKTREE_BASELINE_MISMATCH` despite clean Git status because system `core.autocrlf=true` caused raw-byte disagreement in the detached execution worktree. The fixture now uses repository-local `core.autocrlf=false`; the runbook requires explicit line-ending preflight and a Git-visible mutating task.

The earlier synthetic Speech stub and the failed read-only/mismatched fixture runs receive no runtime or acceptance credit. They were diagnosis-only rehearsals.

## D-053 review closure

### Implementation self-review

The implementing workers and Main checked the positive route, flag-off behavior, wrong connection/identity, malformed WAV, output limits, outer/inner authority mismatch, replay conflict and zero-forbidden-effect cases. Main re-read the server durable store contract to distinguish three cancel results:

1. repeated cancel: non-terminal, acknowledged, `applied=false`, no outbox;
2. dispatched attempt cancel: non-terminal, acknowledged, `applied=true`, durable cancel outbox;
3. cancellation before dispatch: terminal, acknowledged, `applied=true`, no outbox.

### Cold complete-diff review

Main reviewed the complete nine-file source/test diff against the W2 request, repository rules, D-046/D-053, the actual Gateway/AgentServer response shapes and executed tests. No unresolved P0-P2 finding remained. Linear resampling is a bounded W2 conversion, not a production-quality anti-aliasing claim; the current target route is the observed 24 kHz to 48 kHz upsample. Broader codec/rate/quality work remains outside this closure.

### Independent review

Literal `/review` was unavailable. A separate read-only subagent reviewed the complete diff as the recorded equivalent and did not edit, stage or commit.

The first independent pass returned one P1: cancel adoption accepted `cancel_acknowledged=false` as UI success and rejected the legitimate repeated-cancel result whose outbox was omitted. The implementation then added the closed ack/applied/state/outbox contract and zero-state-effect tests. The independent follow-up returned **PASS with no P0-P2 findings**, confirming outer/inner bindings, stable replay, cancel variants, resampling limits and exact physical-connection media authority.

## Verification

All source checks below ran from the implementation worktree that became `8649a8219`.

| Check | Result |
|---|---|
| P1/Gateway affected backend matrix | `144 passed` |
| P3 backend affected matrix | `277 passed` |
| Final Integrated Web suite after restoring the declared local renderer dependency | `139/139 passed` |
| Final focused frontend P3/P1/product matrix | `85/85 passed` |
| Gateway Batch Speech frontend suite | `24/24 passed` |
| Production frontend build | PASS, 4512 modules; only existing locale/caniuse/chunk-size warnings |
| Ruff check and format-check over four changed Python files | PASS |
| `git diff --check` | PASS; Windows line-ending notices only |

The machine's existing `node_modules` initially omitted the already-declared `react-test-renderer`, so an earlier full Integrated Web attempt ran all loadable tests but could not load the mounted-panel test. Restoring `react-test-renderer@18.2.0` locally without changing package metadata closed that environment issue and produced the final `139/139` result. `npm` reported existing dependency-audit debt (`2 moderate`, `7 high`); no automatic audit fix or dependency upgrade was applied because it is outside this blocker batch and may be breaking.

Whole-file Prettier still reports legacy formatting mismatch in the touched frontend files, including their pre-existing HEAD content. This batch did not reformat entire legacy files merely to hide unrelated churn; TypeScript compile, targeted tests, production build and diff whitespace checks passed.

## Selected real Provider and remaining Gate boundary

D-064 freezes the current W2 rehearsal choice as Gateway-owned OpenAI-compatible Speech with `gpt-4o-mini-transcribe`, `gpt-4o-mini-tts` and initial voice `marin`. The API key remains machine-private and is injected only into the Gateway process through hidden local input.

The source is ready for a new clean candidate rehearsal. Acceptance remains open until the same immutable candidate completes:

1. a shortest real STT/TTS probe that proves authentication, model/voice availability and actual mono PCM16 WAV/rate;
2. Chrome microphone → committed transcript → real DeepSeek Agent/Tool → authoritative final → OpenAI TTS → physical playout with human heard confirmation;
3. a Git-visible disposable P3 task plus progress/cancel/terminal and restart reconciliation;
4. required retriable/non-retriable zero-effect faults and three consecutive showcases;
5. externally rooted artifact predeclaration, closure/signing and strict `w2_gate_cli evaluate` PASS.

This review itself awards no Replacement Ledger credit. Read the mutable package state and current score only from [STATUS.md](STATUS.md).
