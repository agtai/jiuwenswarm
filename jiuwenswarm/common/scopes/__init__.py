# Copyright (c) Huawei Technologies Co., Ltd. 2025-2026. All rights reserved.

"""``scopes`` -- one addressing scheme for per-conversation rules.

A top-level list of rules *about requests*, as against ``channels.<platform>``,
which holds properties of the connector. This version carries every axis the
design names -- ``channel``, ``chat``, ``user`` and ``role``, with ``not`` on
identity -- and all four sections: ``delivery``, ``agent``, ``permissions`` and
``clicks``.

``role`` is resolved against two sibling blocks, ``people:`` and ``roles:``,
into the ids ``user`` would have enumerated. They are one axis and they OR (D5),
and a role carries no permissions of its own (D8): it names a set of people.
All authority stays in ``scopes``, which is therefore the one place that answers
"what can happen here".

See ``docs/local/scopes-design.md`` for the design and for what each remaining
deferral is waiting on.
"""

from jiuwenswarm.common.scopes.capabilities import (
    ANY_KEY,
    AxisRestriction,
    ChannelCapabilities,
    channel_capabilities,
    known_channels,
    register_channel,
    restriction_in,
)
from jiuwenswarm.common.scopes.compose import (
    click_rule,
    compose_section,
    compose_values,
    scoped_chats,
)
from jiuwenswarm.common.scopes.people import (
    EMPTY_DIRECTORY,
    PEOPLE_KEY,
    ROLES_KEY,
    PeopleDirectory,
    compile_people,
)
from jiuwenswarm.common.scopes.permissions import (
    denied_tool_level,
    narrow_config_for_scopes,
    settled_tool_levels,
)
from jiuwenswarm.common.scopes.schema import (
    APPEND_SUFFIX,
    AXIS_CHANNEL,
    AXIS_CHAT,
    AXIS_ROLE,
    AXIS_USER,
    CLICK_APPROVE,
    CLICK_KEYS,
    CLICK_STOP,
    CONNECTOR_SECTIONS,
    DEFERRED_AXES,
    DEFERRED_SECTIONS,
    IDENTITY_AXES,
    KEY_MID_TURN,
    LEVEL_ALLOW,
    LEVEL_ASK,
    LEVEL_DENY,
    MATCH_AXIS_RESTRICTIONS,
    MATCH_NOT,
    MID_TURN_CANCEL,
    MID_TURN_QUEUE,
    MID_TURN_STEER,
    MID_TURN_VALUES,
    NOT_AXES,
    PERMISSION_KEYS,
    PERMISSION_LEVELS,
    SECTION_AGENT,
    SECTION_CLICKS,
    SECTION_DELIVERY,
    SECTION_PERMISSIONS,
    SUPPORTED_AXES,
    SUPPORTED_MATCH_KEYS,
    SUPPORTED_SECTIONS,
    ClickRule,
    Scope,
    ScopeMatch,
    compile_scopes,
    matching_scopes,
    signed_entries,
)

__all__ = [
    "ANY_KEY",
    "APPEND_SUFFIX",
    "AXIS_CHANNEL",
    "EMPTY_DIRECTORY",
    "AXIS_CHAT",
    "AXIS_ROLE",
    "AXIS_USER",
    "AxisRestriction",
    "CLICK_APPROVE",
    "CLICK_KEYS",
    "CLICK_STOP",
    "CONNECTOR_SECTIONS",
    "ChannelCapabilities",
    "ClickRule",
    "DEFERRED_AXES",
    "DEFERRED_SECTIONS",
    "IDENTITY_AXES",
    "KEY_MID_TURN",
    "LEVEL_ALLOW",
    "LEVEL_ASK",
    "LEVEL_DENY",
    "MATCH_AXIS_RESTRICTIONS",
    "MATCH_NOT",
    "MID_TURN_CANCEL",
    "MID_TURN_QUEUE",
    "MID_TURN_STEER",
    "MID_TURN_VALUES",
    "NOT_AXES",
    "PEOPLE_KEY",
    "PERMISSION_KEYS",
    "PERMISSION_LEVELS",
    "ROLES_KEY",
    "PeopleDirectory",
    "SECTION_AGENT",
    "SECTION_CLICKS",
    "SECTION_DELIVERY",
    "SECTION_PERMISSIONS",
    "SUPPORTED_AXES",
    "SUPPORTED_MATCH_KEYS",
    "SUPPORTED_SECTIONS",
    "Scope",
    "ScopeMatch",
    "channel_capabilities",
    "click_rule",
    "compile_people",
    "compile_scopes",
    "compose_section",
    "compose_values",
    "denied_tool_level",
    "known_channels",
    "matching_scopes",
    "narrow_config_for_scopes",
    "register_channel",
    "restriction_in",
    "scoped_chats",
    "settled_tool_levels",
    "signed_entries",
]
