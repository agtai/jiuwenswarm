# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""Slack provenance for cron jobs: what a job's session id may be trusted for.

A cron job stores the session id of the conversation it was created in so its
result can be delivered back there, and for Slack that string also names the
channel: ``slack_{team}_{channel}_{user_or_thread_ts}``. That makes it the only
record of which Slack conversation a job belongs to -- and therefore the obvious
source for the runtime's Slack history tools, which read "the current channel"
from trusted request metadata rather than from a model argument.

On its own the string proves nothing. ``CronController`` accepts ``session_id``
verbatim from its callers, so anyone able to create a job could write
``slack_T_<any channel>_x`` into one. While that field only decides *delivery*
the worst outcome is a misdirected report; the moment it also decides *reads* it
becomes a way to pull any channel the bot is in, and an allow-list of ``["*"]``
would not stop it.

This module holds the two halves that turn the field into something a read gate
may rely on:

* ``slack_cron_session_is_trusted`` -- the creation-time check. A job's Slack
  session is trusted only when the request creating it was itself that Slack
  session. The answer is recorded on the job (``CronJob.slack_session_trusted``)
  rather than re-derived later from the string, because by then the request that
  could prove it is gone.
* ``slack_history_metadata_for_cron_job`` -- the run-time construction. It
  re-reads ``channels.slack.history`` on every run and takes exactly the
  decision the inbound Slack path takes -- literally the same resolver -- so
  narrowing the policy narrows cron on its next firing without touching a
  single stored job.

A cron run is **not** held to a weaker or a stronger rule than a live message.
It has a conversation and no sender, and the guarantee the membership rule makes
is about the *audience*: nobody in the conversation the answer lands in learns
anything they could not already learn. That is fully checkable without knowing
who scheduled the job, and who scheduled it does not bear on whether the
disclosure is sound. So the source ``S`` for a cron run is the conversation it
delivers into, the subset test is ``members(S) - exempt subset-of members(T)``,
and the only term that drops is the asker -- who, for a live message, is
normally already in ``members(S)`` anyway.

A job with no delivery conversation at all gets ``{}`` from here, which mounts
no history tool. With no room there is no audience to check the disclosure
against, so there is nothing to allow.

It also holds the other question a job's session id answers -- "does this job
have a Slack conversation to deliver into at all?" -- because the answer is read
off the same string by the same parser, and separating the two would be two
readings of one field.

Every helper fails closed: anything it cannot prove is not Slack.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from jiuwenswarm.common.slack_history_policy import (
    METADATA_ORIGIN_KEY,
    ORIGIN_CRON_JOB,
    history_policy_metadata,
    resolve_history_exempt_members,
    resolve_history_never_read,
    resolve_history_policy,
    slack_config,
)

logger = logging.getLogger(__name__)

# The channel id an inbound Slack request carries. A cron run has no Slack
# channel of its own; it arrives on ``__cron__`` (see ``CronSchedulerService``).
SLACK_CHANNEL_ID = "slack"
CRON_CHANNEL_ID = "__cron__"

# Stamped on a cron run's request metadata alongside the Slack conversation, so
# that a Slack context on a cron turn is only ever one the scheduler put there
# and never one that some other cron code path happened to leave behind.
SLACK_HISTORY_ORIGIN_KEY = METADATA_ORIGIN_KEY
SLACK_HISTORY_ORIGIN_CRON_JOB = ORIGIN_CRON_JOB


def parse_slack_cron_session(session_id: Any) -> tuple[str, str]:
    """Return the ``(channel_id, thread_ts)`` a Slack cron session id names.

    Returns ``("", "")`` for anything that is not one. A session id is built as
    ``slack_{team}_{channel}_{target}``, and the trailing field is one of three
    things: a thread ts (``1710000005.000600``), a DM user id (``U-ONE``), or an
    opaque discriminator (``nightly-digest``). A ts always contains a dot and
    the other two never do, so the dot is the documented discriminator between
    "deliver into this thread" and "deliver to the channel root" -- see
    ``SlackChannel._extract_delivery`` in ``slack_connect.py``, the field's
    origin. (``maxsplit`` also means a target containing an underscore is
    truncated at its first one; harmless here since only the dot is asked
    about.)

    This function is a deliberate, stdlib-only copy of that parse rather than a
    shared import, because ``slack/__init__.py`` pulls in the whole connector
    and ``slack_sdk`` -- too much for the cron path to carry. Keep the two in
    step by hand: two parsers that could disagree would be two answers to
    "which channel is this job's", which is exactly the ambiguity the trust
    flag exists to remove.
    """
    raw = str(session_id or "").strip()
    if not raw.startswith("slack_"):
        return "", ""
    parts = raw.split("_", 4)
    if len(parts) < 4:
        return "", ""
    channel_id = parts[2].strip()
    if not channel_id:
        return "", ""
    session_target = parts[3].strip()
    return channel_id, (session_target if "." in session_target else "")


def slack_cron_session_is_trusted(
    *,
    request_channel_id: Any,
    request_session_id: Any,
    job_session_id: Any,
) -> bool:
    """Whether *job_session_id* is provably the creating request's own session.

    True only when all of the following hold, and False for anything this cannot
    establish -- including every call that does not know which request it is
    serving, which is why the provenance arguments have no defaults at any call
    site that matters:

    1. the creating request arrived on the Slack channel (``channel_id`` is set
       by the connector, never by a client or a model);
    2. the session id about to be stored on the job is that request's own
       session id, character for character;
    3. that session id parses as a Slack conversation.

    (2) is what makes this a provenance check rather than a shape check. A
    hand-written ``slack_T_C123_x`` submitted through the web or TUI cron RPC
    fails (1); one submitted on a Slack turn for a *different* channel fails (2),
    because the session id of a Slack turn is derived by the connector from the
    channel the message actually arrived in.
    """
    if str(request_channel_id or "").strip().lower() != SLACK_CHANNEL_ID:
        return False
    job_sid = str(job_session_id or "").strip()
    if not job_sid or job_sid != str(request_session_id or "").strip():
        return False
    channel_id, _thread_ts = parse_slack_cron_session(job_sid)
    return bool(channel_id)


CRON_SLACK_UNREACHABLE_TEMPLATE = (
    "[Cron] job %s targets Slack but no delivery channel can be resolved: its"
    " session_id %r does not name a Slack conversation and"
    " channels.slack.default_channel_id is unset, so every run of this job will"
    " fail at delivery. Create the job from the Slack conversation it should"
    " post into, or set channels.slack.default_channel_id."
)


def warn_if_slack_cron_delivery_unreachable(
    *,
    targets: Any,
    session_id: Any,
    job_id: Any = "",
    default_channel_id: Any = None,
) -> bool:
    """Say so when a Slack-targeted job has nowhere to deliver its result.

    ``CronJob.targets`` names a *connector*, never a conversation, so "slack" on
    its own says nothing about where a run lands. The conversation comes from
    ``session_id``, which only a job created inside a Slack turn has; a job
    aimed at Slack from the web panel, the TUI or a non-Slack agent turn carries
    a session id from that channel instead, and then only
    ``channels.slack.default_channel_id`` is left. When that is unset too, the
    job is created and scheduled, fires on time, and then raises
    ``SlackDeliveryError`` inside the send path of an unattended run, with
    nothing reported at creation time.

    Asked here, at creation and on every write that moves ``targets`` or
    ``session_id``, because that is the last point where a person is looking.
    The job is still written: a config mistake on this connector is a warning,
    never a refusal, and the fallback this job lacks can be added to config
    afterwards without touching the job at all.

    Returns whether it warned. Never raises -- a warning that could break a job
    write would be worse than the silence it replaces -- so a reachability check
    that itself fails is reported and treated as "nothing to say".
    """
    if str(targets or "").strip().lower() != SLACK_CHANNEL_ID:
        return False
    try:
        from jiuwenswarm.gateway.channel_manager.im_platforms.slack.slack_connect import (
            SlackChannel,
            slack_default_channel_id_from_config,
        )

        fallback = (
            slack_default_channel_id_from_config()
            if default_channel_id is None
            else default_channel_id
        )
        reachable = SlackChannel.delivery_is_reachable(
            session_id=session_id, default_channel_id=fallback
        )
    except Exception as exc:  # noqa: BLE001 - a warning may not break a write.
        logger.warning(
            "[Cron] could not check Slack delivery reachability for job %s: %s",
            str(job_id or "").strip() or "<new>",
            exc,
        )
        return False
    if reachable:
        return False
    logger.warning(
        CRON_SLACK_UNREACHABLE_TEMPLATE,
        str(job_id or "").strip() or "<new>",
        str(session_id or ""),
    )
    return True


