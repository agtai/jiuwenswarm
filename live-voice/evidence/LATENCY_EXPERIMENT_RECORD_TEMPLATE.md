# Live Voice latency experiment record template

> Copy this file for a new experiment and replace every bracketed instruction.
> A field that does not apply must say `NOT APPLICABLE` with a reason. A fact
> that was not observed must say `UNKNOWN`. A missing raw artifact must say
> `NOT RETAINED` or `LOST`; do not omit it.

## 1. Decision and credit boundary

| Field | Required value |
|---|---|
| Experiment ID | `[stable LVL identifier]` |
| Date | `[YYYY-MM-DD]` |
| Decision | `[ACCEPT / REJECT / STOP / INCONCLUSIVE / DIAGNOSTIC ONLY]` |
| Credit scope | `[deterministic component / real Provider / real Agent / deployed product / physical Browser]` |
| Optimization enabled | `[exact flag and value, or NOT APPLICABLE]` |
| Remaining gate | `[next exact validation requirement]` |

State the decision in one paragraph. A faster failed workflow is a regression
and cannot receive optimization credit.

## 2. Question, mechanism and rationale

### 2.1 Question

`[One falsifiable latency/materiality question.]`

### 2.2 Suspected mechanism

`[Exact serialization, wait, buffering, transport or authority mechanism.]`

### 2.3 Why this approach

`[Why this is the smallest safe experiment and why alternatives were not used.]`

## 3. Exact source, dependency and environment

| Field | Required value |
|---|---|
| JiuwenSwarm branch | `[branch]` |
| JiuwenSwarm source commit | `[40-character commit]` |
| Source state before run | `[clean / dirty; dirty runs cannot receive formal credit]` |
| Reference commit(s) | `[A1/A2 commit or NOT APPLICABLE]` |
| Candidate commit | `[B commit or NOT APPLICABLE]` |
| Agent-Core branch/commit | `[exact value or NOT APPLICABLE]` |
| OS/kernel/architecture | `[sanitized exact values]` |
| Runtime versions | `[Python/Node/npm and relevant dependency versions]` |
| Provider/adapter | `[exact provider class or CONTROLLED fixture]` |
| Model/voice/config | `[exact labels without credentials]` |
| Network policy | `[real uncontrolled / controlled / offline]` |
| Warm/cold policy | `[exact definition]` |

Never record credentials, bearer tokens, private endpoints, device identifiers
or private project contents.

## 4. Workload, corpus and input path

| Field | Required value |
|---|---|
| Workload IDs | `[stable case names]` |
| Public prompt/transcript | `[exact text when safe]` |
| Corpus ID/version | `[identifier or NOT APPLICABLE]` |
| Corpus/file SHA-256 | `[digest or NOT APPLICABLE]` |
| Input path | `[physical microphone / controlled Browser WAV / direct PCM / transcript injection / deterministic event fixture]` |
| Browser/device involved | `[yes with declared class / no]` |
| Attempt count | `[per case and population]` |
| Fixed execution order | `[A1 → B → A2 or exact alternative]` |

State what this input path does not prove. Direct injection never grants
physical capture/device credit.

## 5. Method and changed variable

### 5.1 Lane

`[Gate A deterministic causal / Gate B real Agent or Provider / Gate C deployed Live Voice]`

### 5.2 One changed variable

`[Exact configuration or source behavior changed between A and B.]`

### 5.3 Execution method

`[Exact owner/adapter/runner invoked and ordered steps.]`

### 5.4 Controls

`[Inputs, delays, source, Provider/model, state template and environment held constant.]`

## 6. Measurement contract

### 6.1 Truth labels

Use only:

- `MEASURED`: direct compatible-clock observation;
- `DERIVED`: deterministic calculation from measured/controlled facts;
- `CONTROLLED`: fixture-injected delay;
- `ESTIMATED`: projection or counterfactual;
- `UNKNOWN`: unobserved boundary;
- `REPORTED_EXTERNAL`: external report without local artifact binding.

### 6.2 Start/end and total class

| Field | Required value |
|---|---|
| Start boundary | `[exact event]` |
| End boundary | `[exact event]` |
| Clock domain | `[exact monotonic clock owner]` |
| Total class | `[physical full experience / Browser-clock code E2E / controlled round total / component total / projected perceived latency]` |
| Included waits | `[enumerated stages]` |
| Excluded waits | `[enumerated stages]` |

