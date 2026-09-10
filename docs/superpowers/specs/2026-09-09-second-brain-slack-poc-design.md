# Second Brain PoC — a papers channel on Slack

Date: 2026-09-09 · Branch: `second-brain-slack-poc-renan` (base `55c3c3a85`)
Target: demo on 2026-09-11 (Friday)

## 1. Goal

A Slack channel dedicated to papers, where:

1. someone drops a PDF;
2. the agent compiles the paper into a **persistent wiki** (Karpathy's LLM Wiki
   pattern), with interlinked entity/concept pages and an index;
3. the wiki's claims carry **pointers back to the original text** (file + page +
   short quote), so they can be checked;
4. later questions are answered by **hybrid search** (BM25 + vector) over the wiki
   pages.

The point of the demo is **not** to prove the agent avoided re-reading the PDF.
Re-reading is *verification*, and the pointer is the product.

## 2. Out of scope

- **WikiSkill** (Google): it compiles the *agent's own execution* into procedural
  skills, not sources into knowledge. That is a different demo.
- Native graph/backlinks, export, synchronisation, page versioning.
- Proving the absence of re-reading (denying read tools).
- Making the wiki generic across document types. The PoC is scoped to one channel.

## 3. What already exists (verified in code, not assumed)

| Piece | State | Evidence |
|---|---|---|
| Three-layer wiki (`sources/`, `wiki/`, `schema/`) | ✅ works | smoke test: one 28-page PDF → 17 pages in 294 s |
| `wiki_ingest` / `wiki_query` / `wiki_lint` | ✅ implemented | `tools/wiki_tools.py` |
| `index.md` (Entities/Concepts/Sources) + `log.md` | ✅ generated | smoke test |
| SHA-256 dedup + copy into `sources/` | ✅ | `_SourceManifest` |
| Page-level PDF reading | ✅ | `read_file{"pages": "2-11"}` — the PDF parser is registered |
| Hybrid BM25 + vector index | ✅ exists | `memory/manager.py`, `_merge_hybrid_results` |
| `extraPaths` | ⚠️ **plumbed into the wrong manager** — see §3.1 | `config.py:170` → `manager.py:604`, but that manager does not serve the agent |
| Slack `has_file` trigger | ✅ | `slack_connect.py:200` |
| Per-conversation `delivery.prompt` (scopes) | ✅ | `scope_capabilities.py` |

### 3.1 Two memory stacks — and the agent uses the one that ignores `extraPaths`

    jiuwenswarm/agents/harness/common/memory/     openjiuwen/core/memory/lite/
    MemoryIndexManager                             (kernel, pin 61becb17)
         │ reads memory.extraPaths      ✅               │ receives extra_paths?  ❌
         │                                              │
         └─ used by: memory_tools.py                    └─ used by: MemoryRail
                     memory_rpc.py                                    │
                     (the TUI's /memory console)                      ▼
                                                        THIS IS THE ONE THE AGENT USES

- `interface_deep.py:6897` builds the `MemoryRail` from `openjiuwen.core.memory.lite`.
- `lite/manager.py:954` calls `list_memory_files(self.workspace, node_name=...)`
  **without `extra_paths`**, although the parameter exists (`lite/internal.py:35`).
- Nothing in `server/`, `gateway/` or `agents/swarm/` imports jiuwenswarm's
  `memory_tools.py` (empty grep).

Consequence: **`memory.extraPaths` is a dead key for the agent.** §5.4 as written in v1
would have failed deterministically. Corrected in §5.4 of this version.

The `lite` scan is also **flat** — `os.listdir`, not `os.walk` (`lite/internal.py:80`).

### What does **not** exist

| Gap | Detail |
|---|---|
| Wiki tools registered | unregistered upstream in `e4fae3061` (MR !4526, 6 Aug) |
| Anchoring to the source | the generated `AGENT.md` only asks for links *within* `wiki/` |
| Hybrid search inside `wiki_query` | it uses `read_file`/`grep`; no BM25, no vector |
| Embeddings configured | `EMBED_API_KEY`/`_BASE`/`_MODEL` empty |

## 4. Architecture

    PDF in #papers
        │  has_file trigger
        ▼
    Slack connector — downloads to <session>/uploads/, puts the path in the text
        │  delivery.prompt tells it to call wiki_ingest(source=<path>, workspace=<papers>)
        ▼
    wiki_ingest → maintainer subagent
        │  reads schema/AGENT.md (carrying the anchoring rule)
        │  reads the PDF in page ranges
        │  writes wiki/*.md with [[fonte: file.pdf p.N]] + quote
        ▼
    <papers>/.llm_wiki/wiki/*.md
        │  publication: file-by-file copy (§5.4)
        ▼
    <agent workspace>/memory/*.md
        │  the lite watcher reindexes
        ▼
    the lite kernel's index (FTS5 + vector)
        ▲
        │  memory_search  ← the user's question
    the channel agent synthesises the answer with the anchors

Two reading paths coexist, with distinct roles:

- **`memory_search`** (hybrid, fast) — the common case: a pointed question.
- **`wiki_query`** (subagent reading the wiki) — questions that require sweeping the
  whole library ("what do the three papers have in common?").

## 5. The four changes

### 5.1 Register the wiki tools  *(code — required)*

`server/runtime/agent_adapter/interface_deep.py`, reverting `e4fae3061`:

```python
from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_ingest, wiki_query
...
SHARED_AGENT_TOOLS = (wiki_ingest, wiki_query, read_pdf)   # wiki_lint is not needed
```

**Registration is global — and that is a choice, not an impossibility.**

*Via `scopes` it would be impossible*: they only narrow permissions (D4: `allow` never
widens, because the merge is `strictest`) and `not` exists only on identity axes, so no
scope can **grant** a tool to a channel.

*Via code it would be possible*: the adapter has `_is_session_scoped_adapter`, and
`_tool_owner_id()` already scopes by session (`<card id>_s_<session>`). Since a Slack
session id is `slack_{team}_{channel}_{thread}`, the channel is derivable inside
`_get_tool_cards`.

*We chose global* on cost/benefit: the conditional touches the hot path of agent
construction and needs a third parse of the session id — which the code itself
discourages (`parse_slack_cron_session` is documented as an unwanted second copy of that
parse).

**But global carries a security cost, and v2 understated it.** The earlier claim ("not a
risk, because an agent does not call `wiki_ingest` unless instructed") is wrong.

`wiki_ingest` validates extensions **only on its directory branch**; for a single file it
validates nothing (`wiki_tools.py:498-508`), and the copy is a bare `shutil.copy2`
(`wiki_tools.py:331`), **outside `SysOperation`** — hence outside the permission rail
that guards `read_file`. An agent in any channel could therefore call
`wiki_ingest(source="~/.jiuwenswarm/config/.env")`: the file is copied into `sources/`,
the subagent reads it, and the content becomes a wiki page — which §5.4 then publishes
into the index.

The precision matters: this does **not create** the ability to read files where the agent
already has `bash`/`read_file`. What it creates is a **read path that does not pass
through the permission rail** — in a channel where `bash` was denied by a scope,
`wiki_ingest` would stay open. It is a guard inconsistency.

**Mitigations.** A later review showed the earlier list was weak; this is the corrected
one:

1. **Restrict `source`** to the session's upload directory
   (`get_agent_sessions_dir()/<sid>/uploads`, where the connector deposits attachments —
   `slack_connect.py:11358`) or to the agent workspace. **This is the real fix.**
   Validating the extension alone is not enough: the directory branch runs `glob("**/*")`
   from any root (`wiki_tools.py:500-506`), so `wiki_ingest(source="~")` would ingest
   every markdown file the user owns.
2. **Validate the extension on the single-file branch too** — the `.pdf/.md/.txt` filter
   already exists on the other branch; it is the obvious bug, but a complement to (1),
   not a substitute.
3. **Use `sys_operation.fs()` for the copy** instead of `shutil.copy2`. The
   `sys_operation` parameter **already arrives** at the function (`wiki_tools.py:475`)
   and is ignored. This puts the read back behind the permission rail, which is the
   original inconsistency.
4. **Deny by scope where it is unwanted** — `permissions: {tools: {wiki_ingest: deny}}`.
   It works (narrowing is allowed), but it is opt-out per channel: the global default
   stays open, so it does not replace (1).

> **What is NOT a mitigation.** Leaving `wiki_lint` out of the registration protects
> nothing: it only reads the wiki. What writes to it is `wiki_query` — *"write it back
> into the wiki"*, `wiki_tools.py:352` — and that one **stays** registered. An earlier
> version of this spec listed that as a mitigation; it was theatre.

What scopes the *behaviour* is `delivery.prompt` (§5.3): the tool exists everywhere, but
only the papers channel instructs its use. Conditional registration is the natural
evolution if the PoC becomes a product.

> **Note on the divergence from upstream.** MR !4526 removed these three tools as part of
> a prompt-surface cleanup; it reports no defect in the wiki and the review was
> procedural (`/lgtm`). The same MR introduced *per-channel* prompt injection
> (`BrowserTaskPromptRail`), so its principle is "scope it, do not hand it to everyone" —
> which is what we do through `delivery.prompt`. Even so, this is a divergence to be
> revisited at the next rebase.

### 5.2 The anchoring rule  *(file — zero code)*

`ensure_initialized` writes `schema/AGENT.md` **only if it does not already exist**. So
it is enough to **pre-seed** the file in the papers workspace before the first ingest;
the code never overwrites it.

Rules added to the seven that already existed:

```markdown
8.  Every substantive claim carries a pointer to its source, ON THE SAME LINE as the
    claim: `[[fonte: <file> p.N]]`. For a PDF, N is the number in the `## Page N`
    heading that `read_file` returns — never an inferred number.
9.  Directly below, a short literal quote (≤ 25 words) in a blockquote. Quote it AS
    EXTRACTED; it may carry hyphenation and line-break artefacts.
10. If a read returned no locator, anchor on the file. Never invent a page.
11. Read a PDF with `read_file` and `pages`, in ranges of AT MOST 5 pages. If a response
    looks truncated, re-read a smaller range before writing any claim about that stretch.
12. Ingest only `.pdf`, `.md` and `.txt`. Anything else: do not ingest, report why.
```

Why these differ from v1:

- **"same line"** (rule 8) — the index chunks at ~256 tokens. An anchor separated from
  its claim lands in another chunk and S5 fails even with S3 perfect.
- **`## Page N`** (rule 8) — `harness/tools/filesystem.py:750` writes
  `f"## Page {page_no}\n{page_text}"`. The number is given, not inferred; this is what
  sustains S3. **Careful when checking:** it is pdfplumber's *physical* index (the file's
  first page is 1), not the number printed on the page. In a paper with a cover or roman
  numerals up front the two diverge — check against the PDF viewer's counter, not the
  printed number.
