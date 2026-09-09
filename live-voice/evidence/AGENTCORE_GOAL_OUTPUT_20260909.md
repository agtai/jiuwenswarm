# Shared Goal execution admission and Web controls

This is a prerequisite boundary within the active [unified execution Goal](../reviews/AGENTCORE_UNIFIED_EXECUTION_20260909.md).
It does not complete Task 2/3, Native invocation or product acceptance.

## Source and implementation

- Main baseline remains `66833d5ced9203ce54ffa2fcf009d4de380f62a7` on
  `hx/0812_live_voice_w3`; the adapter/Web changes belong to the uncommitted
  Task 2 batch. No remote ref was updated and no changed service was restarted.
- SDK commit `fc12e445348bfdb60f4a2e2e0208a97674b28111`:
  `fix(goal): admit output ownership atomically with exact controls`.
  Parent is `a43444ff5326a0c1a72954126eea4f91e071d916`; reviewed content tree is
  `b33ed6baaa912e3cc279011dbd72b3a16eaf4efe`.
- `agentcore-goal-output.patch` is the ordered source delta after the existing
  Responses, Goal-control and task-settlement patches. Actual reconstruction
  from upstream base `94e10cb6102c36fe78a64547957c0def97299273` and all four patches
  matched the manifest tree in `.codex_tmp/agentcore-source-replay-goal-output-20260909`.
  The installed-source check passed with actual editable origin `.deps/agent-core`.
  This preserves the original explicit uninstall/source installation; no wheel
  replacement or repeated environment reinstall was necessary.

`DeepAgent.set_goal` and `resume_goal` use the existing GoalManager control lock,
SessionGoalStore, EventManager and output lease. They validate identity, control
revision, fresh admission and state before attaching output. New execution
entries never repair corrupt Goal state. Existing readers retain ownership;
finishing readers drain their last chunks before a new lease is acquired, with
admission rechecked after waiting. Repeated cancellation cannot abandon cleanup
of a newly acquired lease or discard unrelated queued user work.

Text streaming calls the SDK entry directly. Legacy text pause/resume/clear
capture the observed target and use CAS; a clear that observes no Goal returns
immediately. Stale errors carry current state when readable, while unavailable
state omits a Goal snapshot rather than claiming absence.

Web editing captures session/Goal/control revision when the dialog opens.
Changed target/version/session invalidates that edit. New requests do not
overwrite unfinished Goals implicitly. Starting the next Goal after completion
uses the exact observed completed predecessor. Clear sends only the SDK Goal
command; App no longer also cancels/pauses the whole session. The actual Gateway
preserves `goal.confirm_required`, including the existing Goal's control target.
InputArea and new-session App creation no longer pre-credit a successful Goal:
the accepted set snapshot creates the objective bubble using the existing busy
turn deferral. Unscoped or mismatched-session Goal events cannot change another
session's Goal or accepted-objective history.

## Focused checks and review

Python checks used the source-installed `.venv`, `--no-cov -o log_cli=false -q`,
separately in each repository. These are boundary results, not a full-suite sum.

- SDK initial output-admission/GoalManager/interaction run: 53 passed. Two
  initial failures first proved missing lifecycle recheck and corrupt-state
  rejection, then passed after repair. Final new output-admission file:
  22 passed. Existing interaction regression after cleanup changes: 7 passed.
  The combined boundary has 56 distinct tests, with only affected reruns.
- Main shared-session/Goal adapter run: 65 passed. Added legacy empty-clear
  concurrency case passed; added completed-predecessor scenario and its active
  regression both passed. The two files cover 67 distinct passing scenarios.
- Actual Gateway Goal payload regressions: 2 passed, including the real
  MessageHandler chunk conversion and WebChannel payload serializer.
- Frontend original mounted GoalBar/hook/client cases: 7 passed. Expanded run:
  9 passed plus one composer setup failure; writing through the actual mounted
  contenteditable fixed the setup and that affected case passed. All 10 final
  scenarios have passing evidence. Independent recheck also passed the three
  affected frontend scenarios and actual Gateway serialization case.
- Frontend `tsc --noEmit --pretty false` passed after final behavioral changes.
  The Node fixture replaces transport and Vite provider-icon discovery, not Goal
  stores, command adapters, InputArea or GoalBar. It proves no Provider, physical
  audio or visual asset acceptance. Its initial Vite `import.meta.glob` setup
  error was fixed in the test bundle only. Existing duplicate `empty` locale keys
  outside the changed Goal strings remain an explicit build warning.
- Scoped SDK/Main new-test Ruff and whitespace checks passed. Whole-file SDK
  Ruff reports inherited unused `prompt` at DeepAgent line 528, reproduced from
  parent HEAD before this commit; no unrelated prompt-building repair is claimed.

Independent SDK review found and closed two P2s: treating a finishing reader as
usable, and losing lease cleanup under repeated cancellation. Main/Web review
found and closed four P2s: legacy empty-clear racing creation, Gateway dropping
confirmation fields, completed-then-new-Goal regression, and prematurely accepted
objective bubbles. Repairs were rechecked at the affected seams rather than
through repeated full suites.

## Remaining execution boundary

Native still needs actual shared Agent/Goal set/resume, Team/HITL and Core
Workflow invocation, plus model/permission/history authority carried through the
shared producer. The SDK API and cross-entry observations alone do not satisfy
that requirement. Work/formal Task cutover, duplicate runtime retirement,
Task 2/3 main commits, final broad checks/review and real browser/Provider/Agent/
tool acceptance remain pending. The Goal stays active.

## Tested runtime identities

- `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py`: `0b59cab4448929e8f154a43b60b0b08ca772585b80182b077c14aae1c9cc5d9d`
- `jiuwenswarm/common/schema/message.py`: `51af3ab118461affbab862c72ea951d46011d61409761618d1a1a46e6aff77c5`
- `jiuwenswarm/gateway/channel_manager/web/web_connect.py`: `2cb848f7234bbc3b1e5c218fc2247fa468f4f50650546245881c196909b4974b`
- `jiuwenswarm/channels/web/frontend/src/services/goalCommands.ts`: `79ff74f3b0ab6a20ee91d911efb26e4f1775adf76ada07669a52a8cfdd186db0`
- `jiuwenswarm/channels/web/frontend/src/services/webClient.ts`: `12a5b8a04e27c276b49d3cee680d00c190279bc15b6131c5bae00fcdb177ccc9`
- `jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts`: `e636a9ffbd5ed2d5b412563858b2bae43c4b03df100bb11fef1c3b85303a477a`
- `jiuwenswarm/channels/web/frontend/src/components/GoalBar/index.tsx`: `82c1477baea09249c8f593e484f3203fb67bf5b31528c58dfdf7851a26bbe3f1`
- `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx`: `a44ce46c16f63916fda557f7ebc656eb27a94ab71c9466ea07330c9ef62d877a`
- `jiuwenswarm/channels/web/frontend/src/App.tsx`: `0f88c2c9a66a4f40698ce5cdd8062bce0a0f3c552165ea93834a8581c2b7835c`
