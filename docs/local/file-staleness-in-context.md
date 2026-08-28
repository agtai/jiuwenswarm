# File staleness in the model's context

Investigation, 2026-08-12. No code changed.

Prompted by a live incident: a SKILL.md was read into a running Slack session,
rewritten on disk by an external process, and the session was then asked about
its new contents. It answered from the copy already in its context and stated
the absence of the new marker as fact.

### Provenance of the citations

`file:line` citations are against `agent-core` and `jiuwenswarm`
(`local/deployed`, `65b1368dd`). The load-bearing citations were verified
against the venv the service actually runs —
`/home/jiuwenswarm/venvs/current`, a symlink to `2026-08-12-full-v5` — where
`filesystem.py`, `skill_tool.py` and `skill_use_rail.py` are byte-identical to
agent-core `7b0a3c49` (an ancestor of `local/deployed`). **The incident ran
against exactly the code cited here.**

One caveat, which is on-topic. The agent-core worktree was checked out at
`6e878cf2` when this investigation started and at `7b0a3c49` partway through —
another agent switched branches underneath it, and `skill_use_rail.py` changed
on disk at 15:33 while it was being read. Every cited line was re-verified
afterwards and all of them hold in both revisions, but the first diff of the
deployed venv produced a result the second diff contradicted. The investigation
into stale file contents was itself briefly working from stale file contents,
and noticed only because the two runs disagreed.

### The incident, from the live log

The three turns are in `~/.jiuwenswarm/agent/.logs/full.log`, session
`slack_T0BKJQBQ1AN_D0BL5N1K3C7_U0BLHQQBCCD`:

| Time | Turn |
|---|---|
| 15:15:51 | "What is the midsession-probe-zulu marker?" |
| 15:17:09 | "Read the SKILL.md file for the midsession-probe-zulu skill. Reply with exactly two things: the marker string it contains, and the absolute path you read it from." |
| 15:24:23 | "What is the secondary marker of the midsession-probe-zulu skill?" |

Note what the third turn contains: a skill **name**, no path, and no
instruction to read. The second turn had said "Read the SKILL.md file"
explicitly. This distinction matters in §7.

## 1. The direct answer

**Freshness tracking exists, and it is comprehensive — but every consumer of it
is a write gate. Nothing checks freshness for content that is only being read,
and nothing ever tells the model that something already in its context has
changed.**

There are three independent layers of staleness protection on the write path
and zero on the read path.

### The read-state ledger

`openjiuwen/harness/tools/filesystem.py:145` declares the ledger:

```python
_FILE_READ_REGISTRY: Dict[str, _FileReadState] = {}
```

`_FileReadState` (filesystem.py:67-82) records `mtime_ns`, `size_bytes`,
`is_partial`, an optional full-content snapshot, and cumulative read-coverage
ranges. `ReadFileTool` populates it on every successful text read
(filesystem.py:1000-1009, via `_record_read_state` at filesystem.py:540). The
comment at filesystem.py:143-144 states the design intent exactly:

> ReadFileTool populates it on successful text reads.
> EditFileTool consumes it to enforce "must read before edit" and detect external modifications.

That is the whole contract. The registry has exactly one consumer class —
the writers.

### Layer 1: read-before-write gate

- `EditFileTool` refuses to edit a path with no registry entry
  (filesystem.py:1550-1558): *"Error: File must be read before editing"*.
- `WriteFileTool` refuses unless the union of read ranges covers the whole file
  (filesystem.py:1130-1165), and tells the agent which line to resume from.

### Layer 2: modified-since-read check

Both writers compare the recorded `(mtime_ns, size_bytes)` against a fresh
`os.stat` and reject on mismatch:

- `WriteFileTool` — filesystem.py:1170-1180, *"Error: File has been modified
  since read: … Read it again before attempting to write it."*
- `EditFileTool` — filesystem.py:1561-1579, *"Error: File has been modified
  since read: … Read it again before attempting to edit it."*

Both fall back to a full content comparison before rejecting
(filesystem.py:1171, 1563-1569), so a touch that does not change bytes is not a
false positive. Both `pop` the registry entry on rejection, forcing a genuine
re-read.

### Layer 3: compare-and-swap at the filesystem layer

`EditFileTool` passes a SHA-256 of the bytes it matched against
(filesystem.py:1643):

```python
options={"expected_content_sha256": hashlib.sha256(raw).hexdigest()},
```

