# Second Brain PoC (Slack papers channel) — Setup runbook

Everything that makes this branch *work* lives outside the repository: API keys, the
`config.yaml` scope block, the Slack app, and the wiki's own rule file. This runbook is
that missing half. Clone the branch, follow it top to bottom, and you get the same system.

- Design and results: `docs/superpowers/specs/2026-09-09-second-brain-slack-poc-design.md`
- Task-by-task implementation: `docs/superpowers/plans/2026-09-09-second-brain-slack-poc.md`

**No secret in this file is real.** Every key is a placeholder. Do not commit real ones:
`~/.jiuwenswarm/config/config.yaml` and `.env` hold live credentials and should be `chmod 600`.

---

## 1. What it does

A PDF dropped in a Slack channel is compiled into a persistent agent-authored wiki (the
Karpathy "LLM wiki" pattern), where every substantive claim carries an anchor back to the
page of the source it came from. Questions in the channel are answered from that wiki via
hybrid search, citing those anchors.

Current state of the reference library: 4 papers, 52 pages, 1276 anchors, 0 broken links.

---

## 2. Prerequisites

```bash
git checkout second-brain-slack-poc-renan
uv sync          # openjiuwen is PINNED; do not upgrade it casually
```

The pin matters. `pyproject.toml` fixes `openjiuwen` at a commit, and an out-of-sync venv
fails in a way that looks like a code bug: tools appear unregistered, and the agent
truthfully reports that `wiki_ingest` does not exist. If you see that, run `uv sync`
before debugging anything else.

Run the backend from the worktree/checkout you edited, not from another one. Running the
backend from a checkout that lacks the tool registration produces exactly the same
symptom.

---

## 3. Embeddings — not optional

This is the single configuration item most likely to be skipped, and skipping it is the
difference between a demo that works and one that does not.

Retrieval quality measured on the same 10 questions against the same library:

| Configuration | Score |
|---|---|
| BM25 only, no embeddings | 3/10 |
| hybrid, `baai/bge-m3`, questions in Portuguese | 7/10 |
| hybrid, `baai/bge-m3`, questions in English | 9/10 |

Without embeddings the keyword leg alone is left, and the FTS5 trigram tokenizer matches
short foreign-language stopwords inside English words: `'o que e AREX?'` becomes
`'"que" OR "AREX"'`, and `que` matches inside *frequency*, *sequence* and *technique*,
sinking the right page out of the top-5.

The model must be **multilingual**. `baai/bge-m3` was chosen for that reason: the library
is written in English while questions arrive in any language, and a monolingual embedding
turns every non-English question into a miss.

In `~/.jiuwenswarm/config/.env`:

```bash
EMBED_API_BASE=https://openrouter.ai/api/v1
EMBED_API_KEY=<your OpenRouter key>
EMBED_MODEL=baai/bge-m3
```

In `~/.jiuwenswarm/config/config.yaml` (the block reads those variables):

```yaml
embed:
  embed_api_key: <your key, or leave the env var to supply it>
  embed_base_url: ${EMBED_API_BASE}
  embed_model: ${EMBED_MODEL}
```

**If you change the embedding model, delete `memory.db` and let it rebuild.** Vectors
from two different models are not comparable, and nothing detects the mismatch for you:

```bash
rm ~/.jiuwenswarm/agent/workspace/memory/memory.db
```

### The BM25 index used to empty itself on every restart

If you see `chunks` holding rows while `chunks_fts_docsize` holds 0, the lexical half of
hybrid search is dead and only the vector channel is answering. The cause is upstream, in
`openjiuwen/core/memory/lite/manager.py`: `_ensure_schema` creates the table with
`tokenize='trigram'` (quoted, and SQLite stores the CREATE verbatim) while
`_fts_table_is_legacy` looks for the unquoted `tokenize=trigram`. The substring never
matches, so the table the manager just created is read as legacy and dropped — on every
startup. The force-reindex that would refill it is gated on a `ftsTrigram` flag in `meta`
that the first startup already recorded, so from the second boot onwards the table is
dropped and never refilled. Nothing raises; the only trace is an INFO line,
`Migrating chunks_fts from unicode61 to trigram`, which repeats on every boot.

`jiuwenswarm/server/runtime/memory/fts_trigram_patch.py` fixes both halves and is applied
at adapter startup, so on this branch you should not hit it. Delete `memory.db` only if
you are running without that patch.

### The lexical ranking was also inverted

