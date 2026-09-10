# Second brain (papers wiki) — data flow and storage schema

Three questions, three diagrams: what happens when a paper arrives, what is on disk
afterwards, and what happens when somebody asks a question.

Source of truth for everything below: `jiuwenswarm/agents/harness/common/tools/wiki_tools.py`,
`jiuwenswarm/server/runtime/agent_adapter/interface_deep.py` (tool registration and the
kernel patches), and the wiki's own `schema/AGENT.md`, which lives outside the repository.

This is the *compiling* half of a second brain: a model writes the artefact. A companion
document, `second-brain-architecture-miguel.md`, describes a *cataloguing* design over the
same problem, where the model writes only a summary and everything structural is derived.
Section 4 here compares them, because the two are not competitors so much as different
answers to "who is trusted to write what".

---

## 1. Ingestion — a paper arrives

A PDF posted in the papers channel becomes a conversation turn, unlike the cataloguing
design where ingestion is silent. That is deliberate and it is also the main cost: the
turn lasts minutes and the channel watches it happen.

```mermaid
flowchart TD
    POST(["someone posts a .pdf in the papers channel"])
    POST --> TRIG{"does the scope's<br/>mode match?"}
    TRIG -->|"no — plain chatter"| IGNORE["the bot stays quiet<br/><i>mode is [mention, has_file],<br/>so the channel is not a chatroom</i>"]
    TRIG -->|"yes — has_file"| SAVE["the connector saves the attachment<br/>into the session's uploads directory"]

    SAVE --> AGENT["the main agent takes the turn<br/><i>mid_turn: queue — a message arriving<br/>during the ingest waits instead of<br/>cancelling it</i>"]
    AGENT --> CALL["calls wiki_ingest(source=…, workspace=…)"]

    CALL --> GUARD{"is the path under<br/>sessions/ or workspace/?"}
    GUARD -->|no| REFUSE["refuse<br/><i>wiki_ingest copies with shutil, so it never<br/>passes the permission rail that guards<br/>read_file; the guard is the rail</i>"]
    GUARD -->|yes| EXT{".pdf / .md / .txt?"}
    EXT -->|no| REFUSE2["refuse and say why"]
    EXT -->|yes| SEEN{"sha256 already<br/>in the manifest?"}

    SEEN -->|yes| DUP["skip<br/><i>recognised by content: a rename or a<br/>reshare is the same paper</i>"]
    SEEN -->|no| KEEP["copy into sources/ as<br/>&lt;sha8&gt;_&lt;filename&gt;.pdf<br/><i>immutable from here on</i>"]

    KEEP --> SUB["hand the job to the maintainer subagent<br/><i>its own DeepAgent, its own workspace,<br/>its own session — not the channel's</i>"]

    SUB --> RULES["it reads schema/AGENT.md<br/><i>17 rules; the product lives here</i>"]
    RULES --> DISCOVER["reads wiki/index.md, greps for the<br/>source's key terms, and opens in full<br/>ONLY the pages that matched"]
    DISCOVER --> READ["reads the PDF in page ranges<br/><i>every claim it will write is in context<br/>together with the page it came from</i>"]

    READ --> WRITE["writes and rewrites topic pages<br/><i>including the four transversal pages,<br/>so an old paper's page changes when<br/>a new one arrives</i>"]
    WRITE --> LINK["cross-links them and updates<br/>wiki/index.md and wiki/log.md"]

    LINK --> OK{"did the subagent<br/>report an error?"}
    OK -->|yes| NOREC["do not record the hash<br/><i>so a retry starts clean</i>"]
    OK -->|no| REC["record sha256 in manifest.json"]
    REC --> PUB["copy every page into the agent's<br/>memory directory as wiki__&lt;name&gt;.md"]
    PUB --> IDX["the memory index picks them up"]
    IDX --> DONE(["the agent says the ingest finished"])
```

**Three things worth knowing.**

- **The model writes the artefact, not a summary of it.** This is the whole bet. The
  maintainer does not describe the paper; it compiles the paper into topic pages that
  another paper can later contradict. The library therefore *compounds*: ingesting the
  second paper rewrote the first's pages to distinguish two senses of "recursive
  self-improvement", and the third produced a three-way comparison using the first's H1
  hypothesis as a ruler. Nothing in the design asked for that; it falls out of letting a
  writer own the pages.
- **Trust is bought with rules, not with structure.** Every substantive claim carries
  `[[fonte: <file> p.N]]` on the same line, with a ≤25-word blockquote of the source
  underneath, quoted as extracted — hyphenation artefacts and all. Rule 10 forbids
  inventing a page when a read returned no locator; rule 13 forbids inventing any value to
  fill a gap. Current state: 1276 anchors across 52 pages, 0 broken links. The weakness is
  structural: these are *instructions*, and an instruction can be disobeyed. See §4.
