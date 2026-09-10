# coding: utf-8
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from typing import Any, List, Optional, Dict
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import logging

from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
from openjiuwen.core.foundation.tool import Tool, ToolCard, McpServerConfig, tool
from openjiuwen.core.single_agent.rail.base import AgentRail
from openjiuwen.core.single_agent.schema.agent_card import AgentCard
from openjiuwen.core.foundation.tool.exposure import ToolExposure
from openjiuwen.core.sys_operation import SysOperation
from openjiuwen.core.foundation.kv_cache import resolve_session_lineage
from openjiuwen.core.session import get_current_session
from openjiuwen.core.session.agent import Session
from openjiuwen.harness.deep_agent import DeepAgent
from openjiuwen.harness.factory import create_deep_agent
from openjiuwen.harness.prompts import resolve_language
from openjiuwen.harness.rails import SysOperationRail
from openjiuwen.harness.schema.config import SubAgentConfig
from jiuwenswarm.common.config import (
    get_config,
    get_configured_read_image_multimodal,
    get_default_models,
)
from jiuwenswarm.common.kv_cache_affinity_config import (
    build_kv_cache_affinity_config,
    model_provider,
)
from jiuwenswarm.common.reasoning_injector import build_reasoning_model_request_kwargs
from jiuwenswarm.common.utils import get_agent_sessions_dir, get_agent_workspace_dir


logger = logging.getLogger(__name__)

# Constants for wiki workspace resolution
DEFAULT_WIKI_DIR = ".llm_wiki"

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


#: Prefix for a wiki page copied into the agent's memory directory. It keeps the pages
#: apart from conversation memory, makes them greppable, and cannot collide with the
#: dated session files the memory index also stores.
WIKI_PUBLISH_PREFIX = "wiki__"

#: Pages that are navigation rather than knowledge, and are kept out of the memory
#: index. They name every topic in the wiki, so they match almost any query and crowd
#: out the pages that actually answer it; and their chunks carry no source anchor, so a
#: retrieval landing on one leaves the agent with nothing to cite.
NON_PUBLISHED_PAGES: frozenset[str] = frozenset({"index.md", "log.md"})


def build_query_prompt(question: str, allow_write: bool = False) -> str:
    """The instruction ``wiki_query`` gives its subagent.

    **Search first, read second.** The subagent used to be told only to answer "strictly
    based on `wiki/`", with no method, so it listed the directory and read every page.
    That is affordable at twenty pages and not at two hundred: the wiki is a compounding
    artefact, so the naive version gets slower and less reliable with every source
    ingested, which is the opposite of what the design promises.

    ``index.md`` first because it is the catalogue -- one line per page -- so it narrows
    the candidates for the cost of a single read. ``grep`` second for the terms the
    question actually uses. Only then whole pages, and only the ones that survived.

    **Read-only unless the caller says otherwise.** The write-back is kept, because an
    analysis worth having is worth filing, and it stays bound to ``schema/AGENT.md`` so a
    filed page follows the same anchoring rules as the rest of the wiki. What changed is
    the default. Offering it unconditionally put the decision in the wrong place: a
    caller that wants a frozen library -- the papers channel during a demo, say -- states
    that in its own prompt, which addresses the main agent and never reaches this
    subagent. A real run duly created a page, registered it in ``index.md`` and appended
    to ``log.md`` while merely answering a question. Freezing is the caller's policy, so
    it belongs in the caller's argument, not in prose the caller cannot see.
    """
    return (
        f"Answer this question strictly from `wiki/`: '{question}'.\n"
        "Work in this order, and do NOT read the whole wiki:\n"
        "1. read `wiki/index.md` to see which pages exist and pick the candidates;\n"
        "2. `grep` the wiki for the question's key terms to catch pages the index"
        " summary did not reveal;\n"
        "3. read in full ONLY the pages steps 1 and 2 selected.\n"
        "Cite the `[[fonte: ...]]` anchors of every claim you use; if a page carries no"
        " anchor for something, say so rather than asserting it.\n"
        + (
            "If the answer forms a genuinely new insight worth keeping, you may write it"
            " back as a wiki page -- but read `schema/AGENT.md` first and follow its"
            " rules, anchors included."
            if allow_write
            else "This is a read-only query: do NOT create, edit or delete any file."
            " If you notice a gap or inconsistency in the wiki, report it in your answer"
            " instead of repairing it on disk."
        )
    )


