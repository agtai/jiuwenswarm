# Second Brain PoC — a papers channel on Slack

Date: 2026-09-09 · Branch: `feat/second-brain-slack-poc` (base `55c3c3a85`)
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

## 12. Embeddings — de opcional a requisito

A §11 e as versões anteriores desta seção tratavam embeddings como acabamento, e a
alternativa barata seria expansão de consulta por prompt. **Ambas as posições estavam
erradas**, e o que as derrubou foi uma observação simples: *não deveria ser problema
perguntar em português, chinês ou alemão sobre um acervo em inglês, nem deveria ser
preciso um método ad-hoc por idioma.*

### A medição que motivou a mudança

Dez perguntas sobre o acervo de dois papers, medindo se a página correta aparece no
top-5 do ranking BM25 (usando `split_query_tokens` e `build_fts_query` reais):

    baseline, pergunta literal em português:  3/10

E o modo de falha não é vocabulário divergente — é pior:

    'o que e AREX?'  →  FTS: '"que" OR "AREX"'  →  arex.md nem entra no top-5

Uma stopword portuguesa afundou a pergunta mais fácil possível sobre o corpus, porque o
tokenizador `trigram` casa **substring**: `que` casa *frequency*, *sequence*, *technique*.

### Por que expansão de consulta não é a resposta

Num cenário multilíngue, expandir a consulta por prompt **é tradução disfarçada**:
depende do modelo acertar o vocabulário do documento a cada pergunta, falha em silêncio,
e precisa de uma regra nova por idioma. É exatamente o método ad-hoc que se quer evitar.

**Busca lexical é monolíngue por construção.** Não existe substring comum entre
"escalável" e "scalable"; nenhum ajuste de tokenizador resolve isso. O próprio kernel
admite o problema e o resolve um idioma por vez:

- `lite/internal.py:182` — *"Short tokens (<3 chars, e.g. 2-char Chinese) can't match trigram"*
- `lite/manager.py:584` — migração `unicode61 → trigram` feita porque a anterior *"never matched Chinese queries"*
- `JiuwenMemory` configura `tokenizer: jieba` **especificamente** para BM25 chinês

Um tokenizador dedicado por idioma não escala.

### A decisão

**Embedding multilíngue é o único mecanismo principiado**, e passa a ser requisito do
produto — não da PoC, que já funciona em BM25 para perguntas em inglês com vocabulário
literal. Um encoder multilíngue aproxima "escalável", "scalable" e "可扩展" no espaço
vetorial porque foi treinado para isso; não é heurística.

| Método | Cross-lingual? |
|---|---|
| BM25 / trigram | ❌ por construção |
| doc2query, SPLADE | ❌ expandem termos no mesmo idioma |
| Expansão de consulta | ⚠️ só via tradução implícita — ad-hoc |
| **Embedding multilíngue** | ✅ **por construção** |
| Híbrido (denso + BM25) | ✅ o denso carrega o cross-lingual |

**A wiki (§11-A/doc2query) continua valendo e não é redundante com isso.** Ela resolve
outra coisa: perguntas globais, que nenhum embedding recupera se ninguém escreveu a
comparação. Foi o que respondeu à pergunta "onde os dois papers discordam". As duas são
complementares — a wiki compõe conhecimento, o embedding cruza idiomas.

### Como configurar

O OpenRouter passou a servir embeddings em `/api/v1/embeddings`, compatível com OpenAI,
o que encaixa direto nas três variáveis já existentes:

```
EMBED_API_BASE=https://openrouter.ai/api/v1
EMBED_API_KEY=<chave do OpenRouter>
EMBED_MODEL=baai/bge-m3
```

**A dimensão não precisa ser configurada:** `_ensure_vector_table` recria a tabela
vetorial sob a dimensão do modelo no primeiro write, e há lógica de DROP quando o modelo
muda (`lite/manager.py:427-487`).

### Modelos a testar, em ordem

| Modelo | Dim | Contexto | Preço /M | Por quê |
|---|---|---|---|---|
| **`baai/bge-m3`** | 1024 | 8K | **$0.01** | referência aberta em multilíngue (100+ idiomas), mais barato da lista, dimensão modesta |
| `qwen/qwen3-embedding-8b` | — | 33K | $0.01 | mesmo preço, contexto muito maior; multilíngue forte |
| `openai/text-embedding-3-large` | — | 8K | $0.13 | controle conhecido, 13× mais caro e não é o melhor cross-lingual |

