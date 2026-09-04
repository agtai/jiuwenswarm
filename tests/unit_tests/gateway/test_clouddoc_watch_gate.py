"""The dispatch gate (PR2b): the watcher × the standing-mandate registry.

The gate is D2's zero-dispatch default made mechanical: no watch, no turn — the
collaborator hears why once, the trigger is consumed (the signed cutline:
observation-time, fail-closed — a later grant covers new events only), and the
mode a dispatched turn carries is the registry's, snapshotted at dispatch (IC-1).
"""

from __future__ import annotations

import pytest

from jiuwenswarm.gateway.clouddoc.comment_watcher import CloudDocCommentWatcher, WatcherConfig
from jiuwenswarm.gateway.clouddoc.cursor_store import CloudDocStore
from jiuwenswarm.gateway.clouddoc.triggers import TriggerConfig
from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

from test_clouddoc_watcher import C, Clock, FakeProvider, DOC, SA


@pytest.fixture
async def gated(tmp_path):
    """The steady-state watcher rig, gated by a real registry."""
    prov = FakeProvider()
    store = CloudDocStore(tmp_path / "s.json", now_fn=Clock())
    reg = WatchRegistry(tmp_path / "w.json")
    dispatched: list[tuple] = []

    async def dispatch(doc_id, comment_id, metadata):
        dispatched.append((doc_id, comment_id, metadata))
        return "ok"

    w = CloudDocCommentWatcher(
        prov, store, TriggerConfig(sa_address=SA), WatcherConfig(),
        dispatch=dispatch, now_fn=Clock(), registry=reg,
    )
    w._docs = [DOC]
    await store.seed_if_new(DOC, [])
    return w, prov, store, reg, dispatched


def _assigned(cid="c1", content="改这句"):
    return C(cid, f"@{SA} {content}", mentioned=(SA,))  # C 默认 assignee=SA


async def test_no_watch_never_dispatches_three_ways(gated):
    w, prov, store, reg, dispatched = gated
    for i in (1, 2, 3):
        prov.comments = [_assigned(f"c{i}")]
        await w.tick()
    assert dispatched == [], "D2 零派发:未签发 watch 的指派永不派发"


async def test_no_watch_posts_unauthorized_reply_once(gated):
    w, prov, store, reg, dispatched = gated
    prov.comments = [_assigned("c1")]
    await w.tick()
    replies = [r for r in prov.replies if "尚未获得" in r[1] or "not been authorized" in r[1]]
    assert len(replies) == 1, "②机械回帖:每线程一次"
    await w.tick()
    replies2 = [r for r in prov.replies if "尚未获得" in r[1] or "not been authorized" in r[1]]
    assert len(replies2) == 1, "第二个 tick 不重复回帖(触发键已消耗)"


async def test_pre_grant_assignment_stays_backlogged_after_grant(gated):
    # The signed cutline: authority is strictly forward-looking. An assignment
    # observed before the grant must NOT dispatch after it.
    w, prov, store, reg, dispatched = gated
    prov.comments = [_assigned("c1")]
    await w.tick()                      # observed unauthorized -> consumed
    reg.issue(DOC, "apply_scoped")
    await w.tick()
    assert dispatched == [], "授权前的指派在授权后不得自动补派(③切割线)"


async def test_fresh_assignment_after_grant_dispatches_with_mode(gated):
    w, prov, store, reg, dispatched = gated
    reg.issue(DOC, "reply_only")
    prov.comments = [_assigned("c9")]
    await w.tick()
    assert len(dispatched) == 1
    assert dispatched[0][2]["clouddoc"]["mode"] == "reply_only", (
        "IC-1: watch 档位随授权载荷下发"
    )


async def test_mode_is_snapshotted_not_live(gated):
    # A modification drains: the turn dispatched under the old terms keeps them.
    w, prov, store, reg, dispatched = gated
    reg.issue(DOC, "apply_scoped")
    prov.comments = [_assigned("c1")]
    await w.tick()
    assert dispatched[0][2]["clouddoc"]["mode"] == "apply_scoped"
    reg.issue(DOC, "reply_only")        # modify after dispatch
    assert dispatched[0][2]["clouddoc"]["mode"] == "apply_scoped", (
        "已派发回合的档位是快照,变更不追溯(D3 drain)"
    )


async def test_suspended_watch_posts_neutral_reply_not_unauthorized(gated):
    w, prov, store, reg, dispatched = gated
    reg.issue(DOC, "apply_scoped")
    reg.suspend(DOC)
    prov.comments = [_assigned("c1")]
    await w.tick()
    assert dispatched == []
    text = "".join(r[1] for r in prov.replies)
    assert "本轮暂不安排" in text or "not scheduled this round" in text
    assert "尚未获得" not in text, "挂起态授权存在,不得谎称未授权(MINOR-15)"


