# Native conversational execution

User-authorized implementation packet, 2026-09-06. The user accepted execution
after the scoped Native architecture audit and the latency/experience discussion.
This packet replaces the previous repair-only active scope; prior fixes remain
regression obligations. Root TESTING.md owns verification and review cadence.

## Intended behavior and scope

Native Realtime owns foreground conversation and typed business proposals.
Authenticated server code validates and dispatches Task operations without a
second semantic model or Agent receipt paraphrase. Real Jiuwen Agent/tools own
analysis; Task Core/Executor keep all canonical business authority. Cascade keeps
its current route and semantics; no silent cross-mode fallback.

Foreground Agent work has identity and lifecycle separate from spoken responses.
Acceptance and queried progress are truthful; speech interruption does not cancel
accepted work. Explicit work/Task cancellation, updates and supersession have
exact identities. Results can be queried and scheduled without reviving retired
audio. Restore authorized context/work facts on Native replacement sessions;
never replay mutations or label generated/unheard text as heard.

Owned defects: incomplete semantic/Agent/reconnect context; read-only question
misrouted to task.adjust; pending-response and cursorless interruption gaps;
Native truncated Task results; existing-session model-selection propagation;
Task projection refresh/retry; retention of critical diagnostic milestones.

## Modules, risk and interfaces

- **Main (Tier 3):** Native business proposal/carrier, Registry dispatch and exact
  authority, context/work orchestration, Runtime/client/server integration,
  accepted decision and deployment. New typed business proposals require an
  explicit version/capability; old strict payloads must not silently change.
- **Media (Tier 2/3):** Engine/Gateway response interruption and sequencing,
  Provider context/result integration once Main's interface is fixed; Native
  audio fixtures and actual serialized client regressions. Preserve ACK truth.
- **Execution (Tier 3):** scoped conversation/context and work ownership module,
  Agent runtime/harness integration, bounds/cancel/recovery tests. Interface
  changes are coordinated with Main before editing shared owners.
- **UI (Tier 2/3):** Task projection, critical diagnostics, actual model selection,
  work/conversation display as protocol becomes available, mounted regressions.

Main owns shared semantics. Workers operate in separate task worktrees and may
edit/test/commit only assigned files to their task branch. Main alone integrates;
workers must not merge, change the integration branch or update remote refs.
Main continues on the clean task branch; the running Demo stays on its current
process until the candidate is verified. No unrelated worktree is touched.

Dependencies are explicit: proposal and work contracts precede their media/UI
integration. Existing Task authority and authenticated context selection precede
Provider disclosure. Stop generation and played-cursor truncation are separate;
an already admitted work item is not cancelled by retiring its speech response.

## Work sequence

1. Record D-119's accepted Native contract expansion and scoped tests; baseline
   current connected seams. Use isolated test data/logs, not the running Demo.
2. Implement typed Task/read/Agent-work proposals and exact authorized dispatch;
   complete context/result transfer and model binding. No new keyword classifier.
3. Implement independent work/result lifecycle and Native response arbitration;
   integrate interruption fixes, recovery, late results and bounded capacity.
4. Integrate Task projection, model confirmation, work state, text/notification
   ownership and milestone diagnostics with actual strict serialization.
5. Review coherent diffs independently, fix findings, run affected Python/Node
   and mounted integration checks and production build. Test Native and Cascade.
6. Commit verified coherent modules, deploy through existing controlled launcher
   if needed, preserving credentials/project/data/Task state. Bind source/assets
   and real Provider/Agent evidence; report physical-user acceptance separately.

## Acceptance and exclusions

Use all applicable P/N/B/S/T/C/R/I/F/K/X dimensions in root TESTING.md, particularly:
real positive Task A/B create/read/adjust/cancel; independent refund question has
zero Task mutation; long analysis plus interjected question/update/cancel; exact
context after prior Native speech and reconnection; complete long result tail;
pending-created and cursorless interruption; delayed/duplicate/multiple function
results; unknown outcomes and retry without replay; stale/foreign scope rejection
with zero forbidden Agent/Tool/Task/audio/history effects; Task refresh failure
without re-execution; existing-session model switch; one Task-event notification;
critical timeline retention under high-frequency audio; Cascade regressions.

