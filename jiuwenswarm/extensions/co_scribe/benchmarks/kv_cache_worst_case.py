"""API-level KV-cache reuse benchmark for co-scribe prompt layouts.

Replays scripted co-scribe sessions (chat path and watch path) against an
OpenAI-compatible endpoint and records ``usage.prompt_tokens_details.cached_tokens``
per request. Nothing below the API is touched: ``/chat/completions`` for the
measurement, and ``/tokenize`` and ``/metrics`` when the server offers them
(vLLM does) for the ideal ratio and the engine-wide counters.

The prompts are the real ones: the harness system prompt, the 13 co-scribe tool
schemas from ``CloudDocToolkit.get_tools()`` (4 on the unattended path), the
watch-path turn prompt from ``build_turn_prompt``, and -- for every read -- whatever
``CloudDocToolkit.read`` returns for a scripted document that the scripted edits
change from turn to turn. Assistant turns are scripted, not generated: the model's
one-token reply is discarded, only its usage is kept. That keeps a run deterministic
and cheap, and makes the same script measure any commit of the toolkit.

Run from the repository root with the project venv::

    .venv/bin/python jiuwenswarm/extensions/co_scribe/benchmarks/kv_cache_worst_case.py \
        --out bench/kv-cache

Endpoint: ``--api-base/--api-key/--model``, else ``KVBENCH_API_BASE`` etc., else
``models.defaults[0]`` of ``~/.jiuwenswarm/config/config.yaml``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- endpoint


@dataclass
class Endpoint:
    api_base: str
    api_key: str
    model: str

    @property
    def host(self) -> str:
        return self.api_base.rsplit("/v1", 1)[0]


def resolve_endpoint(args: argparse.Namespace) -> Endpoint:
    base = args.api_base or os.environ.get("KVBENCH_API_BASE")
    key = args.api_key or os.environ.get("KVBENCH_API_KEY")
    model = args.model or os.environ.get("KVBENCH_MODEL")
    if not (base and model):
        import yaml

        cfg_path = Path(os.path.expanduser("~/.jiuwenswarm/config/config.yaml"))
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        mc = cfg["models"]["defaults"][0]["model_client_config"]
        base = base or mc["api_base"]
        key = key or mc.get("api_key", "")
        model = model or mc["model_name"]
    return Endpoint(api_base=base.rstrip("/"), api_key=key or "", model=model)


class Client:
    def __init__(self, ep: Endpoint, timeout: float = 300.0) -> None:
        self.ep = ep
        self.timeout = timeout
        self.tokenize_ok: bool | None = None

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            self.ep.host + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.ep.api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def _get(self, path: str) -> str | None:
        try:
            req = urllib.request.Request(self.ep.host + path, headers={"Authorization": f"Bearer {self.ep.api_key}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - optional endpoint
            return None

    def chat(self, messages: list[dict], tools: list[dict] | None) -> tuple[dict, float]:
        body: dict[str, Any] = {
            "model": self.ep.model,
            "messages": messages,
            "max_tokens": 1,
            "temperature": 0,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        t0 = time.perf_counter()
        resp = self._post("/v1/chat/completions", body)
        return resp.get("usage") or {}, time.perf_counter() - t0

    def tokenize(self, messages: list[dict], tools: list[dict] | None) -> int | None:
        if self.tokenize_ok is False:
            return None
        body: dict[str, Any] = {"model": self.ep.model, "messages": messages, "add_generation_prompt": False}
        if tools:
            body["tools"] = tools
        try:
            out = self._post("/tokenize", body)
            self.tokenize_ok = True
            return int(out["count"])
        except Exception:  # noqa: BLE001 - optional endpoint
            self.tokenize_ok = False
            return None

    def version(self) -> str:
        body = self._get("/version")
        return body.strip() if body else "unknown"

    def prefix_counters(self) -> dict[str, float]:
        text = self._get("/metrics")
        if not text:
            return {}
        out: dict[str, float] = {}
        for line in text.splitlines():
            for key in ("vllm:prefix_cache_hits_total", "vllm:prefix_cache_queries_total", "vllm:kv_cache_usage_perc"):
                if line.startswith(key + "{") or line.startswith(key + " "):
                    out[key] = out.get(key, 0.0) + float(line.rsplit(" ", 1)[1])
        return out


# --------------------------------------------------------------------------- assets


def build_assets(doc_chars: int) -> dict[str, Any]:
    """Real prompts and schemas from the codebase, plus one synthetic document."""
    from jiuwenswarm.agents.harness.code.prompt import build_code_system_prompt
    from jiuwenswarm.extensions.co_scribe.backend.toolkit.clouddoc_tools import (
        CloudDocToolkit,
        unattended_allowlist_for,
    )
    from jiuwenswarm.extensions.co_scribe.backend.toolkit.providers.provider import DocSnapshot

    class _Provider:
        """A document held in memory; the scripted edits rewrite ``text``."""

        kind = "fake"

        def __init__(self, text: str = "") -> None:
            self.text = text
            self.reads = 0

        def doc_url(self, doc_id, kind=""):
            return f"https://example.test/{kind or 'doc'}/{doc_id}"

        def parse_doc_ref(self, ref):
            return ref

        async def read(self, doc_ref):
            self.reads += 1
            return DocSnapshot(doc_id=doc_ref, kind="document", revision_id=f"rev{self.reads}", text=self.text)

    def tools_with_titles(titles: list[str]) -> list[dict]:
        kit = CloudDocToolkit(_Provider())
        if titles:
            shown = "、".join(f"《{x}》" for x in titles[:12])
            more = f" 等 {len(titles)} 篇" if len(titles) > 12 else ""
            line = f"当前已纳管：{shown}{more}——这些名字都是云文档，直接用本工具族。"
        else:
            line = ""
        kit._adopted_titles_line = lambda: line  # noqa: SLF001 - benchmark knob
        return [
            {
                "type": "function",
                "function": {
                    "name": t.card.name,
                    "description": t.card.description,
                    "parameters": t.card.input_params,
                },
            }
            for t in kit.get_tools()
        ]

    allowed = unattended_allowlist_for("apply_scoped")
    paragraph = "本季度的推广计划分为三个阶段，先在两个试点城市验证渠道转化率，再按结果决定预算分配。"
    text = ""
    i = 0
    while len(text) < doc_chars:
        text += f"第{i + 1}段 " + paragraph + "\n"
        i += 1
    def new_kit(doc_text: str | None = None):
        """A toolkit of its own for one session, over its own copy of the document."""
        provider = _Provider(text if doc_text is None else doc_text)
        return CloudDocToolkit(provider), provider

    return {
        "system_prompt": build_code_system_prompt(),
        "tools_with_titles": tools_with_titles,
        "unattended_names": allowed,
        "doc_text": text,
        "new_kit": new_kit,
    }


def watch_quote(turn: int) -> str:
    """The text the turn's comment is anchored on: one paragraph's opening, unique in the body."""
    return f"第{turn}段 本季度的推广计划分为三个阶段"


def watch_turn_prompt(turn: int, thread_len: int, workmode: str, conventions_text: str, passage: str | None = None) -> str:
    from jiuwenswarm.extensions.co_scribe.backend.host.conventions import Conventions
    from jiuwenswarm.extensions.co_scribe.backend.host.watch.turn_prompt import build_turn_prompt
    from jiuwenswarm.extensions.co_scribe.backend.toolkit.providers.provider import DocComment, DocReply

    replies = tuple(
        DocReply(
            reply_id=f"r{k}",
            author_is_self=(k % 2 == 1),
            author_display_name="someone",
            created_time="2026-09-22T10:00:00Z",
            content=f"第 {k + 1} 轮讨论：请保留「甲」这个术语，并把数字改成千分位格式。",
        )
        for k in range(thread_len)
    )
    comment = DocComment(
        comment_id="c1",
        author_is_self=False,
        author_display_name="someone",
        created_time="2026-09-22T09:00:00Z",
        content="@助手 请把这一段润色得更正式一些，保留原意。",
        quoted_text=watch_quote(turn),
        resolved=False,
        replies=replies,
    )
    conv = Conventions(source="in_doc", comment_id="c0", text=conventions_text, item_count=2, truncated=False, content_hash="x")
    reply = f"第 {turn} 次追问：再简洁一点。" if turn > 1 else None
    extra = {"anchor_context": passage} if passage else {}
    return build_turn_prompt(
        comment,
        text_domain="plain",
        mode="apply_scoped",
        workmode_text=workmode,
        conventions=conv,
        reply_content=reply,
        thread=replies,
        **extra,
    ).text


def anchored_passage(s: "Session", turn: int) -> str | None:
    """What the watcher hands the turn, where the toolkit under test offers it.

    None on a commit that predates the passage, and whenever the real helper declines
    (an anchor that is not unique, a passage that is too long): the turn then opens
    with a read, as the product does.
    """
    try:
        from jiuwenswarm.extensions.co_scribe.backend.toolkit.rails.range_rail import anchor_context
    except ImportError:
        return None
    return anchor_context(asyncio.run(s.provider.read(DOC)), watch_quote(turn))


# --------------------------------------------------------------------------- session


@dataclass
class Row:
    scenario: str
    session: str
    turn: int
    step: str
    prompt_tokens: int
    cached_tokens: int
    ideal_cached: int | None
    latency_s: float
    note: str = ""

    @property
    def measured(self) -> float:
        return self.cached_tokens / self.prompt_tokens if self.prompt_tokens else 0.0

    @property
    def ideal(self) -> float | None:
        return None if self.ideal_cached is None else self.ideal_cached / self.prompt_tokens


class Session:
    """One engine session: an append-only message list unless a scenario edits it."""

    salt: str = ""

    new_kit: Any = None

    def __init__(self, client: Client, scenario: str, name: str, system_prompt: str, tools: list[dict], rows: list[Row],
                 *, doc_text: str | None = None) -> None:
        self.client = client
        # The toolkit is per session in the product, and so is what it remembers
        # having shown the model.
        self.kit, self.provider = Session.new_kit(doc_text)
        self.scenario = scenario
        self.name = name
        self.tools = tools
        # One line per run and scenario so scenarios do not warm each other's prefix.
        # The tools block precedes the system text in the chat template, so it still shares.
        if self.salt:
            system_prompt = f"{system_prompt}\n[bench {self.salt}/{scenario}]"
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]
        self.rows = rows
        self.turn = 0
        self._prev_messages: list[dict] | None = None
        self._prev_tools: list[dict] | None = None
        self._calls = 0

    def user(self, content: str) -> None:
        self.turn += 1
        self.messages.append({"role": "user", "content": content})

    def tool_call(self, name: str, arguments: dict, result: str) -> None:
        self._calls += 1
        cid = f"call_{self._calls}"
        self.messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}],
        })
        self.messages.append({"role": "tool", "tool_call_id": cid, "content": result})

    def assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def read(self) -> None:
        """A clouddoc_read call whose result is what the toolkit really returns now."""
        result = asyncio.run(self.kit.read(DOC))
        self.tool_call("clouddoc_read", {"doc_id": DOC}, json.dumps(result, ensure_ascii=False))

    def edit_document(self, old: str, new: str) -> None:
        """What a successful write leaves behind: the document, changed in one place."""
        self.provider.text = self.provider.text.replace(old, new, 1)

    def _ideal_cached(self) -> int | None:
        if self._prev_messages is None:
            return 0
        if self._prev_tools != self.tools:
            # Template-dependent: tools may sit before or after the system text.
            return None
        k = 0
        for a, b in zip(self._prev_messages, self.messages):
            if a != b:
                break
            k += 1
        k = min(k, len(self._prev_messages), len(self.messages))
        if k == 0:
            return 0
        return self.client.tokenize(self.messages[:k], self.tools)

    def step(self, label: str, note: str = "") -> Row:
        ideal = self._ideal_cached()
        usage, dt = self.client.chat(self.messages, self.tools)
        details = usage.get("prompt_tokens_details") or {}
        row = Row(
            scenario=self.scenario,
            session=self.name,
            turn=self.turn,
            step=label,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            cached_tokens=int(details.get("cached_tokens") or usage.get("prompt_cache_hit_tokens") or 0),
            ideal_cached=ideal,
            latency_s=dt,
            note=note,
        )
        self.rows.append(row)
        self._prev_messages = [dict(m) for m in self.messages]
        self._prev_tools = list(self.tools)
        print(f"  {self.scenario:<24} {self.name:<8} t{row.turn:<2} {label:<12} prompt={row.prompt_tokens:>6} cached={row.cached_tokens:>6} "
              f"measured={row.measured:5.1%} ideal={'  n/a' if row.ideal is None else f'{row.ideal:5.1%}'} {dt:5.2f}s {note}", flush=True)
        return row


# --------------------------------------------------------------------------- scenarios

DOC = "1AAAAAAAAAAAAAAAAAAAAA"
WORKMODE = "回复保持简短。修改正文时不要改变段落数量。"
CONVENTIONS = "1. 术语「甲」不翻译。\n2. 数字用千分位。"


def chat_turn(s: Session, i: int) -> None:
    s.user(f"请把《推广计划》第 {i} 段润色一下，保持原意。")
    s.step("user")
    s.read()
    s.step("after_read")
    old, new = f"第{i}段 本季度的推广计划", f"第{i}段 本季度推广计划"
    s.tool_call(
        "clouddoc_batch_edit",
        {"doc_id": DOC, "edits": [{"old_string": old, "new_string": new}]},
        json.dumps({"ok": True, "detail": "已修改 1 处。", "receipt_id": f"R-{i:03d}"}, ensure_ascii=False),
    )
    s.edit_document(old, new)
    s.step("after_edit")
    s.assistant(f"已把第 {i} 段润色完毕，回执 R-{i:03d}。")


def watch_turn(s: Session, i: int, *, workmode: str = WORKMODE, conventions: str = CONVENTIONS) -> None:
    passage = anchored_passage(s, i)
    s.user(watch_turn_prompt(i, thread_len=i - 1, workmode=workmode, conventions_text=conventions, passage=passage))
    s.step("user")
    if passage is None:
        s.read()
        s.step("after_read")
    old, new = watch_quote(i), f"第{i}段 本季度推广计划分三个阶段"
    s.tool_call(
        "clouddoc_apply_for_comment",
        {"scope": "sentence", "edits": [{"old_string": old, "new_string": new}]},
        json.dumps({"ok": True, "detail": "已修改 1 处并高亮。", "receipt_id": f"R-W{i:03d}"}, ensure_ascii=False),
    )
    s.edit_document(old, new)
    s.step("after_apply")
    s.assistant("已按要求修改。")


def run_scenarios(client: Client, assets: dict, turns: int, rows: list[Row], *, interleave: int, large_doc_chars: int) -> None:
    sysp = assets["system_prompt"]
    tools_chat = assets["tools_with_titles"](["推广计划"])
    tools_watch = [t for t in tools_chat if t["function"]["name"] in assets["unattended_names"]]

    print("\n[1] chat_baseline: append-only chat session, 3 requests per turn")
    s = Session(client, "chat_baseline", "chat", sysp, tools_chat, rows)
    for i in range(1, turns + 1):
        chat_turn(s, i)

    print("\n[2] watch_baseline: one session per document, new nonce fence each turn, thread grows")
    s = Session(client, "watch_baseline", "watch", sysp, tools_watch, rows)
    for i in range(1, turns + 1):
        watch_turn(s, i)

    print("\n[3] watch_rotate_each_turn: session rotated every turn (session_max_turns=1)")
    for i in range(1, turns + 1):
        s = Session(client, "watch_rotate_each_turn", f"w{i}", sysp, tools_watch, rows)
        watch_turn(s, 1)

    print("\n[4] chat_titles_change: adopted-titles line in clouddoc_read changes after turn 3")
    s = Session(client, "chat_titles_change", "chat", sysp, tools_chat, rows)
    for i in range(1, turns + 1):
        if i == 4:
            s.tools = assets["tools_with_titles"](["推广计划", "Q3 发布说明"])
        chat_turn(s, i)

    print("\n[5] toolset_switch: watch session (4 tools) right after a chat session (13 tools)")
    s = Session(client, "toolset_switch", "chat", sysp, tools_chat, rows)
    chat_turn(s, 1)
    s = Session(client, "toolset_switch", "watch", sysp, tools_watch, rows)
    watch_turn(s, 1)
    s = Session(client, "toolset_switch", "notools", sysp, [], rows)
    s.user("你好")
    s.step("user", "system prompt only, no tools")

    print("\n[6] watch_workmode_edit: work-mode text and conventions change after turn 3")
    s = Session(client, "watch_workmode_edit", "watch", sysp, tools_watch, rows)
    for i in range(1, turns + 1):
        if i >= 4:
            watch_turn(s, i, workmode=WORKMODE + " 标题保持原样。", conventions=CONVENTIONS + "\n3. 不用被动语态。")
        else:
            watch_turn(s, i)

    print("\n[7] chat_history_rewrite: old tool results replaced by a summary after turn 3 (compressor / offloader)")
    s = Session(client, "chat_history_rewrite", "chat", sysp, tools_chat, rows)
    for i in range(1, turns + 1):
        if i == 4:
            summary = "（以下为压缩摘要）前三轮已分别润色第 1、2、3 段，回执 R-001、R-002、R-003。"
            for m in s.messages:
                if m.get("role") == "tool" and '"text"' in m.get("content", ""):
                    m["content"] = json.dumps({"ok": True, "summary": summary}, ensure_ascii=False)
        chat_turn(s, i)

    print(f"\n[8] chat_large_reads: chat with a {large_doc_chars}-char document read every turn")
    big = assets["doc_text"] * max(1, large_doc_chars // max(1, len(assets["doc_text"])))
    s = Session(client, "chat_large_reads", "chat", sysp, tools_chat, rows, doc_text=big)
    for i in range(1, turns + 1):
        chat_turn(s, i)

    if interleave > 1:
        print(f"\n[9] interleaved_chat: {interleave} chat sessions round-robin")
        sessions = [Session(client, "interleaved_chat", f"c{k}", sysp, tools_chat, rows) for k in range(interleave)]
        for i in range(1, turns + 1):
            for s in sessions:
                chat_turn(s, i)


# --------------------------------------------------------------------------- report


def summarize(rows: list[Row]) -> str:
    by: dict[str, list[Row]] = {}
    for r in rows:
        by.setdefault(r.scenario, []).append(r)
    lines = ["| scenario | requests | prompt tokens (sum) | cached (sum) | measured | ideal | worst request (measured) |", "|---|---|---|---|---|---|---|"]
    for name, rs in by.items():
        p = sum(r.prompt_tokens for r in rs)
        c = sum(r.cached_tokens for r in rs)
        ideal_rows = [r for r in rs if r.ideal_cached is not None]
        ideal = sum(r.ideal_cached for r in ideal_rows) / max(1, sum(r.prompt_tokens for r in ideal_rows)) if ideal_rows else None
        # The first request of a session is cold by definition; the worst is taken after it.
        later = [r for r in rs if not (r.turn == 1 and r.step == "user")]
        worst = min(later, key=lambda r: r.measured) if later else None
        worst_txt = f"t{worst.turn} {worst.step}: {worst.measured:.1%}" if worst else "-"
        lines.append(f"| {name} | {len(rs)} | {p} | {c} | {c / p:.1%} | {'-' if ideal is None else f'{ideal:.1%}'} | {worst_txt} |")
    return "\n".join(lines)


def per_request_table(rows: list[Row]) -> str:
    lines = ["| scenario | session | turn | step | prompt | cached | measured | ideal | latency s | note |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ideal = "-" if r.ideal is None else f"{r.ideal:.1%}"
        lines.append(f"| {r.scenario} | {r.session} | {r.turn} | {r.step} | {r.prompt_tokens} | {r.cached_tokens} | {r.measured:.1%} | {ideal} | {r.latency_s:.2f} | {r.note} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-base")
    ap.add_argument("--api-key")
    ap.add_argument("--model")
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--doc-chars", type=int, default=6000, help="synthetic document size for normal reads")
    ap.add_argument("--large-doc-chars", type=int, default=60000, help="document size for the large-read scenario")
    ap.add_argument("--interleave", type=int, default=0, help="run N chat sessions round-robin (0 = skip)")
    ap.add_argument("--out", default="kv-cache-bench", help="output directory for requests.jsonl and summary.md")
    ap.add_argument("--salt", default=str(int(time.time())), help="per-run marker appended to the system prompt; '' shares the prefix with earlier runs")
    args = ap.parse_args()

    Session.salt = args.salt
    ep = resolve_endpoint(args)
    client = Client(ep)
    print(f"endpoint {ep.host} model {ep.model} server {client.version()}")
    assets = build_assets(args.doc_chars)
    Session.new_kit = staticmethod(assets["new_kit"])
    print(f"system prompt {len(assets['system_prompt'])} chars; clouddoc tools {len(assets['tools_with_titles']([]))}; unattended {sorted(assets['unattended_names'])}")

    before = client.prefix_counters()
    rows: list[Row] = []
    t0 = time.time()
    run_scenarios(client, assets, args.turns, rows, interleave=args.interleave, large_doc_chars=args.large_doc_chars)
    after = client.prefix_counters()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "requests.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({**r.__dict__, "measured": r.measured, "ideal": r.ideal}, ensure_ascii=False) + "\n")

    engine = ""
    if before and after:
        dq = after.get("vllm:prefix_cache_queries_total", 0) - before.get("vllm:prefix_cache_queries_total", 0)
        dh = after.get("vllm:prefix_cache_hits_total", 0) - before.get("vllm:prefix_cache_hits_total", 0)
        engine = (f"\nEngine counters over the run (all traffic on the instance, not only this run): "
                  f"queries {int(dq)}, hits {int(dh)}, hit rate {dh / dq:.1%}\n" if dq else "")
    summary = (
        f"# KV-cache worst-case benchmark\n\n"
        f"endpoint {ep.host}, model {ep.model}, server {client.version()}, "
        f"{len(rows)} requests in {time.time() - t0:.0f}s, salt {args.salt!r}, turns per session {args.turns}, "
        f"doc {args.doc_chars} chars, large doc {args.large_doc_chars} chars.\n"
        f"measured = cached_tokens / prompt_tokens from the response usage; ideal = tokens of the message prefix "
        f"shared with the previous request of the same session (server /tokenize), an upper bound.\n"
        f"{engine}\n## Per scenario\n\n{summarize(rows)}\n\n## Per request\n\n{per_request_table(rows)}\n"
    )
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summarize(rows))
    print(engine)
    print(f"written {out / 'summary.md'} and {out / 'requests.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
