# September 8 three-fix execution boundary

## Accepted scope

The user accepted tearing and ordinary first-sound latency under the measured
browser EOT-to-start criterion and explicitly requested repairs 1–3. This resumes
only the following work, not the earlier full six-hour backlog:

1. Unplayed Task completion announcements retain identity and retry at idle after
   yielding; no false audio/history ACK and no duplicate speech.
2. Reduce voice Task create/query/adjust feedback latency and prevent a transient
   background observation timeout from closing the usable Native media stream.
3. Allow a short truthful spoken preamble while the actual tool runs. Durable
   acceptance/application/completion claims still require the real tool receipt.
   The user clarified that wording must remain natural and request-specific;
   examples such as “我来查一下” are not fixed response templates.

Task-intent interpretation and the rejected early-tea adjustment (item 4) are
excluded. Preserve gpt-realtime-2.1, speed 1.25, selected Jiuwen Agent, original
source/file protections, exact scope authority and the existing ordinary audio
path. No new classifier, wire protocol or persisted schema is planned.

## Owned boundary and verification

Tier 2: notification ownership/retry and Native business/audio concurrency.
The real Registry regression exposed consumed Speech response/unit authority
after an unplayed cancellation. Its repair is a Tier 3 sub-boundary: a local
issuer-only predecessor permit, minted only for the same authenticated unread
notification after zero attach/emitted frames/receipts and completed cleanup.
The old permits/tickets are revoked; arbitrary same-generation replacements
remain rejected. This is necessary to restore the already accepted idle retry,
with no wire/schema or additional product behavior change. Review and tests
include this shared authority seam and interruption before admission.
Owners are Integrated Web/P1 notification presentation, Native Gateway observation
and Engine business continuations, and the business router's redundant reads.
Tests follow these surfaces; positive business calls must still execute once,
and stale/cancelled/cross-scope paths must have zero forbidden effects.

Acceptance covers idle replay after preparation-time activity, real user speech
priority, duplicate/late/closed-owner fencing, transient observation recovery,
fatal authority failure, tool/preamble concurrency, truthful successor results,
and no ordinary-response regression. Use focused frontend/Python regressions,
frontend typecheck/build, complete scoped diff review and an independent review
where available. Bind actual Provider/Agent/Task checks to the clean candidate;
record measured results and failures separately from human speaker acceptance.

The controlled local deployment authority from this task persists. Preserve the
existing private runtime/data and take readiness checks before handing it back.
Do not update remote refs. Physical results are reported only when observed.

## Execution evidence

Implementation, scoped review, controlled deployment and actual Provider
measurements are complete. Human playback acceptance remains open. The preceding
[human-session diagnosis](REALTIME_HUMAN_ACCEPTANCE_DIAGNOSIS_20260908.md) supplies
the regression evidence; it is not proof that these repairs have passed.

- Python: 586 passed (`logs/three-fixes-python-final.txt`), including actual
  Registry/streaming/media seams, cancellation during cleanup and before the
  replacement producer starts, single render receipt, attached/stale rejections,
  observation timeout retry, business authority and receipt-only continuations.
- Integrated frontend: 717 tests, 705 passed, 11 failed, 1 skipped
  (`logs/three-fixes-web-final.txt`). All 11 failures match the earlier
  `logs/repair-20260908/frontend-integrated.txt` baseline: the old product-entry
  source assertion and retired bounded Task-intent/mutation UI fixtures. They
  are excluded from this fix; the entire suite is not claimed green.
- New mounted preparation-time speaker yield/idle replay and close-pending
  cases pass. P1 covers a single noise frame decaying before readiness, a user
  arriving during claim, single eventual receipt and exact BUSY retries.
- Full scoped cold review and an independent review completed. The independent
  reviewer reproduced the original authority/retry failures, then verified
  early-cancel → third preparation succeeds, old permits fail and no early ACK.
  Its Engine probe separately verified simultaneous preamble/tool admission,
  exact ACK-gated successor, wrong ACK rejection and STOP fencing late PCM.