def publish_wiki_pages(wiki_dir: Path, memory_dir: Path) -> List[Path]:
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

    # A wiki published before this rule left index/log copies behind; they would
    # otherwise stay in the index for ever, since nothing else ever deletes them.
    for name in NON_PUBLISHED_PAGES:
        stale = memory_dir / f"{WIKI_PUBLISH_PREFIX}{name}"
        if stale.exists():
            stale.unlink()

    published: List[Path] = []
    for page in sorted(wiki_dir.glob("*.md")):
        if not page.is_file() or page.name in NON_PUBLISHED_PAGES:
            continue
        target = memory_dir / f"{WIKI_PUBLISH_PREFIX}{page.name}"
        shutil.copyfile(page, target)
        published.append(target)
    return published

DEFAULT_WIKI_AGENT_SYSTEM_PROMPT_EN = (
    "You are an LLM Wiki Maintainer. You manage a workspace consisting of three primary directories:\n"
    "1. `sources/`: where immutable raw text and PDF files are placed.\n"
    "2. `wiki/`: the destination for compiled, structured markdown entity pages.\n"
    "3. `schema/`: contains an `AGENT.md` document defining the architecture and rules.\n\n"
    "CRITICAL RULES:\n"
    "- Always read `schema/AGENT.md` first to understand operational rules.\n"
    "- Always read `wiki/index.md` before making modifications to ensure you append new items properly.\n"
    "- You MUST update `wiki/log.md` with an entry describing every major action or ingestion you perform!\n"
    "- To ingest PDFs, use the `read_pdf` tool. For large documents, start by reading the FIRST page to"
    " understand the structure and total page count. Then, read subsequent pages in chunks as needed to"
    " ensure complete synthesis without exceeding your context limit.\n"
    "- Prioritize ingesting new, unprocessed files from `sources/` before performing secondary cross-linking.\n"
    "- When calling tools (especially `edit_file`), you MUST use the exact parameter names defined in the"
    " tool schema (e.g., `old_string`, `new_string`). Do not append symbols like `=` to keys, and do not provide lists"
    " or indices as string values."
    " Only use `replace_all: true` if you are providing the COMPLETE new content for a section.\n"
    "- DO NOT create subdirectories within `wiki/`. Always save pages directly in the `wiki/` root folder."
)

DEFAULT_WIKI_AGENT_SYSTEM_PROMPT_CN = (
    "你是 LLM Wiki 维护者。你负责管理一个包含三个主要目录的工作区：\n"
    "1. `sources/`：存放不可变的原始文档和 PDF。\n"
    "2. `wiki/`：存放编译后结构化的 markdown 主题页面。\n"
    "3. `schema/`：包含一个 `AGENT.md` 文档，定义了架构和操作规则。\n\n"
    "关键规则：\n"
    "- 务必首先读取 `schema/AGENT.md`，以了解操作规范。\n"
    "- 在进行任何修改之前，务必先读取 `wiki/index.md` 和 `wiki/log.md`，以确保正确追加新项并维护一致的交叉引用。\n"
    "- 对于 PDF 摄取，请使用 `read_pdf` 工具。对于大型文档，请先阅读第一页以了解结构和总页数，然后根据需要分块阅读后续页面，以确保在不超出上下文限制的情况下完成综合。\n"
    "- 在对现有 `wiki/` 页面进行二次交叉引用或 lint 之前，优先从 `sources/` 摄取新的、未经处理的文件。\n"
    "- 调用工具（特别是 `edit_file`）时，必须使用工具架构中确化的准确参数名称（例如 `old_string`、`new_string`）。不要在键名后添加 `=` 等符号，也不要提供列表或索引作为字符串值。"
    "仅当你为某个部分提供完整的全新内容时，才使用 `replace_all: true`。\n"
    "- 不要在 `wiki/` 中创建子目录。始终将页面直接保存在 `wiki/` 根文件夹中。"
)

DEFAULT_WIKI_AGENT_SYSTEM_PROMPT: Dict[str, str] = {
    "cn": DEFAULT_WIKI_AGENT_SYSTEM_PROMPT_CN,
    "en": DEFAULT_WIKI_AGENT_SYSTEM_PROMPT_EN,
}