`LocalFsOperation.write_file` re-hashes under a file lock and aborts on
mismatch (`openjiuwen/core/sys_operation/local/fs_operation.py:441-458`),
closing the TOCTOU window between the layer-2 check and the write itself.

This is a genuinely well-built optimistic-concurrency stack. It is also, on the
evidence of the incident, aimed entirely at the wrong failure.

### What is not covered

- **`read_file` returns no freshness information to the model.** The tool
  output is `{content, file_path, line_count}` (filesystem.py:1011-1019), and
  `AbilityManager._build_tool_message_content`
  (`openjiuwen/core/single_agent/ability_manager.py:145-163`) short-circuits on
  `data["content"]` and discards every other field. The model sees the bytes
  and nothing else — no mtime, no hash, not even the path.
- **A second read of a changed file is silent.** `_record_read_state` detects
  the change (filesystem.py:566-569) — and uses it only to reset the coverage
  ranges. No warning is produced, because the only caller is bookkeeping.
- **`grep`, `glob`, `list_dir` record nothing.** `GrepTool`
  (filesystem.py:1823) puts matched file content into the context with no
  registry entry at all.
- **`skill_tool` records nothing.** See below.
- **The memory *tools* have no freshness concept, though the memory *index*
  does.** `openjiuwen/harness/tools/memory.py` is 173 lines of thin wrappers;
  the implementations in `openjiuwen/core/memory/lite/memory_tool_ops.py`
  record nothing on read (`read_memory_with_context`, :247) and skip the
  read-before-write gate entirely on write (:121). Separately, the memory
  *index* does real change detection — `sha256[:16]` plus mtime and size per
  file (`openjiuwen/core/memory/lite/internal.py:97-105`, `hash_text` at :163),
  used to skip unchanged files on re-index (`manager.py:964-971`). That
  freshness feeds `memory_search` results only; it never corrects a memory file
  already sitting in the context.
- **The registry is process-global, not per-session.** It is keyed on path
  alone (filesystem.py:145). Every session in the agent server process shares
  one entry per file. Session A reads a file; session B edits it; B's write
  refreshes the entry to the new mtime; A's subsequent edit now passes the
  layer-2 check against content A never saw. Layer 3 and `old_string` matching
  still catch most of the damage, so this is narrow rather than dangerous — but
  it is a real defect, and it is invisible today. *(The consequence is inferred
  from the process model; the process-global keying is a code fact.)*

## 2. `skill_tool` did not cache anything

This matters for blame allocation, so it is worth stating plainly.

`SkillTool.invoke` resolves the skill directory and reads the file from disk on
**every single call**
(`openjiuwen/harness/tools/skills/skill_tool.py:396-404`):

```python
file_path = str(Path(skill.directory) / relative_file_path)
read_file_result = await self.operation.fs().read_file(file_path)
```

There is no memoization, no TTL, no content cache. Had the model called
`skill_tool` a second time, it would have received the new marker. It also does
not populate `_FILE_READ_REGISTRY`, so SKILL.md bodies enter the context
completely untracked.

`SkillManager._registry`
(`openjiuwen/core/single_agent/skills/skill_manager.py:57`) caches skill
*metadata* — name, description, directory — never the body.

## 3. The near miss: the harness already detected this change and said nothing

This is the most important finding in the investigation.

`SkillUseRail` polls SKILL.md mtimes **on every model call**.
`before_model_call` calls `_refresh_skill_prompt_if_changed`
(`openjiuwen/harness/rails/skills/skill_use_rail.py:425`), which builds a
signature over every skill directory and its SKILL.md mtime and compares it to
the stored snapshot (skill_use_rail.py:446-474):

```python
entries.append((str(item.resolve()), skill_md_path.stat().st_mtime))
```

`BEFORE_MODEL_CALL` fires before every LLM call in the ReAct loop
(`openjiuwen/core/single_agent/agents/react_agent.py:846-850`, event defined at
`openjiuwen/core/single_agent/rail/base.py:380`), so this stat sweep runs on
every tool-loop iteration, not once per user turn. In this deployment that is
roughly a few dozen `stat()` calls per model call — a cost already being paid.

So during the incident, the harness **stat'd the rewritten SKILL.md, saw the
new mtime, and reloaded the skill** (skill_use_rail.py:193-196). The
information was in hand.