- **The manifest only records success.** A failed ingest leaves no entry, so a retry is
  clean — but a *rejection* leaves no entry either, so a re-posted PNG pays for its refusal
  every time. The cataloguing design memoises refusals; this one does not.

---

## 2. Storage — what is on disk

Two roots, and the second one is the surprise: the wiki root is also the maintainer
subagent's own agent workspace, so `.llm_wiki/` carries `AGENT.md`, `memory/`, `todo/` and
`skills/` alongside the three directories the design cares about.

```mermaid
flowchart TD
    R["&lt;workspace&gt;/wikis/papers/.llm_wiki/"]

    R --> SRC["sources/<br/><i>immutable; never indexed</i>"]
    R --> WIKI["wiki/<br/><i>the artefact — agent-owned</i>"]
    R --> SCH["schema/AGENT.md<br/><i>17 rules; not code</i>"]
    R --> OWN["(the subagent's own workspace:<br/>memory/, todo/, skills/, context/ …)"]

    SRC --> SRCF["&lt;sha8&gt;_&lt;filename&gt;.pdf"]
    SRC --> MAN["manifest.json<br/><i>one entry per sha256</i>"]

    WIKI --> TOPIC["&lt;topic&gt;.md × 50<br/><i>published to the index</i>"]
    WIKI --> IDX2["index.md<br/><i>the catalogue — read, never published</i>"]
    WIKI --> LOG["log.md<br/><i>append-only timeline — never published</i>"]

    M["&lt;workspace&gt;/memory/<br/><i>the only indexed directory</i>"]
    TOPIC -.->|"copyfile at the end<br/>of a successful ingest"| MEMF
    M --> MEMF["wiki__&lt;topic&gt;.md × 50"]
    M --> DB["memory.db<br/>sqlite + WAL"]
```

> **`index.md` and `log.md` are deliberately not published.** They are navigation and
> bookkeeping, and indexing them puts a catalogue of every topic into competition with the
> topics themselves — a query for any subject matches the index line about it. They are read
> directly by path when the channel asks to see the library.

> **`copyfile`, never a move or a symlink.** The index's watcher has no `on_moved` handler,
> so a moved file is not reindexed; and `copyfile` rather than `copy2` so the copy gets a
> fresh mtime and change detection fires.

### `manifest.json` — one entry per set of bytes

```mermaid
erDiagram
    SOURCE_ENTRY {
        string sha256 PK "the manifest key"
        string name "the filename as posted"
        string destination "sources/<sha8>_<name>"
        string ingested_at "UTC, seconds precision"
    }
```

Keyed by sha256 and written whole. Deliberately thin: it answers "have we seen these
bytes?" and nothing else. Everything a reader would want — what the paper claims, where a
claim came from — lives in `wiki/`, because that is the artefact. Note what is *absent*
and what that costs: no `slack_permalink`, no poster, no `posted_at`. A page can point at
page 11 of a PDF but not back at the message that brought it.

### `wiki/<topic>.md` — the indexed artefact

```
# <Title>

<one paragraph saying what this page covers>

## <a self-describing section heading>        ← rule 14: the index is built
                                                 from these without reading the page
<claim> [[fonte: bdfaa68d_1706.03762v7.pdf p.3]]
> the source text, ≤25 words, quoted as extracted
```

Four of the pages are **transversal** — `limitations-and-gaps.md`, `cost-and-scale.md`,
`disagreements.md`, `open-questions.md` — mandated by rules 15-17 and rewritten on every
ingest. They are what answers a question no single paper's page can ("where do these
disagree?", "what does this cost to run?"), and they are the mechanism by which the library
compounds rather than accumulates.

### `memory.db` — the kernel's `lite` schema

Unchanged from the kernel: `files`, `chunks` (~256-token chunks, 32 overlap),
`chunks_fts` (FTS5 trigram, BM25), `chunks_vec` (sqlite-vec), `embedding_cache`, `meta`.
Chunks, not pages, are the retrieval unit, so one page occupies several rows.

Two defects in that shared code were found by building on it and are patched from
`jiuwenswarm/server/runtime/memory/`: the FTS table was dropped on every restart and never
refilled, and the BM25 rank-to-score transform was inverted. Spec §15 has both.

---

## 3. Retrieval — a question arrives

There is no rail here. Retrieval is whatever the channel prompt tells the agent to do, and
the agent has two tools with very different costs.

