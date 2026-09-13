# 17:27 acceptance failures: scoped diagnosis and repairs

Source baseline: JiuwenSwarm ac5bd9bf, AgentCore 13493418 (editable 0.1.17+livevoice.1).
Evidence: swarm-20260913-172141.log, read-only formal_tasks.sqlite3 queries,
browser diagnostics 15-28-44-584Z and 15-42-52-803Z. Local time is UTC+2.

Confirmed task repair boundary (Tier 2): dedicated project execution must expose
its permitted file tools and declaration tool consistently. ProgressiveToolRail
currently hides declare_file_effect_plan/list_files and advertises removed
tool_search/tool_call. Disable that discovery rail only on dedicated project
adapters; preserve the exact file ability allow-list, write checkpoints, ordinary
Agent/Work profiles and the SDK version. Test with actual SDK rail lifecycle and
ability registry, plus existing positive/negative file-plan checks. Also close
the owned asynchronous stream before releasing checkpoint/session ownership;
the failed-stream trace shows a leaked generator and cross-context finalization.
No new Task policy, automatic retry or real project mutation is authorized here.

Observed business facts: first Shenzhen task failed after its adjustment was
applied; second Shenzhen task failed and its later adjustment was rejected with
TASK_TERMINAL_BEFORE_ADJUSTMENT. Hangzhou task cancellation was acknowledged and
settled cancelled at 17:30:34. The new-chat welcome page is an intentional draft;
the user expects voice-first creation, which is retained since c707c1e2. Actual
browser inspection confirms mouse clicks hit the absolutely positioned bee image
above the LiveVoice enable button. Keyboard Enter reaches the existing creation
path. Tier 1 layout repair: raise only the welcome voice controls above the bee;
preserve the allocation/authorization flow and verify actual pointer hit-testing.

## Confirmed speech races (Tier 2)

1. Browser stopped response generation 14 at 17:27:42.153. The Provider returned
   response_cancel_not_active at 17:27:43.355. The played-cursor cancel path did
   not establish the local fence required by its own exact-receipt race handler,
   so an ordinary cancel/completion race became NATIVE_PROVIDER_ERROR and closed
   the uplink. Establish the local fence after cursor validation, before Provider
   writes; preserve exact cancel receipt validation and response.done settlement.
2. Browser stopped generation 19 at 17:28:35.823. Host rejected concurrent audio
   as NATIVE_AUDIO_RESPONSE_STALE at 35.861, before Gateway retained the local
   stop fence (it was waiting for the Host ACK). Retain the validated local stop
   before that await. Existing stale-frame handling then discards the exact old
   response without tearing down the current media session. MEDIA_STOP_STALE and
   uplink consumer failures in this sequence are downstream consequences.

These repairs change local ordering, not Provider latency, buffer limits or
timeout policy. No unmatched Provider errors or cross-response audio are ignored.

## Observations kept open

At 17:28:44 a Task announcement obtained response generation 21. Native response
22 began at 17:28:52.874; the older announcement reached TTS at 17:29:14.700.
AudioPort correctly rejected it with RESPONSE_GENERATION_NOT_INCREASING. This is
a stale prepared announcement, not proof that Realtime was slow. Existing retry
keeps the same response identity/generation; no verified authoritative rebind
path was established in this repair. Do not increment generations in the browser
or relax the monotonic fence. A separate repair must define retained delivery,
fresh Host response allocation, one playback acknowledgement and no Agent rerun.
The diagnostic's later 'recovered' label alone does not prove resumed playback.

The Work request at 17:30:58 was admitted as work.start, started Agent execution
at 17:30:59.713 and reached agent_completed/outcome=complete at 17:31:13.501.
Thus this Work query completed. It does not establish success of the two Tasks.
The second cancel at 17:30:36 was rejected after the first cancellation settled;
it does not negate the successful cancellation.

## Verification and limits

- Task adapter/file-effect suites: 124 passed, including real SDK rail removal,
  callable declaration visibility and same-context stream close before cleanup.
- Native engine/Gateway suites: 400 passed, exit 0, with coverage disabled to
  avoid unrelated shared report-file contention.
- Welcome voice-start tests: 11 passed; TypeScript/Vite build passed.
- Browser: before repair, pointer hit-test found the bee above the button and
  keyboard Enter alone reached allocation. After repair, hit-test resolves to
  the button and an actual mouse click created web_1a09b9a2fb6_a767f52bf381 from
  the registered demo project without a text message. Voice was exited after
  this entry test; this is not microphone/conversation quality acceptance.
- Independent scoped review: no actionable findings. Production Python Ruff
  check and scoped diff whitespace check passed.
- AgentCore remains clean at 13493418, version 0.1.17+livevoice.1. No SDK/Work
  implementation, model configuration, protected data or failed-task state edits.
- Temporary built-bundle diagnostics were restored before the final source build.
  No real background Task was rerun; the user can recheck after redeployment.
