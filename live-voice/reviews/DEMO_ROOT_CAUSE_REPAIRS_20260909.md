# Demo root-cause repairs — accepted execution boundary

The user accepted the repair order on 2026-09-09: diagnose and fix causes, then
verify the real conversation and Task journeys before Demo preparation. This
extends the completed passive-diagnostic batch. It does not resume the broad
feature-completeness backlog or authorize remote Git updates.

## Owned boundaries and order

1. Native input delivery and failure recovery (Tier 2): reproduce the observed
   800-frame input saturation and 14.607 s browser EOT-to-render interval; measure
   queue residence, transport send/lock/drain and loop scheduling before choosing
   a fix. Own Native Session/Engine, dedicated media and browser lifecycle tests.
   Preserve input order, exact generation ownership, bounded memory, no stale
   audio/history revival and zero replayed business effects. A physical network
   or Provider limitation must remain explicit if outside the product's control.
2. Executor worktree fidelity (Tier 3, file durability): preserve the admitted
   authorized source bytes through worktree seeding and result application.
   Own project_code_executor and its preservation/atomic-apply tests. Keep strict
   baselines, source-change detection and protected-file boundaries. Cover Git
   conversion/attributes, binary files, deletion and dirty snapshots. No global
   Git configuration change and no substitution of content-normalized hashes.
3. Business facts publication/binding (Tier 2): refresh changed Task facts outside
   the shared audio lock, publish before binding a successor response, preserve
   immutable in-flight bindings and revalidate present authority. Own Native
   Engine/Router and exact-context/race tests. No permission cache and no blind
   replay of mutating operations.
4. Prepared response and cleanup compatibility (Tier 2): use structural failure
   evidence to locate the rejected branch, then fix the supported Provider
   response/cleanup lifecycle without relaxing output admission.
5. Integrated verification: real ordinary speech, Task create/query/adjust/result
   notification, interruption and recovery; complete component timing and retain
   failed attempts. The existing physical calibration protocol remains required
   for last-phoneme-to-headphone claims. Unobservable one-way/network/Provider
   internals stay unknown, not inferred by subtracting unrelated clocks.
6. Closure: unify launcher local URLs, update the owning status/runbook and
   controlled deployment; prepare a small separate Demo business project after
   repairs. Work/projectless support, Task intent/result semantics item 4, model
   replacement and broad productization stay excluded.

## Verification and review

Use root TESTING.md's applicable P/N/B/S/T/C/R/I/F/K/X dimensions per module.
Reproduce each defect before changing behavior; use focused affected regressions,
cold scoped-diff review and independent Tier 2/3 boundary review. No full-suite
green or physical acceptance claim from unit counts. Test tools do not get Task
or production authority from being probes. Raw logs/audio/private configuration
remain in ignored local evidence. Maintain the user's pinned AgentCore wheel
choice in the isolated Demo and gpt-realtime-2.1 / 1.25 baseline for comparisons.

## Evidence routing

Initial human failures are preserved in private
`logs/demo-20260909/failure-web_1a08581b5cc/INVESTIGATION.md` and
`logs/demo-20260909/failure-web_1a085c08011/INVESTIGATION.md`.
New probes and exact commands/results belong in this record at module closure;
STATUS owns live progress and missing acceptance.

## Executor worktree fidelity — module implementation verified

The checkout's Git conversion and index stat cache both caused the mismatch.
Applying patches or merely restoring LF working bytes left checkout-derived
CRLF sizes in the index: `status --porcelain=v2` reported changes even when
`diff` was empty and `hash-object` matched the index blob. `update-index --refresh`
did not correct that distinction. The seed now copies the admitted index (with
split-index backing data), retires replaced checkout paths, restores actual
Git-visible source bytes, verifies both strict fingerprints, then stages only
the owned attempt baseline. Source bytes/index and global Git settings remain
unchanged. This retains the existing authorized result-application boundary.

Verification: the executor module passed 152 tests with 2 existing skips in
659.44 s. Independent review found a path ordering issue for directory/file
replacement and Windows case-only rename. Both were reproduced and fixed;
9 affected checks then passed in 40.68 s, including six attribute/split-index
combinations and existing result-relocation/autocrlf apply/restart checks. The
reviewer confirmed the finding resolved, with no additional material finding.
The expanded matrix also covers staged plus unstaged changes, intent-to-add,
untracked/deleted files, mixed line endings and binary bytes. Scoped diff check
passed. Private commands/results are in `logs/demo-20260909/repair-probes/`.
The later deployed real Agent Task created and applied its new file while all
37 original project files retained their hashes; see the results record below.

## Prepared-response compatibility — refined implementation boundary

