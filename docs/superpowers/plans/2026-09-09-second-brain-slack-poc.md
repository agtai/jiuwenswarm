# Second Brain PoC (Slack papers channel) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a PDF posted in a Slack channel become wiki pages anchored to the source and searchable through the agent's `memory_search`, with no manual intervention.

**Architecture:** Four changes. Two in `wiki_tools.py` (restrict where `wiki_ingest` may read from, and publish the pages into the agent's memory directory at the end of a successful ingest); one in `interface_deep.py` (register `wiki_ingest`/`wiki_query`, partially reverting `e4fae3061`); and two configuration ones (pre-seed the papers workspace's `schema/AGENT.md` with the anchoring rules, and write the channel scope).

**Tech Stack:** Python 3.11, pytest + monkeypatch, `openjiuwen` pinned at commit `61becb17`, uv.

**Spec:** `docs/superpowers/specs/2026-09-09-second-brain-slack-poc-design.md`

## Global Constraints

- Working branch: `second-brain-slack-poc-renan`; worktree
  `/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/wiki-smoke`.
- Run everything with the worktree's venv: `.venv/bin/python`, `.venv/bin/pytest`.
- Do **not** touch anything under `.venv/` (that is the pinned `openjiuwen`). Every change
  goes in `jiuwenswarm/`.
- New tests go in `tests/unit_tests/agents/`, following the pattern of
  `test_wiki_tools_runtime_config.py` (pytest, `monkeypatch`, `SimpleNamespace`).
- Repository style: docstrings in English, comments explaining *why*.
- One commit per task, message in English, conventional prefix (`feat:`/`fix:`/`test:`).
- **Tasks 1-3 and 5 do not depend on Slack.** Only Task 6 needs the tokens.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `jiuwenswarm/agents/harness/common/tools/wiki_tools.py` | wiki tools; gains the source guard and publication | Modify |
| `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py` | agent tool registration | Modify (`:7716-7722`) |
| `tests/unit_tests/agents/test_wiki_ingest_source_guard.py` | source guard tests | Create |
| `tests/unit_tests/agents/test_wiki_publish.py` | publication tests | Create |
| `tests/unit_tests/agents/test_shared_tool_registration.py` | registration test | Create |
| `~/.jiuwenswarm/wikis/papers/.llm_wiki/schema/AGENT.md` | maintainer rules (outside the repo) | Create |
| `~/.jiuwenswarm/config/config.yaml` | `scopes:` block (outside the repo) | Modify |

---

### Task 1: Restrict where `wiki_ingest` may read from

Closes the hole in §5.1: today `wiki_ingest` accepts any absolute path, validates no
extension in the single-file branch, and its directory branch does `glob("**/*")` from any
root -- `wiki_ingest(source="~")` would ingest every `.md` the user owns.

**Files:**
- Modify: `jiuwenswarm/agents/harness/common/tools/wiki_tools.py`
- Test: `tests/unit_tests/agents/test_wiki_ingest_source_guard.py`

