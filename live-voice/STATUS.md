# Live Voice current status

> Updated: 2026-08-03
> This is the only mutable current-state source. Other documents link here instead of repeating branch status, current milestone, or next work.

## Git and release identity

- Development branch: `hx/0803_live_voice`.
- Shared remote branch: `agtai/hx/0803_live_voice`.
- V0 immutable Released / Frozen baseline: `ee2896a4afb186e693c720476b6de10797e66f72`.
- V0 release-evidence commit on this branch: `a42668f8`.
- Original Post-V0 foundation tip: `4a3e11f1`; integrated by merge commit `ac988b85` after the V0 evidence commit.
- D-039 ASR-fidelity direction: `e539dd23`.
- The cleaned history intentionally excludes the unrelated commits identified during the 2026-08-03 audit. Runtime equivalence and ancestry are verified before push; do not reintroduce old merge/noise commits merely to reproduce the former log.

## Current milestone

### V0: RELEASED / FROZEN

V0 is a controlled Web vertical slice, not the production release. It has verified:

- real microphone input through Browser Speech;
- committed final transcript sent once to the real JiuwenSwarm Agent;
- real tool execution and truthful tool result;
- final answer rendered and spoken once by browser TTS;
- automatic return to listening;
- the documented thinking/tool supplement behavior and speaking-time stop-then-new-turn behavior;
- Gate 0–6, including normal turns, staged interruption, 21m58s soak, degradation, three consecutive showcase runs, and equivalent clean-environment recovery.

The immutable evidence is [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md). Post-V0 code is not part of that V0 capability claim.

### Post-V0 foundation: INTEGRATED / PARTIAL

The original foundation commits are preserved through `4a3e11f1`. The branch contains backend and Web foundations for task identity, idempotent request handling, execution target/provenance, schedule-backed task operations, frontend task client/adapter/bridge, task projection/card behavior, streaming speech support, feature flags, and focused tests.

These foundations are not full P3 and are not production closure. In particular, a foundation type, adapter, or card does not prove durable task lifecycle, cross-process exactly-once behavior, production authentication, or cancellation fencing.

## Next development slice

The next accepted slice is D-031: a narrow poll-backed, non-blocking task monitor.

Before semantic implementation, perform the D-032 pre-review and record in this file:

1. precise module definition and non-goals;
2. existing and planned test inventory, with why every test exists;
3. P/N/B/S/T/C/R/I/F/K/X scenario matrix;
4. exact backend response/error/terminal semantics;
5. same-page reconnect behavior and explicit full-page-refresh non-support;
6. A→B successor behavior, preservation of A's terminal card, and zero invented outcomes.

Only after that checkpoint is reviewed and separately approved for commit/push should D-031 code begin. Do not expand it into TaskEvent push/replay, general multi-task NLU, complete P3, D1/D2 durability, or production security.

## Accepted boundaries that affect upcoming work

- D-032: every module closes with pre/post review and complete positive, negative, boundary, state, timing, cancellation, recovery, idempotency, fallback, capability, and cross-layer coverage as applicable.
- D-033/D-034: current Web owner/project scope is single-user request consistency, not authentication. D-031 promises same-page reconnect only. Required identity/status/target/provenance fields fail closed; missing optional progress/error displays `unknown`; deleted/missing/error outcomes are not success.
- D-039: Browser Speech remains a fallback. Dedicated ASR and any future Native Audio Engine must implement one provider-neutral Speech Port with auditable hypothesis/provenance and critical-token safety. This does not displace D-031 and does not mean a provider has been selected.

## Known gaps

- Browser Speech first-pass fidelity remains weak for Chinese homophones, negation, English technical terms, paths, SHAs, dates, and numbers.
- V0 supplement success is not a production response/generation fence; side-effecting tool cancellation, hard process resource limits, and cross-process cancellation remain open.
- No production streaming-media transport, VAD/AEC/duplex device matrix, provider SLO, privacy retention system, or multi-language closure exists yet.
- Task projection is page-memory state; full-page reload recovery and durable command journal are not implemented.
- Credentials, provider configuration, project records, browser permissions/devices, runtime data, and network state remain machine-private.

## Verification ledger

- V0 exact-SHA acceptance: Gate 0–6 PASS; see immutable evidence.
- Runtime tested SHA for the cleaned integration: `ac988b85e8a21eb4f378086bab58dac6a4d55d82` (only documentation was uncommitted during this verification).
- D-037 guard: `test_circuit_breaker_repeated_failure.py` **20/20 PASS**; the exact adapter regression case modified by `ee2896a4` **1/1 PASS**.
- Post-V0 backend: Live Voice contract/Web handler **122/122 PASS**; schedule request/task service **104/104 PASS**.
- Post-V0 frontend: 12 focused Live Voice scripts (core, turn/recognition lifecycle, TTS ownership/text, message gate, supplement quarantine, streaming speech, task client/adapter/bridge, chat streaming) all PASS; TypeScript + Vite production build PASS.
- Adjacent non-Live-Voice observation: the complete `test_agentserver_modes.py` run produced **74 PASS / 1 FAIL** because pytest promoted unclosed-socket `ResourceWarning` cleanup into an exception group in `test_deep_adapter_routes_team_simplify_answer_by_evolution_meta`; that case passes when isolated. It is retained as a flaky cleanup gap and is not represented as a clean full-file pass.
- Documentation integrity: 99 Markdown links checked with zero empty/broken targets; no tracked `docs/zh/live-voice/` duplicate; `git diff --check` PASS. Final ancestry/exclusion checks run after the documentation commit and before push.

## Resume checklist

1. Verify clean/expected worktree, `HEAD`, branch, upstream, and ahead/behind.
2. Read [README.md](README.md), this file, and only the task-routed documents.
3. Confirm the next slice is still D-031 unless a newer accepted decision changes it.
4. Re-establish private runtime conditions only when the task needs real E2E.
5. Follow the root `AGENTS.md` approval gate separately for every commit and push.