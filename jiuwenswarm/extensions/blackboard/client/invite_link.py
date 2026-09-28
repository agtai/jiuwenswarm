"""Invite links look like ``<host url>/blackboard/join/<code>``."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from jiuwenswarm.extensions.blackboard.common.errors import invalid

_CODE = re.compile(r"^[a-z2-7]{20}$")


def parse_invite_link(link: str) -> tuple[str, str]:
    """Return ``(host base url, code)``. The host may sit under a path prefix
    behind a reverse proxy, so everything before ``/blackboard/join/`` is the base."""
    if not isinstance(link, str) or not link.strip():
        raise invalid("paste the invite link", field="url")
    parsed = urlparse(link.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise invalid("an invite link starts with http:// or https://", field="url")
    marker = "/blackboard/join/"
    index = parsed.path.find(marker)
    if index < 0:
        raise invalid("this is not a Blackboard invite link", field="url")
    code = parsed.path[index + len(marker):].strip("/")
    if not _CODE.match(code):
        raise invalid("the invite code in this link is not valid", field="url")
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path[:index]}".rstrip("/")
    return base, code