```mermaid
flowchart TD
    Q(["@bot asks a question in the channel"]) --> SCOPE["the scope's prompt_append applies<br/><i>layered under a broad slack prompt;<br/>a scope can only narrow, never widen</i>"]

    SCOPE --> LANG["SEARCH LANGUAGE:<br/>phrase the query in English<br/><i>the library is English; the user is<br/>answered in their own language</i>"]

    LANG --> PICK{"does it need the<br/>whole corpus?"}
    PICK -->|no| MS["memory_search<br/><i>hybrid over the chunks of wiki__*.md</i>"]
    PICK -->|yes| WQ["wiki_query<br/><i>spawns the maintainer subagent again</i>"]

    MS --> HYB["0.7 × vector + 0.3 × BM25<br/>kept above min_score"]
    HYB --> PAGES["the matching pages"]

    WQ --> RECIPE["index.md → grep → read only<br/>the pages that matched"]
    RECIPE --> RO{"allow_write?"}
    RO -->|"false (default)"| READONLY["read-only: report gaps<br/>in the answer, never on disk"]
    RO -->|true| FILE["may file the answer<br/>as a new page"]
    READONLY --> PAGES
    FILE --> PAGES

    PAGES --> ANS["answer, citing [[fonte: …]] anchors"]
    ANS --> FROZEN["FROZEN LIBRARY:<br/>answering never writes<br/><i>the wiki changes only by ingestion</i>"]
```

### What the query is matched against

**The chunks of the wiki pages** — never the PDF. The PDF is read only during ingestion.
A reader who wants the source follows an anchor by hand; there is no drill-down tool that
seeks into the original.

### The two tools, and when each is right

| | `memory_search` | `wiki_query` |
|---|---|---|
| cost | one search | a whole subagent session, minutes |
| sees | the chunks that matched | index, grep, then whole pages |
| good for | "what is X?", "which benchmarks?" | "where do these disagree?" |
| writes | never | only if `allow_write=True` |

`allow_write` defaults to false, and that default was bought with a bug: the write-back was
unconditional, and the channel's FROZEN LIBRARY rule could not prevent it, because that rule
addresses the *main agent* while the write happened inside `wiki_query`'s subagent — a layer
the channel prompt never reaches. A question duly created a page, registered it in
`index.md` and appended to `log.md`. **A rule cannot be enforced from a layer that does not
control where the action happens**; the flag moved the decision to the caller, where it can
be seen.

### Containment

There is none, and this is the clearest gap. Papers are untrusted content arriving from a
shared channel, their text is read into the maintainer's context during ingestion, and their
content ends up inside wiki pages that are later injected into the answering agent's
context. Nothing fences that content, marks it as data, or neutralises instruction-shaped
text inside it. The cataloguing design's `<<<BRAIN_DOC>>>` fences — with `<<<`/`>>>` in the
body replaced by look-alike characters that cannot close a fence — are the reference for
what this needs.

---

## 4. The trade against the cataloguing design

Same problem, opposite answer to "who writes what".

| | this (compiling) | cataloguing |
|---|---|---|
| what the model writes | the pages, including cross-source synthesis | a summary, nothing else |
| provenance | rules the model must obey | derived from the file and from Slack |
| cross-document layer | four transversal pages, rewritten per ingest | none |
| ingestion cost | minutes, and a visible channel turn | seconds, two emoji |
| re-posting a rejected file | pays again | memoised |
| untrusted content | unfenced | fenced, and declared twice |

The honest summary: **the cataloguing design cannot send a reader to the wrong page; this
one can be told not to.** Rules 8-13 exist precisely because the failure is possible, and
the failure has been observed — the maintainer invented a `log.md` date when it could not
run `date`, and the library once claimed eight authors while anchoring four. Both were
caught, one by the agent itself reporting the gap rather than filling it.

What this design buys for that price is the thing the other cannot do: an artefact that
answers a question no single document contains, and that gets better as documents arrive
rather than merely larger. Whether that is worth an unfenced, model-written corpus depends
entirely on who is posting the documents.

The two compose, in principle: cataloguing as a cheap, safe, trustworthy ingestion layer,
compiling as a synthesis layer over it. Neither document has designed that seam.

---

## Debugging

| Question | Where to look |
|---|---|
| What is in the corpus? | `wiki/index.md`, and `sources/manifest.json` for what was ingested when |
| Did a page reach the search index? | `ls <workspace>/memory/wiki__*.md`, then count rows in `memory.db` |
| Is the lexical channel alive? | `chunks` vs `chunks_fts_docsize` in `memory.db` — if the second is 0, see spec §15.1 |
| Are the anchors intact? | `grep -c "\[\[fonte:" wiki/*.md`, and check that every `](*.md)` target exists |
| Why did an ingest take so long? | `~/.jiuwenswarm/logs/run/jiuwen.log`; a `timed out after 300.0s` means the patch of §15.1 is not in your checkout |
| What did the maintainer actually do? | `wiki/log.md` — one entry per ingest, capped at 30 lines, with the rules it could not satisfy |
