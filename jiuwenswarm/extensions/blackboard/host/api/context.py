"""What every request handler of the host needs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.common.errors import (
    DISABLED,
    FORBIDDEN,
    NOT_LINKED,
    UNAUTHORIZED,
    UNAVAILABLE,
    BlackboardError,
)
from jiuwenswarm.extensions.blackboard.common.tokens import hash_token
from jiuwenswarm.extensions.blackboard.host.api.events import EventHub
from jiuwenswarm.extensions.blackboard.host.api.locks import LockWaits
from jiuwenswarm.extensions.blackboard.host.api.ratelimit import BOT_CALLS_PER_MINUTE, READS_PER_MINUTE, RateLimiter
from jiuwenswarm.extensions.blackboard.host.secrets import HostSecrets
from jiuwenswarm.extensions.blackboard.host.store import Store, bots, users
from jiuwenswarm.extensions.blackboard.host.store.models import Bot, User

if TYPE_CHECKING:
    from jiuwenswarm.extensions.blackboard.host.docservice_manager import DocServiceClient, DocServiceManager

_TOUCH_INTERVAL_S = 60.0

NOT_LINKED_MESSAGE = (
    "This IM account is not connected to a Blackboard user on this host. In the jiuwenswarm web app, open "
    "Blackboard settings, choose Connect under Connected IM accounts, and send the code to this bot."
)


@dataclass
class HostContext:
    store: Store
    hub: EventHub
    secrets: HostSecrets
    host_uid: str
    version: str
    get_settings: Callable[[], HostSettings]
    # The document service (milestone 3); None where only milestone 2 features run.
    docs: "DocServiceManager | None" = None
    # Where reference files are kept: <files_dir>/<workspace id>/<reference id><ext>.
    files_dir: Path | None = None
    # Where exports wait to be downloaded: <exports_dir>/<export id>/<file name>.
    exports_dir: Path | None = None
    lock_waits: LockWaits = field(default_factory=LockWaits)
    limits: RateLimiter = field(default_factory=RateLimiter)
    _last_touch: dict[str, float] = field(default_factory=dict)

    @property
    def settings(self) -> HostSettings:
        return self.get_settings()

    def doc_client(self) -> "DocServiceClient":
        if self.docs is None:
            raise BlackboardError(UNAVAILABLE, "this host runs without a document service")
        return self.docs.require_client()

    def docservice_status(self) -> dict:
        return self.docs.status() if self.docs is not None else {"status": "unavailable", "reason": "not_configured"}

    def invite_url(self, code: str) -> str:
        return f"{self.settings.base_url()}/blackboard/join/{code}"

    async def host_name(self) -> str:
        if self.settings.name:
            return self.settings.name
        operator = await self.store.read(users.operator)
        return f"{operator.display_name}'s Blackboard" if operator else "Blackboard"

    async def host_info(self) -> dict[str, str]:
        return {
            "host_uid": self.host_uid,
            "name": await self.host_name(),
            "public_url": self.settings.base_url(),
            "doc_public_url": self.settings.doc_public_url,
        }

    async def authenticate(self, token: str | None) -> User:
        if not token:
            raise BlackboardError(UNAUTHORIZED, "a member token is required")
        user = await self.store.read(lambda c: users.by_token_hash(c, hash_token(token)))
        if user is None:
            raise BlackboardError(UNAUTHORIZED, "unknown member token")
        if user.status != "active":
            raise BlackboardError(DISABLED, "this user is disabled on the host")
        now = time.monotonic()
        if now - self._last_touch.get(user.id, 0.0) > _TOUCH_INTERVAL_S:
            self._last_touch[user.id] = now
            await self.store.transact(lambda c: users.touch(c, user.id))
        return user

    async def bot_for(self, token: str | None) -> Bot | None:
        """The shared bot a token belongs to, or None when it is no bot's."""
        if not token:
            return None
        bot = await self.store.read(lambda c: bots.by_token_hash(c, hash_token(token)))
        if bot is None:
            return None
        if bot.revoked_at is not None:
            raise BlackboardError(UNAUTHORIZED, "this bot was revoked on the host")
        now = time.monotonic()
        if now - self._last_touch.get(bot.id, 0.0) > _TOUCH_INTERVAL_S:
            self._last_touch[bot.id] = now
            await self.store.transact(lambda c: bots.touch(c, bot.id))
        return bot

    async def acting_for(self, bot: Bot, method: str, on_behalf: str | None) -> User | None:
        """Who a bot's call runs as: nobody for the bot's own methods, else the connected person named
        by the on-behalf-of header, for reading only."""
        self.limits.check(f"bot:{bot.id}", BOT_CALLS_PER_MINUTE)
        if method in p.BOT_OWN_METHODS:
            return None
        if method not in p.BOT_READ_METHODS:
            raise BlackboardError(FORBIDDEN, "a shared bot can only read", {"method": method})
        platform, _, external_id = (on_behalf or "").partition(":")
        if not platform or not external_id:
            raise BlackboardError(NOT_LINKED, NOT_LINKED_MESSAGE)
        self.limits.check(f"identity:{bot.id}:{platform}:{external_id}", READS_PER_MINUTE)
        found = await self.store.read(lambda c: bots.identity(c, platform, external_id))
        if found is None:
            raise BlackboardError(NOT_LINKED, NOT_LINKED_MESSAGE, {"platform": platform})
        user = await self.store.read(lambda c: users.get(c, found.user_id))
        if user is None or user.status != "active":
            raise BlackboardError(DISABLED, "this user is disabled on the host")
        return user
