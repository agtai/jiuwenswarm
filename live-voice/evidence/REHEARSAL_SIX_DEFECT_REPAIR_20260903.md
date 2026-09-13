# Rehearsal repair batch — 2026-09-03

Disposition: **bounded repair with focused automated and real-model evidence;
not complete Demo, acoustic, artifact-quality or product acceptance.** This
follows the [recorded diagnosis](REHEARSAL_MEDIA_CONTEXT_DIAGNOSIS_20260903.md).

## Source and ownership

Baseline HEAD: `87248911fde2220be6a97f72f8c0210ac67d5b67`, branch
`hx/0812_live_voice_w3`, ahead 7 / behind 0 at observation. The inherited
candidate is preserved. No commit, history rewrite or remote update occurred.
Fourteen product/test files changed relative to private pre-edit backups; the
sorted path/hash map SHA-256 is
`3fe449d3e0e17f28265bf855e03c6cc0b0a2a5f21ef74282d7eabebbc7bd5dc0`.

Private evidence: `C:\Users\admin\AppData\Local\Temp\live-voice-six-repair-20260903`.
It contains `before`, `before.json`, `after.json`, normalized `scoped.diff`,
focused test logs, model probe scripts/results and runtime preservation records.
The runtime's `source.json` binds its full source snapshot, private configuration
hashes and deployment flags. Configuration is read in place, never copied.

Tier 2 covers semantic creation/adjustment review, interrupted-context packing
and exact audio/recovery ownership. Tier 1 covers spoken output, activity labels
and observability compatibility. Scope and the two model-driven follow-ups were
recorded in STATUS before implementation. No business keywords, task names,
fixture filenames, trip times, budgets or canned business answers were added to
production decisions. Internal model review has no tools; existing Task scope,
capability, replay and confirmation authority remains in force. No additional
user confirmation was added for clear direct creation.

## Changes

1. A candidate direct create now receives one independent, tool-free semantic
   check of current delegation and matching objective. Prior delegation or an
   assistant offer alone is insufficient. Denial/invalid review produces the
   normal foreground route, with no Task proposal or confirmation. The review
   shares the semantic deadline and rechecks authority before calling the model.
2. Registry receipt context accepts interrupted unanswered user entries. It
   reserves the receipt slot by removing whole oldest groups; orphan assistant
   entries remain invalid. This removes the recorded U/U/A packing failure.
3. P1 bounds downlink attachment at 3 seconds and first-frame availability at
   8 seconds after attachment. Failure retains the exact socket for cleanup,
   emits no render receipt, and exposes its stage. Integrated Web closes the
   failed P1 before retiring P2 and restoring capture, without replaying input,
   mutating Tasks or ACKing unheard audio. Actual successor capture clears the
   retired error label. Pending audio no longer appears as Ready.
4. A contextual adjustment review selects an exact prior user source plus new
   additions. The server copies that source verbatim and revalidates the same
   target/operation. It cannot select assistant text, change target, or rewrite
   raw ASR. Confirmation replay bypasses this reinterpretation.
5. The isolated formal adapter gives long or tool-backed answers one tool-free
   final revision using actual request/context/tool results. The verified
   provider uses per-call reasoning for this revision only, with a 12-second
   deadline; ordinary short dialogue skips it. Normal output is bounded to
   200 characters unless detailed speech was explicitly requested. Provider or
   invalid-revision failure preserves the original answer and logs failure;
   therefore this is not a universal brevity or arithmetic guarantee.
6. Optional observability reads the installed SDK's `setup` exports and avoids
   importing them when observability is inactive.

## Focused verification

- Python: semantic resolver and repair boundaries **86 passed**; formal Agent
  adapter **26 passed**. Checks include authorization recheck, frozen replay,
  invalid target revision, context bounds/orphans, tool-free revision and
  optional observability. These are selected files, not a full repository run.
- Browser automation: **5 P1 + 4 mounted tests passed**. Missing attachment and
  missing first frame close all sockets with zero audio/Task/Tool receipts;
  degraded capture and close ordering remain valid. Mounted recovery reaches
  actual capture with one submission, zero Task mutation, zero false audio ACK,
  and a Listening display. Replacement-generation and stale-output checks pass.
- TypeScript `tsc --noEmit` and scoped diff whitespace checks pass. The isolated
  Vite build passed in 46.57 seconds. Existing duplicate locale `empty` keys,
  large chunk and SDK deprecation warnings remain outside this repair.
- Real configured model: ordinary comparison stays foreground; clear delegation
  and a non-travel task resolve to direct creation. An intentionally injected
  wrong create candidate is rejected by the real secondary review. These probes
  have no Executor and prove semantics, not actual creation or audio.
- ASR/reference probe initially failed under guidance and under a paraphrasing
  review. Final source selection preserves “不考虑租车，只比较航班和高铁” and adds
  “如果今晚能走，就优先今晚出发” for the exact itinerary task.
- Arithmetic revision initially failed without reasoning. A bounded reasoning
  sample and the final production helper returned 16:10 for the flight and
  15:55 for the train, correctly rejecting the train at the supplied 16:00
  scenario clock. Revision took 4.36 seconds and 10.06 seconds respectively;
  these are model-only durations, not speech-end-to-first-sound measurements.

Cold review covered the complete normalized scoped diff. It corrected an
instruction sentence and the post-recovery stale error display; affected
checks were rerun. No independent review tool was available and no parallel
agent was authorized. This cold review is the recorded substitute, without
independent/cumulative review credit.

## Limits and handoff

The underlying cause of the original browser socket's missing attachment is
still unproven. The repair bounds and recovers that failure; it does not claim
the transport will never fail or that failed audio was heard. ASR acoustic
accuracy, all generated artifact calculations, complete Cascade/Realtime
business journeys and physical microphone/speaker acceptance remain unclaimed.
No existing Task was repaired, deleted, cancelled, regenerated or overwritten.
The controlled runtime is reused only after its eight Tasks reached terminal.
Performance optimization and cumulative candidate verification remain outside
this minimal repair batch.

Deployment check: all four owned services are listening and
`http://127.0.0.1:6175` serves `index-D3bhjaJ8.js`, byte-identical to the new
build (SHA-256 `07115697560afe2a70c0ec0c9a5efee7d82fd785305482fa0c4e2bba2d651db5`).
Eight Tasks, 24 command records and the project-material hash are unchanged;
private configuration hashes also match. `deployment.json` records the source
and served bundle checks. This is deployment evidence, not a voice journey.
