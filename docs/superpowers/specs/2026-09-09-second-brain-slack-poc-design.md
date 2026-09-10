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

## 6. Roteiro da demo

**Pré-ensaio (quinta):** ingerir 3 papers com sobreposição temática. ~5 min cada
(medido), logo ~15 min — **inviável ao vivo**. A wiki chega pronta na sexta.

1. Mostrar o acervo: `index.md` com Entities / Concepts / Sources.
2. Abrir uma página e mostrar as âncoras `[[fonte: … p.N]]` com as citações.
3. Perguntar algo pontual no canal → resposta por `memory_search` com âncora.
4. **Conferir**: abrir o PDF na página apontada e comparar com a citação.
   Este é o clímax da demo — é o que "ponteiro" significa.
5. *(Opcional, só se o ensaio aprovar)* pergunta transversal → `wiki_query`.

**Cortes deliberados, e as razões:**

| Cortado | Por quê |
|---|---|
| Ingest ao vivo de um 4º paper | ~5 min de silêncio na frente da plateia. Além disso o dedup por SHA-256 exigiria um paper inédito, e um `mid_turn` mal configurado cancelaria o turno |
| Embeddings / "híbrida" no discurso | as `EMBED_*` estão vazias; BM25 sozinho funciona. Só prometer híbrida se a chave existir na quinta — senão dizer "busca sobre a wiki" |
| `wiki_query` ao vivo (passo 5) | ele **escreve** na wiki (`wiki_tools.py:352`) sem ler o `AGENT.md`, então pode criar páginas sem âncora. Manter só se o ensaio mostrar que não estraga; e sempre por último |

## 7. Critérios de sucesso

| # | Critério | Como verificar |
|---|---|---|
| S1 | PDF no canal vira páginas de wiki **e é publicado no índice** sem intervenção manual | postar e observar. Só é verdade com a publicação em código (§5.4) |
| S2 | ≥ 90% das afirmações substantivas têm âncora | amostrar **3 páginas**, contar à mão as afirmações substantivas (denominador) e as ancoradas (numerador). `grep -c` sozinho não mede: não há denominador automático |
| S3 | Âncoras corretas | conferir 5 amostras contra o PDF |
| S4 | `memory_search` retorna páginas da wiki **após a publicação (§5.4)** | não há CLI para o índice do `lite`; verificar com `sqlite3 ~/.jiuwenswarm/agent/workspace/memory/memory.db "select path from files where path like '%wiki__%'"` |
| S5 | Resposta no canal cita âncoras | inspeção |
| S6 | Ingest de 1 paper < 8 min | cronometrar |

**S4 é o critério que reprova a PoC de forma determinística** se o passo de publicação
(§5.4) não for feito: sem ele o `memory_search` nunca vê a wiki, e o passo 3 da demo cai
para o `wiki_query` — que funciona, mas é lento e não é busca.

**S3 é o critério que pode reprovar de forma probabilística.** Se o modelo inventar números de página,
o ponteiro perde a razão de ser — e como isso é instrução de prompt, não garantia,
tem de ser medido, não presumido.

## 8. Riscos

