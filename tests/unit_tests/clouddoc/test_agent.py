"""The adapter's co-scribe state: the snapshot outlives the binding window, the closed
set precedes every early return, and the toolkit reads the current session.

What happened in a live environment: reading the contextvar inside the binding window
is correct -- the closed-set strip from 49 tools to 4 proved it -- but by the time a
tool actually runs the context has changed, and reading it then yields nothing. The
symptom was the model receiving "missing doc_id" and abandoning the turn: the feature
failed silently while every offline test stayed green.
"""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.clouddoc.host import agent, permissions, turn
from jiuwenswarm.clouddoc.host.agent import CloudDocSessionTools
from jiuwenswarm.clouddoc.providers.base import CLOUDDOC_CHANNEL_ID
from jiuwenswarm.clouddoc.tools.cards import LocalFunction, ToolCard

DOC = "1AAAAAAAAAAAAAAAAAAAAA"


@pytest.fixture
def bind():
    state = {"ctx": (False, "web", None)}
    turn.set_request_context(lambda: state["ctx"])

    def _bind(*, channel_id="web", metadata=None, bound=True):
        state["ctx"] = (bound, channel_id, metadata)

    yield _bind
    turn.set_request_context(None)


@pytest.fixture
def config(monkeypatch):
    def _set(cfg):
        monkeypatch.setattr(agent, "deployment_config", lambda: cfg)

    return _set


class _Card:
    def __init__(self, name):
        self.name = name


class _StubAbilityManager:
    def __init__(self):
        self._items = []

    def list(self):
        return list(self._items)

    def add(self, card):
        self._items.append(card)

    def remove(self, name):
        self._items = [a for a in self._items if getattr(a, "name", "") != name]


class _StubInstance:
    def __init__(self, *names):
        self.ability_manager = _StubAbilityManager()
        for n in names:
            self.ability_manager.add(_Card(n))


class _Toolkit:
    def get_tools(self):
        return []


def _noop(tool):
    return None


def _Tool(name):
    return LocalFunction(card=ToolCard(id=name, name=name, description=name, input_params={}), func=lambda: None)


def test_the_authorization_survives_leaving_the_binding_window(bind, config):
    """Bind, refresh the snapshot, leave the binding window, read: an implementation
    that reads the contextvar gets an empty value at the last step.
    """
    config({"clouddoc": {"enabled": True}})
    tools = CloudDocSessionTools()
    tools.toolkit = _Toolkit()

    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc": {"doc_id": DOC, "comment_id": "c1"}})
    tools.update(_StubInstance(), register=_noop)
    assert tools.turn == {"doc_id": DOC, "comment_id": "c1", "mode": None}

    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata=None, bound=False)
    assert turn.turn_doc_id() is None
    assert tools.turn["doc_id"] == DOC


def test_the_permission_decision_survives_leaving_the_binding_window(bind, config):
    """The same window that hid the doc_id from the tools hid the turn from the
    permission rail; the rail takes the same snapshot the tools take.
    """
    config({"clouddoc": {"enabled": True}})
    tools = CloudDocSessionTools()
    tools.toolkit = _Toolkit()

    bind(
        channel_id=CLOUDDOC_CHANNEL_ID,
        metadata={"clouddoc": {"doc_id": DOC, "comment_id": "c1", "mode": "apply_scoped"}},
    )
    tools.update(_StubInstance(), register=_noop)
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata=None, bound=False)
    assert turn.is_unattended_turn() is False

    assert permissions.unattended_scene("clouddoc_apply_for_comment", tools.turn_snapshot) == ("approve",)
    assert permissions.unattended_scene("bash", tools.turn_snapshot)[0] == "reject"
    # And the shape of the bug: with no snapshot there is nothing to decide from.
    assert permissions.unattended_scene("clouddoc_apply_for_comment", None) is None