DEFAULT_WIKI_AGENT_DESCRIPTION_EN = (
    "You are a Wiki Maintainer agent."
    " You ingest raw documents and continuously compile them into a structured markdown wiki knowledge base."
)

DEFAULT_WIKI_AGENT_DESCRIPTION_CN = (
    "你是 Wiki 维护代理。负责摄取原始文档，并不断将它们编译成结构化的 markdown Wiki 知识库。"
)

DEFAULT_WIKI_AGENT_DESCRIPTION: Dict[str, str] = {
    "cn": DEFAULT_WIKI_AGENT_DESCRIPTION_CN,
    "en": DEFAULT_WIKI_AGENT_DESCRIPTION_EN,
}


class _SourceManifest:
    """Tracks ingested sources by SHA-256 content hash."""

    _MANIFEST_NAME = "manifest.json"

    def __init__(self, sources_dir: Path, sys_operation: Optional[SysOperation] = None) -> None:
        self._path = sources_dir / self._MANIFEST_NAME
        self._sys_op = sys_operation
        self._data: Dict[str, Dict[str, str]] = {}

    async def ensure_initialized(self) -> None:
        self._data = await self._load()

    @staticmethod
    def sha256_of(file_path: Path) -> str:
        if not file_path.is_file():
            raise ValueError(f"Path is not a valid file: {file_path}")
        h = hashlib.sha256()
        with file_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def is_known(self, sha256: str) -> bool:
        return sha256 in self._data

    def get(self, sha256: str) -> Optional[Dict[str, str]]:
        return self._data.get(sha256)

    async def record(self, sha256: str, name: str, destination: Path) -> None:
        if sha256 in self._data:
            return
        self._data[sha256] = {
            "name": name,
            "destination": str(destination),
            "ingested_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(
                timespec="seconds"
            ),
        }
        await self._save()

    def all_entries(self) -> Dict[str, Dict[str, str]]:
        return dict(self._data)

    async def _load(self) -> Dict[str, Dict[str, str]]:
        if self._sys_op:
            res = await self._sys_op.fs().read_file(str(self._path))
            if res.code == 0:
                try:
                    return json.loads(res.data.content)
                except json.JSONDecodeError:
                    return {}
            return {}
        else:
            if not self._path.exists():
                return {}
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}

    async def _save(self) -> None:
        if not self._path.parent.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)

        content = json.dumps(self._data, indent=2, ensure_ascii=False)
        if self._sys_op:
            await self._sys_op.fs().write_file(str(self._path), content)
        else:
            self._path.write_text(content, encoding="utf-8")


