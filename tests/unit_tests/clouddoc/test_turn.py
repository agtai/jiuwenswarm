"""The turn readers: channel decides, unbound reads as None, payloads fail closed."""

from __future__ import annotations

import pytest

from jiuwenswarm.clouddoc.host import turn
from jiuwenswarm.clouddoc.providers.base import CLOUDDOC_CHANNEL_ID

DOC = "1AAAAAAAAAAAAAAAAAAAAA"


@pytest.fixture
def bind():
    """Install a request context on demand, simulating a real request's binding window."""
    state = {"ctx": (False, "web", None)}
    turn.set_request_context(lambda: state["ctx"])

    def _bind(*, channel_id="web", metadata=None, bound=True):
        state["ctx"] = (bound, channel_id, metadata)

    yield _bind
    turn.set_request_context(None)


def test_unbound_reads_as_none_not_as_the_channel_default(bind):
    """The channel contextvar defaults to "web", which would make "nothing bound" and
    "genuinely on the web channel" indistinguishable; the bound flag is consulted first.
    """
    bind(channel_id="web", metadata={"clouddoc": {"doc_id": DOC}}, bound=False)
    assert turn.request_channel_id() is None
    assert turn.request_metadata() is None
    assert turn.is_unattended_turn() is False


def test_a_bound_chat_turn_imposes_no_constraint(bind):
    bind(channel_id="web", metadata={})
    assert turn.request_channel_id() == "web"
    assert turn.is_unattended_turn() is False
    assert turn.turn_doc_id() is None
    assert turn.turn_comment_id() is None
    assert turn.turn_mode() is None
    assert turn.turn_progress() == {}


def test_an_unattended_turn_exposes_its_payload(bind):
    bind(
        channel_id=CLOUDDOC_CHANNEL_ID,
        metadata={
            "clouddoc": {"doc_id": DOC, "comment_id": "c1", "mode": "apply_scoped"},
            "clouddoc_progress": {"reply_id": "r1", "lang": "zh"},
        },
    )
    assert turn.is_unattended_turn() is True
    assert turn.turn_doc_id() == DOC
    assert turn.turn_comment_id() == "c1"
    assert turn.turn_mode() == "apply_scoped"
    assert turn.turn_progress() == {"reply_id": "r1", "lang": "zh"}


def test_a_missing_payload_fails_closed(bind):
    """This is the only cross-process authorization field, and its absence means no
    authorization: the empty string, which is not None -- None means "chat path, no
    constraint", the opposite meaning.
    """
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={})
    assert turn.turn_doc_id() == ""
    assert turn.turn_comment_id() == ""
    assert turn.turn_mode() is None
    assert turn.turn_progress() == {}


def test_the_discriminator_is_the_channel_not_the_metadata(bind):
    """Were it "does metadata exist", it would be circular with the fail-closed rule:
    with metadata missing you could not tell this was an unattended turn at all.
    """
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata=None)
    assert turn.is_unattended_turn() is True
    assert turn.turn_doc_id() == ""


def test_progress_is_decoration_and_never_widens_anything(bind):
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc_progress": {"reply_id": ""}})
    assert turn.turn_progress() == {}
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc_progress": "r1"})
    assert turn.turn_progress() == {}


def test_leaving_the_binding_window_yields_none_at_once(bind):
    """The metadata reader must not fall back to the previous turn's snapshot, which
    would have a tool authorizing an operation on document B while holding A's id.
    """
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc": {"doc_id": DOC}})
    assert turn.request_metadata() == {"clouddoc": {"doc_id": DOC}}
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc": {"doc_id": DOC}}, bound=False)
    assert turn.request_metadata() is None
    assert turn.turn_doc_id() is None


def test_the_default_source_is_the_adapters_request_binding():
    """Without an installed source the readers consult the agent adapter's contextvars,
    the ones every request binds for the length of its setup.
    """
    from jiuwenswarm.server.runtime.agent_adapter import interface_deep as idp

    turn.set_request_context(None)
    assert idp._CRON_TOOL_CHANNEL_ID.get() == "web"
    assert turn.request_channel_id() is None
    tokens = [
        idp._CRON_TOOL_BOUND.set(True),
        idp._CRON_TOOL_CHANNEL_ID.set(CLOUDDOC_CHANNEL_ID),
        idp._CRON_TOOL_METADATA.set({"clouddoc": {"doc_id": DOC}}),
    ]
    try:
        assert turn.is_unattended_turn() is True
        assert turn.turn_doc_id() == DOC
    finally:
        for t in reversed(tokens):
            t.var.reset(t)
    assert turn.is_unattended_turn() is False
