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
| `extraPaths` | ⚠️ **plumbado no gestor errado** — ver §3.1 | `config.py:170` → `manager.py:604`, mas esse gestor não serve o agente |
| Trigger `has_file` no Slack | ✅ | `slack_connect.py:200` |
| `delivery.prompt` por conversa (scopes) | ✅ | `scope_capabilities.py` |

### 3.1 Duas pilhas de memória — e o agente usa a que ignora `extraPaths`

    jiuwenswarm/agents/harness/common/memory/     openjiuwen/core/memory/lite/
    MemoryIndexManager                             (kernel, pin 61becb17)
         │ lê memory.extraPaths        ✅                │ recebe extra_paths?  ❌
         │                                              │
         └─ usado por: memory_tools.py                  └─ usado por: MemoryRail
                       memory_rpc.py                                   │
                       (console /memory da TUI)                        ▼
                                                        É ESTE QUE O AGENTE USA

- `interface_deep.py:6897` monta o `MemoryRail` de `openjiuwen.core.memory.lite`.
- `lite/manager.py:954` chama `list_memory_files(self.workspace, node_name=...)`
  **sem `extra_paths`**, embora o parâmetro exista (`lite/internal.py:35`).
- Nada em `server/`, `gateway/` ou `agents/swarm/` importa o `memory_tools.py` do
  jiuwenswarm (grep vazio).

Consequência: **`memory.extraPaths` é chave morta para o agente.** A §5.4 da v1 falharia
de forma determinística. Corrigido na §5.4 desta versão.

O scan do `lite` é ainda **plano** — `os.listdir`, não `os.walk` (`lite/internal.py:80`).

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
        │  publicação: cópia/symlink arquivo-a-arquivo (§5.4)
        ▼
    <agent workspace>/memory/*.md
        │  watcher do lite reindexa
        ▼
    índice do kernel lite (FTS5 + vetor)
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
for wtool in [wiki_ingest, wiki_query, read_pdf]:   # wiki_lint não é preciso na demo
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
indesejada desse parse).

**Mas o global tem um custo de segurança, e a v2 o subestimava.** A afirmação anterior
("não é risco, porque um agente não chama `wiki_ingest` sem ser instruído") está errada.

`wiki_ingest` valida extensão **apenas no ramo de diretório**; para um arquivo único não
valida nada (`wiki_tools.py:498-508`), e a cópia é `shutil.copy2` direto
(`wiki_tools.py:331`), **fora do `SysOperation`** — logo fora do rail de permissão que
guarda `read_file`. Um agente em qualquer canal pode então chamar
`wiki_ingest(source="~/.jiuwenswarm/config/.env")`: o arquivo é copiado para `sources/`,
o subagente o lê, e o conteúdo vira página de wiki — que a §5.4 publica no índice.

A precisão importa: isto **não cria** a capacidade de ler arquivos onde o agente já tem
`bash`/`read_file`. O que cria é um **caminho de leitura que não passa pelo rail de
permissão** — num canal onde `bash` foi negado por scope, `wiki_ingest` continuaria
aberto. É uma inconsistência de guarda.

**Mitigações.** Uma revisão posterior mostrou que a lista anterior era fraca; esta é a
corrigida:

1. **Restringir `source`** ao diretório de uploads da sessão
   (`get_agent_sessions_dir()/<sid>/uploads`, que é onde o conector deposita os anexos —
   `slack_connect.py:11358`) ou ao workspace do agente. **Este é o fecho real.** Validar
   extensão sozinho não basta: o ramo de diretório faz `glob("**/*")` a partir de
   qualquer raiz (`wiki_tools.py:500-506`), logo `wiki_ingest(source="~")` ingeriria todo
   `.md` do usuário.
2. **Validar extensão também no ramo de arquivo único** — o filtro `.pdf/.md/.txt` já
   existe no outro ramo; é o bug óbvio, mas é complemento, não substituto de (1).
3. **Usar `sys_operation.fs()` para a cópia**, em vez de `shutil.copy2`. O parâmetro
   `sys_operation` **já chega** na função (`wiki_tools.py:475`) e é ignorado. Isto põe a
   leitura de volta atrás do rail de permissão, que é a inconsistência de origem.
4. **Negar por scope onde não se quer** — `permissions: {tools: {wiki_ingest: deny}}`.
   Funciona (estreitar é permitido), mas é opt-out por canal: o default global segue
   aberto, então não substitui (1).

