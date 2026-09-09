# Native foreground uses the shared configured Agent service

Current closure: the prepared cutover is activated by the Task 3 commit above
Task 2 `546ca7e7`. Installed SDK is now `ffeb1abc`. Earlier checkpoint source IDs
and uncommitted labels below describe the historical scoped checks. Final
candidate acceptance remains pending; see [Task 3 evidence](AGENTCORE_TASK3_COMMIT_20260909.md).

This records the prepared Task 3 working-tree cutover. Task 2 carries the common
service prerequisites and this checkpoint; the separate Task 3 commit activates
the replacement and legacy-facade deletion.

Task 3 checkpoint, still uncommitted above Main `66833d5c` and not deployed.
Installed SDK is `1aac45ec`; this retirement consumes the already reviewed shared
formal execution path. It adds no further SDK primitive.

## Change and responsibility

Native foreground delegates now call `SessionExecutionService.start_formal`,
`wait_formal` and exact-entry `cancel_formal`. The configured public Web Agent
facade owns execution through its formal child session. The conversation runtime
retains only speech admission, replay, deadlines, presentation/history and the
actual producer task needed for pending teardown. The former Harness/Bridge
reservation, cancellation-envelope and completion-projection sequence is removed
from this path. Standard P2 keeps its existing profile and behavior.

The changed conversation runtime has 56 added and 216 removed lines relative to
Task 1 after ignoring line-ending differences: net reduction 160. This is a
module figure, not the final whole-Live-Voice reduction; new shared-capability
adapters and remaining retirement are still in progress.

## Verification and review

Independent worker tested the real common service and facade with controlled
lower Agent output. The first affected selection passed 31 cases; the corrected
late-close assertion passed separately, followed by two real selected-result
cases: 34 affected cases passed. The default 26-second execution budget was
tested once. Ordinary caller cancellation leaves the admitted producer intact;
foreground interruption/timeout targets its exact entry. Slow cleanup retains
the original task and pin, close reports pending, and a later settled close
releases them without late output/history effects. Concurrent ordinary Text
output uses the same facade with independent lifetime. Selected Task results
remain tool-less and use the actual formal answer contract.

Review found an invalid `ResponseRef.to_dict()` call; Main replaced it with its
three explicit identity fields before running those positive cases. Main read
the scoped production diff and the independent test changes. Scoped Ruff, AST
and whitespace checks passed.

One pre-existing Registry scenario still expects `background.query` but its
fixture selects `dialogue`: `test_native_available_result_uses_toolless_agent_delegate`.
It is in the recorded September 8 baseline failure list. A separate probe loaded
only HEAD `66833d5c`'s original `_run_native_delegate` and reproduced the same
route failure after executing that method once. The original oracle remains
unchanged; direct selected-result tests cover this cutover without that unrelated
semantic-route failure.

Local detailed artifacts are retained under
`.codex_tmp/native-foreground-shared-worker/`: `affected.html`, `route-close.html`,
`legacy-route.html`, `selected-result.html` and the three scoped test diffs.
These controlled seams do not replace final browser/Provider/Agent acceptance.

## Whole retirement boundary review follow-up

The independent Task 3 cold review found the public facade's transport cleanup
preserved the public session but omitted the actual `lv-formal-*` Deep child.
A real service/facade/Deep-root/AgentManager test reproduced the unwanted child
abort. `retained_sessions` now includes the exact formal child while that
retained physical task remains live; unrelated Text still cancels. This is a
Task 2 shared-service prerequisite of the Task 3 cutover. Four affected formal,
Goal, cleanup and Gateway-loss cases passed in 31.77s. The output producer and
SDK abort calls are controlled; the Host routing and cleanup methods are real.
The remaining cold review found no new blocking issue in output, cancellation,
model/history isolation or the retained Standard P2 path.

The obsolete facade admission entrypoints and their sole-source attachment
branches have now been retired under the recorded Task 3 extension. Product P2
already uses `submit_committed_turn`; Native still invokes the underlying
ConversationRuntime through its existing runtime owner. All production and
dynamic-call searches found no consumer of the four removed facade entrypoints.
The tests now use product submission and retain capacity-before-effect, exact
identity, concurrency/replay, cancellation, output and history assertions.
Eleven product-submit checks passed before deletion; 78 affected checks passed
after deletion, then 27 generation/speculation and actual Registry seam checks
passed. The unchanged 26-second Native case was not repeated for this deletion.
Scoped Ruff passed. The extension removes another 261 CR and 21 Harness lines;
the final whole backend Live Voice directory is net -28 against Task 1 at this
checkpoint. Main read the complete scoped production deletion; independent
limited review passed with no new findings. Detailed local diffs, file hashes and line
counts are under `.codex_tmp/legacy-admission-retirement/`.

## Shared output validation retirement

Main also removed the retained P2 Harness's duplicate identity, no-tool buffer,
control-markup and final/error validation. It now uses the same
`FormalAgentOutput` as the shared service. The legacy streaming path explicitly
keeps its existing unbounded final policy; the service's retained result remains
bounded at 131072 bytes. Reservations, terminal events and exact cleanup stay
with the original Harness. Its current total diff above Task 1 is 11 additions
and 107 deletions, net -96 (including the earlier shared-markup extraction).

The affected Harness/shared-service selection passed 24 cases in 12.74 s:
plain output, split DSML and invalid Unicode zero leakage, result bounds,
invalid identity, empty/duplicate/error finals, original final-size compatibility,
exact cancel and cleanup. Scoped Ruff and whitespace checks passed. Main reviewed
the deletion against the common validator; independent cumulative review remains
part of candidate closure. This removes duplicate validation rather than moving
media or presentation policy into AgentCore.
