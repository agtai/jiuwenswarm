"""The inbound Slack path must not be able to lose a message silently.

Written against a live incident in which direct messages arrived in Slack,
were visible in ``conversations.history``, and produced no turn, no reply, no
acknowledgement reaction and not one log line anywhere. The ingestion path had
thirteen ways to stop before dispatching, twelve of them a bare ``return``, so
all twelve looked identical from outside -- and identical to Slack never having
sent the message at all. These tests hold that closed.
"""

from __future__ import annotations

import logging

import pytest

from jiuwenswarm.common.schema.message import Message
from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.im_platforms.slack import slack_connect
from jiuwenswarm.gateway.channel_manager.im_platforms.slack.slack_connect import (
    SlackChannel,
    SlackChannelConfig,
    SlackChannelOverride,
)

_LOGGER_NAME = slack_connect.logger.name


@pytest.fixture(autouse=True)
def _isolated_dedup_store(tmp_path, monkeypatch):
    """Give every test its own dedup file, never the real workspace's."""
    real_init = slack_connect.SlackEventDedupStore.__init__
    monkeypatch.setattr(
        slack_connect.SlackEventDedupStore,
        "__init__",
        lambda self, path=None, **kw: real_init(
            self, path or tmp_path / "slack_seen_events.json", **kw
        ),
    )


def _dm_channel() -> tuple[SlackChannel, list[Message]]:
    channel = SlackChannel(
        SlackChannelConfig(enabled=True, allow_from=["U0ALLOWED1"]),
        RobotMessageRouter(),
    )
    channel._running = True
    channel._acknowledge_request = _noop  # type: ignore[method-assign]
    received: list[Message] = []
    channel.on_message(received.append)
    return channel, received


async def _noop(*_args, **_kwargs) -> None:
    return None


def _dm_event(ts: str, text: str, **extra) -> dict:
    event = {
        "type": "message",
        "channel_type": "im",
        "channel": "D0DIRECT01",
        "user": "U0ALLOWED1",
        "text": text,
        "ts": ts,
    }
    event.update(extra)
    return event


def _body(event_id: str) -> dict:
    return {"event_id": event_id, "team_id": "T0TESTTEAM"}


def _outcome_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if " outcome=" in r.getMessage()]


@pytest.mark.asyncio
async def test_a_dispatched_direct_message_is_reported_at_the_boundary(caplog) -> None:
    channel, received = _dm_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _dm_event("1710000001.000100", "the parcel arrived"),
            _body("EvDirect"),
        )

    assert len(received) == 1
    (line,) = _outcome_lines(caplog)
    assert "channel=D0DIRECT01" in line
    assert "ts=1710000001.000100" in line
    assert "subtype=-" in line
    assert "outcome=dispatched:dm" in line
    # The identity is enough to find the message in Slack, and stops short of
    # what it said: this line is written for every event including the ignored
    # ones, so it has to be safe to leave on at INFO.
    assert "the parcel arrived" not in line


@pytest.mark.asyncio
async def test_a_second_delivery_of_one_message_says_it_was_deduplicated(caplog) -> None:
    channel, received = _dm_channel()
    event = _dm_event("1710000002.000100", "Four cats sit on a fence.")
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(event, _body("Ev1"))
        # Slack redelivers an envelope it did not see acked in time. The second
        # arrival is correct behaviour and must not read as a lost message.
        await channel._handle_message_event(event, _body("Ev1-retry"))

    assert len(received) == 1
    first, second = _outcome_lines(caplog)
    assert "outcome=dispatched:dm" in first
    assert "outcome=ignored:already-handled (dedupe)" in second


