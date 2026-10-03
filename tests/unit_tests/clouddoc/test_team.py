"""Assembling the co-scribe toolkit onto a team member.

The gating is what these tests are about, and one gate is not like the others.
Disabled, or no connection configured, is ordinary: build nothing, say so, move
on. An unattended turn is different: this path cannot narrow the ability set, so a
turn that requires a narrowed one gets no tools at all, and the refusal has a test.
"""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.clouddoc.host.team import build_team_tools
from jiuwenswarm.clouddoc.providers.base import CLOUDDOC_CHANNEL_ID
from jiuwenswarm.clouddoc.tools.toolkit import ALL_TOOL_NAMES


@pytest.fixture
def key(tmp_path):
    """A credentials file shaped like a service-account key, never used to call out."""
    p = tmp_path / "sa.json"
    p.write_text(
        json.dumps({
            "type": "service_account",
            "client_email": "agent@example.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
            "private_key": "",
            "project_id": "p",
        }),
        encoding="utf-8",
    )
    return str(p)


def _cfg(key: str, **over):
    cfg = {
        "enabled": True,
        "connections": [{"credentials_file": key, "documents": ["doc-1"]}],
    }
    cfg.update(over)
    return cfg


def test_a_team_member_gets_the_co_scribe_tools(key):
    tools = build_team_tools(_cfg(key), channel_id="web")
    assert {t.card.name for t in tools} == set(ALL_TOOL_NAMES)


def test_an_unattended_turn_is_refused_rather_than_served(key):
    """This path cannot narrow the ability set, so a turn that requires a narrowed one
    gets no tools at all -- not the un-narrowed full set.
    """
    assert build_team_tools(_cfg(key), channel_id=CLOUDDOC_CHANNEL_ID) == []


def test_disabled_builds_nothing(key):
    assert build_team_tools(_cfg(key, enabled=False), channel_id="web") == []
    assert build_team_tools({}, channel_id="web") == []


def test_no_configured_connection_builds_nothing():
    """A deployment with the feature on but no key is a half-configured one, not an
    error: the panel is where a person adds the key.
    """
    assert build_team_tools({"enabled": True, "connections": []}, channel_id="web") == []


def test_an_unreadable_key_does_not_stop_the_member_being_built(tmp_path):
    """A corrupt key is a configuration problem for one capability; raising here would
    fail the member, and a person would see a team that cannot start.
    """
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    cfg = {"enabled": True, "connections": [{"credentials_file": str(bad), "documents": ["d"]}]}
    assert build_team_tools(cfg, channel_id="web") == []


def test_a_team_member_reaches_every_connection(key, tmp_path):
    """A team turn is a person talking, so it is routed across all connections like the
    chat path; a second connection's documents must not be invisible to it.
    """
    second = tmp_path / "sa2.json"
    second.write_text(json.dumps({
        "type": "service_account",
        "client_email": "agent2@example.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token", "private_key": "", "project_id": "p",
    }), encoding="utf-8")
    cfg = _cfg(key)
    cfg["connections"].append({"credentials_file": str(second), "documents": ["doc-2"]})
    assert build_team_tools(cfg, channel_id="web")


def test_the_configured_roster_reaches_the_providers(key, monkeypatch):
    """The chat host hands its providers the configured agent roster; the team host
    must hand over the same one, or a provider built here cannot tell another agent's
    mention from a person's.
    """
    from jiuwenswarm.clouddoc.providers import routing

    seen: dict = {}
    real = routing.build_routed_provider

    def capture(specs, **kw):
        seen.update(kw)
        return real(specs, **kw)

    monkeypatch.setattr(routing, "build_routed_provider", capture)
    assert build_team_tools(_cfg(key, agent_roster=["ou_x"]), channel_id="web")
    assert seen["agent_roster"] == ("ou_x",)
