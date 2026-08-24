# LVL-10L long-form authoritative-final chunked-TTS result

> Date: 2026-08-24
>
> **Disposition: STOP long-duration testing with repeatable directional
> evidence; no formal materiality, Browser or product credit.** The clean v2
> pilot passed 12/12 attempts and showed a 6.93–7.75 second derived completion
> gain on the 2,150-character output. The approved five-round formal was then
> stopped on Hongxing's direction before the runner wrote any attempt rows.

## 1. Question and honest boundary

LVL-10L followed the inconclusive LVL-10 screen with a new, prospectively
completion-primary question: after one complete immutable authoritative final,
does bounded two- or four-request TTS reduce source-side synthesis completion
for long outputs enough to justify request amplification?

The runner measures Provider/source first PCM, 250 ms reserve, synthesis
completion, generated audio duration, exact request/error counts and derived
paired deltas. It does **not** measure Browser scheduling, audible output,
playout continuity, prosody, barge-in, receipt ACK, Agent execution or end-to-
end latency. The current product route still sends one full final in one SSE
request.

## 2. Source, dependencies and branches

| Role | Branch/worktree | Relevant source |
|---|---|---|
| Integration, specification, implementation and result owner | `latency/hx-optimizations` at `live-voice-w3` | LVL-10L commits `6bf8d5245..bcbf6a423` |
| Historical LVL-10 runner worker | `latency/lvl10-provider-screen` at `lvl10-provider-screen` | local tip `dfee94142`; integrated predecessor source later stabilized at `9cbb462dc` |
| Historical LVL-10 corpus/oracle worker | `latency/lvl10-validation` at `lvl10-validation` | local tip `65f90df23`; integrated through the LVL-10 stack |
| Historical clean LVL-10 Provider run | detached `lvl10-run-e493799f7` | run source `9cbb462dc` |

LVL-10L implementation used one writer lease in the integration worktree and
read-only reviewers in tmux panes. It did not create another feature branch.
No branch was pushed as part of this packet.

| Field | Value |
|---|---|
| Initial LVL-10L real-pilot source | `76f4413de604b768321a094fd0b56cd8c3a1e917` |
| Revision-2 pilot/formal source | `bcbf6a423130ebb6409135f41ad3a2831bf0407b` |
| Installed Agent-Core source | `94e10cb6102c36fe78a64547957c0def97299273` from venv `direct_url.json` |
| Provider/model/voice | configured OpenAI streaming Speech / `gpt-4o-mini-tts-2025-12-15` / `marin` |
| Environment | WSL2; real Provider; no Browser; same private `.env` configuration |
| Product source changes | none; validation runner, fixtures, tests and documentation only |

## 3. Implementation and review history

| Commit | Purpose |
|---|---|
| `6bf8d5245` | prospectively specify completion-primary LVL-10L |
| `a8c196c60` | implementation plan |
| `ac9b1741f` | initial independent runner/corpus/tests |
| `f8535fa3a` | close pilot, capacity, provenance and report gates |
| `1358e67d7` | retain complete failure and decision evidence |
| `76f4413de` | render complete human-readable decision evidence |
| `28a65211c` | revise corpus/formal contract after the v1 pilot exposed the 8 MiB boundary |
| `1a94415ca` | add immutable v2 600/1200/2100 corpus and five-round reducer |
| `bcbf6a423` | label five-round p90/p95 as descriptive nearest-rank, non-gating |

The final affected verification on revision 2 was **210/210 passed**: 42
LVL-10L tests, 34 historical LVL-10 tests and 134 Provider/conformance tests;
Ruff and `git diff --check` passed. Independent reviews closed synthesis-
identity capacity, pilot/formal separation, fence reasons, failure retention,
decision-input serialization, corpus/cap sizing and percentile labelling with
zero open Critical/Important findings.

## 4. Corpus and route design

| Corpus | Fixtures | Hash | State |
|---|---|---|---|
| v1 | 734 / 1,422 / 2,938 characters (`long_600/1200/2400`) | `6d7225fecb44b584a08af7431f54ae1a4230773e2cdb2f5d1bc8b23ddc5a78cc` | immutable pilot corpus; largest fixture invalid for this comparison because the one-request control reaches the 8 MiB boundary |
| v2 | 734 / 1,422 / 2,150 characters (`long_600/1200/2100`) | `60327f98371f91908a1838f160929b72b0e783debb222200b68be9329a30e7a3` | clean pilot corpus; first 4/8/12 units of the same frozen text |

Every attempt used A1/B2/B4/A2 bracketing. A1/A2 submit one full final; B2
submits two manifest groups; B4 submits four. Candidates open at most two
requests concurrently and release PCM in order. Stable stream IDs plus round
generations keep the conformance identity ledger below 64 without changing its
cap. Retries are zero.

## 5. Real-Provider episodes

### 5.1 V1 pilot 1 — external quota rejection

Run `lvl10l-provider-pilot-20260824T144516Z-76f4413de` retained 12 attempts but
opened only 18/24 requests, with 18 Provider errors and zero measured timing
rows. A separate sanitized authenticated diagnostic reached OpenAI and returned
HTTP 429 with `insufficient_quota / credit_balance_exhausted`. This isolated
the root cause from DNS, TLS, WSL, proxy, corpus, runner and Agent-Core.

Decision: `REJECTED` by the runner's integrity/reliability gate; optimization
materiality remained `UNKNOWN`.

### 5.2 V1 pilot 2 — 8 MiB boundary discovery

