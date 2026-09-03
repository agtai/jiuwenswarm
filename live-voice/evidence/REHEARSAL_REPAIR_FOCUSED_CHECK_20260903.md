# Rehearsal repair: focused checkpoint, 2026-09-03

Status: **PARTIAL; functional rehearsal candidate, not a latency or complete Demo acceptance.**

## Scope and source

Latest authorization: the user approved proceeding with the diagnosed rehearsal
repairs, including targeted latency reduction. Broad regression and repeated
complete Demo runs remain excluded. No new intent classifier, business-specific
rule, authority/schema change, provider configuration edit or external operation.

Branch `hx/0812_live_voice_w3`, base HEAD
`87248911fde2220be6a97f72f8c0210ac67d5b67`, ahead 7 / behind 0 at resume.
The inherited working candidate already contained extensive uncommitted changes.
This batch preserves those changes; it is not a new committed final candidate.
No staging, history rewrite or remote update was performed.

Machine-local evidence root:
`C:/Users/admin/AppData/Local/Temp/live-voice-approved-repair-20260903`.
`baseline/` and `approved-incremental.diff` distinguish this batch from the
inherited working tree. Each runtime `source*.json` records exact file hashes,
HEAD, working status and configuration hashes, without copying credentials.

## Repairs

- Tier 2, Cascade submission/listening: reopen capture while unified submission
  is pending. Retain an early correction against its exact local final, wait for
  the server's real response identity, then interrupt that response and submit
  the replacement once. Exit and stale captures cannot submit or cancel a Task.
- Tier 2, notification/UI ownership: an older presentation settlement cannot
  overwrite a newer submitting/waiting state. A Task notification deadline must
  use text fallback while foreground capture is pending, rather than force its
  EOT. Resume capture after an ACK barrier clears; wake a successor poll when an
  obsolete poll returns. Display pending notification work as processing/recovery.
- Tier 2, continuity: remove automatic second-pass extraction of presented
  analyses and the next-input recovery wait. Retain actual presented analysis
  and original authenticated USER requirements. Resolve them with the current
  input once; old structured proposal/confirmation records remain readable.
- Tier 1, bounded inference/narration: official DeepSeek bounded semantic and
  tool-disabled receipt calls use per-call non-thinking options. The actual SDK
  keeps the model name in request config, which must participate in capability
  resolution. Clone the isolated receipt model and restore it after settlement;
  full tool-using Agents and saved configuration remain unchanged.
- Tier 1, query narration: the current authoritative `formal_task_result`
  supersedes historical assistant claims. `dispatched` describes request
  dispatch, not Task execution. Put this rule in the formal system presentation
  instructions as well as the answer contract; ask for brief routine receipts.
  Log only request ID, Task ID and actual state/outcome for status diagnostics.
- Existing Web Task owner boundary: remove serial retry-inspection bootstrap
  from the accepted voice-answer path. Register the exact independent progress
  owner, start its authoritative reads separately, and refresh the actual Task
  collection. Querying an already watched Task does not bootstrap it again.

These are generic lifecycle, continuity, inference and presentation repairs.
Garden/travel utterances and expected results occur only in test inputs/oracles.

## Minimum verification actually performed

- Registry selection: 7 passed (contextual delegation/original requirements,
  replay, wrong-source/negated effect rejection, Native exact Task reads).
- Bounded inference/isolated adapter selection after the SDK model-name fix:
  9 passed, 21 deselected; `bounded-final.log`.
- Final authoritative query selection after system narration guidance:
  3 passed, 60 deselected; `query-contract-final.log`.
- Mounted selection: 13 passed in `mounted-final.log`; after decoupling Task
  discovery, 9 affected generation cases passed in `mounted-discovery.log` and
  the rebuilt mounted business bootstrap case passed in `mounted-bootstrap.log`.
  Early correction tests assert exact interruption, one replacement, no old
  audio/history/ACK and zero Task cancellation, including Exit.
- TypeScript check passed (`tsc-final.log`); Vite runtime builds passed.
  Existing duplicate locale-key and chunk-size warnings were not repaired here.