async def test_global_suspend_freezes_every_dispatch(gated):
    w, prov, store, reg, dispatched = gated
    reg.issue(DOC, "apply_scoped")
    reg.suspend_all(by="biometric_lapse")
    for i in (1, 2, 3):
        prov.comments = [_assigned(f"c{i}")]
        await w.tick()
    assert dispatched == [], "全局挂起冻结一切派发(三连测)"


async def test_resume_does_not_auto_dispatch_suspended_backlog(gated):
    # The unified backlog law: leaving the backlog takes a human act.
    w, prov, store, reg, dispatched = gated
    reg.issue(DOC, "apply_scoped")
    reg.suspend(DOC)
    prov.comments = [_assigned("c1")]
    await w.tick()                      # backlogged under suspension
    reg.resume(DOC)
    await w.tick()
    assert dispatched == [], "恢复不自动补派挂起期积压"


async def test_over_budget_posts_queued_wording_and_counts_persist(gated):
    w, prov, store, reg, dispatched = gated
    reg.issue(DOC, "apply_scoped", budget={"max_dispatches_per_day": 1})
    prov.comments = [_assigned("c1")]
    await w.tick()
    assert len(dispatched) == 1
    prov.comments = [_assigned("c1"), _assigned("c2")]
    await w.tick()
    assert len(dispatched) == 1, "超预算不派发"
    text = "".join(r[1] for r in prov.replies)
    assert "额度已用完" in text or "budget is used up" in text, (
        "M-cluster-1:超预算对协作者可见(第三文案)"
    )


async def test_ungated_watcher_keeps_pr1_shape(tmp_path):
    # registry=None is the PR1 shape used across the legacy suite: everything
    # dispatches as apply_scoped. Production wiring always passes a registry.
    prov = FakeProvider()
    store = CloudDocStore(tmp_path / "s.json", now_fn=Clock())
    dispatched: list[tuple] = []

    async def dispatch(doc_id, comment_id, metadata):
        dispatched.append((doc_id, comment_id, metadata))
        return "ok"

    w = CloudDocCommentWatcher(
        prov, store, TriggerConfig(sa_address=SA), WatcherConfig(),
        dispatch=dispatch, now_fn=Clock(),
    )
    w._docs = [DOC]
    await store.seed_if_new(DOC, [])
    prov.comments = [_assigned("c1")]
    await w.tick()
    assert len(dispatched) == 1
    assert dispatched[0][2]["clouddoc"]["mode"] == "apply_scoped"


def test_production_wiring_passes_a_registry():
    """The gate exists only if app_gateway wires it: assert at source level, the same
    guard style as the dangling-reference test."""
    import inspect

    from jiuwenswarm.gateway import app_gateway

    src = inspect.getsource(app_gateway)
    assert "WatchRegistry(" in src, "app_gateway 必须构造 WatchRegistry"
    assert "registry=" in src, "app_gateway 必须把 registry 传给 watcher"


