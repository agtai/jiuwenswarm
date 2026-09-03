# Task notification presentation repair — 2026-09-03

## Scope recorded before implementation

Baseline: `1576313d40ae4a5cd2b602fe0d11fa1cc42ee0f1`.
The user requested repair of duplicate accepted announcements, notification
timestamps/foreground elapsed time, and unusable temporary result paths.

- Notification presentation (Tier 2): suppress initial `task.accepted` at the
  product presentation sinks and skip it in unread presentation selection.
  Keep the canonical event and internal Arbiter lifecycle projection; no forged
  displayed/played ACK. Running, blocked, decision and terminal notifications
  remain presentable. Retry/recovery accepted retain their existing policy.
  Own `task_progress_return.py`, `presentation_ledger.py`,
  `product_composition_registry.py` and affected notification tests.
- Timeline (Tier 1): identify Task notifications by their existing persisted
  response identity, show independent metadata and exclude them from foreground
  elapsed time. Own `buildTurnTimeline.ts` and focused frontend tests. No new
  message schema, text classifier or notification/ACK authority.
- Result location (Tier 2): relocate references to actual result artifacts from
  the isolated checkout to the registered project before durable result capture;
  retain existing apply/hash/seal gates. Own `project_code_executor.py` and its
  tests. No rewriting old sealed results, filenames, file contents or user input.

Applicable checks: positive presentation/result, invalid or unrelated identity,
empty/notification-only timeline, state/order/duplicate/recovery, scope isolation,
text/voice fallback, preserved foreground behavior and real component seams.
Existing state/concurrency/failure tests cover unchanged owners; add checks for
zero presentation/ACK effects of initial accepted and truthful later delivery.
No change to Task lifecycle, Store schema, security, Provider/account settings,
model routing, or project registration. Full physical A/B/A2, Native, cumulative
review and latency optimization remain outside this batch. Project stays PARTIAL.

## Verification

Implemented: the presentation classification skips initial accepted, while the
internal progress projection continues to establish the Arbiter lifecycle. Both
integrated sinks and the deferred queue suppress its presentation; feature-off
legacy transport stays unchanged. No Store event is deleted and no ACK is minted
for a hidden notification. Retry/recovery accepted policy is unchanged.

The timeline uses the persisted `response-task-progress-` namespace, not prose,
to keep notification metadata visible and exclude its timestamps from foreground
duration. Foreground elapsed time stays next to the last foreground activity.
The result adapter replaces only exact discovered-artifact paths (native paths,
forward slashes and file URIs), before durable capture. Existing apply/hash/seal
checks still determine whether a result can be published.

### Focused checks

From the repository root, each command uses
`.venv/Scripts/python.exe -X utf8 -m pytest --no-cov -q --tb=short --show-capture=no -o log_cli=false`:

- **21 passed**: `tests/unit_tests/live_voice/test_task_presentation_consumption.py tests/unit_tests/live_voice/test_project_code_executor.py -k "presentation or result_relocates or result_path_relocation or preserves_user_instruction or generic_task_can_seal"`.
- **9 passed**: `tests/unit_tests/live_voice/test_task_progress_return.py -k "projection_preserves_source_truth or voice_package_contract or text_live_route or cross_scope_events or duplicate_is_idempotent or concrete_authority_source_is_the_only or concrete_authority_source_replays_store_prefix"`.
- **18 passed**: `tests/unit_tests/live_voice/test_product_composition_registry.py -k "(real_store_progress or real_store_audio_resumes or agent_ack_drains or text_runtime_ack_then_core or audio_runtime_ack_then_core or audio_ack_wins_progress_close or p2_close_settles_shared_task or audio_playout_failure_falls_back or later_audio_failure_replays or text_progress_reaches_web_sink or requested_voice_progress_without_exact_origin or progress_authority_failure_allocates) and not unread_predecessor"`.
- From `jiuwenswarm/channels/web/frontend`, `npm run test:task-notification-timeline`: **5 passed**; `npm run build:live-voice`: TypeScript and Vite **passed**. Existing locale duplicate-key, mixed import and bundle-size warnings are not fixed here.