class LLMWiki:
    def __init__(
        self,
        workspace: str | Path,
        model: Model,
        *,
        session_id: Optional[str] = None,
        parent_session_id: Optional[str] = None,
        card: Optional[AgentCard] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Tool | ToolCard]] = None,
        mcps: Optional[List[McpServerConfig]] = None,
        subagents: Optional[List[SubAgentConfig | DeepAgent]] = None,
        rails: Optional[List[AgentRail]] = None,
        enable_task_loop: bool = True,
        max_iterations: int = 15,
        skills: Optional[List[str]] = None,
        backend: Optional[Any] = None,
        sys_operation: Optional[SysOperation] = None,
        language: Optional[str] = None,
        prompt_mode: Optional[str] = None,
        **config_kwargs: Any,
    ):
        self.workspace = Path(workspace)
        self.sources_dir = self.workspace / "sources"
        self.wiki_dir = self.workspace / "wiki"
        self.schema_dir = self.workspace / "schema"
        self._sys_op = sys_operation

        self._manifest = _SourceManifest(self.sources_dir, sys_operation=self._sys_op)

        resolved_language = resolve_language(language)
        final_card = card or AgentCard(
            name="wiki_agent",
            description=DEFAULT_WIKI_AGENT_DESCRIPTION.get(
                resolved_language, DEFAULT_WIKI_AGENT_DESCRIPTION["cn"]
            ),
        )
        final_prompt = system_prompt or DEFAULT_WIKI_AGENT_SYSTEM_PROMPT.get(
            resolved_language, DEFAULT_WIKI_AGENT_SYSTEM_PROMPT["cn"]
        )
        final_tools = tools if tools is not None else []
        final_rails = rails if rails is not None else [SysOperationRail()]

        self.agent = create_deep_agent(
            model=model,
            card=final_card,
            system_prompt=final_prompt,
            tools=final_tools,
            mcps=mcps,
            subagents=subagents,
            rails=final_rails,
            enable_task_loop=enable_task_loop,
            max_iterations=max_iterations,
            workspace=str(self.workspace),
            skills=skills,
            backend=backend,
            sys_operation=sys_operation,
            language=resolved_language,
            prompt_mode=prompt_mode,
            **config_kwargs,
        )

        _sid = session_id or hashlib.sha256(str(self.workspace.resolve()).encode()).hexdigest()[:16]
        self._session_id: str = _sid
        self.agent_card: AgentCard = final_card
        # The card is not decoration: ``Session.get_agent_id`` reads ``self._card.id``,
        # and the kernel's write_file/edit_file/bash call it while building their history
        # path -- AFTER the file is already written. A card-less session therefore made
        # every successful write report ``'NoneType' object has no attribute 'id'`` (167
        # times in one three-paper run). The maintainer then spent turns re-reading files
        # to verify writes that had in fact succeeded, and `bash date` failed, which is
        # why every log.md entry was dated [unknown] in violation of its own rule 13.
        self._session: Session = Session(
            session_id=_sid,
            card=final_card,
            parent_session_id=parent_session_id,
        )

    async def ensure_initialized(self):
        for d in [self.sources_dir, self.wiki_dir, self.schema_dir]:
            d.mkdir(parents=True, exist_ok=True)

        await self._manifest.ensure_initialized()

        schema_file = self.schema_dir / "AGENT.md"
        schema_content = (
            "# Wiki Maintainer Rules\n"
            "1. Never modify files inside `sources/`.\n"
            "2. All pages you generate MUST be saved directly inside the `wiki/` directory root.\n"
            "3. You must maintain a `wiki/index.md` listing all topics.\n"
            "4. You must maintain a `wiki/log.md` with an append-only timeline of ingestions.\n"
            "5. Break concepts down into modular topic pages.\n"
            "6. Make heavy use of markdown links to interconnect pages within `wiki/`.\n"
            "7. DO NOT create subdirectories (like `wiki/entity/`). Save all files in the `wiki/` root.\n"
        )
        if self._sys_op:
            res = await self._sys_op.fs().read_file(str(schema_file))
            if res.code != 0:
                await self._sys_op.fs().write_file(
                    str(schema_file), schema_content, create_if_not_exist=True
                )
        else:
            if not schema_file.exists():
                schema_file.write_text(schema_content)

        index_file = self.wiki_dir / "index.md"
        index_content = (
            "# Wiki Index\n\n"
            "This index lists all topics covered in the wiki.\n\n"
            "## Entities\n\n"
            "<!-- entity pages go here, one bullet per page -->\n\n"
            "## Concepts\n\n"
            "<!-- concept pages go here -->\n\n"
            "## Sources\n\n"
            "<!-- one bullet per ingested source, link to its summary page -->\n"
        )
        if self._sys_op:
            res = await self._sys_op.fs().read_file(str(index_file))
            if res.code != 0:
                await self._sys_op.fs().write_file(
                    str(index_file), index_content, create_if_not_exist=True
                )
        else:
            if not index_file.exists():
                index_file.write_text(index_content)

        log_file = self.wiki_dir / "log.md"
        log_content = (
            "# Wiki Log\n\n"
            "Append-only timeline of all wiki operations.\n"
            "Each entry starts with `## [YYYY-MM-DD] <operation> | <title>`\n"
            "so it is grep-parseable:\n"
            "<!-- append new entries below this line -->\n"
        )
        if self._sys_op:
            res = await self._sys_op.fs().read_file(str(log_file))
            if res.code != 0:
                await self._sys_op.fs().write_file(
                    str(log_file), log_content, create_if_not_exist=True
                )
        else:
            if not log_file.exists():
                log_file.write_text(log_content)

        await self.agent.ensure_initialized()

    def list_sources(self) -> Dict[str, Dict[str, str]]:
        return self._manifest.all_entries()

    async def ingest(self, source_path: str | Path, *, force: bool = False) -> Dict[str, Any]:
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        sha256 = _SourceManifest.sha256_of(source_path)
        if not force and self._manifest.is_known(sha256):
            entry = self._manifest.get(sha256)
            logger.warning("Skipping already-ingested source '%s'", source_path.name)
            return {
                "output": "Skipped duplicate source",
                "skipped": True,
                "sha256": sha256,
                "ingested_at": entry["ingested_at"],
            }

        destination = self.sources_dir / f"{sha256[:8]}_{source_path.name}"
        if source_path.resolve() != destination.resolve():
            shutil.copy2(source_path, destination)

        # Two clauses here used to dominate the ingest's wall clock. "other relevant
        # .md files" was read as licence to open the whole wiki (~30 pages, driving the
        # prompt to 146k tokens), and "a detailed summary" produced a 6.8k-token log
        # entry that cost 46 s in a single call and grows log.md without bound. The
        # replacements below narrow both without touching the anchoring contract: the
        # discovery recipe is the same index-then-grep one build_query_prompt already
        # uses, and the log entry is capped rather than dropped.
        #
        # The date is passed in because the maintainer cannot shell out for it. It used
        # to try `bash date`, which failed, and rule 13 then obliged it to write
        # [unknown] -- so every log entry carried a non-date. UTC here matches the
        # manifest's ingested_at, so the two can never disagree.
        today = datetime.datetime.now(tz=datetime.timezone.utc).date().isoformat()
        query = (
            f"Read the rules in your `schema/AGENT.md`."
            f" Process the new raw source document '{destination.name}' inside `sources/` into the wiki."
            f" Today's date is {today}; use it for any date you must record."
            f" To discover existing topics: read `wiki/index.md`, then grep the wiki for"
            f" the key terms of this source, and read in full ONLY the pages that match."
            f" Do not read the wiki exhaustively."
            f" Actively interconnect them by adding deep Markdown cross-links."
            f" FINALLY, append an entry to `wiki/log.md` of AT MOST 30 lines: the pages"
            f" you created, the pages you edited, the page ranges you read, and any rule"
            f" you could not satisfy. Read only the tail of `wiki/log.md` before"
            f" appending -- it is an append-only timeline and you never need its history."
        )
        result = await self.agent.invoke({"query": query}, session=self._session)

        if "error" in result or str(result.get("output", "")).startswith("[ERROR"):
            # Do not record the hash if the agent explicitly failed!
            return result

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

    async def query(self, question: str, *, allow_write: bool = False) -> Dict[str, Any]:
        return await self.agent.invoke(
            {"query": build_query_prompt(question, allow_write=allow_write)},
            session=self._session,
        )

    async def lint(self) -> Dict[str, Any]:
        query = (
            "Health-check the `wiki/` directory."
            " Actively evaluate all topic pages to discover orphaned documents or related, un-linked concepts."
            " You MUST proactively use your file editing tools to forge new Markdown cross-links between related"
            " pages, transforming isolated files into a highly connected knowledge graph."
            " Report the links you established."
            " FINALLY, you MUST append a detailed summary of the repairs and link established into `wiki/log.md`!"
        )
        return await self.agent.invoke({"query": query}, session=self._session)