A second, independent defect in the same subsystem. FTS5 reports match quality in `rank`
as a negative number where more negative is better -- which is why the kernel's keyword
query says `ORDER BY rank` with no `DESC`. But `bm25_rank_to_score` mapped it with
`1 / (1 + |rank|)`, so the score *fell* as the match improved.

Measured on this corpus, for one query's top five rows:

| rank | stock score | corrected |
|---|---|---|
| -3.7968 (best) | 0.2085 | 0.7915 |
| -3.6085 (worst of the five) | 0.2170 | 0.7830 |

Hybrid search merges `0.7 * vector + 0.3 * text` and keeps rows scoring at least 0.7, so
a document with a vector score of 0.80 and that best keyword hit scored 0.623 and was
filtered out -- *because* its keyword match was good. Corrected it scores 0.797 and is
kept. The symptom had been noticed upstream and read as a property of BM25: the kernel
comments that scores "commonly land 0.1-0.3 after the rank->score transform" and
compensates with a lower floor on the no-embeddings path.

`jiuwenswarm/server/runtime/memory/bm25_score_patch.py` corrects it, and the copy of the
same function in `jiuwenswarm/agents/harness/common/memory/internal.py` is fixed directly.
Both bindings have to be rebound in the kernel: `manager.py` imports the function by name
at module level, so patching only `internal` would silently do nothing.

---

## 4. Chat model

`models.defaults` in `config.yaml`; the first entry with `is_default: true` is what the
wiki maintainer subagent uses.

```yaml
models:
  defaults:
    - model_client_config:
        api_base: https://api.deepseek.com/
        api_key: <your key>
        model_name: deepseek-v4-flash
        client_provider: OpenAI
        timeout: 1800
      model_config_obj:
        temperature: 0.95
      is_default: true
```

`timeout: 1800` is deliberate — an ingest makes long calls.

**A cost worth knowing:** DeepSeek runs in thinking mode at effort `high` by default, and
no `thinking` parameter is sent to turn it down. Measured on a real ingest, reasoning was
**43% of total LLM time** (93 s of 214 s), with single calls spending 72 s purely
thinking. Adding `reasoning_level: low` to `model_config_obj` reclaims most of that, but
it is untested against anchor quality: the reasoning traces show the model carefully
copying exact quote substrings to satisfy the anchoring rules. Treat it as an A/B to run,
not a free win.

---

## 5. Slack app

Create an app with **Socket Mode** enabled.

Bot token scopes: `app_mentions:read`, `channels:history`, `groups:history`,
`chat:write`, `files:read`, `users:read`.

**Event subscriptions — subscribe to `app_mention`.** Having the `app_mentions:read`
*scope* is not the same as subscribing to the *event*, and the failure mode is silent:
the bot sits in the channel and never answers. This cost us a debugging session.

Then in `config.yaml`:

```yaml
channels:
  slack:
    bot_token: xoxb-<your bot token>
    app_token: xapp-<your app token>
    allowed_channel_ids:
      - <papers channel id, e.g. C0XXXXXXXXX>
    default_channel_id: <a channel id>
    reply_in_thread: true
    enabled: true
```

Invite the bot to the private channel. Get the channel id from the channel's URL or
"View channel details".

---

## 6. The channel scope

`scopes:` is a top-level key in `config.yaml`. Two layers: a broad one for all Slack, and
a narrow one for the papers channel. **A scope can only narrow, never widen** — it cannot
grant a tool the agent does not already have.

