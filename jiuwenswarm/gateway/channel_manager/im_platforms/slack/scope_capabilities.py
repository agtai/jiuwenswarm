# Copyright (c) Huawei Technologies Co., Ltd. 2025-2026. All rights reserved.

"""Slack's ``scopes`` declaration -- what it can be matched on, and what it reads.

Found by filename, not by a list kept in ``common/``: the registry globs for
``scope_capabilities.py`` beside each connector, so a connector opting in is one
new file and no edit anywhere else.

**Nothing heavy may be imported at module level here.** This runs during
registry discovery, in both the gateway and the runtime, whether or not Slack is
configured -- so importing ``slack_connect`` would drag ``slack_sdk`` into a
process that has no Slack in it. Two of the three validators below need it and
import it inside their own bodies, where the cost is paid only by a config that
names a model or a trigger. The third, ``history``, checks the word list in
``common/slack_history_policy``. That module imports nothing beyond the standard
library, so it can be read at module level here, and it is already where the
connector, the runtime and the history toolkit read the four words from. A copy
spelled here would be a second list to keep equal to that one.
"""

from __future__ import annotations

from typing import Any

from jiuwenswarm.common.scopes import (
    AXIS_CHANNEL,
    AxisRestriction,
    ChannelCapabilities,
    register_channel,
)
from jiuwenswarm.common.slack_history_policy import HISTORY_POLICY_VALUES

#: How far a history read may reach, widening left to right, and the whole of
#: the surface: one key, four words, one axis of permissiveness.
#:
#: ``disabled`` -- no history tool at all. ``origin`` -- this conversation only,
#: which is what shipped before any of this. ``members`` -- another conversation,
#: every one subject to ``members(S) subset-of members(T)`` at read time.
#: ``open`` -- as ``members``, except that a *public* target skips that rule.
#:
#: ``origin`` grants nothing ``members`` does not: for ``T = S`` the subset test
#: is trivially satisfied. It is kept because it is the only value whose
#: correctness does not depend on our own gate being right -- there is no target
#: argument on the tool card, so there is nothing to probe -- and because it is
#: the cheap one: every ``members`` call naming a target costs a
#: ``conversations.info`` and two paginated ``conversations.members``. It is a
#: capability and cost switch, not a privacy boundary.
#:
#: ``open`` relaxes *targets* only, and there is deliberately no value that
#: reads the source's privacy. The asymmetry is what forces it: as a target a
#: public conversation is safe, because membership there is self-serve and the
#: content was already reachable; as a *source* it is the dangerous side, since
#: the subset check holds when it is evaluated and somebody may join afterwards
#: and read the answer out of the scrollback.
#:
#: The list is ``common/slack_history_policy``'s rather than the shared schema's
#: because ``agent`` has no shared key list: a key exists in that section
#: because a connector named it in ``sections``, and this is the only connector
#: that names this one. If a second implements it the list should move to the
#: schema, the way ``mid_turn``'s did -- at that point there will be two
#: implementations to check the claim "every connector reads these the same way"
#: against, rather than one to guess from.


def _trigger_name(entry: str) -> str:
    """One ``mode`` entry with its sign taken off, if it had one."""
    entry = entry.strip()
    return entry[1:].strip() if entry[:1] in ("+", "-") else entry


