"""The clouddoc.* method table: the shell every RPC goes through.

A missing panel is a guidance state, not an error; a bad request never reaches the
panel; an exception out of the panel becomes a response, so an RPC can fail but
never hang.
"""

from __future__ import annotations

import pytest

from jiuwenswarm.clouddoc.host import web


class _Channel:
    def __init__(self):
        self.responses = []
        self.methods = {}
        self.events = []

    async def send_response(self, ws, req_id, *, ok, payload=None, error=None, code=None):
        self.responses.append({"req_id": req_id, "ok": ok, "payload": payload, "error": error, "code": code})

    def register_method(self, name, handler):
        self.methods[name] = handler

    async def broadcast_event(self, *a, **kw):
        self.events.append((a, kw))


class _Panel:
    def __init__(self):
        self.calls = []

    async def get_conf(self):
        return {"enabled": True, "mode": "mandate"}

    async def list_docs(self):
        return [{"doc_id": "d1"}]

    async def watch_set(self, doc_id, mode, *, expires_at=None, permanent=False, budget=None):
        self.calls.append(("watch_set", doc_id, mode, expires_at, permanent, budget))
        return {"ok": True}

    async def watch_set_many(self, ids, mode):
        self.calls.append(("watch_set_many", ids, mode))
        return {"ok": True}

    async def add_doc(self, url, connection_id=None):
        self.calls.append(("add_doc", url, connection_id))
        return {"ok": True, "doc_id": "d2"}

    async def set_poll_interval(self, seconds):
        self.calls.append(("set_poll_interval", seconds))
        return {"ok": True}

    async def watch_audit(self, limit):
        self.calls.append(("watch_audit", limit))
        return {"items": []}

    async def remove_connection(self, conn_id):
        raise RuntimeError("the key file is gone")


EXPECTED = {
    "clouddoc.get_conf", "clouddoc.list_docs", "clouddoc.sync_shared_docs",
    "clouddoc.sync_all_shared_docs", "clouddoc.list_keys", "clouddoc.delete_key",
    "clouddoc.add_doc", "clouddoc.update_doc", "clouddoc.add_connection",
    "clouddoc.remove_connection", "clouddoc.watch_list", "clouddoc.watch_usage",
    "clouddoc.set_mode", "clouddoc.set_model", "clouddoc.set_doc_model",
    "clouddoc.set_poll_interval", "clouddoc.watch_set", "clouddoc.watch_revoke",
    "clouddoc.watch_revoke_all", "clouddoc.watch_set_many", "clouddoc.watch_revoke_many",
    "clouddoc.watch_audit", "clouddoc.receipts", "clouddoc.unhighlight",
}


def test_the_table_names_every_method_the_frontend_calls():
    assert set(web.build_methods(_Channel(), None)) == EXPECTED


@pytest.mark.asyncio
async def test_a_missing_panel_answers_as_a_guidance_state_not_an_error():
    ch = _Channel()
    m = web.build_methods(ch, None)
    await m["clouddoc.get_conf"](None, "r1", {}, "s")
    await m["clouddoc.list_docs"](None, "r2", {}, "s")
    await m["clouddoc.watch_set"](None, "r3", {"doc_id": "d1", "mode": "apply_scoped"}, "s")
    await m["clouddoc.receipts"](None, "r4", {"doc_id": "d1"}, "s")
    assert [r["ok"] for r in ch.responses] == [True, True, True, True]
    assert ch.responses[0]["payload"] == {"enabled": False}
    assert ch.responses[1]["payload"] == {"enabled": False, "docs": []}


@pytest.mark.asyncio
async def test_the_panel_reference_is_resolved_on_every_call():
    """The gateway hands over a cell it may rebind; the table must not capture the
    panel it saw at registration."""
    ch = _Channel()
    cell = {"value": None}
    m = web.build_methods(ch, cell)
    await m["clouddoc.get_conf"](None, "r1", {}, "s")
    cell["value"] = _Panel()
    await m["clouddoc.get_conf"](None, "r2", {}, "s")
    assert ch.responses[0]["payload"] == {"enabled": False}
    assert ch.responses[1]["payload"] == {"enabled": True, "mode": "mandate"}


