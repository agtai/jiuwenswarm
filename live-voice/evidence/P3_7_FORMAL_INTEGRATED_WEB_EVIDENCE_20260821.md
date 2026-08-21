# P3-7 formal Integrated Web evidence — 2026-08-21

> Evidence status: **VALIDATED — SCOPED P3-7 PACKAGE.** This record binds the
> accepted automation and independent review to integrated source
> `98e063f084c140cb6eb0042de32f3695c89c7279`. It contains no credentials,
> prompts, Task content, raw audio or private runtime paths.

## 1. Source boundary

- Branch: `hx/0812_live_voice_w3`.
- Activation baseline:
  `29589734a0bb51a697bf7d594e3b1bb552ddcd34`.
- Packet-record baseline:
  `965fc827fb409b97d791f64febc7d32f0aaf71d3`.
- A-lane commit:
  `4e3d4bf591c21c8ac843032e5fc5d919f09786b9`.
- Integrated source:
  `98e063f084c140cb6eb0042de32f3695c89c7279`.
- Reviewed diff: 13 files, 3,159 insertions and 14 deletions.

## 2. Automated product-path evidence

The backend Gate ran the complete authenticated P3 composition and AgentServer
route files in the repository environment. It completed `184 passed` with one
Authlib deprecation warning. Those tests include the actual AgentServer to
Registry query surface, the existing authenticated authority reader, SQLite
Persistent Core, structured confirmation continuation, current-principal
operation filtering, cross-scope rejection and zero Store/Executor effects.

The formal owner completed `14/14`. Its scenarios cover multi-page collection
truth, exact fresh detail reads, two Tasks, hint-only selection, result and
lineage, all accepted operation shapes, stable unsupported controls, current
Attempt progress, prior Attempt history, concurrent refresh, wrong Session and
feature-off zero transport.

The mounted affected set completed `10/10`. It exercises natural Task handoff,
structured failure, foreign origin, response loss, terminal progress/ACK,
historical restoration, the complete formal owner and feature-off. Its
reconnect scenario deliberately holds the result read and proves activation and
ACK do not advance; after release, activation occurs after result. A second
reconnect rejects result and proves the fail-closed snapshot with no additional
activation or ACK.

The full Formal Integrated Web invocation compiled strict formal TypeScript,
bundled the Panel and ran 440 tests. Result: `439 passed, 1 failed`. The failure
is the independently reproducible baseline P1/TTS Exit/immediate-re-enable late
presentation-ACK timeout, not a P3 Task surface. The explicit profile tests
completed `2/2`; the Live Voice production build passed with 4,644 transformed
modules. Existing i18n duplicate-key, dynamic-import/chunk and bundle-size
warnings were recorded but are not P3-7 regressions.

## 3. Authority and zero-effect observations

| Observation | Result |
| --- | --- |
| Two authenticated Tasks list/select/detail/result | PASS |
| Fresh list → status → events → result before validated route | PASS |
| Current-principal supported-operation projection | PASS |
| Structured continuation and existing Core mutation | PASS |
| Durable P3-5B progress/DOM ACK reuse | PASS |
| Reconnect pending result: additional activation / ACK | `0 / 0` |
| Reconnect rejected result: additional activation / ACK | `0 / 0` |
| Unsupported controls: transport / Agent / Tool / Task / audio / history | all `0` |
| Feature-off formal Task transport / mutation | `0 / 0` |
| Foreign or forged authority: Store / Executor effects | `0 / 0` |

## 4. Review history

The cold independent Tier-3 review was allowed to fail the lane. Its first pass
returned six Important findings, all repaired with focused regression evidence.
The second pass returned one Important reconnect ordering finding. Main took the
single-writer lease, added a connection-local route invalidation and formal
Session revalidation fence, and strengthened success/failure timing evidence.
The final review independently reran the 14 owner and 10 mounted scenarios,
strict TypeScript, Panel bundling and diff checks. Verdict:
`PASS — Critical 0 / Important 0 / Minor 0`.

## 5. Claim disposition

| Claim | Disposition |
| --- | --- |
| P3-7 formal multi-Task Web source/automation/review | **PASS** |
| P3-7 frozen interface available to P3-8B | **PASS** |
| Existing P3-5B durable presentation authority preserved | **PASS** |
| Physical browser microphone/TTS perception | **NOT CLAIMED** |
| Complete P3 / feature complete / controlled product | **NOT CLAIMED** |
| P1/P2 Exit/re-enable or notification-latency repair | **NOT INCLUDED** |
| P3-8B composition/retirement | **NOT YET CLAIMED** |
| Remote branch update | **NOT RUN — approval required** |

The scoped verdict and interface freeze are recorded in the
[P3-7 implementation review](../reviews/P3_7_FORMAL_INTEGRATED_WEB_IMPLEMENTATION_REVIEW_2026-08-21.md).
