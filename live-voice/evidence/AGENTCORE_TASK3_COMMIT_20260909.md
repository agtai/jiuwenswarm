# Task 3 — Native execution cutover and duplicate-code retirement

Task 2 is `20915742` and already contains the common-service prerequisites and
their paired SDK source patches. This commit activates Native foreground and
detached Work execution through that service, removes the replaced private
composition and retires unused facade admission/validation. Standard P2 keeps
its actual runtime owner and product submission route. Speech admission,
presentation ACK, authorized project effects and durable Work/Task product facts
remain in JiuwenSwarm.

The demonstrated generic gaps are implemented in the original AgentCore owners:
exact pending input/Goal/Workflow continuation, output lifetime and provenance,
final model admission, and physical task settlement. The installed paired SDK is
`ffeb1abcc5cc0bc72b5c813a3316d4334d39e15f`; its twelve-patch reconstructed tree is
`6f3826983ea8c15eb182ec7761705fd5058c1235`. Task 2 carries these prerequisites so
each numbered Host commit remains independently executable. Source-only
installation and actual import verification remain mandatory.

## Scoped verification and review

The [Native Work record](AGENTCORE_NATIVE_WORK_SHARED_20260909.md),
[Native foreground record](AGENTCORE_NATIVE_FOREGROUND_SHARED_20260909.md) and
[SDK settlement record](AGENTCORE_TASK_SETTLEMENT_20260909.md) contain commands,
source limits and repaired review findings. Coverage includes actual shared
facade/service ownership, exact cancellation, delayed or failed cleanup reported
as unknown, durable retry/restart without replaying execution, stale/conflicting
identity with zero effects, capacity-before-effect, ordinary Text isolation,
heard-history authority and the retained P2 submission path.

Relevant completed selections include 27 Work/formal-output, 105 shared-formal,
8 original speech regressions, 34 foreground/cancel/late-close/selected-result
cases, and 4 affected formal-child/Gateway-loss/cleanup cases. The subsequent
legacy deletion passed 11 product-submit checks before removal, 78 affected
checks after removal, and 27 generation/speculation/actual Registry seam checks.
The shared Harness validator passed its 24 affected cases. These selections
overlap and are not added together as a unique test count. Unchanged long cases
were not rerun solely for mechanical deletion. Scoped Ruff and whitespace checks
passed. Main and an independent reviewer read the complete owned changes and
closed the reported findings; the last deletion received limited independent
review with no new finding.

## Code reduction and remaining acceptance

Against Task 1 `66833d5c`, the whole backend `jiuwenswarm/server/live_voice`
directory has **757 added / 775 removed production lines, net -18**, including
new common-capability adapters. The conversation runtime alone is net -421;
the retained Harness is net -117. The last legacy-admission removal contributed
another net -282 within those totals. Local hashes and scoped deletion evidence
are in `.codex_tmp/legacy-admission-retirement/`.

This is a whole-Live-Voice production-directory reduction, not a claim that
adding shared AgentCore/Host capabilities reduced the entire repository. Existing
project Task storage/effect policy has not been wholesale moved into the SDK.

All three numbered implementation boundaries are now present in local commits.
Final applicable broad automated/build/static checks, cumulative integration
review and clean-candidate deployment are complete, with baseline/environment
failures and scoped repairs recorded in [final verification](AGENTCORE_FINAL_VERIFICATION_20260909.md).
The final bounded real continuation passed strict artifact/public Task identity,
terminal playback acknowledgement and independent settled Work. Earlier transport
failures and the corrected speech/format mismatch remain explicit in that record;
continuous connection reliability and the full physical product matrix are not
claimed as passed. Controlled lower Model/producer tests do not prove audible or physical
Provider behavior, and the historical broader physical-device backlog is not
silently reactivated.

Final review also removed the obsolete manually named `live_voice_native_work`
disconnect exemption. Actual shared sessions use exact retention records; the
formal-child protection remains. The affected channel test and actual retained
formal-child Gateway-loss test passed together (2 passed, 22.36 s).