The Store seam verifies no presentation reservation for accepted-only unread
pages; real running ACK consumes through sequence 3, leaving the other class
untouched. Fault/recovery tests retain zero effects for wrong/stale ACKs, cover
lost ACK responses, shutdown races, fresh-session/process recovery, bounded
capacity, and AUDIO → TEXT prefix replay. Existing two-notification tests now use
running/terminal instead of accepted/running; their isolation oracles remain.
The Direct adapter test uses actual Git checkouts and retained files with a
controlled Agent; it checks cleanup, literal names, content/hash and durable text.
This is not real-model or physical-audio evidence by itself.

An initial command used the system Python without `openjiuwen`; validation was
rerun with the repository venv. A broader Task-progress invocation was stopped;
no full-suite PASS is claimed. Test-only sequence expectations, a fixture clock
and one renamed helper were corrected before the focused passing runs.

### Known failures compared with the baseline

An isolated detached checkout of `1576313d4` reproduced these existing failures:

- `test_unified_create_ack_releases_accepted_then_running_progress` reaches the
  dialogue Agent before the notification assertion (retired semantic fixture).
- `test_real_store_progress_replays_unread_predecessor_before_retry_attempt` and
  `test_real_store_voice_replays_unread_predecessor_before_retry_attempt` fail to
  produce the expected predecessor presentation.
- `test_real_store_text_projects_recovery_attempt_boundary` and
  `test_real_store_audio_projects_recovery_attempt_boundary` fail at presentation
  delivery; the audio snapshot reports `VOICE_SINK_FAILED`.

Baseline comparison used the same pytest options and these exact `-k` selections:
`"unified_create_ack_releases or real_store_voice_replays or real_store_text_projects_recovery or real_store_audio_projects_recovery"` (4 failures), then
`"real_store_progress_replays_unread_predecessor"` (1 failure).
They remain open; no claim of complete retry/recovery or cumulative regression.

### Real retained-file check and deployment

The same owned local formal runtime was restarted after checking zero live Tasks.
The existing private environment was reused; `.env` and `config.yaml` hashes
remained unchanged. Frontend bundle: `index-DkDgMvdJ.js`; final runtime parent
PID 6396, Agent PID 2384, frontend port 6175. These are run facts, not resume defaults.

One authenticated structured request used the real configured Agent and Direct
executor to create `通知路径复核.md` containing `notification check` and return its
absolute path. This was an API/file check with Live Voice off, not a microphone,
heard-playback or end-to-end notification acceptance run.

- Task: `task-b8a43cd42a9c46e7a6b34849028d14e6`.
- Attempt: `attempt-2ab1a83ef1cc4a388972e4a722bdeda6`.
- Both authoritative states: terminal/completed; no live Tasks left at inspection.
- accepted: `2026-09-03T19:26:29.697587Z`; running:
  `19:26:30.996678Z`; completed: `19:26:37.845328Z`.
- Queue about 1.30 s, execution about 6.85 s, accepted → completed about 8.15 s.
  This different, simple input is not a measured optimization over the earlier
  135-second case. Stable latency baselines/optimization remain open.
- Actual file SHA-256:
  `33f6078eecbd2233fad79fe7fda2c24edf586c01bf19c4cc1203476f8777f0a7`, matching the sealed artifact.
- Result text and refreshed Registry UI both point to the retained registered
  project file, not its disposable checkout. Old sealed results were not rewritten.

Final product file SHA-256 values:

| File | SHA-256 |
|---|---|
| `project_code_executor.py` | `b3e8f21dd1413f2b826efda099126a4cf184cdc7def5924c63b9aadd881cb095` |
| `product_composition_registry.py` | `975ddb0b2c49df494ce20b2582a0f4b93da6882e50a92ba81fdeeea711b1c49f` |
| `task_progress_return.py` | `18359dcad207c1fa9071d2c840a67044d9072b4a751d8807a5a482c7289c862b` |
| `buildTurnTimeline.ts` | `b91d69a0756d38195d9923d422912033f95ecf20d5cd4dea488eb42faea256c0` |

Complete scoped self-review covered source, oracle migration and retained authority
boundaries. Tool discovery exposed no independent review capability; self-review
is the unavailable-tool substitute and does not close independent review. No
subagent review, full Demo, full test suite, cumulative review, Native business
journey or human microphone/speaker acceptance is claimed. Overall PARTIAL.
