"""index.html must not be cacheable; hashed assets must stay cacheable."""

from __future__ import annotations

import sys
import threading
import types
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

bootstrap_module = types.ModuleType("jiuwenswarm.agents.harness.team.bootstrap")
bootstrap_module.configure_agent_teams_home = lambda: None
sys.modules.setdefault(bootstrap_module.__name__, bootstrap_module)

from jiuwenswarm.channels.web.app_web import _SpaStaticHandler


def _serve(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><script type="module" src="/assets/index-abc123.js"></script>'
    )
    (dist / "assets" / "index-abc123.js").write_text("console.log('build 1')")

    class Handler(_SpaStaticHandler):
        project_root = tmp_path
        workspace_root = tmp_path / "agent"
        agent_teams_root = tmp_path / "agent-teams"
        logs_root = tmp_path / "logs"
        auto_harness_root = tmp_path / "auto-harness"
        api_target = ""
        ws_target = ""

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(dist), **kw)

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


def _headers_for(server, path):
    conn = HTTPConnection("127.0.0.1", server.server_port)
    conn.request("GET", path)
    resp = conn.getresponse()
    try:
        resp.read()
        return resp.status, resp.getheader("Cache-Control")
    finally:
        conn.close()


def test_index_is_never_served_from_cache(tmp_path):
    """A cached index.html pins the browser to the previous build's JavaScript.

    Nothing looks broken when that happens -- the page renders and silently runs old
    code -- so the symptom reaches users as "the new feature does nothing".
    """
    server = _serve(tmp_path)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        status, cache = _headers_for(server, "/")
        assert status == 200
        assert cache is not None and "no-cache" in cache, "index.html 可被缓存"

        # The SPA fallback returns index.html under any unknown path, and it is the
        # path a returning user actually requests.
        status, cache = _headers_for(server, "/chat/new")
        assert status == 200
        assert cache is not None and "no-cache" in cache, "SPA 回退路径漏掉了"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_hashed_assets_stay_cacheable(tmp_path):
    """Their names change whenever their contents do, so re-fetching them is waste."""
    server = _serve(tmp_path)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        status, cache = _headers_for(server, "/assets/index-abc123.js")
        assert status == 200
        assert cache is None or "no-cache" not in cache, "带 hash 的资源被误加了 no-cache"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