@pytest.mark.asyncio
async def test_the_same_text_sent_twice_is_two_distinguishable_lines(caplog) -> None:
    """A prompt sent twice, as in the incident: same words, two Slack messages.

    Both were lost and the pair was the reason a content-keyed dedup was
    suspected. The boundary line is keyed on ``ts``, so the two are separable
    even though nothing about their text is.
    """
    channel, received = _dm_channel()
    text = "Four cats - one white, three black - sit on a fence."
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(_dm_event("1710000002.000100", text), _body("EvA"))
        await channel._handle_message_event(_dm_event("1710000003.000100", text), _body("EvB"))

    assert len(received) == 2
    first, second = _outcome_lines(caplog)
    assert "ts=1710000002.000100" in first
    assert "ts=1710000003.000100" in second
    assert first != second


@pytest.mark.asyncio
async def test_an_edit_is_reported_as_ignored_rather_than_passed_over(caplog) -> None:
    channel, received = _dm_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _dm_event("1710000004.000100", "", subtype="message_changed"),
            _body("EvEdit"),
        )

    assert received == []
    (line,) = _outcome_lines(caplog)
    assert "subtype=message_changed" in line
    assert "outcome=ignored:subtype-not-user-content (message_changed)" in line


@pytest.mark.asyncio
async def test_a_stopped_channel_says_so_instead_of_returning_in_silence(caplog) -> None:
    channel, received = _dm_channel()
    channel._running = False
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _dm_event("1710000005.000100", "is anyone there"), _body("EvStopped")
        )

    assert received == []
    (line,) = _outcome_lines(caplog)
    assert "outcome=dropped:channel-not-running" in line


@pytest.mark.asyncio
async def test_a_handler_exception_is_logged_at_the_connector_edge(caplog) -> None:
    """slack_bolt swallows this. It must not also be invisible here.

    Bolt catches whatever a listener raises and reports it on its own logger,
    which carries no handler unless ``configure_sdk_logging`` has run. A raise
    inside the handler was therefore perfectly silent, and from the channel it
    looked exactly like a message Slack never sent.
    """
    channel, _received = _dm_channel()

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("wire fell off")

    channel._handle_slack_event = _boom  # type: ignore[method-assign]

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        # Does not propagate: bolt would swallow it anyway, and a listener that
        # raises out of this handler takes no other message with it.
        await channel._handle_message_event(
            _dm_event("1710000001.000100", "the parcel arrived"), _body("EvBoom")
        )

    raised = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert raised, "an exception inside the handler must reach the log"
    assert "ts=1710000001.000100" in raised[0].getMessage()
    # The traceback comes with it: knowing a message was lost to a raise is
    # only half of what the next occurrence needs.
    assert "RuntimeError: wire fell off" in caplog.text
    (line,) = _outcome_lines(caplog)
    assert "outcome=handler-raised" in line


# ---------------------------------------------------------------------------
# One name per kind of event, whichever surface it arrived on.
#
# The outcome vocabulary is only worth logging if each name means one thing.
# ``ignored:no-trigger-matched`` had come to mean three: human conversation in a
# watched channel, a join notice or an edit that is not user content at all, and
# a question addressed to the bot in a way that could never wake it. Nineteen
# events in one night, and the third was one of them.
# ---------------------------------------------------------------------------

_BOT_USER_ID = "U0BOTUSER1"
_BOT_ID = "B0BOTAPP01"
_WATCHED_CHANNEL = "C0WATCHED1"


def _channel_channel(**config_kwargs) -> tuple[SlackChannel, list[Message]]:
    """A connector watching one channel in the default ``mention`` mode.

    Which is the deployed shape: the channel has triggers configured, but the
    only one is ``mention``, and ``mention`` is delivered as ``app_mention`` --
    so every ordinary message in it reaches the end of the trigger match.
    """
    config_kwargs.setdefault("enabled", True)
    config_kwargs.setdefault("allow_from", ["U0ALLOWED1", "U0SENDER01"])
    channel = SlackChannel(SlackChannelConfig(**config_kwargs), RobotMessageRouter())
    channel._running = True
    channel._bot_user_id = _BOT_USER_ID
    channel._bot_id = _BOT_ID
    channel._acknowledge_request = _noop  # type: ignore[method-assign]
    received: list[Message] = []
    channel.on_message(received.append)
    return channel, received


