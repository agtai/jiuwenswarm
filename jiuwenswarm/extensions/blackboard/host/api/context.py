"""What every request handler of the host needs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.common.errors import DISABLED, UNAUTHORIZED, BlackboardError
from jiuwenswarm.extensions.blackboard.common.tokens import hash_token
from jiuwenswarm.extensions.blackboard.host.api.events import EventHub
from jiuwenswarm.extensions.blackboard.host.secrets import HostSecrets
from jiuwenswarm.extensions.blackboard.host.store import Store, users
from jiuwenswarm.extensions.blackboard.host.store.models import User

_TOUCH_INTERVAL_S = 60.0


@dataclass
class HostContext:
    store: Store
    hub: EventHub
    secrets: HostSecrets
    host_uid: str
    version: str
    get_settings: Callable[[], HostSettings]
    _last_touch: dict[str, float] = field(default_factory=dict)

    @property
    def settings(self) -> HostSettings:
        return self.get_settings()

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
