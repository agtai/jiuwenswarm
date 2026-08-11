# D101 W2 new-environment manual handoff — 2026-08-11

## Disposition

The user will perform the remaining assisted/manual W2 validation in a new environment and a new Codex Session. The source implementation boundary remains `ebd95ba1e`; [D100](D100_P3_TERMINAL_REPLAY_VALIDATION_READY_2026-08-11.md) records the passing unsigned automatic validation-ready run on the original machine. That runtime is diagnostic only and creates no portable machine readiness, evidence or Gate credit.

The original machine created fresh-attempt scaffold label `20260811-112651-21f376eb7a` from clean documentation commit `21f376eb7`, but the visible external-root acknowledgement was not completed and no rehearsal policy signature was created. The signing window is closed. Because an external-root directory was partially created, this label and all of its candidate, staging, browser-profile, database, key, rehearsal/formal evidence and external-root paths are abandoned and must never be resumed, signed or imported.

## Git handoff

The new environment must fetch the exact pushed `agtai/hx/0803_live_voice` branch, verify its final 40-character HEAD dynamically and require a clean checkout with zero upstream divergence before trusting this record. Git carries source and documentation only. It does not carry provider credentials, private configuration, persistent Session/project registration, selected model/device, browser permission/profile, runtime database, policy/key/signature or evidence roots.

The implementation commits that close the latest observed blockers are:

- `1cc0e9cb2`: preserve the complete Agent-only provider binding across repeated dotenv loads;
- `bf6873596`: accept only request-bound closed product errors while rejecting transport failures;
- `a0453ff19`: reconcile authoritative P3 completed/failed origin truth and exact outcome/reason pairing; and
- `ebd95ba1e`: atomically replay terminal progress and fence predecessor/successor late updates.

## New-environment execution boundary

Before any signature, the new machine must repeat the unsigned [validation-ready lane](runbooks/E2E_RUNBOOK.md#validation-ready-before-signing) because machine-private readiness does not transfer with Git. At minimum it must prove:

1. clean exact source and disposable fixture roots, private-config schema/reference, persistent Session, registered project, selected Agent model and real Speech provider;
2. two consecutive AgentServer epochs retain the same complete Agent configuration;
3. one isolated Chrome page at the exact `/chat/<session_id>` route with exactly one CDP page target and the expected project/model/device;
4. deterministic-WAV P1, short real-Agent P2, forced read-only Terminal Tool, authoritative P3 completed and failed UI, reconnect/late-response fencing and graceful `p2.close`; and
5. zero active owner, nonterminal task/attempt, pending outbox, lease, port or disposable-project mutation afterward.

Only after those checks pass may the new environment create one entirely new candidate label and candidate-specific profile/database/policy/key/evidence roots. Run the generated rehearsal-policy signing script in a visible PowerShell window, independently compare/type the complete external-root fingerprint and sign the rehearsal policy once.

Then complete Pair 1, Pair 2, Pair 3 and A4 continuously. Physical `Jabra EVOLVE 30 II` capture, complete audible playout and the user's receipt remain human-owned. Nonfatal TTS/capture/operator findings are recorded and the remaining experiments continue; identity/authority/credential/policy/evidence-owner mismatch, wrong or dirty candidate, wrong Session/project/model, multiple pages, required-route loss or residual mutation/task/lease requires immediate stop. Formal policy remains forbidden until all four rehearsal experiments pass.

After successful rehearsal derivation, issue the new formal policy, run the four same-shape formal experiments, close/sign the 31 non-runtime artifacts, assemble the 38-slot manifest and run `w2_gate_cli evaluate`. Until the CLI returns PASS, the product remains `SOURCE-INTEGRATED / GATE-PARTIAL` and the Replacement Ledger remains `0/100`.
