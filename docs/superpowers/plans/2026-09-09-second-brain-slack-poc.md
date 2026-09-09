# Second Brain PoC (canal de papers no Slack) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer com que um PDF postado num canal do Slack vire páginas de wiki ancoradas na fonte e pesquisáveis pelo `memory_search` do agente, sem intervenção manual.

**Architecture:** Quatro mudanças. Duas em `wiki_tools.py` (restringir de onde o `wiki_ingest` lê, e publicar as páginas no diretório de memória do agente ao final de um ingest bem-sucedido); uma em `interface_deep.py` (registrar `wiki_ingest`/`wiki_query`, revertendo parte de `e4fae3061`); e duas de configuração (pré-semear o `schema/AGENT.md` do workspace de papers com as regras de ancoragem, e escrever o scope do canal).

**Tech Stack:** Python 3.11, pytest + monkeypatch, `openjiuwen` no commit fixado `61becb17`, uv.

**Spec:** `docs/superpowers/specs/2026-09-09-second-brain-slack-poc-design.md`

## Global Constraints

- Branch de trabalho: `feat/second-brain-slack-poc`; worktree
  `/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/wiki-smoke`.
- Rodar tudo com o venv da worktree: `.venv/bin/python`, `.venv/bin/pytest`.
- **Não** alterar nada em `.venv/` (é o `openjiuwen` fixado). Toda mudança é em `jiuwenswarm/`.
- Testes novos vão em `tests/unit_tests/agents/`, seguindo o padrão de
  `test_wiki_tools_runtime_config.py` (pytest, `monkeypatch`, `SimpleNamespace`).
- Estilo do repositório: docstrings em inglês, comentários explicando *por quê*.
- Commit por tarefa, mensagem em inglês, prefixo convencional (`feat:`/`fix:`/`test:`).
- **As Tasks 1–3 e 5 não dependem do Slack.** Só a Task 6 (ensaio) precisa dos tokens.

---

## File Structure

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `jiuwenswarm/agents/harness/common/tools/wiki_tools.py` | ferramentas da wiki; ganha guarda de origem e publicação | Modificar |
| `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py` | registro de tools do agente | Modificar (`:7716-7722`) |
| `tests/unit_tests/agents/test_wiki_ingest_source_guard.py` | testes da guarda de origem | Criar |
| `tests/unit_tests/agents/test_wiki_publish.py` | testes da publicação | Criar |
| `tests/unit_tests/agents/test_shared_tool_registration.py` | teste do registro | Criar |
| `~/.jiuwenswarm/wikis/papers/.llm_wiki/schema/AGENT.md` | regras do mantenedor (fora do repo) | Criar |
| `~/.jiuwenswarm/config/config.yaml` | bloco `scopes:` (fora do repo) | Modificar |

---

### Task 1: Restringir de onde o `wiki_ingest` pode ler

Fecha o buraco da §5.1: hoje `wiki_ingest` aceita qualquer caminho absoluto, sem validar
extensão no ramo de arquivo único, e o ramo de diretório faz `glob("**/*")` de qualquer
raiz — `wiki_ingest(source="~")` ingeriria todo `.md` do usuário.

**Files:**
- Modify: `jiuwenswarm/agents/harness/common/tools/wiki_tools.py`
- Test: `tests/unit_tests/agents/test_wiki_ingest_source_guard.py`

**Interfaces:**
- Consumes: `get_agent_workspace_dir()` e `get_agent_sessions_dir()` de `jiuwenswarm.common.utils`.
- Produces: `INGESTIBLE_SUFFIXES: tuple[str, ...]`, `source_is_allowed(path: Path) -> bool`.

- [ ] **Step 1: Write the failing test**

Criar `tests/unit_tests/agents/test_wiki_ingest_source_guard.py`:

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

Em `wiki_tools.py:37`, **substituir** a linha

```python
from jiuwenswarm.common.utils import get_agent_workspace_dir
```

por