It then threw it away. `_update_runtime_skill_attachment` computes what to tell
the model purely as a **name-set difference** (skill_use_rail.py:590-593):

```python
additions = [skill for skill in self.skills if skill.name not in baseline_by_name]
removals  = [skill for skill in baseline_skills if skill.name not in current_by_name]
```

and `_build_runtime_skill_change_content` returns the empty string when there
are no additions, no removals, and no evolution text (skill_use_rail.py:631-632).

A skill **modified in place** — same name, new body — is by construction
invisible. The mechanism that renders "Newly available skills:" / "新增可用
Skill：" (skill_use_rail.py:639, 661; introduced around `7b0a3c49`, snapshot
signature added in `768dfa6c`) has no "changed" branch at all.

The harness was one `elif` away from catching this incident.

## 4. The context engine makes it worse, in one specific place

The context engine rewrites already-emitted tool results routinely. Every
`ContextProcessor` may edit history in place — the contract is
`ContextEvent.messages_to_modify`
(`openjiuwen/core/context_engine/processor/base.py:30-34`), and processors call
`context.set_messages(...)` after editing by index. **So the machinery to
retroactively rewrite a `read_file` result already exists and is in active
use.** It is simply never driven by file state; every decision is made from
message position, token count, or tool name.

Three behaviours matter here.

**`read_file` is protected from offload.** Both `MessageOffloader`
(`processor/offloader/message_offloader.py:54`) and the
`MessageSummaryOffloader` actually configured in this deployment (:165) list
`read_file` in `protected_tool_names` by default, so file bodies persist in
context rather than being swapped for a handle. Good for continuity — and it is
also why the stale copy was still verbatim in context seven minutes later. The
design decision that preserves file reads is the same one that preserves stale
file reads; there is no mechanism that distinguishes them.

**`MicroCompactProcessor` clears old file reads by position.** Its config
docstring says *"Clear stale tool results while keeping recent ones per tool"*
(`processor/compressor/micro_compact_processor.py:22`), and `read_file`, `grep`
and `glob` are in the default `compactable_tool_names` (:32). But "stale" here
means **old in the transcript**, not stale relative to disk — the selection is
purely positional (:119-134), replacing content with
`"[Old tool result content cleared]"` (:18). The word is already taken by an
unrelated concept, which is worth knowing before naming anything new.

**The reinjection builder re-asserts stale bodies as fresh reads.** This is the
sharpest finding in the context engine. After a compaction,
`render_read_file_snapshots`
(`processor/forked/compressor/reinjection/builders.py:597-620`) re-injects file
contents under a header:

```python
lines = [
    f"Recently read file: {snapshot.file_path}",
    f"Lines returned: {snapshot.line_count if ... else 'unknown'}",
]
```

The content is scraped from the **old ToolMessage text in the transcript**
(`parse_read_file_result` over `find_tool_result_text`, :562). It never re-reads
`snapshot.file_path` and never stats it. Reinjection is enabled by default in
`round_level_compressor.py:41`, `current_round_compressor.py:43`, and
`dialogue_compressor.py:42`.

So a compaction can take a file body that was already stale and re-present it
to the model under a header asserting it was *recently read*. The path is right
there in the snapshot; one `stat()` would settle it.

**And there is a `skill_tool`-specific version of the same thing.** The
`"skills"` reinject builder (`builders.py:67-90`) is not about skill metadata —
it reconstructs SKILL.md bodies. `extract_skill_tool_snapshot`
(builders.py:488-500) walks the transcript for prior `skill_tool` calls, pulls
`skill_content` and `skill_directory` out of the **old tool result**, and emits:

```python
return f"Skill: {skill_name}\nPath: {directory}/SKILL.md\n\n{content.strip()}"
```

with a `read_file` fallback for paths ending in `skill.md`
(`extract_read_file_skill_snapshot`, :503-515). `reinject_recent_skills`
defaults to 3, and `"skills"` is in the default `reinject_builder_names` of all
three forked compressors — including the `DialogueCompressor` configured in
this deployment (`dialogue_compressor.py:42`).

This is the incident's exact file, tool, and code path. A compaction in that
session would have re-emitted the stale `midsession-probe-zulu` body, labelled
with its real absolute path, as a current statement of what that skill
contains — while `skill_tool` itself, three lines of code away, would have
returned the correct new content on any fresh call.

