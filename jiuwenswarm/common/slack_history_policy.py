# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""One word for how far a Slack conversation may read, and the names it travels under.

Four words, each strictly wider than the one above it:

``disabled``
    No history tool at all.
``origin``
    This conversation only. It is what shipped before any of this existed: the
    tool card declares no target, and the conversation comes from trusted
    request metadata.
``members``
    Another conversation may be named, and every named one is gated at read
    time on ``members(S) subset-of members(T)``.
``open``
    As ``members``, except that a *public* target skips the subset rule.

The rule is about the room and not about the asker, because the answer is
posted into ``S`` and everybody there sees it: a rule keyed on the asker alone
would summarise ``T`` into a room full of people who are not in ``T``. It
subsumes the DM case rather than special-casing it -- in a DM ``members(S)`` is
the user and the bot, so it reduces to *the asking user and the bot are both in
T*.

Publicness is asymmetric and only targets relax. As a *target* a public ``T`` is
safe: membership there is self-serve, so the content was already reachable by
anybody who cared to join. As a *source* a public ``S`` is the dangerous side --
the check holds at the instant it is evaluated, and somebody may join ``S``
afterwards and read ``T`` out of the scrollback. ``open`` therefore relaxes
targets only, enforced by there being no value that reads the source's privacy
rather than by reading it and deciding.

**Why this module exists at all.** Three processes need the same four words and
the same resolution: the Slack connector, which settles the word and stamps it;
the cron scheduler, which settles it again per run for a job's conversation; and
the runtime's history toolkit, which acts on the stamp. The connector cannot be
imported from either of the other two -- it pulls in ``slack_bolt`` -- and the
runtime must not read connector config at all. Written once here, a mapping in
and a word out, so that a cron run and a live message in the same conversation
can never disagree about what that conversation may read.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

#: The four words, in widening order. The order lets a reader answer "is this at
#: least X" without a table, and it is the property the design asserts about the
#: vocabulary.
HISTORY_DISABLED = "disabled"
HISTORY_ORIGIN = "origin"
HISTORY_MEMBERS = "members"
HISTORY_OPEN = "open"
HISTORY_POLICY_VALUES: tuple[str, ...] = (
    HISTORY_DISABLED,
    HISTORY_ORIGIN,
    HISTORY_MEMBERS,
    HISTORY_OPEN,
)
#: What a deployment that has written none of this gets. ``disabled`` rather
#: than ``origin`` because the shipped ``history_digest_channel_ids`` was ``[]``,
#: which read as "no history", and an upgrade must not turn a feature on.
HISTORY_POLICY_DEFAULT = HISTORY_DISABLED

#: The words that let a request name a conversation other than its own.
HISTORY_POLICY_NAMES_A_TARGET: frozenset[str] = frozenset(
    {HISTORY_MEMBERS, HISTORY_OPEN}
)

#: Layer-0 keys, under ``channels.slack``.
KEY_HISTORY = "history"
KEY_HISTORY_NEVER_READ = "history_never_read"
KEY_HISTORY_EXEMPT_MEMBERS = "history_exempt_members"
#: The key ``history`` retires. Still read, still shipped in the template: a key
#: removed from the shipped template is deleted from the operator's file on
#: upgrade, so dropping it outright would silently take history away from a
#: deployment that had configured it, with nothing in the diff to see.
LEGACY_KEY_HISTORY_CHANNEL_IDS = "history_digest_channel_ids"

#: What the connector stamps onto request metadata and the runtime toolkit
#: reads. Literals rather than a shared enum on the wire, because request
#: metadata crosses a process boundary as JSON; a test pins the connector, the
#: cron path and the toolkit to these three names.
METADATA_POLICY_KEY = "slack_history_policy"
METADATA_NEVER_READ_KEY = "slack_history_never_read"
METADATA_EXEMPT_MEMBERS_KEY = "slack_history_exempt_members"
#: Who is asking. Already on every inbound Slack request; named here because the
#: gate reads it, and a cron run legitimately has none.
METADATA_ASKER_KEY = "slack_user_id"
#: Which path built the metadata. A cron run says so, and the gate reads the
#: marker rather than inferring one from a missing sender: "no asker, and that
#: is expected" and "no asker, and something is wrong" are opposite answers, and
#: nothing that can be forged distinguishes them. The connector never stamps
#: this, so an inbound request cannot claim to be a cron run.
#:
#: Held here rather than in the cron module so that the runtime's history
#: toolkit can read it without importing the gateway. ``slack_routing`` re-
#: exports both under its own long-standing names.
METADATA_ORIGIN_KEY = "slack_history_origin"
ORIGIN_CRON_JOB = "cron_job"

#: Said once per distinct translation rather than once per call, because the
#: cron path resolves on every run and a per-run deprecation line is how a
#: warning worth reading gets filtered out. Keyed by what was translated, so an
#: operator who changes the legacy value hears about the new one.
_WARNED_LEGACY_TRANSLATIONS: set[tuple[str, str]] = set()


