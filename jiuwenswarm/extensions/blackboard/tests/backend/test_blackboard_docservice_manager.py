"""The document service manager: a missing Node is reported, and a killed service comes back."""

from __future__ import annotations

from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.host.docservice_manager import DocServiceManager, node_args
from jiuwenswarm.extensions.blackboard.host.secrets import load_or_create
from jiuwenswarm.extensions.blackboard.tests.backend.support import eventually, free_port


def _manager(tmp_path, **settings) -> DocServiceManager:
    config = HostSettings(doc_port=free_port(), doc_api_port=free_port(), **settings)
    return DocServiceManager(
        data_dir=tmp_path, get_settings=lambda: config, secrets=load_or_create(tmp_path / "secrets.json"), version="test"
    )


async def test_without_node_the_service_is_reported_unavailable(tmp_path):
    manager = _manager(tmp_path, node_path=str(tmp_path / "no-node.exe"))
    manager.start()
    assert manager.status()["status"] == "unavailable" and manager.status()["reason"] == "node_missing"
    assert not await manager.wait_ready(0.1)
    await manager.stop()


async def test_a_killed_service_is_restarted(real_docservice, tmp_path):
    manager = _manager(tmp_path)
    manager.start()
    try:
        assert await manager.wait_ready(20), manager.status()
        first = manager.status()["pid"]
        manager._process.kill()
        await eventually(lambda: manager.running and manager.status()["pid"] not in (None, first), timeout=20)
        assert manager.status()["restarts"] == 1
        assert (await manager.client.health())["ok"] is True
    finally:
        await manager.stop()
    assert manager.status()["status"] == "stopped"


def test_node_before_22_13_gets_the_sqlite_flag(tmp_path):
    bundle = tmp_path / "server.mjs"
    assert "--experimental-sqlite" in node_args("v22.11.0", bundle)
    assert "--experimental-sqlite" not in node_args("v22.13.0", bundle)
    assert node_args("v26.5.0", bundle)[-1] == str(bundle)