Nor is this confined to the forked tree. The mainline `FullCompactProcessor`
reinjects skill-read rounds too (`processor/compressor/util.py:250-275`, config
at `full_compact_processor.py:220-226`, same default of 3), with
`reinject_file_tool_names` covering `read_file`, `write_file`, `edit_file`,
`glob` and `grep`. Every compaction path in the codebase re-asserts remembered
file content, and none of them stats anything.

**Offloaded content has no identity.** Offload handles are `uuid4().hex`
(`processor/base.py:258`), unrelated to content. The only `hashlib` uses under
`context_engine/` are `sha256(session_id)[:12]` for filenames. There is no
version counter, generation number, or content digest on any offloaded or
compacted message. Reload (`context/message_buffer.py:111-157`) restores the
frozen JSON snapshot of the *message*, not the source file it described — and
`enable_reload` defaults to `False` (`schema/config.py:102`).

## 5. Adjacent machinery that could be reused

Ranked by how close it already is.

| Mechanism | Where | Reusable? |
|---|---|---|
| SKILL.md mtime poll on every model call | skill_use_rail.py:446-474 | **Yes — already running.** Needs a "changed" branch beside additions/removals. |
| Runtime-changes prompt attachment | skill_use_rail.py:582-611 | **Yes.** The delivery vehicle for a staleness notice already exists, is session-scoped, and self-clears. |
| Context-file re-read per model call | `openjiuwen/harness/prompts/sections/context.py:105-192` | **Yes — the closest precedent in the repo.** AGENT.md / SOUL.md / USER.md are re-read on *every model call*, cached on `(mtime_ns, size)`, and deliberately not cached under a sandbox. Exactly the pattern wanted, already accepted, scoped to a fixed file set. |
| `_FILE_READ_REGISTRY` | filesystem.py:145 | **Yes.** Already holds `(mtime_ns, size_bytes)` per path; needs a reader that is not a write gate, and per-session keying. |
| Retroactive tool-result rewriting | `context_engine/processor/base.py:30-34` | **Yes, mechanically** — but see §6 on prompt-cache cost. Exists and is used; never driven by file state. |
| `PromptAttachment` schema | prompt_attachment_manager.py:39-56 | **Partly.** Declares `kind = FILE`, `content_path`, `content_sha256` — but `content_sha256` hashes the attachment's own text (:607), and `add_file_reference` (:440-462) stores only a path and a summary. No producer sets `content_path`. |
| `PromptAttachmentKind.WORKSPACE_DELTA` | prompt_attachment_manager.py:37 | Declared and **never produced** — one grep hit repo-wide, the definition. Scaffolding for exactly this, unused. |
| Memory index hash+mtime+size | `core/memory/lite/internal.py:97-105` | Precedent. Real change detection; feeds search, not context. |
| mtime+size parse cache | `jiuwenswarm/common/config.py:142-167` | Precedent. Same `(mtime_ns, size)` stamp pair, invalidating a YAML parse. |
| mtime cache for security rules | `harness/security/tiered_policy.py:87-109` | Precedent. Same pattern again. |
| `expected_content_sha256` CAS | fs_operation.py:441-458 | Write-path only; not applicable to reads. |
| Checkpoint store | `~/.jiuwenswarm/agent/.checkpoint/checkpoint.db` | **No.** Single `kv_store` table, 202 rows of agent state blobs. No file identity anywhere. |
| File watcher | `core/memory/lite/manager.py:711-786` | **No — effectively dead code.** Uses `watchdog`, which is absent from both `pyproject.toml` and `uv.lock`, so the `ImportError` branch (:783) always fires. Even when live it only re-indexes memory `.md` for search. |

Two things stand out. First, the repo has independently reinvented the
`(mtime_ns, size)` freshness stamp **four times** — context files, config YAML,
security rules, skill metadata — which says the pattern is well understood here
and merely never pointed at tool results. Second, `WORKSPACE_DELTA` is a
declared-and-never-produced enum member: someone anticipated exactly this notion
and never wired a producer.

One counter-example worth flagging: `_FILE_READ_REGISTRY` is imported in exactly
two places repo-wide. The second is
`context_engine/context/session_memory_manager.py:439-449`, where
`_prime_notes_file_as_read` **pre-seeds** the registry so a sub-agent can edit a
notes file without reading it first. That is the freshness ledger being used to
*bypass* the gate. It is defensible for a file the harness itself just wrote,
but it means the registry is not a reliable record of "what this agent has
actually seen" — which matters for anything built on top of it.

