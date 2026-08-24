# LVL-10 authoritative-final chunked-TTS Provider result

> Date: 2026-08-24
>
> **Result: INCONCLUSIVE for the predeclared first-playable materiality
> question; no product wiring authorized.** Two formal real-Provider runs
> completed 45/45 attempts with zero Provider errors, but each violated the
> frozen A1/A2 drift gate in one workload. A repeatable long-form completion
> signal is retained as a new hypothesis, not retroactive LVL-10 credit.

## 1. Question and boundary

The no-Browser screen compared:

- `LVL-10-A1/A2`: one SSE TTS request containing the complete authoritative
  final text;
- `LVL-10-B`: the same committed text split into one to four manifest-bound
  chunks, one Provider request per chunk, at most two active requests and one
  prefetched successor.

Phase 1 measured Provider first PCM, 250 ms / 12,000-sample source reserve,
completion, ordered-release stall and request/error counts. It did not measure
Browser scheduling, first audible word, physical playback, prosody or barge-in.

## 2. Source and verification

| Field | Value |
|---|---|
| JiuwenSwarm source | `9cbb462dc7fb9a1740d30bd1c74b18bd1b68f79b` |
| Agent-Core source | `94e10cb6102c36fe78a64547957c0def97299273` |
| Source state | clean detached run worktree |
| Provider | configured real OpenAI streaming Speech route |
| TTS | configured `gpt-4o-mini-tts` family / `marin` class from private environment |
| Corpus | frozen English short/medium/long manifest, SHA-256 `7e47dab2fdbbe3161e0d56942e59d576fd9754b45a7bf38a70632b12fc3e0c7f` |
| Automated verification | `168 passed`; Ruff and `git diff --check` PASS |

The initial source `e493799f7` preflight expired at approximately 2,003 ms
because the validation runner imposed a 2-second Provider-event timeout. It was
interrupted, retained and receives no timing credit. Commit `80768c395` raised
the validation idle interval to 15 seconds and preserved process-control truth;
the corrected source then passed 9/9 pilot attempts.

## 3. Corrected pilot

Run `lvl10-provider-pilot-v2-20260824T125242Z-9cbb462dc` completed all nine
attempts with zero Provider errors. Its `INCONCLUSIVE` label is expected because
the formal reducer requires five attempts in every role/fixture cell.

| Role | Workload | First PCM | 250 ms reserve | Complete | Requests |
|---|---|---:|---:|---:|---:|
| A1 | short | 1,018.7 ms | 1,570.0 ms | 1,803.0 ms | 1 |
| A1 | medium | 1,504.4 ms | 2,074.3 ms | 3,847.4 ms | 1 |
| A1 | long | 965.4 ms | 1,500.3 ms | 6,213.9 ms | 1 |
| B | short | 1,017.2 ms | 1,974.7 ms | 2,029.7 ms | 1 |
| B | medium | 919.6 ms | 1,475.7 ms | 4,013.0 ms | 3 |
| B | long | 666.5 ms | 1,503.9 ms | 5,013.2 ms | 4 |
| A2 | short | 945.7 ms | 1,757.0 ms | 1,903.2 ms | 1 |
| A2 | medium | 1,177.8 ms | 1,599.9 ms | 3,285.0 ms | 1 |
| A2 | long | 993.7 ms | 1,901.1 ms | 6,774.1 ms | 1 |

## 4. Formal run 1

Run `lvl10-provider-formal-20260824T125358Z-9cbb462dc` completed 45/45 with
zero Provider errors.

| Role | Workload | First PCM p50 | Reserve p50 | Complete p50 | Reserve p95 |
|---|---|---:|---:|---:|---:|
| A1 | short | 902.0 ms | 1,532.4 ms | 1,673.8 ms | 1,667.3 ms |
| A1 | medium | 1,037.4 ms | 1,955.7 ms | 3,607.8 ms | 2,447.7 ms |
| A1 | long | 1,041.6 ms | 1,515.8 ms | 6,350.2 ms | 1,726.3 ms |
| B | short | 1,039.4 ms | 1,613.0 ms | 1,690.5 ms | 1,851.7 ms |
| B | medium | 854.3 ms | 1,470.0 ms | 4,015.4 ms | 1,690.7 ms |
| B | long | 889.1 ms | 1,351.2 ms | 5,065.1 ms | 2,265.9 ms |
| A2 | short | 1,007.4 ms | 1,757.7 ms | 1,854.5 ms | 4,886.0 ms |
| A2 | medium | 899.1 ms | 1,528.9 ms | 3,638.4 ms | 2,101.2 ms |
| A2 | long | 995.4 ms | 1,612.2 ms | 6,480.1 ms | 1,939.3 ms |

The medium A1/A2 reserve differed by 426.8 ms and about 27.9%, violating both
the 250 ms and 20% validity bounds. The run is therefore `INCONCLUSIVE` before
candidate materiality is judged.

## 5. Formal run 2