- **ranges ≤ 5** (rule 11) — the declared ceiling is 20 pages
  (`PDF_MAX_PAGES_PER_READ`), but `MAX_TOKENS = 25_000` blows first and **truncates**; a
  truncated range produces a displaced anchor without the model noticing.
- **rule 12** — `has_file` wakes on *any* attachment, and `wiki_ingest` accepts a single
  file of any type (`wiki_tools.py:507`): without this rule the subagent tries to "read"
  a PNG pasted into the channel.

Rule 8 has an **agnostic part and a concrete part**, and the distinction matters: the
principle is "the unit the reader reported", but the format actually demanded is `p.N`,
which only exists for PDFs. Other types fall to rule 10 (anchor on the file). A real
generalisation — line for `.md`, cell for a spreadsheet — waits until a second source
type is in use.

Rules 8 and 11 also correct a real defect: the default prompt tells the subagent to use
`read_pdf`, a tool it **does not receive** (`final_tools=[]`, `wiki_tools.py:213`). That
**produces no failed call**: in the smoke test the subagent simply ignored the
instruction and went straight to `read_file` (zero occurrences of `read_pdf` in the log).
The prompt is wrong and harmless; rules 8 and 11 are what start telling the truth.

### 5.3 The papers channel  *(configuration)*

Written in **two layers**, using the composition `compose.py` already implements: prose
with `<key>_append` adds to what the layer above settled, rather than replacing it.

```yaml
scopes:
  # layer 1 — base behaviour, every Slack conversation
  - match: {channel: slack}
    delivery:
      prompt: |
        Answer directly and cite your sources.

  # layer 2 — this conversation is a papers library
  - match:
      channel: slack
      chat:    "<PAPERS_CHANNEL_ID>"
    delivery:
      mode: [mention, has_file]
      mid_turn: queue          # see below — the `cancel` default kills the ingest
      prompt_append: |
        <INGESTING · ANSWERING · SHOWING THE LIBRARY · CONSTRAINTS>
```

The prompt body is kept in the live config rather than duplicated here, because it has
been edited repeatedly and a copy in this document would drift. Its four sections are:
**INGESTING** (when and how to call `wiki_ingest`), **ANSWERING** (search, search
language, anchors, answer directly), **SHOWING THE LIBRARY** (the tree) and
**CONSTRAINTS** (frozen library, no bash). It is written in English; see §14.

`mode: [mention, has_file]` is the minimum pair: `has_file` wakes on the PDF upload,
`mention` allows asking.

**`mid_turn: queue` is not optional.** The default is `cancel` (`scopes/schema.py:123` —
*"cancel is first because it is the default"*). During the ~5 minutes of an ingest, **any
message from another person in the thread cancels the turn**; and because the manifest
only records on success (`wiki_tools.py:340`), the next attempt starts from nothing. In a
channel where people comment, that is close to guaranteed. `queue` holds the message
until the session goes idle; Slack implements all three mechanisms.

