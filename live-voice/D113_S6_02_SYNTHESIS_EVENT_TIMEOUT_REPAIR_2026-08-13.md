# D113 S6-02 synthesis event-timeout repair

> Frozen review record for source commit `10062c3e` on 2026-08-13. Current
> milestone state and next actions remain authoritative in [STATUS.md](STATUS.md).

## 1. Packet and result

- Stage/node: `S6 - Alpha Module Closure` / `A1`.
- Task: `S6-02`.
- Track/modules: P1 AIO/SR/SS and Shared-X Web/Gateway composition.
- Risk: Tier 2 because the change alters a bounded streaming-lifetime contract.
- Base: remote candidate `e83d4d85f`; comparison baseline `2a69c2b87`.
- Tested source: `10062c3e` (`fix(live-voice): make synthesis timeout event-scoped`).
- Result: defect 11 is source-fixed and automated-verified. `S6-02` remains
  `ENVIRONMENT` because the required real-path rollback proof and physical
  re-listen could not run in this execution environment.

The scope was limited to synthesis timeout semantics, the OpenAI streaming
Adapter, Gateway streaming composition, the browser RPC declaration and their
tests. It did not change Speech credentials, provider/model selection, media
authority, Task authority, browser permissions, deployment topology or the
candidate defect-12 audio-buffer behavior.

## 2. Design checkpoint

The public Web RPC field remains `timeout_ms`. Its meaning is route-dependent:

- batch recognition and batch synthesis retain their existing whole-operation
  budget;
- when synthesis selects the streaming route, `timeout_ms` is the maximum idle
  interval until the next valid Provider synthesis event;
- every accepted non-terminal synthesis event renews that interval;
- SSE comments and blank lines do not renew it;
- the Gateway route applies the smaller of the request interval and its own
  hard provider-event upper bound;
- no finite whole-stream duration is reintroduced.

This preserves the existing fail-closed behavior for a stalled Provider while
allowing a healthy speech stream to exceed 15 seconds. The request timeout stays
in the request-binding digest. A pre-first-audio failure remains eligible for
exactly one batch fallback with the original `timeout_ms`; a failure after audio
delivery remains ineligible for batch replay.

## 3. Implementation and scenario review

The internal request now names `event_timeout_seconds` explicitly. The
conformance owner slides its event deadline after each valid non-terminal event.
The OpenAI Adapter bounds stream open and each complete data-bearing SSE event
separately, rather than wrapping the entire stream in one timeout. The Gateway
producer uses the request interval as well as its internal hard limit. The
browser client uses separate batch and streaming-synthesis constants even though
both currently default to 15 seconds, making the different semantics explicit.

Reviewed scenarios:

| Scenario | Result |
|---|---|
| Meaningful events each arrive inside the budget while total duration exceeds it | PASS |
| Provider stalls before the next data event | PASS, bounded timeout and degradation |
| SSE comments arrive but no data event arrives | PASS, comments do not extend the budget |
| Gateway internal event cap is longer than the request budget | PASS, request budget wins |
| Pre-first-audio streaming failure | PASS, one batch fallback retains original `timeout_ms` |
| Batch route selected directly | PASS, original whole-operation semantics retained |
| Request binding changes only by event timeout | PASS, binding changes |
| Forbidden Agent, Tool, Task, history, Store and cross-scope effects | PASS, zero asserted by affected conformance tests |

The complete scoped diff received a cold self-review. A first independent review
attempt was interrupted by the installed CLI's model/config incompatibility; a
second read-only review completed with `gpt-5.4` at low reasoning and reported no
actionable finding. Before that completed review, the cold review identified and
repaired the Gateway fixed-20-second/request-budget mismatch described above.

## 4. Regression distinguishability

The paced Adapter regression was added before the repair and run against the old
whole-stream implementation. With a 300 ms budget and three meaningful SSE
events spaced 120 ms apart, it failed after approximately 312 ms with
`STREAMING_SPEECH_PROVIDER_TIMEOUT`, even though every event was timely. With
the repair restored, the same test passes and produces the ordered started,
audio and completed sequence.

The existing bounded-stall test still passes. A new comment-only stream test
also times out, proving that transport keepalives cannot keep a silent synthesis
alive. A Gateway regression proves that a 20 ms request interval bounds a route
whose internal provider-event upper limit is one second.

## 5. Automated verification

- Live Voice unit plus integration suites: `1503 passed, 2 skipped`, one warning,
  113.38 seconds.
- Gateway unit suite after the final route correction: `845 passed, 4 skipped,
  2 failed`, 24.68 seconds. The two failures are unchanged, unrelated Windows
  path-expectation failures in `test_harmonyos_dev.py` and
  `test_upload_storage.py`; no touched Live Voice test failed.
- Frontend Gateway batch-Speech suite: `29 passed`.
- Frontend Integrated Web suite: `315 passed`; only the existing duplicate i18n
  key warnings were emitted.
- Production frontend build with Integrated Web, P1 and P3 mutation enabled and
  the retired streaming/task-demo flags absent: PASS, 4,640 modules transformed;
  only the existing large-chunk warning was emitted.
- Ruff on every affected Python source/test and `git diff --check`: PASS.
- Independent read-only Tier 2 review: PASS, no actionable finding.

## 6. Real-path and physical status

The requested private run root, its browser profile and the specified worktree
were not mounted in this execution environment. The equivalent clean
integration worktree was fast-forwarded to the same remote candidate before
implementation. Ports 443, 18092, 19000 and 19001 were down,
and `https://live-voice.localhost` was unreachable. Therefore the mandated
`services.py` startup, real-paced `s6_02_realtime_playout.py` run and real-path
revert-fail/restore-pass proof did not run. No new sample, p50, p95 or heard
playout claim is made; D112 remains the last real-path measurement record.

Defect 11 is consequently `FIXED / AUTOMATED_VERIFIED / REAL_PATH_PENDING`.
The user's last heard-playout O5 result remains FAIL until the repaired build is
deployed to the private topology and a greater-than-15-second answer is heard to
completion. O6 hidden/background/resume is still unobserved.

Candidate defect 12, described as tearing/clicking or electrical-sounding audio,
remains `UNMEASURED`. No buffer-size or playout fix was made. Diagnosis still
requires browser AudioWorklet underrun counts, frame interarrival distribution
and in-flight watermark measurements on the real topology before attribution.

## 7. S6 closure and Git state at record freeze

| Task | Status | Evidence consequence |
|---|---|---|
| S6-01 | `SATISFIED` | Unchanged from D112. |
| S6-02 | `ENVIRONMENT` | Defect 11 source-fixed; real-path proof, O5 re-listen, O6 and defect-12 measurements remain. |
| S6-03 | `SATISFIED` | Unchanged real media-route evidence from D112. |
| S6-04 | `SATISFIED` | Unchanged real P3alpha evidence from D112. |
| S6-05 | `SATISFIED` | Unchanged observability/privacy/Web evidence from D112. |
| S6-06 | `SATISFIED` | Unchanged joint-route evidence from D112. |

No remote ref was updated. Machine-private credentials, provider configuration,
browser data, raw audio and private run artifacts remain outside Git.
