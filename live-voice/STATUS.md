# Live Voice current status

> Updated: 2026-08-17. This is the only mutable source for current branch, stage,
> candidate, blockers and next actions; Git overrides frozen candidate history.

## Current source, milestone and Demo work

- **Product source:** `f118f51bae9b085fff48ee1ee33df57fda7fc6d2` on
  `hx/0812_live_voice_w3`; local/upstream matched before these documentation changes.
- **Accepted milestone:** `PASS — INTEGRATED WEB ALPHA`; S8/A3 remains closed
  for exact accepted source `d33b520e0d21ae0829d30814d77a01cc18256f09`.
  Post-Alpha changes do not roll back that result or reopen S7/S8.
- **Current work:** `POST-ALPHA DEMO PREPARATION / BUG REPAIR`, Tier 3,
  covering unified submit, running adjustment, terminal presentation/ACK and
  hands-free Web lifecycle. The two bugs below block the new Demo, not Alpha.
- **Stage relation:** this bounded Demo stabilization is not S9; S9 has not
  started and remains Later/Beta/Production under [D-081](decisions/DECISIONS.md).
- **Engineering verification reference:** exact source
  `3bc7f9345f5b3832367e0a34b0dee8853d3d2c02` has the complete batch review in
  [D119](D119_RUNNING_TASK_ADJUSTMENT_AND_TERMINAL_NOTIFICATION_REVIEW_2026-08-16.md),
  but its historical S7/A2 wording does not define the current workflow.
- Earlier hands-free history is the [pre-D119 D118 snapshot](D118_UNIFIED_HANDS_FREE_LIVE_VOICE_REVIEW_2026-08-16.md).

## Implemented boundary

- **Hands-free entry:** one click starts a generation-fenced loop. Only an
  authoritative ASR final enters `live_voice.composition.unified.submit`;
  partial/interim speech has zero Agent, Tool, Task, file or presentation effect.
- **Closed semantic routes:** `dialogue`, `background.create`,
  `background.update`, `background.query`, `background.status` and
  `background.cancel`. Create/update use distinct high-confidence grammars;
  ambiguity, negation, ordinary questions and low confidence do not mutate Task.
- **One current background Task:** Store schema v3 owns the authenticated
  subject/project/Session pointer and restores it after activation rollover or
  refresh. Current check, Task/attempt/outbox creation and pointer update are
  atomic; a non-terminal current Task blocks a second create.
- **Running adjustment:** `task.adjust` writes the command,
  `task.adjust_requested` and ordered outbox atomically. The real Executor
  consumes it at a pre-terminal checkpoint; only persisted
  `task.adjust_applied` supports an applied claim. Terminal Tasks reject it.
- **Result truth:** immutable `task_results` bind task/attempt/source-event
  identity plus bounded artifact path/SHA. Only a completed Task with a legal
  result is `available`; running is `not_ready`, and failed/cancelled/
  interrupted or invalid is `unavailable`. Only `available` enters P2 Agent
  as untrusted reference context.
- **Authority and durability:** unified submit validates current P2 activation,
  Session and Gateway voice claim before parsing. Its journal provides replay,
  conflict, lease and crash recovery; unavailable authority fails closed.
- **Presentation lifecycle:** one coordinator owns capture start/stop; Exit
  advances the loop-generation fence. Playout barge-in stops only the current
  response/TTS with zero Task mutation. Committed-user and acknowledged
  assistant TEXT facts enter normal Session history; context selects at most
  four acknowledged dialogue pairs.
- **Focused session repairs in `f118f51b`:** overlap capture publishes its
  exact P2 binding before final playout/EOT; failed presentation keeps answer
  text and stable codes; stale/absent predecessor ACK can settle for one successor.

## Current blockers

1. **Unified-create completion announcement:** a real voice-created background
   Task accepted its adjustment and completed with a legal result/artifact, but
   unified create did not retain and activate the exact Task progress binding.
   No proactive terminal presentation was constructed. The repair must bind
   the returned Task, reuse the existing TaskEvent → P2 presentation/TTS/ACK
   path, announce exactly once after ACK, preserve crash-before-ACK replay,
   pause only active capture while speaking and resume exactly one capture.
2. **Completion-adjacent barge/P2 recovery race:** when Task completion,
   intentional playout interruption and the next utterance occur together, an
   old ACK can race route recovery and the successor Agent round. One owner
   must settle normal/recovery ACKs, serialize recovery with next submit, show
   truthful recovering state, preserve the stable failure reason and keep Task
   cancel/mutation at zero.

