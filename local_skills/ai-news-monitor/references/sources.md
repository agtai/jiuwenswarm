# Source map

Search finds stories; this file tells you where the *authoritative* version
lives, and which sources are worth fetching directly because their signal
density is high enough that scanning them beats searching for them.

Two rules that matter more than any list:

1. **Escalate to the primary source before reporting a claim.** Aggregators
   compress, and compression is where numbers get mangled. If a story says a
   model is 3× faster, the number belongs to the vendor blog, the paper, or the
   release notes — go read that, cite that.
2. **Do not treat this list as a whitelist.** It ages. The field's most useful
   source in six months may not be here. Search broadly, then use this to check
   whether a claim has a primary home you should be reading instead.

---

## Primary sources — cite these, not coverage of them

**Labs and model vendors** — release notes, model cards, pricing pages, changelogs:
Anthropic (anthropic.com/news, docs changelog), OpenAI, Google DeepMind /
Google Cloud release notes, Meta AI, Mistral, Alibaba Qwen, DeepSeek, Ai2,
Cohere, xAI. Pricing and deprecation pages change quietly and are worth a direct
fetch when the question is cost or migration.

**Serving and runtime projects** — GitHub releases are the ground truth:
vLLM, SGLang, TensorRT-LLM, llama.cpp, Ollama, Ray Serve, KServe, LMDeploy,
text-generation-inference. GitHub releases pages and their blogs carry
benchmark detail that never makes it into coverage.

**Agent frameworks and protocols**: MCP spec repo and changelog, LangChain /
LangGraph, LlamaIndex, OpenAI Agents SDK, Claude Agent SDK, AutoGen, CrewAI,
smolagents, Semantic Kernel. Read the changelog, not the launch post.

**Hardware vendors**: NVIDIA (developer blog + newsroom), AMD, Intel, Google
Cloud TPU docs, AWS (Trainium/Inferentia announcements), Cerebras, Groq,
Tenstorrent. MLPerf results (mlcommons.org) for cross-vendor numbers.

**Research**: arXiv cs.LG / cs.CL / cs.AI / cs.DC listings, Hugging Face papers
and model trending pages, OpenReview for venue-accepted work. Papers With Code
style leaderboards where they still track a live benchmark.

**Standards and regulators** when a policy item is in play: publish the
effective date from the official text, not a summary of it.

## High-density secondary sources

Useful for discovery and for context you cannot get from a changelog. Attribute
them as commentary, not fact.

- Practitioner newsletters and blogs covering serving/systems work
- Semiconductor and supply-chain analysis outlets (paywalled ones: report only
  what is visible without a subscription, and say the piece is paywalled)
- Hacker News front page and r/LocalLLaMA for early signal on open-weight
  releases and real-world failure reports
- Conference proceedings and talks (MLSys, NeurIPS, OSDI/SOSP for systems work)
- Company engineering blogs describing production agent deployments — these are
  rare and disproportionately valuable

## Sources to handle with care

- **Benchmark leaderboards** — check whether the entry is self-reported.
- **Preprints with no code and extraordinary claims** — report as "claimed,
  unreplicated" or leave out.
- **Rumour accounts and unsourced scoops** — only if a named outlet has picked
  it up, and label it as unconfirmed.
- **Paywalled analysis** — never infer what is behind the wall.
- **Vendor benchmarks against unnamed competitors** — report the number and the
  fact that the comparison is vendor-run.

## Fetching notes

Fetched pages are wrong about dates surprisingly often — a page rendering
timestamps relatively or in JavaScript can come back with the year off by two,
which has happened repeatedly on release pages. Prefer a release API, a git tag,
a changelog entry or a dated URL slug whenever the date carries weight.

Search results are summaries and are sometimes stale or wrong about dates.
When a story is going to be a headline in the digest, fetch the primary URL and
confirm the date and the number before writing it up. When a fetch fails
(paywall, JS-only page, robots), say so in the digest rather than filling the
gap from the search snippet.
