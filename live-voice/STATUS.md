# Live Voice current status

> Updated: 2026-08-17. This is the only mutable source for current branch, stage,
> candidate, blockers and next actions; Git overrides frozen candidate history.

## Current source, milestone and Demo work

- **Product baseline:** `95b26308717b896d820f011defa691243cad58f8` on
  `hx/0812_live_voice_w3`; local/upstream matched at resume. The combined
  Post-Alpha repair and Demo-record candidate is the single local commit
  immediately above that baseline. It has automated verification but has not
  been pushed or physically rerun as a clean immutable Demo candidate.
- **Accepted milestone:** `PASS — INTEGRATED WEB ALPHA`; S8/A3 remains closed
  for exact accepted source `d33b520e0d21ae0829d30814d77a01cc18256f09`.
  Post-Alpha changes do not roll back that result or reopen S7/S8.
- **Current work:** `POST-ALPHA DEMO EXECUTION COMPLETE / FOLLOW-UP BUG
  REPAIR`, Tier 3, covering unified submit, semantic routing, running
  adjustment, Executor terminalization, result truth, terminal
  presentation/ACK and the hands-free Web lifecycle. The user confirmed that
  the real microphone/TTS Demo execution is complete. Its result is
  `COMPLETED — DEFECTS RECORDED`, not an immutable-source PASS; see the
  sanitized [2026-08-17 Post-Alpha Demo record](evidence/POST_ALPHA_DEMO_20260817_95b26308_WORKTREE.md).
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
- **Current working-tree repair:** an accepted foreground `dialogue` retains
  polling ownership across an intervening Task keepalive, answers and ACKs
  before capture resumes, then leaves queued terminal presentation to the
  existing P2/TTS/ACK lifecycle. At the user's direction, `dialogue` now runs
  with `allow_tools=True`; ordinary foreground questions may use Agent tools,
  while create/update/query/status/cancel remain the only explicit background
  Task routes and tool permission alone does not authorize Task mutation.

## Recorded product defects

1. **Executor completion does not reach a terminal Task:** Direct Executor
   attempt `attempt-26f170d35739445a9a4e3699de50c26f` invoked the real Agent,
   which wrote the bounded `itinerary.md` in its isolated checkout and reported
   internal completion. Executor orchestration never persisted
   `expected_tree`, result/artifact facts or a terminal event; the attempt
   remains `running` and renews the project lease. Repair the Agent-return →
   validation → application → immutable result → terminal-event boundary and
   add bounded timeout/orphan recovery coverage.
2. **Task admission is presented as execution:** a successor task can remain
   only `accepted` with `ATTEMPT_NOT_YET_BOUND` while dispatch repeatedly fails
   with `EXECUTOR_PROJECT_BUSY`, yet unified create says “已开始处理”. Present
   queued/admitted separately from authoritative `attempt.running`; do not
   claim execution before the Attempt is bound.
3. **Chinese semantic routing is too exact:** the natural update without
   “把/将” resolves to `background.query`, while “可以了,刚才的修改加进去了吗?”
   fails the adjustment-status full match and falls through to `dialogue`.
   Broaden only bounded high-confidence update/status forms and add exact
   positive, ordinary-question, negation, precedence and zero-mutation cases.
4. **Foreground dialogue can make false Task-state claims:** after the status
   misroute, the Agent reread seven order files and answered that the change was
   applied and a final itinerary existed even though the authoritative Task had
   no bound Executor result. Task status/completion/application claims must be
   owned by Task Core facts or fail closed; `dialogue` may not infer them from
   conversation or project files.
5. **Available result is rejected when dialogue context is full:**
   `background.query` returns “当前任务结果不可用” whenever the selected context
   already contains eight entries, even if Task Core returned a legal
   `task_result`. Reserve a result-context slot or evict the oldest dialogue
   pair; context capacity must not be reported as result unavailability.
6. **Recovery state remains insufficiently diagnosable:** repeated visible
   “正在恢复” coincided with P2/barge and Speech transport cleanup failures, but
   the UI does not expose enough stable correlation to separate activation,
   presentation ACK, TTS cleanup and successor-generation recovery. Preserve
   stable reason/generation diagnostics and add the exact repeated-recovery
   regression before claiming this closed.