def slack_config(config: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """The ``channels.slack`` block, or an empty mapping.

    Four callers need it and none of them may import the connector that writes
    it: the history toolkit's settings, the search tool's settings and its
    enablement flag, and the cron scheduler's per-run policy read. Each walked
    the same two levels with the same two shape guards, because ``channels`` and
    ``channels.slack`` are operator-written and either can be absent or be
    something other than a mapping.

    ``config`` is for a caller that already holds one. With nothing passed the
    live config is read on every call rather than captured at start-up, which is
    what lets an operator edit a key and be obeyed without a restart.

    That read is wrapped and an unreadable config answers ``{}`` rather than
    raising. Every caller reads an absent block as the feature being
    unconfigured, and for the two that gate a read that means refusing -- a
    config nobody can parse must not be what decides a read is allowed.
    """
    if config is None:
        from jiuwenswarm.common.config import get_config

        try:
            config = get_config() or {}
        except Exception as exc:  # noqa: BLE001 - a read gate must fail closed.
            logger.warning(
                "channels.slack is unreadable; every caller reads it as unset,"
                " which for a read gate means refusing: %s",
                exc,
            )
            return {}
    channels = config.get("channels") if isinstance(config, Mapping) else None
    slack = channels.get("slack") if isinstance(channels, Mapping) else None
    return slack if isinstance(slack, Mapping) else {}


def normalize_history_policy(raw: Any) -> str | None:
    """One written value as a policy word, or ``None`` if it is not one.

    ``None`` and ``""`` are not errors and are not words: they are a key nobody
    wrote, or wrote with nothing after the colon, which is how the templates
    ship a key an upgrade must not delete. Both mean *no value here*, leaving
    whatever is below to answer.

    A boolean gets no special reading, and that is the point of the word being
    ``disabled``. YAML 1.1 -- which is what ``safe_load`` implements -- resolves
    a bare ``off`` to the boolean false, so while the narrowest word was ``off``
    it was the one value of the four an operator could not write unquoted, and
    the compensation was a ``False``-means-the-narrow-word branch here plus a
    quoted value in every template. ``disabled`` is not a YAML boolean under any
    schema, so the hazard is gone rather than absorbed, and both booleans now
    fail as what they are: an unrecognised value, warned about and resolved to
    the shipped default, which is the narrow one.
    """
    if raw is None:
        return None
    word = str(raw).strip().lower()
    if not word:
        return None
    return word if word in HISTORY_POLICY_VALUES else ""


def id_list(raw: Any) -> tuple[str, ...]:
    """A configured or stamped list of Slack ids, cleaned and de-duplicated.

    Order is preserved rather than sorted, so a warning that quotes the list
    quotes it as the operator wrote it. A bare string is read as the single id
    it plainly is, for the reason ``_as_trigger_set`` is defensive about one:
    iterating a string would silently become a list of letters, which is an
    unreadable corruption rather than an error anybody can see.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        entry = raw.strip()
        return (entry,) if entry else ()
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return ()
    seen: list[str] = []
    for item in raw:
        entry = str(item or "").strip()
        if entry and entry not in seen:
            seen.append(entry)
    return tuple(seen)


def history_policy_from_legacy_channel_ids(entries: Iterable[Any]) -> tuple[str, str]:
    """``history_digest_channel_ids`` as a policy word, plus what was lost.

    Three rows. The third loses information:

    ==========================  ============  ==============================
    ``history_digest_channel_ids``  word      note
    ==========================  ============  ==============================
    ``[]`` or absent            ``disabled``  --
    ``["*"]``                   ``origin``    --
    ``["C0A", "C0B"]``          ``disabled``  per-conversation, not expressible
    ==========================  ============  ==============================

    ``["*"]`` becomes ``origin`` rather than ``members``: the legacy key never
    let a request name another conversation, so translating it to a word that
    does would widen a deployment on upgrade.

    A list of ids becomes ``disabled`` and says so. ``history`` matches on
    ``channel`` only -- it is one word for the Slack platform -- so "these three
    conversations and no others" has no form here. ``disabled`` is the safe
    direction: it removes a capability rather than granting one to conversations
    that were never named. The note is the whole of what an operator can act on,
    so it is returned rather than logged from here, and the caller decides
    whether this resolution is the one in force.

    ``"*"`` alongside ids is read as ``"*"``, matching the legacy reader, whose
    test was ``"*" in entries or channel in entries``.
    """
    listed = id_list(entries)
    if not listed:
        return HISTORY_DISABLED, ""
    if "*" in listed:
        return HISTORY_ORIGIN, ""
    return (
        HISTORY_DISABLED,
        f"it named {len(listed)} conversation(s) and per-conversation history"
        f" is no longer expressible: {KEY_HISTORY} is one word for the whole"
        f" Slack connector. History is disabled; set {KEY_HISTORY}:"
        f" {HISTORY_ORIGIN} to restore it for every conversation",
    )


def resolve_history_policy(
    slack_conf: Mapping[str, Any] | None,
    *,
    warn: Any = None,
) -> str:
    """The layer-0 word for ``channels.slack``, legacy key included.

    ``history`` decides on its own whenever it names a known word, so a config
    carrying both keys is answered by the new one and the legacy list is not
    read at all -- the same precedence ``acknowledge_mode`` takes over
    ``acknowledge_requests``. An unrecognised word is a misspelling rather than
    a request to fall back: it resolves to the shipped default without reaching
    the legacy key either, because falling through would let a typo silently
    buy whatever the old list happened to say.

    Fails closed everywhere. Anything that is not a mapping, and any word that
    is not one of the four, lands on ``disabled``.
    """
    emit = warn if callable(warn) else logger.warning
    if not isinstance(slack_conf, Mapping):
        return HISTORY_POLICY_DEFAULT

    word = normalize_history_policy(slack_conf.get(KEY_HISTORY))
    if word:
        return word
    if word == "":
        emit(
            "channels.slack.%s=%r is not one of %s; reading no Slack history"
            " (%s)",
            KEY_HISTORY,
            slack_conf.get(KEY_HISTORY),
            "/".join(HISTORY_POLICY_VALUES),
            HISTORY_POLICY_DEFAULT,
        )
        return HISTORY_POLICY_DEFAULT

    legacy_raw = slack_conf.get(LEGACY_KEY_HISTORY_CHANNEL_IDS)
    if legacy_raw is None:
        return HISTORY_POLICY_DEFAULT
    resolved, note = history_policy_from_legacy_channel_ids(legacy_raw)
    marker = (repr(id_list(legacy_raw)), resolved)
    if marker not in _WARNED_LEGACY_TRANSLATIONS:
        _WARNED_LEGACY_TRANSLATIONS.add(marker)
        emit(
            "channels.slack.%s is deprecated; set %s: %s instead%s",
            LEGACY_KEY_HISTORY_CHANNEL_IDS,
            KEY_HISTORY,
            resolved,
            f". Note: {note}" if note else "",
        )
    return resolved


def resolve_history_never_read(
    slack_conf: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Conversations that may never be a target, whoever asks.

    A property of the workspace rather than of one conversation: if a channel
    must never travel, that is true whichever room asks. Absent and ``[]`` both
    mean *nothing is denied*, which is what a deny-list's empty state has to
    mean and dissolves the absent-versus-empty ambiguity a per-scope allow-list
    would have had.
    """
    if not isinstance(slack_conf, Mapping):
        return ()
    return id_list(slack_conf.get(KEY_HISTORY_NEVER_READ))


def resolve_history_exempt_members(
    slack_conf: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Members whose presence in the source does not block the subset test.

    A list of ids and not an ``exclude_bots`` boolean. A boolean asserts
    something the operator does not know, cannot be audited, and silently covers
    every integration added later; a list names what was decided and can be read
    back.
    """
    if not isinstance(slack_conf, Mapping):
        return ()
    return id_list(slack_conf.get(KEY_HISTORY_EXEMPT_MEMBERS))


def history_policy_metadata(
    policy: str,
    *,
    never_read: Iterable[Any] = (),
    exempt_members: Iterable[Any] = (),
) -> dict[str, Any]:
    """The three keys a request carries, always all three.

    Stamped as values rather than left absent even when they are the default.
    An absent policy word means *no Slack connector settled this request*, which
    the runtime gate reads as a refusal; that is a different thing from a
    connector that settled it to ``disabled``, and only one of them should
    ever be reachable from a path that has a Slack conversation in hand.

    The lists are stamped rather than read from config on the far side, because
    the runtime must not read connector config: a deployment where the two
    disagree would be a gate evaluated against a policy nobody wrote.
    """
    word = normalize_history_policy(policy) or HISTORY_POLICY_DEFAULT
    return {
        METADATA_POLICY_KEY: word,
        METADATA_NEVER_READ_KEY: list(id_list(never_read)),
        METADATA_EXEMPT_MEMBERS_KEY: list(id_list(exempt_members)),
    }


__all__ = [
    "HISTORY_DISABLED",
    "HISTORY_MEMBERS",
    "HISTORY_OPEN",
    "HISTORY_ORIGIN",
    "HISTORY_POLICY_DEFAULT",
    "HISTORY_POLICY_NAMES_A_TARGET",
    "HISTORY_POLICY_VALUES",
    "KEY_HISTORY",
    "KEY_HISTORY_EXEMPT_MEMBERS",
    "KEY_HISTORY_NEVER_READ",
    "LEGACY_KEY_HISTORY_CHANNEL_IDS",
    "METADATA_ASKER_KEY",
    "METADATA_EXEMPT_MEMBERS_KEY",
    "METADATA_NEVER_READ_KEY",
    "METADATA_ORIGIN_KEY",
    "METADATA_POLICY_KEY",
    "ORIGIN_CRON_JOB",
    "history_policy_from_legacy_channel_ids",
    "history_policy_metadata",
    "id_list",
    "normalize_history_policy",
    "resolve_history_exempt_members",
    "resolve_history_never_read",
    "resolve_history_policy",
]
