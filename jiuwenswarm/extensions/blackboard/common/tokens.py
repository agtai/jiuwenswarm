"""Member tokens, invite codes, secrets, and signed document tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from jiuwenswarm.extensions.blackboard.common.errors import EXPIRED, UNAUTHORIZED, BlackboardError

MEMBER_TOKEN_PREFIX = "bbm_"
_BASE32 = "abcdefghijklmnopqrstuvwxyz234567"


def new_member_token() -> str:
    return MEMBER_TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_invite_code() -> str:
    """20 random base32 characters (100 bits)."""
    return "".join(secrets.choice(_BASE32) for _ in range(20))


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


_HEADER = _b64(json.dumps({"alg": "HS256", "typ": "BBDOC"}, separators=(",", ":")).encode())


def mint_doc_token(claims: dict[str, Any], secret: str, ttl_seconds: int = 3600) -> str:
    """Token for the document service: ``{uid, ws, doc, role}`` plus ``iat`` and ``exp``.

    The same format is verified in Node by the document service.
    """
    now = int(time.time())
    body = dict(claims)
    body["iat"] = now
    body["exp"] = now + ttl_seconds
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), f"{_HEADER}.{payload}".encode(), hashlib.sha256).digest()
    return f"{_HEADER}.{payload}.{_b64(signature)}"


def verify_doc_token(token: str, secret: str) -> dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        raise BlackboardError(UNAUTHORIZED, "malformed token")
    header, payload, signature = parts
    expected = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    try:
        given = _unb64(signature)
        claims = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise BlackboardError(UNAUTHORIZED, "malformed token") from exc
    if not hmac.compare_digest(given, expected):
        raise BlackboardError(UNAUTHORIZED, "bad token signature")
    if not isinstance(claims, dict) or not isinstance(claims.get("exp"), int):
        raise BlackboardError(UNAUTHORIZED, "malformed token")
    if claims["exp"] < int(time.time()):
        raise BlackboardError(EXPIRED, "token expired")
    return claims
