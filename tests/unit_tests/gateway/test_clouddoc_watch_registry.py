"""The standing-mandate registry (PR2b): lifecycle, gate verdicts, budget, audit.

Safety behaviors get three-shot repetition per the §13 discipline where the
behavior guards authority (revocation intercepting, suspension freezing,
no-watch refusing).
"""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.gateway.clouddoc.watch_registry import (
    MODES,
    WatchRegistry,
    WatchVerdict,
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


# ---------------------------------------------------------------- issue / gate


def test_no_watch_means_no_dispatch_three_ways(reg):
    # D2 zero-dispatch: the founding behavior, three shots.
    for doc in ("d1", "d2", "d3"):
        v = reg.check(doc)
        assert v == WatchVerdict(False, None, "no_watch")


def test_issue_then_dispatchable_with_mode(reg):
    reg.issue("d1", "reply_only")
    v = reg.check("d1")
    assert v.dispatchable and v.mode == "reply_only" and v.reason == "ok"
    reg.issue("d2", "apply_scoped")
    assert reg.check("d2").mode == "apply_scoped"


def test_issue_rejects_unknown_mode(reg):
    with pytest.raises(ValueError):
        reg.issue("d1", "off")  # off is a policy value, never a watch mode (M-4)
    with pytest.raises(ValueError):
        reg.issue("d1", "propose")


def test_reissue_is_modify_and_replaces_terms(reg):
    reg.issue("d1", "reply_only")
    reg.issue("d1", "apply_scoped", budget={"max_dispatches_per_day": 5})
    e = reg.get("d1")
    assert e["mode"] == "apply_scoped"
    events = [a["event"] for a in reg.audit_tail()]
    assert events == ["grant", "modify"]


# ------------------------------------------------------------------ revocation


def test_revoke_intercepts_three_ways(reg):
    for doc in ("d1", "d2", "d3"):
        reg.issue(doc, "apply_scoped")
        assert reg.is_write_live(doc)
        reg.revoke(doc)
        assert not reg.check(doc).dispatchable
        assert not reg.is_write_live(doc), "撤销必须立即拦截写入(D3 硬急停)"


def test_kill_switch_revokes_everything(reg):
    for doc in ("d1", "d2", "d3"):
        reg.issue(doc, "reply_only")
    assert reg.revoke_all() == 3
    for doc in ("d1", "d2", "d3"):
        assert reg.check(doc).reason == "no_watch"
        assert not reg.is_write_live(doc)
        assert reg.get(doc).get("revoked") is True, "急停也留碑"
    assert reg.revoke_all() == 0, "已撤销的条目不再计数"


def test_revocation_keeps_a_flagged_entry(reg):
    """The entry is the tombstone, not the journal alone: a lost audit line must not
    turn a revocation into a re-issue at the next startup."""
    reg.issue("d1", "apply_scoped")
    assert reg.revoke("d1") is True
    entry = reg.get("d1")
    assert entry is not None and entry["revoked"] is True
    assert entry["revoked_at"] == reg.clock["t"]
    assert entry["mode"] == "apply_scoped", "留碑保留原档位供面板显示"
    assert reg.check("d1").reason == "no_watch"
    assert not reg.is_write_live("d1")
    assert reg.revoke("d1") is False, "二次撤销无事发生"
    assert reg.suspend("d1") is True and reg.resume("d1") is True
    assert reg.check("d1").reason == "no_watch", "恢复不能复活撤销的条目"


def test_a_manual_grant_replaces_the_tombstone(reg):
    reg.issue("d1", "reply_only")
    reg.revoke("d1")
    reg.issue("d1", "apply_scoped", issued_by="manual")
    entry = reg.get("d1")
    assert not entry.get("revoked") and "revoked_at" not in entry
    assert reg.check("d1").dispatchable and reg.check("d1").mode == "apply_scoped"
    assert reg.is_write_live("d1")
    events = [a["event"] for a in reg.audit_tail()]
    assert events == ["grant", "revoke", "grant"], "盖过留碑是新的授予，不是变更"


# ----------------------------------------------------- the pre-write checkpoint


def test_write_liveness_holds_the_entry_to_the_turns_mode(reg):
    """A tier changed mid-turn intercepts the write: a turn dispatched under
    apply_scoped whose mandate now says reply_only is no longer write-live at
    that tier."""
    reg.issue("d1", "apply_scoped")
    assert reg.is_write_live("d1", mode="apply_scoped")
    reg.issue("d1", "reply_only")
    assert not reg.is_write_live("d1", mode="apply_scoped"), "降档必须拦截在途写入"
    assert reg.is_write_live("d1", mode="reply_only")
    assert reg.is_write_live("d1"), "不带档位的查询只问存续"


def test_write_liveness_ends_at_expiry(reg):
    reg.issue("d1", "apply_scoped")
    assert reg.is_write_live("d1")
    reg.clock["t"] += 31 * 24 * 3600
    assert not reg.is_write_live("d1"), "按时钟已过期，即使尚未被 check() 标记"
    assert reg.check("d1").reason == "expired"
    assert reg.get("d1")["expired"] is True
    assert not reg.is_write_live("d1"), "已标记过期同样不存续"


# ------------------------------------------------------------------ suspension


def test_suspend_freezes_but_preserves_terms_three_ways(reg):
    for doc in ("d1", "d2", "d3"):
        reg.issue(doc, "apply_scoped", budget={"max_edits_per_turn": 4})
        assert reg.suspend(doc)
        v = reg.check(doc)
        assert not v.dispatchable and v.reason == "suspended"
        assert not reg.is_write_live(doc), "挂起也拦在途写入前的新提交"
        assert reg.resume(doc)
        after = reg.check(doc)
        assert after.dispatchable and after.mode == "apply_scoped"
        assert reg.get(doc)["budget"] == {"max_edits_per_turn": 4}, "挂起≠撤销:条款保留"


def test_global_suspend_overrides_every_watch(reg):
    reg.issue("d1", "reply_only")
    reg.issue("d2", "apply_scoped")
    reg.suspend_all(by="biometric_lapse")
    assert reg.check("d1").reason == "global_suspended"
    assert reg.check("d2").reason == "global_suspended"
    assert not reg.is_write_live("d2")
    reg.resume_all()
    assert reg.check("d1").dispatchable


def test_suspend_missing_watch_returns_false(reg):
    assert not reg.suspend("ghost")
    assert not reg.resume("ghost")


# ---------------------------------------------------------------------- expiry


def test_expiry_flags_the_entry_and_keeps_it(reg):
    """E1: expiry ends the delegation but the entry stays as its own tombstone.

    Deleting on expiry is what let the adoption policy silently re-issue the
    watch at the next startup -- the calendar endpoint became a no-op."""
    reg.issue("d1", "reply_only", expires_at=1_000_100.0)
    assert reg.check("d1").dispatchable
    reg.clock["t"] = 1_000_200.0
    v = reg.check("d1")
    assert not v.dispatchable and v.reason == "expired"
    entry = reg.get("d1")
    assert entry is not None and entry.get("expired") is True, "到期留碑不删"
    assert any(a["event"] == "expire" for a in reg.audit_tail()), "到期必须留审计行"


def test_expiry_audit_line_lands_exactly_once(reg):
    reg.issue("d1", "reply_only", expires_at=1_000_100.0)
    reg.clock["t"] = 1_000_200.0
    reg.check("d1")
    reg.check("d1")
    reg.check("d1")
    assert sum(1 for a in reg.audit_tail() if a["event"] == "expire") == 1


def test_default_issuance_carries_the_default_term(reg):
    """E1: silence is not permanence -- an unstated term is the default TTL."""
    from jiuwenswarm.gateway.clouddoc.watch_registry import DEFAULT_WATCH_TTL_SECONDS

    reg.issue("d1", "reply_only")
    entry = reg.get("d1")
    assert entry["expires_at"] == 1_000_000.0 + DEFAULT_WATCH_TTL_SECONDS
    reg.clock["t"] = 1_000_000.0 + DEFAULT_WATCH_TTL_SECONDS + 1
    assert reg.check("d1").reason == "expired"


def test_explicit_permanent_has_no_calendar_endpoint(reg):
    """None stays legal, but only as the owner's explicit word (D3)."""
    reg.issue("d1", "reply_only", expires_at=None)
    reg.clock["t"] = 1_000_000.0 + 400 * 24 * 3600  # 400 days later
    assert reg.check("d1").dispatchable, "显式永久无日历终点"


def test_renewal_after_expiry_opens_a_fresh_window(reg):
    """Re-issuance is recertification: the expired flag must not survive it."""
    reg.issue("d1", "reply_only", expires_at=1_000_100.0)
    reg.clock["t"] = 1_000_200.0
    assert reg.check("d1").reason == "expired"
    reg.issue("d1", "reply_only")
    v = reg.check("d1")
    assert v.dispatchable, v.reason
    assert not reg.get("d1").get("expired")


def test_owner_revocation_is_terminal_for_the_policy(reg):
    """The adoption policy must not resurrect what the owner revoked."""
    reg.issue("d1", "reply_only", issued_by="policy")
    reg.revoke("d1")
    assert reg.terminated_by_owner("d1"), "audit 的最后一笔是 revoke"
    reg.issue("d1", "reply_only", issued_by="manual")
    assert not reg.terminated_by_owner("d1"), "手工再授权盖过撤销"
    assert not reg.terminated_by_owner("d-never-seen")


# ---------------------------------------------------------------------- budget


def test_budget_over_cap_stops_dispatch_but_not_writes(reg):
    reg.issue("d1", "apply_scoped", budget={"max_dispatches_per_day": 2})
    assert reg.check("d1").dispatchable
    reg.note_dispatch("d1")
    reg.note_dispatch("d1")
    v = reg.check("d1")
    assert not v.dispatchable and v.reason == "over_budget"
    # Budget bounds volume of NEW dispatches; it is not a revocation, so the
    # in-flight write checkpoint stays live.
    assert reg.is_write_live("d1")


def test_budget_refreshes_on_a_new_day_for_new_events_only(reg):
    reg.issue("d1", "apply_scoped", budget={"max_dispatches_per_day": 1})
    reg.note_dispatch("d1")
    assert reg.check("d1").reason == "over_budget"
    reg.clock["t"] += 24 * 3600
    assert reg.check("d1").dispatchable, "预算按天刷新"


def test_budget_survives_restart(reg, tmp_path):
    reg.issue("d1", "apply_scoped", budget={"max_dispatches_per_day": 1})
    reg.note_dispatch("d1")
    fresh = WatchRegistry(tmp_path / "watches.json", now_fn=lambda: reg.clock["t"])
    assert fresh.check("d1").reason == "over_budget", "重启不清预算计数"


def test_no_budget_means_no_cap(reg):
    reg.issue("d1", "apply_scoped")  # D9: optional, default no budget
    for _ in range(50):
        reg.note_dispatch("d1")
    assert reg.check("d1").dispatchable


# --------------------------------------------------------------------- storage


def test_registry_is_cross_process_readable(reg, tmp_path):
    reg.issue("d1", "apply_scoped")
    # A second process (IC-3), on the same clock: the default term is thirty days
    # from the issuing clock, and a real wall clock would read that as expired.
    other = WatchRegistry(tmp_path / "watches.json", now_fn=lambda: reg.clock["t"])
    assert other.get("d1")["mode"] == "apply_scoped"
    assert other.is_write_live("d1")
    reg.revoke("d1")
    assert not other.is_write_live("d1"), "撤销必须跨进程立即可见"


def test_corrupt_file_treated_as_empty_not_crash(reg, tmp_path):
    (tmp_path / "watches.json").write_text("{not json", encoding="utf-8")
    assert reg.check("d1").reason == "no_watch"


def test_audit_covers_full_lifecycle(reg):
    reg.issue("d1", "reply_only")
    reg.issue("d1", "apply_scoped")
    reg.suspend("d1")
    reg.resume("d1")
    reg.revoke("d1")
    events = [a["event"] for a in reg.audit_tail()]
    assert events == ["grant", "modify", "suspend", "resume", "revoke"], (
        "D3:授予/变更/挂起/恢复/撤销各一行审计"
    )


def test_modes_constant_is_two_rungs():
    assert MODES == ("reply_only", "apply_scoped")  # D1: exactly two watch modes


# ------------------------------------------------------- panel term semantics


@pytest.mark.asyncio
async def test_watch_set_keeps_silence_and_forever_apart(reg):
    """E1 at the RPC seam: omission issues the default term, permanent=true is
    the owner's explicit word, and an explicit timestamp is honored verbatim.
    Over JSON a missing field and null both arrive as None -- the flag is what
    keeps the two meanings apart."""
    from jiuwenswarm.gateway.clouddoc.panel import CloudDocPanel
    from jiuwenswarm.gateway.clouddoc.watch_registry import DEFAULT_WATCH_TTL_SECONDS

    panel = object.__new__(CloudDocPanel)
    panel._registry = lambda: reg

    out = await panel.watch_set("d-def", "reply_only")
    assert out["entry"]["expires_at"] == 1_000_000.0 + DEFAULT_WATCH_TTL_SECONDS

    out = await panel.watch_set("d-perm", "reply_only", permanent=True)
    assert out["entry"]["expires_at"] is None

    out = await panel.watch_set("d-ts", "reply_only", expires_at=1_000_500.0)
    assert out["entry"]["expires_at"] == 1_000_500.0


# ------------------------------------------------------------ audit view (E1)


def test_usage_summary_counts_dispatches_and_denials(reg):
    reg.issue("d1", "apply_scoped")
    reg.note_dispatch("d1")
    reg.note_dispatch("d1")
    reg.note_denied("d1", "over_budget")
    reg.note_denied("d1", "suspended")
    reg.note_denied("d1", "over_budget")
    u = reg.usage_summary("d1")
    assert u["grants"] == 1 and u["dispatches"] == 2
    assert u["denials"] == {"over_budget": 2, "suspended": 1}
    assert u["last_grant_at"] == 1_000_000.0
    # another doc's lines never bleed in
    reg.issue("d2", "reply_only")
    assert reg.usage_summary("d2")["dispatches"] == 0


@pytest.mark.asyncio
async def test_watch_usage_reads_granted_minus_used(reg, tmp_path, monkeypatch):
    """The panel view: the registry's grant beside the ledger's writes, and the
    friction hint when denials pile up."""
    from jiuwenswarm.agents.harness.common.tools import clouddoc as _pkg
    import jiuwenswarm.agents.harness.common.tools.clouddoc.receipts as rc
    from jiuwenswarm.gateway.clouddoc.panel import CloudDocPanel

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
    journal; the UI only ever offers mandate and direct."""
    from jiuwenswarm.gateway.clouddoc.panel import CloudDocPanel

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


# ------------------------------------------------------ the rolling-window loop brake

def test_the_rate_brake_stops_a_burst_within_the_window(reg_rated):
    reg_rated.issue("d1", "apply_scoped")  # no daily budget at all
    assert reg_rated.check("d1").dispatchable
    for _ in range(3):
        reg_rated.note_dispatch("d1")
    v = reg_rated.check("d1")
    assert not v.dispatchable and v.reason == "rate_limited"
    # It is a pause, not a revocation: in-flight writes still checkpoint live.
    assert reg_rated.is_write_live("d1")


def test_the_rate_brake_recovers_after_the_window_passes(reg_rated):
    reg_rated.issue("d1", "apply_scoped")
    for _ in range(3):
        reg_rated.note_dispatch("d1")
    assert reg_rated.check("d1").reason == "rate_limited"
    reg_rated.clock["t"] += 61.0  # slide past the window
    assert reg_rated.check("d1").dispatchable, "窗口滑过后自行恢复"


def test_the_rate_brake_is_per_document(reg_rated):
    reg_rated.issue("d1", "apply_scoped")
    reg_rated.issue("d2", "apply_scoped")
    for _ in range(3):
        reg_rated.note_dispatch("d1")
    assert reg_rated.check("d1").reason == "rate_limited"
    assert reg_rated.check("d2").dispatchable, "一篇的回环不牵连另一篇"


def test_the_daily_budget_trips_before_the_rate_brake_when_tighter(reg_rated):
    # Both caps exist; check() reports the budget first, which is the tighter one here.
    reg_rated.issue("d1", "apply_scoped", budget={"max_dispatches_per_day": 2})
    reg_rated.note_dispatch("d1")
    reg_rated.note_dispatch("d1")
    assert reg_rated.check("d1").reason == "over_budget"