def _get_default_model() -> Model:
    defaults = get_default_models()
    model_conf = next((m for m in defaults if m.get("is_default")), defaults[0] if defaults else {})

    client_config = model_conf.get("model_client_config", {})
    req_config = model_conf.get("model_config_obj", {})

    if client_config.get("custom_headers") == "":
        del client_config["custom_headers"]

    # Provide safe fallbacks for required fields to prevent ValidationError
    client_config.setdefault("api_key", "")
    client_config.setdefault("api_base", "")
    client_config.setdefault("client_provider", "OpenAI")
    client_config.setdefault("model_name", "default")
    model_name = req_config.get("model") or client_config["model_name"]
    req_config.setdefault("model", model_name)

    runtime_req_config = build_reasoning_model_request_kwargs(
        model_client_config=client_config,
        model_config_obj=req_config,
        model_name=model_name,
    )

    return Model(
        model_client_config=ModelClientConfig(**client_config),
        model_config=ModelRequestConfig(**runtime_req_config),
    )


def _resolve_workspace(workspace: str) -> Path:
    """
    Ensure workspace strings are safely mapped into the central or target workspace as absolute paths.
    """
    cleaned_workspace = (workspace or "").strip()
    base_dir = get_agent_workspace_dir()

    if not cleaned_workspace or cleaned_workspace == DEFAULT_WIKI_DIR:
        return (base_dir / DEFAULT_WIKI_DIR).resolve()

    workspace_path = Path(cleaned_workspace).expanduser()
    if not workspace_path.is_absolute():
        workspace_path = base_dir / workspace_path

    if workspace_path.name != DEFAULT_WIKI_DIR:
        workspace_path = workspace_path / DEFAULT_WIKI_DIR

    return workspace_path.resolve()


