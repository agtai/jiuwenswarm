# Copyright (c) Huawei Technologies Co., Ltd. 2025-2026. All rights reserved.

"""Reading the ``scopes:`` list, and saying what is wrong with it.

``scopes`` is a top-level list of rules about *requests* -- which conversation,
on which platform -- as against ``channels.<platform>``, which holds properties
of the connector. Each entry pairs a ``match`` with one or more sections:

.. code-block:: yaml

    scopes:
      - match:    {channel: slack, chat: C0BKHE3AH4M}
        delivery: {mode: [+has_file], prompt_append: "Be terse."}
        agent:    {model_name: "deepseek-v3"}

Loose YAML in, frozen dataclasses out, compiled once at load. That shape is
lifted from ``file_guard.paths``, which is the better-engineered of the two
list-of-rules-with-a-matcher mechanisms already in the tree.

**One name collides and must not be confused with the other.**
``file_guard.paths[].match`` is the match *kind* -- the string ``"prefix"`` or
``"glob"``, saying how ``path`` should be read. A scope's ``match`` is the
criteria themselves. Nothing here is a "match kind" and nothing there is a
criteria block, though both are spelled ``match``.

**Nothing in this module raises, and nothing it is given can fail a load.**
Config is re-read on reload rather than only at boot, so an exception on a
malformed entry would take down every correctly configured scope, and the
connector with them, over one typo. Every failure below warns, keeps going, and
leaves the affected scope or key on a defensible default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from jiuwenswarm.common.scopes.capabilities import (
    ANY_KEY,
    AxisRestriction,
    Warn,
    channel_capabilities,
    known_channels,
    restriction_in,
)
from jiuwenswarm.common.scopes.people import (
    EMPTY_DIRECTORY,
    PEOPLE_KEY,
    ROLES_KEY,
    PeopleDirectory,
    compile_people,
)

logger = logging.getLogger(__name__)

AXIS_CHANNEL = "channel"
AXIS_CHAT = "chat"
AXIS_USER = "user"
AXIS_ROLE = "role"

#: The key that inverts the identity axis. Not an axis itself: ``not`` names no
#: dimension of its own, it removes people from the one ``user`` and ``role``
#: name together, which is why it is listed apart from :data:`SUPPORTED_AXES`
#: and why it never adds a layer of its own (see :class:`ScopeMatch`).
MATCH_NOT = "not"

#: The axes the matcher understands. ``user`` reads the sender; ``role`` is the
#: same axis spelled as a named set of people, resolved against ``people:`` and
#: ``roles:`` at load into the very ids ``user`` would have enumerated.
SUPPORTED_AXES: tuple[str, ...] = (AXIS_CHANNEL, AXIS_CHAT, AXIS_USER, AXIS_ROLE)

#: Everything a ``match:`` block may legally carry -- the axes, plus ``not``.
SUPPORTED_MATCH_KEYS: tuple[str, ...] = (*SUPPORTED_AXES, MATCH_NOT)

#: The axes that name *who is asking*. They are one axis and they OR: a role
#: resolves to a set of the same ``(platform, id)`` pairs ``user`` enumerates,
#: so ``role`` is sugar over ``user`` rather than a second dimension, and
#: ``{user: [U1], role: admin}`` means U1 *or* an admin. AND would mean "U1, but
#: only if also an admin", which nobody wants and which a config author would
#: write by accident.
IDENTITY_AXES: tuple[str, ...] = (AXIS_USER, AXIS_ROLE)

#: What ``not:`` may name in this version. Identity only: ``not: {chat: [...]}``
#: raises a question that need not be answered yet -- whether
#: ``not: {chat: A, user: B}`` means *not (A and B)* or *(not A) and (not B)* --
#: and channel lists are short enough to write out. The syntax below stays
#: forward-compatible with either reading.
#:
#: Both identity spellings are in it, and they union rather than replace one
#: another: ``not: {user: [U1], role: admin}`` excludes U1 *and* the admins,
#: which is the same OR the positive half performs (D5).
NOT_AXES: tuple[str, ...] = (AXIS_USER, AXIS_ROLE)

#: Written into the design, not into the matcher. Named separately so an author
#: who writes one is told it is deferred rather than told it is a typo, and kept
#: as a name now that it is empty so an axis added ahead of its reader still has
#: somewhere to be declared inert.
#:
#: Empty since ``role`` left it: every axis the schema names is now read.
DEFERRED_AXES: tuple[str, ...] = ()

SECTION_DELIVERY = "delivery"
SECTION_AGENT = "agent"
SECTION_PERMISSIONS = "permissions"
SECTION_CLICKS = "clicks"

CLICK_APPROVE = "approve"
CLICK_STOP = "stop"

LEVEL_ALLOW = "allow"
LEVEL_ASK = "ask"
LEVEL_DENY = "deny"

#: The three words a ``permissions.tools`` entry may use, in widening order.
#: The same vocabulary the permission engine parses, spelled here so a typo is
#: caught at load rather than at the tool call it was written to stop.
PERMISSION_LEVELS: tuple[str, ...] = (LEVEL_ALLOW, LEVEL_ASK, LEVEL_DENY)

KEY_MID_TURN = "mid_turn"

MID_TURN_CANCEL = "cancel"
MID_TURN_STEER = "steer"
MID_TURN_QUEUE = "queue"

#: What ``delivery.mid_turn`` may say a mid-turn message does, and the one
#: vocabulary in this module that is *not* a connector's to define. ``mode``
#: names Slack triggers and ``model_name`` names configured models, so both are
#: checked through the channel's own declaration; these three name mechanisms
#: any connector implementing the key implements the same way -- cancel the
#: running turn, join it, or wait for it -- so spelling them per connector would
#: be three copies of one word list and three chances for one of them to drift.
#:
#: ``cancel`` is first because it is the default, and the default is what every
#: deployment that writes nothing gets: the running turn is finished and the new
#: message starts a fresh one, which is what this has always done.
#:
#: The three are not grammatically parallel, deliberately. ``cancel`` and
#: ``steer`` act on the turn already running; ``queue`` acts on the message that
#: just arrived. Each names a mechanism a reader can grep for, which is worth
#: more than the symmetry -- ``join``/``wait`` were considered and rejected
#: because in concurrency vocabulary ``join`` *means* wait, so the pair reads as
#: synonyms while behaving as opposites.
#:
#: ``follow_up`` is deliberately absent. It exists in the runtime, but its answer
#: is emitted on the *first* request's stream under the first request's id, so a
#: connector whose stream bookkeeping is request-id-shaped would have to
#: demultiplex one stream carrying two answers -- and a follow-up round is
#: genuinely its author's work, which makes a single-valued record of who may
#: stop a turn wrong. ``queue`` reaches the same place by giving each message its
#: own turn, its own id and its own owner.
MID_TURN_VALUES: tuple[str, ...] = (MID_TURN_CANCEL, MID_TURN_STEER, MID_TURN_QUEUE)

#: What a ``permissions`` section may set. One key, because ``tools`` is the one
#: field ``narrow_permissions`` is monotone over: ``rules``, ``defaults`` and
#: ``approval_overrides`` have no narrowing operation that cannot also widen,
#: and a scope that could widen them would undo the point of the section.
PERMISSION_KEYS: frozenset[str] = frozenset({"tools"})

#: The gestures a ``clicks`` section may gate (D13, section 8.5). Two, because
#: two exist: an approval button, which answers a question the agent stopped at,
#: and a stop button, which cancels a running turn. A third would need a surface
#: before it needed a key here.
#:
#: Spelled in the shared schema for the same reason ``PERMISSION_LEVELS`` is: a
#: connector narrows this further in its own declaration, but the vocabulary
#: itself is one list, and a misspelled gesture is caught at load rather than at
#: the click it was written to refuse.
CLICK_KEYS: frozenset[str] = frozenset({CLICK_APPROVE, CLICK_STOP})

#: Which match axes a key may be addressed on, for the keys whose meaning this
#: module defines. Keyed ``"<section>.<key>"``, with ``"<section>.*"`` for a
#: statement about a whole section, and intersected with whatever the channel's
#: own declaration says about the same key (§7.2).
#:
#: **Absent means unrestricted, and most keys are absent.** ``delivery.prompt``
#: is the example worth naming: it says what to splice into a message and
#: nothing whatever about how the rule was addressed, so every axis is
#: legitimate there and it has no entry. A key earns an entry only when its own
#: meaning already accounts for an axis, or when the consumer cannot be given
#: the axis at all -- both a small and stateable class rather than a default.
#:
#: **``permissions`` is the second kind, and the restriction is provisional.**
#: A ``permissions`` section is settled in the runtime, at the tool call, from
#: the two ContextVars the request handler sets: a channel and a chat, and no
#: sender. Every such rule is therefore evaluated with ``user=None``, and
#: :meth:`Match.selects` answers that the fail-closed way in both directions --
#: which is the right answer for a sender nobody could name and the wrong one
#: for a sender nobody asked about. ``match: {chat: C1, user: [U_ONCALL]}``
#: never fires at all, so the narrowing an operator wrote is simply absent;
#: ``match: {chat: C1, not: {user: [U_ADMIN]}}`` fires for everybody including
#: U_ADMIN, so the exemption is not merely inert but inverted. Neither is
#: visible from the config, and the second is the more dangerous, because a
#: rule that reads as "restrict everyone but the admins" restricts the admins.
#: Lift this row when the runtime learns who is asking: the restriction is a
#: statement about today's consumer, not about what ``permissions`` means, and
#: the section's own design (§4.3) wants the identity axis back.
#:
#: **The division of labour is by who defines the key.** The ``agent`` and
#: ``delivery`` sections have no shared key list at all -- a key exists in them
#: because a connector named it in ``sections`` -- so a restriction on one of
#: those belongs beside that declaration, in the connector's own
#: ``scope_capabilities``. ``clicks`` is the other case: the gestures are
#: :data:`CLICK_KEYS`, spelled here, and the reason the section cannot be
#: addressed on a sender is a fact about what a click *is* rather than about any
#: platform. It is therefore stated here, once, and it holds for a channel that
#: has not declared at all -- which is exactly the case a connector-side table
#: could not reach.
#:
#: ``not`` needs no entry of its own and gets none. It names no dimension: it
#: removes people from the axis ``user`` and ``role`` name together (see
#: :data:`MATCH_NOT`), so a ``not:`` clause constrains whichever axis it is
#: written over, and barring ``user`` and ``role`` bars ``not`` with them. When
#: ``not`` grows a non-identity form it will constrain that axis instead, and a
#: table permitting the axis will permit it without an edit.
MATCH_AXIS_RESTRICTIONS: Mapping[str, AxisRestriction] = MappingProxyType(
    {
        f"{SECTION_CLICKS}.{ANY_KEY}": AxisRestriction.only_on(
            AXIS_CHANNEL,
            AXIS_CHAT,
            because=(
                "It has no effect on a rule that also names a sender: clicks"
                " says who may press a button, which is not the person the"
                " match selects on, and nothing resolves the two together. So"
                " those clicks stay gated by layer 0 alone, which is wider than"
                " the rule that was written -- move it to a rule matching the"
                " conversation alone"
            ),
        ),
        f"{SECTION_PERMISSIONS}.{ANY_KEY}": AxisRestriction.only_on(
            AXIS_CHANNEL,
            AXIS_CHAT,
            because=(
                "Its consumer is given no sender: the permission hook settles"
                " this section from the channel and the chat alone, so a rule"
                " naming a person never fires and a not: clause exempting one"
                " applies to them as well -- inert one way round and inverted"
                " the other, and invisible either way. Address it on the"
                " conversation instead. The bar is on today's consumer, not on"
                " the section, and lifts when the runtime carries an identity"
            ),
        ),
    }
)

#: Each section has exactly one reader: ``delivery`` the connector, ``agent``
#: the runtime, ``permissions`` the permission engine, ``clicks`` the
#: connector's interaction handler. A key belongs to the section whose reader
#: *acts* on it, which is not always the process that reads the config.
#:
#: The distinction that decides it is carry versus consume. ``prompt`` is read by
#: the connector and consumed there: it is spliced into the message text, and
#: nothing named ``prompt`` ever leaves the connector, so it is ``delivery``.
#: ``model_name`` is read by the connector and merely carried: it goes onto the
#: request as ``params["model_name"]`` and the runtime is what acts on it, so it
#: is ``agent``. Resolving a key in the process that only forwards it is an
#: implementation detail of where the config is read, and must not decide which
#: section names it -- otherwise every key a connector touches would drift into
#: ``delivery`` and the sections would stop meaning anything.
#: ``clicks`` is read by the connector and *is* consumed there -- the refusal
#: happens in the click handler, not one process later -- which is why it is not
#: folded into ``delivery`` all the same: ``delivery`` settles what happens to a
#: message, and a click is not a message. It arrives against a turn that already
#: exists, from someone who may not have started it, and it carries its own
#: principal (D13).
SUPPORTED_SECTIONS: tuple[str, ...] = (
    SECTION_DELIVERY,
    SECTION_AGENT,
    SECTION_PERMISSIONS,
    SECTION_CLICKS,
)

#: The sections a *connector* settles per conversation. ``permissions`` is not
#: one of them: it is resolved in the runtime, where the tool call happens
#: (§7.1). Neither is ``clicks``, which the connector does settle but not per
#: conversation-to-answer: it is read when a button is pressed, against a
#: conversation the connector is already talking in. The distinction is
#: load-bearing rather than tidy -- see ``scoped_chats``, where treating a
#: restricting section as a connector one would let it open a conversation it
#: was written to lock down.
CONNECTOR_SECTIONS: tuple[str, ...] = (SECTION_DELIVERY, SECTION_AGENT)

#: Written into the design, not into any reader. Empty since ``permissions``
#: left it: every section named in the schema is now read by something. Kept as
#: a name rather than deleted, so that a section added ahead of its reader has
#: somewhere to be declared inert instead of being silently obeyed in part.
DEFERRED_SECTIONS: tuple[str, ...] = ()

ENTRY_KEYS: frozenset[str] = frozenset(
    {"match", *SUPPORTED_SECTIONS, *DEFERRED_SECTIONS}
)

#: A key ending in this appends to the key it names instead of replacing it.
#: Two keys rather than a sigil inside the text, because a marker embedded in a
#: multi-line prose block is hard to read and hard to escape.
APPEND_SUFFIX = "_append"



def _describe_identity(
    users: "tuple[str, ...] | None", roles: "tuple[str, ...] | None"
) -> "list[str]":
    """The ``user:`` and ``role:`` clauses of a description, in that order.

    ``None`` omits a clause; an empty tuple prints as an empty list, which is
    the distinction a ``clicks`` rule needs -- there, naming nobody is a rule
    that refuses everybody and not an absent one.

    Role-derived ids appear under ``user:`` as well as the role name they came
    from, because the ids are what a sender or a clicker is checked against.
    Showing the name alone would describe the config rather than the rule, and
    the two differ exactly when a role resolves to fewer people than it reads as
    -- which is the case worth being able to see in a log.
    """
    parts: "list[str]" = []
    if users is not None:
        parts.append(f"{AXIS_USER}: [{', '.join(users)}]")
    if roles is not None:
        parts.append(f"{AXIS_ROLE}: [{', '.join(roles)}]")
    return parts


@dataclass(frozen=True)
class ScopeMatch:
    """The criteria one scope is selected by.

    ::

        match     = channel? and chat? and identity?
        identity  = sender in (user or role) minus not.(user or role)

    Different axes AND; an absent axis matches anything. An absent positive
    identity means everyone; an absent ``not`` excludes nobody.

    ``users`` and ``not_users`` are the two halves of **one** axis, held as
    sorted tuples because the config spells them as lists and the order of a set
    means nothing.

    **A ``role`` is resolved into those same two tuples at load, and that is the
    whole of the feature.** A role names a set of people and a person is a set of
    ``(platform, id)`` pairs, so on the one platform a scope names, a role *is* a
    list of ids -- which is exactly what ``user`` enumerates (D5). Resolving at
    load rather than at match time keeps ``role`` sugar over ``user`` in the code
    as well as in the design: the matcher, the composition and both readers are
    untouched by it, the OR between the two spellings is a set union performed
    once instead of a branch evaluated per message, and there is no way for the
    two to drift into meaning different things. ``roles`` and ``not_roles`` keep
    the names the ids came from, for the description only.
    """

    channel: "str | None" = None
    chat: "str | None" = None
    users: "tuple[str, ...] | None" = None
    not_users: "tuple[str, ...] | None" = None
    roles: "tuple[str, ...] | None" = None
    not_roles: "tuple[str, ...] | None" = None

    @property
    def constrains_identity(self) -> bool:
        """Whether this match says anything at all about who is asking.

        Every half counts, and they count as **one**. ``not: {user: [U_intern]}``
        with no positive is "everyone except one person", which is narrower than
        "everyone" and is therefore a constraint on the same axis a positive
        ``user`` constrains; ``role`` is that axis spelled as a name (D5). One
        boolean rather than a count is what keeps ``{channel, chat, role}`` and
        ``{channel, chat, user}`` at the same layer, so that rewriting a list of
        ids as a role cannot silently change which scope wins.

        The role halves are still tested here even though resolution has already
        folded their ids into ``users``, because a role that resolves to nobody
        on this platform leaves an empty tuple -- and a match that says "the
        admins, of whom there are none here" constrains identity every bit as
        much as one naming an id. Reading it as unconstrained would promote it
        to a broader layer for having matched nobody.
        """
        return (
            self.users is not None
            or self.not_users is not None
            or self.roles is not None
            or self.not_roles is not None
        )

    @property
    def specificity(self) -> int:
        """How many axes were given -- and that number is the layer (section 6).

        ::

            layer 0   channels.<platform>.*
            layer 1   {channel: X}
            layer 2   {channel: X, chat: Y}
            layer 3   {channel: X, chat: Y, user: [Z]}

        **Identity counts once, however it is spelled.** ``user``, ``role`` and
        ``not`` are one axis (D5, D6), so ``{channel, chat, user}`` and
        ``{channel, chat, user, not}`` are both layer 3 and neither outranks the
        other. Counting the keys instead would make the second layer 4 and let
        adding an exemption to a rule silently promote it above a rule that had
        been winning. The reordering produces no crash and no log line: it
        appears as the wrong model or the wrong trigger set on a real
        conversation.

        **Two scopes at the same layer can be incomparable, and that is the case
        to know about.** ``{channel, user}`` -- this person anywhere on the
        platform -- and ``{channel, chat}`` -- everyone in this conversation --
        are both layer 2, and neither contains the other. Section 6 orders the
        nested case and says nothing about this one, so there is no narrower
        scope to prefer, and inventing a weight for identity would answer an
        open question by accident and reorder the nested cases as a side effect.
        They tie, and the tie is broken the way every other tie here is: by
        position in the file, later wins. That is the only ordering rule an
        author can apply without counting axes, and it is written down in
        :class:`Scope`.
        """
        return sum(
            1
            for present in (
                self.channel is not None,
                self.chat is not None,
                self.constrains_identity,
            )
            if present
        )

    def selects(
        self,
        *,
        channel: "str | None",
        chat: "str | None",
        user: "str | None" = None,
    ) -> bool:
        """Whether this match claims a request from ``user`` in ``chat``.

        **An unidentified sender fails both halves of the identity axis in the
        same direction, and it falls out of one rule rather than two.** Ids are
        non-empty, so an empty sender is in no positive list -- a scope written
        for named people does not fire for someone the connector could not name
        -- and is in no ``not`` list either, so a restriction written to exempt
        named people still applies to them. Both are the fail-closed answer, and
        they are section 8.3's rule for a person with no id on this platform:
        the restriction applies where they have not been identified.
        """
        if self.channel is not None and self.channel != channel:
            return False
        if self.chat is not None and self.chat != chat:
            return False
        sender = (user or "").strip()
        if self.users is not None and sender not in self.users:
            return False
        if self.not_users is not None and sender in self.not_users:
            return False
        return True

    def describe(self) -> str:
        """This match as one line, for a log or a startup summary.

        The identity halves are ``_describe_identity``'s, twice: once for what
        the match selects and once inside ``not``, which is the same two clauses
        about the other direction.
        """
        parts = [
            f"{name}: {value}"
            for name, value in ((AXIS_CHANNEL, self.channel), (AXIS_CHAT, self.chat))
            if value is not None
        ]
        parts.extend(_describe_identity(self.users, self.roles))
        written = _describe_identity(self.not_users, self.not_roles)
        if written:
            parts.append(f"{MATCH_NOT}: {{{', '.join(written)}}}")
        return "{" + ", ".join(parts) + "}" if parts else "{}"


#: What a warning says has happened to a value it could not read. Everything in
#: ``match`` drops the whole scope, which is the safe direction there; a
#: ``clicks`` clause drops the clause alone, and saying "dropping that scope" of
#: it would send an operator looking for settings that are still in force.
DROP_SCOPE = "Dropping that scope"


@dataclass(frozen=True)
class ClickRule:
    """Who may make one kind of click in the conversations a scope matches.

    ``users`` is the settled list of ids, with every ``role`` already folded into
    it at load exactly as :func:`_resolve_roles` folds one into a ``match``: the
    two spellings are one axis and they OR (D5). ``roles`` keeps the names they
    came from, for the description only.

    **An empty ``users`` is a rule and not an absence, and that is F2.** A role
    that is declared but holds nobody with an id on this platform settles here as
    an empty tuple, and the answer is section 8.3's second rule read at click
    time -- a person with no id for the current platform is not in the role there
    -- so nobody satisfies it and every click is refused.

    A rule that should not apply is left out (F1: layer 0 decides) rather than
    written empty.
    """

    users: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()

    def permits(self, user_id: "str | None") -> bool:
        """Whether ``user_id`` may make this click (F2).

        Both halves of "cannot be identified" fail here in the same direction and
        by the same line. A payload that carried no value for any of the
        channel's ``identity_keys`` arrives as an empty string, and ids are
        non-empty, so it is in no list; an id the rule's ``role`` maps nobody
        onto is likewise in no list. Neither is read as a permission, so the
        refusal is the answer whenever the id is missing, by whichever of the two
        routes it went missing.
        """
        clicker = (user_id or "").strip()
        return bool(clicker) and clicker in self.users

    def describe(self) -> str:
        """This rule as one line, for a log.

        ``user:`` is always written, empty tuple included, because an empty one
        here is a rule that refuses everybody rather than an absent clause.
        """
        parts = _describe_identity(self.users, self.roles or None)
        return "{" + ", ".join(parts) + "}"


@dataclass(frozen=True)
class Scope:
    """One compiled entry, with everything unusable already dropped.

    ``index`` is the entry's position in the file. It breaks ties between two
    scopes of equal specificity, so that within one layer the later line wins --
    the only ordering rule an author can apply without counting axes.
    """

    match: ScopeMatch
    sections: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    index: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sections",
            MappingProxyType(
                {k: MappingProxyType(dict(v)) for k, v in self.sections.items()}
            ),
        )

    @property
    def layer(self) -> int:
        return self.match.specificity

    def selects(
        self,
        *,
        channel: "str | None",
        chat: "str | None",
        user: "str | None" = None,
    ) -> bool:
        return self.match.selects(channel=channel, chat=chat, user=user)

    def section(self, name: str) -> Mapping[str, Any]:
        return self.sections.get(name, {})


def signed_entries(value: Any) -> "tuple[str, ...] | None":
    """The ``+x`` / ``-x`` entries of ``value``, or ``None`` if it has none.

    A list is either all-plain or all-signed. ``[mention, +has_file]`` is
    rejected because it reads as either "replace with these two" or "replace
    with mention, then add has_file", and would mean whichever the
    implementation happened to do.
    """
    if not isinstance(value, (list, tuple)):
        return None
    entries = [str(item).strip() for item in value if isinstance(item, str)]
    if len(entries) != len(list(value)):
        return None
    signed = [e for e in entries if e[:1] in ("+", "-")]
    if not signed:
        return None
    return tuple(signed) if len(signed) == len(entries) else ()


def _describe_list_mix(value: Sequence[Any]) -> str:
    return "[" + ", ".join(repr(item) for item in value) + "]"


def _compile_ids(
    raw_value: Any,
    *,
    position: str,
    label: str,
    warn: Warn,
    consequence: str = DROP_SCOPE,
) -> "tuple[str, ...] | None":
    """The ids under one identity key, or ``None`` if it cannot be honoured.

    In ``match``, every failure here drops the whole scope rather than the key,
    and the direction is the reason. An identity axis that could not be read and
    were simply ignored would leave a rule written for named people applying to
    everyone in the conversation, and a ``not`` that were ignored would apply a
    restriction inside the exemption it was written to carve out. Both reach
    further than what was written. Dropping reaches less far, and leaves the
    conversation on the layer below rather than on a rule nobody wrote.

    ``consequence`` is what the caller does about it, said out loud in the
    warning. A ``clicks`` clause drops the clause and not the scope -- it is one
    key of one section, and the sections beside it are still perfectly readable
    -- so it says so rather than sending an operator looking for delivery
    settings that are still in force.
    """
    if isinstance(raw_value, str):
        # A bare id where a list is wanted. Refused rather than read as a list
        # of one: section 4.2 makes ``user`` a list precisely so that promoting
        # an inline list to a role later is a pure refactor, and accepting both
        # spellings would give the axis two shapes with one meaning.
        warn(
            "scopes%s.%s=%r is a single id where a list is wanted; write"
            " [%s]. %s",
            position,
            label,
            raw_value,
            raw_value,
            consequence,
        )
        return None
    if not isinstance(raw_value, (list, tuple)):
        warn(
            "scopes%s.%s=%r is not a list of ids. %s",
            position,
            label,
            raw_value,
            consequence,
        )
        return None

    ids: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            warn(
                "scopes%s.%s=%s is not a list of ids; quote ids so YAML leaves"
                " them as written. %s",
                position,
                label,
                _describe_list_mix(list(raw_value)),
                consequence,
            )
            return None
        text = item.strip()
        if not text:
            warn(
                "scopes%s.%s has an empty id in it. %s",
                position,
                label,
                consequence,
            )
            return None
        ids.append(text)

    if not ids:
        # Not read as "no constraint". An author who wrote the key meant to name
        # somebody, and reading an empty positive list as everyone would turn
        # a key written to name specific people into a match on all of them.
        warn(
            "scopes%s.%s is an empty list, which names nobody; it is not read as"
            " everyone. %s",
            position,
            label,
            consequence,
        )
        return None
    return tuple(sorted(set(ids)))


def _compile_role_names(
    raw_value: Any,
    *,
    position: str,
    label: str,
    warn: Warn,
    consequence: str = DROP_SCOPE,
) -> "tuple[str, ...] | None":
    """The role names under one key, or ``None`` if it cannot be honoured.

    A scalar and a list are both accepted, and this is not the inconsistency it
    looks like beside :func:`_compile_ids`, which refuses a bare id for the
    reason given at that refusal. A role name has no such refactor to protect,
    ``role: admin`` is what the design writes, and naming two roles is the same
    OR the axis already performs, so refusing either spelling would be a rule
    nobody asked for.
    """
    values = [raw_value] if isinstance(raw_value, str) else raw_value
    if not isinstance(values, (list, tuple)):
        warn(
            "scopes%s.%s=%r is not a role name or a list of them. %s",
            position,
            label,
            raw_value,
            consequence,
        )
        return None

    names: list[str] = []
    for item in values:
        if not isinstance(item, str):
            warn(
                "scopes%s.%s=%s is not a list of role names. %s",
                position,
                label,
                _describe_list_mix(list(values)),
                consequence,
            )
            return None
        text = item.strip()
        if not text:
            warn(
                "scopes%s.%s has an empty role name in it. %s",
                position,
                label,
                consequence,
            )
            return None
        names.append(text)

    if not names:
        # The same reading as an empty ``user`` list, for the same reason: an
        # author who wrote the key meant to name somebody, and an empty positive
        # matching everyone is the widest possible reading of the narrowest
        # possible instruction.
        warn(
            "scopes%s.%s is an empty list, which names no role; it is not read"
            " as everyone. %s",
            position,
            label,
            consequence,
        )
        return None
    return tuple(sorted(set(names)))


def _compile_not(
    raw: Any, *, position: str, warn: Warn
) -> "tuple[bool, tuple[str, ...] | None, tuple[str, ...] | None]":
    """Settle a ``not:`` block into the people it excludes.

    Returns ``(kept, not_users, not_roles)``. ``kept`` is false when the scope
    must go. The two halves are collected separately and both survive: a block
    naming ``user`` and ``role`` together excludes the union of them, which is
    the same OR the positive half performs.
    """
    if not isinstance(raw, Mapping):
        warn(
            "scopes%s.match.%s=%r is not a mapping of criteria to exclude;"
            " dropping that scope",
            position,
            MATCH_NOT,
            raw,
        )
        return False, None, None
    if not raw:
        warn(
            "scopes%s.match.%s is empty, so it excludes nobody; dropping that"
            " scope rather than reading it as a rule that names no exemption",
            position,
            MATCH_NOT,
        )
        return False, None, None

    not_users: "tuple[str, ...] | None" = None
    not_roles: "tuple[str, ...] | None" = None
    for raw_key, raw_value in raw.items():
        key = str(raw_key).strip()
        if key in DEFERRED_AXES:
            warn(
                "scopes%s.match.%s.%s is not supported in this version;"
                " dropping that scope rather than applying a restriction to the"
                " people its exemption named",
                position,
                MATCH_NOT,
                key,
            )
            return False, None, None
        if key == AXIS_ROLE:
            names = _compile_role_names(
                raw_value,
                position=position,
                label=f"match.{MATCH_NOT}.{key}",
                warn=warn,
            )
            if names is None:
                return False, None, None
            not_roles = names
            continue
        if key not in NOT_AXES:
            # Section 4.4. Not a typo and not a deferral of the whole axis: the
            # axis is readable, ``not`` on it is what is undecided, because
            # ``not: {chat: A, user: B}`` has two defensible meanings and
            # picking one here would settle an open question by accident.
            warn(
                "scopes%s.match.%s.%s is not something this version can"
                " exclude: %s applies to the identity axis only, and %s is not"
                " it. Dropping that scope; write the conversations out instead",
                position,
                MATCH_NOT,
                key,
                MATCH_NOT,
                key,
            )
            return False, None, None
        ids = _compile_ids(
            raw_value, position=position, label=f"match.{MATCH_NOT}.{key}", warn=warn
        )
        if ids is None:
            return False, None, None
        not_users = ids

    return True, not_users, not_roles


def _compile_match(
    raw: Any, *, position: str, warn: Warn
) -> "ScopeMatch | None":
    """Settle one ``match`` block, or ``None`` if the scope must be dropped."""
    if raw is None:
        # A scope with no criteria applies everywhere. That is legal -- an
        # absent axis matches anything -- and is the layer below any scope that
        # names a platform.
        return ScopeMatch()
    if not isinstance(raw, Mapping):
        warn(
            "scopes%s.match=%r is not a mapping of criteria; dropping that"
            " scope, so nothing it configured applies",
            position,
            raw,
        )
        return None

    values: dict[str, str] = {}
    users: "tuple[str, ...] | None" = None
    not_users: "tuple[str, ...] | None" = None
    roles: "tuple[str, ...] | None" = None
    not_roles: "tuple[str, ...] | None" = None
    for raw_key, raw_value in raw.items():
        key = str(raw_key).strip()
        if key in DEFERRED_AXES:
            # Dropped rather than ignored, and the direction matters. A scope
            # written for one person would, with its identity axis ignored,
            # apply to everyone in the conversation instead -- a rule that
            # reaches further than it was written to reach. Dropping it reaches
            # less far, which is the failure an operator can see and fix.
            warn(
                "scopes%s.match.%s is not supported in this version and would"
                " otherwise widen the scope to everyone it did not name;"
                " dropping that scope",
                position,
                key,
            )
            return None
        if key == MATCH_NOT:
            kept, not_users, not_roles = _compile_not(
                raw_value, position=position, warn=warn
            )
            if not kept:
                return None
            continue
        if key == AXIS_USER:
            users = _compile_ids(
                raw_value, position=position, label=f"match.{key}", warn=warn
            )
            if users is None:
                return None
            continue
        if key == AXIS_ROLE:
            roles = _compile_role_names(
                raw_value, position=position, label=f"match.{key}", warn=warn
            )
            if roles is None:
                return None
            continue
        if key not in SUPPORTED_AXES:
            warn(
                "scopes%s.match.%s is not a match axis; a match carries %s."
                " Dropping that scope rather than matching more broadly than it"
                " was written to",
                position,
                key,
                ", ".join(SUPPORTED_MATCH_KEYS),
            )
            return None
        if raw_value is None:
            warn(
                "scopes%s.match.%s has no value; dropping that scope",
                position,
                key,
            )
            return None
        if not isinstance(raw_value, str):
            warn(
                "scopes%s.match.%s=%r is not an id; quote ids so YAML leaves"
                " them as written. Dropping that scope",
                position,
                key,
                raw_value,
            )
            return None
        text = raw_value.strip()
        if not text:
            warn(
                "scopes%s.match.%s is empty; dropping that scope",
                position,
                key,
            )
            return None
        values[key] = text

    return ScopeMatch(
        channel=values.get(AXIS_CHANNEL),
        chat=values.get(AXIS_CHAT),
        users=users,
        not_users=not_users,
        roles=roles,
        not_roles=not_roles,
    )


def _require_channel_for_chat(
    match: "ScopeMatch", *, position: str, warn: Warn
) -> bool:
    """Whether a scope naming a chat also names the channel it belongs to.

    A conversation id is only meaningful inside a platform: ``C0BKHE3AH4M`` is a
    Slack channel and nothing else, but the matcher cannot know that, and a chat
    named without a channel selects for **every** declaring connector.

    The reason to refuse it is not tidiness. Validation is keyed on the channel:
    ``_compile_section`` looks the capabilities up from ``match.channel``, so a
    scope with no channel is checked against nothing at all -- not the key
    allow-list, not the layer-0 map, not a single connector validator. It then
    still matches, and on Slack a scope naming a chat also exempts that
    conversation from ``allowed_channel_ids``. An unvalidated rule that widens
    who can be answered is exactly the shape this design refuses elsewhere.

    Dropped rather than validated-against-everything: which connector's
    validators should apply is section 13's Q2, still open, and guessing at it
    here would settle an open question by accident. A scope with neither axis is
    untouched -- there is no channel to ask, it names no conversation, and it
    cannot exempt one.
    """
    if match.chat is None or match.channel is not None:
        return True
    warn(
        "scopes%s.match.chat=%s names a conversation without saying which"
        " channel it belongs to, so nothing can validate it and it would match"
        " every connector that declares scopes; dropping that scope. Add"
        " channel: alongside chat:",
        position,
        match.chat,
    )
    return False


def _require_channel_for_identity(
    match: "ScopeMatch", *, position: str, warn: Warn
) -> bool:
    """Whether a scope naming senders also names the platform they are on.

    The same rule as :func:`_require_channel_for_chat`, for the same reason and
    with one more of its own. A raw id is meaningless without the platform that
    issued it: identity is an opaque per-channel bag (D9), ``U0BLHQQBCCD`` is a
    Slack id and nothing else, and the matcher cannot know that. Without a
    channel the scope is also checked against no capability declaration at all,
    so nothing says whether the axis is populated there.

    "This person, anywhere" is a real requirement and it is not this. It is what
    ``people:`` is for (section 8.2): a person is named once and mapped to an id
    per platform, which is the only shape in which one entry can mean the same
    human on two of them. That is now built -- and it makes the rule *stricter*
    rather than looser, because a role is resolved per platform. ``role: admin``
    on no channel is not "the admins everywhere": it is a set of ids this
    function cannot even look up, since the same role holds different ids on
    each platform its members are on. A scope that names a sender, by id or by
    role, names the platform.
    """
    if not match.constrains_identity or match.channel is not None:
        return True
    named = [
        *(match.users or ()),
        *(match.not_users or ()),
        *(match.roles or ()),
        *(match.not_roles or ()),
    ]
    warn(
        "scopes%s.match names senders (%s) without saying which platform they"
        " are on, so nothing can resolve or validate them and they would be"
        " matched against every connector that declares scopes; dropping that"
        " scope. Add channel: alongside",
        position,
        ", ".join(named),
    )
    return False


def _identity_spelling(
    users: "tuple[str, ...] | None", roles: "tuple[str, ...] | None"
) -> str:
    """Which spelling of the identity axis the author actually wrote.

    One axis, two spellings, and a warning that named the wrong one would send
    an operator looking for a ``user:`` line that is not in their file.
    """
    written = [
        name
        for name, value in ((AXIS_USER, users), (AXIS_ROLE, roles))
        if value is not None
    ]
    return "/".join(written) or AXIS_USER


def _match_axes(match: ScopeMatch) -> frozenset[str]:
    """The axes a ``match`` constrains, spelled the way the author wrote them.

    **Must be taken before roles are resolved**, and the caller does. After
    :func:`_resolve_roles` a role-only match carries a ``users`` tuple of the
    ids the role folded into, so this would report ``user`` on a rule whose file
    contains no ``user:`` line -- the same mistake :func:`_identity_spelling`
    exists to avoid, made one function over.

    ``not`` contributes no axis of its own. It removes people from the axis
    ``user`` and ``role`` name together (:data:`MATCH_NOT`), so ``not: {user:
    [...]}`` constrains ``user`` and is reported as ``user``. That is what makes
    a restriction barring the identity axes bar the negative half with the
    positive one, without ``not`` needing a row anywhere.
    """
    axes: set[str] = set()
    if match.channel is not None:
        axes.add(AXIS_CHANNEL)
    if match.chat is not None:
        axes.add(AXIS_CHAT)
    if match.users is not None or match.not_users is not None:
        axes.add(AXIS_USER)
    if match.roles is not None or match.not_roles is not None:
        axes.add(AXIS_ROLE)
    return frozenset(axes)


#: What dropping a scope costs, in the words the warning uses. Paired with
#: ``_DROP_CLAUSE`` below: both say the drop is a *widening*, and they say
#: different things because the two clauses leave different things behind. A
#: dropped ``match`` leaves the conversation on the layer below; a dropped
#: ``clicks`` clause leaves the click gated by layer 0 alone, there being no
#: scope under it to fall to.
_DROP_SCOPE = (
    "Dropping that scope, which leaves that conversation on the layer below --"
    " a restriction written this way is not applied either"
)


def _refuse_unknown_roles(
    names: "tuple[str, ...]",
    *,
    directory: PeopleDirectory,
    position: str,
    label: str,
    consequence: str,
    warn: Warn,
) -> bool:
    """Warn and answer ``True`` if any of ``names`` is in no ``roles:`` block.

    Both places a config may name a role -- a ``match`` and a ``clicks`` clause
    -- refuse an undeclared name, and refuse it for one reason: a name in no
    ``roles:`` block is a typo or a role deleted from under a rule still using
    it, and reading it as "nobody" would make ``not: {role: admin}`` exclude
    nobody and land the restriction on exactly the people it was written to
    exempt.

    ``consequence`` is the caller's and is not shared, because the two drops
    leave different things standing and saying so is the whole of F1's
    distinction from F2. The declared roles are listed either way, so the
    warning that reports a typo also shows what could have been meant.
    """
    unknown = sorted({name for name in names if not directory.knows_role(name)})
    if not unknown:
        return False
    warn(
        "scopes%s.%s names %s, which %s: does not declare, so nothing can say"
        " who is in %s. %s. The declared roles are %s",
        position,
        label,
        ", ".join(unknown),
        ROLES_KEY,
        "them" if len(unknown) > 1 else "it",
        consequence,
        ", ".join(sorted(directory.roles)) or "none",
    )
    return True


def _resolve_roles(
    match: ScopeMatch,
    *,
    directory: PeopleDirectory,
    position: str,
    warn: Warn,
) -> "ScopeMatch | None":
    """Fold every named role into the ids it holds on this scope's platform.

    Returns the match with ``users`` and ``not_users`` widened by the roles, or
    ``None`` if the scope must be dropped. Runs after the channel checks above,
    because a role has no meaning without the platform whose ids it resolves to.

    **An undeclared role name is refused, and a declared one that resolves to
    nobody here is not.** They look alike -- both contribute no ids -- and they
    are different configs. A name that is in no ``roles:`` block is one this
    file cannot honour at all: it is a typo, or a role deleted from under a rule
    still using it, and reading it as "nobody" would make ``not: {role: admin}``
    exclude nobody and land the restriction on exactly the people it was written
    to exempt. The scope is dropped, which leaves the conversation on the layer
    below rather than under a rule nobody wrote -- the same direction every
    other refusal in this module takes, and the same one this axis already took
    while it was deferred.

    A *declared* role whose members simply have no id on this platform is a
    config that can be honoured, and its answer is section 8.3's second rule:
    a person with no id for the current platform is not in the role there. So
    the positive half matches nobody and the negative half excludes nobody --
    which is bit for bit the answer the ``user`` axis already gives for a sender
    the connector could not name, and it is why this is a warning and not a
    refusal. Both directions are said out loud, because a restriction that
    applies to everyone including its intended exemptions is the failure section
    8.3 asks to be warned about by name.
    """
    if match.roles is None and match.not_roles is None:
        return match

    channel = match.channel
    named = (*(match.roles or ()), *(match.not_roles or ()))
    if _refuse_unknown_roles(
        named,
        directory=directory,
        position=position,
        label="match",
        consequence=_DROP_SCOPE,
        warn=warn,
    ):
        return None

    def _ids(names: "tuple[str, ...] | None", *, excluding: bool) -> "tuple[str, ...] | None":
        if names is None:
            return None
        found: set[str] = set()
        for name in names:
            ids = directory.ids_for_role(name, channel=channel)
            if ids:
                found.update(ids)
                continue
            elsewhere = ", ".join(directory.channels_for_role(name)) or "no platform"
            if excluding:
                warn(
                    "scopes%s.match.%s.%s=%s excludes nobody on %s: nobody in"
                    " that role has an id there, so the restriction applies to"
                    " them too. Add their %s id under %s: -- they are identified"
                    " on %s",
                    position,
                    MATCH_NOT,
                    AXIS_ROLE,
                    name,
                    channel,
                    channel,
                    PEOPLE_KEY,
                    elsewhere,
                )
            else:
                warn(
                    "scopes%s.match.%s=%s adds nobody on %s: nobody in that role"
                    " has an id there. Add their %s id under %s: -- they are"
                    " identified on %s",
                    position,
                    AXIS_ROLE,
                    name,
                    channel,
                    channel,
                    PEOPLE_KEY,
                    elsewhere,
                )
        return tuple(sorted(found))

    def _union(
        written: "tuple[str, ...] | None", from_roles: "tuple[str, ...] | None"
    ) -> "tuple[str, ...] | None":
        """The OR of the two spellings, as one set of ids (D5, ``IDENTITY_AXES``)."""
        if from_roles is None:
            return written
        return tuple(sorted(set(written or ()) | set(from_roles)))

    return ScopeMatch(
        channel=match.channel,
        chat=match.chat,
        users=_union(match.users, _ids(match.roles, excluding=False)),
        not_users=_union(match.not_users, _ids(match.not_roles, excluding=True)),
        roles=match.roles,
        not_roles=match.not_roles,
    )


def _check_axes_against_capabilities(
    match: ScopeMatch, *, position: str, warn: Warn
) -> None:
    """Warn about a channel that has not opted in, or an axis it cannot fill."""
    if match.channel is None:
        return
    capabilities = channel_capabilities(match.channel)
    if capabilities is None:
        warn(
            "scopes%s.match.channel=%s is not a channel that supports scopes,"
            " so that scope is inert and will never apply. The channels that"
            " declare support are %s",
            position,
            match.channel,
            ", ".join(known_channels()) or "none",
        )
        return
    if match.chat is not None and not capabilities.populates(AXIS_CHAT):
        warn(
            "scopes%s.match.chat is set but %s does not identify a conversation,"
            " so that scope will never match. Match on channel alone",
            position,
            match.channel,
        )
    if match.constrains_identity and not capabilities.populates(AXIS_USER):
        # Two warnings, because the two halves fail in opposite directions and
        # an operator needs to be told which one happened. A positive identity
        # on a channel that names no sender matches nobody, so the rule is
        # inert. A negative one excludes nobody, so the rule applies to
        # everyone -- including the people it was written to exempt, which is
        # the failure section 8.3 asks to be warned about by name.
        #
        # Warned rather than dropped, and ``role`` gets the same treatment as
        # ``user`` because it is the same axis (D5). The config here is
        # perfectly readable -- it is the *channel* that cannot fill the axis --
        # so this is the class of mistake this function reports and the
        # per-scope refusals above are for the class it cannot read at all.
        # Giving one spelling of one axis a refusal where the other gets a
        # warning would be a second answer to one question.
        if match.users is not None or match.roles is not None:
            warn(
                "scopes%s.match.%s is set but %s does not identify a sender, so"
                " that scope will never match. Match on the conversation"
                " instead",
                position,
                _identity_spelling(match.users, match.roles),
                match.channel,
            )
        if match.not_users is not None or match.not_roles is not None:
            warn(
                "scopes%s.match.%s excludes senders but %s does not identify"
                " one, so nobody is excluded and that scope applies to everyone"
                " there -- including whoever it was written to exempt",
                position,
                MATCH_NOT,
                match.channel,
            )


def _effective_axis_restriction(
    section: str,
    key: str,
    capabilities: "Any | None",
) -> "AxisRestriction | None":
    """What both tables together say about how ``section.key`` may be addressed.

    :data:`MATCH_AXIS_RESTRICTIONS` speaks for the keys this module defines and
    for every channel, declared or not; the channel's own declaration speaks for
    the keys it declares. They are intersected rather than ordered, which is
    what makes "a connector may narrow, never widen" true by construction: there
    is no precedence to get the wrong way round, and a connector permitting an
    axis the schema bars simply does not get it.

    An axis name in a declaration that is not one of :data:`SUPPORTED_AXES` is a
    typo in that file, and it is already fail-closed -- an allow-list permits
    only what it names, so an unrecognised name permits nothing and the key ends
    up barred from a rule the author meant to allow. It is reported all the same,
    on the module logger, because otherwise the only evidence is a warning about
    a rule that looks correct. The audience is whoever is editing the
    declaration, not whoever wrote the config.
    """
    shared = restriction_in(MATCH_AXIS_RESTRICTIONS, section, key)
    declared = (
        capabilities.axis_restriction(section, key) if capabilities is not None else None
    )
    if declared is None:
        restriction = shared
    elif shared is None:
        restriction = declared
    else:
        restriction = declared.narrowed_by(shared)
    if restriction is None:
        return None

    unknown = sorted(restriction.allowed - set(SUPPORTED_AXES))
    if unknown:
        logger.warning(
            "scopes: the axis restriction on %s.%s permits %s, which %s not"
            " %s; the axes are %s. Nothing matches on it, so the restriction is"
            " narrower than it reads",
            section,
            key,
            ", ".join(unknown),
            "are" if len(unknown) > 1 else "is",
            "axes" if len(unknown) > 1 else "an axis",
            ", ".join(SUPPORTED_AXES),
        )
    return restriction


def _refuse_for_axis(
    restriction: AxisRestriction,
    matched_axes: "frozenset[str]",
    *,
    position: str,
    section: str,
    key: "str | None",
    warn: Warn,
) -> bool:
    """Warn and refuse if the rule is addressed on an axis ``section.key`` bars.

    Returns whether it refused, so the caller can drop the key -- or the whole
    section, when ``key`` is ``None``.

    **Whether dropping widens or narrows depends on the key, and is not knowable
    here.** For a restriction-shaped key the drop is a widening, and that is the
    direction this module otherwise refuses: a ``clicks`` clause dropped leaves
    the click gated by layer 0 alone, which is exactly what
    :func:`_settle_click_rule` says out loud about its own drops. For a
    value-shaped key -- ``model_name``, or anything a connector settles per
    conversation -- the drop leaves the conversation on the layer below, and
    whether that layer is wider or narrower than the refused rule depends on
    what the operator wrote there. So the sentence naming the direction is the
    declaration's ``because``, written by whoever knows which kind of key it is,
    and this function states only what happened.

    **Refusing is nonetheless the fail-closed answer, and for a reason that does
    not depend on the direction.** The rule cannot be honoured as written: its
    match addresses an axis the key has no meaning on. Keeping the value and
    ignoring the axis would apply a setting written for some requests to all of
    them -- the widening that actually matters, because it is one nobody wrote.
    Dropping grants nothing; it only declines to tighten, and a tightening that
    was wanted can be rewritten at a layer the key does accept.
    """
    refused = restriction.refuses(matched_axes)
    if not refused:
        return False
    warn(
        "scopes%s.%s%s cannot appear in a rule matching on %s. %s. %s. It may"
        " be addressed on %s",
        position,
        section,
        f".{key}" if key is not None else "",
        ", ".join(refused),
        (
            "Ignoring that key, which leaves that conversation on the layer"
            " below"
            if key is not None
            else "Ignoring the whole section, which leaves everything it set on"
            " the layer below"
        ),
        restriction.because or "That axis is not one this key has a meaning on",
        restriction.describe(),
    )
    return True


def _settle_permission_tools(
    raw: Any,
    *,
    position: str,
    channel: "str | None",
    attended: bool,
    warn: Warn,
) -> "dict[str, str] | None":
    """Settle ``permissions.tools``, or ``None`` if nothing in it survives.

    Per entry rather than per key, and this is the one place in this module
    where a partial result is the safe one. Everywhere else a bad value drops
    the whole key, because a half-read ``mode`` would answer messages nobody
    asked it to. Here the direction is reversed: the surviving entries are
    *restrictions*, so keeping them is the conservative reading and dropping
    the lot because one tool name was misspelled would quietly hand back
    permissions the operator believed they had taken away.
    """
    if not isinstance(raw, Mapping):
        warn(
            "scopes%s.%s.tools=%r is not a mapping of tool to allow/ask/deny;"
            " ignoring it, so nothing it named is restricted",
            position,
            SECTION_PERMISSIONS,
            raw,
        )
        return None

    settled: dict[str, str] = {}
    for raw_tool, raw_level in raw.items():
        tool = str(raw_tool).strip()
        if not tool:
            warn(
                "scopes%s.%s.tools has an entry with no tool name; ignoring it",
                position,
                SECTION_PERMISSIONS,
            )
            continue
        level = str(raw_level).strip().lower() if isinstance(raw_level, str) else ""
        if level not in PERMISSION_LEVELS:
            warn(
                "scopes%s.%s.tools.%s=%r is not one of %s; ignoring that entry,"
                " which leaves %s on whatever the permission config already"
                " said rather than on a level nobody wrote",
                position,
                SECTION_PERMISSIONS,
                tool,
                raw_level,
                "/".join(PERMISSION_LEVELS),
                tool,
            )
            continue
        if level == LEVEL_ALLOW:
            # Kept, not dropped: strictest(base, allow) is base, so dropping
            # it would only make the warning and the behaviour describe
            # different configs.
            warn(
                "scopes%s.%s.tools.%s=allow grants nothing: a scope can only"
                " tighten, so this leaves %s exactly as the permission config"
                " already had it. Remove it, or write ask/deny",
                position,
                SECTION_PERMISSIONS,
                tool,
                tool,
            )
        elif level == LEVEL_ASK and not attended:
            warn(
                "scopes%s.%s.tools.%s=ask asks a question nobody can answer on"
                " %s, so it is enforced as deny. Write deny if that is what was"
                " meant",
                position,
                SECTION_PERMISSIONS,
                tool,
                channel,
            )
        settled[tool] = level

    return settled or None


def _settle_mid_turn(key: str, value: Any) -> "tuple[str | None, str]":
    """``(settled value, reason it was refused)`` for one ``mid_turn``.

    Refuses rather than narrows, which is the idiom every other key here
    follows: an unrecognised value drops the key and leaves that conversation on
    the layer below, so a typo costs the setting rather than buying a behaviour
    nobody wrote. What the layer below is depends on where the typo was -- a
    conversation whose own scope is refused falls back to the platform scope, and
    a platform scope refused falls back to ``cancel`` -- and that direction is
    the safe one: ``cancel`` is what this connector did before the key existed.

    Case and surrounding space are settled rather than refused. The three values
    are a closed vocabulary rather than an id belonging to somebody else, so
    there is nothing for ``Queue`` to collide with and nothing gained by making
    an operator find the capital letter -- while refusing it would silently
    leave a conversation cancelling when it was written to wait.

    An ``_append`` on it is refused outright, whatever it says. Appending is for
    prose, and appending to one of three words produces a fourth that is not one
    of them.
    """
    if key.endswith(APPEND_SUFFIX):
        return None, (
            f" appends to a setting that is one of {', '.join(MID_TURN_VALUES)}"
            f" and has nothing to append to. Ignoring it; write {KEY_MID_TURN}"
            f" with the value you want"
        )
    if not isinstance(value, str):
        return None, (
            f"={value!r} is not one of {', '.join(MID_TURN_VALUES)}; ignoring it,"
            f" which leaves that conversation on the layer below"
        )
    settled = value.strip().lower()
    if settled not in MID_TURN_VALUES:
        return None, (
            f"={value!r} is not one of {', '.join(MID_TURN_VALUES)}; ignoring it,"
            f" which leaves that conversation on the layer below rather than on"
            f" a behaviour nobody wrote"
        )
    return settled, ""


_DROP_CLAUSE = "Ignoring that clause, so nothing gates that click here"


def _settle_click_rule(
    raw: Any,
    *,
    position: str,
    kind: str,
    channel: "str | None",
    directory: PeopleDirectory,
    identifies_clicker: bool,
    warn: Warn,
) -> "ClickRule | None":
    """Settle one ``clicks.<gesture>`` clause, or ``None`` if it cannot be read.

    A clause names people the way a ``match`` does -- ``user``, ``role``, or both
    -- because D13's decision is that a click is authorized like a sender, and
    the whole of that decision is reusing section 8.1's identity bag and section
    8.3's roles rather than growing a second principal model beside them.

    **A clause that cannot be read is dropped, and the drop is a widening.** That
    is said out loud in every warning below, because it is the one direction this
    module otherwise refuses: a ``clicks`` clause is a restriction, so ignoring
    it leaves the click on whatever layer 0 already gates (F1) rather than on the
    rule that was written. It is not F2's case and must not be confused with it.
    F2 is a readable config missing a fact at click time: nothing is warned at
    load and the click is refused. This case is a config that cannot be read: it
    warns at load and refuses no click. Refusing every click over a
    typo would take a deployment's approvals away for a mistake it can see and
    fix from the same warning.

    **``not`` is not offered.** Section 4.4 leaves ``not`` on non-identity axes
    open, and a click has no second axis to exclude on: "anyone but these people
    may approve" is the same permissive default `clicks` exists to close, written
    the long way round. Accepting it would answer a question this design has not
    asked.
    """
    if not isinstance(raw, Mapping):
        warn(
            "scopes%s.%s.%s=%r is not a mapping of who may click; write user: or"
            " role:. %s",
            position,
            SECTION_CLICKS,
            kind,
            raw,
            _DROP_CLAUSE,
        )
        return None
    if not raw:
        warn(
            "scopes%s.%s.%s is empty, which names nobody; it is not read as"
            " everyone. %s",
            position,
            SECTION_CLICKS,
            kind,
            _DROP_CLAUSE,
        )
        return None

    users: "tuple[str, ...] | None" = None
    roles: "tuple[str, ...] | None" = None
    for raw_key, raw_value in raw.items():
        key = str(raw_key).strip()
        label = f"{SECTION_CLICKS}.{kind}.{key}"
        if key == AXIS_USER:
            ids = _compile_ids(
                raw_value,
                position=position,
                label=label,
                warn=warn,
                consequence=_DROP_CLAUSE,
            )
            if ids is None:
                return None
            users = ids
            continue
        if key == AXIS_ROLE:
            names = _compile_role_names(
                raw_value,
                position=position,
                label=label,
                warn=warn,
                consequence=_DROP_CLAUSE,
            )
            if names is None:
                return None
            roles = names
            continue
        warn(
            "scopes%s.%s.%s.%s is not a way of naming who may click; a click"
            " names %s. %s",
            position,
            SECTION_CLICKS,
            kind,
            key,
            " or ".join(IDENTITY_AXES),
            _DROP_CLAUSE,
        )
        return None

    settled = set(users or ())
    if roles is not None:
        # The same refusal ``_resolve_roles`` makes on a ``match``, and for the
        # same reason. The consequence differs because the clause differs --
        # there is no scope to leave on the layer below, only a click that goes
        # back to being gated by layer 0 alone -- so it is passed in.
        if _refuse_unknown_roles(
            roles,
            directory=directory,
            position=position,
            label=f"{SECTION_CLICKS}.{kind}",
            consequence=_DROP_CLAUSE,
            warn=warn,
        ):
            return None
        for name in roles:
            ids = directory.ids_for_role(name, channel=channel)
            if ids:
                settled.update(ids)
                continue
            # Kept rather than dropped, and this is F2's second case written
            # into the config rather than met at click time: a declared role
            # whose members have no id here holds nobody here, so it admits
            # nobody here. Said out loud because it is a live restriction that
            # reads like a no-op.
            elsewhere = ", ".join(directory.channels_for_role(name)) or "no platform"
            warn(
                "scopes%s.%s.%s.%s=%s admits nobody on %s: nobody in that role"
                " has an id there, so every %s click there is refused. Add their"
                " %s id under %s: -- they are identified on %s",
                position,
                SECTION_CLICKS,
                kind,
                AXIS_ROLE,
                name,
                channel,
                kind,
                channel,
                PEOPLE_KEY,
                elsewhere,
            )

    if not identifies_clicker:
        # The other half of section 8.5's distinction, and the half that is not
        # "has no effect". A channel that renders no buttons gets the ordinary
        # ineffective-section warning from ``_compile_section``, because there is
        # no click to refuse. A channel that renders them and names nobody has a
        # click to refuse and refuses it -- every one of them -- which is F2 and
        # is worth a different sentence.
        warn(
            "scopes%s.%s.%s says who may click but %s does not identify who"
            " clicked, so every %s click there is refused rather than gated."
            " That is not the same as %s rendering no such button, which would"
            " report the section as having no effect",
            position,
            SECTION_CLICKS,
            kind,
            channel,
            kind,
            channel,
        )

    return ClickRule(users=tuple(sorted(settled)), roles=roles or ())


def _compile_section(
    name: str,
    raw: Any,
    match: ScopeMatch,
    *,
    position: str,
    matched_axes: "frozenset[str]",
    channels_config: Mapping[str, Any],
    directory: PeopleDirectory = EMPTY_DIRECTORY,
    warn: Warn,
) -> dict[str, Any]:
    """Settle one section's keys, dropping the ones that cannot be honoured.

    ``directory`` is needed by ``clicks`` alone, which resolves a ``role`` of its
    own -- one that ``_resolve_roles`` cannot fold, because it names who may
    press a button rather than who the rule is about.

    ``matched_axes`` is passed in rather than read off ``match`` because by the
    time this runs the roles have been folded into ``users``, and a warning
    derived from that would name an axis the author's file does not contain.
    :func:`_match_axes` is taken before the fold, in :func:`compile_scopes`.
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        warn(
            "scopes%s.%s=%r is not a mapping of settings; ignoring that section",
            position,
            name,
            raw,
        )
        return {}

    capabilities = (
        channel_capabilities(match.channel) if match.channel is not None else None
    )
    if capabilities is not None and not capabilities.reads(name):
        warn(
            "scopes%s.%s has no effect: %s does not read the %s section."
            " The sections it reads are %s",
            position,
            name,
            match.channel,
            name,
            ", ".join(sorted(capabilities.sections)) or "none",
        )
        return {}

    # Section-wide first, and dropping the section is the whole answer when it
    # fires. ``clicks`` is the entry that makes this concrete: a ``match``'s
    # identity axis names the sender of a *turn*, a ``clicks`` clause names the
    # person who pressed a button, and a rule carrying both would be settled for
    # nobody -- inert, silently, in the one section written to restrict. That
    # was a hand-written branch here until the restriction table existed; it is
    # one row in that table now, so there is one mechanism and one place to read
    # what a section will accept.
    section_restriction = _effective_axis_restriction(name, ANY_KEY, capabilities)
    if section_restriction is not None and _refuse_for_axis(
        section_restriction,
        matched_axes,
        position=position,
        section=name,
        key=None,
        warn=warn,
    ):
        return {}

    connector_block = channels_config.get(match.channel) if match.channel else None
    connector_block = connector_block if isinstance(connector_block, Mapping) else {}

    settled: dict[str, Any] = {}
    for raw_key, value in raw.items():
        key = str(raw_key).strip()
        base_key = key[: -len(APPEND_SUFFIX)] if key.endswith(APPEND_SUFFIX) else key

        if capabilities is not None and not capabilities.acts_on(name, base_key):
            allowed = capabilities.keys_for(name)
            warn(
                "scopes%s.%s.%s has no effect: %s ignores it. The %s settings it"
                " reads are %s",
                position,
                name,
                key,
                match.channel,
                name,
                ", ".join(sorted(allowed)) if allowed else "none",
            )
            continue

        # Before the value is looked at, because how the rule was addressed is
        # settled whatever the value says: a key barred from ``user`` is barred
        # there whether the value is well formed or not, and checking the value
        # first would warn twice about one rule that has one thing wrong with
        # it. On ``base_key``, so that ``x_append`` is restricted exactly as
        # ``x`` is -- an append is a way of writing the key, not a second key.
        key_restriction = _effective_axis_restriction(name, base_key, capabilities)
        if key_restriction is not None and _refuse_for_axis(
            key_restriction,
            matched_axes,
            position=position,
            section=name,
            key=key,
            warn=warn,
        ):
            continue

        if key.endswith(APPEND_SUFFIX):
            if not isinstance(value, str):
                warn(
                    "scopes%s.%s.%s=%r is not text; %s appends to %s and has"
                    " nothing else to mean. Ignoring it",
                    position,
                    name,
                    key,
                    value,
                    key,
                    base_key,
                )
                continue
        elif isinstance(value, (list, tuple)):
            signed = signed_entries(value)
            if signed == ():
                warn(
                    "scopes%s.%s.%s=%s mixes plain entries with +/- ones, which"
                    " could mean either replacing the set or changing it."
                    " Ignoring it; write every entry signed to change the"
                    " inherited set, or none of them to replace it",
                    position,
                    name,
                    key,
                    _describe_list_mix(value),
                )
                continue
            if signed is not None and any(len(entry) < 2 for entry in signed):
                warn(
                    "scopes%s.%s.%s=%s has a sign with nothing after it;"
                    " ignoring it",
                    position,
                    name,
                    key,
                    _describe_list_mix(value),
                )
                continue
            if signed is None and any(not isinstance(item, str) for item in value):
                warn(
                    "scopes%s.%s.%s=%s is not a list of names; ignoring it",
                    position,
                    name,
                    key,
                    _describe_list_mix(value),
                )
                continue

        if name == SECTION_CLICKS:
            if base_key not in CLICK_KEYS:
                warn(
                    "scopes%s.%s.%s is not a click this version can gate; the"
                    " clicks are %s. Ignoring it",
                    position,
                    name,
                    key,
                    ", ".join(sorted(CLICK_KEYS)),
                )
                continue
            rule = _settle_click_rule(
                value,
                position=position,
                kind=key,
                channel=match.channel,
                directory=directory,
                identifies_clicker=(
                    capabilities.populates(AXIS_USER)
                    if capabilities is not None
                    else True
                ),
                warn=warn,
            )
            if rule is None:
                continue
            settled[key] = rule
            continue

        if name == SECTION_PERMISSIONS:
            if base_key not in PERMISSION_KEYS:
                warn(
                    "scopes%s.%s.%s is not a permissions setting; the settings"
                    " are %s. Ignoring it",
                    position,
                    name,
                    key,
                    ", ".join(sorted(PERMISSION_KEYS)),
                )
                continue
            settled_tools = _settle_permission_tools(
                value,
                position=position,
                channel=match.channel,
                attended=capabilities.attended if capabilities is not None else True,
                warn=warn,
            )
            if settled_tools is None:
                continue
            settled[key] = settled_tools
            continue

        # Checked here rather than through a channel's declaration, because
        # unlike every other value in this loop the vocabulary is not the
        # channel's: the three words name mechanisms, and a connector that
        # implements the key implements the same three. A channel that does not
        # implement it at all has already dropped the key above, on ``acts_on``.
        if name == SECTION_DELIVERY and base_key == KEY_MID_TURN:
            settled_mid_turn, refusal = _settle_mid_turn(key, value)
            if settled_mid_turn is None:
                warn("scopes%s.%s.%s %s", position, name, key, refusal)
                continue
            value = settled_mid_turn

        validator = capabilities.validator(name, base_key) if capabilities else None
        if validator is not None:
            reason = validator(value)
            if reason:
                warn("scopes%s.%s.%s %s", position, name, key, reason)
                continue

        # Only a scope that names no conversation. A platform-only scope is
        # layer 1 sitting directly on layer 0, and setting the same key in both
        # leaves the connector value governing nothing -- that is the redundancy
        # worth a line. A scope that names a conversation is not redundant with
        # anything: layer 0 has no per-conversation form, and the connector
        # setting still governs every other conversation, so saying it had gone
        # dead would be false as well as noisy.
        if capabilities is not None and match.chat is None:
            layer0 = capabilities.layer0_key(name, base_key)
            if layer0 is not None and connector_block.get(layer0) not in (None, "", [], {}):
                warn(
                    "scopes%s.%s.%s and channels.%s.%s both set this, and the"
                    " scope is above it for every conversation, so the connector"
                    " setting now governs nothing. Two places to look for one"
                    " value; keep whichever one is meant",
                    position,
                    name,
                    key,
                    match.channel,
                    layer0,
                )

        settled[key] = value

    return settled


