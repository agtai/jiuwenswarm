# Second Brain PoC — canal de papers no Slack

Data: 2026-09-09 · Branch: `feat/second-brain-slack-poc` (base `55c3c3a85`)
Alvo: demo em 2026-09-11 (sexta)

## 1. Objetivo

Um canal do Slack dedicado a papers onde:

1. alguém joga um PDF;
2. o agente compila o paper numa **wiki persistente** (padrão LLM Wiki do Karpathy),
   com páginas de entidade/conceito interligadas e um índice;
3. as afirmações da wiki carregam **ponteiros para o texto original** (arquivo + página
   + citação curta), para conferência;
4. perguntas posteriores são respondidas por **busca híbrida** (BM25 + vetorial) sobre
   as páginas da wiki.

O ponto da demo **não** é provar que o agente evitou reler o PDF. Releitura é
*verificação*, e o ponteiro é o produto.

## 2. Fora de escopo

- **WikiSkill** (Google): compila a *execução do agente* em skills procedurais, não
  fontes em conhecimento. É outra demo.
- Grafo/backlinks nativos, export, sincronização, versionamento de páginas.
- Provar ausência de releitura (negar ferramentas de leitura).
- Tornar a wiki genérica para outros tipos de documento. A PoC é condicionada a um canal.

## 3. O que já existe (verificado em código, não suposto)

| Peça | Estado | Evidência |
|---|---|---|
| Wiki de 3 camadas (`sources/`, `wiki/`, `schema/`) | ✅ funciona | smoke test: 1 PDF de 28 pág. → 17 páginas em 294 s |
| `wiki_ingest` / `wiki_query` / `wiki_lint` | ✅ implementadas | `tools/wiki_tools.py` |
| `index.md` (Entities/Concepts/Sources) + `log.md` | ✅ gerados | smoke test |
| Dedup por SHA-256 + cópia para `sources/` | ✅ | `_SourceManifest` |
| Leitura de PDF por página | ✅ | `read_file{"pages": "2-11"}` — o parser de PDF está registrado |
| Índice híbrido BM25 + vetorial | ✅ existe | `memory/manager.py`, `_merge_hybrid_results` |
| `extraPaths` (indexar Markdown fora das pastas padrão) | ✅ plumbado | `config.py:170` → `manager.py:604` + watcher em `:377` |
| Trigger `has_file` no Slack | ✅ | `slack_connect.py:200` |
| `delivery.prompt` por conversa (scopes) | ✅ | `scope_capabilities.py` |

### O que **não** existe

| Lacuna | Detalhe |
|---|---|
| Wiki tools registradas | removidas pelo upstream em `e4fae3061` (MR !4526, 06/ago) |
| Ancoragem na fonte | o `AGENT.md` gerado manda interligar só *dentro* de `wiki/` |
| Busca híbrida no `wiki_query` | ele usa `read_file`/`grep`; sem BM25, sem vetor |
| Embeddings configurados | `EMBED_API_KEY`/`_BASE`/`_MODEL` vazias |

