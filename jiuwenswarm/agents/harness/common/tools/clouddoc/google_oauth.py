"""Google personal identity: the OAuth user-token flow, host-free (matrix S.1).

A personal Google connection acts as the person, with a user token rather than a
service-account key. Getting that token is a one-time consent: the person opens an
authorisation link, Google redirects the browser back to a loopback address this
process listens on, and the code in that redirect is exchanged for a refresh
token. The refresh token, together with the OAuth client that issued it, is
written as an ``authorized_user`` file (Google's own shape, mode 0600) and the
provider refreshes from it thereafter.

Everything with a network in it is injectable: the exchange takes a ``post``
callable, the receiver is a plain asyncio server, so the flow is tested end to
end without an OAuth client. Where the loopback cannot be reached (a remote
browser), the person pastes the redirected URL or the bare code instead.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import _SCOPES
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

SCOPES: tuple[str, ...] = tuple(_SCOPES)


def new_state() -> str:
    return secrets.token_urlsafe(24)


def build_auth_url(client_id: str, redirect_uri: str, state: str, scopes=SCOPES) -> str:
    """The consent link. ``access_type=offline`` and ``prompt=consent`` are what make
    Google issue a refresh token rather than a one-hour access token only."""
    if not client_id:
        raise ProviderError("invalid", "Google OAuth 未配置 client_id。")
    q = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(q)}"


def parse_code(text: str, *, expected_state: str | None = None) -> str:
    """Accept a bare authorisation code or the whole redirected URL the browser
    landed on. A URL carrying a different ``state`` is refused: it belongs to
    another attempt, and exchanging it would bind a token to the wrong request."""
    s = str(text or "").strip()
    if not s:
        raise ProviderError("invalid", "没有授权码。")
    if "://" in s or s.startswith("/?") or "code=" in s:
        query = urllib.parse.urlsplit(s).query if "://" in s or s.startswith("/") else s
        params = urllib.parse.parse_qs(query)
        code = (params.get("code") or [""])[0]
        state = (params.get("state") or [""])[0]
        if expected_state and state and state != expected_state:
            raise ProviderError("invalid", "授权回调的 state 与本次请求不符。")
        if not code:
            raise ProviderError("invalid", "回调地址里没有 code 参数。")
        return code
    return s


def _default_post(url: str, data: dict) -> dict:
    import requests

    resp = requests.post(url, data=data, timeout=30)
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": "invalid_response", "error_description": resp.text[:200]}
    if resp.status_code >= 400 and "error" not in payload:
        payload["error"] = f"http_{resp.status_code}"
    return payload


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    *,
    post: Callable[[str, dict], dict] | None = None,
) -> dict:
    """Trade the code for tokens. Returns Google's token payload; a payload
    without a refresh token is an error here, because a personal connection that
    cannot refresh is one that stops working in an hour."""
    if not client_id or not client_secret:
        raise ProviderError("invalid", "Google OAuth 未配置 client_id / client_secret。")
    payload = (post or _default_post)(TOKEN_URL, {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    })
    if not isinstance(payload, dict) or payload.get("error"):
        detail = ""
        if isinstance(payload, dict):
            detail = str(payload.get("error_description") or payload.get("error") or "")
        raise ProviderError("auth", f"授权码兑换失败：{detail or 'unknown'}")
    if not payload.get("refresh_token"):
        raise ProviderError(
            "auth",
            "Google 没有返回 refresh_token（通常是这个应用之前已授权过）。"
            "请到 https://myaccount.google.com/permissions 撤销该应用后重新授权。",
        )
    return payload


def authorized_user_info(
    client_id: str, client_secret: str, token_payload: dict, *, scopes=SCOPES,
    email: str = "", name: str = "",
) -> dict:
    """The file the provider refreshes from: Google's ``authorized_user`` shape,
    marked as a personal connection so the factory routes it."""
    return {
        "kind": "personal",
        "brand": "google",
        "type": "authorized_user",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": str(token_payload["refresh_token"]),
        "token_uri": TOKEN_URL,
        "scopes": list(scopes),
        "email": email,
        "name": name,
    }


def write_authorized_user_file(path: Path, info: dict) -> None:
    """Persist the token file with the private bits readable by the owner only."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=1)
    os.chmod(path, 0o600)


_PAGE = (
    "<!doctype html><meta charset=\"utf-8\"><title>JiuwenSwarm</title>"
    "<body style=\"font-family:sans-serif;padding:2em\">{body}</body>"
)


class LoopbackReceiver:
    """One-shot HTTP listener on a loopback port for the OAuth redirect.

    Binds an ephemeral port so two attempts never collide, accepts exactly one
    redirect carrying the expected ``state``, answers the browser with a short
    page and hands the code to whoever is awaiting ``wait``. Anything else --
    another path, a foreign state, an ``error`` parameter -- is answered and
    ignored; the wait keeps going until a good redirect or the timeout.
    """

    def __init__(self, state: str, *, host: str = "127.0.0.1") -> None:
        self._state = state
        self._host = host
        self._server: asyncio.AbstractServer | None = None
        self._code: asyncio.Future[str] | None = None
        self.port: int = 0
        self.redirect_uri: str = ""

    async def start(self, port: int = 0) -> str:
        loop = asyncio.get_running_loop()
        self._code = loop.create_future()
        self._server = await asyncio.start_server(self._handle, self._host, port)
        self.port = self._server.sockets[0].getsockname()[1]
        self.redirect_uri = f"http://{self._host}:{self.port}/"
        return self.redirect_uri

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            parts = line.decode("latin-1").split()
            path = parts[1] if len(parts) >= 2 else "/"
            # Drain the headers; the request body, if any, is not read.
            while True:
                h = await asyncio.wait_for(reader.readline(), timeout=10)
                if not h or h in (b"\r\n", b"\n"):
                    break
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            code = (params.get("code") or [""])[0]
            state = (params.get("state") or [""])[0]
            err = (params.get("error") or [""])[0]
            if err:
                body, status = f"授权被拒绝：{err}。可以关闭此页。", "200 OK"
            elif not code or state != self._state:
                body, status = "这不是本次授权的回调，已忽略。", "404 Not Found"
            else:
                body, status = "授权完成，可以回到 JiuwenSwarm 了。", "200 OK"
                if self._code is not None and not self._code.done():
                    self._code.set_result(code)
            page = _PAGE.format(body=body).encode("utf-8")
            writer.write(
                f"HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(page)}\r\nConnection: close\r\n\r\n".encode("latin-1") + page
            )
            await writer.drain()
        except Exception:  # noqa: BLE001 - a malformed request is not the flow's failure
            pass
        finally:
            writer.close()

    async def wait(self, timeout: float = 600.0) -> str:
        assert self._code is not None, "start() first"
        try:
            return await asyncio.wait_for(asyncio.shield(self._code), timeout=timeout)
        finally:
            await self.close()

    def deliver(self, code: str) -> None:
        """The manual fallback: a code pasted by the person settles the same wait."""
        if self._code is not None and not self._code.done():
            self._code.set_result(code)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            self._server = None


def identity_from_info(info: dict) -> tuple[str, str]:
    return str(info.get("email") or ""), str(info.get("name") or "")


def is_personal_google_file(data: Any) -> bool:
    return isinstance(data, dict) and (
        str(data.get("type") or "") == "authorized_user"
        or (str(data.get("kind") or "").lower() == "personal" and str(data.get("brand") or "").lower() == "google")
    )