**`delivery.prompt` is spliced into the user's message text**, not into the system
prompt: `slack_connect.py:10498` does `text = "\n\n".join([text, *appended])`. The
channel's instruction therefore arrives as user text on every triggered turn — which
matters both for how it is written (it is instruction, not persona) and for the per-turn
cost.

`chat` is **scalar** (`schema.py:899` refuses any non-string value), so each papers
channel needs its own scope with the same `prompt_append` copied. With one channel that
does not hurt; with several, it is the repetition §10.2 solves.

### 5.4 Hybrid search  *(publication + credential)*

**This section changed completely from v1.** v1 declared `memory.extraPaths` pointing at
the wiki; that does not work, because the key feeds a manager the agent does not use
(§3.1).

The index the agent consults is the `lite` kernel's, and it scans
`<agent workspace>/memory/*.md` — flat, no recursion. So the wiki has to be **published**
there.

**The publication step — in code, not by prompt.** v3 of this spec told the agent to
mirror the pages via `prompt_append`. **That does not work on Slack**, for two verified
reasons:

- the model **does not know where the workspace is**: the directory section is injected
  only for the `tui`/`web`/`ws_client` channels (`runtime_prompt_rail.py:325`);
- copying would need `bash cp` from a directory **outside** the workspace, which passes
  through the `file_guard` and on Slack becomes an **approval button mid-turn**. The demo
  would hang on a click.

Since `wiki_tools.py` is already being edited for the §5.1 mitigations, publication
becomes ~5 lines there: after `[Success]`, copy `wiki/*.md` into
`get_agent_workspace_dir()/memory/wiki__*.md`. That removes the risk §8 marked as "high"
and makes S1 ("no manual intervention") true.