**Interfaces:**
- Consumes: `get_agent_workspace_dir()` and `get_agent_sessions_dir()` from `jiuwenswarm.common.utils`.
- Produces: `INGESTIBLE_SUFFIXES: tuple[str, ...]`, `source_is_allowed(path: Path) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit_tests/agents/test_wiki_ingest_source_guard.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from jiuwenswarm.agents.harness.common.tools import wiki_tools


@pytest.fixture
def fake_roots(tmp_path, monkeypatch):
    """Point both allowed roots at a tmp dir so the guard is testable."""
    sessions = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    sessions.mkdir()
    workspace.mkdir()
    monkeypatch.setattr(wiki_tools, "get_agent_sessions_dir", lambda: sessions)
    monkeypatch.setattr(wiki_tools, "get_agent_workspace_dir", lambda: workspace)
    return sessions, workspace


def test_allows_a_file_under_the_sessions_dir(fake_roots):
    sessions, _ = fake_roots
    uploaded = sessions / "s1" / "uploads" / "paper.pdf"
    uploaded.parent.mkdir(parents=True)
    uploaded.write_text("x")
    assert wiki_tools.source_is_allowed(uploaded) is True


def test_allows_a_file_under_the_agent_workspace(fake_roots):
    _, workspace = fake_roots
    doc = workspace / "notes.md"
    doc.write_text("x")
    assert wiki_tools.source_is_allowed(doc) is True


def test_refuses_a_file_outside_both_roots(fake_roots, tmp_path):
    secret = tmp_path / "config" / ".env"
    secret.parent.mkdir(parents=True)
    secret.write_text("API_KEY=x")
    assert wiki_tools.source_is_allowed(secret) is False


def test_refuses_traversal_out_of_an_allowed_root(fake_roots):
    sessions, _ = fake_roots
    escape = sessions / ".." / "elsewhere.md"
    assert wiki_tools.source_is_allowed(escape) is False


def test_ingestible_suffixes_are_the_three_document_types():
    assert wiki_tools.INGESTIBLE_SUFFIXES == (".pdf", ".md", ".txt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/wiki-smoke && .venv/bin/pytest tests/unit_tests/agents/test_wiki_ingest_source_guard.py -v`

Expected: FAIL — `AttributeError: module 'wiki_tools' has no attribute 'source_is_allowed'`

- [ ] **Step 3: Write minimal implementation**

In `wiki_tools.py:37`, **replace** the line

```python
from jiuwenswarm.common.utils import get_agent_workspace_dir
```

with

```python
from jiuwenswarm.common.utils import get_agent_sessions_dir, get_agent_workspace_dir
```

(`shutil` is already imported on line 11; `Path` on line 7.)

Right below `DEFAULT_WIKI_DIR = ".llm_wiki"`:

```python
#: The document types the wiki maintainer can actually read. The directory branch of
#: ``wiki_ingest`` already filtered on these; the single-file branch did not, which is
#: how a PNG dropped in a Slack channel reached the subagent.
INGESTIBLE_SUFFIXES: tuple[str, ...] = (".pdf", ".md", ".txt")


def source_is_allowed(path: Path) -> bool:
    """Whether ``wiki_ingest`` may read ``path``.

    The tool copies with ``shutil`` rather than through ``SysOperation``, so it does not
    pass the permission rail that guards ``read_file``. Without a guard here, an agent in
    any conversation could name ``~/.jiuwenswarm/config/.env`` and have the maintainer
    subagent summarise it into a wiki page. Two roots are allowed because they are the two
    places a document legitimately arrives: the session upload directory, where the Slack
    connector saves attachments, and the agent workspace.

    Resolved before comparing so ``..`` cannot walk out of an allowed root.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False
    roots = (get_agent_sessions_dir().resolve(), get_agent_workspace_dir().resolve())
    return any(resolved == root or root in resolved.parents for root in roots)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit_tests/agents/test_wiki_ingest_source_guard.py -v`
Expected: 5 passed

- [ ] **Step 5: Wire the guard into `wiki_ingest`**

In `wiki_ingest`, right after the `if not src_path.exists(): ...` block:

```python
        if not source_is_allowed(src_path):
            return (
                f"Error: wiki_ingest only reads documents under the agent's session "
                f"uploads or workspace directory; {source} is outside both."
            )
```

And in the single-file branch, replace:

```python
        else:
            targets.append(src_path)
```

with:

```python
        else:
            if src_path.suffix.lower() not in INGESTIBLE_SUFFIXES:
                return (
                    f"Error: wiki_ingest handles {', '.join(INGESTIBLE_SUFFIXES)}; "
                    f"got '{src_path.suffix or 'no extension'}'."
                )
            targets.append(src_path)
```

And in the directory branch, replace `for ext in (".pdf", ".md", ".txt"):` with
`for ext in INGESTIBLE_SUFFIXES:` -- one list, not two.