```yaml
scopes:
  - match:
      channel: slack
    delivery:
      prompt: |
        Answer directly and cite your sources.

  - match:
      channel: slack
      chat: "<papers channel id>"
    delivery:
      mode: [mention, has_file]
      # The default is `cancel`: any message in the thread during the minutes an ingest
      # takes would cancel the turn, and the manifest only records after success, so the
      # retry would start from zero. `queue` holds until the session goes idle.
      mid_turn: queue
      prompt_append: |
        This channel is a library of papers backed by an LLM Wiki at
        <WIKI_WORKSPACE>.

        - New attachment, and only if it is .pdf/.md/.txt:
          1. call wiki_ingest(source=<local path of the attachment>,
             workspace="<WIKI_WORKSPACE>");
          2. when it answers [Success], say the ingest finished and invite questions.
             Publishing to the memory index is automatic; do not do it yourself.

        - If asked to SEE the wiki, the library, the index or "what's in there":
          read with read_file the file <WIKI_WORKSPACE>/.llm_wiki/wiki/index.md
          and present it as a TREE inside a code block, grouped by the index's own
          sections, one line per page: file name followed by its description. Do NOT
          reproduce the [text](file.md) syntax -- Slack does not resolve those links and
          they show up raw. End by saying how many pages and how many sources it holds.

        Do NOT use bash or ls. Apart from the index.md above, do not open wiki files to
        inspect it: use memory_search or wiki_query.
        - Question about the papers: use memory_search to find the relevant pages and
          answer citing the anchors [[fonte: file.pdf pN]]. For questions that require
          sweeping the whole library, use wiki_query.
        - SEARCH LANGUAGE: the library is in English. Phrase EVERY memory_search query in
          English, even when the question came in another language, and use the terms the
          papers themselves would use. Answer the user in the language they asked in.
        - Never assert anything about a paper without an anchor.
        - ANSWER DIRECTLY: do not announce what you are about to do, do not narrate your
          tools, and do not comment on installed skills or environment configuration.
        - FROZEN LIBRARY: when ANSWERING, never write to the wiki. Do not create pages,
          do not edit existing pages, do not update index.md or log.md. Never pass
          allow_write=true to wiki_query: that flag lets the answer be filed back as a
          page, which is exactly what this rule forbids. If while answering you notice a
          gap or inconsistency, REPORT it in the answer instead of fixing it on disk.
        - Attachment that is not .pdf/.md/.txt: do not ingest; say why.
```

Two rules there are load-bearing and worth understanding before you edit them:

- **SEARCH LANGUAGE** exists because of the 7/10-vs-9/10 gap in §3. The library is
  English; querying it in English and answering in the user's language is what recovers
  those two points.
- **FROZEN LIBRARY** keeps the demo reproducible. Note the explicit mention of
  `allow_write`: the rule is addressed to the main agent, but the write it forbids used to
  happen inside `wiki_query`'s subagent, a layer the channel prompt does not reach. Naming
  the flag is what makes the rule enforceable at the layer where the write occurs.

---

## 7. Permissions — the approval trap

Default `permissions` gives `bash: ask`, and a rule list allows only a fixed set of
patterns (`ls`, `cat`, `head`, `tail`, `pwd`, `cd`, `echo`, and a few `git`). Anything
else prompts for approval.

**In Slack, an approval prompt is a dead turn.** The connector says so at boot:

```
[SlackChannel] approval buttons inactive: an approval is only delivered on a streamed
turn and channels.slack.enable_streaming is false, so a task that asks for one pauses
with nothing shown in Slack
```

The task hangs and the user sees nothing. This is why the channel prompt forbids `bash`,
and why the wiki lives *inside* the agent workspace (§8): a path outside it triggers an
approval on any file operation.

If you need the agent to run something new (downloading an arXiv PDF, say), either add a
narrow allow rule, or enable streaming so the buttons render — but note that a shell
pattern allowlist is weak: `curl a; curl b` is one command string.

---

## 8. The wiki workspace and its rules

**Put the wiki inside the agent workspace.** Anywhere else and every file operation asks
for approval — see §7.

```bash
export WIKI=~/.jiuwenswarm/agent/workspace/wikis/papers
mkdir -p $WIKI/.llm_wiki/schema
```

`ensure_initialized` writes `schema/AGENT.md` **only if it does not already exist**, so
seeding it before the first ingest is how you install the anchoring rules without
touching the code default. This file is the product: it is what makes the wiki
trustworthy rather than a pile of summaries.

```bash
cat > $WIKI/.llm_wiki/schema/AGENT.md <<'RULES'
# Wiki Maintainer Rules
1. Never modify files inside `sources/`.
2. All pages you generate MUST be saved directly inside the `wiki/` directory root.
3. You must maintain a `wiki/index.md` listing all topics.
4. You must maintain a `wiki/log.md` with an append-only timeline of ingestions.
5. Break concepts down into modular topic pages.
6. Make heavy use of markdown links to interconnect pages within `wiki/`.
7. DO NOT create subdirectories. Save all files in the `wiki/` root.
8. Every substantive claim carries a pointer to its source ON THE SAME LINE as the
   claim: `[[fonte: <filename> p.N]]`. For a PDF, N is the number in the `## Page N`
   heading that `read_file` returns. Never infer a page number.
9. Directly below the claim, quote the source in a blockquote, 25 words or fewer. Quote
   it AS EXTRACTED; it may contain hyphenation and line-break artefacts.
