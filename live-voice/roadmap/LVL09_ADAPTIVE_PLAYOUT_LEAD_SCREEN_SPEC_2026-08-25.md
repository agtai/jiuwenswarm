# LVL-09 adaptive playout lead setup specification

Status: setup only; no Browser/Provider/product credit.

## Scope
Repair the private manual driver so an A1=1000/B=250/A2=1000 Browser screen can be run later with terminal/profile/round-bound snapshots and complete process-tree cleanup. The production default remains 1000 ms.

## Contract
Each manifest declares one source commit, three ordered arms, one frozen profile/case per arm, expected `round_index`, and `VITE_LIVE_VOICE_PLAYOUT_STARTUP_LEAD_MS` (`unset`, `250`, `unset`). A snapshot is advance-eligible only when the newly exported JSONL row exactly matches the active arm profile/case/round and `terminal_outcome == "completed"`. Failed/cancelled/mismatched rows are retained, beeped as non-creditable, and cannot advance.

The driver starts every service in its own session/process group and terminates the complete group SIGINT → bounded wait → SIGTERM → SIGKILL. Snapshot names derive from authoritative row identity, not operator stage.

## Measurements and gates
`schedule→start_estimate` is a measured wait with estimated endpoint; underrun/rebuffer and terminal outcome are measured. Audible first word is unknown. A physical screen is blocked until driver tests pass and the manual-driver Gate is closed. Later physical B requires zero underrun/rebuffer, visible completed rows, clean A1/A2 drift and retained full denominators.

## Exclusions
No Chrome, Provider, product source/default/flag change, Browser acceptance, p50/p95 claim, remote update or Task authority change.