> **O que NÃO é mitigação.** Deixar `wiki_lint` de fora do registro não protege nada: ele
> apenas lê a wiki. Quem escreve nela é o `wiki_query` — *"write it back into the wiki"*,
> `wiki_tools.py:352` — e esse **fica** registrado. Uma versão anterior deste spec listava
> isso como mitigação; era teatro.

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
8.  Toda afirmação substantiva carrega um ponteiro para a fonte, **na mesma linha da
    afirmação**: `[[fonte: <arquivo> p.N]]`. Para PDF, N é o número do cabeçalho
    `## Page N` que o `read_file` devolve — nunca um número inferido.
9.  Logo abaixo, uma citação literal curta (≤ 25 palavras) em blockquote. Cite o texto
    **como extraído**; ele pode conter artefatos de hifenização e quebra de linha.
10. Se a leitura não devolveu localizador, ancore no arquivo. Nunca invente página.
11. Ao ler um PDF use `read_file` com `pages`, em faixas de **no máximo 5 páginas**.
    Se a resposta indicar truncagem, releia em faixa menor antes de escrever qualquer
    afirmação sobre aquele trecho.
12. Ingira apenas `.pdf`, `.md` e `.txt`. Qualquer outro tipo: não ingerir, reportar.
```

Justificativa das mudanças em relação à v1:

- **"mesma linha"** (regra 8) — o índice fragmenta em ~256 tokens. Uma âncora separada
  da afirmação cai noutro chunk e o S5 falha mesmo com o S3 perfeito.
- **`## Page N`** (regra 8) — `harness/tools/filesystem.py:750` escreve
  `f"## Page {page_no}\n{page_text}"`. O número é dado, não inferido; isto é o que
  sustenta o S3. **Atenção ao conferir:** é o índice *físico* do pdfplumber (a 1ª página
  do arquivo é 1), não o número impresso na página. Num paper com capa ou numeração
  romana no início, os dois divergem — confira pelo contador do visualizador de PDF, não
  pelo número impresso.
- **faixa ≤ 5** (regra 11) — o teto declarado é 20 páginas (`PDF_MAX_PAGES_PER_READ`),
  mas `MAX_TOKENS = 25_000` estoura antes e **trunca**; uma faixa truncada produz âncora
  deslocada sem o modelo perceber.
- **regra 12** — `has_file` acorda para *qualquer* anexo, e `wiki_ingest` aceita arquivo
  único de qualquer tipo (`wiki_tools.py:507`): sem esta regra o subagente tenta "ler" um
  PNG colado no canal.

A regra 8 tem uma **parte agnóstica e uma parte concreta**, e a distinção importa: o
princípio é "a unidade que o leitor reportou", mas o formato efetivamente exigido é
`p.N`, que só existe para PDF. Para outros tipos a regra 10 cobre (âncora no arquivo).
Uma generalização real — linha para `.md`, célula para planilha — fica para quando houver
um segundo tipo de fonte em uso.

O princípio permanece: fala em "a unidade que a
ferramenta reportou", não em PDF. A especificidade vem do leitor (página para PDF, linha
para `.md`, célula para planilha), e degrada para ancoragem em nível de arquivo quando
não há localizador. As regras 8 e 11 também corrigem um defeito real: o prompt padrão manda usar `read_pdf`,
ferramenta que o subagente **não recebe** (`final_tools=[]`, `wiki_tools.py:213`); ele já
usa `read_file` com `pages`, e as regras passam a dizer a verdade. A linha 54 do `wiki_tools.py` continua mandando usar `read_pdf`, mas
**isso não produz chamada falhada**: no smoke test o subagente simplesmente ignorou a
instrução e foi direto ao `read_file` (zero ocorrências de `read_pdf` no log). O prompt
está errado e é inofensivo; as regras 8 e 11 é que passam a dizer a verdade.

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
      mid_turn: queue          # ver nota abaixo — o default `cancel` mata o ingest
      prompt_append: |
        Este canal é uma biblioteca de papers com uma LLM Wiki em
        <WIKI_ROOT>.
        - Anexo novo, e só se for .pdf/.md/.txt:
          1. chame wiki_ingest(source=<caminho do anexo>, workspace="<WIKI_ROOT>");
          2. relate quais páginas foram criadas ou atualizadas, listando o
             diretório da wiki — o retorno de wiki_ingest diz apenas [Success].
             A publicação no índice é automática (§5.4); não a faça você.
        - Pergunta: use memory_search para achar as páginas relevantes e
          responda citando as âncoras [[fonte: … p.N]]. Para perguntas que
          exigem varrer o acervo inteiro, use wiki_query.
        - Nunca afirme sem âncora.
        - Anexo que não seja .pdf/.md/.txt: não ingira; diga por quê.