> **Coverage of spec §5.1, and what is left out.** This task implements mitigations
> (1) restrict `source` and (2) validate the extension. The other two are deliberately
> out of scope for the PoC:
>
> - **(3) use `sys_operation.fs()` for the copy** -- this is the architecturally correct
>   fix (it puts the read back behind the permission rail), but with `source` restricted
>   to the two directories the agent can already read, the marginal gain over 2 days is
>   small and the risk of disturbing the copy path is real. **Record as debt.**
> - **(4) deny by scope** -- only makes sense once other channels exist; it is opt-out and
>   does not replace (1).
>
> If Task 1 gets cut for time, **the demo must not go live**: without it any Slack
> conversation can make `wiki_ingest` read an arbitrary file.

- [ ] **Step 6: Run the full wiki test file to check nothing regressed**

Run: `.venv/bin/pytest tests/unit_tests/agents/ -k wiki -v`
Expected: all pass (includes `test_wiki_tools_runtime_config.py`)

- [ ] **Step 7: Commit**

```bash
git add jiuwenswarm/agents/harness/common/tools/wiki_tools.py \
        tests/unit_tests/agents/test_wiki_ingest_source_guard.py
git commit -m "fix(wiki): only ingest documents from the session uploads or workspace

wiki_ingest copies with shutil rather than through SysOperation, so it
never passed the permission rail that guards read_file. Any conversation
could name a path outside the workspace and have the maintainer subagent
summarise it. The single-file branch also validated no extension, while
the directory branch did -- one list now serves both."
```

---

### Task 2: Publish the wiki pages into the agent's index

Without this `memory_search` never sees the wiki and the demo loses search (S4). Spec
§5.4 explains why this is code and not prompt: in Slack the model is not given the
workspace path, and a `cp` from outside it would trigger an approval mid-turn.

**Files:**
- Modify: `jiuwenswarm/agents/harness/common/tools/wiki_tools.py`
- Test: `tests/unit_tests/agents/test_wiki_publish.py`

**Interfaces:**
- Consumes: `get_agent_workspace_dir()`.
- Produces: `WIKI_PUBLISH_PREFIX: str`, `publish_wiki_pages(wiki_dir: Path, memory_dir: Path) -> list[Path]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit_tests/agents/test_wiki_publish.py`:

```python
from __future__ import annotations

from pathlib import Path

from jiuwenswarm.agents.harness.common.tools import wiki_tools


def test_publishes_every_markdown_page_with_the_prefix(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text("# Index")
    (wiki / "sparse_attention.md").write_text("# Sparse attention")
    memory = tmp_path / "memory"

    published = wiki_tools.publish_wiki_pages(wiki, memory)

    names = sorted(p.name for p in published)
    assert names == ["wiki__index.md", "wiki__sparse_attention.md"]
    assert (memory / "wiki__index.md").read_text() == "# Index"


def test_creates_the_memory_directory_when_absent(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "a.md").write_text("a")
    memory = tmp_path / "does" / "not" / "exist"

    wiki_tools.publish_wiki_pages(wiki, memory)

    assert (memory / "wiki__a.md").is_file()


def test_republishing_overwrites_the_previous_copy(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    page = wiki / "a.md"
    page.write_text("first")
    memory = tmp_path / "memory"
    wiki_tools.publish_wiki_pages(wiki, memory)

    page.write_text("second")
    wiki_tools.publish_wiki_pages(wiki, memory)

    assert (memory / "wiki__a.md").read_text() == "second"


def test_ignores_non_markdown_and_subdirectories(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "sub").mkdir(parents=True)
    (wiki / "a.md").write_text("a")
    (wiki / "notes.txt").write_text("t")
    (wiki / "sub" / "b.md").write_text("b")
    memory = tmp_path / "memory"

    published = wiki_tools.publish_wiki_pages(wiki, memory)

    assert [p.name for p in published] == ["wiki__a.md"]


def test_returns_empty_list_when_the_wiki_directory_is_missing(tmp_path):
    assert wiki_tools.publish_wiki_pages(tmp_path / "nope", tmp_path / "memory") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit_tests/agents/test_wiki_publish.py -v`
