# Rehearsal query, interruption and notification repair — 2026-09-03

Disposition: **PARTIAL; targeted repairs deployed for rehearsal, not full Demo
or physical acceptance.** This follows the user's repair instruction and the
[interruption/query diagnosis](REHEARSAL_INTERRUPTION_QUERY_DIAGNOSIS_20260903.md)
and [latency breakdown](REHEARSAL_REPLY_LATENCY_BREAKDOWN_20260903.md).

## Source and ownership

HEAD remains `87248911fde2220be6a97f72f8c0210ac67d5b67` on
`hx/0812_live_voice_w3`, ahead 7 / behind 0. The inherited dirty candidate is
preserved. No commit, history rewrite or push was performed. Eight product
files changed relative to the start-of-repair backups; their sorted path/hash
map has aggregate SHA-256
`343758898acbfb1d16f3301082edc433f0022afa872e7c53c00a3f02f04ae2dc`.

Private evidence root:
`C:\Users\admin\AppData\Local\Temp\live-voice-rehearsal-repair-20260903-150710`.
It contains `before`, `repair.diff`, `final-product-manifest.json`, focused
check logs, real-model reports and deployment/data fingerprints. Provider
configuration was read in place and its hashes remained unchanged.

Tier 2 owns existing semantic retry/continuity, exact interrupted context,
notification scheduling and capture settlement. Tier 1 owns spoken guidance
and notification language projection. No protocol/schema/migration, new
classifier, Task authorization, provider change or domain-specific business
answer was introduced. Numeric query limits and lifecycle notification strings
are protocol/presentation constraints, not decisions about the Demo's business.

## Changes and bounded evidence

| Boundary | Change | Evidence and limit |
|---|---|---|
| Query validation | Give operation-specific required fields and safe structural feedback; retain two total tool-free attempts, one deadline and authority recheck | Missing status/list argument cases pass. A real replay of the reported query produced `task.list`, `query_kind=list`, `limit=20` in 3.235 s. Injected malformed output regenerated structurally valid status arguments in 1.922 s; a null target still needs downstream resolution/clarification. No Task effect was executed by these model-only probes. |
| Generation correction | Preserve the exact interrupted committed user question in formal context and bounded semantic history; never invent an assistant answer or revive fenced output | Context/isolation/bounds and generation-fence checks pass. Real Agent reads files and completes an air/train comparison instead of merely acknowledging the correction. The recommendation itself still fails the quality check below. |
| Listening state | Release an empty notification fetch when no foreground input, retained presentation, ACK or deferred Task owns capture; display actual capturing/playing before generic Agent waiting | Mounted correction test now checks replacement ACK followed by actual capture. Existing nonterminal Task AUDIO, stale Task TEXT, Exit and feature-off cases pass. The exact historical frontend state at 14:43 remains unavailable; this is not proof of its sole cause. |
| Task notifications | Do not clear every Task's pending-notification flag when one Task completes; localize exact Task progress and text fallback consistently from Task instruction | Existing real-store deferred-presentation/ACK checks and frontend fallback identity checks pass. The specific full A/B/offline/unread journey was not repeated; historical missing A delivery is not retroactively declared fixed by a local test. |
| Post-Agent delay | Skip Task presentation preparation while the existing foreground-safety gate forbids it; apply the frontend 500 ms backoff only to keepalives, not real progress | Foreground busy/free, exact replay, batch barrier and effect-free keepalive checks pass. Slow notification pulls now log preparation, receive, settlement and total time. No paired real-audio before/after latency claim is made. |
| Grounding/brevity | Reconcile spoken length guidance; require whole-sequence deadline checks, checked arithmetic and evidence for actions claimed inside drafts | Real arithmetic sample returns 17:40 / 16:10. One real completed Task sealed `check.json` with those values and a draft stating alternative transport is not booked or changed. Broad foreground correctness and brevity remain failed. |

The real background Task was `task-fce62ecc450a4583a0c2f58cc1c91933` in its
own disposable project. Completion, exact specification, artifact set/hash and
unchanged input file were asserted. It took 71.344 s through task execution and
cleanup; that duration is **not voice first-audio latency**. No booking,
refund or message was sent. This is a sealed-file check, not the full voice
business journey.

## Verification and retained failures

- Focused semantic structural-retry checks: 7 passed. Focused continuity,
  generation fence and formal-context regressions: 6 passed. Final bounded
  history/foreground priority/keepalive selection: 4 passed (226 deselected).
  The final pytest invocation took 141.16 s including repository-configured
  coverage processing; no full test suite was run.
- Registry terminal-result, foreground busy/free, batch order/replay and
  deferred Task presentation/ACK cases passed. The changed test double now
  implements the same authoritative Task fact read used by production.
- Initial targeted mounted frontend selection: 5 passed; additional stale
  TEXT/Exit/feature-off checks: 4 passed; strengthened replacement-to-capture
  case: 1 passed. These are automation, not physical microphone/speaker evidence.
- TypeScript check, targeted bundle, final Vite build, scoped Ruff correctness
  checks and scoped whitespace diff checks passed. Existing duplicate locale
  key / large bundle warnings remain disclosed build warnings.
- Early added tests exposed a misplaced test helper and empty assistant context;
  both were repaired and affected cases rerun. Probe setup attempts using an
  incorrect import/interpreter are retained as harness failures. Two successful
  provider runs saved their reports before a Windows stdout encoding failure;
  saved assertions/results were separately validated without reissuing work.
- The **latest foreground comparison still recommends T01**, which would need
  departure at 15:55 (17:35 minus 30-minute station margin minus 70-minute
  connection) before the material's 16:00 reference time. It also exceeds the
  requested spoken brevity. Both pre-guidance and post-guidance answers remain
  in evidence. Generic prompt changes alone have not closed this problem.
- The latest real foreground comparison took 16.813 s at the Agent seam;
  the previous one took 19.5 s. They are not controlled first-audio samples.
  End-of-speech endpointing and actual speaker onset still need correlated
  browser/audio measurements. Recognition timeout/degradation near capture
  closure remains unclassified rather than being labeled a network failure.

Cold review covered the complete incremental product diff against its private
baseline. No independent local review tool was available; this self-review is
an unavailable-tool substitute with **no independent review credit**. Candidate
cumulative review and the full human journey remain open. Applicable bounded
checks cover P/N/B/S/T/C/R/I/F/K/X across the touched seams; process-crash
durability and physical Provider quality are not claimed by this batch.

## Retained rehearsal deployment

The owned 6175 runtime was stopped through its own control marker and rebuilt
with `--reuse-owned-runtime`. Final `ready.json` identifies its new owned
processes. HTTP for the existing chat returns 200; the deployed product-file
hashes match the tested working tree. Read-only before/after fingerprints prove
the original **6 Tasks**, attempts, results, commands, Task/Executor events and
business project files are unchanged. No result notification was deliberately
consumed by the deployment check.

This candidate is available to retest query parsing, correction completion and
capture/notification recovery. It is not yet a reliable full Demo candidate:
foreground recommendation quality, measured few-second first audio, complete
multi-Task/offline/revision acceptance and independent/cumulative review remain
open. Do not ask the user to treat those gaps as already passed.