## 4. Arquitetura

    PDF no canal #papers
        │  trigger has_file
        ▼
    conector Slack — baixa para <session>/uploads/, põe o caminho no texto
        │  delivery.prompt manda chamar wiki_ingest(source=<path>, workspace=<papers>)
        ▼
    wiki_ingest → subagente mantenedor
        │  lê schema/AGENT.md (com a regra de ancoragem)
        │  lê o PDF por faixas de página
        │  escreve wiki/*.md com [[fonte: arquivo.pdf p.N]] + citação
        ▼
    <papers>/.llm_wiki/wiki/*.md
        │  indexado via memory.extraPaths
        ▼
    índice da memória (FTS5 + vetor)
        ▲
        │  memory_search  ← pergunta do usuário
    agente do canal sintetiza a resposta com as âncoras

Dois caminhos de leitura coexistem, com papéis distintos:

- **`memory_search`** (híbrido, rápido) — o caso comum: pergunta pontual.
- **`wiki_query`** (subagente lendo a wiki) — perguntas que exigem varrer o acervo
  inteiro ("o que há em comum entre os três papers?").

## 5. As quatro mudanças

### 5.1 Registrar as três wiki tools  *(código — obrigatório)*

`server/runtime/agent_adapter/interface_deep.py`, revertendo `e4fae3061`:

```python
from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_ingest, wiki_query, wiki_lint
...
for wtool in [wiki_ingest, wiki_query, wiki_lint, read_pdf]:
```

**O registro é global — e isto é uma escolha, não uma impossibilidade.**

*Via `scopes` seria impossível*: eles só estreitam permissões (D4: `allow` nunca amplia,
pois a fusão é `strictest`) e `not` existe apenas em eixos de identidade, então nenhum
scope pode **conceder** uma ferramenta a um canal.

*Via código seria possível*: o adapter tem `_is_session_scoped_adapter`, e o
`_tool_owner_id()` já se escopa por sessão (`<card id>_s_<session>`). Como o id de sessão
do Slack é `slack_{team}_{channel}_{thread}`, o canal é derivável dentro de
`_get_tool_cards`.

*Escolhemos global* por custo/benefício: o condicional mexe no caminho quente de
construção do agente e exige um terceiro parse de id de sessão — que o próprio código já
desaconselha (`parse_slack_cron_session` está documentado como uma segunda cópia
indesejada desse parse). O custo do global é 3 tool cards a mais no prompt de cada agente;
não é risco de segurança, porque um agente não chama `wiki_ingest` sem ser instruído.

O que escopa o *comportamento* é o `delivery.prompt` (§5.3): a ferramenta existe em todo
lugar, mas só o canal de papers instrui a usá-la. Registro condicional é a evolução
natural se a PoC virar produto.

Se depois quisermos proibi-la em algum canal, aí sim `scopes` serve —
`permissions: {tools: {wiki_ingest: deny}}` estreita e funciona.

> **Nota sobre a divergência com o upstream.** A MR !4526 removeu estas três tools como
> parte de uma faxina de superfície de prompt; ela não relata defeito na wiki e a revisão
> foi procedimental (`/lgtm`). A mesma MR introduziu injeção de prompt *por canal*
> (`BrowserTaskPromptRail`), ou seja, o princípio dela é "escope, não distribua a todos" —
> que é o que fazemos via `delivery.prompt`. Ainda assim, isto é uma divergência a ser
> reavaliada no próximo rebase.

### 5.2 Regra de ancoragem  *(arquivo — zero código)*

`ensure_initialized` escreve `schema/AGENT.md` **somente se ele não existir**. Logo
basta **pré-semear** o arquivo no workspace de papers antes do primeiro ingest; o código
nunca o sobrescreve.

Regras acrescentadas às 7 existentes:

```markdown
8. Toda afirmação substantiva carrega um ponteiro para a fonte, na unidade que a
   ferramenta de leitura reportou. Para um PDF isso é a página:
   `[[fonte: <arquivo> p.N]]`.
9. Acompanhe o ponteiro de uma citação literal curta (≤ 25 palavras) em blockquote,
   para que a afirmação seja conferível sem abrir a fonte.
10. Se a ferramenta de leitura não oferece localizador, ancore no arquivo. Nunca
    invente número de página.
11. Ao ler um PDF, use `read_file` com o parâmetro `pages`, em faixas, e registre as
    páginas que cada seção cobre.
```

A regra 8 é deliberadamente **agnóstica de formato** — fala em "a unidade que a
ferramenta reportou", não em PDF. A especificidade vem do leitor (página para PDF, linha
para `.md`, célula para planilha), e degrada para ancoragem em nível de arquivo quando
não há localizador. A regra 11 corrige um defeito real: o prompt padrão manda usar
`read_pdf`, ferramenta que o subagente **não recebe** (`final_tools=[]`); ele já usa
`read_file` com `pages`, e a regra passa a dizer a verdade.

### 5.3 O canal de papers  *(configuração)*

Escrito em **duas camadas**, usando a composição que `compose.py` já implementa: prosa
com `<key>_append` acrescenta ao que a camada acima assentou, em vez de substituir.

```yaml
scopes:
  # camada 1 — comportamento base, todo canal Slack
  - match: {channel: slack}
    delivery:
      prompt: |
        <comportamento base do bot>

  # camada 2 — este canal é de papers
  - match:
      channel: slack
      chat:    <ID_DO_CANAL_DE_PAPERS>
    delivery:
      mode: [mention, has_file]
      prompt_append: |
        Este canal é uma biblioteca de papers com uma LLM Wiki em
        <WIKI_ROOT>.
        - Anexo novo: chame wiki_ingest(source=<caminho do anexo>,
          workspace="<WIKI_ROOT>") e responda com a página criada.
        - Pergunta: use memory_search para achar as páginas relevantes e
          responda citando as âncoras [[fonte: … p.N]]. Para perguntas que
          exigem varrer o acervo inteiro, use wiki_query.
        - Nunca afirme sem âncora.
```

`mode: [mention, has_file]` é o par mínimo: `has_file` acorda no upload do PDF,
`mention` permite perguntar.

`chat` é **escalar** (`schema.py:899` recusa qualquer valor que não seja string), logo
cada canal de papers exige seu próprio scope com o mesmo `prompt_append` copiado. Com um
canal isso não incomoda; com vários, é a repetição que a §10.2 resolve.

### 5.4 Busca híbrida  *(configuração + credencial)*

```yaml
memory:
  extraPaths:
    - "<WIKI_ROOT>/.llm_wiki/wiki"     # caminho ABSOLUTO
```

`extraPaths` aceita arquivo ou diretório; um diretório é varrido recursivamente por
`.md` (`internal.py:50-58`). **Use caminho absoluto**: o resolvedor faz
`os.path.join(workspace_dir, extra)`, então um caminho relativo é interpretado a partir
do workspace do agente, não do diretório corrente.

E as três variáveis de embedding em `~/.jiuwenswarm/config/.env`:
`EMBED_API_KEY`, `EMBED_API_BASE`, `EMBED_MODEL`. Sem elas o índice funciona, mas
**só com BM25** — a metade vetorial não existe e "híbrida" sai do discurso.

## 6. Roteiro da demo

**Pré-ensaio (quinta):** ingerir 3 papers com sobreposição temática. ~5 min cada
(medido), logo ~15 min — **inviável ao vivo**. A wiki chega pronta na sexta.

1. Mostrar o acervo: `index.md` com Entities / Concepts / Sources.
2. Abrir uma página e mostrar as âncoras `[[fonte: … p.N]]` com as citações.
3. Perguntar algo pontual no canal → resposta por `memory_search` com âncora.
4. **Conferir**: abrir o PDF na página apontada e comparar com a citação.
5. Perguntar algo transversal ("o que estes papers discordam entre si?") →
   `wiki_query`.
6. *(Se o tempo permitir)* ingerir um 4º paper ao vivo e mostrar o `index.md` mudando.

## 7. Critérios de sucesso

| # | Critério | Como verificar |
|---|---|---|
| S1 | PDF no canal vira páginas de wiki sem intervenção manual | postar e observar |
| S2 | ≥ 90% das afirmações substantivas têm âncora | `grep -c "\[\[fonte:"` por página |
| S3 | Âncoras corretas | conferir 5 amostras contra o PDF |
| S4 | `memory_search` retorna páginas da wiki | consulta direta ao índice |
| S5 | Resposta no canal cita âncoras | inspeção |
| S6 | Ingest de 1 paper < 8 min | cronometrar |

**S3 é o critério que pode reprovar a PoC.** Se o modelo inventar números de página,
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

## 9. Questões em aberto

1. Qual `<WIKI_ROOT>` — sugestão: `~/.jiuwenswarm/wikis/papers`.
2. Qual o ID do canal de papers (o `C0BKNLQ1FR7` atual é o canal de testes geral).
3. Quais 3 papers.
4. Há endpoint de embeddings disponível?

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
