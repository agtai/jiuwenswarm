"""The gateway service: loud startup checks, one registry even when empty, and a stop
order that lets a turn in flight finish before the client goes away.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from jiuwenswarm.clouddoc.host import gateway


@pytest.fixture
def config(monkeypatch):
    def _set(cfg):
        monkeypatch.setattr(gateway, "deployment_config", lambda: {"clouddoc": cfg})

    return _set


@pytest.fixture
def key(tmp_path):
    p = tmp_path / "sa.json"
    p.write_text(json.dumps({
        "type": "service_account",
        "client_email": "agent@example.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token", "private_key": "", "project_id": "p",
    }), encoding="utf-8")
    return str(p)


@pytest.fixture(autouse=True)
def _state_at_tmp(tmp_path, monkeypatch):
    from jiuwenswarm.clouddoc import settings

    ws = tmp_path / "ws"
    (ws / "config").mkdir(parents=True)
    monkeypatch.setattr(settings, "_workspace_provider", lambda: ws)
    yield
    monkeypatch.setattr(settings, "_workspace_provider", None)


@pytest.mark.asyncio
async def test_an_unconfigured_deployment_still_gets_a_registry(config):
    """The panel is the only way to add the first connection; a None registry would
    make every RPC answer "feature off" and a fresh install could never be set up.
    """
    config({"enabled": False})
    registry = await gateway.build_connections(agent_client=None)
    assert registry is not None
    assert registry.list() == []


@pytest.mark.asyncio
async def test_a_configured_connection_is_added_at_startup(config, key):
    config({"enabled": False, "connections": [{"credentials_file": key, "documents": ["1AAAABBBBCCCC"]}]})
    registry = await gateway.build_connections(agent_client=None)
    assert [c.credentials_file for c in registry.list()] == [key]
    assert registry.all_docs() == ["1AAAABBBBCCCC"]


@pytest.mark.asyncio
async def test_one_broken_connection_does_not_block_the_others(config, key, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    config({"enabled": False, "connections": [
        {"credentials_file": str(bad), "documents": ["d"]},
        {"credentials_file": key, "documents": ["1AAAABBBBCCCC"]},
    ]})
    registry = await gateway.build_connections(agent_client=None)
    assert [c.credentials_file for c in registry.list()] == [key]


@pytest.mark.asyncio
async def test_colliding_trigger_words_stop_the_feature_loudly(config, caplog):
    """Starting with a prefix collision is worse than not starting: not starting is at
    least visible.
    """
    config({"enabled": True, "conventions_marker": "   "})
    with caplog.at_level("ERROR"):
        registry = await gateway.build_connections(agent_client=None)
    assert registry is None
    assert any("did not start" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_the_policy_and_rate_settings_reach_the_registry(config, key):
    config({
        "enabled": False, "auto_watch_on_adopt": "apply_scoped",
        "dispatch_rate_max": 3, "dispatch_rate_window_seconds": 10,
        "connections": [{"credentials_file": key, "documents": []}],
    })
    registry = await gateway.build_connections(agent_client=None)
    assert registry.auto_watch_policy == "apply_scoped"
    assert registry._watch_registry._rate_max == 3
    assert registry._watch_registry._rate_window == 10.0


@pytest.mark.asyncio
async def test_discovery_is_off_without_a_panel_or_by_configuration(config):
    assert gateway.start_discovery(None) is None
    config({"auto_discover_shared": False})
    assert gateway.start_discovery(object()) is None


@pytest.mark.asyncio
async def test_discovery_interval_has_a_floor_and_a_default(config, monkeypatch):
    seen = []

    async def fake_loop(panel, *, interval_seconds):
        seen.append(interval_seconds)

    from jiuwenswarm.clouddoc.panel import service

    monkeypatch.setattr(service, "discover_shared_periodically", fake_loop)
    for raw, expected in ((5, 60.0), ("bogus", service.DISCOVERY_INTERVAL_SECONDS), (900, 900.0), (None, service.DISCOVERY_INTERVAL_SECONDS)):
        config({"discover_interval_seconds": raw})
        task = gateway.start_discovery(object())
        await task
    assert seen == [60.0, service.DISCOVERY_INTERVAL_SECONDS, 900.0, service.DISCOVERY_INTERVAL_SECONDS]


@pytest.mark.asyncio
async def test_the_service_stops_discovery_before_the_watchers(config, monkeypatch):
    order = []

    class _Conns:
        async def start_all(self):
            order.append("start")

        async def stop_all(self):
            order.append("stop_all")

        def all_docs(self):
            return []

    class _Panel:
        def __init__(self, conns):
            pass

        def commit_retirements(self):
            return []

    async def build(*, agent_client):
        return _Conns()

    async def loop(panel, *, interval_seconds):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            order.append("discovery cancelled")
            raise

    from jiuwenswarm.clouddoc.panel import service as panel_service

    monkeypatch.setattr(gateway, "build_connections", build)
    monkeypatch.setattr(panel_service, "CloudDocPanel", _Panel)
    monkeypatch.setattr(panel_service, "discover_shared_periodically", loop)
    config({})

    svc = gateway.CloudDocService()
    await svc.prepare(agent_client=None)
    assert svc.panel is not None and svc.connections is not None
    assert order == [], "preparing builds; it does not poll"
    await svc.start()
    await asyncio.sleep(0)  # let the discovery loop enter its sleep
    await svc.stop()
    assert order == ["start", "discovery cancelled", "stop_all"]


@pytest.mark.asyncio
async def test_the_service_without_extras_has_no_panel_and_stops_quietly(monkeypatch, config):
    async def build(*, agent_client):
        return None

    monkeypatch.setattr(gateway, "build_connections", build)
    svc = gateway.CloudDocService()
    await svc.prepare(agent_client=None)
    assert svc.panel is None
    await svc.start()
    await svc.stop()


def test_startup_and_shutdown_reference_no_unbound_names():
    """The shutdown path never fires during normal operation, so a missed rename there
    raises only as the process exits; only reading the structure finds it.
    """
    import ast
    import builtins
    import inspect

    tree = ast.parse(inspect.getsource(gateway))
    checked = 0
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bound = {
            t.id
            for n in ast.walk(func)
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.For, ast.AsyncFor))
            for t in ([n.target] if hasattr(n, "target") and n.target else getattr(n, "targets", []))
            if isinstance(t, ast.Name)
        }
        bound |= {a.arg for a in func.args.args + func.args.kwonlyargs}
        bound |= {
            alias.asname or alias.name.split(".")[0]
            for n in ast.walk(func)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for alias in n.names
        }
        bound |= {n.name for n in ast.walk(func) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        bound |= {h.name for n in ast.walk(func) if isinstance(n, ast.Try) for h in n.handlers if h.name}
        bound |= {
            t.id
            for n in ast.walk(func)
            if isinstance(n, ast.comprehension)
            for t in ast.walk(n.target)
            if isinstance(t, ast.Name)
        }
        bound |= {a.arg for n in ast.walk(func) if isinstance(n, ast.Lambda) for a in n.args.args}
        module_names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        module_names |= {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        module_names |= {alias.asname or alias.name.split(".")[0] for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) for alias in n.names}
        for n in ast.walk(func):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                checked += 1
                assert n.id in bound or n.id in module_names or n.id in dir(builtins) or n.id == "self", (
                    f"{func.name} reads {n.id!r}, which nothing binds"
                )
    assert checked
