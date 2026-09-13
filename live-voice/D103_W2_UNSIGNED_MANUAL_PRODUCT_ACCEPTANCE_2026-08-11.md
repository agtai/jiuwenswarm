# D103 W2 unsigned manual product acceptance

> Date: 2026-08-11
> Status: P1/P2 product-level manual acceptance passed; formal Gate and Replacement Ledger credit remain open
> Tested source: `d26aa17797331f053bb584ec017f3ffa6ce90156`
> Boundary: this was an evidence-disabled manual product check. It is not a signed rehearsal/formal artifact and grants no Gate credit.
> Supersession: D-071 later retired the signed Gate/credit requirement. This record now counts as the completed W2 P1/P2 human product-acceptance portion; its original no-credit statement remains only as historical context.

## Result

The user completed the remaining physical-input and audible P1/P2 product check on the exact persistent Session using the real Agent, Speech Adapter and Terminal Tool route. The environment used a working physical input device selected by the user, but it was not the earlier `Jabra EVOLVE 30 II` device and is not claimed as that environment's hardware evidence.

After refreshing and starting again:

1. The initial P1 turn recognized the user's speech correctly.
2. The formal P2 input requested a read-only Terminal execution of `git branch --show-current`.
3. The product returned an acknowledged P2 response reporting `main`, and the user heard the complete response read aloud.
4. After playout, P1 automatically returned to successor `capturing`; the user stopped that empty successor manually.
5. The empty successor then surfaced `SPEECH_PROVIDER_EMPTY_TRANSCRIPT`. It did not create a second Agent/Tool submission and does not invalidate the already completed P1/P2 turn.

## Corroboration and cleanup

- The stock route panel retained `P2 ... acknowledged` and the response `main`.
- The AgentServer log showed one real `bash` Tool call with the exact command `git branch --show-current`, working directory bound to the disposable fixture, exit code `0` and stdout `main`.
- The disposable fixture remained clean on branch `main`.
- Gateway, AgentServer, isolated Chrome and Vite stopped cooperatively. Ports `5173`, `9223`, `18092`, `19000` and `19001` all had zero listeners afterward.
- The source worktree remained clean.

## Explicit limitations

- Evidence collection was disabled. No trust policy, evidence owner, signature, formal artifact or Gate credit was created.
- A blank Chrome new-tab page was present during part of the interaction, so this run makes no formal exactly-one-page claim.
- The physical input device was not the frozen Jabra baseline.
- This run did not repeat the P3, fault-class, restart or 38-slot formal matrix. Those remain governed by current [STATUS](STATUS.md), [D102](D102_W2_SIGNED_REHEARSAL_FAULT_PROBE_REPAIR_2026-08-11.md) and the W2 acceptance/runbook.

The product statement is **W2 P1/P2 manual product acceptance passed on this environment**. Under D-071, the remaining W2 decision depends only on the applicable automated checks and the unfinished human product steps listed in current [STATUS](STATUS.md); no signed Gate evaluation is required.