## 6. Prompt caching constrains the design

`openjiuwen/core/foundation/llm/model_clients/openrouter_model_client.py:154-177`
places `cache_control` breakpoints on the tool list, the system prompt, a
stable prefix message, and the tail. This has a hard consequence for any fix:

- **Appending** a staleness notice near the tail is cheap.
- **Rewriting a historical tool result** in place invalidates the cached prefix
  from that point on, and re-bills every token after it.

Any design that mutates an already-emitted tool result is paying a large,
recurring, invisible cost. This rules out the most obvious-sounding fix.

## 7. Verdict on the timestamp proposal

The proposal: *"if a prompt asks about a file, the harness could detect that and
check file timestamps to force a context update."*

The instinct is right — the harness has information the model does not, and
should use it. The specific formulation has four problems, roughly in order of
severity.

1. **"Asks about a file" is intent detection, not a lookup.** Deciding whether
   a turn is about a file requires either a classifier or a model call before
   the model call. It has both false negatives (the incident: the user said
   "the secondary marker", naming no path) and false positives (any mention of
   the word "file"). Building a gate on an unreliable predicate produces
   unreliable protection, which is worse than none because it is trusted.
2. **The incident referenced a skill by name, not a path.** The failing turn was
   *"What is the secondary marker of the midsession-probe-zulu skill?"* — no
   path, no file extension, not even the word "file". Path extraction would
   have found nothing. The turn that *did* work said "Read the SKILL.md file",
   which is exactly the case a naive detector handles and exactly the case that
   needs no help.
3. **"Force a context update" is ambiguous and the expensive reading is the
   natural one.** Re-reading and *replacing* the earlier tool result breaks
   prompt caching (§6) and leaves the transcript claiming the model saw
   something it never saw. Re-reading and *appending* is safe but silently
   re-bills the file on every turn that trips the heuristic.
4. **Stale is often fine.** Most files do not change mid-session. Unconditional
   re-reading burns tokens to confirm nothing happened, and for a large file
   the re-read may itself be truncated.

### The better variant

Two changes, neither of which requires guessing intent. **Both are shipped
designs in other harnesses rather than novel proposals** — see §10, which
corrects an earlier draft of this document on exactly that point.

**(a) Stamp reads with their identity.** Include mtime and a short content hash
in what `read_file` and `skill_tool` return to the model — a single header
line. The model then has the freshness information rather than the harness
having to act on the model's behalf, and a later "is this current?" becomes
answerable rather than guessable. Cost is a few tokens per read. This requires
touching `ability_manager.py:145-163`, which currently discards everything
except `content` — that discard is the actual blocker, and it is a
harness-wide constraint worth knowing about independently.

Prior art: Claude Code does precisely this for its *memory* store, where reads
return a 12-character version token and writes require `if_version` (§10).
Notably it does **not** do it for disk files, where the marker stays hidden
from the model — which is the gap Codex issue #22384 asks to close.

**(b) Emit a changed-file notice from machinery already running.** On the
existing `before_model_call` sweep, diff the current stamps against what was
read into *this session's* context. When a path whose content is in context has
changed, append one line to the runtime attachment:

> `midsession-probe-zulu/SKILL.md` changed on disk since you read it. Re-read it before answering questions about its contents.

This inverts the proposal's trigger, and that is the point. Instead of *"the
user asked about a file → check if it is stale"* (needs intent detection, fails
on the incident), it becomes *"a file in context changed → say so"* (needs only
a stat, catches the incident). It is strictly cheaper: no classifier, no
speculative re-read, no cache invalidation. It fires rarely, because files
rarely change mid-session — which is exactly the property that makes the
proposal's unconditional re-read wasteful and makes this notice nearly free.

It does not *force* anything, and should not. It gives the model a reason to
re-read and leaves the decision there, which is the same contract the write
gate already uses successfully: the harness detects, reports, and lets the
agent act. Claude Code, Cline and Roo Code all landed on this same
detect-and-announce contract independently (§10); none of them blocks a read.

**Scope note.** (b) is only sound for content the session actually read.
Tracking every file the process ever touched would produce notices about files
this session never saw. This is the per-session-keying problem from §1 —
fixing it is a prerequisite, not an optional extra.

## 8. Where the blame lies

Four candidate causes were proposed; one is disproved, and the investigation
added a fifth.