def _create_llm_wiki(
    *,
    workspace: str,
    model: Model,
    sys_operation: Optional[SysOperation],
) -> LLMWiki:
    """Create the internal Wiki agent with runtime policy and KVC lineage.

    Wiki tools create a separate ``DeepAgent`` instead of going through the
    main Code/Deep adapter.  Without forwarding the explicit runtime value,
    text-only deployments fall back to ``None`` and trigger the asynchronous
    image-capability probe even when the parent Agent disabled native image
    input.
    """

    config = get_config()
    react_config = config.get("react") if isinstance(config, dict) else None
    react_config = react_config if isinstance(react_config, dict) else {}
    configured = get_configured_read_image_multimodal(config)
    kwargs: Dict[str, Any] = {
        "kv_cache_affinity_config": build_kv_cache_affinity_config(
            react_config,
            provider=model_provider(model),
        ),
    }
    if isinstance(configured, bool):
        kwargs["enable_read_image_multimodal"] = configured

    owner_session_id, _ = resolve_session_lineage(get_current_session())
    if owner_session_id:
        workspace_scope = hashlib.sha256(
            str(Path(workspace).resolve()).encode()
        ).hexdigest()[:12]
        kwargs["session_id"] = (
            f"{owner_session_id}:subagent:wiki:{workspace_scope}"
        )
        kwargs["parent_session_id"] = owner_session_id
    return LLMWiki(
        workspace=workspace,
        model=model,
        sys_operation=sys_operation,
        **kwargs,
    )


@tool(
    name="wiki_ingest",
    description="Ingest a source file (PDF, TXT, MD) or a directory into the LLM Wiki."
    " By default, identical files (by SHA-256) are skipped perfectly (deduplication)."
    " Set `force=True` if the user explicitly asks to re-ingest, rebuild, or force the ingestion."
    " The `workspace` parameter is the root folder where the `.llm_wiki` will be created."
    " If the user specifies a target directory like 'wiki_lib' or 'bibliography', pass that exact path as `workspace`.",
)
async def wiki_ingest(
    source: str,
    workspace: str = "",
    force: bool = False,
    sys_operation: Optional[SysOperation] = None,
) -> str:
    """Ingests a file or directory of files into the LLM Wiki."""
    try:
        model = _get_default_model()
        final_workspace = _resolve_workspace(workspace)
        wiki = _create_llm_wiki(
            workspace=str(final_workspace),
            model=model,
            sys_operation=sys_operation,
        )
        await wiki.ensure_initialized()

        src_path = Path(source).expanduser()
        if not src_path.is_absolute():
            src_path = get_agent_workspace_dir() / src_path

        if not src_path.exists():
            return f"Error: Source {source} not found."

        if not source_is_allowed(src_path):
            return (
                f"Error: wiki_ingest only reads documents under the agent's session "
                f"uploads or workspace directory; {source} is outside both."
            )

        # Ensure we avoid circular ingestion by skipping the .llm_wiki directory itself
        protected_root = str(final_workspace).lower()

        targets = []
        if src_path.is_dir():
            for ext in INGESTIBLE_SUFFIXES:
                for p in src_path.glob(f"**/*{ext}"):
                    posix_path = p.as_posix()
                    # Skip if the file is located inside the .llm_wiki workspace
                    if posix_path.lower().startswith(protected_root):
                        continue
                    targets.append(p)
        else:
            if src_path.suffix.lower() not in INGESTIBLE_SUFFIXES:
                return (
                    f"Error: wiki_ingest handles {', '.join(INGESTIBLE_SUFFIXES)}; "
                    f"got '{src_path.suffix or 'no extension'}'."
                )
            targets.append(src_path)

        all_results = {}
        for file_path in targets:
            res = await wiki.ingest(source_path=file_path, force=force)
            if "error" in res:
                all_results[str(file_path)] = f"[Failed]: {res['error']}"
            elif res.get("skipped"):
                all_results[str(file_path)] = "[Skipped]: Deduplicated"
            else:
                all_results[str(file_path)] = "[Success]"

        return "Wiki Ingestion Results:\n" + json.dumps(all_results, indent=2)
    except Exception as e:
        return f"Wiki Ingest Error: {str(e)}"


