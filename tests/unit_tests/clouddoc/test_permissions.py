"""The unattended scene decides from the caller's snapshot, never from contextvars.

Every test here binds no request contextvars, because that is the production
condition: the permission rail's scene hook runs while a tool is executing, one
task removed from the request that bound them. Deciding the turn from a
request-scoped flag there answered False, so ``clouddoc_apply_for_comment``
(permission tier ``ask``) raised an approval interrupt with nobody to answer it
and the turn came back empty.
"""

from __future__ import annotations

import pytest

from jiuwenswarm.clouddoc.host import permissions


@pytest.fixture(autouse=True)
def _no_fallback():
    permissions.set_fallback_snapshot(None)
    yield
    permissions.set_fallback_snapshot(None)


def _turn(mode="apply_scoped"):
    return lambda: {"doc_id": "d1", "mode": mode}


def test_a_closed_set_tool_is_approved_from_the_snapshot():
    assert permissions.unattended_scene("clouddoc_apply_for_comment", _turn()) == ("approve",)


def test_a_tool_outside_the_closed_set_is_refused_not_parked():
    """Refusal has to be a decision, not an interrupt: the model gets a tool result it
    can act on, instead of a turn that stalls.
    """
    outcome = permissions.unattended_scene("bash", _turn())

    assert outcome[0] == "reject"
    assert "bash" in outcome[1]


def test_ask_user_is_refused_on_an_unattended_turn():
    """The rail approves ask_user unconditionally further down; reaching that line on a
    turn with no reader is a wait for an answer that never comes.
    """
    assert permissions.unattended_scene("ask_user", _turn())[0] == "reject"


def test_the_watch_level_grants_exactly_its_own_tools():
    assert permissions.unattended_scene("clouddoc_reply_comment", _turn()) == ("approve",)
    assert permissions.unattended_scene("clouddoc_apply_for_comment", _turn()) == ("approve",)
    assert permissions.unattended_scene("bash", _turn())[0] == "reject"


def test_a_retired_or_unknown_mode_gets_no_tools():
    """The watcher refuses to dispatch such a turn at all, so this is the backstop
    behind the gate. It must not fall back to some narrower family: every tool below
    apply is one the agent can already use without a mandate.
    """
    for mode in ("reply_only", "", None, "bogus"):
        for tool in ("clouddoc_reply_comment", "clouddoc_read", "clouddoc_apply_for_comment"):
            assert permissions.unattended_scene(tool, _turn(mode))[0] == "reject", f"{mode!r}/{tool}"


def test_a_chat_turn_is_left_alone():
    """The snapshot is emptied on every non-clouddoc turn. Reading an empty one as
    unattended would refuse every tool in an ordinary chat session.
    """
    assert permissions.unattended_scene("bash", lambda: {}) is None
    assert permissions.unattended_scene("bash", lambda: None) is None


def test_a_failing_resolver_does_not_stall_the_turn():
    """A raising resolver reads as "not unattended" and the rail goes on to the tiered
    engine; it must never surface as a scene-hook failure.
    """

    def boom():
        raise RuntimeError("snapshot unavailable")

    assert permissions.unattended_scene("bash", boom) is None


def test_without_a_snapshot_the_installed_fallback_decides():
    """Team members and the code adapter supply no snapshot; the host installs one
    fallback for them. With none installed, nothing is recognised as unattended.
    """
    assert permissions.unattended_scene("bash", None) is None

    permissions.set_fallback_snapshot(_turn())
    assert permissions.unattended_scene("clouddoc_read", None) == ("approve",)
    assert permissions.unattended_scene("bash", None)[0] == "reject"

    permissions.set_fallback_snapshot(lambda: None)
    assert permissions.unattended_scene("bash", None) is None