```python
from jiuwenswarm.common.utils import get_agent_sessions_dir, get_agent_workspace_dir
```

(`shutil` já está importado na linha 11; `Path` na 7.)

Logo abaixo de `DEFAULT_WIKI_DIR = ".llm_wiki"`:

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

Em `wiki_ingest`, logo após o bloco `if not src_path.exists(): ...`:

```python
        if not source_is_allowed(src_path):
            return (
                f"Error: wiki_ingest only reads documents under the agent's session "
                f"uploads or workspace directory; {source} is outside both."
            )
```

E no ramo de arquivo único, trocar:

```python
        else:
            targets.append(src_path)
```

por:

```python
        else:
            if src_path.suffix.lower() not in INGESTIBLE_SUFFIXES:
                return (
                    f"Error: wiki_ingest handles {', '.join(INGESTIBLE_SUFFIXES)}; "
                    f"got '{src_path.suffix or 'no extension'}'."
                )
            targets.append(src_path)
```

E no ramo de diretório, trocar `for ext in (".pdf", ".md", ".txt"):` por
`for ext in INGESTIBLE_SUFFIXES:` — uma lista, não duas.

> **Cobertura da §5.1 do spec, e o que fica de fora.** Esta task implementa as
> mitigações (1) restringir `source` e (2) validar extensão. As outras duas ficam
> deliberadamente fora da PoC:
>
> - **(3) usar `sys_operation.fs()` para a cópia** — é a correção arquitetural correta
>   (põe a leitura de volta atrás do rail de permissão), mas com `source` restrito aos
>   dois diretórios que o próprio agente já pode ler, o ganho marginal em 2 dias é
>   pequeno e o risco de mexer no caminho de cópia é real. **Registrar como dívida.**
> - **(4) negar por scope** — só faz sentido depois de existirem outros canais; é opt-out
>   e não substitui (1).
>
> Se a Task 1 for cortada por tempo, **a demo não deve ir ao ar**: sem ela qualquer
> conversa no Slack pode mandar o `wiki_ingest` ler um arquivo arbitrário.

- [ ] **Step 6: Run the full wiki test file to check nothing regressed**

Run: `.venv/bin/pytest tests/unit_tests/agents/ -k wiki -v`
Expected: todos passam (inclui `test_wiki_tools_runtime_config.py`)

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

### Task 2: Publicar as páginas da wiki no índice do agente

Sem isto o `memory_search` nunca vê a wiki e a demo perde a busca (S4). O spec §5.4
explica por que isto é código e não prompt: no Slack o modelo não recebe o caminho do
workspace, e um `cp` de fora dele dispararia aprovação no meio do turno.

**Files:**
- Modify: `jiuwenswarm/agents/harness/common/tools/wiki_tools.py`
- Test: `tests/unit_tests/agents/test_wiki_publish.py`

**Interfaces:**
- Consumes: `get_agent_workspace_dir()`.
- Produces: `WIKI_PUBLISH_PREFIX: str`, `publish_wiki_pages(wiki_dir: Path, memory_dir: Path) -> list[Path]`.

- [ ] **Step 1: Write the failing test**

Criar `tests/unit_tests/agents/test_wiki_publish.py`:

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

Em `wiki_tools.py`, abaixo de `source_is_allowed`:

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

Em `LLMWiki.ingest`, substituir as duas últimas linhas:

```python
        await self._manifest.record(sha256=sha256, name=source_path.name, destination=destination)
        return result
```

por:

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
Expected: todos passam

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

### Task 3: Registrar `wiki_ingest` e `wiki_query` no runtime

Sem isto o agente não tem as ferramentas — elas estão definidas e nunca registradas
desde `e4fae3061`. `wiki_lint` fica de fora: a demo não precisa dele.

**Files:**
- Modify: `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py` (`:7716-7722`)
- Test: `tests/unit_tests/agents/test_shared_tool_registration.py`

