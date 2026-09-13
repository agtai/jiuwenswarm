# Live Voice develop rebaseline — 2026-09-12

## Authorized boundary

User requests local branch `hx/0912_livevoice`, rebased onto official
`https://github.com/openJiuwen-ai/jiuwenswarm` develop, all Live Voice changes
in one commit, semantic conflict resolution, then redeployment on this machine.

- Official develop: `8c7bfecdf0cc7607b07763fe687e08bf24f6ab83`.
- Original Live Voice: `537c5d2c9fc595fe38b2ccd1f93b8984fce594a3`.
- Common ancestor: `3f3cdbb7f45fdd29e7d03deafa5bca10e363434e`.
- Implement as a three-way cumulative squash onto the exact official parent;
  result must have exactly one added commit and preserve original source branch.

## Intended behavior and ownership

Retain upstream UI/runtime improvements and existing Live Voice Native/Cascade,
media ownership, response interruption/history fencing, real Agent/tool bridge,
project-scoped durable Tasks and notification ownership. No new product policy,
protocol, permission boundary or provider selection is introduced. This is Tier 3
integration compatibility work. Main owns integration and all final Git operations.
Frontend/backend helpers have isolated detached worktrees and may edit only their
assigned paths there; no commits, branch switching, pushes, or integration by workers.

Main owns remaining conflicts, dependency resolution, startup branch allowlist,
review integration, test selection, final single commit and private redeployment.

## Verification and exclusions

Inspect semantic conflict resolutions and affected automatic merges. Run focused
backend integration seams and affected frontend tests/build; independently review
resolved boundaries. Preserve existing baseline failures rather than silently
weakening tests. Require source clean/one-commit ancestry, exact runtime contract,
real TTS→STT probe, Realtime availability and real Agent read_file smoke after
redeployment. Physical microphone/speaker acceptance remains user-observed; no
new full-product or stable-latency claim. Preserve private configuration, sessions,
Task Store and demo files. No remote push, product feature expansion, automatic
broad SDK migration or system proxy change.

## Integration decisions

- Preserve official dependency lock and its pinned AgentCore: the upstream Code
  Agent/spec and tokenizer APIs require that baseline. Do not carry the old SDK
  hash-only lock change over the newer pinned upstream dependency graph.
- Preserve upstream skill-router restructuring and generic skill documents;
  old branch generic skill-trigger grooming is outside the Live Voice boundary.
- Keep the upstream removal of the obsolete README roadmap.
- Migrate Live Voice additions from the deleted top-level Web handler test into
  `tests/unit_tests/gateway/test_app_web_handlers.py`, preserving upstream tests.
- Launcher defaults to the requested new branch, retaining old explicit branch
  choices; no hardcoded new source hash in runtime behavior.
- Preserve upstream Code Agent spec/tokenizer construction, permission handling,
  interrupt quarantine and explicit configuration reload behavior. Remove the
  SDK factory's pending anomaly rail only when the generated spec's configured
  feature is disabled; caller-supplied specs retain authority.
- PersonalContext was a newly discovered integration isolation risk: upstream
  mounting must not grant dedicated file-only background tasks application
  memory access. Gate it before initialization through clean-support ownership,
  strictly detach any mounted rail, and retain that gate across Host refresh.
- Preserve upstream application-task/subagent UI, queued questions and session
  settings alongside Live Voice event identity, elapsed-time ownership and
  project-scoped recent tasks. Promotion retains persistence, plugins, MCP,
  Agent intent and Plan entry settings.
- Tests follow the moved handler module and updated factory signatures. Windows
  launcher introspection uses process-only ExecutionPolicy Bypass, like its
  existing execution test; no machine policy is changed.

## Independent review

Read-only independent review covered frontend session promotion, WebSocket event
gating, history and timeline integration, plus SDK/spec/anomaly handling,
background PersonalContext isolation and unary timeout forwarding. One P1
PersonalContext issue was fixed and independently re-reviewed; no remaining
actionable integration regression was identified in those reviewed boundaries.
Review is static evidence, separate from the checks and real runtime evidence.

## Results

Source integration checked on 2026-09-13. Runtime evidence is produced after the
single commit in `logs/live_voice_runtime_contract.json` and the machine-private
deployment report; no physical device acceptance is inferred from automated tests.

- Official dependency lock retained; SDK 0.1.17 installed. Owned Python AST and
  resolved-source undefined-name checks passed apart from two unchanged upstream
  annotation references. Frontend TypeScript and production build passed.
- Gateway/Agent/Code/context/PersonalContext/team/reviewer seams: 347 tests,
  initially 344 pass and three failures. Two test-fixture/API expectation updates
  were verified by all 23 Team tests passing; the third is the same unavailable
  GPT-5.6 SDK prerequisite reproduced on the original branch. Additional stream,
  privacy, media and launcher checks passed; 12 portable launcher tests passed.
- Frontend integrated suite: 704 pass, 12 fail, one skip. Every failure appears
  in the original run (700 pass, 16 fail, one skip). The unchanged Home pending
  button assertion also fails on both versions. Scoped session, timeline, queued
  question and runtime-ACK checks passed. These are existing limitations, not a
  claim of a green complete product suite.
- Full Live Voice Python comparison used the same 4,607 tests without coverage:
  original 4,517 pass / 85 fail / five skip; integrated 4,516 pass / 86 fail /
  five skip. Two new failure identities were identified: the pre-commit HEAD
  provenance assertion (must be rerun after committing), and the removed local
  observability wrapper. The latter now tests the SDK's canonical exports and
  zero tracer acquisition while disabled/uninitialized; all six owning tests
  pass and independent review found no issue. One original cancellation test
  passed in the integrated run. Remaining failure identities are shared with
  the original branch; broad product verification remains PARTIAL.
- Initial coverage-enabled broad runs were interrupted after profiling proved
  excessive coverage/report overhead; their partial output is not credited as
  a complete run. The completed JUnit files and exact comparison are retained
  in the machine-private `rebase-checks` directory.
- Scoped/cumulative diff review and `git diff --check` completed; old source
  branch is preserved. This local branch has no upstream and is not pushed.

### Applicable compatibility scenario coverage

| Dimensions | Owned verification |
|---|---|
| P / K | Frontend production build; session promotion, timeline and queued-question tests; Code spec/tokenizer, team runtime and gateway-handler tests. |
| N / B / I | Dedicated PersonalContext never constructs or mounts on Host refresh; detach failure retains ownership and blocks; malformed/contradictory tool results cannot become success or trusted permission decisions. |
| S / T / C | Session event fences, retained unary/reconnect/timeout tests; background prepare/cancel/replacement cleanup; Live Voice module lifecycle and concurrency regressions. |
| R / F | Durable task/store and executor fault/restart tests; optional context-processor and anomaly feature-off checks; exact launcher profile/branch/build-flag validation. |
| X | Required post-commit deployment contract, real Provider speech round trip and real Jiuwen Agent read_file smoke. Physical mic/speaker acceptance remains excluded from this automated rebaseline claim. |

The complete module run compares original and integrated source in isolated test
data/config directories. Existing failures remain visible rather than redefining
their assertions to claim a full-product pass. GPT-5.6's context-preserving SDK
guard fails on both original SDK 0.1.16 and official SDK 0.1.17; this optional
unavailable profile is not the configured DeepSeek + Realtime deployment.