def _channel_event(ts: str, text: str, **extra) -> dict:
    event = {
        "type": "message",
        "channel_type": "channel",
        "channel": _WATCHED_CHANNEL,
        "user": "U0SENDER01",
        "text": text,
        "ts": ts,
    }
    event.update(extra)
    return event


def _outcome_of(line: str) -> str:
    return line.split(" outcome=", 1)[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("subtype", ["channel_join", "message_changed"])
async def test_a_non_content_subtype_is_named_the_same_in_a_channel_as_in_a_dm(
    subtype, caplog
) -> None:
    """The asymmetry the vocabulary was hiding, held closed in both directions.

    Observed live within the same hour: an edit in a DM reported
    ``ignored:subtype-not-user-content (message_changed)``, and the identical
    edit in a channel reported ``ignored:no-trigger-matched``. Four
    ``channel_join`` notices went the same way -- the bot being invited to four
    channels at once, filed as though four people had been chatting.
    """
    dm_channel, dm_received = _dm_channel()
    dm_channel._bot_user_id = _BOT_USER_ID
    ch_channel, ch_received = _channel_channel()

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await dm_channel._handle_message_event(
            _dm_event("1710000006.000100", "", subtype=subtype), _body("EvDM")
        )
        await ch_channel._handle_message_event(
            _channel_event("1710000007.000100", "", subtype=subtype), _body("EvCh")
        )

    assert dm_received == []
    assert ch_received == []
    in_dm, in_channel = (_outcome_of(line) for line in _outcome_lines(caplog))
    assert in_dm == f"ignored:subtype-not-user-content ({subtype})"
    assert in_channel == in_dm


@pytest.mark.asyncio
async def test_a_join_notice_is_not_user_content_before_it_is_an_unwatched_channel(
    caplog,
) -> None:
    """Being a join notice is the more fundamental fact, so it is reported first.

    Otherwise the same ``channel_join`` would be named three ways depending on
    where it landed, and the one name would still not mean one thing.
    """
    channel, received = _channel_channel(group_chat_mode="off")
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _channel_event("1710000008.000100", "", subtype="channel_join"),
            _body("EvJoin"),
        )

    assert received == []
    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line) == "ignored:subtype-not-user-content (channel_join)"


@pytest.mark.asyncio
async def test_an_ordinary_channel_message_still_reports_no_trigger_matched(
    caplog,
) -> None:
    """The bucket keeps its original meaning; it just stops holding the rest."""
    channel, received = _channel_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _channel_event("1710000009.000100", "the kettle is on"), _body("EvChat")
        )

    assert received == []
    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line) == "ignored:no-trigger-matched"


@pytest.mark.asyncio
async def test_a_question_addressed_to_the_bot_id_is_not_filed_as_chatter(
    caplog,
) -> None:
    """The lost message: a real request, ignored in silence, logged as noise.

    ``B0BOTAPP01`` is the app's bot id. Slack only makes a mention out of the
    bot's user id, so this raised no app_mention, matched no trigger, and got no
    reply and no error. It is still ignored -- a bot id is not a way to address
    this bot -- but it no longer looks like the chatter around it.
    """
    channel, received = _channel_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _channel_event(
                "1710000010.000100",
                f"<@{_BOT_ID}> put every open ticket into a spreadsheet"
                " for me, sorted by age.",
            ),
            _body("EvBotIdMention"),
        )

    assert received == [], "naming the case must not start dispatching it"
    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line) == "ignored:bot-id-mention-not-a-trigger"
    # Still the identity only: this line reports that the bot was named the
    # wrong way, not what was asked.
    assert "spreadsheet" not in line


