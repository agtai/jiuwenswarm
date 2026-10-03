"""The ``clouddoc.*`` WebSocket methods: one table, registered on the web channel.

Each method is a thin shell over one panel operation. The shell is the contract
the frontend relies on: a missing panel answers ``{"enabled": false}`` with
``ok=true``, which the UI renders as its guidance state rather than an error;
a bad request answers ``BAD_REQUEST`` before the panel is touched; every
exception out of the panel becomes an ``INTERNAL_ERROR`` response, so an RPC can
fail but never hang.

The panel is passed as a reference the gateway may rebind -- either the object
itself or a ``{"value": panel}`` cell -- resolved on every call.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[Any, Any, Any, Any], Awaitable[None]]


def _resolve(ref: Any) -> Any:
    if isinstance(ref, dict):
        return ref.get("value")
    return ref


def _ids(raw: Any) -> list[str]:
    return [str(x) for x in raw if str(x or "")] if isinstance(raw, list) else []


def build_methods(channel: Any, panel_ref: Any) -> dict[str, Handler]:
    """The method table: name to handler, for ``channel.register_method``."""

    async def call(ws, req_id, op, *args):
        panel = _resolve(panel_ref)
        if panel is None:
            await channel.send_response(ws, req_id, ok=True, payload={"enabled": False})
            return
        try:
            payload = await getattr(panel, op)(*args)
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except Exception as e:  # noqa: BLE001 - an RPC boundary: every exception becomes a response
            logger.exception("[clouddoc.%s] %s", op, e)
            await channel.send_response(ws, req_id, ok=False, error=str(e), code="INTERNAL_ERROR")

    async def bad_request(ws, req_id, message):
        await channel.send_response(ws, req_id, ok=False, error=message, code="BAD_REQUEST")

    def params_of(params) -> dict:
        return params if isinstance(params, dict) else {}

    async def get_conf(ws, req_id, params, session_id):
        await call(ws, req_id, "get_conf")

    async def list_docs(ws, req_id, params, session_id):
        panel = _resolve(panel_ref)
        if panel is None:
            await channel.send_response(ws, req_id, ok=True, payload={"enabled": False, "docs": []})
            return
        try:
            docs = await panel.list_docs()
            await channel.send_response(ws, req_id, ok=True, payload={"enabled": True, "docs": docs})
        except Exception as e:  # noqa: BLE001
            logger.exception("[clouddoc.list_docs] %s", e)
            await channel.send_response(ws, req_id, ok=False, error=str(e), code="INTERNAL_ERROR")

    async def sync_shared_docs(ws, req_id, params, session_id):
        await call(ws, req_id, "sync_shared_docs", params_of(params).get("connection_id"))

    async def sync_all_shared_docs(ws, req_id, params, session_id):
        await call(ws, req_id, "sync_all_shared_docs")

    async def add_doc(ws, req_id, params, session_id):
        p = params_of(params)
        url = p.get("url", "")
        if not url:
            await bad_request(ws, req_id, "params.url required")
            return
        await call(ws, req_id, "add_doc", url, p.get("connection_id"))

    async def update_doc(ws, req_id, params, session_id):
        doc_id = params_of(params).get("doc_id", "")
        if not doc_id:
            await bad_request(ws, req_id, "params.doc_id required")
            return
        await call(ws, req_id, "update_doc", doc_id)

    async def list_keys(ws, req_id, params, session_id):
        await call(ws, req_id, "list_keys")

    async def delete_key(ws, req_id, params, session_id):
        p = params_of(params)
        if not p.get("filename"):
            await bad_request(ws, req_id, "params.filename required")
            return
        await call(ws, req_id, "delete_key", p.get("filename"))

    async def add_connection(ws, req_id, params, session_id):
        p = params_of(params)
        if not p.get("credentials_path") and not p.get("credentials_json"):
            await bad_request(ws, req_id, "credentials_path or credentials_json required")
            return
        await call(
            ws, req_id, "add_connection",
            p.get("credentials_path"), p.get("credentials_json"), p.get("filename"),
        )

    async def remove_connection(ws, req_id, params, session_id):
        conn_id = params_of(params).get("connection_id", "")
        if not conn_id:
            await bad_request(ws, req_id, "params.connection_id required")
            return
        await call(ws, req_id, "remove_connection", conn_id)

    async def watch_list(ws, req_id, params, session_id):
        await call(ws, req_id, "watch_list")

    async def watch_usage(ws, req_id, params, session_id):
        await call(ws, req_id, "watch_usage", str(params_of(params).get("doc_id") or ""))

    async def watch_set(ws, req_id, params, session_id):
        p = params_of(params)
        panel = _resolve(panel_ref)
        if panel is None:
            await channel.send_response(ws, req_id, ok=True, payload={"enabled": False})
            return
        try:
            payload = await panel.watch_set(
                str(p.get("doc_id") or ""), str(p.get("mode") or ""),
                expires_at=p.get("expires_at"),
                permanent=bool(p.get("permanent")),
                budget=p.get("budget"),
            )
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except Exception as e:  # noqa: BLE001
            logger.exception("[clouddoc.watch_set] %s", e)
            await channel.send_response(ws, req_id, ok=False, error=str(e), code="INTERNAL_ERROR")

    async def watch_revoke(ws, req_id, params, session_id):
        await call(ws, req_id, "watch_revoke", str(params_of(params).get("doc_id") or ""))

    async def watch_revoke_all(ws, req_id, params, session_id):
        await call(ws, req_id, "watch_revoke_all")

    async def watch_set_many(ws, req_id, params, session_id):
        p = params_of(params)
        await call(ws, req_id, "watch_set_many", _ids(p.get("doc_ids")), str(p.get("mode") or ""))

    async def watch_revoke_many(ws, req_id, params, session_id):
        await call(ws, req_id, "watch_revoke_many", _ids(params_of(params).get("doc_ids")))

    async def watch_audit(ws, req_id, params, session_id):
        await call(ws, req_id, "watch_audit", int(params_of(params).get("limit") or 100))

    async def receipts(ws, req_id, params, session_id):
        # Derived per document: the history view's receipt feed.
        p = params_of(params)
        panel = _resolve(panel_ref)
        if panel is None:
            await channel.send_response(ws, req_id, ok=True, payload={"enabled": False})
            return
        try:
            from jiuwenswarm.clouddoc.receipts import ReceiptStore

            items = ReceiptStore().list_for(str(p.get("doc_id") or ""), limit=int(p.get("limit") or 50))
            await channel.send_response(ws, req_id, ok=True, payload={"receipts": items})
        except Exception as e:  # noqa: BLE001
            logger.exception("[clouddoc.receipts] %s", e)
            await channel.send_response(ws, req_id, ok=False, error=str(e), code="INTERNAL_ERROR")

    async def unhighlight(ws, req_id, params, session_id):
        await call(ws, req_id, "unhighlight", str(params_of(params).get("receipt_id") or ""))

    async def set_mode(ws, req_id, params, session_id):
        await call(ws, req_id, "set_mode", str(params_of(params).get("mode") or ""))

    async def set_model(ws, req_id, params, session_id):
        await call(ws, req_id, "set_model", str(params_of(params).get("model_name") or ""))

    async def set_doc_model(ws, req_id, params, session_id):
        p = params_of(params)
        await call(
            ws, req_id, "set_doc_model",
            str(p.get("doc_id") or ""), str(p.get("model_name") or ""),
        )

    async def set_poll_interval(ws, req_id, params, session_id):
        # How often the watcher looks: the half of first-response time a deployment
        # can actually choose.
        await call(ws, req_id, "set_poll_interval", params_of(params).get("seconds"))

    return {
        "clouddoc.get_conf": get_conf,
        "clouddoc.list_docs": list_docs,
        "clouddoc.sync_shared_docs": sync_shared_docs,
        "clouddoc.sync_all_shared_docs": sync_all_shared_docs,
        "clouddoc.list_keys": list_keys,
        "clouddoc.delete_key": delete_key,
        "clouddoc.add_doc": add_doc,
        "clouddoc.update_doc": update_doc,
        "clouddoc.add_connection": add_connection,
        "clouddoc.remove_connection": remove_connection,
        "clouddoc.watch_list": watch_list,
        "clouddoc.watch_usage": watch_usage,
        "clouddoc.set_mode": set_mode,
        "clouddoc.set_model": set_model,
        "clouddoc.set_doc_model": set_doc_model,
        "clouddoc.set_poll_interval": set_poll_interval,
        "clouddoc.watch_set": watch_set,
        "clouddoc.watch_revoke": watch_revoke,
        "clouddoc.watch_revoke_all": watch_revoke_all,
        # The panel acts on a selection: what is being turned on or off is on screen
        # while it is decided.
        "clouddoc.watch_set_many": watch_set_many,
        "clouddoc.watch_revoke_many": watch_revoke_many,
        "clouddoc.watch_audit": watch_audit,
        "clouddoc.receipts": receipts,
        "clouddoc.unhighlight": unhighlight,
    }


def register_methods(channel: Any, panel_ref: Any) -> dict[str, Handler]:
    """Register every ``clouddoc.*`` method on the channel and, when a panel exists,
    start the ledger watch that pushes ``clouddoc.receipts_changed`` to every client.
    Returns the table that was registered.
    """
    methods = build_methods(channel, panel_ref)
    for name, handler in methods.items():
        channel.register_method(name, handler)
    if _resolve(panel_ref) is not None:
        # Receipts land from other processes; the gateway watches the shared ledger
        # file and pushes, so the workbench does not have to poll.
        from jiuwenswarm.clouddoc.panel.receipts_watch import watch_receipts_file

        asyncio.create_task(
            watch_receipts_file(channel.broadcast_event),
            name="clouddoc.receipts_watch",
        )
    return methods
