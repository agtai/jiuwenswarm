# Beats and query bank

Each beat is a slice of the field with its own vocabulary, its own primary
sources, and its own failure mode for search. Sweep beats independently — one
generic "AI news" search returns the same five consumer-facing stories every
time and misses the serving-stack and silicon news entirely, which is usually
where the decision-relevant detail lives.

Default sweep: all seven. Narrow only when the ask itself is narrow — "any vLLM
news" is one beat. Scale a quick check by running fewer queries per beat, not by
dropping beats: a beat that comes back empty costs almost nothing, and the week
the story is a grid constraint or an agent exploit is exactly the week a
narrower sweep would have missed it.

Angle brackets in the query seeds below are placeholders, not literals.
`<month year>`, `<year>`, `<quarter>` and `<date>` must be filled from the
`date -u +%F` run in Step 1 of SKILL.md — the actual current month and year, not
a month recalled from memory. None of the search backends available here accepts
a recency or date-range parameter, so these words are the only thing scoping a
query to now; a seed issued with a stale month returns confident, well-ranked
results from the wrong period, and nothing downstream will flag them. A query
that still contains a literal `<` was not filled in and should not be issued.

Each beat has a fixed slug, used as the `beat` value on every ledger entry and
as the argument to `recent --beat`. Reuse these exactly; a run that invents its
own splits a beat's history so later filtering silently misses half of it. The
right-hand column is the reader-facing label used in the digest — beats
themselves never appear in published output.

| # | Beat | Ledger slug | Digest label |
|---|---|---|---|
| 1 | Agentic AI — frameworks, protocols, tool use | `agents` | Agents & protocols |
| 2 | Inference and serving | `inference` | Inference & serving |
| 3 | Hardware and silicon | `hardware` | Hardware |
| 4 | Model releases and capability shifts | `models` | Models |
| 5 | Evaluation and benchmarks | `evaluation` | Evaluation |
| 6 | Infrastructure economics and business | `business` | Business & infrastructure |
| 7 | Policy, safety, and security | `policy` | Policy & security |

**One item takes one slug.** Stories routinely span beats — an MLPerf submission
is hardware, inference and evaluation at once; an export rule is hardware and
policy. File it under the beat whose *reader* most needs it, which is usually the
one whose "watch for" note applies: MLPerf numbers live or die on how they were
run, so they are `evaluation`; an export rule changes what you can buy, so it is
`hardware`. Recording one item twice inflates the published count and splits its
history, which is the exact failure these slugs exist to prevent. When it is
genuinely a toss-up, prefer the beat you filed the earlier parts of the story
under, so the thread stays together.

---

## 1. Agentic AI — frameworks, protocols, tool use

The core beat. Anything about models taking multi-step actions: agent
frameworks and SDKs, tool/function calling, computer use, MCP and other
interop protocols, multi-agent orchestration, memory and context management,
sandboxing and permissioning, agent evaluation harnesses, coding agents.

Query seeds:
- `agent framework release <month year>`
- `Model Context Protocol MCP update`
- `computer use agent benchmark results`
- `multi-agent orchestration production deployment`
- `coding agent SWE-bench results`
- `agent tool calling reliability`
- `long-running autonomous agent incident postmortem`

Watch for: capability claims without an eval; framework launches that are
wrappers; and the genuinely load-bearing stuff — protocol version changes,
permission models, anything that changes what an agent is allowed to do
unattended.

## 2. Inference and serving

How models actually run: serving engines (vLLM, SGLang, TensorRT-LLM,
llama.cpp), batching and scheduling, KV-cache management and offload,
speculative decoding, quantisation, prefill/decode disaggregation, long-context
serving, routing and caching layers, latency/throughput/cost numbers.

Query seeds:
- `vLLM release notes` / `SGLang release`
- `inference throughput tokens per second benchmark <quarter>`
- `KV cache offload disaggregated prefill`
- `speculative decoding production results`
- `quantization FP8 FP4 accuracy tradeoff`
- `LLM inference cost per million tokens <month year>`

Watch for: benchmark numbers without hardware, batch size, and precision stated
— they are not comparable and should be reported with that caveat or not at all.

## 3. Hardware and silicon

Accelerators (NVIDIA, AMD, Google TPU, AWS Trainium/Inferentia, Cerebras, Groq,
Tenstorrent), interconnect and networking, memory (HBM supply, capacity per
part), datacenter power and buildouts, supply chain and export controls,
on-device NPUs.

Query seeds:
- `<vendor> AI accelerator announcement <month year>`
- `HBM supply capacity <year>`
- `TPU Trainium instance availability pricing`
- `AI datacenter power gigawatt buildout`
- `GPU export controls rule change`
- `inference chip benchmark MLPerf`

Watch for: roadmap slides restated as shipping products. Distinguish announced /
sampling / generally available — the date something is buyable is the news.

## 4. Model releases and capability shifts

New frontier and open-weight models, context-window and modality changes,
pricing changes, deprecations, licence changes, meaningful system-card findings.

Query seeds:
- `frontier model release <month year>`
- `open weights model release benchmark`
- `API pricing change per token <month year>`
- `model deprecation sunset date`
- `context window <n>k release`

Watch for: leaderboard-only claims. A release matters when weights, an API, or a
paper exists; otherwise it is a preannouncement, and worth labelling as one.

## 5. Evaluation and benchmarks

New benchmarks and harnesses, contamination and saturation findings,
reproduction attempts and failures, agentic eval methodology, red-team results.

Query seeds:
- `agent benchmark contamination reproduction`
- `new LLM benchmark release methodology`
- `evaluation harness disagreement results`
- `<benchmark> saturation successor benchmark <year>`
- `independent evaluation frontier model <month year>`
- `red team results system card finding`
- `benchmark results could not be reproduced`
- `long-horizon agentic evaluation methodology`

Watch for: leaderboard PR dressed as evaluation. A new high score is not a
finding. What is reportable here is a method, a saturation result, a failed
reproduction, or a disagreement between harnesses — and in every case, who ran
it. Self-reported and independently-run numbers are different claims.

## 6. Infrastructure economics and business

Capacity deals, cloud commitments, pricing wars, unit economics disclosures,
funding rounds large enough to change the field's structure, notable adoption
numbers with a source.

Query seeds:
- `AI compute deal capacity commitment <month year>`
- `inference gross margin disclosure`
- `enterprise agent deployment adoption numbers`
- `multi-year cloud compute agreement AI <year>`
- `datacenter capex guidance earnings call AI`
- `API price cut per million tokens <month year>`
- `token volume disclosure quarterly results`

Watch for: funding-round noise. A round is news here only if it changes who can
buy compute at scale, or comes with real operating numbers.

## 7. Policy, safety, and security as deployment constraints

Regulation that changes what can ship, agent-specific security research (prompt
injection, tool-use exploits, sandbox escapes), incident reports, liability and
audit requirements.

Query seeds:
- `prompt injection agent exploit disclosure`
- `AI agent security incident report`
- `AI regulation compliance deadline <year>`
- `CVE agent runtime sandbox escape <year>`
- `supply chain attack MCP server package`
- `AI act obligation takes effect <date>`
- `model weights export restriction rule change`
- `enforcement action AI deployment liability`

Watch for: the practical hook. Report the date something takes effect, or the
concrete attack class — not the general debate.