def _check_mode(value: Any) -> "str | None":
    """Whether every entry in a ``mode`` list is a trigger name.

    Reached through the declaration rather than duplicated in the shared loader:
    the loader knows that a list is a set and that its entries may be signed,
    and knows nothing whatever about what a Slack trigger is called.

    Reported for the whole key rather than per entry, because the shared loader
    drops a key it cannot honour rather than editing it: the whole list is
    refused, which leaves the conversation on the layer below instead of on a
    narrower set the operator did not write. That is not the same as narrowing:
    the layer below can answer more than the refused list would have, so the
    warning names the conversation and every entry it did not recognise.
    """
    from jiuwenswarm.gateway.channel_manager.im_platforms.slack.slack_connect import (
        CHANNEL_MODE_TRIGGERS,
    )

    if isinstance(value, str):
        # A bare string is the legacy group_chat_mode spelling. It has a meaning
        # here only because a list of one is what it denotes, so say so rather
        # than accepting a shape whose composition rule would be "scalar".
        return (
            f"={value!r} is a single word where a list of triggers is wanted;"
            f" write [{value}]. Ignoring it"
        )
    if not isinstance(value, (list, tuple)):
        return f"={value!r} is not a list of triggers; ignoring it"

    # One sign, then the name, which is how the fold reads a signed entry:
    # ``_apply_signed`` takes ``entry[0]`` as the sign and ``entry[1:]`` as the
    # trigger. Stripping every leading sign instead would pass ``++url`` and
    # leave the fold adding a trigger called ``+url`` -- a name nothing matches,
    # in a set nobody wrote, with no warning anywhere.
    unknown = [
        str(entry)
        for entry in value
        if _trigger_name(str(entry)) not in CHANNEL_MODE_TRIGGERS
    ]
    if unknown:
        return (
            f" names {', '.join(repr(name) for name in unknown)}, which"
            f" {'are' if len(unknown) > 1 else 'is'} not"
            f" {'triggers' if len(unknown) > 1 else 'a trigger'}."
            f" The triggers are {'/'.join(CHANNEL_MODE_TRIGGERS)}. Ignoring the"
            f" whole list, which leaves that conversation on the layer below"
            f" rather than on a set nobody wrote"
        )
    return None


def _check_model_name(value: Any) -> "str | None":
    """Whether ``model_name`` is one of the models actually configured.

    Checked rather than passed through because of how the adapter fails on a
    name it does not have: ``_resolve_model_by_name`` returns the default model
    for anything unrecognised and logs nothing at all. An unchecked typo leaves
    a conversation that looks configured, answers normally, and runs on a model
    nobody chose, with no line anywhere saying so.

    Nothing to check against is not a reason to refuse. A config read that fails
    would otherwise drop a correct setting, which is the one failure an operator
    cannot act on.
    """
    from jiuwenswarm.gateway.channel_manager.im_platforms.slack.slack_connect import (
        configured_models,
    )

    known = configured_models()
    if value is None or isinstance(value, bool) or not isinstance(value, str):
        return f"={value!r} is not a model name; that conversation runs on {known.describe_fallback()}"
    name = value.strip()
    if not name:
        # Unlike a prompt, an empty value here is not a request for "nothing":
        # every turn runs on some model, so there is no empty state to mean.
        return f"is empty; a turn always runs on some model, so that conversation runs on {known.describe_fallback()}"
    if not known.known:
        return None
    if not known.accepts(name):
        return (
            f"={value!r} is not one of the models configured in models.defaults"
            f" ({known.describe()}); dropping it, so that conversation runs on"
            f" {known.describe_fallback()}"
        )
    return None


def _check_history(value: Any) -> "str | None":
    """Whether ``history`` is exactly one of the four words.

    Refuses rather than narrows, which is the idiom every closed vocabulary in
    this design follows: an unrecognised word drops the key and leaves that
    conversation on the layer below, whose floor is ``channels.slack.history``
    and whose default is ``disabled``. That direction is the one that matters
    here -- a typo costs a reach somebody wrote rather than buying one nobody
    did, and the opposite would hand a conversation the right to read another
    one on the strength of a misspelling.

    **Exactly, where ``mid_turn`` settles case and surrounding space, and the
    difference is a property of the mechanism rather than a judgement about the
    words.** ``mid_turn`` is settled by a branch in the shared loader, which can
    replace the value with the word it recognised; this is a connector
    ``validator``, which may only say whether a value is usable. Accepting
    ``Members`` here would therefore store ``Members``, and the contract with the
    connector is that the resolved value is one of the four words -- so a
    spelling the loader cannot normalise is a spelling that must not be
    accepted. Refusing it is the readable failure: the warning names all four,
    and the operator's next edit is correct.

    An ``_append`` reaches this too, carrying whatever was to be appended, and is
    refused by the same test: appending to one of four words produces a fifth
    that is not one of them. The refusal says so rather than leaving an operator
    to work out why their append was not a word.
    """
    if isinstance(value, str) and value in HISTORY_POLICY_VALUES:
        return None
    return (
        f"={value!r} is not one of {', '.join(HISTORY_POLICY_VALUES)}, written"
        f" exactly and in lower case; ignoring it, which leaves that conversation"
        f" on the layer below rather than on a reach nobody wrote. There is"
        f" nothing to append to a word from a closed vocabulary either -- write"
        f" history with the value you want"
    )