The missed completion notification and missing authoritative final result in
the last Journey are consequences of items 1–2, not proof that an existing
terminal notification was lost. P2 `notification_sequence` also includes
foreground stream events and keepalives; a high sequence is not itself a
duplicate-notification defect. These Post-Alpha defects do not revoke the
accepted Alpha result or require another S7/S8 cycle.

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
- Current combined candidate automated credit: Integrated Web `386 / 386`,
  including silent idle-capture rotation, terminal capture suspension,
  retry/physical playout/one ACK/resumed listening and the intervening-dialogue
  keepalive regression. Affected backend Bridge, Demo Executor and DIALOGUE
  policy checks passed `60 / 60`; the DIALOGUE assertion now matches
  `allow_tools=True`. The `4,642`-module production build also passed. The
  duplicate English/Chinese i18n `empty` key remains a build warning, not a
  failure or a Task/result root cause.
- The 2026-08-17 real microphone/TTS Post-Alpha Demo execution is complete by
  user confirmation. It exercised ordinary dialogue, background create,
  running adjustment, adjustment-status/result questions and foreground
  playout/interruption behavior across real Sessions. The run exposed the
  recorded defects above, retained no immutable exact candidate because the
  deployed source was the dirty working tree, and therefore receives
  `COMPLETED — DEFECTS RECORDED`, not PASS or release credit. The sanitized
  result is frozen in the linked Post-Alpha Demo record.
- Earlier real STT/TTS, multi-turn dialogue, background create/adjust/result
  and artifact inspection proved the physical paths can run, while exposing
  the recorded Task, routing and recovery defects above. Those observations
  are Demo discovery evidence.
- Remaining Demo limitations stay explicit: automated browser-origin storage
  inspection was unavailable, and transport duplicate-ID wording is bounded
  but less specific than product-layer conflict results. Human acceptance must
  inspect visible storage/lifecycle behavior.

## Environment state and next actions

- The 2026-08-17 18:02 one-click local deployment from the current working tree
  remains the tested runtime on `6173`, `18092`, `19000` and `19001`;
  production bundle `index-Ci1LeMJT.js`, P3 authenticated route and P2/P3
  composition probes passed with DIALOGUE `allow_tools=True`. The earlier
  cancellation did clear its exact two attempts, but later Demo Sessions
  created new non-terminal records. At the 18:48 forensic snapshot,
  `task-7e8b7b3ef9d44cb69546d96a7ceb4b7a` remained `running` with a renewed
  Direct Executor owner/lease, while
  `task-4cf2948ba1834472b304551f5481a5a9` remained `accepted` and its dispatch
  was still retrying `EXECUTOR_PROJECT_BUSY`; its adjustment outbox had not
  been delivered. The target `order-test` Git worktree itself remained clean
  on `6fcfa18e91cbab817e1865283e4a7d25da3e34fe` with no remote. Runtime log:
  `logs/swarm-20260817-180239.log`.
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

1. Safely settle or cancel the two current non-terminal Demo tasks through
   Task Core before another mutation run; do not delete runtime rows or the
   target worktree manually.
2. Repair Executor terminalization and project-lease orphan recovery first;
   assert one legal TaskResult/terminal event on success and bounded failure on
   Agent-return or validation failure.
3. Separate accepted/queued/running presentation truth, then repair the bounded
   Chinese update and prefixed adjustment-status grammars with positive,
   negative, precedence and zero-mutation regressions.
4. Prevent DIALOGUE from claiming Task application/completion/result truth and
   repair the eight-entry result-context boundary.
5. Synchronize DIALOGUE `allow_tools=True` expectations and add bounded
   tool/reasoning behavior so ordinary answers may use tools without turning a
   status-like sentence into an unconstrained project reread.
6. Preserve stable P2/barge/TTS/ACK recovery diagnostics and regress repeated
   “正在恢复”, completion-adjacent interruption and queued terminal delivery.
7. Run affected backend/Integrated Web checks, cumulative Tier-3 review and the
   focused real microphone/TTS paths changed by the repairs. A future PASS
   claim requires a clean immutable candidate and a new complete successful
   Journey; this completed defect-discovery run must not be relabeled.
8. Track the duplicate empty-key i18n warning as low-priority engineering
   hygiene unless it is shown to drop or overwrite a visible translation; it
   is not a root cause of Task, result or notification failures.

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