@pytest.mark.asyncio
async def test_a_bad_request_is_refused_before_the_panel_is_touched():
    ch = _Channel()
    panel = _Panel()
    m = web.build_methods(ch, panel)
    await m["clouddoc.add_doc"](None, "r1", {}, "s")
    await m["clouddoc.update_doc"](None, "r2", {"doc_id": ""}, "s")
    await m["clouddoc.delete_key"](None, "r3", None, "s")
    await m["clouddoc.add_connection"](None, "r4", {"filename": "k.json"}, "s")
    await m["clouddoc.remove_connection"](None, "r5", "not-a-dict", "s")
    assert [r["code"] for r in ch.responses] == ["BAD_REQUEST"] * 5
    assert all(r["ok"] is False for r in ch.responses)
    assert panel.calls == []


@pytest.mark.asyncio
async def test_parameters_are_coerced_the_way_the_panel_expects():
    ch = _Channel()
    panel = _Panel()
    m = web.build_methods(ch, panel)
    await m["clouddoc.watch_set"](
        None, "r1", {"doc_id": "d1", "mode": "apply_scoped", "permanent": 1, "budget": 5}, "s"
    )
    await m["clouddoc.watch_set_many"](None, "r2", {"doc_ids": ["a", "", None, 3], "mode": "apply_scoped"}, "s")
    await m["clouddoc.watch_set_many"](None, "r3", {"doc_ids": "a", "mode": "apply_scoped"}, "s")
    await m["clouddoc.watch_audit"](None, "r4", {}, "s")
    await m["clouddoc.set_poll_interval"](None, "r5", {"seconds": "45"}, "s")
    await m["clouddoc.add_doc"](None, "r6", {"url": "https://docs.google.com/document/d/x"}, "s")
    assert panel.calls == [
        ("watch_set", "d1", "apply_scoped", None, True, 5),
        ("watch_set_many", ["a", "3"], "apply_scoped"),
        ("watch_set_many", [], "apply_scoped"),
        ("watch_audit", 100),
        ("set_poll_interval", "45"),
        ("add_doc", "https://docs.google.com/document/d/x", None),
    ]
    assert ch.responses[-1]["payload"] == {"ok": True, "doc_id": "d2"}
    assert ch.responses[1]["payload"] == {"ok": True}


@pytest.mark.asyncio
async def test_an_exception_out_of_the_panel_becomes_a_response():
    ch = _Channel()
    m = web.build_methods(ch, _Panel())
    await m["clouddoc.remove_connection"](None, "r1", {"connection_id": "google:sa@x"}, "s")
    (r,) = ch.responses
    assert r["ok"] is False
    assert r["code"] == "INTERNAL_ERROR"
    assert "the key file is gone" in r["error"]


@pytest.mark.asyncio
async def test_list_docs_wraps_the_rows_with_the_enabled_flag():
    ch = _Channel()
    m = web.build_methods(ch, _Panel())
    await m["clouddoc.list_docs"](None, "r1", {}, "s")
    assert ch.responses[0]["payload"] == {"enabled": True, "docs": [{"doc_id": "d1"}]}


@pytest.mark.asyncio
async def test_registration_puts_every_method_on_the_channel(monkeypatch):
    ch = _Channel()
    started = []
    monkeypatch.setattr(web.asyncio, "create_task", lambda coro, name=None: (started.append(name), coro.close()))
    web.register_methods(ch, None)
    assert set(ch.methods) == EXPECTED
    assert started == [], "no panel, no ledger watch"

    ch2 = _Channel()
    web.register_methods(ch2, {"value": _Panel()})
    assert set(ch2.methods) == EXPECTED
    assert started == ["clouddoc.receipts_watch"]
