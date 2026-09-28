from __future__ import annotations

import pytest

from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.runtime import HostRuntime
from jiuwenswarm.extensions.blackboard.host.secrets import load_or_create
from jiuwenswarm.extensions.blackboard.host.store import Store, meta
from jiuwenswarm.extensions.blackboard.tests.backend.support import HostWorld, RecordingHub, free_port


@pytest.fixture
async def store(tmp_path):
    store = Store(tmp_path / "blackboard.db")
    await store.open()
    yield store
    await store.close()


@pytest.fixture
async def world(store, tmp_path):
    hub = RecordingHub()
    ctx = HostContext(
        store=store,
        hub=hub,  # type: ignore[arg-type]
        secrets=load_or_create(tmp_path / "secrets.json"),
        host_uid=await store.transact(meta.ensure_host_uid),
        version="0.1.0",
        get_settings=lambda: HostSettings(port=19999),
    )
    return HostWorld(ctx, hub)


@pytest.fixture
async def host(tmp_path):
    """A running host on a free port. Yields the runtime; ``runtime.base`` is its URL."""
    settings = HostSettings(enabled=True, port=free_port())
    runtime = HostRuntime(lambda: settings, tmp_path / "host", "0.1.0")
    await runtime.start()
    runtime.base = settings.base_url()  # type: ignore[attr-defined]
    yield runtime
    await runtime.stop()