- Actual-provider semantic probes: analysis, direct delegation, missing objective,
  explicit negation and ambiguous cancellation; failed earlier samples retained.
  Final four-case selection passed in 1.27–2.31 seconds per semantic call;
  actual-history delegation with original requirements passed in 2.75 seconds.
  These numbers measure semantic inference, not end-to-end voice latency.
- Reviewed the complete incremental diff against the saved module baseline.
  No independent review tool was callable in this run; this self-review is an
  explicitly limited substitute, **not independent Tier 2 review credit**.

No full suite, complete A/B/A2 Demo, physical-device acceptance or renewed
complete Realtime route acceptance was performed.

## Real audio observations (isolated runtime, port 6176)

All business utterances entered an actual MediaStream and provider ASR, then
the production semantic/Registry/Agent path. Oracles read real SQLite state,
actual files, browser presentation and non-silent rendered PCM.

Task `task-add813e71da140c7b4764a4ed4c7c36f`, attempt
`attempt-998860408bbf49ae9de0d6727c0a9973`, was created once and completed.
The actual `runtime/business-project/园艺建议.md` contains the four recorded
plants, watering/light conclusions and the no-purchase boundary. This is a
bounded non-travel result, not a travel calculation acceptance.

| Attempt | Result | Speech end to first non-silent scheduled audio |
| --- | --- | --- |
| `garden-create.json`, initial repair build | One Task and actual artifact; still slow | 33.445 s |
| `garden-query-final.json`, intermediate build | Exact read/no mutation and audio passed the harness, but **manual content check FAILED**: completed Task was narrated as unfinished | 20.505 s |
| `garden-query-status.json`, final query repair | Same recorded question; correctly spoke completed, same Task/artifact, zero create/control effects | 17.325 s |

The harness PASS in the middle row does not assert natural-language factual
correctness and must not override the recorded content failure. The first row
is a create, so it is not an apples-to-apples latency comparison with a query.
The last two rows use the same audio. One sample each is not a percentile or a
stable performance guarantee.

Final query timestamps, local UTC+02:

- Unified request received 13:22:13.615.
- Semantic model 13:22:14.590–16.557; current receipt logged at 16.808 as
  `terminal / completed`.
- Formal narration model started 18.055; answer and adapter cleanup finished
  about 19.587. Actual model request contained `thinking.type=disabled`.
- P2 notification requests continued through 27.529; browser history showed
  the correct answer at 27 with a 13.95-second turn timer.
- Speech-end to first non-silent scheduled PCM: 17.325 seconds; provider EOT
  to that audio: 16.609 seconds. Capture reopened 1.415 seconds after EOT,
  while submission was still pending.

`timing-summary.json` records browser clock calculations, buffer hashes and
the WebAudio scheduling lead. This proves digital capture/render behavior,
not physical microphone/speaker latency. The remaining post-model
notification/media delay is material and is not closed by the inference fix.

## Handoff and open boundaries

The original port 6175 runtime is updated in place with the tool's owned-runtime
reuse path. `demo-before-update.json` / `demo-after-update.json` compare original
Task rows, result rows, command rows and project file hashes. Original A/B were
both already terminal/completed before restart; their immutability is preserved.

Still open:

1. Stable few-second end-to-end latency. This batch removed evidenced serial
   work, but the final real query still took 17.325 seconds to first audio.
   Separate remaining authority/notification transport/media waits before
   making another optimization claim; do not skip authorization to save time.
2. Physical generation-time and playback-time interruption, speaker echo and
   ASR accuracy. Listening-window software evidence does not replace this.
3. The original A terminal-notification/ACK gap and complete offline recovery /
   refresh deduplication were not reproduced to closure in this minimal run.
4. The ordinary chat read-aloud button still requests `tts.synthesize`, which has
   no registered server handler. This is separate from formal Live Voice media;
   re-enabling an allowlist string alone would not implement that missing route.
5. Independent review, remaining affected acceptance and final committed-source
   human Demo/hardcode acceptance. Earlier historical PASS cannot cover this
   uncommitted candidate or unrun scenarios.

Therefore this checkpoint may be used for a functional pre-rehearsal, but must
not be described as complete delivery or “only human acceptance remains.”
