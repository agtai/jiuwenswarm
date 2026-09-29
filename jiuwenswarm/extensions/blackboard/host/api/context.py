"""What every request handler of the host needs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.common.errors import DISABLED, UNAUTHORIZED, UNAVAILABLE, BlackboardError
from jiuwenswarm.extensions.blackboard.common.tokens import hash_token
from jiuwenswarm.extensions.blackboard.host.api.events import EventHub
from jiuwenswarm.extensions.blackboard.host.api.locks import LockWaits
from jiuwenswarm.extensions.blackboard.host.secrets import HostSecrets
from jiuwenswarm.extensions.blackboard.host.store import Store, users
from jiuwenswarm.extensions.blackboard.host.store.models import User

if TYPE_CHECKING:
    from jiuwenswarm.extensions.blackboard.host.docservice_manager import DocServiceClient, DocServiceManager

_TOUCH_INTERVAL_S = 60.0


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
    lock_waits: LockWaits = field(default_factory=LockWaits)
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
