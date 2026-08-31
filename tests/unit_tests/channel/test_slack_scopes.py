# Copyright (c) Huawei Technologies Co., Ltd. 2025-2026. All rights reserved.

"""Slack's scopes declaration, and what a written scope settles to.

Two halves. The declaration says which axes Slack populates and which settings
it reads in which section, and the shared loader refuses anything else against
it. The fold turns the compiled scopes into the two things the connector reads
per conversation: a platform-wide layer and a per-conversation map.

The property the whole shape turns on is pinned first: **with nothing written,
nothing is settled.** An operator with no scopes: block gets a connector that
follows channels.slack alone.

Warnings are captured by replacing the module logger's ``warning`` rather than
through ``caplog``: this project's loggers do not propagate, so ``caplog`` sees
nothing under the pytest CI runs on, and a test written against it would pass
locally and assert nothing where it matters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from jiuwenswarm.common.scopes import (
    channel_capabilities,
    compile_scopes,
    compose_section,
)
from jiuwenswarm.gateway.channel_manager.im_platforms.slack import slack_connect
from jiuwenswarm.gateway.channel_manager.im_platforms.slack.slack_connect import (
    SlackChannel,
    SlackChannelConfig,
    SlackChannelOverride,
    apply_scopes_to_slack_overrides,
    channel_triggers,
    describe_configured_channels,
    sections_as_override,
    settled_override,
)

_RESOURCES = Path(__file__).resolve().parents[3] / "jiuwenswarm" / "resources"


@pytest.fixture
def warnings(monkeypatch) -> list[str]:
    recorded: list[str] = []

    def record(message: str, *args: Any, **kwargs: Any) -> None:
        recorded.append(message % args if args else message)

    monkeypatch.setattr(slack_connect.logger, "warning", record)
    return recorded


@pytest.fixture
def any_model(monkeypatch):
    """Accept every model name, so a test can isolate something else."""
    monkeypatch.setattr(slack_connect, "configured_models", lambda: slack_connect.ConfiguredModels())
    return None


def _scopes(entries: Any, warn=None):
    return compile_scopes(entries, warn=warn or (lambda *a: None))


# --------------------------------------------------------------------------
# The declaration
# --------------------------------------------------------------------------


def test_slack_is_discovered_without_importing_the_connector():
    # The declaration module is found by filename and must not drag slack_sdk
    # into a process that has no Slack in it, so it may not import
    # slack_connect at module level.
    source = (
        Path(slack_connect.__file__).parent / "scope_capabilities.py"
    ).read_text(encoding="utf-8")
    module_level = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "slack_connect" in line
    ]
    assert module_level == []
    assert channel_capabilities("slack") is not None


def test_slack_declares_the_conversation_axis():
    assert channel_capabilities("slack").populates("chat")


def test_slack_declares_a_sender_even_though_this_version_will_not_read_one():
    # The declaration states the truth about the connector. Which axes are
    # readable is a property of the matcher and is stated once, elsewhere.
    assert channel_capabilities("slack").populates("user")


def test_slack_declares_exactly_the_settings_the_carrier_holds():
    # Five settings, split across the two sections by who acts on them: the
    # connector consumes mode, prompt and mid_turn, and only carries model_name
    # and history onto the request for the runtime.
    declared = channel_capabilities("slack")
    assert declared.keys_for("delivery") == frozenset({"mode", "prompt", "mid_turn"})
    assert declared.keys_for("agent") == frozenset({"model_name", "history"})


def test_slack_opts_into_permissions_without_naming_its_keys():
    # The third section is neither consumed nor carried here -- it is resolved
    # in the runtime from the ids the request arrived with. Slack declares it
    # because the declaration is the opt-in, and leaves its keys to the shared
    # loader rather than keeping a second copy of the vocabulary.
    declared = channel_capabilities("slack")
    assert declared.reads("permissions")
    assert declared.keys_for("permissions") is None


def test_slack_is_attended_so_a_scope_may_ask():
    # D11 degrades an ask to a deny where nobody can click. Slack renders
    # interactive approvals on this branch, so it does not get the degrade --
    # and this is the assertion that says the interactive path is a capability
    # of the deployment rather than a comment.
    from jiuwenswarm.common.scopes import settled_tool_levels

    assert channel_capabilities("slack").attended is True
    scopes = _scopes(
        [
            {
                "match": {"channel": "slack", "chat": "C0"},
                "permissions": {"tools": {"bash": "ask"}},
            }
        ],
        warn=lambda *a: None,
    )
    assert settled_tool_levels(scopes, channel="slack", chat="C0") == {"bash": "ask"}


def test_a_permissions_only_scope_does_not_open_a_slack_conversation():
    # The ids scoped_chats returns are what exempt a channel from
    # allowed_channel_ids. A rule written to take bash away must not hand out an
    # answer in a channel the operator never listed.
    from jiuwenswarm.common.scopes import scoped_chats

    scopes = _scopes(
        [
            {
                "match": {"channel": "slack", "chat": "C-LOCKED"},
                "permissions": {"tools": {"bash": "deny"}},
            }
        ],
        warn=lambda *a: None,
    )
    assert scoped_chats(scopes, channel="slack") == ()


def test_a_model_name_written_under_delivery_is_reported_as_the_wrong_section():
    # Where a config written against the earlier shape lands. delivery is still
    # a section slack reads, so the line is about the key rather than about the
    # section, and the rest of the rule stands.
    said: list[str] = []
    scopes = _scopes(
        [
            {
                "match": {"channel": "slack"},
                "delivery": {"mode": ["all"], "model_name": "anything"},
            }
        ],
        warn=lambda m, *a: said.append(m % a),
    )
    assert any("delivery.model_name has no effect" in line for line in said), said
    assert compose_section(scopes, channel="slack") == {"mode": frozenset({"all"})}
    assert compose_section(scopes, channel="slack", section="agent") == {}


def test_the_wrong_section_warning_names_the_delivery_settings_that_are_left():
    said: list[str] = []
    _scopes(
        [{"match": {"channel": "slack"}, "delivery": {"model_name": "anything"}}],
        warn=lambda m, *a: said.append(m % a),
    )
    assert any("it reads are mid_turn, mode, prompt" in line for line in said), said


def test_slack_declares_no_layer_zero_key_for_the_model():
    # There is no channels.slack key that pins a model for every conversation,
    # so there is nothing for a scope to be a second home for. Declaring one
    # would fire the "two homes for one value" warning against a setting that
    # does not exist.
    assert channel_capabilities("slack").layer0_key("agent", "model_name") is None


def test_a_setting_slack_does_not_read_is_reported(warnings):
    said: list[str] = []
    _scopes(
        [{"match": {"channel": "slack"}, "delivery": {"reasoning_level": "high"}}],
        warn=lambda m, *a: said.append(m % a),
    )
    assert any("delivery.reasoning_level has no effect" in line for line in said), said


def test_a_work_mode_is_refused_because_a_session_locks_it_on_its_first_turn():
    """The other key that looks like ``model_name`` and is not one.

    It would pass the section rule: a connector would only carry it onto
    ``params["work_mode"]`` and the runtime is what acts on it. What it fails is
    the question after that. The runtime writes a session's ``work_mode`` the
    first time it sees the session and never overwrites it, so a scope setting
    it would apply to conversations that have not spoken yet and be ignored,
    silently and permanently, for every one that has. Nothing connector-side can
    warn about that: the lock lives in the other process's session metadata.

    Asserted rather than left to the allow-list so that adding the key to the
    declaration fails a test that names the reason, instead of shipping a
    setting an operator cannot tell is working.
    """
    said: list[str] = []
    scopes = _scopes(
        [{"match": {"channel": "slack"}, "agent": {"work_mode": "code"}}],
        warn=lambda m, *a: said.append(m % a),
    )
    assert scopes == ()
    assert any("agent.work_mode has no effect" in line for line in said), said
    # Sorted, and history is beside it now: the point of the assertion is that
    # work_mode is not in the list, not how long the list is.
    assert any("settings it reads are history, model_name" in line for line in said), said


def test_a_bad_trigger_name_is_refused_through_the_declaration():
    said: list[str] = []
    scopes = _scopes(
        [{"match": {"channel": "slack"}, "delivery": {"mode": ["menshun"]}}],
        warn=lambda m, *a: said.append(m % a),
    )
    assert scopes == ()
    assert any("is not a trigger" in line for line in said), said


def test_the_bad_trigger_warning_names_the_triggers():
    said: list[str] = []
    _scopes(
        [{"match": {"channel": "slack"}, "delivery": {"mode": ["menshun"]}}],
        warn=lambda m, *a: said.append(m % a),
    )
    assert any("mention/reply/all/url/has_file" in line for line in said), said


def test_a_sign_is_stripped_before_a_trigger_name_is_checked():
    said: list[str] = []
    scopes = _scopes(
        [{"match": {"channel": "slack"}, "delivery": {"mode": ["+has_file"]}}],
        warn=lambda m, *a: said.append(m % a),
    )
    assert len(scopes) == 1
    assert said == []


def test_only_one_sign_is_stripped_because_only_one_is_applied(any_model):
    """The check has to read an entry the way the fold reads it.

    ``_apply_signed`` takes ``entry[0]`` as the sign and ``entry[1:]`` as the
    name, so ``++url`` asks it to add a trigger called ``+url``. A check that
    stripped every leading sign would call that entry well-formed and leave the
    conversation on a set containing a name nothing matches, with nothing said
    anywhere.
    """
    said: list[str] = []
    scopes = _scopes(
        [{"match": {"channel": "slack"}, "delivery": {"mode": ["++url"]}}],
        warn=lambda m, *a: said.append(m % a),
    )

    assert scopes == ()
    assert any("'++url'" in line and "is not a trigger" in line for line in said), said

    # And the set the fold would have produced is the one the refusal avoided.
    platform, _ = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [{"match": {"channel": "slack"}, "delivery": {"mode": ["+url"]}}]
        ),
    )
    assert platform.mode == frozenset({"mention", "url"})


def test_the_legacy_bare_string_spelling_is_refused_with_the_list_to_write():
    said: list[str] = []
    _scopes(
        [{"match": {"channel": "slack"}, "delivery": {"mode": "mention"}}],
        warn=lambda m, *a: said.append(m % a),
    )
    assert any("write [mention]" in line for line in said), said


def test_a_model_name_is_checked_against_the_configured_models(monkeypatch):
    monkeypatch.setattr(
        slack_connect,
        "configured_models",
        lambda: slack_connect.ConfiguredModels(names=("good",)),
    )
    said: list[str] = []
    scopes = _scopes(
        [{"match": {"channel": "slack"}, "agent": {"model_name": "typo"}}],
        warn=lambda m, *a: said.append(m % a),
    )
    assert scopes == ()
    assert any("is not one of the models configured" in line for line in said), said


def test_an_unreadable_model_list_does_not_drop_a_correct_setting(monkeypatch):
    # A config read that failed must not cost the operator a setting, which is
    # the one failure they cannot act on.
    monkeypatch.setattr(
        slack_connect, "configured_models", lambda: slack_connect.ConfiguredModels()
    )
    scopes = _scopes(
        [{"match": {"channel": "slack"}, "agent": {"model_name": "anything"}}]
    )
    assert compose_section(scopes, channel="slack", section="agent") == {
        "model_name": "anything"
    }


def test_group_chat_mode_is_declared_as_the_connector_setting_mode_sits_above():
    said: list[str] = []
    compile_scopes(
        [{"match": {"channel": "slack"}, "delivery": {"mode": ["all"]}}],
        channels_config={"slack": {"group_chat_mode": "mention"}},
        warn=lambda m, *a: said.append(m % a),
    )
    assert any(
        "channels.slack.group_chat_mode both set this" in line for line in said
    ), said


# --------------------------------------------------------------------------
# Nothing written changes nothing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scopes", [None, (), []])
def test_with_no_scopes_nothing_is_settled(scopes):
    platform, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"}, scopes=scopes
    )

    assert resolved == {}
    assert platform == SlackChannelOverride()


# --------------------------------------------------------------------------
# Reading composed sections back as the carrier
# --------------------------------------------------------------------------


def test_settled_sections_read_back_as_one_override():
    assert sections_as_override(
        {
            "delivery": {"mode": ["mention"], "prompt": "hi"},
            "agent": {"model_name": " m "},
        }
    ) == SlackChannelOverride(mode=frozenset({"mention"}), prompt="hi", model_name="m")


def test_a_model_name_settled_under_delivery_is_not_read_back():
    # The carrier spans two sections; it does not merge them. A value in the
    # section that no longer declares it has already been warned about and
    # dropped at load, and honouring it here would put it back.
    assert sections_as_override({"delivery": {"model_name": "m"}}).model_name is None


def test_a_bare_string_mode_never_becomes_a_set_of_letters():
    # frozenset("all") is {"a", "l"}, which would be an unreadable corruption
    # of a channel's triggers rather than an error anybody could see.
    assert sections_as_override({"delivery": {"mode": "all"}}).mode == frozenset(
        {"mention", "all"}
    )


# --------------------------------------------------------------------------
# Layering against a real Slack config
# --------------------------------------------------------------------------


def test_a_signed_mode_inherits_group_chat_mode(any_model):
    _, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "reply"},
        scopes=_scopes(
            [
                {
                    "match": {"channel": "slack", "chat": "C-NEW"},
                    "delivery": {"mode": ["+has_file"]},
                }
            ]
        ),
    )
    assert resolved["C-NEW"].mode == frozenset({"mention", "reply", "has_file"})


def test_a_removal_narrows_what_the_platform_default_answered(any_model):
    _, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "all"},
        scopes=_scopes(
            [
                {
                    "match": {"channel": "slack", "chat": "C-QUIET"},
                    "delivery": {"mode": ["-all"]},
                }
            ]
        ),
    )
    assert resolved["C-QUIET"].mode == frozenset({"mention"})


def test_a_platform_scope_is_the_layer_between_the_global_and_a_conversation(any_model):
    platform, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {"match": {"channel": "slack"}, "delivery": {"mode": ["all"], "prompt": "p"}},
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "delivery": {"mode": ["mention"]},
                },
            ]
        ),
    )
    assert platform == SlackChannelOverride(mode=frozenset({"all"}), prompt="p")
    assert resolved["C-A"] == SlackChannelOverride(mode=frozenset({"mention"}), prompt="p")


def test_the_platform_layer_beats_group_chat_mode_for_a_channel_nobody_named(any_model):
    platform, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes([{"match": {"channel": "slack"}, "delivery": {"mode": ["all"]}}]),
    )
    config = SlackChannelConfig(
        conversation_overrides=resolved, platform_override=platform, group_chat_mode="mention"
    )
    assert channel_triggers(config, "C-UNNAMED", group_chat_mode="mention") == frozenset(
        {"all"}
    )


def test_a_named_conversation_still_beats_the_platform_layer(any_model):
    platform, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {"match": {"channel": "slack"}, "delivery": {"mode": ["all"]}},
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "delivery": {"mode": ["mention"]},
                },
            ]
        ),
    )
    config = SlackChannelConfig(
        conversation_overrides=resolved, platform_override=platform, group_chat_mode="mention"
    )
    assert channel_triggers(config, "C-A", group_chat_mode="mention") == frozenset(
        {"mention"}
    )


def test_a_prompt_append_adds_to_a_scope_prompt(any_model):
    _, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {"match": {"channel": "slack"}, "delivery": {"prompt": "Answer in English."}},
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "delivery": {"prompt_append": "Be terse."},
                },
            ]
        ),
    )
    assert resolved["C-A"].prompt == "Answer in English.\n\nBe terse."


def test_a_platform_scope_pins_a_model_for_every_conversation(any_model):
    platform, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {"match": {"channel": "slack"}, "agent": {"model_name": "platform-model"}},
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "agent": {"model_name": "channel-model"},
                },
            ]
        ),
    )
    # Layer 1 for anything nobody named, layer 2 where somebody did. The same
    # cascade delivery gets, which is the point of composing per section rather
    # than per mechanism.
    assert platform.model_name == "platform-model"
    assert resolved["C-A"].model_name == "channel-model"


def test_a_scope_sets_the_model_without_disturbing_the_triggers(any_model):
    # Per key across sections as well as within one. A scope that speaks only
    # about agent must leave delivery exactly as the layer below left it.
    _, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "delivery": {"mode": ["url"], "prompt": "from delivery"},
                },
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "agent": {"model_name": "m"},
                },
            ]
        ),
    )
    assert resolved["C-A"] == SlackChannelOverride(
        mode=frozenset({"url"}), prompt="from delivery", model_name="m"
    )


def test_a_conversation_named_only_by_an_agent_scope_is_settled(any_model):
    # It reaches the map at all only because scoped_chats spans both sections.
    # Per-section, this conversation would not have been iterated and the model
    # would have been dropped with nothing said about it.
    _, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {
                    "match": {"channel": "slack", "chat": "C-NEW"},
                    "agent": {"model_name": "m"},
                }
            ]
        ),
    )
    assert resolved["C-NEW"].model_name == "m"
    # And nothing else: delivery said nothing, so the connector's own chain
    # still decides what that conversation answers.
    assert resolved["C-NEW"].mode is None


def test_a_model_name_under_delivery_is_dropped_rather_than_applied(any_model):
    _, resolved = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "delivery": {"mode": ["all"], "model_name": "wrong-section"},
                }
            ]
        ),
    )
    assert resolved["C-A"].mode == frozenset({"all"})
    assert resolved["C-A"].model_name is None


# --------------------------------------------------------------------------
# What the composition warns about
# --------------------------------------------------------------------------


def test_a_composed_mode_that_drops_mention_is_reported(warnings, any_model):
    apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "delivery": {"mode": ["-mention", "+url"]},
                }
            ]
        ),
    )
    assert any(
        "do not list mention" in line and "C-A" in line for line in warnings
    ), warnings


def test_a_composition_that_silences_a_conversation_is_reported(warnings, any_model):
    apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [
                {
                    "match": {"channel": "slack", "chat": "C-A"},
                    "delivery": {"mode": []},
                }
            ]
        ),
    )
    assert any("is now silent" in line for line in warnings), warnings


def test_a_platform_scope_that_drops_mention_is_reported(warnings, any_model):
    apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"},
        scopes=_scopes(
            [{"match": {"channel": "slack"}, "delivery": {"mode": ["url"]}}]
        ),
    )
    assert any(
        "the scope for channel slack" in line and "do not list mention" in line
        for line in warnings
    ), warnings


# --------------------------------------------------------------------------
# The startup summary
# --------------------------------------------------------------------------


def test_the_summary_names_scopes_as_the_source_of_a_scoped_conversation():
    config = SlackChannelConfig(
        conversation_overrides={"C-A": SlackChannelOverride(prompt="p")},
        group_chat_mode="mention",
    )
    assert "via=scopes" in describe_configured_channels(config)
    assert "prompt=scopes" in describe_configured_channels(config)


def test_the_summary_says_what_an_unnamed_channel_follows_once_a_scope_replaces_it():
    # Naming group_chat_mode here would print the one value no longer in force,
    # and this line exists to be checked against what the operator meant.
    config = SlackChannelConfig(
        platform_override=SlackChannelOverride(mode=frozenset({"all"})),
        group_chat_mode="mention",
    )
    assert "follows the scope for channel slack: mode=[all]" in (
        describe_configured_channels(config)
    )


def test_the_summary_is_unchanged_when_no_scope_replaced_the_global():
    config = SlackChannelConfig(group_chat_mode="mention")
    assert "follows group_chat_mode=mention" in describe_configured_channels(config)


def test_the_summary_reports_what_a_platform_scope_settled_for_a_named_channel():
    """The line reports what is in force in a conversation.

    A platform scope reaches every conversation that did not override it,
    including the ones some other scope named for something else. This line
    exists to be checked against what an operator meant, so a channel that has
    both must not be printed as "prompt=none model=default".
    """
    config = SlackChannelConfig(
        platform_override=SlackChannelOverride(
            prompt="House rules apply.", model_name="deepseek-v3"
        ),
        conversation_overrides={"C-A": SlackChannelOverride(mode=frozenset({"all"}))},
        group_chat_mode="mention",
    )

    summary = describe_configured_channels(config)

    assert "prompt=scopes" in summary
    assert "model=deepseek-v3" in summary


# --------------------------------------------------------------------------
# The worked example an operator copies out of the template
# --------------------------------------------------------------------------


def test_the_worked_example_in_the_template_compiles_clean(monkeypatch):
    """The example an operator copies must not warn when they copy it.

    Lifted out of the comment block rather than restated, so a change to the
    documented shape that the loader would reject fails here instead of in
    somebody's config file.
    """
    monkeypatch.setattr(
        slack_connect,
        "configured_models",
        lambda: slack_connect.ConfiguredModels(names=("deepseek-v3",)),
    )
    text = (_RESOURCES / "config.yaml").read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "#   scopes:")
    example: list[str] = []
    for line in lines[start:]:
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            break
        body = stripped[1:]
        if body.strip() == "":
            break
        example.append(body[2:] if body.startswith("  ") else body.lstrip())

    parsed = yaml.safe_load("\n".join(example))
    said: list[str] = []
    scopes = compile_scopes(parsed["scopes"], warn=lambda m, *a: said.append(m % a))

    assert said == [], said
    assert len(scopes) == 6
    composed = compose_section(scopes, channel="slack", chat="C000000AAAA")
    assert composed["mode"] == frozenset({"mention", "url", "has_file"})
    # The example splits the sections, and the assertion follows it. If the
    # comment block ever puts model_name back under delivery the loader would
    # warn, said would not be empty, and this test fails before an operator
    # copies the wrong shape out of their own config file.
    #
    # history comes from the platform rule and model_name from the conversation
    # one, so this line is also where the example demonstrates that agent is
    # settled a key at a time: a rule that names only the model keeps the
    # history word the rule above it set. The example writes history on
    # {channel: slack} alone because that is the only match it may take -- had
    # it been written on the conversation rule instead, the loader would have
    # reported it and said would not be empty.
    assert compose_section(
        scopes, channel="slack", chat="C000000AAAA", section="agent"
    ) == {"model_name": "deepseek-v3", "history": "origin"}
    assert compose_section(scopes, channel="slack", chat="C000000BBBB")["prompt"] == (
        "This is a support channel. Be terse."
    )
    # The fourth entry is the one that is not Slack's: a restriction on the
    # scheduled runs, which are unattended, which is why it is written as deny
    # rather than as the ask the Slack conversation above gets.
    from jiuwenswarm.common.scopes import settled_tool_levels

    assert settled_tool_levels(scopes, channel="slack", chat="C000000BBBB") == {
        "bash": "ask"
    }
    assert settled_tool_levels(scopes, channel="__cron__") == {"bash": "deny"}

    # The clicks clause on that same conversation. An operator copying the
    # example gets a rule, not a comment: the named person may answer the
    # approval the ask above turns into, and nobody else may.
    from jiuwenswarm.common.scopes import click_rule

    gate = click_rule(scopes, channel="slack", chat="C000000BBBB")
    assert gate is not None
    assert gate.permits("U000000AAAA")
    assert not gate.permits("U000000ZZZZ")
    # And no rule reaches the conversation above it, which is the layering the
    # rest of this test checks for delivery read once for clicks.
    assert click_rule(scopes, channel="slack", chat="C000000AAAA") is None

    # The two identity rules in the example, checked the way an operator would
    # read them: the named person gets the extra paragraph, everyone else in
    # that conversation gets the narrowed trigger set, and neither reaches the
    # other. Composed with a sender because that is what the axis needs; the
    # assertion above composed without one and is the same example seen by a
    # conversation nobody has spoken in yet.
    named = compose_section(
        scopes, channel="slack", chat="C000000BBBB", user="U000000AAAA"
    )
    assert named["prompt"] == (
        "This is a support channel. Be terse.\n\nAnswer this person in French."
    )
    # The narrowing rule excludes them by name, so they keep the platform
    # scope's triggers -- which is the shape section 4.3 replaces an "override:"
    # directive with: the exemption is written into the rule it exempts from.
    assert named["mode"] == frozenset({"mention", "url"})

    everyone_else = compose_section(
        scopes, channel="slack", chat="C000000BBBB", user="U000000ZZZZ"
    )
    assert everyone_else["mode"] == frozenset({"mention"})
    assert everyone_else["prompt"] == "This is a support channel. Be terse."


def test_the_template_documents_what_a_scope_can_and_cannot_set():
    """The constraints an operator only ever meets in this comment block.

    None of them is discoverable from the code an operator can run: a trigger
    name that is not one of the five refuses the whole list and drops the
    conversation to the layer below, a mode that omits ``mention`` is honoured,
    and a reasoning level is simply not a thing a scope can carry. The template
    is where all three are stated, so it is the template this asserts against.
    """
    text = (_RESOURCES / "config.yaml").read_text(encoding="utf-8")
    start = text.index("# ========== scopes:")
    block = text[start : text.index("\nscopes: []", start)]

    for trigger in ("mention", "reply", "all", "url", "has_file"):
        assert trigger in block, trigger
    assert "not implicit" in block.lower()
    assert "the layer below" in block
    assert "[trigger: url]" in block
    assert "models.defaults" in block
    # It cannot be a per-conversation setting: a reasoning level is fixed when a
    # model entry is built, and there is no per-request path for it. Saying so
    # is what stops the key being asked for again.
    assert "no per-conversation reasoning level" in block
    # And the one that will be asked for next. A session's work_mode is locked
    # on its first turn, so a scope could set it only for conversations that
    # have not spoken yet -- which is a setting nobody can tell is working.
    assert "no per-conversation work_mode" in block


# --------------------------------------------------------------------------
# A rule that names a sender, settled per message
# --------------------------------------------------------------------------


def _configured(entries: Any, *, group_chat_mode: str = "mention") -> SlackChannelConfig:
    """A config built the way ``app_gateway`` builds one, from written scopes."""
    scopes = _scopes(entries)
    platform, per_chat = apply_scopes_to_slack_overrides(
        {"group_chat_mode": group_chat_mode}, scopes=scopes
    )
    return SlackChannelConfig(
        group_chat_mode=group_chat_mode,
        conversation_overrides=per_chat,
        platform_override=platform,
        scopes=scopes,
    )


def test_a_config_with_no_identity_rule_settles_exactly_as_before(any_model):
    """The fast path, and the property that makes this change free.

    With no rule naming a sender there is nothing a sender could change, so
    passing one and passing none must give the same answer -- and both must be
    what the settled per-conversation map already held.
    """
    config = _configured(
        [
            {"match": {"channel": "slack"}, "delivery": {"mode": ["mention"]}},
            {
                "match": {"channel": "slack", "chat": "C1"},
                "delivery": {"prompt": "be terse"},
                "agent": {"model_name": "m"},
            },
        ]
    )

    for who in ("", "U_anyone", "U_someone_else"):
        override = settled_override(config, "C1", user_id=who)
        assert override.mode == frozenset({"mention"})
        assert override.prompt == "be terse"
        assert override.model_name == "m"


def test_the_platform_layer_is_still_read_per_key_for_a_conversation_scope(any_model):
    config = _configured(
        [
            {"match": {"channel": "slack"}, "delivery": {"mode": ["all"]}},
            {"match": {"channel": "slack", "chat": "C1"}, "delivery": {"prompt": "p"}},
        ]
    )

    # The conversation named a prompt and nothing else, so the platform layer's
    # triggers still govern there. Pinned because settled_override is now what
    # performs that fallthrough for all three settings at once.
    override = settled_override(config, "C1")
    assert override.mode == frozenset({"all"})
    assert override.prompt == "p"


def test_a_rule_naming_a_sender_settles_only_for_that_sender(any_model):
    config = _configured(
        [
            {"match": {"channel": "slack", "chat": "C1"}, "agent": {"model_name": "base"}},
            {
                "match": {"channel": "slack", "chat": "C1", "user": ["U1"]},
                "agent": {"model_name": "theirs"},
            },
        ]
    )

    assert settled_override(config, "C1", user_id="U1").model_name == "theirs"
    assert settled_override(config, "C1", user_id="U2").model_name == "base"
    # No sender is not everybody. A caller with none gets the layer below.
    assert settled_override(config, "C1").model_name == "base"


def test_a_not_narrows_everyone_except_the_people_it_names(any_model):
    config = _configured(
        [
            {"match": {"channel": "slack"}, "delivery": {"mode": ["all"]}},
            {
                "match": {"channel": "slack", "chat": "C1", "not": {"user": ["U_admin"]}},
                "delivery": {"mode": ["mention"]},
            },
        ]
    )

    # Section 4.3's motivating case, end to end: the exemption is written into
    # the rule it exempts from, and the admin matches no narrowing scope.
    assert channel_triggers(
        config, "C1", group_chat_mode="mention", user_id="U_admin"
    ) == frozenset({"all"})
    assert channel_triggers(
        config, "C1", group_chat_mode="mention", user_id="U_other"
    ) == frozenset({"mention"})
    # And an unidentified sender is not exempt: the restriction holds where
    # nobody could be named, rather than lapsing.
    assert channel_triggers(config, "C1", group_chat_mode="mention") == frozenset(
        {"mention"}
    )


def test_a_signed_mode_on_an_identity_rule_still_inherits_layer_zero(any_model):
    config = _configured(
        [
            {
                "match": {"channel": "slack", "chat": "C1", "user": ["U1"]},
                "delivery": {"mode": ["+has_file"]},
            }
        ],
        group_chat_mode="mention",
    )

    # The per-message fold has to be given the same layer 0 the load-time fold
    # was, or "+has_file" would settle to a set of one and silence @mentions
    # for that person alone.
    assert channel_triggers(
        config, "C1", group_chat_mode="mention", user_id="U1"
    ) == frozenset({"mention", "has_file"})


def test_a_platform_scope_naming_a_sender_reaches_a_conversation_nobody_named(any_model):
    config = _configured(
        [
            {
                "match": {"channel": "slack", "user": ["U1"]},
                "delivery": {"prompt": "for U1 anywhere on slack"},
            }
        ]
    )

    # No scope names C9, so it has no entry in the settled map -- and the rule
    # still applies there, because it was written about the platform. The
    # per-message fold is given the real conversation id rather than None for
    # exactly this case.
    assert settled_override(config, "C9", user_id="U1").prompt == (
        "for U1 anywhere on slack"
    )
    assert settled_override(config, "C9", user_id="U2").prompt is None


def test_the_startup_summary_reports_the_unidentified_answer(any_model, warnings):
    config = _configured(
        [
            {"match": {"channel": "slack", "chat": "C1"}, "delivery": {"mode": ["all"]}},
            {
                "match": {"channel": "slack", "chat": "C1", "user": ["U1"]},
                "delivery": {"mode": ["mention"]},
            },
        ]
    )

    # It is written before anyone has spoken, so it can only report the layer
    # that does not depend on who is speaking. Stated here so the line is read
    # as what it is rather than as a claim about every message in C1.
    summary = describe_configured_channels(config)
    assert "C1" in summary
    assert channel_triggers(config, "C1", group_chat_mode="mention") == frozenset(
        {"all"}
    )


# --------------------------------------------------------------------------
# people: and roles: reaching the connector
# --------------------------------------------------------------------------


def _config_with_a_role() -> dict:
    return {
        "channels": {"slack": {"group_chat_mode": "mention"}},
        "people": {
            "harenome": {"slack": "U000000AAAA"},
            "boss": {"slack": "U000000BBBB"},
        },
        "roles": {"admin": ["harenome", "boss"]},
        "scopes": [
            {
                "match": {
                    "channel": "slack",
                    "chat": "C000000BBBB",
                    "not": {"role": "admin"},
                },
                "delivery": {"prompt_append": "Ask an admin before acting."},
            }
        ],
    }


def test_the_loader_reads_people_and_roles_beside_the_scopes(monkeypatch, warnings):
    import jiuwenswarm.common.config as config_module

    monkeypatch.setattr(config_module, "get_config", _config_with_a_role)

    scopes = slack_connect.load_slack_scopes()

    # The connector's own entry point has to pass them: compiling without them
    # would leave every role undeclared and drop every scope naming one, for a
    # config that is perfectly good.
    assert warnings == []
    assert len(scopes) == 1
    assert scopes[0].match.not_users == ("U000000AAAA", "U000000BBBB")


def test_a_role_bearing_scope_is_folded_per_message(monkeypatch, any_model, warnings):
    import jiuwenswarm.common.config as config_module

    monkeypatch.setattr(config_module, "get_config", _config_with_a_role)
    scopes = slack_connect.load_slack_scopes()
    platform, per_chat = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"}, scopes=scopes
    )
    config = SlackChannelConfig(
        scopes=scopes,
        platform_override=platform,
        conversation_overrides=per_chat,
        group_chat_mode="mention",
    )

    # A role constrains identity, so the per-message path is the one that runs
    # -- the settled map cannot hold an answer that depends on who is speaking.
    admin = settled_override(config, "C000000BBBB", user_id="U000000AAAA")
    everyone_else = settled_override(config, "C000000BBBB", user_id="U000000ZZZZ")

    assert admin.prompt is None
    assert everyone_else.prompt == "Ask an admin before acting."


def test_an_unidentified_sender_is_not_exempted_by_a_role(
    monkeypatch, any_model, warnings
):
    import jiuwenswarm.common.config as config_module

    monkeypatch.setattr(config_module, "get_config", _config_with_a_role)
    scopes = slack_connect.load_slack_scopes()
    platform, per_chat = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"}, scopes=scopes
    )
    config = SlackChannelConfig(
        scopes=scopes,
        platform_override=platform,
        conversation_overrides=per_chat,
        group_chat_mode="mention",
    )

    # The settled map is composed with no sender, and for a "not" that is the
    # same answer the per-message fold gives: nobody is excluded, so the rule
    # applies. Restrictions hold where nobody could be identified.
    assert settled_override(config, "C000000BBBB").prompt == "Ask an admin before acting."


# delivery.mid_turn
# --------------------------------------------------------------------------


def test_a_conversation_nobody_wrote_a_rule_for_cancels(any_model):
    channel = SlackChannel(SlackChannelConfig(enabled=True), slack_connect.RobotMessageRouter())

    # The whole contract of the default: an operator who writes nothing sees
    # exactly what this connector did before the key existed.
    assert channel._mid_turn_mode("C1", "U1") == slack_connect.MID_TURN_CANCEL


def test_a_scope_settles_what_a_mid_turn_message_does(any_model):
    config = _configured(
        [
            {
                "match": {"channel": "slack", "chat": "C1"},
                "delivery": {"mid_turn": "queue"},
            }
        ]
    )
    channel = SlackChannel(config, slack_connect.RobotMessageRouter())

    assert channel._mid_turn_mode("C1", "U1") == slack_connect.MID_TURN_QUEUE
    # Every other conversation is untouched, which is what makes this a
    # per-conversation setting rather than a connector one.
    assert channel._mid_turn_mode("C2", "U1") == slack_connect.MID_TURN_CANCEL


def test_a_platform_scope_settles_it_for_every_conversation(any_model):
    config = _configured(
        [{"match": {"channel": "slack"}, "delivery": {"mid_turn": "steer"}}]
    )
    channel = SlackChannel(config, slack_connect.RobotMessageRouter())

    assert channel._mid_turn_mode("C-never-named", "U1") == slack_connect.MID_TURN_STEER


def test_a_conversation_overrides_the_platform_layer(any_model):
    config = _configured(
        [
            {"match": {"channel": "slack"}, "delivery": {"mid_turn": "queue"}},
            {
                "match": {"channel": "slack", "chat": "C1"},
                "delivery": {"mid_turn": "cancel"},
            },
        ]
    )
    channel = SlackChannel(config, slack_connect.RobotMessageRouter())

    assert channel._mid_turn_mode("C1", "U1") == slack_connect.MID_TURN_CANCEL
    assert channel._mid_turn_mode("C2", "U1") == slack_connect.MID_TURN_QUEUE


def test_it_is_settled_per_key_like_everything_else(any_model):
    config = _configured(
        [
            {"match": {"channel": "slack"}, "delivery": {"mid_turn": "steer"}},
            {
                "match": {"channel": "slack", "chat": "C1"},
                "delivery": {"prompt": "be terse"},
            },
        ]
    )

    # A conversation whose scope set only a prompt keeps the platform layer's
    # mid_turn rather than being read as having declined it.
    settled = settled_override(config, "C1")
    assert settled.prompt == "be terse"
    assert settled.mid_turn == slack_connect.MID_TURN_STEER


def test_a_rule_naming_a_sender_settles_it_for_that_person(any_model):
    config = _configured(
        [
            {"match": {"channel": "slack", "chat": "C1"}, "delivery": {"mid_turn": "queue"}},
            {
                "match": {"channel": "slack", "chat": "C1", "user": ["U1"]},
                "delivery": {"mid_turn": "steer"},
            },
        ]
    )
    channel = SlackChannel(config, slack_connect.RobotMessageRouter())

    assert channel._mid_turn_mode("C1", "U1") == slack_connect.MID_TURN_STEER
    assert channel._mid_turn_mode("C1", "U2") == slack_connect.MID_TURN_QUEUE


def test_an_unrecognised_value_leaves_the_conversation_cancelling(any_model):
    said: list[str] = []
    scopes = _scopes(
        [{"match": {"channel": "slack"}, "delivery": {"mid_turn": "wait"}}],
        warn=lambda m, *a: said.append(m % a),
    )
    platform, per_chat = apply_scopes_to_slack_overrides(
        {"group_chat_mode": "mention"}, scopes=scopes
    )
    channel = SlackChannel(
        SlackChannelConfig(
            conversation_overrides=per_chat, platform_override=platform, scopes=scopes
        ),
        slack_connect.RobotMessageRouter(),
    )

    assert any("is not one of cancel, steer, queue" in line for line in said), said
    # The layer below the last of them is cancel, which is the safe direction:
    # it is what this connector did before the key existed.
    assert channel._mid_turn_mode("C1", "U1") == slack_connect.MID_TURN_CANCEL


def test_slack_declares_no_layer_zero_key_for_mid_turn():
    # No channels.slack key says what a mid-turn message does, so a scope is not
    # a second home for anything and declaring one would report a home an
    # operator could edit to no effect.
    assert channel_capabilities("slack").layer0_key("delivery", "mid_turn") is None


def test_slack_does_not_validate_the_value_itself():
    # The three words name mechanisms rather than Slack ids, so the schema owns
    # the vocabulary and a validator here would be a second copy of it.
    assert channel_capabilities("slack").validator("delivery", "mid_turn") is None


def test_the_summary_names_it_only_where_it_departs_from_the_default(any_model):
    config = _configured(
        [
            {"match": {"channel": "slack", "chat": "C1"}, "delivery": {"mid_turn": "queue"}},
            {"match": {"channel": "slack", "chat": "C2"}, "delivery": {"prompt": "hi"}},
        ]
    )

    summary = describe_configured_channels(config)
    entries = [part for part in summary.split("; ") if " mode=[" in part]
    for_c1 = next(part for part in entries if " C1 " in f" {part} ")
    for_c2 = next(part for part in entries if part.startswith("C2 "))
    assert "mid_turn=queue" in for_c1
    # C2 is on the default, and printing cancel on every line of every
    # deployment would bury the one line where it says something.
    assert "mid_turn" not in for_c2