@pytest.mark.asyncio
async def test_mentioning_a_colleague_stays_ordinary_chatter(caplog) -> None:
    """Someone addressing a human in a watched channel is not a near-miss.

    This is the case that keeps the new name worth reading: it fires on one id
    that this connector knows to be its own, never on a guess about who a
    message was for.
    """
    channel, _received = _channel_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _channel_event("1710000011.000100", "<@U0COLLEAG1> does this look right to you?"),
            _body("EvColleague"),
        )

    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line) == "ignored:no-trigger-matched"


@pytest.mark.asyncio
async def test_a_typed_bot_name_is_not_reported_as_a_bot_id_mention(caplog) -> None:
    """``@name`` is a valid token elsewhere in this connector, so it is left alone."""
    channel, _received = _channel_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _channel_event("1710000012.000100", "@jiuwenswarm anybody home?"),
            _body("EvTypedName"),
        )

    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line) == "ignored:no-trigger-matched"


@pytest.mark.asyncio
async def test_a_bot_id_mention_that_matches_a_trigger_still_dispatches(caplog) -> None:
    """Naming the miss changes nothing about the messages that do wake the bot."""
    channel, received = _channel_channel(
        conversation_overrides={
            _WATCHED_CHANNEL: SlackChannelOverride(mode=frozenset({"mention", "url"}))
        },
        allow_from=["U0SENDER01"],
    )
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _channel_event(
                "1710000013.000100",
                f"<@{_BOT_ID}> look at https://example.invalid/pr/1",
            ),
            _body("EvUrlTrigger"),
        )

    assert len(received) == 1
    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line).startswith("dispatched:url")


@pytest.mark.asyncio
async def test_the_correct_mention_wins_even_carrying_a_bot_id_beside_it(
    caplog,
) -> None:
    """What a retype looks like when the first attempt woke nothing: both ids.

    The valid mention leads, so app_mention takes the message and the ``message``
    copy of it says so. The new name must not step in front of that.
    """
    channel, _received = _channel_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _channel_event(
                "1710000014.000100",
                f"<@{_BOT_USER_ID}> <@{_BOT_ID}> list the open tickets"
                " for me, sorted by age.",
            ),
            _body("EvLeadingBotId"),
        )

    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line) == "ignored:leading-bot-mention-handled-as-app_mention"


@pytest.mark.asyncio
async def test_an_unresolved_bot_id_falls_back_to_the_old_name(caplog) -> None:
    """auth.test can fail at startup. Nothing may be claimed about the id then."""
    channel, _received = _channel_channel()
    channel._bot_id = ""
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_message_event(
            _channel_event("1710000010.000100", f"<@{_BOT_ID}> where are the tickets?"),
            _body("EvNoBotId"),
        )

    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line) == "ignored:no-trigger-matched"


@pytest.mark.asyncio
async def test_auth_test_keeps_the_bot_id_beside_the_bot_user_id() -> None:
    """Both ids arrive in one payload; the bot id used to be dropped on the floor."""

    class _Client:
        async def auth_test(self):
            return {"ok": True, "user_id": _BOT_USER_ID, "bot_id": _BOT_ID}

    channel = SlackChannel(SlackChannelConfig(enabled=True), RobotMessageRouter())
    channel._client = _Client()
    await channel._load_bot_user_id()

    assert channel._bot_user_id == _BOT_USER_ID
    assert channel._bot_id == _BOT_ID


@pytest.mark.asyncio
async def test_an_app_post_is_named_the_same_in_a_channel_as_in_a_dm(caplog) -> None:
    """The loop protection moved with the subtype check, and moved together.

    It is one predicate with two callers now; this is what keeps it one.
    """
    dm_channel, _dm_received = _dm_channel()
    ch_channel, _ch_received = _channel_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await dm_channel._handle_message_event(
            _dm_event("1710000015.000100", "posted by an app", bot_id="B0BOTHER"),
            _body("EvAppDM"),
        )
        await ch_channel._handle_message_event(
            _channel_event("1710000015.000100", "posted by an app", bot_id="B0BOTHER"),
            _body("EvAppCh"),
        )

    in_dm, in_channel = (_outcome_of(line) for line in _outcome_lines(caplog))
    assert in_dm == "ignored:posted-by-an-app"
    assert in_channel == in_dm