Expected: FAIL — `AttributeError: module 'wiki_tools' has no attribute 'publish_wiki_pages'`

- [ ] **Step 3: Write minimal implementation**

In `wiki_tools.py`, below `source_is_allowed`:

```python
#: Prefix for a wiki page copied into the agent's memory directory. It keeps the pages
#: apart from conversation memory, makes them greppable, and cannot collide with the
#: dated session files the memory index also stores.
WIKI_PUBLISH_PREFIX = "wiki__"


def publish_wiki_pages(wiki_dir: Path, memory_dir: Path) -> list[Path]:
    """Copy each wiki page into the agent's memory directory, and say which.

    The memory index the agent searches is the kernel's ``lite`` manager, and it scans
    ``<workspace>/memory`` with ``os.listdir`` -- flat, no recursion, any ``.md``. So the
    pages have to be published there file by file rather than by pointing a config key at
    the wiki: the key that would have done that (``memory.extraPaths``) feeds a different
    manager, which the agent never consults.

    ``copyfile`` rather than ``copy2`` so the copy gets a fresh mtime, and never a move or
    a symlink: the index's watcher has no ``on_moved`` handler, so a moved file is not
    reindexed.
    """
    if not wiki_dir.is_dir():
        return []
    memory_dir.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    for page in sorted(wiki_dir.glob("*.md")):
        if not page.is_file():
            continue
        target = memory_dir / f"{WIKI_PUBLISH_PREFIX}{page.name}"
        shutil.copyfile(page, target)
        published.append(target)
    return published
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit_tests/agents/test_wiki_publish.py -v`
Expected: 5 passed

- [ ] **Step 5: Call it at the end of a successful ingest**

In `LLMWiki.ingest`, replace the last two lines:

```python
        await self._manifest.record(sha256=sha256, name=source_path.name, destination=destination)
        return result
```

with:

```python
        await self._manifest.record(sha256=sha256, name=source_path.name, destination=destination)

        # Publish before returning, so the pages are searchable by the time the agent
        # answers in the channel. Failure here must not fail the ingest: the wiki is
        # written and correct either way, and a missing publication is recoverable by
        # ingesting again or copying by hand.
        try:
            published = publish_wiki_pages(self.wiki_dir, get_agent_workspace_dir() / "memory")
            logger.info("[LLMWiki] published %d wiki page(s) to the memory index", len(published))
        except Exception as exc:
            logger.warning("[LLMWiki] publishing wiki pages failed: %s", exc)

        return result
```

- [ ] **Step 6: Run the whole wiki test suite**

Run: `.venv/bin/pytest tests/unit_tests/agents/ -k wiki -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add jiuwenswarm/agents/harness/common/tools/wiki_tools.py \
        tests/unit_tests/agents/test_wiki_publish.py
git commit -m "feat(wiki): publish wiki pages into the agent's memory index

The index the agent searches is the kernel's lite manager, which scans
<workspace>/memory flat for .md files. memory.extraPaths, which looks
like the way to add the wiki, feeds a different manager that the agent
never consults -- so the pages are copied there instead, at the end of a
successful ingest. Publication failure is logged, never fatal: the wiki
is correct either way."
```

---

### Task 3: Register `wiki_ingest` and `wiki_query` in the runtime

Without this the agent has no such tools -- they are defined and never registered, since
`e4fae3061`. `wiki_lint` stays out: the demo does not need it.

**Files:**
- Modify: `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py` (`:7716-7722`)
- Test: `tests/unit_tests/agents/test_shared_tool_registration.py`

**Interfaces:**
- Produces: `SHARED_AGENT_TOOLS: tuple` in the `interface_deep` module.

- [ ] **Step 1: Write the failing test**

Create `tests/unit_tests/agents/test_shared_tool_registration.py`:

```python
from __future__ import annotations

from jiuwenswarm.server.runtime.agent_adapter import interface_deep


def _names(tools):
    return sorted(t.card.name for t in tools)


def test_shared_tools_include_the_wiki_and_pdf_tools():
    assert _names(interface_deep.SHARED_AGENT_TOOLS) == [
        "read_pdf",
        "wiki_ingest",
        "wiki_query",
    ]


def test_wiki_lint_is_deliberately_not_registered():
    # It only lints an existing wiki and the PoC does not use it; keeping it out
    # keeps three tool cards off every agent's prompt instead of four.
    assert "wiki_lint" not in _names(interface_deep.SHARED_AGENT_TOOLS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit_tests/agents/test_shared_tool_registration.py -v`
Expected: FAIL — `AttributeError: module 'interface_deep' has no attribute 'SHARED_AGENT_TOOLS'`

- [ ] **Step 3: Write minimal implementation**

In `interface_deep.py`, **right below** line 334
(`from jiuwenswarm.agents.harness.common.tools.pdf_tools import read_pdf`), add:

```python
from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_ingest, wiki_query
```

At module level, right below that import:

```python
#: Tools every agent shares. wiki_ingest and wiki_query were unregistered upstream in
#: e4fae3061 as part of trimming prompt surface, not because of any defect; the papers
#: channel needs them, and a scope cannot grant a tool (it can only narrow), so they come
#: back globally and the channel's prompt is what puts them to use. wiki_lint stays out:
#: the PoC never lints.
SHARED_AGENT_TOOLS = (wiki_ingest, wiki_query, read_pdf)
```

And replace the loop in `_get_tool_cards`:

```python
        for wtool in [read_pdf]:
            self._register_shared_tool(wtool)
            tool_cards.append(wtool.card)
```

with:

```python
        for wtool in SHARED_AGENT_TOOLS:
            self._register_shared_tool(wtool)
            tool_cards.append(wtool.card)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit_tests/agents/test_shared_tool_registration.py -v`
Expected: 2 passed

- [ ] **Step 5: Check the adapter still imports and nothing else broke**

Run: `.venv/bin/pytest tests/unit_tests/agentserver/ -x -q`
Expected: no new failures (note the pre-existing ones, if any, before changing anything)

- [ ] **Step 6: Commit**

```bash
git add jiuwenswarm/server/runtime/agent_adapter/interface_deep.py \
        tests/unit_tests/agents/test_shared_tool_registration.py
git commit -m "feat(runtime): register wiki_ingest and wiki_query as shared tools

Partially reverts e4fae3061, which unregistered the three wiki tools
while trimming prompt surface. The papers channel needs ingest and
query, and no scope can grant a tool -- scopes only narrow -- so
registration is global and the channel prompt is what scopes the
behaviour. wiki_lint stays out. The list becomes a module constant so it
is testable."
```

---

### Task 4: Pre-seed the papers workspace's `schema/AGENT.md`

`ensure_initialized` writes the file **only if it does not exist**, so seeding it before
the first ingest is the way to supply the anchoring rules without touching the code
default.

**Files:**
- Create: `~/.jiuwenswarm/wikis/papers/.llm_wiki/schema/AGENT.md` (outside the repo)

- [ ] **Step 1: Create the directory**

```bash
mkdir -p ~/.jiuwenswarm/wikis/papers/.llm_wiki/schema
```

- [ ] **Step 2: Write the file**

```bash
cat > ~/.jiuwenswarm/wikis/papers/.llm_wiki/schema/AGENT.md <<'EOF'
# Wiki Maintainer Rules
1. Never modify files inside `sources/`.
2. All pages you generate MUST be saved directly inside the `wiki/` directory root.
3. You must maintain a `wiki/index.md` listing all topics.
4. You must maintain a `wiki/log.md` with an append-only timeline of ingestions.
5. Break concepts down into modular topic pages.
6. Make heavy use of markdown links to interconnect pages within `wiki/`.
7. DO NOT create subdirectories (like `wiki/entity/`). Save all files in the `wiki/` root.
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
EOF
```