SLACK_CAPABILITIES = ChannelCapabilities(
    channel="slack",
    # Slack populates a sender, and the matcher now reads it: event["user"] is
    # set by Slack on every user message and is the only writer of it, which is
    # what an identity axis needs. role -- the same axis spelled as a named set
    # of people -- is still not readable, and that is a property of the matcher
    # rather than of this connector, so it is stated once in the schema module
    # instead of here.
    axes=frozenset({"channel", "chat", "user"}),
    # mode, prompt, mid_turn and model_name, split across the two sections by
    # who acts on the value rather than by who reads the config. This connector
    # resolves all four, and that is not the
    # question: it *consumes* mode, prompt and mid_turn -- mode decides whether
    # a message is answered at all, prompt is spliced into the message text and
    # nothing named prompt ever leaves here, mid_turn decides whether the
    # message is sent, sent as a steer, or held here until the session goes
    # idle -- while model_name it only carries, onto the request as
    # params["model_name"], for the runtime to act on. So the first three are
    # delivery and the fourth is agent.
    #
    # mid_turn is the one whose value this file does not check. mode names Slack
    # triggers and model_name names configured models, both of which belong to
    # this connector; mid_turn names one of three mechanisms the schema defines,
    # so the schema checks it and a validator here would be a second copy of
    # that word list. Declaring the key is still this file's job: the
    # declaration is the opt-in, and it says Slack has actually implemented the
    # three rather than merely recognising the word.
    #
    # prompt_append needs no entry of its own: declaring prompt declares the
    # thing being appended to.
    #
    # permissions is the odd one out and is declared as "all of it": Slack
    # neither consumes nor carries it. It is resolved in the runtime, from the
    # channel and chat ids the request arrived with, and the connector never
    # sees the section at all. The declaration is here because the declaration
    # is the opt-in (§7.2) and because attended is here -- Slack renders
    # interactive approvals, so an ask written for a Slack conversation is a
    # question somebody can actually answer, which is what stops D11 degrading
    # it to a deny. Its keys are left to the shared loader, which knows the
    # allow/ask/deny vocabulary; naming them again here would be a second place
    # to keep that list correct.
    #
    # clicks is named with both of its gestures, because Slack renders both and
    # the list is a statement about this connector rather than about the
    # section: an approval button on every ask, and a stop button on the
    # activity card of a running turn. Declaring it is what separates the two
    # failures section 8.5 keeps apart -- a channel that renders no buttons does
    # not name the section, and a rule against it reports as having no effect,
    # while a rule here is a rule with a click to refuse.
    sections={
        "delivery": frozenset({"mode", "prompt", "mid_turn"}),
        "agent": frozenset(
            {
                "model_name",
                # Carried, never consumed here, exactly as model_name is. This
                # connector settles the word per conversation and stamps it onto
                # the request as params["slack_history_policy"]; the runtime's
                # history toolkit is what acts on it, and it is the only thing
                # that can, because what the word buys is a membership
                # comparison taken at read time against Slack rather than a
                # value anything can settle at load. Config carries the policy,
                # the toolkit enforces it -- the same split permissions makes
                # between a declared level and the engine's decision.
                "history",
            }
        ),
        "permissions": None,
        "clicks": frozenset({"approve", "stop"}),
    },
    # True of this deployment and of no upstream IM connector: the interactive
    # approval path is ours. Read by D11, which degrades a permissions ask to a
    # deny where nobody can answer it.
    attended=True,
    # One id per person, and it is the one the event carries -- on a
    # block_actions payload as much as on a message, which is what makes a
    # clicks rule enforceable here at all: a channel naming no clicker refuses
    # every click rather than gating one. Slack also carries
    # a team id, which is part of the identity bag and is not what a scope
    # matches on: one deployment of this connector talks to one workspace, so a
    # team would be the same value on every side of every comparison. The tuple
    # is ordered for the platforms where that is not true -- Feishu has three
    # ids for one person -- and this one has a single entry rather than an
    # accidental one.
    identity_keys=("user",),
    # The connector settings that answer the same questions. A scope above one
    # of them is the cascade working as intended, and is worth a line only
    # because the value then has two homes.
    #
    # delivery.mode and agent.history have one each. agent.model_name,
    # delivery.prompt and delivery.mid_turn deliberately have none and must not
    # gain any: no channels.slack key pins a model, a standing prompt, or what a
    # mid-turn message does, so inventing a layer-0 key here would make the "two
    # homes for one value" warning fire against a setting that does not exist --
    # and, worse, would make the resolver report a home an operator could go and
    # edit to no effect.
    #
    # channels.slack.history is the real thing rather than an invented one: it
    # is the same question in the same four words, one layer down, and it is
    # where a deployment that wants the feature on everywhere says so without
    # writing a scope at all. Registering it as the twin buys the existing
    # two-homes warning and one vocabulary. group_chat_mode is the precedent,
    # and it also shows the twin need not share a type -- this pair happens to.
    layer0_keys={
        "delivery": {"mode": "group_chat_mode"},
        "agent": {"history": "history"},
    },
    validators={
        "delivery.mode": _check_mode,
        "agent.model_name": _check_model_name,
        "agent.history": _check_history,
    },
    # One axis, and the argument for it is about what the key means rather than
    # about what this connector can populate. Slack does populate a sender --
    # ``axes`` says so and ``model_name`` is matched on one -- and history still
    # may not be addressed that way.
    #
    # user and role are barred because the asker is already handled, and handled
    # dynamically: members(S) subset-of members(T) is the correct treatment of
    # who is asking, taken per request against the room as it stands. A second,
    # static treatment on the same axis is redundant at best, and at worst it
    # grants exactly what membership was withholding. Barring them is also what
    # keeps ``not`` safe here: negation on an identity axis fails open, since a
    # role that resolves to nobody excludes nobody and hands the grant to the
    # people the rule was written to exempt. On ``channel`` a negation names a
    # platform rather than a person, which is why the axis that is left admits
    # one.
    #
    # chat was argued for -- without it the switch reaches every DM, where the
    # subset rule takes its most permissive form -- and does not earn its place.
    # That argument is true about the *number* of eligible targets and wrong
    # about the risk: a DM source discloses to one person whom the rule has just
    # established is a member of the target, and a DM's membership cannot grow,
    # which is the one hole the rule has. The hazard belongs to channels, not
    # DMs. What remained for chat was rollout and API budget, and neither is a
    # reason to put an authorization key on a second axis.
    axis_restrictions={
        "agent.history": AxisRestriction.only_on(
            AXIS_CHANNEL,
            because=(
                "Who is asking is settled per request, by the membership rule,"
                " which is the dynamic and correct treatment of it -- a second"
                " static one on the same axis can grant exactly what membership"
                " was withholding. A conversation is not the unit either: the"
                " membership rule already decides per target. Write the rule on"
                " {channel: slack} alone, or set channels.slack.history"
            ),
        ),
    },
)

register_channel(SLACK_CAPABILITIES)
