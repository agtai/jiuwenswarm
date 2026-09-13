# Answer hardcode retirement

## Accepted scope

The user authorized six repairs and one local commit, on baseline `cbb56e727`:
authoritative Agent explanations of Task control/results; removal of business
analysis instructions from the voice adapter; lossless regular/legacy TTS;
removal of successor-name derivation; retirement of the unreachable legacy
Chinese Task bridge; and complete bounded Task-result context delivery.

Native-specific interaction/response generation, language selection, workspace
admission/execution design and the disabled critical-token policy are excluded.
No deployment, provider reconfiguration or remote update is authorized here.

## Intended behavior and ownership

- Registry / Agent Bridge (Tier 2): successful authorized control and unavailable
  result receipts reach one tool-disabled Agent answer, with exact server facts.
  Invalid, unauthorized and stale operations retain their fail-closed paths.
  Task snapshots include existing admission, execution and adjustment reasons;
  missing reasons remain unknown. No lexical question classifier or second
  answer-rewriting model is introduced. Native-only templates remain deferred.
- Result context (Tier 2): preserve the complete stored result through bounded
  pages, each at most 32 KiB, with explicit source/range/completeness metadata.
  Source and page-count limits bound aggregate input; exceeding them rejects
  explicitly. History yields whole oldest pairs to reserve result pages. The
  Agent has no new tools, file permissions or result authority.
- Voice instructions (Tier 1): retain current-turn, context and truthful receipt
  boundaries; remove clocks, deadline arithmetic and mandatory work-offer policy.
  Existing Agent/project instructions retain their own ownership.
- TTS (Tier 2): preserve URLs, code, paths and long text; synthesize/play bounded
  chunks with cancellation/ownership checks. No text-prefix status classifier.
- Legacy retirement (Tier 1): remove business successor derivation and the
  unreachable frontend bridge cluster. Preserve current semantic explicit specs,
  identity, confirmation, replay and state regression scenarios in their owners.

## Implementation / verification sequence

1. Add failing behavior regressions for Agent receipt delivery, full result pages,
   faithful long TTS and explicit successor specifications.
2. Implement backend receipt/context/prompt repair, then frontend TTS and legacy
   retirement. Inventory legacy test scenarios before deleting their old owners.
3. Run focused Python and Node regressions, affected frontend build/typecheck,
   current Task intent/Agent bridge integration checks and scoped diff review.
4. Complete one independent module review, fix affected findings, record evidence,
   update STATUS and make one reviewed local commit.

Applicable Tier-2 dimensions: positive/negative/bounds, cancellation/stale/replay,
identity/isolation, no-tools enforcement, failure and integration compatibility.
No new public RPC/schema, durable state or physical audio contract is claimed.
Real model speech quality and physical listening remain candidate acceptance.

## Verification evidence

Implemented on `cbb56e727` as one scoped working diff; the containing commit
identifies the final source. No service restart, deployment or remote update.

- Python: current semantic Registry/SQLite, Task semantics, classifier, resolver
  trust and formal Agent adapter suites: **252 passed**. Focused authenticated
  P3 snapshot/status/adjustment/result checks: **10 passed**. Result page/bounds
  checks in the lifecycle Registry module: **5 passed**. Tests use the repository
  `.venv/Scripts/python.exe`, isolated `JIUWENSWARM_DATA_DIR` and per-run pytest
  temporary directories; model/executor ports are controlled, not live-model
  classification or physical speech evidence.
- Frontend: lossless TTS text **10 passed**, streaming continuation **18 passed**,
  TTS playback **6 passed** (including mounted browser hook, stop/unmount, late
  audio, duplicate final and changed final), current Task/input/result/ownership
  owners **99 passed**. `npm run build:live-voice` passed, including TypeScript.
  Existing duplicate locale keys and bundle-size warnings remain outside scope.