The mirroring is file by file:

    <WIKI_ROOT>/.llm_wiki/wiki/*.md   →   <agent workspace>/memory/wiki__*.md

- file by file, **not** the directory: the scan is `os.listdir` (`lite/internal.py:80`);
- the `wiki__` prefix keeps the pages from colliding with conversation memory and makes
  them easy to clean up;
- **copy, never `mv` or a symlink**: the watcher has no `on_moved` handler
  (`lite/manager.py:778`), so a moved file is not reindexed;
- events in the **first second** after start-up are ignored, and there is **no periodic
  sync** fallback if the watcher fails (`lite/config.py:52`). If publication happens
  right after a restart, force a fresh write or restart the session.

Who runs it: `wiki_ingest` itself, at the end of a successful ingestion.

**Credential.** The three variables in `~/.jiuwenswarm/config/.env`: `EMBED_API_KEY`,
`EMBED_API_BASE`, `EMBED_MODEL`. They reach the kernel via `config.yaml` →
`interface_deep.py:6938`. Without them the `MemoryRail` is **still created** (it only
logs a warning) and search falls back to **pure BM25** — it works, but it is not hybrid.

> Note: the direct env fallback inside jiuwenswarm reads `EMBED_BASE`/`EMBED_BASE_URL`
> (`embeddings.py:49`), different names from the ones `config.yaml` uses. Filling the
> three in `.env` is the correct path; do not rely on the fallback.

**Recorded debt:** the right fix is for `lite/manager.py:954` to pass `extra_paths` to
`list_memory_files` — two lines, but inside the `openjiuwen` pinned at `61becb17`. It
would require a fork or a dependency upgrade, out of reach in two days. See §10.3.

## 6. Demo script

**Pre-rehearsal (Thursday):** ingest three papers with overlapping subject matter.
~7-9 min each (measured), so ~25 min — **not viable live**. The wiki arrives ready on
Friday.

1. Show the library: the tree from `index.md`, grouped into Entities / Concepts /
   Sources / Transversal pages.
2. Open a page and show the `[[fonte: … p.N]]` anchors with their quotes.
3. Ask a pointed question in the channel → answer via `memory_search`, with anchors.
4. **Check it**: open the PDF at the cited page and compare against the quote.
   This is the climax — it is what "pointer" means.
5. Ask a comparative question ("what is MetaSkill's strength against the other two?") →
   an answer that spans three sources with anchors from all of them.

**Deliberate cuts, and why:**

| Cut | Why |
|---|---|
| Live ingest of a fourth paper | 7-9 minutes of silence in front of an audience. SHA-256 dedup would also demand a paper never ingested before, and a misconfigured `mid_turn` would cancel the turn |
| Write-back during answers | `wiki_query` writes to the wiki (`wiki_tools.py:352`); a corpus that changes while you rehearse cannot be rehearsed. Frozen for the demo — see §13 |

## 7. Success criteria

| # | Criterion | How to verify |
|---|---|---|
| S1 | A PDF in the channel becomes wiki pages **and is published to the index** with no manual step | post one and watch. Only true with publication in code (§5.4) |
| S2 | ≥ 90% of substantive claims carry an anchor | sample **3 pages**, count substantive claims by hand (the denominator) and anchored ones (the numerator). `grep -c` alone does not measure this: there is no automatic denominator |
| S3 | Anchors are correct | check 5 samples against the PDF |
| S4 | `memory_search` returns wiki pages **after publication (§5.4)** | there is no CLI for the `lite` index; check with Python's `sqlite3` against `~/.jiuwenswarm/agent/workspace/memory/memory.db` (`select count(*) from files where path like '%wiki__%'`) |
| S5 | The channel's answer cites anchors | inspection |
| S6 | Ingesting one paper takes < 8 min | stopwatch |

**S4 is the criterion that fails the PoC deterministically** if the publication step
(§5.4) is skipped: without it `memory_search` never sees the wiki, and step 3 of the demo
falls back to `wiki_query` — which works, but is slow and is not search.

**S3 is the criterion that can fail probabilistically.** If the model invents page
numbers the pointer loses its reason to exist — and since that is a prompt instruction
rather than a guarantee, it has to be measured, not assumed.

## 8. Risks

Resolved rows are struck through rather than deleted, so the reasoning survives.

| Risk | Prob. | Mitigation |
|---|---|---|
| Model invents pages (S3) | medium | measure at the rehearsal; if it fails, fall back to file+section anchors |
| ~~No `EMBED_*`~~ | — | **resolved**: `baai/bge-m3` via OpenRouter, 1024 dims (§12) |
| ~~Slack without credentials~~ | — | **resolved**: app authorised, seven scopes granted, bot in the channel |
| Three papers ≈ 25 min of ingest | certain | pre-rehearsal on Thursday |
| 120 s attachment budget | medium | one PDF per message |
| Divergence from upstream (§5.1) | low | two lines, documented |
| ~~Publication step forgotten → S4 fails~~ | — | **resolved**: publication runs inside `wiki_ingest` |
| `read_file` truncates a range at 25k tokens → displaced anchor | medium | rule 11: ranges ≤ 5 pages |
| Anchor lands in a chunk separate from its claim | medium | rule 8: anchor on the same line |
| ~~`wiki_query` writes without reading `AGENT.md`~~ | — | **resolved**: the write-back is bound to `AGENT.md`, and frozen for the demo (§13) |
| A "live" fourth paper already ingested → `[Skipped]: Deduplicated` | medium | keep an un-ingested paper aside |
| ~~Slack app missing `files:read` or the message subscription~~ | — | **resolved**: verified against the API |
| `has_file` wakes on any attachment (image, screenshot) | medium | rule 12 of `AGENT.md` plus the extension guard in `prompt_append` |
| ~~`wiki_ingest` reads any file outside the permission rail~~ | — | **resolved**: `source` restricted to session uploads and the workspace |
| ~~`mid_turn` default `cancel` kills a multi-minute ingest~~ | — | **resolved**: `mid_turn: queue` in the scope |
| **46 `NoneType … 'id'` errors in the smoke test** (see §8.1) | **unknown** | still unexplained; the ingests through Slack succeeded regardless |
| Publication right after a restart lands in the watcher's dead window | low | force a fresh write; see §5.4 |
| ~~`config.yaml` at 0644~~ | — | **resolved**: every secret-bearing file at 0600 |

### 8.1 The smoke test was not clean — and every measurement came from it

The ingest that produced the reference wiki ended in `[Success]`, but its log carries
**46 occurrences of `'NoneType' object has no attribute 'id'`** — on every `write_file`,
`edit_file` and `bash`. The files **were** written (the wiki exists and is good), but the
model saw failure and spent iterations re-reading to check.

Consequences that need saying out loud:

- the **294 s** measured and the behaviour observed ("ignored `read_pdf`", "read in four
  ranges") come from that degraded run. They are not a trustworthy baseline;
- the likely cause is a harness difference between the standalone runner used and the
  real Slack path — **but nobody verified that**;
- the subagent **improvises when it cannot satisfy a rule**: with `bash` failing, it
  invented the `log.md` date (using the arXiv one) instead of stopping, and read ranges
  of ten pages while describing them as three blocks. That is the direct prognosis for
  rules 8-12: expect **partial conformance**, not obedience.

**Later:** the ingests run through Slack succeeded and produced good pages, so the errors
did not block the result. They remain unexplained, and the honest reading is that the
timings in this document are upper bounds from a degraded path.

## 9. Open questions — all answered on 2026-09-10

| # | Question | Answer |
|---|---|---|
| 1 | `<WIKI_ROOT>` | `/home/renan/.jiuwenswarm/agent/workspace/wikis/papers` — **inside** the agent workspace, so file access there does not trip the external-directory guard. It must be a literal absolute path in the YAML: on Slack the model never receives the directory section (`runtime_prompt_rail.py:325`) |
| 2 | Papers channel id | `C0C0T5WBAMU`, a **private** channel — hence `groups:history`/`groups:read` and the `message.groups` subscription rather than the `channels:*` pair |
| 3 | Which papers | SARSI (`2607.12254v2`), AREX (`2607.21461v2`), MetaSkill-Evolve (`2607.05297v1`) |
| 4 | Embeddings endpoint | `baai/bge-m3` through OpenRouter — see §12 |

Notes on the live config (`~/.jiuwenswarm/config/config.yaml`):

- there was **no `scopes:` block**; §5.3 was written from scratch rather than edited;
- naming the papers channel in a `delivery` scope **already exempts it** from
  `allowed_channel_ids` (`compose.py:228`), so the bot answers there without touching
  that list. Desired behaviour — recorded so it does not surprise anyone;
- a synchronous ingest of several minutes fits comfortably: the bound on one turn is
  3600 s (`_TURN_INITIATOR_TIMEOUT_SECONDS`);
- **`models.defaults` holds 11 entries and all 11 carry `is_default: true`.** The code
  takes the first (`wiki_tools.py:368`); changing model means reordering or clearing the
  flags, not just replacing a key;
- **hygiene:** `config.yaml`, `.env` and every `.bak*`/`.pre-align` are now at `0600`.
  When restoring Slack tokens, **do not restore a whole backup** — it carries other
  `models.defaults` differences; copy only the two lines.

## 9.1 Result — verified through Slack on 2026-09-10

The PoC ran end to end through the real channel.

| Criterion | Result |
|---|---|
| S1 PDF becomes wiki with no manual step | ✅ |
| S2 anchors | ✅ **1117** anchors across 45 pages (three papers) |
| S3 anchors correct | ✅ samples checked against the PDF |
| S4 the index serves the wiki | ✅ published and searchable |
| S5 the channel's answer carries anchors | ✅ |
| S6 ingest < 8 min | ⚠️ ~7-9 min per paper |

    papers  1 → 2 → 3      pages  18 → 30 → 45      anchors  229 → 556 → 1117

### The library compounded, and that is the main finding

The second paper did **not** merely add pages: it rewrote the first paper's.
`sarsi-agents.md` gained eight references to AREX, `recursive-self-improvement.md` nine,
and `evaluation-framework.md` four — not as decoration, but as a conceptual distinction.
The agent noticed the two papers use *"recursive self-improvement"* for different things
and wrote a section saying so on the concept's page.

With the third paper the effect strengthened: asked for MetaSkill-Evolve's strength
against the other two, the answer built a three-way comparison in which each cell was
anchored, and its caveats used one paper as a ruler on another — SARSI's H1 hypothesis
(equal-compute efficiency) applied to MetaSkill's evaluation, noting it is not actually
tested. Nobody wrote that anywhere; it was derived across three sources.

This is Karpathy's thesis observed — *"the cross-references are already there"* — and it
is the strongest argument that this is not RAG: a RAG would retrieve both passages and
leave the contradiction to the reader.

**Consequence for the demo:** the climax is not the search. It is the comparison across
sources, and the page that exists only because a second paper arrived.

### A reported defect that does NOT exist — the anchor extension

An earlier version of this section recorded that the second paper's anchors truncated the
extension (`.df` instead of `.pdf`). **That was wrong, and the error belonged to the
checker, not the model.**

The measurement had piped the anchors through `sed 's/p[0-9]*//'` to group them by file.
`p[0-9]*` matches a `p` followed by **zero** or more digits, so it matched the `p` in
`.pdf` and removed it. The `.df` was manufactured by the verification command itself.

Correct count across the whole wiki:

    567 anchors reading ".pdf p"        0 anchors with a broken extension

Recorded as a method note: **a conformance measurement needs checking as carefully as the
artefact it measures.** A badly written `sed` nearly bought a nine-minute re-ingest per
paper to fix nothing. It was not the last such error either — see §14.

