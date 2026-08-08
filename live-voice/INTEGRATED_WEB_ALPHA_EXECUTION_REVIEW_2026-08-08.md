# Integrated Web Alpha bounded execution review

> Review date: 2026-08-08
> Base: `5ac969af8244094973ae1b7f1ced9d761199b921`
> Tested implementation: `950ae8f19810ccf3876bcbcba3a014996b38a2ce`
> Acceptance authority: [Integrated Web Alpha acceptance](validation/ALPHA_ACCEPTANCE.md)
> Mutable state: [STATUS.md](STATUS.md)

This is an immutable engineering record for the bounded second-stage Alpha batch. It is not runtime acceptance evidence and does not redefine current priority, score or next action. Those mutable facts remain in `STATUS.md`.

## Outcome

The reviewed source/conformance batch is `PASS`; the Integrated Web Alpha product Gate remains `PARTIAL`.

The batch closes deterministic and formal source boundaries for exact barge-in fencing, bounded performance reporting, cascade conformance, streaming Speech conformance, D90 voice-origin binding, six-operation P3 Web control, attempt-root Agent execution attribution and D0 byte preservation. It does not supply a physical Chrome/device journey, a real streaming Speech Provider journey, a deployed HTTPS/WSS origin, complete external X-OBS/retention/SLO evidence or a signed immutable Alpha Gate result.

## Integrated commits

| Commit | Bounded scope |
|---|---|
| `05187943` | exact local-first barge-in and late-effect fencing |
| `9ee149e6` | bounded Alpha benchmark summary |
| `49430bca` | deterministic cascade conformance fake |
| `42124669` | streaming Speech conformance |
| `f525109c` | exact D90 voice interaction origin |
| `abc4d5b9` | response-cancel retention through teardown |
| `a367c236` | six formal P3 structured controls |
| `73a21d05` | D0 worktree baseline-byte preservation |
| `11ff0f48` | attempt-root P3 Agent lifecycle and execution attribution |
| `950ae8f1` | P3 Web query/mutation/progress authority closure |

The local Alpha branch has no upstream and was not pushed. The original W2 feature worktree and branch remained at `5ac969af`; its implementation parent `2fdf849a`, Gate state and Replacement Ledger were not changed by this batch.

## P3 authority and executor closure

The stock Web surface exposes `task.create`, `task.get`, `task.list`, `task.status`, `task.cancel` and `task.events` through exact authenticated Task Core bindings. Retained truth is monotonic across reconnect, exact event identity and sequence conflicts fail closed, task and attempt lifecycles remain separate, terminal truth cannot be reopened, mutation results survive transport ambiguity until explicit local adoption, and confirmation expiry cannot replay a completed business mutation. Rejected paths assert zero forbidden Store, carrier, confirmation, Agent, Tool and Authority effects.

The direct D0 executor creates the real JiuwenSwarm Agent only at the exact attempt root. Setup, post-terminal and cleanup mutations fail closed; exact terminal content is sealed before cleanup; the Authority mirror preserves bytes; attribution mismatch attempts exact rollback; and exact Agent bindings are retired. Replay reauthorizes current scope/session/command/target facts instead of borrowing the original grant.

## Real P3 probe

A disposable, machine-local Authority fixture was used outside the repository and outside the immutable evidence system. The real task followed `create -> accepted -> terminal`, completed successfully, invoked the real configured DeepSeek model and real `write_file` Tool, wrote an exact 41-byte LF-terminated file, and retired the attempt Agent. The Authority file SHA-256 was `660BA9F5A5F2D42C8C27C38FE0E09963487B69672F5332412A82F6D73A5C774F`; fixture HEAD did not change.

This proves a bounded real P3 Agent/Tool executor path only. The probe script, runtime logs, provider configuration and fixture were intentionally outside Git; the fixture retained one untracked output file. A Windows console encoding error occurred while logging the Chinese goal, after which task/model/tool execution still completed. No credential or private configuration value is recorded here. This probe is not Chrome, Speech, joint-route or signed Gate evidence.

## Verification

| Area | Result |
|---|---|
| P3 frontend integrated route | `174/174 PASS`; strict TypeScript and bundles PASS; only pre-existing duplicate `empty` i18n-key warnings |
| P3 backend focused matrix | `130 passed, 2 skipped`; skips are Windows symlink-capability cases |
| P3 independent final delta | retained-result immutability `1/1 PASS`; strict TypeScript PASS |
| D0 executor baseline | `58 passed, 2 skipped` in its independent review |
| D90 origin regression | `435 passed, 2 skipped` |
| Streaming Speech conformance | focused `50/50`, related `154/154`; independent `50/50` plus `91/91` |
| Cascade conformance | focused `50/50`, relevant `271/271`; independent `94/94` |
| Alpha benchmark | `13/13 PASS` |
| Exact barge-in/fencing | independent frontend `56/56`, strict TypeScript, benchmark `13/13` and Ruff PASS |
| Cumulative Live Voice backend | `1230 passed, 2 skipped` across `tests/unit_tests/live_voice` and `tests/integration/live_voice` in 140.25 seconds |
| Python static/diff checks | Ruff PASS for the six changed Python files; `git diff --check` PASS |

Scoped Python runs used the existing working repository virtual environment, disabled repository-wide `addopts`, enabled automatic asyncio mode and ignored the third-party `pysbd` Python 3.12 `SyntaxWarning`. Test selection and assertions were unchanged. The ignored warning is an environment limitation, not a product test failure.

## Review closure

1. Implementation self-review checked exact identity, terminality, reconnect, replay, confirmation, lifecycle mutation and zero-forbidden-effect boundaries and fixed all findings before the final runs.
2. A cold complete-diff review compared the 12-file P3 batch with the original request, repository rules, existing behavior and actual tests. Its findings were fixed and the complete frontend/backend matrices were rerun.
3. A separate read-only Sol agent performed an independent equivalent review. Literal `/review` was not available, so this is recorded as the D-053 substitute rather than claiming that command ran. The final result was `PASS` with no remaining P0-P3 actionable finding; it independently obtained frontend `174/174`, backend `130 passed, 2 skipped`, strict TypeScript, Ruff and `git diff --check` PASS, then separately reviewed the final nested-result freeze and obtained `1/1 PASS`.

## Configuration and exclusions

- The original `C:\Users\admin\.jiuwenswarm\config\config.yaml` was not modified. Verification used an isolated machine-local data directory with TLS verification enabled.
- No remote ref, external account, billing setting, public deployment or provider credential was changed.
- No real streaming STT/TTS provider path, physical microphone/speaker, real Chrome lifecycle/fault matrix, non-localhost secure origin, remote observability exporter, retention policy, operational SLO or signed immutable Alpha evidence set was exercised.
- The real P3 probe and deterministic Speech/cascade fakes cannot be combined to claim a real cumulative P1/P2/P3alpha journey.
- Production identity, exact-once cross-process semantics, D1/D2, wider platforms and production authorization remain outside this Alpha batch.

## Gate judgement

| Boundary | Judgement |
|---|---|
| Bounded source/conformance batch | `PASS` |
| P3 formal Web/Agent/Tool executor batch | `PASS` within the tested local boundary |
| Real streaming Speech | `BLOCKED` on selected provider/configuration and real route evidence |
| Desktop Chrome/device and HTTPS/WSS deployment | `BLOCKED` on controlled environment and deployment authority |
| X-OBS retention/SLO and signed evidence | `PARTIAL / OPEN` |
| Integrated Web Alpha overall | `PARTIAL`; no Gate closure or replacement credit |
