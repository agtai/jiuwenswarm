# Delegation, capture recovery and recent Tasks repair — 2026-09-03

Disposition: **deployed functional repair with focused evidence; not complete
Demo, performance, physical-audio or cumulative acceptance.**

## Scope and source

Baseline HEAD is `87248911fde2220be6a97f72f8c0210ac67d5b67` on
`hx/0812_live_voice_w3`, ahead 7 / behind 0 at resume. The inherited working
candidate contains extensive uncommitted changes. This repair was isolated
against private pre-edit file copies; no staging, commit, history rewrite or
remote update occurred. Committing the overlapping whole files would also
capture unrelated inherited work, so the deployed candidate remains a working
tree rather than a clean committed source point.

Private evidence is under
`C:/Users/admin/AppData/Local/Temp/live-voice-task-integration-20260903` and
contains the normalized scoped diff, path/hash maps, focused probes, runtime
before/after records and deployment report. Credentials and provider settings
remain in their original private configuration directory and are represented
only by hashes.

Tier 2 owns delegation verification and streaming recognition/media/capture
recovery. Tier 1 owns removal of the manual form and the scoped read-only Task
view. The packet excludes new protocol/schema, provider configuration, business
keywords, performance redesign, full suites and the complete physical Demo.

## Repairs

1. The secondary delegation verifier returns an exact nonempty quote from the
   current user input. One malformed verifier result gets one tool-free retry
   under the existing semantic deadline and authority recheck. A second invalid
   result fails closed. A valid negative verdict remains foreground dialogue
   with zero Task effect and no confirmation prompt. This replaces unreliable
   model-generated character indices; it does not add a task-name, location,
   travel, budget or phrase classifier.
2. A failed streaming recognition receive/send path sets a typed failure event.
   `next_recognition_event` races that event against provider output and wakes
   immediately rather than waiting for the long recognition timeout.
3. The production Cascade media registration closes the uplink with
   `MEDIA_CONSUMER_FAILED` when its negotiated speech-start/EOT source fails.
   The compatibility default still permits manual fallback for non-product
   callers. Product P1 maps only negotiated uplink consumer failure to
   `SPEECH_RECOGNITION_STREAM_FAILED`.
4. Integrated Web performs one bounded capture-only retry per active voice-loop
   generation for recognition-stream or capture-duration failure. Exact session,
   P2 activation, Exit, presentation and barge-in fences remain in force. The
   retry does not replay recognized text, call the Agent, mutate a Task or emit a
   presentation ACK.
5. The bottom formal Task creation/control form is removed. A small Zustand view
   shares the existing `FormalP3TaskExperienceOwner` with the normal right-side
   recent-tasks panel. It filters exact session/project scope, displays the
   Registry Task ID/state/progress/result and calls the same owner's refresh and
   select operations. It does not persist or synthesize a Todo/Task copy.

## Focused verification

- `tests/unit_tests/live_voice/test_task_semantics.py`: **79 passed**, including
  direct/negative delegation, malformed exact-quote retry, frozen replay and
  zero-effect rejection.
- Streaming provider send failure wakes a pending 30-second event reader within
  the test's one-second bound: **1 passed**.
- Media boundary compatibility plus production fail-fast: **2 passed**. The
  product case closes `MEDIA_CONSUMER_FAILED` with zero accepted audio frames;
  the default case retains its established cleanup/manual-fallback behavior.
- Product P1 mapping: **1 passed**. Only negotiated uplink failure becomes the
  recognition-stream reason; downlink and non-negotiated paths retain their
  specific adapter reason.
- Mounted capture recovery: **1 passed**. It reaches a second live capture with
  two media activations, zero unified submissions, zero Task mutations and zero
  presentation ACKs.
- Mounted formal bar removal: **1 passed**. The manual panel is absent. The
  right-side Registry view/store checks are **2 passed**, including exact
  session/project filtering, exact Task selection and stale-owner release.
- Full TypeScript `tsc --noEmit` and the production `npm run build` passed. The
  build completed in 1 minute 13 seconds. Existing duplicate locale `empty` keys,
  large chunks and a dynamic/static import warning remain outside this packet.
- The actual configured model resolved the original long Chinese delegation to
  direct `task.create` in 4.06 seconds in a no-Executor probe. This proves the
  repaired semantic output, not Task execution or end-to-end voice latency.
- The isolated owned runtime rebuilt and serves
  `/assets/index-DrU_nykG.js` at `http://127.0.0.1:6175`; served bytes match the
  isolated build. Before/after records match for eight Tasks, 24 commands and two
  project files. Configuration hashes are unchanged.
- Read-only browser inspection of existing session
  `web_1a06779d66f_3cc112920518` showed two completed Registry Tasks in the right
  “最近任务” panel with their original IDs, selected result and combined counts.
  The removed bottom manual panel was absent. No business request was submitted.

An earlier command placed Node's test-name filter after the package script. It
therefore ran the broad Integrated Web inventory unintentionally and reported
multiple failures in inherited mounted scenarios. This packet does not use that
run as pass credit and does not classify those failures as unrelated. Every
changed boundary above was rebuilt and rerun with correctly targeted commands,
but broad/cumulative regression remains open.

The complete normalized scoped diff received a cold self-review after focused
tests. No independent review tool or parallel agent was authorized, so this does
not receive independent Tier 2 review credit.

## Remaining boundary

The user can start a functional pre-rehearsal on port 6175. The first useful
check is analysis followed by the same explicit delegation and inspection of the
new right-side Registry entry. The known tens-of-seconds end-to-end latency is
still outside this repair. Physical generation/playback interruption, repeated
provider failure, complete A/B control, offline completion/ACK refresh, A2
immutability and both route journeys remain unproven on this exact candidate.