Required seams include Registry -> actual Agent WebSocket serialization -> strict
Gateway client -> media owner -> mounted UI, not just independent helper mocks.
Reuse the existing audit's two failing current-behavior probes and prior scoped
tests. Reclassify old exclusions when their boundary is now owned. Measure useful
receipt/first verified conclusion/final result/first audible and interruption
separately; filler does not establish a latency improvement.

No broad performance tuning, new provider/model settings, production/public
deployment, remote update, fixture answers, forged ACK, source-text keyword
policy, or wholesale Cascade rewrite. A new work store must make its restart
semantics explicit; accepted/pending/unknown cannot be called completed.

## Verification record

The implementation separates Native business dispatch from the Cascade semantic
entry. `NativeBusinessRouter` validates observed context/targets and dispatches
through existing production Task authority. `NativeWorkRuntime` and its journal
own read-only Agent execution, exact revision updates/cancellation, reconnect and
restart-unknown state. Runtime/Engine arbitrate one successor for a function-call
group and new work-result speech; actual playback ACK alone records delivery.
Gateway and mounted Web UI carry selected model, work state, Task refresh and
critical diagnostics. No user-project keyword or canned answer determines routing.

Independent module reviews used the authorized media, execution and UI workers
as the available equivalent of a separate review tool. Main reviewed complete
returned diffs and integration seams. Findings repaired before closure include
post-await project-authority checks, same-response sibling arbitration, oversized
history selection, real service observation capacity, Task-origin persistence
after late settlement, strict serialized client compatibility, and recoverable
Provider argument rejection. Real calls also exposed missing operation-to-field
instructions: tool descriptions now explain required/null fields from the same
operation sets as validation, without changing the contract or execution policy.
Workers did not integrate or update remote refs.

### Automated and integration evidence

Private raw output is under `logs/native-conversation-execution/`; source identity
is the clean commit containing this packet and its integrated module commits.
Tests use an isolated `JIUWENSWARM_DATA_DIR`, `PYTHONUTF8=1`, and unique pytest
`--basetemp` paths; the running Demo data is not the test fixture.

| Dimensions | Evidence and remaining limit |
|---|---|
| P/X | Typed Task A/B create/read/adjust/cancel with exact A isolation, full work result, real SQLite Store and actual AgentServer serializer/strict Gateway client. Real configured Agent/file execution is a separate probe below. |
| N/I | Read-only refund analysis has zero Task mutations; wrong project/scope/capability, stale target/revision and post-await rebind fail without prohibited Agent/Tool/Task disclosure or execution. |
| B/K | Closed capability negotiation, legacy payload rejection, server-bound Task observation limit, complete 128 KiB work result with optional context omitted, bounded history and frontend model compatibility. |
| S/T/C | Independent work survives speech stop/reconnect; update/cancel fences older revisions; delayed and sibling function outputs have one successor; STOP before response-created and cursorless generation cancellation; results wait for actual playback settlement. |
| R/F | Exact mutation replay, persisted work restart-unknown state, missing Task-origin association recovered only from a completed receipt, no effect replay, invalid Provider arguments return a bounded exact-call error. Feature-off retains Cascade routing. |

The cumulative Python command is `python -m pytest` with the following modules,
`-q -o addopts=''` and isolated `--basetemp`; `cumulative-1.txt` records **632 passed**:

