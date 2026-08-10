# D97 W2 no-evidence smoke review — 2026-08-10

## Scope and acceptance boundary

This record closes the automated, unsigned checkpoint smoke requested after the D96 source batch. It used machine-private Agent and Speech configuration, a disposable registered Git project, the stock Web UI in desktop Google Chrome, Gateway, AgentServer and the real product P1/P2/P3alpha routes. No rehearsal policy was signed, the evidence owner remained disabled, no JSONL evidence artifact was produced and no Replacement Ledger credit is claimed.

The run followed the accepted checkpoint strategy: retain completed checkpoints, record non-blocking failures, repair the isolated cause and rerun only the affected checkpoint. It is not presented as one uninterrupted signed rehearsal or as final physical-device acceptance.

## Automated journey result

| Checkpoint | Result | Exact boundary |
|---|---|---|
| P1 prepared-WAV Speech | PASS | The repository 48 kHz mono PCM16 WAV completed real configured STT and TTS; the synthesized output was validated as 48 kHz mono PCM16. This does not prove microphone capture, audible playout or barge-in timing. |
| P2 Agent/Tool/UI | PASS | Chrome submitted committed text to the real Agent; the UI received `AGENT_UI_TOOL_OK .gitignore`, presentation acknowledgement and terminal/history truth. Hard refresh advanced the activation generation and did not duplicate the Agent operation. |
| P3 UI lifecycle | PASS | The real mounted UI performed create, cancel A, eligibility inspection, retry B and disconnect/reconnect recovery with exact task/attempt ownership. B reached terminal while disconnected; a later cancel was stably rejected as `TASK_ALREADY_TERMINAL`. |
| Progress/UI ACK | PASS AFTER REPAIR | The first real task exposed an overlong server `evidence_id`. After the bounded-ID repair, a fresh task emitted 85-character `task-progress-return:<sha256>` identities and active plus terminal ACKs returned acknowledged with the exact server-owned task and attempt. |
| Disposable closure | PASS | The final task and attempt were terminal, its dispatch outbox was delivered and unclaimed, the selected Git project remained at its original clean HEAD, no named evidence artifact/configuration was present, Chrome/services were closed and the temporary runtime configuration was restored. |

The final read-only project task ended `failed/NO_EFFECTIVE_TARGET_CHANGE` because its instruction prohibited file mutation. That business outcome is truthful and independent of the progress transport result; its terminal progress ACK succeeded. Cancellation had already been exercised on attempt A.

## Runtime findings and repairs

### Bounded progress authority identity

The production progress source previously concatenated full task, correlation, generation and event fields into `evidence_id`. Valid authority-owned values could exceed the registry's 256-character contract, so every UI ACK failed before acknowledgement.

Implementation commit `87e0188968f9022056aa789fbfa6fe3eb78a295f` hashes the same typed canonical identity and emits the fixed prefix plus SHA-256. The resulting ID is stable, event-sensitive and 85 ASCII characters. It does not move attempt authority into the client or weaken exact delivery/task/attempt checks.

### Windows Speech preflight stdout

The real Speech preflight completed provider work but could fail while printing a Chinese transcript through a strict Windows cp1252 stdout. The same commit emits ASCII-safe JSON escapes. JSON consumers recover the exact Unicode transcript, and no Provider key or raw audio is added to output.

## Verification and review

- Progress source unit suite: `39/39` PASS.
- Rehearsal toolkit suite: `46/46` PASS.
- Registry progress/ACK affected selection: `14/14` PASS.
- Ruff, Python compilation and `git diff --check`: PASS.
- Real Chrome/service affected rerun: bounded active and terminal progress ACKs acknowledged with exact task/attempt; project and outbox closure checks PASS.
- D-053 self-review: PASS.
- Cold complete-diff review: identified the need for a behavioral cp1252 regression and replaced the initial source-string assertion.
- Independent read-only review: one matching P2 test-gap finding; after the behavioral fake-Provider/prepared-WAV/strict-cp1252 test, final result PASS with no remaining P0/P1/P2 finding.

## Remaining work

The next acceptance stage is a fresh reviewed descendant and new signed rehearsal roots. The user should intervene once, at that final stage, for real microphone capture, audible full TTS, barge-in timing and P3 UI/receipt observation. Signed evidence, the formal 38-slot artifact set and `w2_gate_cli evaluate` remain open; the Replacement Ledger therefore stays `0/100`.