**Harness gap — yes, and it is the substantive one.** Not because a harness
must guarantee freshness; because *this* harness detected the change, on the
correct file, at the correct moment, and had an established channel for telling
the model. The gap is the missing "changed" branch at
skill_use_rail.py:590-593, not an absent subsystem. The wider gap is
architectural: freshness data exists (`_FILE_READ_REGISTRY`) and is exposed
exclusively to write gates.

**Expected LLM behaviour — yes, and it is not a defence.** A model with a
file's contents in context will answer from them; re-reading unprompted is not
the behaviour anyone wants by default. The model behaved correctly given its
inputs. The failure is that its inputs were wrong and nothing said so. The
sharp edge is not that it was wrong but that it was *confidently* wrong: it
reported the absence of the second marker as a positive fact about the
documentation. A stale copy is indistinguishable from a current one, so there
was no signal from which to hedge. This is an argument for the harness
supplying the signal, not for prompting the model to distrust its context.

**`skill_tool` caching — no. Ruled out.** `skill_tool` re-reads from disk on
every call (skill_tool.py:397). No cache exists at any layer; `SkillManager`
caches metadata only. A second call would have returned the new content. This
hypothesis is disproved by the code.

**Context-engine amplification — armed in this deployment, unconfirmed for this
incident.** The log shows the configured processors are
`['MessageSummaryOffloader', 'DialogueCompressor']`, and
`DialogueCompressor.reinject_builder_names` includes `"read_file"`
(`processor/forked/compressor/dialogue_compressor.py:42`). So the reinjection
path described in §4 is live here, not theoretical — and its `"skills"` builder
targets `skill_tool` results specifically. Whether a compaction actually ran in
the seven minutes between the read (15:17) and the failing question (15:24) was
**not** established from the logs; for this incident this remains unconfirmed.
But had one run, `extract_skill_tool_snapshot` would have re-emitted the stale
`midsession-probe-zulu` body under `Skill: … / Path: …/SKILL.md`, converting a
merely-old context entry into an affirmative and false claim of currency. That
path needs no model error at all, and it is loaded in production today.

**Test-design artefact — partly, and it cuts the wrong way.** Asking the same
session twice is what made the stale copy authoritative. But this is precisely
the shape of the real hazard in this deployment: long-lived Slack sessions,
skills edited by other agents and by the operator mid-session, and a
`before_model_call` sweep that has been watching those exact files the whole
time. The test did not manufacture an artificial condition; it reproduced the
normal one.

## 9. If something is built

Smallest change that would have caught the incident, in dependency order.

1. **Per-session read tracking.** Key `_FILE_READ_REGISTRY` by session, or add
   a session-scoped set of read paths beside it. Prerequisite for anything
   else, and independently fixes the cross-session write-gate hole in §1.
   *Small; the awkward part is threading session identity into the module-level
   registry, and the tests that assume the global.*
2. **A "changed" branch in the runtime attachment.** At
   skill_use_rail.py:590-593, alongside `additions` and `removals`, compute
   skills whose SKILL.md stamp changed and which this session has loaded. Emit
   one line. Reuses the existing sweep, the existing attachment, and the
   existing self-clearing behaviour. *Small — this is the incident fix.*
   Four details borrowed from the survey (§10):
   - **Exclude the agent's own writes** (Cline's `recentlyEditedByCline`).
     `WriteFileTool` and `EditFileTool` already refresh the registry after
     writing (filesystem.py:1199, 1651), so the discrimination is free.
   - **Do not exclude partial reads.** This is Claude Code's residual hole;
     openjiuwen already tracks `is_partial` and read ranges
     (filesystem.py:72-82) and is better placed to handle them.
   - **Bound the snippet, not the notice.** Claude Code caps per-turn diff
     snippets and degrades to "use the Read tool if you need the current
     content" rather than dropping the warning.
   - **Pick a cadence.** Cline injects on resume, Roo every turn, Claude Code
     per query iteration. Every model call is the most expensive of the three
     and buys little; per user turn is the sensible default here.
3. **Generalise beyond skills.** Extend the same before-model-call diff to
   every path in the session's read set, not just SKILL.md. *Medium: needs a
   bounded stat budget so a session that read a thousand files does not stat
   them all per model call — cap it, or stat only paths read in the last N
   turns.*
4. **Freshness stamps in read output.** Requires relaxing
   `ability_manager.py:145-163`, which discards every field except `content`.
   *Medium, and broader than this problem — that discard affects every tool
   that wants to return structured metadata alongside text.* Worth doing on its
   own merits; not required for 1-3.

