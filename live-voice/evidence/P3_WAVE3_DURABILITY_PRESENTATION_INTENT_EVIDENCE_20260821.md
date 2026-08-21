# P3 Wave-3 durability, presentation and intent evidence — 2026-08-21

> Evidence status: **VALIDATED — SCOPED WAVE-3 PACKAGE.** This sanitized record
> binds the final private run and integrated automation to source
> `17e929650203525dd3cb41d1878908ffd2c1978b`. Raw evidence, configuration,
> prompts, Task identifiers and absolute private paths remain outside Git.

## 1. Source and evidence boundary

- Branch: `hx/0812_live_voice_w3`.
- Activation baseline: `cfff0c43aa599c009ab9517397566fec5c1bdd95`.
- Exact integrated source:
  `17e929650203525dd3cb41d1878908ffd2c1978b`.
- Private root basename:
  `p3-wave3-499a61c2c3f14ab8bd0f478906edc02f`.
- Raw artifact schema: `live-voice.p3-wave2-real-evidence.v1`. The existing
  schema is intentionally reused only for its bounded production-factory,
  Agent, file-Tool, admission/control/reopen/cleanup contract; it does not
  relabel those facts as P3-5B browser audio or P3-6 operation coverage.
- The successful private root remains retained under its restricted ACL. No
  failed root was produced in this Wave-3 run and no recursive deletion ran.

## 2. Final integrated automation

The authoritative broad Python invocation used disabled third-party plugin
autoload plus the repository asyncio plugin/mode. It completed with
`2721 passed, 5 skipped, 1 failed`. The one failure is the known D-087 semantic
conflict in `test_retry_segment_projects_from_authority_owned_nonzero_baseline`:
the test expects completed retry, while the accepted product rule admits only a
cancelled predecessor.

After the final Task-mutation authority fixes, the affected Core/composition
set completed `477 passed`. The post-fix S8 unit/CLI run completed
`67 passed in 94.00s`.

Formal Web completed `414/415`; the only failure is the pre-existing P1/P2
mounted Exit/immediate-re-enable presentation-ACK timing case. Strict contracts
completed `45/45` for Live Voice v2 and `14/14` for product composition. The
production frontend build passed after transforming 4,643 modules. Scoped Ruff,
format, compile and diff checks passed.

## 3. Product-path evidence by package

| Package | Exact positive seam | Negative/restart/race boundary |
| --- | --- | --- |
| P3-4 | SQLite v6 Store, public Core linked recovery, Direct dispatch/apply/reconcile and real OS ownership lock | forged/copy/profile/context/schema drift, cancel/recovery and initializer races, migration/apply failpoints, `UNKNOWN` manual settlement |
| P3-5B | real Store/Core unread-to-ACK, connected React DOM adoption and canonical Runtime AUDIO ACK | new Session/process/Attempt replay, >256 events, delayed ACK, ACK/close, playout/publish/Core/cleanup failure and text fallback |
| P3-6 | actual Registry, raw classifier, Bridge, authenticated Store reader/composition and Persistent Core | origin/clarification/confirmation replay, context/model/task-set/profile/head/result/lineage drift, mutation CAS, response loss and unsupported controls |

The P3-6 corpus contains 68 cases and 14 natural/voice/structured parity groups.
The classifier tests remove expected outputs before classification and reject
fixture lookup. Product composition exposes five queries and six mutations;
three operations remain explicitly unsupported/conflict because no production
primitive exists. The evidence does not claim that one parameterized Registry
test individually traverses all 14 operations.

## 4. ACL-private real run

The producer was executed on the exact integrated source using the existing
private configuration copied into a fresh ACL-protected root. The source root
and private root were disjoint. The producer's Windows process bound, timeout,
configuration-root binding, output-size and cleanup checks remained active.

The emitted artifact and its ACL were independently revalidated after the
producer exited. The closed aggregate was:

| Fact | Result |
| --- | --- |
| Validator result | `ok=true` |
| Observations | 22 |
| Tool calls / results | 11 / 11 |
| Exact paired file Tools | 11 |
| Write/edit pairs | 5 |
| Observer failures / dropped | 0 / 0 |
| Unknown / sequence gaps / unpaired | 0 / 0 / 0 |

All producer checks were true: production factory and registration, persisted
profile and requirements, two-project concurrency, A2 busy queue with zero
pre-release effect, same-Attempt dequeue, adjustment, exact A1/B1 cancellation,
Store reopen, cleanup, unchanged source, real Agent and real Tool.

## 5. Claim disposition

| Claim | Disposition |
| --- | --- |
| P3-4 scoped source/automation/review | **PASS** |
| P3-5B scoped source/automation/review | **PASS** |
| P3-6 scoped source/automation/review | **PASS** |
| Current-source production factory plus real Agent/Tool regression | **PASS** |
| Physical browser/audio-device perception | **NOT CLAIMED** |
| All 14 operations through one Registry E2E | **NOT CLAIMED** |
| Complete P3 / controlled product / feature complete / Production | **NOT CLAIMED** |
| Remote branch update | **NOT RUN — approval required** |

The scoped implementation verdict is recorded in the
[Wave-3 implementation review](../reviews/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_IMPLEMENTATION_REVIEW_2026-08-21.md).