def compile_scopes(
    raw: Any,
    *,
    channels_config: "Mapping[str, Any] | None" = None,
    people: Any = None,
    roles: Any = None,
    directory: "PeopleDirectory | None" = None,
    warn: "Warn | None" = None,
) -> tuple[Scope, ...]:
    """Read the ``scopes:`` list into rules, warning about what it cannot honour.

    ``channels_config`` is the ``channels`` block, used for one check only:
    whether a key a scope sets is also set on the connector it sits above.

    ``people`` and ``roles`` are the two top-level blocks of the same name, read
    here rather than by each caller so that the directory and the rules that
    depend on it are compiled together and warn together. A caller that has
    already built a :class:`~jiuwenswarm.common.scopes.people.PeopleDirectory`
    passes it as ``directory`` instead; passing both prefers the built one, and
    a caller passing neither gets a config in which every ``role:`` is
    undeclared -- which is why the two call sites that read a whole config file
    pass them and no caller may quietly skip them.

    ``warn`` is injected rather than taken from this module's logger so a test
    can read what was said. jiuwenswarm's loggers do not propagate, so ``caplog``
    sees nothing under the pytest CI runs on, and a test written against it
    would pass locally and assert nothing where it matters.
    """
    emit: Warn = warn if warn is not None else logger.warning
    config = channels_config if isinstance(channels_config, Mapping) else {}
    if directory is None:
        directory = (
            compile_people(people, roles, warn=emit)
            if (people is not None or roles is not None)
            else EMPTY_DIRECTORY
        )

    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        emit(
            "scopes=%r is not a list of rules; ignoring it. Every rule is a"
            " list entry pairing a match with the sections it sets",
            raw,
        )
        return ()

    compiled: list[Scope] = []
    for index, entry in enumerate(raw):
        position = f"[{index}]"
        if entry is None:
            continue
        if not isinstance(entry, Mapping):
            emit(
                "scopes%s=%r is not a rule; a rule is a mapping with a match and"
                " the sections it sets. Ignoring it",
                position,
                entry,
            )
            continue

        for unknown in sorted(
            str(key) for key in entry if str(key) not in ENTRY_KEYS
        ):
            emit(
                "scopes%s.%s is not part of a rule and has no effect; a rule"
                " carries match and %s",
                position,
                unknown,
                ", ".join(SUPPORTED_SECTIONS),
            )

        match = _compile_match(entry.get("match"), position=position, warn=emit)
        if match is None:
            continue
        if not _require_channel_for_chat(match, position=position, warn=emit):
            continue
        if not _require_channel_for_identity(match, position=position, warn=emit):
            continue
        # Before resolution, so that a warning names the spelling the author
        # wrote: after it, a role-only match carries a ``users`` tuple and
        # would be reported as a ``user:`` line that is not in their file.
        _check_axes_against_capabilities(match, position=position, warn=emit)
        # Taken here, before the roles are folded into ``users``, so that a
        # refusal names the spelling the author wrote -- the same reason the
        # check above runs before the fold.
        matched_axes = _match_axes(match)
        resolved = _resolve_roles(
            match, directory=directory, position=position, warn=emit
        )
        if resolved is None:
            continue
        match = resolved

        for deferred in DEFERRED_SECTIONS:
            if entry.get(deferred) is not None:
                emit(
                    "scopes%s.%s is not read in this version and has no effect."
                    " Nothing enforces it, so do not rely on it to restrict"
                    " anything",
                    position,
                    deferred,
                )

        sections: dict[str, Mapping[str, Any]] = {}
        for name in SUPPORTED_SECTIONS:
            if name not in entry:
                continue
            settled = _compile_section(
                name,
                entry.get(name),
                match,
                position=position,
                matched_axes=matched_axes,
                channels_config=config,
                directory=directory,
                warn=emit,
            )
            if settled:
                sections[name] = settled

        if not sections:
            continue
        compiled.append(Scope(match=match, sections=sections, index=index))

    return tuple(compiled)