**Interfaces:**
- Produces: `SHARED_AGENT_TOOLS: tuple` no módulo `interface_deep`.

- [ ] **Step 1: Write the failing test**

Criar `tests/unit_tests/agents/test_shared_tool_registration.py`:

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

Em `interface_deep.py`, **logo abaixo** da linha 334
(`from jiuwenswarm.agents.harness.common.tools.pdf_tools import read_pdf`), adicionar:

```python
from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_ingest, wiki_query
```

Em nível de módulo, logo abaixo desse import:

```python
#: Tools every agent shares. wiki_ingest and wiki_query were unregistered upstream in
#: e4fae3061 as part of trimming prompt surface, not because of any defect; the papers
#: channel needs them, and a scope cannot grant a tool (it can only narrow), so they come
#: back globally and the channel's prompt is what puts them to use. wiki_lint stays out:
#: the PoC never lints.
SHARED_AGENT_TOOLS = (wiki_ingest, wiki_query, read_pdf)
```

E trocar o laço em `_get_tool_cards`:

```python
        for wtool in [read_pdf]:
            self._register_shared_tool(wtool)
            tool_cards.append(wtool.card)
```

por:

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
Expected: sem novas falhas (anotar as pré-existentes, se houver, antes de mudar nada)

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

### Task 4: Pré-semear o `schema/AGENT.md` do workspace de papers

`ensure_initialized` só escreve o arquivo **se ele não existir**, então semeá-lo antes do
primeiro ingest é o jeito de dar as regras de ancoragem sem tocar no default do código.

**Files:**
- Create: `~/.jiuwenswarm/wikis/papers/.llm_wiki/schema/AGENT.md` (fora do repo)

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

Nota sobre a regra 13: no smoke test o subagente inventou a data do `log.md` (usou a do
arXiv) quando não conseguiu rodar `date`. A regra existe para tornar esse comportamento
explicitamente proibido, já que ele é o mesmo padrão que produziria uma âncora inventada.

- [ ] **Step 3: Verify it is not overwritten**

```bash
cd /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/wiki-smoke
md5sum ~/.jiuwenswarm/wikis/papers/.llm_wiki/schema/AGENT.md
```
Guardar o hash; conferir de novo depois da Task 6 — deve ser idêntico.

---

### Task 5: Ensaio pelo CLI (sem Slack)

Prova as Tasks 1–3 de ponta a ponta antes de qualquer dependência de credencial.

**Files:**
- Create: `/home/renan/second_brain_rehearsal.py` (script descartável, fora do repo)

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
    fn = wiki_ingest
    for attr in ("func", "_func", "fn", "callback", "handler"):
        cand = getattr(wiki_ingest, attr, None)
        if callable(cand):
            fn = cand
            break
    t0 = time.time()
    out = await fn(source=str(staged), workspace=WS, force=False)
    print(f"\n[rehearsal] {time.time() - t0:.0f}s\n{out}")