Run `lvl10-provider-formal-v2-20260824T125737Z-9cbb462dc` also completed 45/45
with zero Provider errors.

| Role | Workload | First PCM p50 | Reserve p50 | Complete p50 | Reserve p95 |
|---|---|---:|---:|---:|---:|
| A1 | short | 887.0 ms | 1,556.8 ms | 1,728.7 ms | 2,984.0 ms |
| A1 | medium | 1,070.6 ms | 1,515.0 ms | 3,529.4 ms | 1,637.5 ms |
| A1 | long | 1,044.4 ms | 1,854.7 ms | 6,886.7 ms | 3,398.0 ms |
| B | short | 1,091.7 ms | 1,670.4 ms | 1,760.2 ms | 1,849.0 ms |
| B | medium | 984.3 ms | 1,735.0 ms | 4,350.3 ms | 1,863.9 ms |
| B | long | 955.5 ms | 1,520.0 ms | 5,235.9 ms | 1,676.1 ms |
| A2 | short | 1,094.4 ms | 1,556.0 ms | 1,728.2 ms | 1,636.6 ms |
| A2 | medium | 944.6 ms | 1,627.6 ms | 3,505.8 ms | 1,892.8 ms |
| A2 | long | 1,007.6 ms | 1,533.0 ms | 6,543.4 ms | 3,087.2 ms |

The long A1/A2 reserve differed by 321.7 ms and about 21.0%, again violating
both validity bounds. This run is also `INCONCLUSIVE`.

## 6. What the data does establish

The frozen primary question remains unresolved: reserve/first-PCM improvement
was not stable against both controls, and both formal populations failed their
control-drift gate. No threshold may be relaxed after observing the result.

One workload-specific secondary signal repeated:

| Long completion | A reference | B | B delta |
|---|---:|---:|---:|
| Formal 1 vs A1 | 6,350.2 ms | 5,065.1 ms | **-1,285.1 ms / -20.2%** |
| Formal 1 vs A2 | 6,480.1 ms | 5,065.1 ms | **-1,415.0 ms / -21.8%** |
| Formal 2 vs A1 | 6,886.7 ms | 5,235.9 ms | **-1,650.8 ms / -24.0%** |
| Formal 2 vs A2 | 6,543.4 ms | 5,235.9 ms | **-1,307.5 ms / -20.0%** |

Medium completion moved in the opposite direction: B regressed about 10–11%
in formal run 1 and 23–24% in formal run 2. This supports a new hypothesis that
parallel chunk requests amortize their overhead only for sufficiently long
outputs. It does not authorize a universal chunked-TTS route or a post-hoc
change from reserve to completion as LVL-10's primary metric.

## 7. Disposition and next hypothesis

- LVL-10 phase 1: **INCONCLUSIVE; STOP before product wiring and Browser Lane C**.
- Keep the current one-request full-final SSE product route unchanged.
- Preserve LVL-08 Semantic VAD as the next already-specified no-Browser screen.
- A separate prospective `LVL-10L` long-form screen may be proposed with:
  completion as its declared primary metric, frozen output-size buckets,
  exact chunk policy/request bounds, first-audio non-regression, reliability /
  cost gates and no product classifier before materiality PASS.

## 8. Artifact bindings

| Run/artifact | SHA-256 |
|---|---|
| Failed 2 s preflight `run.json` | `60351449276e762312f5d65a728bf47239cc8b9129a4cca9f276d8bb7b2c1684` |
| Pilot v2 `run.json` | `bd26d6ed3d6a2c23d7d6317076fb2685f6c8a547fbdaae3d42851b8962d736c5` |
| Pilot v2 `attempts.jsonl` | `97f3ffd975b19323e2c57c8caddc8531583c83598422662410bfd359052d6d27` |
| Pilot v2 `report.json` | `ac89cf886cc22de187d47c3650c51f13948cc32cffefec781cb8fe3d56802b7d` |
| Formal 1 `run.json` | `e06389a62256334d9fcf91ef3c02717534a1ce0802c978730a5a43e84145aa8c` |
| Formal 1 `attempts.jsonl` | `0514bbfdf40a51ba37a87234c99d2f69de79cd9619e34025574e09d7129566df` |
| Formal 1 `report.json` | `f25ebfe8a5cc88746db1a04f4fd417858cbf4339c2af36bb5be6567aee1a69bf` |
| Formal 2 `run.json` | `5d69ece308cfef10811e91ce56a9ffe50340cfee3e49222d90159a32c1164cfe` |
| Formal 2 `attempts.jsonl` | `c5817c4dae1e3b93cd85f93d7710ac4a17576f445675e312ad976038cf3760b2` |
| Formal 2 `report.json` | `495580c3d0a87553ea9819859785826e5c46c1275084a7df1bcc780911732a8c` |

Raw files remain in the private latency archive. The repository evidence is
sanitized and contains no credential or final-text payload beyond the already
approved public fixture description.