Real gpt-realtime-2.1 probes reproduced the rejection in three independent
sessions: one response contains an assistant audio message with `phase=commentary`
and a separate function-call item. The existing preparation parser rejects that
phase and mixed composition, then treats unadmitted function cleanup as unsupported.
A fourth isolated Provider probe confirmed exact `conversation.item.delete` /
`conversation.item.deleted` for its own unexecuted function item. These probes use
synthetic context receipts and do not execute an Agent/Task or prove product E2E.

Refine this accepted compatibility repair to Tier 3 for Provider-context
preservation across the Session/Engine/preparation boundary: retain the supported
single-audio plus bounded function composition, preserve item identities and
terminal manifests, and release effects only through existing current-response
Runtime admission after promotion. Unplayed audio retains zero-played truncation;
unexecuted function items require exact deletion send and Provider ACK before a
successor. Early/foreign/failed/ambiguous receipts cannot certify cleanup, and
already admitted predecessor/history items must never be removed. No Tool/Task
replay, new business policy, extra output modality or browser wire change.
Required checks include positive mixed promotion, interruption before/after
terminal, exact/early/wrong/rejected delete ACK, source identity collision, zero
forbidden effects and subsequent-turn recovery, plus independent boundary review
and real product verification. Multiple audio outputs and unsupported metadata
remain closed. Private evidence: `prepared-shape-1..5.json` in the probe directory.

## Native repair implementation verification

Business publication now serializes a stable payload and response binding under
one send boundary. Receipt epochs prevent a pre-receipt in-flight context read
from certifying new facts; authoritative refresh is single-flight and reused by
the following request. Old response bindings remain immutable and delayed old
receipts cannot replace newer observer facts. Independent review's three ordering
findings were reproduced, corrected and confirmed resolved.

Prepared storage accepts the observed single commentary audio plus bounded
function-call composition; the fifth real Provider probe completed without
discard or unsupported cleanup. No Agent/Task ran in those isolated probes.
Promotion still requires current Runtime admission. Discard cleanup waits for
exact successful truncation/deletion sends and Provider ACKs. Current/committed
user input and published conversation facts/results are protected against ID
collision, including protection arriving after a cleanup target was observed.
Failed function validation retains identifiable cleanup targets; unknown
identities cannot certify empty cleanup. Independent review's two findings and
the late-protection ordering variant are resolved. The combined Native Engine,
bound business and preparation modules passed **366 tests in 52.59 s**.

The Windows resolver can return a stream socket with proto=0, causing CPython
3.11 to skip its implicit TCP_NODELAY. The Native connection now sets that option
on its own TCP socket. This corrects a local low-latency setting, but **does not
prove the only cause of the 14.607 s run**. Repeated 45 s real transport probes
also measured severe TCP loss/retransmission/timeouts on some connections;
both healthy and congested results exist. No production IP pin, packet dropping,
queue expansion or arbitrary buffering delay was introduced.

Native diagnostics now report actual TCP_NODELAY, sampled send lock/encoding/
socket/drain/write-buffer/loop observations and input queue residence. The exact
source event ID connects successful frame delivery to its send; a Gateway queue
ACK still does not establish Provider receipt. These cannot split unobserved
one-way network transit from Provider processing or establish physical sound.

Input saturation retains its server cause and uses the existing transport-failure
wire classification. Exact owner retirement happens before asynchronous cleanup;
input/event/delivery consumers recheck after waits and cannot start fresh effects
after closure. Pending delivery items retain queue accounting on cancellation or
closure. Already dispatched business operations still settle without replay.
The existing explicit Start successor path is retained, not a new automatic
retry policy. Independent media review confirmed the closure findings resolved.
The final media/Session/socket group passed 233 checks; two failures were a
pre-existing SimpleNamespace fixture missing the newly consulted `closed` field
and a loopback test timing drain from task creation rather than actual drain
entry. The fixture now represents the owner, and the test waits for actual drain
entry and a monotonic deadline. Both affected checks then passed in 7.88 s.
The seven closure/queue/receipt/batching checks passed in 5.90 s. Earlier test
attempts that stalled during diagnostic logging/capture were stopped and retained;
final affected commands used uncaptured output with coverage collection disabled.

The launcher generates 127.0.0.1 page/origin URLs and preserves its original BOM
and allowed-host compatibility. Parser and scoped diff checks passed. Runtime
restart and the real Task/audio recheck are now recorded in the
[deployed results](DEMO_ROOT_CAUSE_REPAIR_RESULTS_20260909.md). They have mixed
outcomes: successful Task application/notification and subsequent conversation,
but playback timeout and input saturation still occurred. Physical calibration
is missing. Local evidence retains failed probes and test runs.