Separately, and independent of the above:

5. **Stop the reinjection builders re-asserting stale bodies.** Both
   `render_read_file_snapshots`
   (`processor/forked/compressor/reinjection/builders.py:597-620`) and
   `extract_skill_tool_snapshot` (:488-500) already hold the absolute path they
   are about to make a claim about. Either `stat()` it and drop or flag the
   snapshot when it changed since the read that produced it, or soften the
   headers so they stop asserting currency. *Small — a stat and a conditional
   per builder.* This is a bug on its own terms: the headers make a freshness
   claim that nothing checks. These two functions are the only place in either
   codebase that actively manufactures the failure mode rather than merely
   failing to prevent it, and they are the cheapest thing here to fix.

Steps 1 and 2 together are the honest scope of "fix the incident". Step 5 is
worth doing regardless of whether anything else here is. Steps 3 and 4 are the
general mechanism, and should be justified separately rather than smuggled in
behind the incident.

## 10. What other harnesses do

**A first pass at this section concluded that only Cline warns the model about
stale context. That was wrong, and the correction changes the recommendation.**
Claude Code does it too, more aggressively than Cline, and it also ships the
freshness-stamp design proposed as variant (a). Both halves of §7 turn out to
be existing designs rather than novel proposals.

The Claude Code findings below come from reading the shipped binary at
`~/.local/share/claude/versions/2.1.228` (a 308 MB Bun-compiled ELF). None of
it is publicly documented. The strings quoted here were verified directly:
`was modified, either by the user or by a linter` (2 hits),
`File has been modified since read` (6), `File has not been read yet` (10),
`Wasted call` (1), `is now stale relative to disk` (1),
`tengu_edit_tool_stale_read` (2), `if_version` (11). Treat this as accurate for
2.1.228 and unsupported for any other version.

| Harness | Mechanism | Trigger | Protects a *question*? |
|---|---|---|---|
| **Claude Code (write)** | Read-state ledger keyed on **mtime** (`statSync(e).mtimeMs`), with a Bun non-cryptographic hash as a secondary equality check. Rejects with *"File has been modified since read, either by the user or by a linter"* | Only edits/writes | No |
| **Claude Code (read)** | `edited_text_file` attachment: walks the read ledger, **re-reads any file whose mtime advanced, diffs it, and injects the diff into context** | Per query iteration — **mid-turn**, not just at turn boundaries | **Yes** |
| **Claude Code (memory)** | True OCC with the marker **exposed to the model**: reads return a 12-character version token, writes require `if_version`, `new` is the create sentinel | Memory reads/writes | Yes |
| **Cline** | `FileContextTracker` — a **chokidar watcher per tracked file**, not mtime polling. Self-edits suppressed via `recentlyEditedByCline`. Ledger records `record_state: active\|stale` | Watcher marks; warning injected on task resume | **Yes**, advisory |
| **Roo Code** | Same lineage; drains `getAndClearRecentlyModifiedFiles()` into `environment_details` as *"# Recently Modified Files"* | **Every turn** | **Yes**, advisory |
| **Gemini CLI** | SHA-256 compare, but only inside `attemptSelfCorrection()` after an edit has already failed. Happy path re-checks nothing. In-tree `TODO` acknowledges the race | Failed edits only | No |
| **OpenAI Codex** | **None.** No mtime, hash, or ledger in `apply-patch`. Prompt actively discourages re-reading: *"don't waste tokens re-reading files after apply_patch"* | — | No |
| **Cursor** | Nothing documented | — | No |
| **Zed** | **None.** Request declined | — | No |
| **Aider** | No ledger; `get_files_content()` calls `io.read_text()` **on every message**, regenerating context from disk each turn. Safety net is git auto-commit, not concurrency control | Every turn | N/A by design |
| **openjiuwen** | Three write-path layers (§1); mtime sweep that detects the change and discards it (§3) | Only edits/writes | **No** |

Five things follow.

**Both halves of the §7 recommendation are shipped designs.** Variant (b) — detect
via file identity, announce the change in context, let the model decide — is
what Claude Code's `edited_text_file` attachment, Cline's `FileContextTracker`
and Roo's `environment_details` block all do. Variant (a) — stamp reads with
their identity so the model can see freshness — is what Claude Code does for
its *memory* store via `if_version` tokens. Neither is speculative. The
recommendation is to adopt a convergent design, not to invent one.