```

`mode: [mention, has_file]` é o par mínimo: `has_file` acorda no upload do PDF,
`mention` permite perguntar.

**`mid_turn: queue` não é opcional.** O default é `cancel`
(`scopes/schema.py:123` — *"cancel is first because it is the default"*). Durante os ~5
minutos de um ingest, **qualquer mensagem de outra pessoa na thread cancela o turno**; e
como o manifesto só grava após sucesso (`wiki_tools.py:340`), a tentativa seguinte
recomeça do zero. Num canal com gente comentando, isso é quase garantido. `queue` segura
a mensagem até a sessão ficar ociosa; o Slack implementa os três mecanismos.

**O `delivery.prompt` é costurado no texto da mensagem do usuário**, não no system
prompt: `slack_connect.py:10498` faz `text = "\n\n".join([text, *appended])`. A
instrução do canal chega, portanto, como texto de usuário a cada turno disparado — o que
importa para escrevê-la (é instrução, não persona) e para o custo por turno.

`chat` é **escalar** (`schema.py:899` recusa qualquer valor que não seja string), logo
cada canal de papers exige seu próprio scope com o mesmo `prompt_append` copiado. Com um
canal isso não incomoda; com vários, é a repetição que a §10.2 resolve.

### 5.4 Busca híbrida  *(publicação + credencial)*

**Esta seção mudou por completo em relação à v1.** A v1 declarava
`memory.extraPaths` apontando para a wiki; isso não funciona, porque a chave alimenta um
gestor que o agente não usa (§3.1).

O índice que o agente consulta é o do kernel `lite`, e ele varre
`<agent workspace>/memory/*.md` — plano, sem recursão. Logo a wiki precisa ser
**publicada** lá.

**Passo de publicação — em código, não por prompt.** A v3 deste spec mandava o agente
espelhar via `prompt_append`. **Isso não funciona no Slack**, por duas razões verificadas:

- o modelo **não sabe onde fica o workspace**: a seção de diretórios só é injetada para
  os canais `tui`/`web`/`ws_client` (`runtime_prompt_rail.py:325`);
- copiar exigiria `bash cp` de um diretório **fora** do workspace, o que passa pelo
  `file_guard` e no Slack vira **botão de aprovação no meio do turno**. A demo dependeria
  de um clique.

Como `wiki_tools.py` já será editado para as mitigações da §5.1, a publicação vira ~5
linhas ali: após `[Success]`, copiar `wiki/*.md` para
`get_agent_workspace_dir()/memory/wiki__*.md`. Isso elimina o risco que a §8 marcava como
"alta" e torna o S1 ("sem intervenção manual") verdadeiro.

O espelhamento é arquivo-a-arquivo:

    <WIKI_ROOT>/.llm_wiki/wiki/*.md   →   <agent workspace>/memory/wiki__*.md

- arquivo a arquivo, **não** o diretório: o scan é `os.listdir` (`lite/internal.py:80`);
- prefixo `wiki__` para que as páginas não colidam com a memória de conversa e sejam
  fáceis de limpar;
- **cópia, nunca `mv` nem symlink**: o watcher não tem handler `on_moved`
  (`lite/manager.py:778`), então um arquivo movido não dispara reindexação;
- eventos no **primeiro segundo** após a inicialização são ignorados, e **não há sync
  periódico** de fallback se o watcher falhar (`lite/config.py:52`). Se a publicação
  acontecer logo após um restart, force uma nova escrita ou reinicie a sessão.

Quem executa: o próprio `wiki_ingest`, ao final de uma ingestão bem-sucedida.

**Credencial.** As três variáveis em `~/.jiuwenswarm/config/.env`:
`EMBED_API_KEY`, `EMBED_API_BASE`, `EMBED_MODEL`. Elas chegam ao kernel via
`config.yaml` → `interface_deep.py:6938`. Sem elas o `MemoryRail` **ainda é criado** (só
loga um warning) e a busca cai para **BM25 puro** — funciona, mas não é híbrida.

> Nota: o fallback direto por env dentro do jiuwenswarm lê `EMBED_BASE`/`EMBED_BASE_URL`
> (`embeddings.py:49`), nomes diferentes dos que o `config.yaml` usa. Preencher os três do
> `.env` é o caminho correto; não confiar no fallback.

**Dívida registrada:** o certo é o `lite/manager.py:954` repassar `extra_paths` ao
`list_memory_files` — duas linhas, mas dentro do `openjiuwen` fixado em `61becb17`.
Exigiria fork ou upgrade da dependência, fora de alcance em 2 dias. Ver §10.3.

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