- Independent read-only review found four issues: missing recorded reasons,
  competing old/current status facts, duplicate-final playback and stale
  retirement references. Repairs and focused regressions cover all four. Main
  also reviewed the complete scoped diff and deletion callers.

The current status snapshot is the sole current-state authority. Earlier
unavailable-result observations have no attempt binding and are explicitly
marked as preceding that snapshot; they cannot deny a later completed result.
Regressions advance a real Task between the initial query and the snapshot.
Adjustment reasons come from exact requested-command events; admission reasons
come from persisted queue facts. Missing or window-excluded causes stay unknown.

Results are delivered in at most eight 32 KiB JSON context pages, bounded by the
existing executor's 32,768-character / 131,072-byte source contract. Ranges and a
source digest preserve reconstruction, including Unicode and JSON escaping.
Only whole oldest history groups yield to result pages. Artifact read limits
remain explicit, and unread artifact content cannot justify a missing-fact claim.

### Retired test ownership

| Retired parser/lane oracle | Current owner retained and checked |
|---|---|
| Interim/uncommitted speech, exact capture and replay | `unifiedCommittedInputOwner.test.mjs`, semantic Registry tests |
| Exact session/project/task/attempt and stale results | `formalTaskControlLeaf.test.mjs`, `formalTaskResultRoute.test.mjs` |
| Consent, mutation-unknown recovery, no duplicate dispatch | `formalTaskIntentRoute.test.mjs`, semantic Registry/SQLite tests |
| Pending versus applied, terminal cancellation and successor truth | `formalP3TaskExperience.test.mjs`, semantic Registry and resolver-trust tests |
| Speech order, bounded continuation, cancellation and ownership | `liveVoiceStreamingSpeech.test.mjs`, `ttsPlayback.test.mjs`, `ttsOutputOwnership.test.mjs` |

Fixed Chinese grammar, pipeline aliases, replacement-by-cancellation and old
poll cadence were implementation-specific oracles of the unreachable lane;
they are removed with it. The legacy speech core remains deferred. The mixed
retirement manifest entry lists only its retained sources/current oracle paths;
its historical Gate is not reactivated.

### Baseline failures separated from this repair

Broader checks are not reported as green:

- Lifecycle Registry suite has **61 pre-existing failures** from retired routes
  and dialogue-default fixtures. Replacing the four affected backend modules at
  import time with their exact `git show cbb56e727:<path>` content reproduced
  the identical failing test set (158 passed). One incorrectly placed new test
  was moved to the real semantic Registry/Store owner rather than expanding a
  fake language classifier.
- Integrated Web suite: **601 passed, 21 failed, 1 skipped**. Rebuilding the two
  affected mounted/entry test carriers with exact baseline TTS/hook source
  reproduced all **21** failing names (162 passed, 1 skipped in those two files).
  No additional failing names were introduced by the repair.
- Historical retirement-manifest suite: **9 passed, 2 pre-existing failures**,
  referring to already-removed `demo_fixture_contract.py` and
  `DEMO_ITINERARY_TASK_NAME`. Both are absent at the baseline. This batch's
  retained legacy entry paths were separately verified. It does not reopen or
  claim closure of that historical audit.

Focused commands used `pytest -o addopts='' -o log_cli=false --tb=short` for
`test_semantic_registry.py`, `test_task_semantics.py`,
`test_production_task_intent_classifier.py`,
`test_production_multi_task_resolver_trust.py` and
`agentserver/test_formal_live_voice_adapter.py`; P3 and result-page checks selected
only the affected snapshot/status/adjustment/result/bounds cases. Frontend
commands were `test:live-voice-tts-text`, `test:live-voice-streaming-speech`,
`test:tts-playback`, the five current Task/input test owners plus
`ttsOutputOwnership.test.mjs`, and `build:live-voice`.

Native-specific templates/single-entry result handling, project workspace
admission/execution policy and language selection remain excluded. Real model
answer quality and physical listening still need candidate acceptance.
