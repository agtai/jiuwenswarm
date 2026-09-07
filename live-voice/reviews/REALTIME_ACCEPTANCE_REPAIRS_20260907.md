# Realtime acceptance repairs

The user accepted the six-point repair design on 2026-09-07 with “开始”.
This supersedes the earlier analysis-only instruction and the narrow D-098
dirty-workspace admission policy for this scoped implementation. Main owns
integration from `af6a5bbb0cadd0e260e12961ee33f737db489d31`, independent review,
local point commits, controlled local deployment and unified user acceptance.
No remote update is authorized. Root [TESTING](../../TESTING.md) owns checks.

## Accepted scope and risk checkpoint

| Point | Intended behavior / owned surfaces | Risk, dependencies and acceptance |
|---|---|---|
| R1 output budget | Native configuration, Engine response creation, selected-Provider validation: default to model maximum (`inf`), consistently configurable. | Tier 2 configuration/protocol validation. All response paths, malformed limits and Cascade compatibility; normal long answer must finish. Model/provider selection unchanged. |
| R2 lifecycle | Native Engine, Gateway reader/delivery and transport diagnostics: generation terminal, delivery and actual playback are independent facts; reader/control never waits for media drain. | Tier 3 lifecycle seam. completed/incomplete/failed/cancelled, stalled predecessor, successor/STOP races, stale identities and bounded cleanup. Retain original exception classification without content or secrets. |
| R3 fault tail | Exact Native playback owner may finish only browser-accepted contiguous PCM frozen at transport failure. | Tier 3 failure playback/ACK extension. STOP/new turn revoke immediately; no late append, replay, new business effects or false complete history. Unknown EOF stays unknown; actual rendered prefix settles only its old owner. Depends on R2 and R6 audio seam. |
| R4 normal interruption UX | Expected prepared cancellation/replacement does not become request failure or an assistant failure bubble; genuine failures remain actionable in status UI. | Tier 2 Engine/Gateway/Web state. Normal interrupt and supersession, real fault, stale response, reconnect and generated/heard distinction. |
| R5 project snapshots and task intent | Accept authorized current project including tracked/untracked user edits; serialize project execution; seed immutable current snapshot and apply only task delta after conflict validation. Preserve A when deriving adjusted AA; project Task UI must converge to canonical completion. | Tier 3 Task admission/Direct durability, replacing blanket clean admission. Read and write dependencies, new-file collision, staged-state preservation, recovery/restart, exact scope and zero partial apply. Unknown dependency coverage uses conservative conflict scope, never unconditional overwrite. |
| R6 audio continuity | Measure ready-to-send delays and remove proven hot-path waits; build bounded startup/recovery reserve from received PCM, never elapsed time alone. Verified final cursor flushes short tails. | Tier 3 EOF/credit/playback seam plus Tier 2 scheduling. Keep transport acceptance distinct from rendered ACK, avoid 8-frame/250ms deadlock, never recreate started sources. Actual arrival traces, STOP during every phase, pause/resume, once-only PCM and truthful startup-delay measurements. No wholesale AudioWorklet migration. |

Applicable P/N/B/S/T/C/R/I/F/K/X dimensions are owned by each boundary above;
physical microphone/speaker evidence belongs to unified candidate acceptance.
Tests and real Provider/Agent/Executor seams do not claim user-perceived playback.
R5 conflict detection rejects the whole Task delta before writeback. An OS write
failure or process crash within writeback retains existing D2 UNKNOWN/manual,
zero automatic effect retry semantics; no new filesystem transaction is claimed.
The current conservative dependency domain covers the whole Git-visible project.
Preserve existing user acceptance Session, private configuration, Agent selection,
project files, Task state and credentials. Probes use disposable isolated fixtures.
No automatic commit/stash/reset/clean of user project files, new classifier,
Production deployment, remote ref update or arbitrary model tuning is included.

## Active parallel ownership (D-060 / D-062)

Main's integration worktree is `live-voice-acceptance-repair-20260907`, branch
`codex/realtime-acceptance-repairs-20260907`. Worker assignments are separate
worktrees based on the integration baseline; they may stage and commit only their
assigned changes on their own branch, one coherent point per commit, after scoped
checks. Workers never switch/integrate w3, rewrite shared history or push.

- Lifecycle worker: `codex/realtime-repair-lifecycle-20260907`, owns R2/R3
  Engine/Gateway/session and integrated Web route surfaces/tests; coordinate
  audio-adapter interfaces with R6 and budget fields with Main before touching.
- Project worker: `codex/realtime-repair-project-20260907`, owns R5 authenticated
  composition, project context/Executor/journal and matching tests. Main owns
  Native intent instructions and Web Task projection; communicate seam needs.
- Audio worker: `codex/realtime-repair-audio-20260907`, owns R6 browser audio I/O,
  audio port/transport EOF-consumer surfaces and matching tests. Main additionally
  delegated the measured Gateway control-reader hot path and its existing leaf
  tests after a separate implementation checkpoint; Main reviewed that return.
  Other backend source and media protocol changes require coordination first.
- Main owns R1/R4, intent/projection, shared decisions/STATUS, R3 product UI,
  independent reviews and cumulative verification. Shared files are integrated
  by Main; worker evidence goes to point-specific review files, not this packet.

Record discoveries that materially change these boundaries before implementation.
Use the user-authorized Astra max/ultra review for difficult lifecycle/authority
conflicts. Keep test failures and limitations visible; no point is complete merely
because its code exists. User acceptance remains open until the current-source
journey succeeds in the designated browser Session.

## Candidate integration result

All six repairs have coherent point changes and independent review. The final
Native/Gateway cumulative run passed 757 checks. The complete Web script reported
706 tests / 681 passed / 24 failed / 1 skipped; all 24 failure names reproduce on
the exact baseline. Twenty-three first errors are byte-identical; the remaining
state-dump error differs only by the new false local-tail field. No new failure
is excluded. The [candidate record](REALTIME_ACCEPTANCE_CANDIDATE_20260907.md)
owns the consolidated evidence and user acceptance instructions. Main integrates
six local commits into w3, preserving the original twelve, and deploys through
the existing controlled launcher. No remote update or physical-hearing claim is
included. The six worker source returns are closed; user acceptance remains open.

Actual Native startup after that deployment exposed an older pending-start
reservation gap plus an insufficient initial browser attachment budget. The
[startup checkpoint and repair](REALTIME_NATIVE_STARTUP_REPAIR_20260907.md)
owns this necessary additional lifecycle repair and its verification. Main owns
the browser readiness change, integration and deployment; the lifecycle worker
owns only registration, matching tests and its evidence file. Independent Astra
ultra review passed both final boundaries. Preserve the six existing commits and
add one coherent startup repair commit; no remote update or expansion into new
business/protocol policy is authorized by this supplementary repair.