| Risco | Prob. | Mitigação |
|---|---|---|
| Modelo inventa páginas (S3) | média | medir na quinta; se falhar, cair para âncora em nível de arquivo + seção |
| Sem `EMBED_*` | alta hoje | demo em BM25; ajustar o discurso |
| Slack sem credencial | alta hoje | reautorizar o app; sem isso não há demo |
| 3 papers ≈ 15 min de ingest | certa | pré-ensaio na quinta |
| 120 s de orçamento para anexos | média | um PDF por mensagem |
| Divergência com upstream (§5.1) | baixa | 2 linhas, documentada |
| Passo de publicação esquecido → S4 falha | **alta** | é o item nº 1 do ensaio de quinta |
| `read_file` trunca faixa em 25k tokens → âncora deslocada | média | regra 11: faixas ≤ 5 páginas |
| Âncora cai em chunk separado da afirmação | média | regra 8: âncora na mesma linha |
| `wiki_query` escreve na wiki sem ler o `AGENT.md` (`wiki_tools.py:352`) | média | não usar `wiki_query` para escrever na demo; se usar, revisar depois |
| 4º paper "ao vivo" já ingerido → `[Skipped]: Deduplicated` | média | separar um paper inédito para o ensaio |
| App Slack sem `files:read` ou sem subscrição `message.channels`/`file_share` | média | conferir escopos ao reautorizar |
| `has_file` acorda para qualquer anexo (imagem, screenshot) | média | regra 12 do `AGENT.md` + a guarda de extensão no `prompt_append` |
| `wiki_ingest` lê qualquer arquivo fora do rail de permissão | **alta** | as 4 mitigações da §5.1, sendo (1) o fecho real |
| **`mid_turn` default `cancel` cancela o ingest de 5 min** | **alta** | `mid_turn: queue` no scope (§5.3) — não é opcional |
| **46 erros `NoneType … 'id'` no smoke test** (ver §8.1) | **desconhecida** | reproduzir pelo Slack na quinta antes de confiar em qualquer medição |
| Publicação após restart cai na janela morta do watcher | baixa | forçar nova escrita; ver §5.4 |
| ~~`config.yaml` em 0644~~ | — | **resolvido**: todos os arquivos com segredo em 0600 |

### 8.1 O smoke test não foi limpo — e todas as medições vêm dele

O ingest que produziu a wiki de referência terminou em `[Success]`, mas o log tem
**46 ocorrências de `'NoneType' object has no attribute 'id'`** — em cada `write_file`,
`edit_file` e `bash`. Os arquivos **foram** escritos (a wiki existe e é boa), mas o modelo
viu falha e gastou iterações relendo para conferir.

Consequências que precisam ser ditas em voz alta:

- os **294 s** medidos e o comportamento observado ("ignorou `read_pdf`", "leu em 4
  faixas") vêm dessa execução degradada. Não são baseline confiável;
- a causa provável é diferença de harness entre o runner standalone (que usei) e o
  caminho real do Slack — **mas ninguém verificou isso**;
- o subagente **improvisa quando não consegue cumprir uma regra**: sem `bash` funcional,
  inventou a data do `log.md` (usou a do arXiv) em vez de parar; e leu faixas de 10
  páginas descrevendo-as como 3 blocos. Isto é o prognóstico direto para as regras 8-12:
  esperar **conformidade parcial**, não obediência.

**Ação:** o primeiro item do ensaio de quinta é reproduzir o ingest **pelo Slack**, não
por CLI, e verificar se os 46 erros somem. Se persistirem, medir S2/S3 contra essa
realidade e não contra a esperança.

## 9. Questões em aberto

1. Qual `<WIKI_ROOT>` — sugestão: `~/.jiuwenswarm/wikis/papers`. **Precisa ser caminho
   literal e absoluto no YAML**: no Slack o modelo não recebe a seção de diretórios
   (`runtime_prompt_rail.py:325`) e não descobriria o caminho sozinho.
2. Qual o ID do canal de papers (o `C0BKNLQ1FR7` atual é o canal de testes geral).
3. Quais 3 papers.
4. Há endpoint de embeddings disponível?

Notas sobre o config vivo (`~/.jiuwenswarm/config/config.yaml`):

- **não existe bloco `scopes:`** — a §5.3 é escrita do zero, não editada;
- `allowed_channel_ids` tem só `C0BKNLQ1FR7`. Nomear o canal de papers num scope de
  `delivery` **já o isenta** dessa lista (`compose.py:228`), então o bot passa a responder
  lá sem tocar em `allowed_channel_ids`. Comportamento desejado — registrado para não
  surpreender;
- o ingest síncrono de ~5 min cabe folgado: o bound de um turno é 3600 s
  (`_TURN_INITIATOR_TIMEOUT_SECONDS`);
- **`models.defaults` tem 11 entradas, e as 11 estão com `is_default: true`.** O código
  pega a primeira (`wiki_tools.py:368`); trocar de modelo exige reordenar ou limpar as
  flags, não só repor uma chave;
- **higiene:** `config.yaml`, `.env` e todos os `.bak*`/`.pre-align` estão agora em
  `0600` (feito). Ao repor os tokens do Slack, **não restaure o backup inteiro** — ele
  carrega outras diferenças de `models.defaults`; copie só as duas linhas.

## 9.1 Resultado — verificado pelo Slack em 2026-09-10

A PoC rodou de ponta a ponta pelo canal real, com dois papers.

| Critério | Resultado |
|---|---|
| S1 PDF vira wiki sem intervenção | ✅ |
| S2 âncoras | ✅ **556** âncoras em 30 páginas |
| S3 âncoras corretas | ✅ 3 amostras conferidas contra o PDF |
| S4 índice serve a wiki | ✅ 30 publicadas, FTS com 324 docs |
| S5 resposta com âncora no canal | ✅ |
| S6 ingest < 8 min | ⚠️ ~9 min por paper |

    papers  1 → 2      páginas  18 → 30      âncoras  229 → 556

### O acervo compôs, e isto é o achado principal

O segundo paper **não** produziu apenas páginas novas: reescreveu as do primeiro.
`sarsi-agents.md` ganhou 8 menções ao AREX, `recursive-self-improvement.md` 9, e
`evaluation-framework.md` 4 — e não como citação decorativa, mas como distinção
conceitual. O agente percebeu que os dois papers usam *"recursive self-improvement"*
com sentidos diferentes e escreveu uma seção sobre isso na página do conceito.

É a tese do Karpathy observada — *"the cross-references are already there"* — e é o
argumento mais forte de que isto não é RAG: um RAG recuperaria os dois trechos e
deixaria a contradição para o leitor.

**Consequência para a demo:** o clímax não é a busca, é abrir
`recursive-self-improvement.md` e mostrar a seção que só existe porque um segundo paper
entrou.

### Defeito reportado que NÃO existe — a extensão na âncora

Uma versão anterior desta seção registrava que as âncoras do segundo paper saíam com a
extensão truncada (`.df` em vez de `.pdf`). **Isso estava errado, e o erro era do
verificador, não do modelo.**

A medição tinha passado as âncoras por `sed 's/p[0-9]*//'` para agrupar por arquivo.
`p[0-9]*` casa um `p` seguido de **zero** ou mais dígitos, portanto casa o `p` de `.pdf`
e o remove. O `.df` foi produzido pelo próprio comando de verificação.

Contagem correta sobre a wiki inteira:

    567 âncoras com ".pdf p"        0 âncoras com extensão quebrada

Fica registrado como lição de método: **uma medição de conformidade precisa ser
verificada com o mesmo rigor que o artefato que ela mede.** Um `sed` mal escrito quase
custou uma reingestão de 9 minutos por paper para consertar um defeito inexistente.

## 10. Evoluções

### 10.1 Híbrida por dentro do `wiki_query`

A PoC coloca a híbrida **ao lado** do `wiki_query`. O passo seguinte é colocá-la
**dentro**: o `wiki_query` recuperaria as páginas relevantes antes de abri-las, em vez
de listar o diretório e ler tudo. Hoje ele lê a wiki inteira — com 17 páginas funciona,
com 200 não. Isso exige modificar uma ferramenta upstream e por isso fica fora da PoC.

### 10.2 `channel_type` — classes de canal em vez de ids

A §5.3 escreve o prompt de papers contra um **id de conversa**. Como `chat` é escalar,
N canais do mesmo tipo exigem N scopes com o mesmo `prompt_append` copiado, e um leitor
do config vê uma lista de ids opacos em vez de uma intenção.

O projeto já tem o padrão certo no eixo de pessoas: `people:` e `roles:` são blocos
irmãos que resolvem um nome (`admin`) para um conjunto de ids, e `role` casa contra isso.
O código é explícito quanto ao papel disso — um role *"não carrega permissões próprias:
ele nomeia um conjunto de pessoas"* (D8). `channel_type` seria o análogo para conversas:

```yaml
channel_types:                     # bloco novo, irmão de people:/roles:
  papers:  [C_PAPERS_1, C_PAPERS_2]
  suporte: [C_SUP_1]

scopes:
  - match: {channel: slack, channel_type: papers}
    delivery: {prompt_append: "<wiki + papers>"}
```

Ganhos: uma definição por tipo, vocabulário legível, e a composição em camadas já
existente passa a valer por classe.

O que isto exige, e por que fica fora da PoC:

- eixo novo no schema, com resolução e validação próprias;
- declaração nas `ChannelCapabilities` de cada conector que o suporte;
- decisões de semântica ainda em aberto: um canal pode ter dois tipos? tipos compõem
  entre si? o que acontece quando dois tipos discordam da mesma chave?
- **e uma consequência de segurança que não é óbvia.** `scoped_chats` documenta que, no
  Slack, os ids nomeados em scopes de `delivery`/`agent` **isentam o canal de
  `allowed_channel_ids`** — nomear uma conversa num scope já é opt-in para o bot
  responder ali. Um `channel_type` mal desenhado abriria vários canais de uma vez sem
  que ninguém percebesse, que é exatamente a direção (D4) que este desenho não permite.

Merece spec próprio.

### 10.3 `extra_paths` no kernel `lite`

A §5.4 publica a wiki copiando arquivos para `<agent workspace>/memory/`. É um contorno.
O correto é `lite/manager.py:954` repassar `extra_paths` — o parâmetro **já existe** na
assinatura de `list_memory_files` (`lite/internal.py:35`) e simplesmente não é passado.
Junto com isso valeria trocar o `os.listdir` do scan de extras por `os.walk`
(`lite/internal.py:80`), para que apontar um diretório funcione de fato.

Duas linhas, mas dentro do `openjiuwen` fixado em `61becb17`: exige contribuição upstream
ou fork da dependência. Depois disso, a §5.4 vira uma chave de config e o passo de
publicação desaparece.

### 10.4 Âncoras clicáveis — hyperlink para a página do PDF

Hoje a âncora `[[fonte: paper.pdf p7]]` é texto. A evolução natural é torná-la um link
que abre o PDF **na página citada**, transformando o double-check de "abra o arquivo e
procure" em um clique.

**O que já está resolvido.** O conector converte link Markdown em `mrkdwn` do Slack
sozinho — `_normalize_slack_mrkdwn` (`slack_connect.py:11916`). Verificado:

    IN : [paper.pdf p.7](http://host/x.pdf#page=7)
    OUT: <http://host/x.pdf#page=7|paper.pdf p.7>

Ou seja, **não é preciso gerar a sintaxe `<url|texto>`**; basta o agente escrever Markdown.

**O que precisa mudar na regra 8.** O colchete duplo quebra o regex e passa intacto:

    IN : [[fonte: x.pdf p7]](http://host/x.pdf#page=7)
    OUT: (inalterado — não vira link)

A âncora teria de virar colchete simples: `[fonte: x.pdf p.7](url)`.

**O elo que falta: de onde vem a URL.** Três opções, nenhuma gratuita.

| Opção | Viável? | Observação |
|---|---|---|
| Permalink do Slack | ❌ | o visualizador do Slack não honra `#page=N` |
| `url_private` do arquivo | ⚠️ | abre no navegador com a sessão do usuário; `#page` só funciona se o navegador renderizar o PDF inline. **É o caminho certo**: o arquivo já está hospedado, com o controle de acesso do canal |
| Servidor HTTP local sobre `sources/` | ✅ | trivial (`python3 -m http.server`), mas a URL é `localhost` — serve para demo com tela compartilhada, não para os outros clicarem |

**E uma cadeia de metadados que hoje não existe.** O `wiki_ingest` copia o PDF para
`sources/` com prefixo de hash e **descarta a origem no Slack**: o `slack_file_id` fica no
registro do anexo (`slack_connect.py:11375`) e nunca chega à wiki. Para um link baseado no
`url_private` seria preciso carregá-lo por toda a cadeia — conector → prompt → parâmetro do
`wiki_ingest` → frontmatter da página → âncora. Isso é o grosso do trabalho, não o link.

**Por que fica fora da PoC.** Nada aqui é difícil isoladamente, mas são quatro mudanças
acopladas (formato da âncora, cadeia de metadados, hospedagem do arquivo, e reingestão das
páginas já escritas no formato antigo) e a demo já entrega a verificação sem elas — o
ponteiro em texto já diz arquivo e página, que é o que a tese exige. O clique é conforto,
não prova.

---

## 11. Pontos de melhora, medidos na wiki real (2 papers)

Estado estrutural em 2026-09-10: 30 páginas, 221 KB, 257 arestas, **0 órfãs, 0 links
quebrados**, 567 âncoras. A estrutura está saudável; o que segue é sobre escala e
precisão.

| # | Ponto | Custo | Estado |
|---|---|---|---|
| A1 | `wiki_query` lia a wiki inteira | prompt | ✅ **aplicado** |
| A2 | `index.md`/`log.md` poluíam o índice | 1 regra | ✅ **aplicado** |
| A3 | chunks no teto cortam afirmação+citação | config | aberto |
| A4 | prefixo de hash nas âncoras | metadados | aberto |
| A5 | ninguém roda o `wiki_lint` | operação | aberto |

### A1 — `wiki_query` não escalava  ✅ aplicado

Ele era instruído apenas a *"answer strictly based on `wiki/`"*, sem método, e portanto
listava o diretório e lia tudo: **221 KB com dois papers**. Como o acervo é projetado
para compor, a versão ingênua piora a cada fonte — o oposto do que o desenho promete.

O prompt agora ordena o trabalho: `index.md` primeiro (é o catálogo, uma linha por
página), `grep` depois pelos termos da pergunta, e só então as páginas que sobreviveram.
O write-back continua, mas agora **preso ao `schema/AGENT.md`** — a redação anterior
permitia escrever uma página sem as âncoras que todas as outras carregam.

Isto **não** é a busca híbrida da §10.1, que segue sendo a solução completa; é a correção
que cabia sem tocar na arquitetura.

### A2 — páginas de navegação fora do índice  ✅ aplicado

`index.md` e `log.md` nomeiam **todos** os tópicos da wiki, então casam com quase
qualquer consulta e afogam a página que de fato responde. Pior: **17 dos 26 chunks sem
âncora eram deles** — uma recuperação que caia ali deixa o agente sem nada para citar.

Ambos deixam de ser publicados, e cópias antigas são removidas (nada mais as apagaria).

### A3 — o chunking está no teto

    245 chunks · média 963 chars · máximo 1067

Os chunks estão colados no limite. Uma afirmação com blockquote de 25 palavras ocupa boa
parte disso, então o par afirmação+citação corre risco real de ser partido — que é
exatamente o que a regra 8 ("âncora na mesma linha") tenta evitar, e ela só protege
dentro de uma linha, não dentro de um chunk.

`memory.chunking` é configurável. Subir para ~1500 daria folga. **Precisa de medição
antes**: chunk maior reduz precisão da recuperação, então é um trade-off, não uma
melhoria óbvia.

### A4 — o prefixo de hash nas âncoras

    [[fonte: 45e4144f_2607.21461v2.pdf p10]]

O `sha256[:8]_` vem de como `wiki_ingest` nomeia o arquivo em `sources/`. Serve para
desambiguar, mas polui toda resposta e impede um link limpo. Guardar o nome original no
frontmatter da página-fonte e ancorar por ele resolve — e é a **mesma cadeia de
metadados** que a §10.4 exige, então as duas devem ser feitas juntas.

### A5 — o `wiki_lint` não roda

Ficou deliberadamente fora do registro de ferramentas (§5.1). Mas é ele quem detecta
órfãs e links quebrados — hoje em zero **por sorte, não por verificação**. Com dez papers
isso degrada silenciosamente. Decidir se entra como passo periódico ou manual.

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