Never call a controlled, Provider-only or component total physical E2E.

### 6.3 Stage catalog

| Stage | Start event | End event | Owner/block | Truth label |
|---|---|---|---|---|
| `[stage ID]` | `[event]` | `[event]` | `[P1/P2/P3/Agent/Browser/Provider]` | `[label]` |

## 7. Attempt and integrity accounting

| Population | Attempted | Completed | Failed | Invalid | Unknown | Semantic success | Cleanup complete |
|---|---:|---:|---:|---:|---:|---:|---:|
| `[A1/B/A2]` | `[n]` | `[n]` | `[n]` | `[n]` | `[n]` | `[n]` | `[n]` |

Record every failure reason. Do not remove semantic mismatch, fallback,
degradation, timeout or failed product output from the denominator.

### 7.1 Forbidden effects

| Effect | Observed count | Required count |
|---|---:|---:|
| Duplicate/stale Agent submission | `[n]` | 0 |
| Unauthorized Tool call | `[n]` | 0 |
| Unauthorized Task mutation | `[n]` | 0 |
| Unauthorized history mutation | `[n]` | 0 |
| Unauthorized TTS/audio effect | `[n]` | 0 |
| Partial authority from invalid input/batch | `[n]` | 0 |
| Other experiment-specific effect | `[n]` | `[declared bound]` |

## 8. Results

### 8.1 Stage-by-stage latency

| Workload | Stage | A1 p50/p95 | B p50/p95 | A2 p50/p95 | B−A1 | B−A2 | Truth label | Outcome |
|---|---|---:|---:|---:|---:|---:|---|---|
| `[case]` | `[stage]` | `[ms]` | `[ms]` | `[ms]` | `[ms/%]` | `[ms/%]` | `[label]` | `[improved/unchanged/regressed/invalid]` |

### 8.2 Total latency

| Workload | Total class | A1 p50/p95 | B p50/p95 | A2 p50/p95 | Absolute delta | Relative delta | Truth label |
|---|---|---:|---:|---:|---:|---:|---|
| `[case]` | `[class]` | `[ms or UNKNOWN]` | `[ms or UNKNOWN]` | `[ms or UNKNOWN]` | `[value]` | `[value]` | `[label]` |

### 8.3 Wait displacement and regressions

State whether the intended wait disappeared, overlapped or moved downstream.
List changes in completion rate, semantic correctness, TTS/playout, Task truth,
recovery, resource use and any other affected output.

## 9. Artifact binding and retention

Raw artifacts stay outside Git under:

```text
/home/renan/openJiuwen-ai/live-voice-latency-runs/
```

Never use `/tmp` for a credited final report.

| Population/artifact | Run ID | Private relative path | Size | SHA-256 | Mode | State |
|---|---|---|---:|---|---|---|
| `[A1/B/A2/report]` | `[run ID]` | `[path below archive root]` | `[bytes]` | `[digest]` | `0600` | `[CREDITED/DIAGNOSTIC/SUPERSEDED/INVALID/FAILED_WORKFLOW/LOST/PRESENT_UNVERIFIED]` |

If the artifact is missing, explain when/why it was lost and which sanitized
record remains authoritative. Never silently substitute a diagnostic run for a
lost credited population.

## 10. Interpretation, limitations and next gate

### 10.1 Decision rationale

`[Tie the outcome directly to predeclared materiality and integrity gates.]`

### 10.2 What this proves

`[Exact source-bound claim.]`

### 10.3 What this does not prove

`[Browser, Provider, Agent, product, physical, Production and other exclusions.]`

### 10.4 Next gate

`[Exact follow-up or reason the lane remains closed.]`

## 11. Reproduction

```bash
[Exact credential-free command with absolute output under the durable archive]
```

List required private configuration by variable name only. State expected
attempt counts, exit result and output files.

## 12. Review and verification

| Check | Exact command or review | Result |
|---|---|---|
| Source/dirty preflight | `[command]` | `[result]` |
| Runner/component tests | `[command]` | `[result]` |
| Positive/integrity population | `[command]` | `[result]` |
| Negative/forbidden-effects population | `[command]` | `[result]` |
| Lint/build/diff check | `[command]` | `[result]` |
| Independent review | `[tier, source and verdict]` | `[result]` |

End with the exact branch/commit that owns the result and the exact artifact
state. Documentation-only commits never upgrade experiment or product credit.