## 10. Evolutions

### 10.1 Hybrid search inside `wiki_query`

The PoC puts hybrid search **beside** `wiki_query`. The next step is to put it
**inside**: `wiki_query` would retrieve the relevant pages before opening them, instead
of listing the directory and reading everything. §11-A1 applied the cheap half of this
as a prompt change; the full version needs the tool to hold an index of its own, which
means modifying an upstream tool and stays out of the PoC.

### 10.2 `channel_type` — classes of conversation instead of ids

§5.3 writes the papers prompt against a **conversation id**. Because `chat` is scalar, N
channels of the same kind need N scopes with the same `prompt_append` copied, and a
reader of the config sees a list of opaque ids rather than an intention.

The project already has the right pattern on the people axis: `people:` and `roles:` are
sibling blocks resolving a name (`admin`) into a set of ids, and `role` matches against
that. The code is explicit about the role of a role — it *"carries no permissions of its
own: it names a set of people"* (D8). `channel_type` would be the analogue for
conversations:

```yaml
channel_types:                     # new block, sibling to people:/roles:
  papers:  [C_PAPERS_1, C_PAPERS_2]
  support: [C_SUP_1]

scopes:
  - match: {channel: slack, channel_type: papers}
    delivery: {prompt_append: "<wiki + papers>"}
```

Gains: one definition per kind, readable vocabulary, and the existing layered composition
starts applying per class.

What it would require, and why it stays out of the PoC:

- a new axis in the schema, with its own resolution and validation;
- a declaration in each supporting connector's `ChannelCapabilities`;
- semantics still undecided: can a channel hold two types? do types compose? what happens
  when two types disagree about the same key?
- **and a security consequence that is not obvious.** `scoped_chats` documents that on
  Slack the ids named in `delivery`/`agent` scopes **exempt the channel from
  `allowed_channel_ids`** — naming a conversation in a scope is already opt-in for the
  bot to answer there. A badly designed `channel_type` would open several channels at
  once without anyone noticing, which is exactly the direction (D4) this design forbids.

Deserves its own spec.

### 10.3 `extra_paths` in the `lite` kernel

§5.4 publishes the wiki by copying files into `<agent workspace>/memory/`. That is a
workaround. The right fix is for `lite/manager.py:954` to pass `extra_paths` to
`list_memory_files` — the parameter **already exists** in the signature
(`lite/internal.py:35`) and is simply never passed. Alongside it, the extras scan's
`os.listdir` should become `os.walk` (`lite/internal.py:80`), so that pointing at a
directory actually works.

Two lines, but inside the `openjiuwen` pinned at `61becb17`: it needs an upstream
contribution or a fork of the dependency. After that, §5.4 collapses into a config key
and the publication step disappears.

### 10.4 Clickable anchors — a hyperlink to the PDF page

Today `[[fonte: paper.pdf p7]]` is text. The natural evolution is to make it a link that
opens the PDF **at the cited page**, turning the double-check from "open the file and
search" into a click.