A note on rule 13: in the smoke test the subagent invented the `log.md` date (it used
arXiv's) when it could not run `date`. The rule exists to make that behaviour explicitly
forbidden, since it is the same pattern that would produce an invented anchor.

- [ ] **Step 3: Verify it is not overwritten**

```bash
cd /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/wiki-smoke
md5sum ~/.jiuwenswarm/wikis/papers/.llm_wiki/schema/AGENT.md
```
Keep the hash; check it again after Task 6 -- it must be identical.

---

### Task 5: CLI rehearsal (no Slack)

Proves Tasks 1-3 end to end before any credential dependency.

**Files:**
- Create: `/home/renan/second_brain_rehearsal.py` (throwaway script, outside the repo)

- [ ] **Step 1: Write the rehearsal script**

```bash
cat > /home/renan/second_brain_rehearsal.py <<'EOF'
import asyncio, os, time
from pathlib import Path
for line in Path("/home/renan/.jiuwenswarm/config/.env").read_text(errors="replace").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k, v)

from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_ingest
from jiuwenswarm.common.utils import get_agent_sessions_dir

WS = "/home/renan/.jiuwenswarm/wikis/papers"
PDF = "/mnt/c/Users/admin/Documents/rsi_articles/2607.12254v2.pdf"

# Copy the paper where the guard allows reading from, mimicking a Slack upload.
uploads = get_agent_sessions_dir() / "rehearsal" / "uploads"
uploads.mkdir(parents=True, exist_ok=True)
staged = uploads / Path(PDF).name
if not staged.exists():
    staged.write_bytes(Path(PDF).read_bytes())

async def main():
    # wiki_ingest is a LocalFunction; the coroutine is on ._func
    t0 = time.time()
    out = await wiki_ingest._func(source=str(staged), workspace=WS, force=False)
    print(f"\n[rehearsal] {time.time() - t0:.0f}s\n{out}")

asyncio.run(main())
EOF
```

- [ ] **Step 2: Run it**

Run: `cd /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/wiki-smoke && .venv/bin/python /home/renan/second_brain_rehearsal.py 2>&1 | tail -30`
Expected: `[Success]`

- [ ] **Step 3: Check for the degraded-harness errors (spec §8.1)**

Run: `.venv/bin/python /home/renan/second_brain_rehearsal.py 2>&1 | grep -c "NoneType.*attribute 'id'"`
Expected: **0**. If it is not 0, the errors did not come from the throwaway runner and
§8.1 must be reopened before trusting any measurement.

- [ ] **Step 4: Verify the guard refuses a file outside the allowed roots**

```bash
.venv/bin/python -c "
import asyncio
from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_ingest
fn = wiki_ingest._func
print(asyncio.run(fn(source='/home/renan/.jiuwenswarm/config/.env', workspace='/tmp/x')))
"
```
Expected: the message `Error: wiki_ingest only reads documents under ...`

- [ ] **Step 5: Verify publication reached the memory directory**

```bash
ls ~/.jiuwenswarm/agent/workspace/memory/wiki__*.md | head
```
Expected: one line per wiki page.

- [ ] **Step 6: Measure the anchoring (spec S2/S3)**

```bash
W=~/.jiuwenswarm/wikis/papers/.llm_wiki/wiki
grep -c "\[\[fonte:" $W/*.md | sort -t: -k2 -rn | head
```
Then pick **3 pages**, count by hand the substantive claims (denominator) and the
anchored ones (numerator), and check 5 anchors by opening the PDF at the page named --
remembering that `## Page N` is pdfplumber's **physical** index, not the printed number.

Record the numbers. If they land below 90%, apply the spec's fallback (file-level + section
anchor) before Friday.

- [ ] **Step 7: Verify the index picked the pages up (S4)**

```bash
sqlite3 ~/.jiuwenswarm/agent/workspace/memory/memory.db \
  "select path from files where path like '%wiki__%' limit 10;"
```
**`sqlite3` is not installed on this machine**; use Python:

```bash
.venv/bin/python -c "
import sqlite3, pathlib
db = pathlib.Path.home()/'.jiuwenswarm/agent/workspace/memory/memory.db'
c = sqlite3.connect(str(db))
print(c.execute(\"select count(*) from files where path like '%wiki__%'\").fetchone()[0])
"
```

**Result of the 2026-09-09 rehearsal: 0.** Not a publication failure -- the 18 files are
in `~/.jiuwenswarm/agent/workspace/memory/`. The point is that **nothing indexes without a
live agent**: the watcher and the initial sync belong to the main agent's memory manager,
which does not run in a CLI script. The wiki subagent has its own workspace
(`<WIKI_ROOT>/.llm_wiki`) and indexes that one, not the agent's.

**Consequence: S4 can only be verified with the backend up.** It is the first item of
Task 6, even before posting a PDF in the channel.

---

### Task 6: Channel scope (depends on the Slack tokens)

**Files:**
- Modify: `~/.jiuwenswarm/config/config.yaml` (outside the repo)

- [ ] **Step 1: Back up the config**

```bash
cp -p ~/.jiuwenswarm/config/config.yaml \
      ~/.jiuwenswarm/config/config.yaml.bak-scopes-$(date +%Y%m%d-%H%M%S)
```

- [ ] **Step 2: Add the scopes block**

At the top of the file (it is a top-level key; today **no** `scopes:` block exists):

```yaml
scopes:
  - match: {channel: slack}
    delivery:
      prompt: |
        Answer directly and cite your sources.

  - match:
      channel: slack
      chat:    "<PAPERS_CHANNEL_ID>"
    delivery:
      mode: [mention, has_file]
      mid_turn: queue
      prompt_append: |
        This channel is a library of papers backed by an LLM Wiki at
        /home/renan/.jiuwenswarm/wikis/papers.
        - New attachment, and only if it is .pdf/.md/.txt:
          1. call wiki_ingest(source=<path of the attachment>,
             workspace="/home/renan/.jiuwenswarm/wikis/papers");
          2. report which pages were created or updated, by listing the wiki
             directory -- wiki_ingest only returns [Success]. Publishing to the
             index is automatic; do not do it yourself.
        - Question: use memory_search to find the relevant pages and answer
          citing the anchors [[fonte: ... p.N]].
        - Never assert anything without an anchor.
        - Attachment that is not .pdf/.md/.txt: do not ingest; say why.
```

Replace `<PAPERS_CHANNEL_ID>` with the real id, in quotes.

- [ ] **Step 3: Validate the YAML**

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('/home/renan/.jiuwenswarm/config/config.yaml'))
s = d['scopes']
print('scopes:', len(s))
print('mid_turn:', s[1]['delivery']['mid_turn'])
print('mode:', s[1]['delivery']['mode'])
"
```
Expected: `scopes: 2`, `mid_turn: queue`, `mode: ['mention', 'has_file']`

- [ ] **Step 4: Start the backend and check the scope was accepted**

```bash
cd /home/renan/openJiuwen-ai/jiuwenswarm && uv run jiuwenswarm-start debug --skip-build
sleep 20
grep -iE "scope|slack" logs/$(ls -t logs | head -1) | head -20
```
Expected: no discarded-scope warning. A warning naming the conversation and the key means
the value was refused and that conversation fell back to the layer below.

- [ ] **Step 5: Post a PDF in the channel and observe**

Criteria: S1 (becomes pages with no intervention), S6 (< 8 min), automatic publication
(`ls ~/.jiuwenswarm/agent/workspace/memory/wiki__*.md`), and then a question in the channel
verifying S5 (an anchored answer).

- [ ] **Step 6: Stop the backend**

```bash
cd /home/renan/openJiuwen-ai/jiuwenswarm && uv run jiuwenswarm-stop
```
If the ports keep listening, kill the PIDs -- `jiuwenswarm-stop` has lost track of the
parent process once already.