@pytest.mark.asyncio
async def test_an_app_mention_event_is_still_guarded_before_dispatch(caplog) -> None:
    """app_mention does not pass through the message router's check.

    So _handle_slack_event keeps its own call to the shared predicate. Slack
    should never send this, which is the point: the gate before dispatch cannot
    depend on that.
    """
    channel, received = _channel_channel()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_app_mention(
            {
                "type": "app_mention",
                "channel": _WATCHED_CHANNEL,
                "user": "U0SENDER01",
                "text": f"<@{_BOT_USER_ID}> hello",
                "ts": "1710000014.000100",
                "subtype": "message_changed",
            },
            _body("EvMentionEdit"),
        )

    assert received == []
    (line,) = _outcome_lines(caplog)
    assert _outcome_of(line) == "ignored:subtype-not-user-content (message_changed)"


# ---------------------------------------------------------------------------
# The two click listeners, which lose a *gesture* rather than a message.
#
# Registered the same way as the event listeners and swallowed the same way by
# bolt, but with one difference that makes the silence worse: both acknowledge
# the interaction before they can fail. The person is shown a control that
# reported success, and nothing happened -- a question still waiting with its
# answer nowhere, or a card whose stop button took the click and left the turn
# running.
# ---------------------------------------------------------------------------


class _Ack:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, *_args, **_kwargs) -> None:
        self.calls += 1


def _click_body(action_id: str) -> tuple[dict, dict]:
    action = {"action_id": action_id, "value": "{}"}
    body = {
        "user": {"id": "U0CLICKER1"},
        "channel": {"id": "C0WATCHED1"},
        "container": {"type": "message", "message_ts": "1710000020.000100"},
        "actions": [action],
    }
    return body, action


@pytest.mark.asyncio
async def test_a_question_click_that_raises_is_logged_at_the_connector_edge(
    caplog,
) -> None:
    channel, _received = _dm_channel()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("button fell off")

    channel._decode_button_value = _boom  # type: ignore[method-assign]
    ack = _Ack()
    body, action = _click_body("jiuwenswarm_answer:req-1:0")

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        # Does not propagate, for the reason the event handlers do not: bolt
        # would swallow it, and one click that raised must not take the
        # listener down for the next one.
        await channel._handle_question_action(ack, body, action)

    assert ack.calls == 1
    raised = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert raised, "an exception inside the click handler must reach the log"
    # Enough to find the click in Slack, and nothing that was said in it.
    assert "action_id=jiuwenswarm_answer:req-1:0" in raised[0].getMessage()
    assert "user=U0CLICKER1" in raised[0].getMessage()
    assert "RuntimeError: button fell off" in caplog.text


@pytest.mark.asyncio
async def test_a_stop_click_that_raises_is_logged_at_the_connector_edge(
    caplog,
) -> None:
    channel, _received = _dm_channel()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("card fell off")

    channel._decode_stop_value = _boom  # type: ignore[method-assign]
    ack = _Ack()
    body, action = _click_body(slack_connect._STOP_ACTION_ID)

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_stop_action(ack, body, action)

    assert ack.calls == 1
    raised = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert raised, "an exception inside the click handler must reach the log"
    assert "message_ts=1710000020.000100" in raised[0].getMessage()
    assert "RuntimeError: card fell off" in caplog.text


@pytest.mark.asyncio
async def test_a_click_that_does_not_raise_logs_nothing_extra(caplog) -> None:
    """The guard is a guard. A click that works reads exactly as it did."""
    channel, _received = _dm_channel()
    ack = _Ack()
    # No pending question for this id, which is a path that returns quietly.
    body, action = _click_body("jiuwenswarm_answer:nothing-waiting:0")

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await channel._handle_question_action(ack, body, action)

    assert ack.calls == 1
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []
