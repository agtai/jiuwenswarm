from __future__ import annotations

import pytest

from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.host import docservice_manager
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.docservice_manager import NodeProblem, locate_node
from jiuwenswarm.extensions.blackboard.host.runtime import HostRuntime
from jiuwenswarm.extensions.blackboard.host.secrets import load_or_create
from jiuwenswarm.extensions.blackboard.host.store import Store, meta
from jiuwenswarm.extensions.blackboard.tests.backend.support import FakeDocs, HostWorld, RecordingHub, free_port


@pytest.fixture(autouse=True)
def _no_docservice(request, monkeypatch, tmp_path):
    """Hosts in tests run without Node unless the test asks for ``real_docservice``."""
    if "real_docservice" not in request.fixturenames:
        monkeypatch.setattr(docservice_manager, "BUNDLE", tmp_path / "no-bundle.mjs")


@pytest.fixture
def real_docservice():
    """The built document service and a Node that can run it, or the test is skipped."""
    try:
        locate_node("")
    except NodeProblem as exc:
        pytest.skip(f"no usable Node: {exc.reason}")
    if not docservice_manager.BUNDLE.exists():
        pytest.skip("the document service is not built (npm run build in host/docservice)")
    return docservice_manager.BUNDLE


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
        docs=FakeDocs(),  # type: ignore[arg-type]
        files_dir=tmp_path / "references",
    )
    return HostWorld(ctx, hub)


@pytest.fixture
async def host(tmp_path):
    """A running host on a free port. ``runtime.base`` is its URL."""
    settings = HostSettings(enabled=True, port=free_port(), doc_port=free_port(), doc_api_port=free_port())
    runtime = HostRuntime(lambda: settings, tmp_path / "host", "0.1.0")
    await runtime.start()
    runtime.base = settings.base_url()  # type: ignore[attr-defined]
    yield runtime
    await runtime.stop()
