"""``blackboard.*`` methods on this jiuwenswarm's web channel.

The browser talks only to its own jiuwenswarm. Host methods are proxied to the
chosen host (``params.host``, else the default host) with the member token.
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import INTERNAL, BlackboardError, invalid

if TYPE_CHECKING:
    from jiuwenswarm.extensions.blackboard.client.runtime import ClientRuntime
    from jiuwenswarm.extensions.blackboard.host.controller import HostController

logger = logging.getLogger(__name__)

Operation = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _handler(channel: Any, name: str, operation: Operation) -> Callable[..., Awaitable[None]]:
    async def handler(ws, req_id, params, session_id):  # noqa: ANN001
        del session_id
        try:
            payload = await operation(dict(params) if isinstance(params, dict) else {})
        except BlackboardError as exc:
            await channel.send_response(
                ws, req_id, ok=False, error=exc.message, code=exc.code, payload={"details": exc.details}
            )
            return
        except Exception:  # noqa: BLE001 - the browser gets a stable code, the log gets the trace
            logger.exception("blackboard: %s failed", name)
            await channel.send_response(
                ws, req_id, ok=False, error="Blackboard could not complete the request", code=INTERNAL
            )
            return
        await channel.send_response(ws, req_id, ok=True, payload=payload)

    return handler


def _proxy(client: "ClientRuntime", method: str) -> Operation:
    async def run(params: dict[str, Any]) -> dict[str, Any]:
        host_id = params.pop("host", None)
        if host_id is not None and not isinstance(host_id, str):
            raise invalid("host must be a host id", field="host")
        return await client.call(host_id or None, method, params)

    return run


def _reference_upload(client: "ClientRuntime") -> Operation:
    """``{host?, workspace_id, name, mime?, note?, data}`` with the file as base64, sent on as multipart."""

    async def run(params: dict[str, Any]) -> dict[str, Any]:
        host_id = params.get("host")
        workspace_id, name, data = params.get("workspace_id"), params.get("name"), params.get("data")
        if not isinstance(workspace_id, str) or not workspace_id:
            raise invalid("workspace_id is required", field="workspace_id")
        if not isinstance(name, str) or not name.strip():
            raise invalid("name is required", field="name")
        if not isinstance(data, str):
            raise invalid("data must be the file as base64", field="data")
        try:
            content = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise invalid("data must be the file as base64", field="data") from exc
        mime = params.get("mime") if isinstance(params.get("mime"), str) and params.get("mime") else "application/octet-stream"
        note = params.get("note") if isinstance(params.get("note"), str) else ""
        return await client.upload(
            host_id if isinstance(host_id, str) and host_id else None,
            workspace_id,
            name=name.strip(),
            content=content,
            mime=mime,
            note=note,
        )

    return run


def register_rpcs(channel: Any, client: "ClientRuntime", host: "HostController") -> list[str]:
    registered: list[str] = []

    def add(name: str, operation: Operation) -> None:
        channel.register_method(name, _handler(channel, name, operation), local_only=True)
        registered.append(name)

    async def hosts_list(params: dict[str, Any]) -> dict[str, Any]:
        return client.hosts_view()

    async def hosts_join(params: dict[str, Any]) -> dict[str, Any]:
        display_name = params.get("display_name")
        return await client.join(
            str(params.get("url") or ""), display_name if isinstance(display_name, str) and display_name.strip() else None
        )

    async def hosts_remove(params: dict[str, Any]) -> dict[str, Any]:
        await client.remove(str(params.get("host") or ""))
        return client.hosts_view()

    async def hosts_set_default(params: dict[str, Any]) -> dict[str, Any]:
        await client.set_default(str(params.get("host") or ""))
        return client.hosts_view()

    async def host_status(params: dict[str, Any]) -> dict[str, Any]:
        return host.status()

    async def host_set_settings(params: dict[str, Any]) -> dict[str, Any]:
        settings = params.get("settings")
        if not isinstance(settings, dict):
            raise invalid("settings must be an object", field="settings")
        return await host.apply_settings(settings)

    add(p.HOSTS_LIST, hosts_list)
    add(p.HOSTS_JOIN, hosts_join)
    add(p.HOSTS_REMOVE, hosts_remove)
    add(p.HOSTS_SET_DEFAULT, hosts_set_default)
    add(p.HOST_STATUS, host_status)
    add(p.HOST_SET_SETTINGS, host_set_settings)
    add(p.REFERENCE_UPLOAD, _reference_upload(client))
    for method in p.HOST_METHODS:
        add(method, _proxy(client, method))
    return registered