**What is already solved.** The connector converts Markdown links into Slack `mrkdwn` on
its own — `_normalize_slack_mrkdwn` (`slack_connect.py:11916`). Verified:

    IN : [paper.pdf p.7](http://host/x.pdf#page=7)
    OUT: <http://host/x.pdf#page=7|paper.pdf p.7>

So **there is no need to emit `<url|text>` syntax**; the agent writing Markdown is enough.

**What rule 8 would have to change.** The double bracket defeats the regex and passes
through untouched:

    IN : [[fonte: x.pdf p7]](http://host/x.pdf#page=7)
    OUT: (unchanged — not a link)

The anchor would have to become a single bracket: `[fonte: x.pdf p.7](url)`.

**The missing link: where the URL comes from.** Three options, none free.

| Option | Viable? | Note |
|---|---|---|
| Slack permalink | ❌ | Slack's viewer does not honour `#page=N` |
| The file's `url_private` | ⚠️ | opens in the browser under the user's session; `#page` only works if the browser renders the PDF inline. **This is the right path**: the file is already hosted, under the channel's access control |
| Local HTTP server over `sources/` | ✅ | trivial (`python3 -m http.server`), but the URL is `localhost` — good for a screen-shared demo, not for others to click |

**And a metadata chain that does not exist today.** `wiki_ingest` copies the PDF into
`sources/` under a hash prefix and **discards its Slack origin**: `slack_file_id` stays in
the attachment record (`slack_connect.py:11375`) and never reaches the wiki. A link based
on `url_private` would need it carried the whole way — connector → prompt →
`wiki_ingest` parameter → page frontmatter → anchor. That is the bulk of the work, not
the link.

**Why it stays out of the PoC.** Nothing here is hard in isolation, but it is four
coupled changes (anchor format, metadata chain, file hosting, and re-ingesting pages
already written in the old format) and the demo already delivers verification without
them — a textual pointer already names file and page, which is what the thesis requires.
The click is comfort, not proof.

---

## 11. Improvements, measured on the real wiki

Structural health on 2026-09-10, at two papers: 30 pages, 221 KB, 257 edges, **0 orphans,
0 broken links**, 567 anchors. The structure is sound; what follows is about scale and
precision. (At three papers: 45 pages, 1117 anchors.)

| # | Point | Cost | State |
|---|---|---|---|
| A1 | `wiki_query` read the whole wiki | prompt | ✅ **applied** |
| A2 | `index.md`/`log.md` polluted the index | 1 rule | ✅ **applied** |
| A3 | chunks at the ceiling split claim from quote | config | open |
| A4 | the hash prefix in anchors | metadata | open |
| A5 | nobody runs `wiki_lint` | operations | open |

### A1 — `wiki_query` did not scale  ✅ applied

It was told only to *"answer strictly based on `wiki/`"*, with no method, so it listed the
directory and read all of it: **221 KB at two papers**. Because the library is designed to
compound, the naive version degrades with every source — the opposite of what the design
promises.

The prompt now orders the work: `index.md` first (it is the catalogue, one line per page),
`grep` next for the question's own terms, and only then whole pages, and only the ones
that survived. The write-back remains, but is now **bound to `schema/AGENT.md`** — the
earlier wording allowed a page to be written without the anchors every other page carries.

This is **not** the hybrid search of §10.1, which remains the complete solution; it is the
correction that fitted without touching the architecture.

### A2 — navigation pages out of the index  ✅ applied

`index.md` and `log.md` name **every** topic in the wiki, so they match nearly any query
and drown the page that actually answers it. Worse: **17 of the 26 anchorless chunks were
theirs** — a retrieval landing on one leaves the agent with nothing to cite.

Neither is published any more, and stale copies are removed (nothing else would delete
them).

### A3 — chunking sits at the ceiling

    245 chunks · mean 963 chars · max 1067

The chunks are pressed against the limit. A claim with a 25-word blockquote takes a good
share of that, so the claim+quote pair runs a real risk of being split — which is exactly
what rule 8 ("anchor on the same line") tries to avoid, and rule 8 only protects within a
line, not within a chunk.

`memory.chunking` is configurable. Raising it to ~1500 would give room. **It needs
measuring first**: a larger chunk lowers retrieval precision, so this is a trade-off, not
an obvious improvement. It also interacts with the encoder — dense retrieval prefers
smaller, coherent chunks while BM25 tolerates larger ones — so changing chunking and the
embedding model at the same time makes it impossible to attribute the result.

### A4 — the hash prefix in anchors

    [[fonte: 45e4144f_2607.21461v2.pdf p10]]

The `sha256[:8]_` comes from how `wiki_ingest` names the file in `sources/`. It
disambiguates, but it pollutes every answer and prevents a clean link. Storing the
original name in the source page's frontmatter and anchoring by that solves it — and it
is the **same metadata chain** §10.4 needs, so the two should be done together.

### A5 — `wiki_lint` never runs

It was deliberately left out of the tool registration (§5.1). But it is what detects
orphans and broken links — today both are zero **by luck, not by verification**. At ten
papers that degrades silently. Decide whether it becomes a periodic step or a manual one.

---

## 12. Embeddings — from optional to required

§11 and earlier versions of this section treated embeddings as polish, with
prompt-driven query expansion as the cheap alternative. **Both positions were wrong**, and
what undid them was a simple observation: *it should not be a problem to ask in
Portuguese, Chinese or German about an English library, and it should not take an ad-hoc
method per language.*

### The measurement that forced the change

Ten questions about the two-paper library, scoring whether the right page reaches the
BM25 top five (using the kernel's own `split_query_tokens` and `build_fts_query`):

    baseline, literal question in Portuguese:  3/10

And the failure mode is worse than vocabulary mismatch:

    'o que e AREX?'  →  FTS: '"que" OR "AREX"'  →  arex.md does not even reach the top 5

A Portuguese stopword sank the easiest possible question about the corpus, because the
`trigram` tokeniser matches **substrings**: `que` matches *frequency*, *sequence*,
*technique*.

### Why query expansion is not the answer

In a multilingual setting, expanding the query by prompt **is translation in disguise**:
it depends on the model guessing the document's vocabulary on every question, it fails
silently, and it needs a new rule per language. That is precisely the ad-hoc method to
avoid.

**Lexical retrieval is monolingual by construction.** No substring is shared between
"escalável" and "scalable"; no tokeniser setting fixes that. The kernel itself concedes
the problem and solves it one language at a time:

- `lite/internal.py:182` — *"Short tokens (<3 chars, e.g. 2-char Chinese) can't match trigram"*
- `lite/manager.py:584` — the `unicode61 → trigram` migration, made because the previous one *"never matched Chinese queries"*
- `JiuwenMemory` configures `tokenizer: jieba` **specifically** for Chinese BM25

A dedicated tokeniser per language does not scale.

### The decision

**A multilingual embedding is the only principled mechanism**, and it becomes a product
requirement — not a PoC one, since the PoC already worked on BM25 for English questions
with literal vocabulary. A multilingual encoder puts "escalável", "scalable" and "可扩展"
near each other in vector space because it was trained to; that is not a heuristic.

| Method | Cross-lingual? |
|---|---|
| BM25 / trigram | ❌ by construction |
| doc2query, SPLADE | ❌ they expand terms within one language |
| Query expansion | ⚠️ only through implicit translation — ad-hoc |
| **Multilingual embedding** | ✅ **by construction** |
| Hybrid (dense + BM25) | ✅ the dense half carries the cross-lingual load |

**The wiki (§11-A/doc2query) still holds and is not redundant with this.** It solves a
different problem: global questions, which no embedding retrieves when nobody wrote the
comparison. It is what answered "where do the two papers disagree". The two are
complementary — the wiki compounds knowledge, the encoder crosses languages.

### Configuration — applied on 2026-09-10

OpenRouter now serves OpenAI-compatible embeddings at `/api/v1/embeddings`, which drops
straight into the three existing variables:

```
EMBED_API_BASE=https://openrouter.ai/api/v1
EMBED_API_KEY=<OpenRouter key>
EMBED_MODEL=baai/bge-m3
```

**The dimension needs no configuration:** `_ensure_vector_table` rebuilds the vector
table under the model's dimension on first write, and there is DROP logic for when the
model changes (`lite/manager.py:427-487`). Verified live: 1024 dimensions, and the index
meta records `{"provider": "openai_compatible", "model": "baai/bge-m3", "chunkTokens":
256, "ftsTrigram": true, "vectorDims": 1024}`.

### Models worth testing, in order

| Model | Dim | Context | Price /M | Why |
|---|---|---|---|---|
| **`baai/bge-m3`** | 1024 | 8K | **$0.01** | the open reference for multilingual retrieval (100+ languages), cheapest tier, modest dimension. **In use.** |
| `qwen/qwen3-embedding-8b` | — | 33K | $0.01 | same price, far longer context; strong multilingual |
| `openai/text-embedding-3-large` | — | 8K | $0.13 | a known control, 13× the price and not the best cross-lingual |

Our chunks run ~963 chars, so 8K of context is ample. Indexing the whole library (245
chunks, ~60k tokens) costs cents in any of them.

### The result

Same ten questions, scored by an **independent LLM judge** against page *content* rather
than fixed page names — the names change on every re-ingest, which broke an earlier
measurement (see §14).

| | Score |
|---|---|
| BM25 only, question in Portuguese | 3/10 |
| + `bge-m3`, question in Portuguese | 7/10 |
| + `bge-m3`, question in English | **9/10** |

> **Measured with a judge that read 500 characters per page.** The median wiki page is
> ~7.5k, so the judge ruled on 7% of it. The row below re-runs the same questions with the
> judge reading the whole page; §14 records the defect. The three-paper numbers above are
> kept as measured rather than restated, because the corpus has also changed since.

Re-measured on 2026-09-10 against the four-paper corpus, with both the judge window and the
two shared-code defects of §15 fixed:

| | Score |
|---|---|
| hybrid, question in Portuguese | 9/10 |
| hybrid, question in English | **10/10** |

The gain is **not** attributable to the §15 fixes, and the isolation run says so: holding
the corpus and the code fixed and varying only the judge window gives 9/10 → 10/10 in
English and 9/10 → 9/10 in Portuguese. The English point came from the instrument. What
the §15 fixes bought is measured elsewhere — the lexical channel went from 0/10 to 8/10
questions returning any hit at all — and this ten-question set cannot show it, because it
was already saturated by the dense channel. A set that would show it is one of exact
identifiers: acronyms, model names, version numbers, author names. That set does not exist
yet.

The whole gain from the encoder landed on the lexical questions — 1/5 → 5/5 — the ones
that should always have worked. That confirms the diagnosis: the problem was the
question's language, not divergent vocabulary.

### And a rule that came out of the last row

Asking in English scores 9/10 against 7/10 in Portuguese, and the mechanism is visible in
the scores: the four transversal pages sat at ~0.52 in the dense ranking, all but tied,
so any additional signal decides. An English query makes the FTS contribute **signal**
instead of noise, and `_merge_hybrid_results` fuses two good rankings instead of carrying
one.

This is not the ad-hoc method rejected above. It is a single rule derived from a fact
about the system — *the library has a language; query it in that language* — and it does
not change per user language or per domain. Formally it is query normalisation to the
index language, standard practice in cross-lingual retrieval. It lives in the channel's
`prompt_append` as SEARCH LANGUAGE, and it separates the query's language from the
answer's: the user is answered in the language they asked in.

Caveats worth keeping: n=10, so two questions of difference may be noise — the
qualitative signal (C3 and L5 turning) is more trustworthy than the number. It assumes a
monolingual library; with mixed-language sources the rule would have to name which
language, or query in several.

## 13. The library that grows when it is queried

Observed on 2026-09-10, in the live channel. Asking *"where do the two papers disagree?"*
produced the expected answer **and wrote a new page**:

    divergence-coverage-gaps.md   5529 bytes   9 anchors   registered in index.md
    wiki: 35 → 37 pages

Not a defect. It is §10.1 working: `wiki_query` keeps its write-back, and the write-back
is bound to `schema/AGENT.md`, so the page came out anchored and indexed like any other.
It is the *"valuable analyses can be filed back into the wiki"* of Karpathy's pattern,
happening without anyone asking.

Before that, the ingestion had already produced `divergence-inventory.md` — an audit of
the wiki's own `disagreements.md`, recording that the page **heads five divergences while
the index and the log count six**, and that a cross-reference points at a section the page
does not carry. The wiki documented its own defect instead of hiding it, which is rule 13
applied at a level nobody specified: not to a missing value, but to the consistency of the
library.

### Why this is the design's most valuable property

A RAG answers and forgets. Here, **the question is a contribution**: it leaves an analysis
in the library that the next question can find. The library grows not only by ingestion
but by use, which is the difference between an index and a second brain.

### And why it was switched off for the demo

Two faces:

- **For:** you can show the tree before and after the same question and watch the library
  grow live. That is a hard argument to refute.
- **Against:** the artefact stops being stable. A question rehearsed on Thursday can
  answer differently on Friday, because the wiki changed during the rehearsal. And there
  is a publication mismatch: pages written by a query **do not** pass through
  `publish_wiki_pages`, which only runs inside `wiki_ingest` — so they exist in the wiki
  and stay **invisible to search** until the next ingestion.

Predictability won for the demo. The channel's `prompt_append` gained a FROZEN LIBRARY
rule: when answering, never write to the wiki, never create or edit pages, never touch
`index.md` or `log.md`; if a gap or inconsistency is noticed while answering, **report it
in the answer** instead of fixing it on disk.

Note that the rule **keeps the finding and drops only the writing**: the agent is still
required to report gaps, it just does not repair them itself. That is how the answer about
the divergences could say "the page heads five, the index counts six" and still deliver
the sixth.

### What to do after the demo

1. **Turn the write-back back on** — it is the property, not the defect.
2. **Publish what a query writes.** The mismatch above is a real bug: call
   `publish_wiki_pages` at the end of a `wiki_query` that wrote. Until that exists, an
   analysis filed by a query is invisible to the next search, which cancels half the value
   of filing it. The two audit pages were published by hand on 2026-09-10.
3. **Decide whether the library needs versions.** If asking changes the wiki, "yesterday's
   wiki" and "today's wiki" are different objects, and nothing today tells them apart. See
   §10.4 and the versioning discussion in §11-A4.

---

## 14. Method note: the instrument was wrong four times

Four measurements reported a problem the system did not have, three of them in one day. In
every case the artefact was fine and the tool measuring it was broken. Recorded because
four is a pattern, not luck.

| What was measured | The bug | What it reported |
|---|---|---|
| Anchor format | `sed 's/p[0-9]*//'` matches a `p` with **zero** digits, eating the `p` in `.pdf` | a `.df` defect that does not exist |
| Retrieval, by page name | the labels were the old wiki's; re-ingestion renamed the pages | a regression from 7/10 to 3/10 |
| Retrieval, by LLM judge | `max_tokens=5` on a reasoning model, which spent them on `reasoning_content` and returned an empty `content` | 0/10, judging even an exactly-matching page as NO |
| Retrieval, by LLM judge | the judge was shown the first 500 characters of a page; the median page is ~7.5k | a MISS on "how many parameters does AREX-Base have?", whose answer sits at character 649 of one retrieved page and 2503 of another — a correct retrieval scored as a failure |

The general lesson: **measuring an AI system with AI tools requires verifying the
instrument before believing the number** — and verifying it against a case whose answer is
known in advance. The third bug was caught precisely because a judge that says NO to
`autonomous-context-updating.md` for "what is Autonomous Context Updating?" is impossible,
not merely surprising.

The practical consequence for this document: every number here carries how it was measured,
and the retracted ones stay retracted in place rather than being deleted.

Two of the four would have cost real work: the first nearly bought a nine-minute
re-ingest per paper to fix nothing; the second nearly attributed a regression to the
`AGENT.md` rules that had just been added.

The fourth is the one worth generalising from, because it did not look like a bug at all.
It reported a plausible number — one hard factual question missed out of ten — for a year
and a half of reading, and nothing about it invited suspicion. It was caught only by
asking a different question of the same MISS: *is this a retrieval failure or a corpus
gap?* Grepping the corpus answered neither, and answered a third: the page was retrieved
and the fact was in it. **A plausible failure deserves the same scrutiny as an implausible
one**; the third bug was caught in minutes because 0/10 is absurd, and the fourth survived
because 9/10 is not.

---

## 15. Three defects in shared code, found by building on it

None of these are in this PoC. All three are in `openjiuwen`'s `memory/lite`, which
`MemoryRail` and `CodingMemoryRail` also use, so they affect every deployment and not just
the papers channel. Each is a one-line fix. Two are corrected on this branch by patch
modules under `jiuwenswarm/server/runtime/memory/`, following the repository's existing
`*_patch.py` convention; the third is left alone because it is cosmetic.

> **Verified still present upstream on 2026-09-10.** In `agent-core`
> (`gitcode.com/openJiuwen/agent-core`) on branch `develop` at `4b3860b5`, all three are
> byte-identical to what we run. In `jiuwenswarm` on branch `develop` at `029c76a64`, the
> rank-to-score inversion is also present, because `jiuwenswarm` carries its own copy of
> that function in `agents/harness/common/memory/internal.py` — and that copy is live code,
> imported by `interface.py`, `memory_tools.py`, `agent_ws_server.py`, `memory_rpc.py` and
> `memory_forbidden_rail.py`. So 15.2 has two independent instances in the product.
> Defects 15.1 and 15.3 are `agent-core`-only: `jiuwenswarm`'s vendored copy predates the
> trigram migration and that `_index_file` branch.
>
> **Upgrading the dependency would fix none of them.** The pin `61becb17` is an ancestor of
> `agent-core` HEAD and 104 commits behind it, but `memory/lite/manager.py` and
> `memory/lite/internal.py` have received **zero** commits in that interval, and the files
> installed in our venv hash identically to HEAD.
>
> Two separate reports are therefore needed: one against `agent-core` `develop` covering all
> three, and one against `jiuwenswarm` `develop` covering 15.2 alone — the latter with a fix
> ready, since it is the same one-line change already made on
> `second-brain-slack-poc-renan`.

### 15.1 The BM25 index emptied itself on every restart

`_ensure_schema` creates `chunks_fts` with `tokenize='trigram'`. SQLite stores the CREATE
statement verbatim, so the quotes are part of the stored text. `_fts_table_is_legacy` then
tests for the unquoted `tokenize=trigram`, never matches, and reports the table it just
created as pre-migration — so it is dropped, on every startup.

That alone would be survivable: `initialize()` force-reindexes after a migration. But the
reindex is gated on `_needs_fts_migration_reindex`, true only while `meta` lacks
`ftsTrigram`. So the first startup is correct — drop, reindex, record the flag — and every
startup after it drops the table and declines to refill it. `chunks` still holds every row,
because the incremental sync skips files whose hash has not changed.

Nothing raises. Hybrid search keeps answering from the vector channel alone, so the symptom
is degraded quality rather than an error, and the only trace is an INFO line that reads like
a one-time migration notice and in fact repeats every boot — nine times in one day here.
It also survives every test that creates a temp database and initialises once: the bug
needs a *persisted* database and a *restart*.

Measured cost on this corpus: 482 chunks indexed, 0 rows in the FTS table, and 0 of 10
questions returning any lexical hit. After repair, 482 and 8 of 10.

### 15.2 The lexical ranking was inverted

Credit for this one to Miguel, who found it while writing up the second brain data-flow
document and worked around it locally rather than fixing shared code.

FTS5 reports match quality in `rank` as a negative number where more negative is better —
which is why the kernel's own keyword query says `ORDER BY rank` with no `DESC`. But
`bm25_rank_to_score` mapped it with `1 / (1 + |rank|)`, so the score *fell* as the match
improved, disagreeing with the SQL ordering of the very rows it scored.

Not cosmetic. `search` merges `0.7 * vector + 0.3 * text` and keeps rows scoring at least
`min_score`, 0.7 by default. On this corpus the best keyword hit for one query sat at rank
−3.7968: it scored 0.2085 and contributed 0.06, so a document also scoring 0.80 on the
vector channel landed at 0.623 and was filtered out — *because* its keyword match was good.
Corrected, the same row scores 0.7915, contributes 0.24, and the document lands at 0.797
and is kept.

The symptom had been seen upstream and read as a property of BM25 rather than a defect: the
kernel comments that pure-keyword scores "commonly land 0.1-0.3 after the rank->score
transform" and compensates with a separate, lower `keywordMinScore` floor. That range is
exactly what an inverted transform yields for good matches. **A workaround that fits the
symptom is evidence the cause was never located.**

One trap in fixing it: `manager.py` imports the function by name at module level, so
patching only `internal` leaves the manager calling the original and the patch silently
does nothing. Both bindings must be rebound. `jiuwenswarm` also carries its own copy of the
same function, with the same defect; that one is fixed directly.

### 15.3 An error message hidden behind an UnboundLocalError

`_index_file` logs `no available sys_operation when _index_file` and then falls through to
use `content`, which was never assigned, so the caller sees
`cannot access local variable 'content'` instead of the real cause. Cosmetic, and left
alone — but it cost time during 15.1, because the useful message was buried under the
useless one.

### 15.4 TODO — orphan FTS rows, mechanism confirmed, impact unmeasured

**Not a finding yet.** The mechanism is established; whether it costs anything is not,
and this is recorded so that it gets measured rather than assumed either way.

Observed on the live corpus after five ingests: `chunks` holds **584** rows while
`chunks_fts_docsize` holds **1393** — **809 orphans, 58% of the table**. The share grows
with every re-index, and every ingest re-indexes every page it rewrote.

The mechanism, confirmed by direct test rather than by reading: when a file is re-indexed,
`manager.py` issues `DELETE FROM chunks_fts WHERE path = ?` before writing the new chunks.
On a contentless FTS5 table (`content=''`) the column values are not stored, so `path` is
NULL for every row and the `WHERE` matches nothing. The delete is a **silent no-op** — it
raises nothing and removes nothing. Deleting by `rowid` works; deleting by any column does
not.

The kernel knows orphans exist and guards the read path, restricting matches to rowids
still present in `chunks`, with the comment: *"without this filter, high-scoring orphans
fill the LIMIT before the real hits surface — returning []"*. So **no orphan content
reaches an answer**, and that is why this is a TODO and not a defect.

What is unmeasured is the effect on *ranking*. BM25 scores a document against corpus
statistics — inverse document frequency and average document length — and SQLite computes
those over the whole FTS table, orphans included. With 58% of the table being text that no
longer exists, every IDF in the index is computed against a corpus that is nearly
two-thirds stale. A term that has since been removed from the wiki still suppresses its own
weight; a page rewritten five times still votes five times on the average length. Whether
that moves anything past the point where ranking changes is exactly the open question.

**How to settle it.** Take the current database, copy it, and rebuild the copy from scratch
so the FTS holds only live rows. Run the same ten questions against both through
`measure_judge_en.py`, and compare not just the hit count but the *ordering* of the top-5
for each question. If the orderings are identical, the orphans are inert and this entry can
be closed as harmless. If they differ, the fix is one line — delete by rowid, which the
kernel already does correctly elsewhere in the same function — and it belongs upstream with
the other three.

Do this measurement *before* proposing the fix, not after. Four instruments in this project
have already reported problems the system did not have (§14), and "58% of the table is
garbage" is exactly the kind of alarming-sounding number that invites a fix nobody verified
was needed.

### What these have in common

All three are silent. None raises where it fails, none logs above INFO, and each presents
as something other than itself: a migration notice, a property of BM25, a variable error.
The subsystem they live in is the one every agent's memory runs through, and its failures
degrade quality rather than break, which is the hardest kind to notice from the outside —
and the reason they were found by *building* on the subsystem rather than by reading it.