```text
tests/unit_tests/live_voice/test_native_business_contract.py
tests/unit_tests/live_voice/test_native_business_context.py
tests/unit_tests/live_voice/test_native_business_registry.py
tests/unit_tests/live_voice/test_native_business_runtime.py
tests/unit_tests/live_voice/test_native_business_authority.py
tests/unit_tests/live_voice/test_native_task_authority_capacity.py
tests/unit_tests/live_voice/test_native_work_runtime.py
tests/unit_tests/live_voice/test_native_work_journal.py
tests/unit_tests/live_voice/test_native_interaction_runtime.py
tests/unit_tests/live_voice/test_openai_realtime_native_engine.py
tests/unit_tests/gateway/test_native_interaction_runtime_client.py
tests/unit_tests/gateway/test_dedicated_media_registration.py
tests/unit_tests/live_voice/test_native_agent_model.py
tests/unit_tests/live_voice/test_agent_conversation_runtime.py
tests/unit_tests/agentserver/test_formal_live_voice_adapter.py
tests/unit_tests/agentserver/test_live_voice_p3_agent_profile.py
tests/unit_tests/agentserver/test_native_work_formal_policy.py
```

`test_audio_diagnostics.py` (Gateway) and `test_demo_profiling.py` (Live Voice)
add **34 passing** diagnostic checks (`diagnostics.txt`). Scoped `ruff --select
F,E9` and `git diff --check` pass.
After the tool-description correction, the business contract and Native Engine
modules pass **152/152** again (`tool-description.txt`).
The final connected probe exposed an additional work-delivery deadlock after
Provider `failed`/`incomplete` audio: Engine scheduling and Runtime admission
waited for an unavailable successful presentation ACK. Both now permit a fresh
work response after that unsuccessful terminal state, preserving shared Task
playback exclusion and leaving the old audio/history unacknowledged. Two Runtime
cases fail at `NATIVE_RESPONSE_PRESENTATION_BUSY` before the fix and pass after
it; Runtime/business regression is **37/37**. Engine adds four corresponding
failed/incomplete and Task-busy cases. This changes no token limit or timeout.
After integration, the business Runtime/Registry/authority, Native Runtime/Engine,
Gateway client and dedicated-media modules pass **377/377**
(`terminal-integration.txt`), with independent cross-owner review of both fixes.

From the Web frontend directory, `node node_modules/typescript/bin/tsc --noEmit`
and the actual Panel esbuild bundle pass. Mounted tests selected by
`formal activity|mounted Native request lifecycle|Native work bar|production
ChatPanel|command bar` pass **23/23**. Native interaction/model activation owners
pass **99/99**; commands and worker output are in
`native-work-ui-evidence/README.txt`. Root `npm run build:live-voice -- --outDir
logs/native-conversation-execution/candidate-dist` passes; existing locale-key
and chunk-size warnings remain. The controlled launcher builds the served `dist`.

### Broader regression exclusions

No full-suite or full Cascade acceptance is claimed. The selected existing
Registry regression command, `-k '(native or p2 or task_notification) and not
native_available_result_uses_toolless_agent_delegate and not
native_background_delegate_clarifies_or_rejects_without_task_effect'`, has
63 passes and 17 failures on both the candidate and the baseline Registry,
Runtime and test source from `800ce21c`. All failure IDs match; 16 assertion/reason
blocks match exactly after normalizing object addresses. The remaining
`after_owner_close_capacity_progress_close_retry` variant fails earlier on the
baseline and at missing successor assistant history on the candidate. Static
review finds no newly reachable Native path for that Cascade fixture, but the
different failure stage is not explained conclusively. It remains an explicit
regression gap (`baseline-registry-comparison.json`,
`baseline-registry-static-review.txt`), not a claimed pass.

The wider frontend regression retains 24 matching baseline failures (candidate
636 passes; baseline 619 passes; one skip each). The final Panel-only command has
69 passes and the same baseline `/onTaskRefresh=/` source assertion failure.
Adjacent P3 checks likewise retain previously demonstrated baseline exclusions;
they are not hidden by the passing changed-owner commands.

### Real execution, deployment and acceptance boundary

The isolated configured GPT Agent probe used actual formal read-only execution,
the Registry/server codec/strict client return path and project-file audit:
receipt at 1.375 s, stream execution 13.047 s, completed work at 13.156 s. The
expected source file was actually read, the answer contained its facts, and Task
count stayed zero. Project/config fingerprints were unchanged. Raw evidence is
in the media worktree's `logs/native-real-business-20260906/run-221702/`.
These inputs differ from the user's recording; these figures do not prove a
before/after speedup or browser first-audible latency.