10. If a read returned no locator, anchor on the file alone. Never invent a page.
11. Read a PDF with `read_file` and its `pages` parameter, in ranges of AT MOST 5 pages.
    If a response looks truncated, re-read a smaller range before writing any claim
    about that stretch.
12. Ingest only `.pdf`, `.md` and `.txt`. Anything else: do not ingest, and say why.
13. If you cannot satisfy a rule, say so in `wiki/log.md`. Never invent a value to fill
    a gap -- an unknown date is written as `unknown`, not guessed.
14. Every page opens with `##` sections that describe themselves, so the index can be
    built without reading the page.
15. Maintain `wiki/limitations-and-gaps.md`: what each source declares out of scope.
16. Maintain `wiki/cost-and-scale.md` and `wiki/disagreements.md` across all sources.
17. Maintain `wiki/open-questions.md`: what each source leaves unanswered.
RULES
```

Rules 15-17 create four **transversal pages** that span every source. They are what let
the library answer conceptual questions ("where do these papers disagree?", "what does
this cost to run?") that no single per-paper page can answer. They are also the reason
the library *compounds*: ingesting a second paper rewrites the first paper's pages.

The literal string `[[fonte:` is Portuguese and is **not** a translation oversight — it
is the anchor token the rules, the pages and the validator all agree on. Changing it
invalidates every existing anchor.

Rule 11's 5-page limit is more conservative than it needs to be: the kernel's real
budget is 20 pages / ~25k estimated tokens, and no truncation occurs at 5, 10 or 20 pages
on typical arXiv papers. Relaxing it saves a few seconds; it is not where the time goes.

---

## 9. Run it

```bash
cd <your checkout>
.venv/bin/python3 -m jiuwenswarm.start_services all
```

At boot, confirm the scope was accepted:

```
channels.slack is configured for 1 channel(s): C0XXXXXXXXX mode=[has_file,mention]
prompt=scopes model=default mid_turn=queue via=scopes
```

A warning naming a conversation and a key means that value was refused and the
conversation fell back to the layer below.

Then, in the channel: drop a PDF, wait for the ingest, and ask a question.

---

## 10. Verifying it actually works

Anchors and link integrity:

```bash
W=$WIKI/.llm_wiki/wiki
grep -c "\[\[fonte:" $W/*.md | sort -t: -k2 -rn | head
```

That the pages reached the search index (this only works with the backend up — nothing
indexes without a live agent, because the watcher belongs to the main agent's memory
manager and does not run in a CLI script):

```bash
.venv/bin/python -c "
import sqlite3, pathlib
db = pathlib.Path.home()/'.jiuwenswarm/agent/workspace/memory/memory.db'
c = sqlite3.connect(str(db))
print(c.execute(\"select count(*) from files where path like '%wiki__%'\").fetchone()[0])
"
```

Three log signals that the timing fixes are in effect:

```bash
L=~/.jiuwenswarm/logs/run/jiuwen.log
grep -c "timed out after 300"          $L   # must be 0 for runs after the fix
grep -c "NoneType.*attribute 'id'"     $L   # must be 0
grep    "^## \[" $WIKI/.llm_wiki/wiki/log.md | tail -3   # dated, never [unknown]
```

Retrieval quality, end to end, judged by content rather than by page name:

```bash
.venv/bin/python /path/to/measurements/measure_judge_en.py
```

---

## 11. Traps that cost us time

- **Measurement instruments were wrong three separate times** and each produced a
  confident false result: a `sed` that ate the `p` in `.pdf` and invented a defect; page-name
  labels invalidated by a re-ingest, reading as a 7→3 regression that never happened; and
  `max_tokens=5` on a reasoning model, which returns empty `content` with the text in
  `reasoning_content` and scores a clean 0/10. Sanity-check the instrument before
  believing the number. Spec §14 has the full account.
- **An ingest used to be killed at 300 s and silently retried from scratch.** Fixed on
  this branch; if you see `timed out after 300.0s` around a `wiki_ingest`, the fix is not
  in your checkout.
- **`memory.extraPaths` looks like the way to point the index at the wiki. It is not.**
  It feeds a different memory manager than the one the agent actually searches. Pages are
  copied into `<workspace>/memory` with a `wiki__` prefix instead, at the end of each
  successful ingest.
- **Ingest cost.** Roughly 3-4 minutes per paper after the fixes on this branch, ~96% of
  it LLM time. Budget for it in a live demo, and prefer ingesting beforehand.