asyncio.run(main())
EOF
```

- [ ] **Step 2: Run it**

Run: `cd /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/wiki-smoke && .venv/bin/python /home/renan/second_brain_rehearsal.py 2>&1 | tail -30`
Expected: `[Success]`

- [ ] **Step 3: Check for the degraded-harness errors (§8.1 do spec)**

Run: `.venv/bin/python /home/renan/second_brain_rehearsal.py 2>&1 | grep -c "NoneType.*attribute 'id'"`
Expected: **0**. Se não for 0, os erros não eram do runner descartável e a §8.1 precisa
ser reaberta antes de confiar em qualquer medição.

- [ ] **Step 4: Verify the guard refuses a file outside the allowed roots**

```bash
.venv/bin/python -c "
import asyncio
from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_ingest
fn = getattr(wiki_ingest, 'func', wiki_ingest)
print(asyncio.run(fn(source='/home/renan/.jiuwenswarm/config/.env', workspace='/tmp/x')))
"
```
Expected: mensagem `Error: wiki_ingest only reads documents under ...`

- [ ] **Step 5: Verify publication reached the memory directory**

```bash
ls ~/.jiuwenswarm/agent/workspace/memory/wiki__*.md | head
```
Expected: uma linha por página da wiki.

- [ ] **Step 6: Measure the anchoring (S2/S3 do spec)**

```bash
W=~/.jiuwenswarm/wikis/papers/.llm_wiki/wiki
grep -c "\[\[fonte:" $W/*.md | sort -t: -k2 -rn | head
```
Depois escolher **3 páginas**, contar à mão as afirmações substantivas (denominador) e as
ancoradas (numerador), e conferir 5 âncoras abrindo o PDF na página indicada — lembrando
que `## Page N` é o índice **físico** do pdfplumber, não o número impresso.

Registrar os números. Se ficarem abaixo de 90%, aplicar o fallback do spec (âncora em
nível de arquivo + seção) antes da sexta.

- [ ] **Step 7: Verify the index picked the pages up (S4)**

```bash
sqlite3 ~/.jiuwenswarm/agent/workspace/memory/memory.db \
  "select path from files where path like '%wiki__%' limit 10;"
```
Expected: as páginas publicadas. Se vier vazio, esperar 5 s (debounce de 2 s) e repetir;
se seguir vazio, o watcher não pegou — forçar uma reescrita ou reiniciar a sessão.

---

### Task 6: Scope do canal (depende dos tokens do Slack)

**Files:**
- Modify: `~/.jiuwenswarm/config/config.yaml` (fora do repo)

- [ ] **Step 1: Back up the config**

```bash
cp -p ~/.jiuwenswarm/config/config.yaml \
      ~/.jiuwenswarm/config/config.yaml.bak-scopes-$(date +%Y%m%d-%H%M%S)
```

- [ ] **Step 2: Add the scopes block**

No topo do arquivo (é uma chave de nível superior; hoje **não existe** bloco `scopes:`):

```yaml
scopes:
  - match: {channel: slack}
    delivery:
      prompt: |
        Responda de forma direta e cite suas fontes.

  - match:
      channel: slack
      chat:    "<ID_DO_CANAL_DE_PAPERS>"
    delivery:
      mode: [mention, has_file]
      mid_turn: queue
      prompt_append: |
        Este canal é uma biblioteca de papers com uma LLM Wiki em
        /home/renan/.jiuwenswarm/wikis/papers.
        - Anexo novo, e só se for .pdf/.md/.txt:
          1. chame wiki_ingest(source=<caminho do anexo>,
             workspace="/home/renan/.jiuwenswarm/wikis/papers");
          2. relate quais páginas foram criadas ou atualizadas, listando o
             diretório da wiki — o retorno de wiki_ingest diz apenas [Success].
             A publicação no índice é automática; não a faça você.
        - Pergunta: use memory_search para achar as páginas relevantes e
          responda citando as âncoras [[fonte: … p.N]].
        - Nunca afirme sem âncora.
        - Anexo que não seja .pdf/.md/.txt: não ingira; diga por quê.
```

Substituir `<ID_DO_CANAL_DE_PAPERS>` pelo id real, entre aspas.

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
Expected: nenhum aviso de scope descartado. Um aviso nomeando a conversa e a chave
significa que o valor foi recusado e aquela conversa caiu para a camada de baixo.

- [ ] **Step 5: Post a PDF in the channel and observe**

Critérios: S1 (vira páginas sem intervenção), S6 (< 8 min), publicação automática
(`ls ~/.jiuwenswarm/agent/workspace/memory/wiki__*.md`), e depois uma pergunta no canal
verificando S5 (resposta com âncora).

- [ ] **Step 6: Stop the backend**

```bash
cd /home/renan/openJiuwen-ai/jiuwenswarm && uv run jiuwenswarm-stop
```
Se as portas continuarem escutando, matar os PIDs — o `jiuwenswarm-stop` já perdeu o
rastro do processo pai uma vez.