Real `gpt-realtime-2` calls exposed invalid unused/target arguments, motivating
the generic exact-call correction path. Subsequent real calls confirm accepted
typed context reads and normal error output without fatal activation or Task
effects. OS audio probes are separate from a browser/microphone/human journey;
retain their actual result and limitations in private evidence.

`run-222941` additionally verifies real work continuing during an interjection,
an independent spoken arithmetic answer with actual OS playback/ACK, and fresh
admission of the completed work's result. It ended before full work-result audio
ACK and cannot prove that last boundary. The next `run-223140`, using improved
tool descriptions, is retained as a failure: VAD split the longer interjection
into three turns, the model queried analysis instead of answering the arithmetic,
and its incomplete audio exposed the work-delivery deadlock repaired above.
The model/turn-segmentation failure is distinct from that fixed scheduler bug;
a later shorter-input probe cannot erase or close it. Neither sample measures
browser first-audible latency because the OS sink buffers each response.

`run-223811` reached real work acceptance and exposed a separate cancellation
race: STOP sent an exact Provider cancel, `response.done(completed)` arrived, and
Provider then returned `response_cancel_not_active`, which the Engine treated as
fatal. The correction recognizes only that error type/code linked to the exact
locally sent cancel for an already fenced response. It does not invent a terminal
event: error-before-done still blocks replacement until real done; error-after-
done and duplicate old errors cannot affect a newer response. Unknown, missing,
non-cancel or unfenced identities and other error codes/types still fail closed.
The initial failed probe did not preserve the error's client event ID; subsequent
connected evidence must retain it before claiming real correlation coverage.
Eight exact/mismatched/reordered cancellation-error cases pass. The same seven
integrated Native business/Runtime/Engine/Gateway modules pass **385/385**
(`cancel-integration.txt`); known correlated cancellation races receive safe
content-free INFO diagnostics, rather than being silently ignored or fatal.

The next `run-224408` proves the real conversational overlap on the integrated
source: work accepted at 35.547 s; Agent execution 34.719–54.438 s; interjection
began at 35.579 s; Provider VAD end at 40.297 s and the direct answer's first
audio frame at 41.313 s. Actual OS playback completed and was ACKed at 42.688 s.
The independently admitted result followed at 55.235 s, with first audio frame
at 56.219 s. This is one synthetic question and received-frame timing, not a
microphone or browser latency benchmark.

That result response ended `incomplete` with the recorded Provider reason
`max_output_tokens`. It had read internal work identity/revision metadata under
the initial instruction to preserve work identity. The owned correction makes
autonomous completion speech a short verified conclusion, keeps identity in
routing data, preserves the complete queried result, and logs safe unsuccessful
Provider status/reason. It does not increase the existing 1024 shared audio/text
output-token budget. Unbounded or long spoken-result delivery is not claimed;
incomplete speech cannot earn full-playback or history credit.
Five diagnostic cases and the actual scheduled-notification contract are checked
in the Engine suite (**160 passes**). On the integrated source, Engine, business
Registry, audio diagnostics and profiling pass **202/202** (`delivery-final.txt`).
The same-input real completion/OS-ACK result and its exact source hashes are
recorded in `logs/native-conversation-execution/real-provider-business-evidence/`;
the original incomplete run remains a failed sample.

Deployment uses the existing controlled launcher, Native voice model/profile,
registered project and data, without consuming notifications in a browser.
`logs/live_voice_runtime_contract.json` and the packet's private
`deployment-verification.json` bind the actual committed source, served asset
hash, ports, readiness and real Speech round trip. Read-only before/after
fingerprints cover existing Task tables and project files. A complete current
microphone/speaker A/B/A2 journey, perceived latency comparison and the broader
regression gaps remain open; this packet does not grant product-candidate PASS.