Recovery is bounded: each exact cleanup BUSY wait allows 2 seconds and P1 makes
at most 3 attempts, separated by 250 ms with current-owner/cancellation checks.
The approximately 6.5-second budget is cleanup waiting only, not total network
or TTS time. A producer that never exits is not discarded to admit replacements;
exhaustion remains an explicit text fallback, never a fake audio receipt.
Preparation retention remains 30 seconds. These limits are distinct from an
ordinary temporary speaker yield successfully replaying at idle.

## Deployed candidate and measured outcome

Code commit `fff2fe15b7` — `fix(live-voice): replay unplayed notifications and
acknowledge task operations promptly` — is deployed from a clean source tree.
The controlled launcher rebuilt the frontend, restarted the managed services,
and passed real TTS→STT/receipt and wrong-identity/forged-claim readiness checks.
Runtime contract retains gpt-realtime-2.1, audio speed 1.25, minimal reasoning,
server-VAD-450 and selected Agent deepseek-v4-flash#0. Ports 5173/18092/19000/19001
are listening. Build/typecheck and `git diff --check` passed; no remote update.

Actual public Web RPC + real-time injected PCM, isolated Session
`web_1a080b11425_0bfacc12d365`, produced these single-sample measurements:

| Operation | Provider EOT observed → first PCM sent | Arguments complete → receipt returned to Realtime | EOT → receipt returned |
| --- | ---: | ---: | ---: |
| Task create | 1.270 s | 0.542 s | 3.850 s |
| Task status | 0.876 s | 0.602 s | 3.819 s |
| Task adjust | 1.165 s | 0.653 s | 3.988 s |
| Ordinary chat control | 1.284 s | — | — |

Every interval uses one Gateway monotonic clock and the exact committed turn;
the long create input contained intermediate VAD endpoints, which are not the
endpoint of the final response. Synthetic input's last non-silent sample to
recorded PCM was respectively 1.920/1.556/1.822/1.993 s. Neither metric measures
browser AudioContext start or physical speaker onset. The old status-query
arguments-complete→receipt interval was 7.651 s; the new sample is 0.602 s.
This is a comparable service seam, not a statistical latency guarantee or a
comparison of the old 15.547-second browser metric with a new server metric.

The real Provider supplied request-specific preambles for creating the report,
checking its progress and adjusting its contents. No fixed Chinese phrase is
imposed. The CLI acknowledges recording-buffer enqueue only, never playback,
so the later receipt/result spoken successor correctly remains gated; its
end-to-end audible latency is **not measured** by this probe.

One actual Task was accepted and completed in 98.856 s, creating
`验收输出/九月八日语音反馈验证.md`; hashes of all pre-existing project files were
unchanged. The same Task's adjustment was actually applied. Its application
waited 18.328 s after request for the existing background checkpoint; the fast
0.653-second receipt does not mean the adjustment was already applied. This
execution wait is retained and must not be presented as a solved sub-second
mutation-completion metric.

The actual completed Task was registered through the same public voice-progress
activation used by the UI. Its real terminal AUDIO notification passed
prepare→claim→cancel→new preparation→claim with formal
`openai-streaming-speech` / `gpt-4o-mini-tts-2025-12-15` / marin. Both claims
succeeded; no child was attached and no playback/history ACK was sent. This
closes the real Provider permission/re-preparation seam; mounted/P1 tests cover
idle replay and one eventual render ACK. Physical notification playback remains
for the user's refreshed browser/device acceptance.

Private evidence is in `logs/three-fixes-deploy.txt`,
`logs/three-fixes-real-provider-recheck.txt`,
`logs/three-fixes-real-notification-progress.txt`, and
`logs/repair-20260908/three-fixes-{session,measurements,diagnostics,notification-result}.json`.
Initial CLI trials are retained separately: a probe-only null optional-field
error aborted early, and a silent observer omitted the UI's voice-progress
registration. Neither is counted as successful product evidence. The corrected
public-route probes above completed without errors.

The candidate is ready for human acceptance after refreshing the page and
starting a new Live Voice activation. Remaining checks are actual idle completion
announcement/replay and complete spoken-result timing on that browser/device.
The excluded Task-intent/result semantics and broader historical backlog were
not resumed. This report does not promote whole-project status to PASS.
