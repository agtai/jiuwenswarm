"""The adoption policy: a watch is issued on adoption, never overwritten, and a
retired policy value lands on off -- never on apply.
"""

from __future__ import annotations

from jiuwenswarm.clouddoc.authority.watch_registry import WatchRegistry


def test_adoption_policy_issues_watch_but_never_overwrites(tmp_path):

    class _FakeConns:
        pass

    reg = WatchRegistry(tmp_path / "w.json")
    # Simulate the policy hook contract directly (the connections method is thin):
    from jiuwenswarm.clouddoc.panel.connections import CloudDocConnections

    conns = CloudDocConnections.__new__(CloudDocConnections)
    conns._watch_registry = reg
    conns.auto_watch_policy = "apply_scoped"
    conns.policy_issue(["d1", "d2"])
    assert reg.get("d1")["issued_by"] == "policy"
    assert reg.get("d2")["mode"] == "apply_scoped"
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


def test_a_retired_policy_value_lands_on_off_never_on_apply(tmp_path, caplog):
    """A config file outlives the release that documented it.

    ``auto_watch_on_adopt: reply_only`` is still out there. It must issue
    **nothing** -- reading an unrecognised level as the one surviving level would
    auto-grant write authority across every adopted document on next startup.
    """
    import logging

    from jiuwenswarm.clouddoc.panel.connections import CloudDocConnections

    reg = WatchRegistry(tmp_path / "w.json")
    conns = CloudDocConnections.__new__(CloudDocConnections)
    conns._watch_registry = reg
    conns.auto_watch_policy = "reply_only"
    with caplog.at_level(logging.WARNING, logger="jiuwenswarm.clouddoc.panel.connections"):
        conns.policy_issue(["d1", "d2"])
    assert reg.get("d1") is None and reg.get("d2") is None, "退役档位的策略值一律按 off"
    assert any("已退役" in r.getMessage() for r in caplog.records), "按 off 处理要告警"