def _live_slack_config() -> Mapping[str, Any]:
    """The ``channels.slack`` block as it stands right now, or nothing.

    Read per run rather than captured on the job. That is the whole mechanism
    the retired allow-list is worth keeping: a job whose conversation is
    narrowed out of the policy stops reading on its next firing, with nothing
    rewritten and no job touched.
    """
    return slack_config()


def slack_history_policy_for_cron(
    slack_conf: "Mapping[str, Any] | None" = None,
) -> str:
    """The same word the inbound Slack path settles for the same conversation.

    Deliberately the connector's own resolver rather than a second reading of
    the same keys: one implementation is what makes "a cron run and a message in
    the same conversation can never disagree" a fact rather than an intention.

    It answers for the platform, not for one conversation. A scope's
    ``agent.history`` can narrow or widen a single conversation on the inbound
    path, and cron does not see it: the scopes are compiled by the connector,
    which is not in this process, and a cron run has no sender for a rule naming
    one to be settled against. Layer 0 is therefore the whole of a cron run's
    answer, which is the narrow reading, and it cannot widen a cron run past
    what layer 0 says.
    """
    return resolve_history_policy(
        _live_slack_config() if slack_conf is None else slack_conf
    )


def _slack_channel_type_for(channel_id: str) -> str:
    """Classify a Slack conversation id the way Slack's own id prefixes do.

    A cron job records a conversation id but not its type, and the history tool
    refuses a request whose ``slack_channel_type`` it does not recognise. Slack
    prefixes a direct message with ``D`` and a channel with ``C``/``G``; the
    inbound ``block_actions`` handler already reads the type off the prefix for
    the same reason, so cron reaches the same answer the same way.
    """
    return "im" if str(channel_id or "").startswith("D") else "channel"


def slack_history_metadata_for_cron_job(
    job: Any,
    *,
    slack_conf: "Mapping[str, Any] | None" = None,
) -> dict[str, Any]:
    """Request metadata letting a cron run present its Slack conversation.

    Returns ``{}`` -- meaning "this run has no Slack context, mount nothing" --
    unless the job carries a Slack session whose provenance was established when
    it was created. The channel is read off the job record, never off anything
    the run's prompt can reach, so the model still cannot influence which
    conversation is read; the only thing it controls remains the tool arguments
    (``hours`` / ``all_history`` / ``include_threads``).

    ``slack_history_policy`` is computed here rather than stored, so a job whose
    conversation is narrowed out of the policy stops reading on its next run.
    It is stamped even when it says ``disabled``: the runtime reads a stamped
    word as "a decision was taken and it said no", which is a different thing
    from "no decision was taken", and only the former should ever reach the gate
    from a run that has a Slack conversation in hand.

    No asker is stamped, and none is expected. The gate reads the absence
    together with the cron origin marker below and applies the subset test
    without an asker term; a request claiming to be inbound Slack and carrying
    no sender is a different shape and is refused.
    """
    if not bool(getattr(job, "slack_session_trusted", False)):
        return {}
    channel_id, thread_ts = parse_slack_cron_session(getattr(job, "session_id", None))
    if not channel_id:
        # A job flagged trusted whose session id no longer parses: the flag and
        # the string it describes have drifted apart, so neither is believed.
        logger.warning(
            "[Cron] job %s is flagged as a trusted Slack session but its "
            "session_id does not name a channel; no Slack history context",
            getattr(job, "id", "<unknown>"),
        )
        return {}
    live = _live_slack_config() if slack_conf is None else slack_conf
    metadata: dict[str, Any] = {
        "slack_channel_id": channel_id,
        "slack_channel_type": _slack_channel_type_for(channel_id),
        SLACK_HISTORY_ORIGIN_KEY: SLACK_HISTORY_ORIGIN_CRON_JOB,
        **history_policy_metadata(
            slack_history_policy_for_cron(live),
            never_read=resolve_history_never_read(live),
            exempt_members=resolve_history_exempt_members(live),
        ),
    }
    if thread_ts:
        metadata["slack_thread_ts"] = thread_ts
    return metadata


__all__ = [
    "CRON_CHANNEL_ID",
    "CRON_SLACK_UNREACHABLE_TEMPLATE",
    "SLACK_CHANNEL_ID",
    "SLACK_HISTORY_ORIGIN_CRON_JOB",
    "SLACK_HISTORY_ORIGIN_KEY",
    "parse_slack_cron_session",
    "slack_cron_session_is_trusted",
    "slack_history_metadata_for_cron_job",
    "slack_history_policy_for_cron",
    "warn_if_slack_cron_delivery_unreachable",
]
