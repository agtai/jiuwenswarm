# Live Voice Latency Experiment Documentation System Design

> Date: 2026-08-22
>
> Status: approved in-chat design awaiting written review before execution.
>
> This document defines documentation organization only. It grants no new
> implementation, optimization, benchmark, product-path or Production credit.

## 1. Goal

Create one coherent English documentation route through every Live Voice
latency experiment performed on 2026-08-20 and 2026-08-21, including accepted,
rejected, screened-out, superseded, invalid and externally reported runs.

A reader must be able to answer without reconstructing Git history:

- what problem each experiment investigated and why;
- which branch, source commit, dependency and environment it used;
- how the input and workload were produced;
- which exact time boundaries were measured;
- whether a value is measured, derived, estimated or unknown;
- whether a reported total is physical end-to-end, Browser-clock code E2E,
  controlled round total or component-only latency;
- what passed or failed, including semantic integrity and forbidden effects;
- where the raw artifacts live, whether they still exist and whether hashes
  were verified;
- why the candidate was accepted, rejected, stopped or left open;
- which product validation gate remains.

## 2. Non-goals

This reorganization will not:

- rewrite frozen experiment evidence to make historical records look uniform;
- merge, rebase, cherry-pick or otherwise compose product branches;
- modify product code, runners, corpus audio or raw JSON/JSONL reports;
- convert deterministic or Provider-only timings into physical E2E claims;
- treat a faster failed workflow as an accepted optimization;
- copy credentials, private endpoints, device identifiers, audio or
  `current.env` into Git;
- update any remote ref.

## 3. Chosen architecture

The system uses a canonical catalog plus immutable owner evidence. This avoids
both extremes: one oversized optimization document and invasive rewriting of
exact-source historical records.

### 3.1 Repository catalog

Create:

`live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md`

This is the dated English entry point for all experiments. It owns:

- the experiment and validation-episode index;
- branch/source/run provenance;
- measurement-lane and total-latency classification;
- comparable headline numbers;
- per-experiment method, result, rationale and evidence routing;
- a branch map and artifact-retention summary.

It does not replace the detailed branch-bound result documents.

### 3.2 Optimization inventory

Retain:

`live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`

It remains the dated decision/headroom inventory. It will link to the catalog
instead of duplicating complete run histories. It owns current interpretation,
candidate ranking, headroom and execution dependencies, not raw run accounting.

### 3.3 Experiment record template

Create:

`live-voice/evidence/LATENCY_EXPERIMENT_RECORD_TEMPLATE.md`

Every future experiment record must use the same sections:

1. decision and credit boundary;
2. question, mechanism and rationale;
3. exact source/dependency/environment;
4. workload, corpus and input path;
5. method and changed variable;
6. measured boundaries and truth labels;
7. attempt and integrity accounting;
8. stage-by-stage and total results;
9. artifact binding and retention;
10. interpretation, limitations and next gate;
11. exact reproduction command;
12. review and verification.

Fields that do not apply must say `NOT APPLICABLE` with a reason. Missing
evidence must say `UNKNOWN` or `NOT RETAINED`; it must not be omitted.

### 3.4 Existing result documents

Existing detailed evidence remains frozen on its owning exact-source branch.
The new catalog points to branch-qualified paths when a file does not exist on
every branch. Later corrections are dated interpretation notes, not silent
rewrites of historical measurements.

### 3.5 Private artifact archive

Expand:

`/home/renan/openJiuwen-ai/live-voice-latency-runs/README.md`

This private, outside-Git file owns the complete artifact ledger. Each run
directory or raw report receives one of these states:

- `CREDITED`: source-bound result used by a recorded decision;
- `DIAGNOSTIC`: useful for investigation but not decision credit;
- `SUPERSEDED`: replaced by a later corrected population;
- `INVALID`: protocol, corpus, identity or integrity gate failed;
- `FAILED_WORKFLOW`: real failure retained in the denominator;
- `LOST`: a referenced artifact no longer exists;
- `PRESENT_UNVERIFIED`: file exists but source/hash/role has not been closed.

For credited artifacts, the ledger records path, run ID, source, role, size,
SHA-256 and owning repository evidence. It never prints private configuration.

## 4. Truth and latency taxonomy

Every number in the catalog uses one truth label:

| Label | Meaning |
|---|---|
| `MEASURED` | Direct timestamp subtraction inside one compatible clock domain |
| `DERIVED` | Deterministic calculation from measured or controlled values |
| `ESTIMATED` | Planning projection or counterfactual not directly exercised |
| `UNKNOWN` | Boundary was not observed and no numeric credit exists |
| `CONTROLLED` | Fixture delay intentionally supplied by the experiment |
| `REPORTED_EXTERNAL` | Reported by Hongxing without a locally bound raw artifact |

The catalog also assigns exactly one total-latency class:

| Total class | Required start/end boundary | Permitted wording |
|---|---|---|
| Physical full experience | Capture ready to confirmed playout ACK in the real Browser/device path | physical full-experience latency |
| Browser-clock code E2E | EOT to confirmed ACK on one Browser clock | Browser-clock code E2E |
| Controlled round total | Fixture speech-end/EOT to controlled terminal ACK | controlled round total, never physical E2E |
| Component total | Exact component start/end, such as model-complete to final-consumed | component latency |
| Projected perceived latency | Counterfactual or algebraic combination | projected/estimated, never measured E2E |

