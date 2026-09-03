"""Co-scribe as a stdio MCP server: cloud-document editing for external CLIs.

What goes out the door is the capability; what never goes out is the mandate.
Every rail that makes co-scribe trustworthy -- the range rail, the predicate
rail, receipts with before images, the D16 floor -- executes **inside this
process**, on this side of the protocol boundary. The connecting client's model
can phrase any request it likes; it cannot reach past the checks, because the
enforcement point is here, not in its prompt.

Three deliberate narrowings against the in-process surface:

* **Six tools, not ten.** ``apply_for_comment`` is the unattended path's
  primitive and refuses without a bound turn, which an MCP call never has;
  the workmode pair carries deployment style, which is not for external
  callers; ``create_document`` is grant-class -- it hands out access -- and the
  floor below would refuse it on every call, so it is not offered at all.
* **No confirmation channel, declared.** MCP has no dialog to raise, so the
  toolkit is constructed with ``ask_channel=False`` -- the D16 floor holds by
  declaration rather than by whatever the deployment config happens to say:
  revertible writes pass (receipts and the panel's revert carry the risk),
  anything irreversible refuses with the reason.
* **The caller is an executor, never the principal.** Receipts from this
  surface carry ``executor="mcp:<client>"``; the keys, the panel and the revert
  stay with the deployment owner. stdio keeps the door local: whoever can spawn
  this process already has this machine.

Run: ``python -m jiuwenswarm.mcp_export.co_scribe_server`` (client name via
``CO_SCRIBE_MCP_CLIENT``, default ``cli``).
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

# The current call's arguments, serialized -- this surface's "user text". The
# ambiguity rail exempts a write when the person's own words name the target
# document; on MCP the caller's words ARE the arguments, and a doc_id passed
# explicitly is precisely such a naming. Feeding the arguments through the
# existing ``user_text`` seam satisfies the rail's own criterion with no special
# case -- and a call that names no document still gets refused, as it should.
_CURRENT_ARGS: contextvars.ContextVar[str] = contextvars.ContextVar(
    "co_scribe_mcp_args", default=""
)

# The exported subset, by canonical name. A tool absent from this list is not
# degraded or hidden -- it is not part of this surface's contract at all.
EXPORTED_TOOLS: tuple[str, ...] = (
    "clouddoc_read",
    "clouddoc_list_documents",
    "clouddoc_list_comments",
    "clouddoc_reply_comment",
    "clouddoc_batch_edit",
    "clouddoc_write_region",
)


def build_toolkit(client_name: str) -> Any:
    """The same construction the swarm factory does, minus the watcher.

    Reads the deployment's own config and keys; there is no separate credential
    story for this surface, which is the point -- the caller borrows the
    deployment's hands, it does not get hands of its own.
    """
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        CloudDocToolkit,
    )
    from jiuwenswarm.agents.harness.common.tools.clouddoc.factory import build_provider
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
        read_connection_specs,
    )
    from jiuwenswarm.common.config import get_config

    cfg = (get_config() or {}).get("clouddoc") or {}
    if not cfg.get("enabled"):
        raise SystemExit("clouddoc 未启用：config.yaml 的 clouddoc.enabled 为 false。")
    specs = read_connection_specs(cfg)
    if not specs:
        raise SystemExit("没有配置任何云文档连接；先在部署里完成接入。")
    provider = build_provider(specs[0]["credentials_file"])
    try:
        from jiuwenswarm.gateway.clouddoc.cursor_store import prime_provider_kinds

        prime_provider_kinds(provider, specs[0].get("documents") or [])
    except Exception:  # noqa: BLE001 - priming must not stop the server
        pass
    try:
        from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore

        provider.receipt_sink = ReceiptStore()
    except Exception as exc:  # noqa: BLE001
        # No sink means writes demote to irreversible and the floor refuses them
        # (ask_channel=False below). Stating it beats a surprise refusal later.
        logger.warning("[co-scribe-mcp] receipt sink 不可用，写入将被底线拒绝：%s", exc)

    def _live_specs() -> list[dict]:
        return read_connection_specs((get_config() or {}).get("clouddoc") or {})

    return CloudDocToolkit(
        provider,
        turn_doc_id=lambda: None,  # every MCP call is an attended-shaped chat turn
        watched_docs=lambda: [d for s in _live_specs() for d in s.get("documents", [])],
        connection_count=lambda: len(_live_specs()),
        user_text=lambda: _CURRENT_ARGS.get(),
        executor_label=f"mcp:{client_name}",
        ask_channel=False,
        # D21's boundary rule: whatever mode the deployment chose for itself, the
        # exported surface is never sold apart from its mandate.
        harness_mode="mandate",
    )


def _exported_cards(toolkit: Any) -> list[tuple[Any, Any]]:
    """(card, callable) pairs for the exported subset, in EXPORTED_TOOLS order."""
    by_name: dict[str, tuple[Any, Any]] = {}
    for tool in toolkit.get_tools():
        card = getattr(tool, "card", None) or tool
        func = getattr(tool, "func", None) or getattr(tool, "_func", None)
        by_name[getattr(card, "name", "")] = (card, func)
    return [by_name[n] for n in EXPORTED_TOOLS if n in by_name]


async def serve() -> None:
    import mcp.types as types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server

    client_name = (os.environ.get("CO_SCRIBE_MCP_CLIENT") or "cli").strip() or "cli"
    toolkit = build_toolkit(client_name)
    pairs = _exported_cards(toolkit)
    funcs = {card.name: func for card, func in pairs}

    server = Server("co-scribe")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        # The cards' schemas verbatim: the schema-to-signature parity test in the
        # toolkit's own suite is what keeps this surface from drifting.
        return [
            types.Tool(
                name=card.name,
                description=card.description,
                inputSchema=card.input_params,
            )
            for card, _ in pairs
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        func = funcs.get(name)
        if func is None:
            payload: dict[str, Any] = {"ok": False, "detail": f"未导出的工具：{name}"}
        else:
            _CURRENT_ARGS.set(json.dumps(arguments or {}, ensure_ascii=False))
            try:
                payload = await func(**(arguments or {}))
            except TypeError as exc:
                payload = {"ok": False, "detail": f"参数不符：{exc}"}
            except Exception as exc:  # noqa: BLE001 - a protocol boundary
                logger.exception("[co-scribe-mcp] %s failed", name)
                payload = {"ok": False, "detail": f"内部错误：{exc}"}
        return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    import anyio

    protocol_out = anyio.wrap_file(_PROTOCOL_STDOUT)
    async with stdio_server(stdout=protocol_out) as (read, write):
        await server.run(read, write, server.create_initialization_options())


# The protocol's private stdout, claimed before any jiuwenswarm import can run.
#
# stdio MCP requires fd 1 to carry nothing but JSON-RPC, and this codebase logs to
# stdout at import time. So the real stdout fd is duplicated away for the protocol,
# fd 1 is pointed at stderr, and ``sys.stdout`` follows -- whatever any module
# prints or logs from then on lands in stderr, where a human reads it, not in the
# frame stream, where a client chokes on it. Measured, not hypothetical: the first
# smoke run fed the client a parser-registry log line as a JSON-RPC message.
_saved_fd = os.dup(1)
os.dup2(2, 1)
sys.stdout = sys.stderr
_PROTOCOL_STDOUT = os.fdopen(_saved_fd, "w", encoding="utf-8", buffering=1)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    asyncio.run(serve())


if __name__ == "__main__":
    main()