**The gap here is squarely on the wrong side of the industry line.** openjiuwen
sits with Codex, Cursor and Zed — write gate only — while the three harnesses
that solve it did so with mechanisms openjiuwen already has running. That is
the uncomfortable part: the mtime sweep exists (§3), the injection channel
exists (§5), and they are not connected.

**Claude Code's exact wording is worth copying.** Its notice is instructive
about *tone*, not just mechanism:

> `Note: <filename> was modified, either by the user or by a linter. This change was intentional, so make sure to take it into account as you proceed (ie. don't revert it unless the user asks you to). Don't tell the user this, since they are already aware.`

It asserts intentionality (pre-empting the model "fixing" the change), it
forbids reverting, and it suppresses chatter. When the diff does not fit a
per-turn snippet budget it degrades gracefully rather than dropping the signal:

> `The diff was omitted because other modified files in this turn already exceeded the snippet budget; use the Read tool if you need the current content.`

That budget is the answer to the cost objection in §7: bound the *snippet*, not
the notice.

**Claude Code's residual hole is the one to avoid inheriting.** The refresh
attachment **skips partial reads** — anything read with `offset`/`limit` is
excluded — while the write gate treats a partial view as not-read-at-all. So
the unguarded path is: partial read → question answered from it → no refresh,
no warning. openjiuwen already tracks `is_partial` and cumulative read ranges
(filesystem.py:72-82), so it is better placed than Claude Code to get this
right. It should not copy the exclusion.

**The read-dedup caution still stands, in weakened form.** Claude Code also
ships a re-read suppressor — *"Wasted call — file unchanged since your last
Read. Refer to that earlier tool_result instead."* — whose predicate in 2.1.228
is mtime equality against disk, so an external write should defeat it. Issue
#60684 reports it firing after a genuine external edit; that report is against
2.1.144 and was closed as not planned, so grade it as version-specific and
unconfirmed against current code. The design lesson survives regardless: a
token-saving read suppressor and a staleness detector are the same mtime
comparison pointed in opposite directions, and shipping the former without the
latter is how a stale answer becomes unrecoverable. openjiuwen's `skill_tool`
currently re-reads unconditionally (§2); if that is ever optimised, the
staleness path must land first.

Sources — code and binaries: Claude Code 2.1.228 shipped binary (strings
verified locally, undocumented);
[Cline `FileContextTracker.ts`](https://github.com/cline/cline/blob/main/apps/vscode/src/core/context/context-tracking/FileContextTracker.ts);
[Roo `getEnvironmentDetails.ts`](https://github.com/RooCodeInc/Roo-Code/blob/main/src/core/environment/getEnvironmentDetails.ts);
[gemini-cli `edit.ts`](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/tools/edit.ts);
[codex `apply-patch/src/lib.rs`](https://github.com/openai/codex/blob/main/codex-rs/apply-patch/src/lib.rs);
[codex apply_patch prompt](https://github.com/openai/codex/blob/main/codex-rs/core/prompt_with_apply_patch_instructions.md);
[aider `base_coder.py`](https://github.com/Aider-AI/aider/blob/main/aider/coders/base_coder.py).

Issues and docs:
[claude-code #28383](https://github.com/anthropics/claude-code/issues/28383),
[#60684](https://github.com/anthropics/claude-code/issues/60684),
[#3513](https://github.com/anthropics/claude-code/issues/3513),
[#25775](https://github.com/anthropics/claude-code/issues/25775);
[openai/codex #22384](https://github.com/openai/codex/issues/22384) (open — asks
for exactly this: *"Codex should treat file contents in context as snapshots
with modification metadata, not as permanently reliable truth"*);
[gemini-cli #9024](https://github.com/google-gemini/gemini-cli/issues/9024)
(closed, not planned);
[zed #53590](https://github.com/zed-industries/zed/issues/53590) (closed, no
maintainer reply);
[Roo-Code #10653](https://github.com/RooCodeInc/Roo-Code/issues/10653);
[Cursor tools docs](https://cursor.com/docs/agent/tools);
[aider git docs](https://aider.chat/docs/git.html),
[repomap](https://aider.chat/docs/repomap.html).

Windsurf, Continue, Copilot agent mode and OpenHands were searched and nothing
was established either way — treat them as unknown, not as confirmed absent.
