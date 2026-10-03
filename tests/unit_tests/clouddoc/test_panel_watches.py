"""The standing-mandate registry (PR2b): lifecycle, gate verdicts, budget, audit.

Safety behaviors get three-shot repetition per the §13 discipline where the
behavior guards authority (revocation intercepting, a retired state's entries
being tombstoned rather than freed, no-watch refusing).
"""

from __future__ import annotations


import pytest

from jiuwenswarm.clouddoc.authority.watch_registry import (
    WatchRegistry,
)


@pytest.fixture()
def reg(tmp_path):
    clock = {"t": 1_000_000.0}
    # The rolling-window loop brake is disabled here (rate_max=0) so the gate and
    # daily-budget tests exercise exactly what they mean; the brake has its own fixture
    # and tests below.
    r = WatchRegistry(
        tmp_path / "watches.json", now_fn=lambda: clock["t"], rate_max=0
    )
    r.clock = clock  # test handle
    return r


@pytest.fixture()
def reg_rated(tmp_path):
    """A registry with the loop brake on, tight for the test: 3 per 60s."""
    clock = {"t": 1_000_000.0}
    r = WatchRegistry(
        tmp_path / "watches.json", now_fn=lambda: clock["t"],
        rate_max=3, rate_window_seconds=60.0,
    )
    r.clock = clock
    return r


@pytest.mark.asyncio
async def test_watch_set_keeps_silence_and_forever_apart(reg):
    """E1 at the RPC seam: omission issues the default term, permanent=true is
    the owner's explicit word, and an explicit timestamp is honored verbatim.
    Over JSON a missing field and null both arrive as None -- the flag is what
    keeps the two meanings apart.
    """
    from jiuwenswarm.clouddoc.panel.service import CloudDocPanel
    from jiuwenswarm.clouddoc.authority.watch_registry import DEFAULT_WATCH_TTL_SECONDS

    import types

    panel = object.__new__(CloudDocPanel)
    panel._registry = lambda: reg
    # watch_set refuses an id nobody adopted; this rig only exercises the term
    # semantics, so every id counts as adopted.
    panel._reg = types.SimpleNamespace(find_doc=lambda _doc_id: object())

    out = await panel.watch_set("d-def", "apply_scoped")
    assert out["entry"]["expires_at"] == 1_000_000.0 + DEFAULT_WATCH_TTL_SECONDS

    out = await panel.watch_set("d-perm", "apply_scoped", permanent=True)
    assert out["entry"]["expires_at"] is None

    out = await panel.watch_set("d-ts", "apply_scoped", expires_at=1_000_500.0)
    assert out["entry"]["expires_at"] == 1_000_500.0


@pytest.mark.asyncio
async def test_watch_usage_reads_granted_minus_used(reg, tmp_path, monkeypatch):
    """The panel view: the registry's grant beside the ledger's writes, and the
    friction hint when denials pile up.
    """
    import jiuwenswarm.clouddoc.receipts as rc
    from jiuwenswarm.clouddoc.panel.service import CloudDocPanel

    monkeypatch.setattr(rc, "get_receipts_path", lambda: tmp_path / "r.json")
    store = rc.ReceiptStore(tmp_path / "r.json")
    rid = store.begin("d1", [{"old": "旧", "new": "新", "for_comment_ids": []}],
                      highlight=False, executor="panel", source="apply_for_comment")
    store.commit(rid, revision_after="rev1")

    reg.issue("d1", "apply_scoped")
    reg.note_dispatch("d1")
    for _ in range(3):
        reg.note_denied("d1", "over_budget")

    panel = object.__new__(CloudDocPanel)
    panel._registry = lambda: reg
    out = await panel.watch_usage("d1")
    assert out["ok"] and out["granted"]["mode"] == "apply_scoped"
    assert out["used"]["write_batches"] == 1
    assert out["used"]["dispatches"] == 1
    assert out["used"]["executors"] == ["panel"]
    assert "frequent_denials" in out["hints"]
    assert "idle_wide_grant" not in out["hints"], "有写入不算闲置"


@pytest.mark.asyncio
async def test_set_mode_persists_and_get_conf_reports_it(reg, tmp_path):
    """D21's switch: an explicit act that lands in the config and on the audit
    journal; the UI only ever offers mandate and direct.
    """
    from jiuwenswarm.clouddoc.panel.service import CloudDocPanel

    cfg = tmp_path / "config.yaml"
    cfg.write_text("clouddoc:\n  enabled: true\n", encoding="utf-8")
    panel = object.__new__(CloudDocPanel)
    panel._config_path = cfg
    panel._registry = lambda: reg

    out = await panel.set_mode("direct")
    assert out["ok"] and "mode: direct" in cfg.read_text()
    assert panel._current_mode() == "direct"
    assert any(a["event"] == "mode" and a.get("value") == "direct" for a in reg.audit_tail())

    assert not (await panel.set_mode("recorded"))["ok"], "隐藏档不可从 UI 设置"
    out = await panel.set_mode("mandate")
    assert out["ok"] and panel._current_mode() == "mandate"


@pytest.mark.asyncio
async def test_watch_set_refuses_the_retired_tier_without_rounding_up(reg):
    """A stale client naming ``reply_only`` gets a refusal, not an upgrade.

    Rounding an unrecognised level to the one that survives would grant write
    authority on a click that asked for less.
    """
    import types

    from jiuwenswarm.clouddoc.panel.service import CloudDocPanel

    panel = object.__new__(CloudDocPanel)
    panel._registry = lambda: reg
    panel._reg = types.SimpleNamespace(find_doc=lambda _doc_id: object())

    out = await panel.watch_set("d1", "reply_only")
    assert out["ok"] is False and "已退役" in out["detail"]
    assert reg.get("d1") is None, "被拒的档位不得落成任何 watch"

    out = await panel.watch_set("d1", "propose")
    assert out["ok"] is False and "未知档位" in out["detail"]
    assert reg.get("d1") is None