@tool(
    name="wiki_query",
    description="Query the LLM Wiki's compiled knowledge base directly via Natural Language."
    " The `workspace` parameter is the folder containing the `.llm_wiki`."
    " If the user specifies a target directory like 'wiki_lib' or 'bibliography', pass that exact path as `workspace`.",
)
async def wiki_query(
    query: str,
    workspace: str = "",
    allow_write: bool = False,
    sys_operation: Optional[SysOperation] = None,
) -> str:
    """Queries the LLM Wiki.

    ``allow_write`` lets the answer be filed back as a wiki page. It defaults to off:
    a question should not mutate the library, and a caller that wants the library to
    grow from questions has to say so.
    """
    if not query or not query.strip():
        return "Error: Query cannot be empty."
    try:
        model = _get_default_model()
        final_workspace = _resolve_workspace(workspace)
        if not final_workspace.exists():
            return (
                f"Error: The workspace '{workspace}' does not have an initialized LLM Wiki."
                " You must use 'wiki_ingest' first to create the knowledge base."
            )
        wiki = _create_llm_wiki(
            workspace=str(final_workspace),
            model=model,
            sys_operation=sys_operation,
        )
        await wiki.ensure_initialized()

        result = await wiki.query(question=query, allow_write=allow_write)
        if "output" in result:
            return str(result["output"])
        elif "error" in result:
            return f"Error querying wiki: {result['error']}"
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Wiki Query Error: {str(e)}"


@tool(
    name="wiki_lint",
    description="Health-check and trigger automatic repairs of broken links, orphans, or anomalies in the LLM Wiki."
    " The `workspace` parameter is the root folder containing the `.llm_wiki`."
    " If the user specifies a target directory like 'wiki_lib' or 'bibliography', pass that exact path as `workspace`.",
)
async def wiki_lint(workspace: str = "", sys_operation: Optional[SysOperation] = None) -> str:
    """Lints the LLM Wiki."""
    try:
        model = _get_default_model()
        final_workspace = _resolve_workspace(workspace)
        if not final_workspace.exists():
            return (
                f"Error: The workspace '{workspace}' does not have an initialized LLM Wiki."
                " You must use 'wiki_ingest' first to create the knowledge base."
            )
        wiki = _create_llm_wiki(
            workspace=str(final_workspace),
            model=model,
            sys_operation=sys_operation,
        )
        await wiki.ensure_initialized()

        result = await wiki.lint()
        if "output" in result:
            return str(result["output"])
        elif "error" in result:
            return f"Error linting wiki: {result['error']}"
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Wiki Lint Error: {str(e)}"


# ``wiki_ingest`` drives a whole subagent session -- reading a paper, writing pages and
# cross-linking them -- and routinely runs for several minutes. The kernel's
# DEFAULT_TOOL_CALL_TIMEOUT of 300 s was killing it mid-write, after which the caller
# silently re-invoked it from scratch; a measured run finished only because the killed
# attempt had already written half the pages, and a paper that genuinely needs more than
# 300 s would loop forever. Declaring the call exempt lets it run to completion, still
# bounded by the kernel's MAX_TOOL_CALL_TIMEOUT_HARD_LIMIT.
#
# The exposure is part of the same fix rather than a separate preference. Under
# progressive tools a deferred tool is reached through the model-visible ``tool_call``
# wrapper, whose own call carries the default timeout -- so exempting only the target
# would still leave it killed by its parent. Declaring the exposure keeps the
# registration policy from deferring these two, and it also spares the ingest the
# ``tool_search`` round trip that discovering a deferred tool costs.
for _long_running_tool in (wiki_ingest, wiki_query):
    _long_running_tool.card.properties = {"resilience": {"timeout_s": None}}
    _long_running_tool.card.exposure = ToolExposure.DIRECT
    _long_running_tool.card.set_exposure_declared(True)