Chunks nossos têm ~963 chars, então 8K de contexto sobra. O custo total de indexar o
acervo atual (245 chunks, ~60k tokens) é de centavos em qualquer um deles.

### Como medir

As mesmas 10 perguntas, com o baseline honesto de **3/10** já registrado. Se um encoder
multilíngue levar isso a 8–9, o número justifica a decisão — e vale para qualquer idioma
que alguém use no canal, não só português. Trocar o modelo força reindexação; medir os
três exige três reindexações do acervo (minutos, não horas).

---

## 13. O acervo que cresce ao ser consultado

Observado em 2026-09-10, no canal real. Perguntar *"onde os dois papers discordam?"*
produziu a resposta esperada **e criou uma página nova na wiki**:

    divergence-coverage-gaps.md   5529 bytes   9 âncoras   registrada no index.md
    wiki: 35 → 37 páginas

Não foi defeito. É a §10.1 funcionando: o `wiki_query` mantém o write-back, e ele está
amarrado ao `schema/AGENT.md`, então a página saiu com âncoras e entrou no índice como
qualquer outra. É o *"valuable analyses can be filed back into the wiki"* do padrão do
Karpathy, acontecendo sem ninguém pedir.

Antes disso, a ingestão já havia produzido `divergence-inventory.md` — uma auditoria da
própria `disagreements.md`, que registra que a página **encabeça cinco divergências
enquanto o índice e o log contam seis**, e que há uma referência cruzada apontando para
uma seção que a página não carrega. A wiki documentou o próprio defeito em vez de
escondê-lo, que é a regra 13 aplicada num nível que ninguém especificou: não a um valor
faltante, mas à consistência do acervo.

### Por que isto é a propriedade mais valiosa do desenho

Um RAG responde e esquece. Aqui, **a pergunta é uma contribuição**: ela deixa no acervo
uma análise que a próxima pergunta encontra. O acervo não cresce só por ingestão — cresce
por uso, que é a diferença entre um índice e um segundo cérebro.

### E por que ela foi desligada para a demo

Duas faces:

- **A favor:** dá para mostrar a árvore antes e depois da mesma pergunta e ver o acervo
  crescer ao vivo. É um argumento difícil de refutar.
- **Contra:** o artefato deixa de ser estável. Uma pergunta ensaiada na quinta pode dar
  outro resultado na sexta, porque a wiki mudou no ensaio. E há um descompasso de
  publicação: páginas criadas por consulta **não** passam pelo `publish_wiki_pages`, que
  só roda no `wiki_ingest` — então elas existem na wiki e ficam **invisíveis à busca**
  até a próxima ingestão.

Para a demo venceu a previsibilidade. O `prompt_append` do canal ganhou:

    ACERVO CONGELADO: ao RESPONDER, nunca escreva na wiki. Nao crie paginas,
    nao edite paginas existentes, nao atualize o index.md nem o log.md. Se ao
    responder voce notar uma lacuna ou inconsistencia no acervo, RELATE na
    resposta em vez de corrigi-la no disco. A wiki so muda por ingestao.

Repare que a regra **preserva o achado e descarta só a escrita**: o agente continua
obrigado a relatar lacunas, apenas não as conserta sozinho. Foi assim que a resposta
sobre as divergências pôde dizer "a página encabeça cinco, o índice conta seis" e ainda
entregar a sexta.

### O que fazer depois da demo

1. **Religar o write-back** — é a propriedade, não o defeito.
2. **Publicar o que a consulta escreve.** O descompasso acima é um bug real: chamar
   `publish_wiki_pages` também ao fim de um `wiki_query` que escreveu. Enquanto isso não
   existir, uma análise arquivada pela consulta é invisível para a busca seguinte, o que
   anula metade do valor de arquivá-la. As duas páginas de auditoria foram publicadas à
   mão em 2026-09-10 (35 publicadas de 37).
3. **Decidir se o acervo precisa de versão.** Se perguntar muda a wiki, "a wiki de
   ontem" e "a wiki de hoje" são objetos distintos, e nada hoje os distingue. Ver §10.4
   e a discussão de versionamento/tombstones na §11-A4.