Headroom from different clock domains or overlapping waits is never added.

## 5. Cataloged experiment set

The initial catalog must cover these records:

| ID | Experiment or episode | Primary decision |
|---|---|---|
| `LVL-00` | Windows Chrome/WSL physical diagnostic A–G | preliminary diagnostic; not an accepted baseline |
| `LVL-01` | P2 one-notification-per-RPC A1 and bounded-pull A1/B/A2 | causal candidate accepted; product gate failed and remains open |
| `LVL-01C` | Hongxing deployed P2 validation | about 46% improvement externally reported; TTS authorization failed |
| `LVL-02` | Fixed-threshold VAD/EOT 1200/900/800/1200 | rejected because 900/800 split every 1000 ms pause case |
| `LVL-03` | TTS successor-capture ACK decoupling | accepted at first-audio causal component scope |
| `LVL-04` | Application-level TTS Provider connection reuse | rejected and reverted; no warm connection reused |
| `LVL-05` | Combined P2 plus TTS accepted-optimizations checkpoint | controlled checkpoint improved; not physical E2E and not P2 product acceptance |
| `LVL-06` | EOT/STT early-result waiter materiality screen | stopped; no material removable serial tail |
| `LVL-07` | Stable-sentence Agent-to-TTS materiality screen | stopped for tested workloads; no product wiring |
| `LVL-08` | Provider-native Semantic VAD | specified, not yet executed or credited |

Each section includes failed pilots and superseded attempts needed to explain
call count, debugging cost and the final credited population.

## 6. Branch organization

The same catalog, inventory and template content will be present on these seven
writable branches:

| Branch | Documentation role |
|---|---|
| `0812_live_voice_w3_renan` | central reading route and physical diagnostic origin |
| `latency/p2-bounded-pull-b` | P2 implementation and causal result owner |
| `latency/vad-eot-causal-benchmark` | fixed-threshold VAD result owner |
| `latency/tts-provider-connection-reuse` | rejected connection-reuse result owner |
| `latency_checkpoint_accepted_optimizations` | combined checkpoint and Semantic VAD specification owner |
| `latency/eot-stt-settlement-overlap` | EOT/STT result and TTS first-audio evidence carrier |
| `latency/stable-sentence-agent-tts` | stable-sentence result owner |

The content hashes of the three canonical files must match across all seven
branches after synchronization. Branch-specific evidence remains only on its
owner branch.

The following source references remain immutable and receive no documentation
commit:

- `latency_checkpoint_accepted_optimizations_a_reference`;
- detached A1/reference worktrees;
- historical candidate commits named inside evidence;
- remote-tracking refs.

Every writable branch receives its own local documentation commit because the
histories diverge. No product commit is copied or integrated by this work.

## 7. Authority synchronization

Update the documentation authorities without changing their roles:

- `STATUS.md`: summarize current latency credit and open gates in the existing
  Observability/latency capability row and tracked-latency paragraph. It must
  retain the product-truth packet as the higher product priority.
- `REFERENCE_INDEX.md`: add one historical/forensic route to the catalog.
- `runbooks/E2E_RUNBOOK.md`: add only a recording link from the existing
  latency sections to the new template/catalog; commands remain owned by the
  runbook and exact evidence.
- `README.md`: remain a short router; no new latency summary is added.

## 8. P2 correction that must remain explicit

The repository A1/B/A2 establishes bounded-pull component causality, but the
deployed product validation is failed, not accepted. The Gateway Media observer
handled only top-level single notifications and ignored the final notification
inside `notification_batch`, so TTS authorization was never established. The
observed result was `SPEECH_OPERATION_NOT_AUTHORIZED`, unsuccessful retry and
required page refresh.

The repair gate is:

1. validate the entire batch before any side effect;
2. reject an invalid batch atomically with zero partial authorization;
3. process every valid item in publish order;
4. let the final item establish TTS authorization;
5. rerun deployed off/on short, medium and long workloads with successful task,
   response and TTS/playout outcomes.

The externally reported approximately 46% improvement stays labeled
`REPORTED_EXTERNAL` until exact source, logs and artifacts are bound locally.

## 9. Completeness and verification

The reorganization is complete only when:

- every `LVL-*` entry has provenance, method, boundaries, result, integrity,
  decision, rationale, artifact state and next gate;
- every reported latency carries a truth label and total class;
- all credited repository artifacts that still exist have fresh SHA-256
  verification;
- absent or lost artifacts are explicitly identified;
- invalid, failed and superseded attempts remain visible;
- the catalog and inventory do not contradict their branch-bound evidence;
- changed local Markdown links resolve;
- the canonical file hashes match across all seven writable branches;
- `git diff --check` and documentation structure checks pass;
- each commit changes only the approved documentation scope;
- pre-existing dirty main-worktree files remain untouched;
- no remote ref is updated.

## 10. Resulting reading route

For a complete latency handoff:

1. read the catalog for experiment history and comparable facts;
2. read the optimization inventory for headroom and next decisions;
3. open only the exact branch-bound result needed for detailed tables;
4. consult the private artifact archive when rerunning or auditing raw data;
5. use the experiment template for every new run.

This route gives Hongxing a complete review surface while preserving the
distinction between measured facts, experimental interpretation and current
product authority.
