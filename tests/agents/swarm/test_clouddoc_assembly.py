"""The co-scribe toolkit on the declarative team path: declared in the catalog, built
through the harness element, and gated the way ``jiuwenswarm.clouddoc.host.team``
gates it (the gating itself is tested there)."""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.agents.swarm import registry
from jiuwenswarm.agents.swarm.context import SwarmBuildContext
from jiuwenswarm.agents.swarm.providers.runtime_tools import build_clouddoc_tools
from jiuwenswarm.clouddoc.providers.base import CLOUDDOC_CHANNEL_ID
from jiuwenswarm.clouddoc.tools.toolkit import ALL_TOOL_NAMES


@pytest.fixture
def key(tmp_path):
    p = tmp_path / "sa.json"
    p.write_text(json.dumps({
        "type": "service_account",
        "client_email": "agent@example.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
        "private_key": "",
        "project_id": "p",
    }), encoding="utf-8")
    return str(p)


def _cfg(key: str, **over):
    cfg = {"enabled": True, "connections": [{"credentials_file": key, "documents": ["doc-1"]}]}
    cfg.update(over)
    return cfg


def test_a_team_member_gets_the_co_scribe_tools(key):
    tools = build_clouddoc_tools(
        {"clouddoc_config": _cfg(key)},
        SwarmBuildContext(session_id="s1", channel_id="web"),
    )
    assert {t.card.name for t in tools} == set(ALL_TOOL_NAMES)


def test_an_unattended_turn_is_refused_rather_than_served(key):
    """The channel comes off the build context, not a contextvar, and the element
    hands it through: the refusal in the host module has to see it."""
    tools = build_clouddoc_tools(
        {"clouddoc_config": _cfg(key)},
        SwarmBuildContext(session_id="s1", channel_id=CLOUDDOC_CHANNEL_ID),
    )
    assert tools == []


def test_disabled_builds_nothing(key):
    tools = build_clouddoc_tools(
        {"clouddoc_config": _cfg(key, enabled=False)},
        SwarmBuildContext(session_id="s1", channel_id="web"),
    )
    assert tools == []


def test_the_element_is_declared_in_the_catalog():
    """Declared, or ``build_member_capability_specs`` cannot resolve it by name and the
    member is built without ever saying why."""
    from openjiuwen.agent_teams.harness.manifest import get_catalog

    from jiuwenswarm.agents.swarm.registry import register_swarm_providers

    register_swarm_providers()
    entry = get_catalog()[registry.CLOUDDOC_TOOLS]
    props = entry.input_schema["properties"]
    assert props["clouddoc_config"]["source"] == "params"
    assert props["channel_id"]["source"] == "context"