def matching_scopes(
    scopes: Sequence[Scope],
    *,
    channel: "str | None",
    chat: "str | None" = None,
    user: "str | None" = None,
    section: str = SECTION_DELIVERY,
) -> tuple[Scope, ...]:
    """The scopes that apply, ordered so that folding them left is the cascade.

    Sorted by specificity first and by file position second. Specificity first
    is §6's layer table read literally: ``{channel, chat}`` is layer 2 and sits
    above ``{channel}`` at layer 1 whichever order they were written in, which
    is also the precedence a per-conversation rule has always had against
    ``channels.<platform>``. Position second is the only tie-break an author can
    reason about without counting axes -- and with the identity axis in play it
    is load-bearing rather than a formality, because ``{channel, user}`` and
    ``{channel, chat}`` are both layer 2 and neither is narrower than the other.

    ``user`` is the sender, read out of the identity bag by whoever is asking
    (D9) and not assumed to be any particular field. Left ``None`` -- which is
    every caller that has no sender to offer -- the answer is the one for an
    unidentified sender: scopes naming people do not fire, scopes excluding
    people still do.
    """
    applicable = [
        scope
        for scope in scopes
        if scope.section(section)
        and scope.selects(channel=channel, chat=chat, user=user)
    ]
    applicable.sort(key=lambda scope: (scope.layer, scope.index))
    return tuple(applicable)