def test_a_chat_turn_leaves_the_snapshot_empty(bind, config):
    """An empty dict means unbound. Expressing unbound as {"doc_id": None} would make it
    indistinguishable from bound with an empty value.
    """
    config({"clouddoc": {"enabled": True}})
    tools = CloudDocSessionTools()
    tools.toolkit = _Toolkit()
    bind(channel_id="web", metadata={})
    tools.update(_StubInstance(), register=_noop)
    assert tools.turn == {}
    assert tools.turn_snapshot() is None


def test_the_closed_set_precedes_every_early_return(bind, config):
    """Feature disabled, credentials missing: each path used to return before stripping,
    so an unattended turn ran with the full default tool set, bash included.
    """
    for cfg in (
        {},
        {"clouddoc": {"enabled": False}},
        {"clouddoc": {"enabled": True, "credentials_file": ""}},
    ):
        config(cfg)
        tools = CloudDocSessionTools()
        instance = _StubInstance("bash", "read_file", "write_file", "code")
        bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc": {"doc_id": DOC, "comment_id": "c1"}})
        tools.update(instance, register=_noop)
        left = [a.name for a in instance.ability_manager.list()]
        assert left == [], f"config {cfg} left dangerous tools behind: {left}"


def test_a_stale_authorization_is_not_reused_when_construction_fails(bind, config):
    config({"clouddoc": {"enabled": False}})
    tools = CloudDocSessionTools()
    tools.turn = {"doc_id": "previous", "comment_id": "old"}
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc": {"doc_id": DOC, "comment_id": "c1"}})
    tools.update(_StubInstance(), register=_noop)
    assert tools.turn["doc_id"] == DOC


def test_the_strip_keeps_only_the_turns_family(bind, config):
    config({"clouddoc": {"enabled": False}})
    tools = CloudDocSessionTools()
    instance = _StubInstance("bash", "clouddoc_read", "clouddoc_edit", "clouddoc_reply_comment")
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc": {"doc_id": DOC, "mode": "apply_scoped"}})
    tools.update(instance, register=_noop)
    assert sorted(a.name for a in instance.ability_manager.list()) == [
        "clouddoc_read",
        "clouddoc_reply_comment",
    ]


def test_the_toolkit_reads_the_session_of_the_current_turn(bind, config):
    """The toolkit is built once and reused; the session it reads must not be. The
    current session is recorded on every call, and the reader resolves it at call
    time rather than at construction.
    """
    config({"clouddoc": {"enabled": False}})
    tools = CloudDocSessionTools()
    tools.toolkit = _Toolkit()
    bind(channel_id="web", metadata={})
    tools.update(_StubInstance(), "session-A", register=_noop)
    tools.update(_StubInstance(), "session-B", register=_noop)
    assert tools.session_id == "session-B"

    import inspect

    src = inspect.getsource(CloudDocSessionTools._build_toolkit)
    assert "user_text=lambda: user_text(self.session_id)" in src


def test_registration_skips_tools_the_instance_already_has(bind, config):
    config({"clouddoc": {"enabled": True}})

    class _Kit:
        def get_tools(self):
            return [_Tool("clouddoc_read"), _Tool("clouddoc_edit")]

    tools = CloudDocSessionTools()
    tools.toolkit = _Kit()
    instance = _StubInstance("clouddoc_read")
    seen = []
    bind(channel_id="web", metadata={})
    tools.update(instance, register=seen.append)
    assert [t.card.name for t in seen] == ["clouddoc_edit"]
    assert sorted(a.name for a in instance.ability_manager.list()) == ["clouddoc_edit", "clouddoc_read"]