These are product-source gaps, not documentation-only or private-environment
blocks. They must close before the new Demo, but they do not revoke the accepted
Alpha result or require another S7/S8 cycle.

## Verification credit

- The Integrated Web Alpha acceptance remains closed on exact `d33b520e`; the
  current Post-Alpha Demo work does not relabel or replace that accepted source.
- Exact `3bc7f934` batch verification: serial backend
  `1,776 passed / 2 expected Windows skips / 1 existing warning`; Integrated
  Web `374 / 374`; post-format affected backend
  `324 passed / 2 skips`; mounted stale-TTS Session-switch regression,
  Ruff, Ruff format, Python compilation, `git diff --check` and the
  `4,642`-module production build passed.
- The D119 self/cold review and independent Tier-3 read-only review found no
  remaining P0-P3 issue on `3bc7f934`; this is engineering credit, not a new
  Alpha stage gate.
- Focused delta now contained in `f118f51b`: Integrated Web
  `376 / 376`, chat-store projection `4 / 4`, focused backend dialogue
  context, product journal/Web owner `85 / 85`, semantic Bridge `52 / 52`,
  `git diff --check` and the `4,642`-module production build passed.
  This is affected-scope credit for the Post-Alpha Demo source.
- Earlier real STT/TTS, multi-turn dialogue, background create/adjust/result
  and artifact inspection proved the physical paths can run, while exposing
  the two blockers above. Those observations are Demo discovery evidence.
- Remaining Demo limitations stay explicit: automated browser-origin storage
  inspection was unavailable, and transport duplicate-ID wording is bounded
  but less specific than product-layer conflict results. Human acceptance must
  inspect visible storage/lifecycle behavior.

## Environment state and next actions

- The 2026-08-17 one-click local deployment is live on `6173`, `18092`,
  `19000` and `19001`; production bundle and P2/P3 readiness probes passed.
- Provider/model settings, Speech credentials, project registration, browser
  permission/devices and isolated runtime data remain machine-private and are
  not restored by Git. Credentials must not enter chat, logs or the repository.
- Frozen Speech target: Gateway-owned official OpenAI origin,
  `gpt-4o-mini-transcribe-2025-12-15`,
  `gpt-4o-mini-tts-2025-12-15`, voice `marin`; explicit degradation is
  Streaming → W2 Batch → Browser/text.
- Use only a registered disposable no-remote Git project, isolated
  `JIUWENSWARM_DATA_DIR` and the reviewed Demo flags. Never use this source
  worktree or a user project as the Executor target.

Next actions:

1. Repair the unified-create completion-announcement seam and run positive,
   ACK/replay, flag-off, wrong-scope and zero-mutation focused regressions.
2. Repair the completion-adjacent barge/P2 recovery race and run the exact
   interruption-immediate-next-utterance regression.
3. Physically regress two consecutive Chinese turns, visible history/context,
   one playout interruption, resumed listening and unchanged background Task.
4. On the final Demo source, run affected/cumulative Demo-scope checks and the
   risk-proportional Tier-3 review; do not recreate S7/S8 gates.
5. Run the seven-step D119-derived microphone/TTS Demo Journey:
   dialogue, create, intervening dialogue, non-terminal adjustment, adjustment
   status, applied-before-terminal/current-generation announcement and
   result-backed artifact query.
6. Verify artifact content/SHA, ACK refresh suppression, crash-before-ACK
   replay, service/lease/outbox settlement and bounded fixture/data cleanup,
   then record the Post-Alpha Demo result and remaining limitations.

## Stable non-goals

- Multiple concurrent background Tasks, generic full-P3 `update`,
  `provide_input`, `pause`, `resume`, `reprioritize`, automatic
  successor revisions and running-draft presentation.
- Interruption while the foreground Agent is generating. During
  “Understanding and answering” the Demo operator must wait; supported
  barge-in begins during playout. A full voice loop for Agent `ask_user`
  questions/answers is Later.
- Speaker echo cancellation, performance optimization, D1/D2, external
  exactly-once, compensation/rollback and cross-device unread/replay.
- Production authentication/multi-tenancy, public deployment, broad browser/mobile/PWA, RC/Production, formal SLO/retention and audit certification.
- S9/Later work has not started and is not implied by the current Demo fixes.
- Credentials, billing/account administration, private runtime data and remote updates remain outside product-source acceptance.