def test_reply_only_family_exposes_no_write_tool_three_ways():
    """IC-1 triple test: a reply_only turn must expose no write tool."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        unattended_allowlist_for,
    )

    write_tools = {"clouddoc_propose_edit", "clouddoc_batch_edit",
                   "clouddoc_create_document", "clouddoc_workmode_edit"}
    for _ in range(3):
        fam = unattended_allowlist_for("reply_only")
        assert not (fam & write_tools), "建议权回合不得出现任何写工具(IC-1)"
        assert fam == {"clouddoc_read", "clouddoc_list_comments", "clouddoc_reply_comment"}


def test_unknown_or_missing_mode_resolves_to_strictest():
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        unattended_allowlist_for,
    )

    strict = unattended_allowlist_for("reply_only")
    assert unattended_allowlist_for(None) == strict
    assert unattended_allowlist_for("") == strict
    assert unattended_allowlist_for("apply_for_everything") == strict


def test_adoption_policy_issues_watch_but_never_overwrites(tmp_path):
    from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

    class _FakeConns:
        pass

    reg = WatchRegistry(tmp_path / "w.json")
    # Simulate the policy hook contract directly (the connections method is thin):
    from jiuwenswarm.gateway.clouddoc.connections import CloudDocConnections

    conns = CloudDocConnections.__new__(CloudDocConnections)
    conns._watch_registry = reg
    conns.auto_watch_policy = "reply_only"
    conns.policy_issue(["d1", "d2"])
    assert reg.get("d1")["issued_by"] == "policy"
    assert reg.get("d2")["mode"] == "reply_only"
    # A manual grant outranks the policy: re-adoption must not reset terms.
    reg.issue("d1", "apply_scoped", issued_by="manual")
    conns.policy_issue(["d1"])
    assert reg.get("d1")["mode"] == "apply_scoped", "策略不得覆盖已有 watch"
    # A revoked entry is the owner's tombstone: the policy leaves it alone even
    # when the journal is not consulted at all.
    reg.revoke("d2")
    conns.policy_issue(["d2"])
    assert reg.get("d2").get("revoked") is True and reg.check("d2").reason == "no_watch"
    # off / invalid issue nothing.
    conns.auto_watch_policy = "off"
    conns.policy_issue(["d3"])
    conns.auto_watch_policy = "garbage"
    conns.policy_issue(["d4"])
    assert reg.get("d3") is None and reg.get("d4") is None


async def test_a_refused_dispatch_logs_the_gate_decision(gated, caplog):
    """The gate's verdict was invisible outside the audit journal; one INFO line per
    refusal names the document, the comment and the reason."""
    import logging

    w, prov, store, reg, dispatched = gated
    prov.comments = [_assigned("c1")]
    with caplog.at_level(logging.INFO, logger="jiuwenswarm.gateway.clouddoc.comment_watcher"):
        await w.tick()
    lines = [r.getMessage() for r in caplog.records if "gate " in r.getMessage()]
    assert any(f"gate {DOC}/c1 denied: no_watch" in ln for ln in lines), lines


async def test_a_rate_limited_pause_logs_without_consuming(tmp_path, caplog):
    """The brake's pause leaves no audit line by design; the log line is its only
    trace, and it carries the brake's own setting."""
    import logging

    prov = FakeProvider()
    store = CloudDocStore(tmp_path / "s.json", now_fn=Clock())
    reg = WatchRegistry(tmp_path / "w.json", rate_max=1, rate_window_seconds=60.0)
    dispatched: list[tuple] = []

    async def dispatch(doc_id, comment_id, metadata):
        dispatched.append((doc_id, comment_id, metadata))
        return "ok"

    w = CloudDocCommentWatcher(
        prov, store, TriggerConfig(sa_address=SA), WatcherConfig(),
        dispatch=dispatch, now_fn=Clock(), registry=reg,
    )
    w._docs = [DOC]
    await store.seed_if_new(DOC, [])
    reg.issue(DOC, "reply_only")
    prov.comments = [_assigned("c1"), _assigned("c2")]
    with caplog.at_level(logging.INFO, logger="jiuwenswarm.gateway.clouddoc.comment_watcher"):
        await w.tick()
    assert len(dispatched) == 1, "第一条派发后刹车生效"
    lines = [r.getMessage() for r in caplog.records if "paused: rate_limited" in r.getMessage()]
    assert any(f"gate {DOC}/c2 paused: rate_limited (1/60s)" in ln for ln in lines), lines
    assert not await store.is_triggered(DOC, f"clouddoc:{DOC}:c2:-"), "暂停不消耗触发键"
    assert not any("尚未获得" in r[1] for r in prov.replies), "暂停不回帖"


async def test_a_refused_dispatch_lands_a_denial_audit_line(gated):
    """E1's friction signal: the audit view can only surface repeated refusals
    if each one leaves a line -- silence here and the signal never exists."""
    w, prov, store, reg, dispatched = gated
    prov.comments = [_assigned("c1")]
    await w.tick()
    denies = [a for a in reg.audit_tail() if a["event"] == "deny"]
    assert len(denies) == 1 and denies[0]["reason"] == "no_watch"
    assert reg.usage_summary(DOC)["denials"] == {"no_watch": 1}


async def test_direct_mode_has_no_unattended_path_at_all(gated, monkeypatch):
    """D21: off mandate, the watcher dispatches nothing and consumes nothing --
    assignments stay in the document exactly as their authors left them, so a
    later switch back to mandate finds an untouched backlog (with the signed
    cutline still applying from the new grant's timestamp)."""
    w, prov, store, reg, dispatched = gated
    reg.issue(DOC, "apply_scoped")
    import jiuwenswarm.common.config as cfgmod
    real_get = cfgmod.get_config
    monkeypatch.setattr(
        cfgmod, "get_config",
        lambda: {**(real_get() or {}), "clouddoc": {**((real_get() or {}).get("clouddoc") or {}), "mode": "direct"}},
    )
    prov.comments = [_assigned("c1")]
    out = await w.tick()
    assert dispatched == [] and out["dispatched"] == 0
    assert prov.replies == [], "直连档不发机械回帖"