def test_an_unattended_turn_registers_only_the_closed_set(bind, config):
    config({"clouddoc": {"enabled": True}})

    class _Kit:
        def get_tools(self):
            return [_Tool("clouddoc_read"), _Tool("clouddoc_edit"), _Tool("clouddoc_reply_comment")]

    tools = CloudDocSessionTools()
    tools.toolkit = _Kit()
    instance = _StubInstance("bash")
    bind(channel_id=CLOUDDOC_CHANNEL_ID, metadata={"clouddoc": {"doc_id": DOC, "mode": "apply_scoped"}})
    tools.update(instance, register=_noop)
    assert sorted(a.name for a in instance.ability_manager.list()) == [
        "clouddoc_read",
        "clouddoc_reply_comment",
    ]


def test_the_allowlist_covers_exactly_the_apply_scoped_family():
    from jiuwenswarm.clouddoc.tools.toolkit import UNATTENDED_ALLOWLIST

    assert UNATTENDED_ALLOWLIST == {
        "clouddoc_read",
        "clouddoc_list_comments",
        "clouddoc_apply_for_comment",
        "clouddoc_reply_comment",
    }
    assert "clouddoc_edit" not in UNATTENDED_ALLOWLIST
    assert "clouddoc_resolve_comment" not in UNATTENDED_ALLOWLIST


# ------------------------------------------------------------------ identity helpers

SPECS = [
    {"credentials_file": "/k/first.json", "documents": ["1AAAABBBBCCCC"]},
    {"credentials_file": "/k/second.json", "documents": [
        "1AAAABBBBCCCCD", "https://acme.feishu.cn/docx/FsTok1?from=x",
    ]},
]


@pytest.mark.parametrize("turn_doc,expected", [
    ("1AAAABBBBCCCC", "/k/first.json"),
    ("1AAAABBBBCCCCD", "/k/second.json"),      # one character longer: the other connection
    ("1AAAABBBBCCC", "/k/first.json"),         # a prefix of a listed id: nobody's; the default
    ("FsTok1", "/k/second.json"),              # listed as a link, compared as its token
    ("https://acme.feishu.cn/docx/FsTok1?from=x", "/k/second.json"),
    ("https://acme.feishu.cn/docx/FsTok1", "/k/second.json"),
    ("https://docs.google.com/document/d/1AAAABBBBCCCC/edit", "/k/first.json"),
    ("FsTok10", "/k/first.json"),
    (None, "/k/first.json"),
    ("", "/k/first.json"),
])
def test_credentials_follow_the_exact_document_id(turn_doc, expected):
    assert agent.credentials_for_turn(SPECS, turn_doc) == expected


def test_self_address_reads_either_vendors_key(tmp_path):
    g = tmp_path / "g.json"
    g.write_text(json.dumps({"type": "service_account", "client_email": "sa@x.iam"}))
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"app_id": "cli_x", "app_secret": "s", "bot_open_id": "ou_bot"}))
    assert agent.self_address(str(g)) == "sa@x.iam"
    assert agent.self_address(str(f)) == "ou_bot"
    assert agent.self_address(str(tmp_path / "nope.json")) == ""


def test_user_text_reads_the_persons_words_and_the_ask_user_answer(tmp_path, monkeypatch):
    from jiuwenswarm.common import utils

    monkeypatch.setattr(utils, "get_agent_sessions_dir", lambda: tmp_path)
    session = tmp_path / "s1"
    session.mkdir()
    lines = [
        {"role": "user", "content": "open the Q3 plan"},
        {"role": "assistant", "content": "which one?"},
        {"role": "assistant", "tool_name": "ask_user", "result": "the launch note"},
        {"role": "user", "content": [{"type": "text", "text": "and the deck"}, {"type": "image"}]},
    ]
    (session / "history.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n{torn")
    assert agent.user_text("s1") == "open the Q3 plan\nthe launch note\nand the deck"
    assert agent.user_text("missing") == ""
    assert agent.user_text(None) == ""


def test_workmode_language_follows_the_conventions_marker():
    assert agent.workmode_prefer_zh({}) is True
    assert agent.workmode_prefer_zh({"conventions_marker": "写作约定"}) is True
    assert agent.workmode_prefer_zh({"conventions_marker": "Writing rules"}) is False