After credit restoration, run
`lvl10l-provider-pilot-v2-20260824T145218Z-76f4413de` opened 24/24 requests and
completed 11/12 attempts. The only failure was A2 `long_2400`: it produced
8,380,799 output samples before the next Provider delta would cross the
adapter's 8 MiB wire-audio safety limit. A1 completed only about 80 KiB below
that same boundary. B2/B4 spread audio over multiple requests, so the v1
fixture would structurally favour them.

| V1 `long_2400` completion | A1 | B2 | B4 | A2 |
|---|---:|---:|---:|---:|
| Measured | 26,037 ms | 14,257 ms | 14,383 ms | failed at safety boundary |

Decision: `REJECTED`; values are diagnostic only. The project did not raise
the safety cap or credit the apparent candidate advantage. This pilot caused
the prospective v2 corpus revision.

### 5.3 V2 clean pilot — PASS and directional materiality

Run `lvl10l-v2-provider-pilot-20260824T152447Z-bcbf6a423` completed 12/12
attempts, opened exactly 24/24 requests, recorded zero Provider errors and
passed every integrity/pilot gate.

| Workload / metric | A1 | B2 | B4 | A2 |
|---|---:|---:|---:|---:|
| 600 completion | 8,516 ms | 4,498 ms | 5,715 ms | 6,760 ms |
| 1200 completion | 12,522 ms | 8,221 ms | 15,581 ms | 22,652 ms |
| 2100 completion | 18,852 ms | 11,878 ms | 11,029 ms | 18,755 ms |
| 2100 first PCM | 965 ms | 782 ms | 782 ms | 783 ms |
| 2100 reserve | 1,456 ms | 1,357 ms | 1,388 ms | 1,462 ms |
| 2100 generated audio | 127.45 s | 131.95 s | 131.00 s | 125.55 s |

Derived against each candidate's time-interpolated A1/A2 bracket:

| Candidate / workload | Completion gain | Positive pilot comparison |
|---|---:|---:|
| B2 / 1200 | **7,793 ms / 48.66%** | 1/1 |
| B4 / 1200 | 2,725 ms / 14.89% | 1/1 |
| B2 / 2100 | **6,930 ms / 36.85%** | 1/1 |
| B4 / 2100 | **7,751 ms / 41.27%** | 1/1 |

These values are `MEASURED` at the component boundaries and `DERIVED` for
paired gains. One pilot round does not provide a formal p50/p95 population.
B4 was about 849 ms faster than B2 at 2100 but doubled B2's request count; the
pilot cannot select an arm. B2 was materially better than B4 at 1200 and is
the simpler directional trade-off.

### 5.4 V2 formal — intentionally aborted, zero timing credit

The user approved a reduced five-round formal (60 attempts / 120 requests),
run ID `lvl10l-v2-provider-formal-20260824T152809Z-bcbf6a423`. During the run,
Hongxing requested that long-duration testing stop. The process ended before
the runner wrote `attempts.jsonl` or `report.*`; only the immutable `run.json`
and copied `manifest.json` survive. No partial timing is reconstructed or
credited.

## 6. Relationship to prior LVL-10 evidence

LVL-10 remains `INCONCLUSIVE` for its original first-playable-reserve primary
metric because two 45/45 real-Provider populations failed separate A1/A2 drift
gates. Its long completion nevertheless improved 20–24% in both populations,
while medium completion regressed 10–24%.

LVL-10L v2 independently reproduced a larger long-completion signal in a clean
12/12 pilot. Together, these establish repeatable **directional long-form
headroom**, not the frozen five-round materiality gate. Stopping now follows
Hongxing's instruction and avoids further high-duration Provider cost.

## 7. Terminal disposition

- **STOP additional long-duration testing.** Do not rerun or reconstruct the
  aborted formal.
- Preserve LVL-10 as `INCONCLUSIVE` and LVL-10L as **directionally positive,
  formal unexecuted**.
- Do not wire B2/B4 into Runtime, Provider, Gateway, P2, Browser or product
  configuration.
- If this hypothesis is ever reopened, begin with a new reviewed product-policy
  packet and real Browser/prosody/cancellation validation; do not reuse the
  stopped formal ID.
- Continue latency work with the separately specified LVL-08 Provider-native
  Semantic VAD screen. The 1200 ms Server-VAD fallback remains unchanged.

## 8. Private artifact bindings

Private root:
`/home/renan/openJiuwen-ai/live-voice-latency-runs/lvl10l/`.

| Run / file set | Key SHA-256 bindings | State |
|---|---|---|
| v1 quota pilot | run `abf741e9`; manifest `6d7225fe`; attempts `1e366abd`; report JSON `89250942`; report MD `f9cd35f3` | `FAILED_WORKFLOW`, retained |
| v1 cap pilot | run `91e9a075`; manifest `6d7225fe`; attempts `a274de91`; report JSON `04e05408`; report MD `faca6831` | `DIAGNOSTIC`, retained |
| v2 passing pilot | run `942ebafc`; manifest `60327f98`; attempts `0fd9ebf9`; report JSON `dc9973c5`; report MD `f2dbf869` | `DIAGNOSTIC_DIRECTIONAL`, retained |
| v2 aborted formal | run `1886b13e`; manifest `60327f98`; no attempts/report | `ABORTED`, zero timing credit |

The complete review/research archive was copied out of `/tmp` to
`/home/renan/openJiuwen-ai/live-voice-latency-runs/private-review-archive/2026-08-24/`.
Raw artifacts and private environment state remain outside Git.
