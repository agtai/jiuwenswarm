# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""Unit tests for the request-scoped Slack history toolkit."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import pytest

import jiuwenswarm.common.config as config_module
from jiuwenswarm.agents.harness.common.tools import slack_history
from jiuwenswarm.agents.harness.common.tools.slack_history import SlackHistoryToolkit

from tests.unit_tests.channel.slack_card_rules import CANONICAL_CARD_SENTENCES


class _FakeClient:
    def __init__(self, responses: dict[str, list[Any]]) -> None:
        self.responses = {name: list(items) for name, items in responses.items()}
        self.calls: dict[str, list[dict[str, Any]]] = defaultdict(list)

    async def _respond(self, method: str, kwargs: dict[str, Any]) -> Any:
        self.calls[method].append(kwargs)
        item = self.responses[method].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def auth_test(self, **kwargs: Any) -> Any:
        return await self._respond("auth_test", kwargs)

    async def conversations_history(self, **kwargs: Any) -> Any:
        return await self._respond("conversations_history", kwargs)

    async def conversations_replies(self, **kwargs: Any) -> Any:
        return await self._respond("conversations_replies", kwargs)

    async def users_info(self, **kwargs: Any) -> Any:
        return await self._respond("users_info", kwargs)


class _ConcurrentClient:
    def __init__(self) -> None:
        self.history_channels: list[str] = []

    async def auth_test(self, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {"user_id": "U-BOT"}

    async def conversations_history(self, **kwargs: Any) -> dict[str, Any]:
        channel = str(kwargs["channel"])
        self.history_channels.append(channel)
        await asyncio.sleep(0)
        return {
            "messages": [{"ts": "199999.0", "user": "U1", "text": f"from {channel}"}]
        }


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        data: dict[str, Any],
        headers: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.data = data
        self.headers = headers or {}


class _FakeSlackError(Exception):
    def __init__(self, response: _FakeResponse) -> None:
        super().__init__("sanitized fake failure")
        self.response = response


@pytest.fixture(autouse=True)
def _config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda: {"channels": {"slack": {"bot_token": "xoxb-config-secret"}}},
    )


def _toolkit(client: _FakeClient, **kwargs: Any) -> SlackHistoryToolkit:
    return SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C-RESEARCH",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        client=client,
        now=lambda: 200_000.0,
        max_user_lookups=0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_requires_trusted_request_channel_and_card_has_no_channel_argument() -> (
    None
):
    client = _FakeClient({})
    toolkit = SlackHistoryToolkit(metadata={"slack_channel_id": "C1"}, client=client)

    result = json.loads(await toolkit.read_slack_conversation())

    assert result == {
        "ok": False,
        "error": "trusted_slack_channel_context_required",
        "messages": [],
    }
    assert not client.calls
    card = toolkit.get_tools()[0]._card
    assert card.name == "read_slack_conversation"
    assert "chat_id" not in card.input_params["properties"]


def test_the_shared_rules_are_worded_the_way_the_other_card_words_them() -> None:
    """One rule, one sentence, across both Slack cards.

    Three rules apply to both tools and were stated twice in different words:
    the untrusted-data warning, the ts-is-not-a-date rule, and the
    never-build-a-link rule. Two wordings of one rule is worse than saying it
    twice, because a model reading both has to decide whether the difference is
    meaningful.

    All three concern this tool's own results and refer to nothing outside it,
    so a model given this card and not the other one loses nothing by the
    sharing.
    """
    toolkit = SlackHistoryToolkit(
        metadata={"slack_channel_id": "C1"}, client=_FakeClient({})
    )
    description = toolkit.get_tools()[0]._card.description
    for sentence in CANONICAL_CARD_SENTENCES:
        assert sentence in description, sentence


def test_the_card_states_its_own_paging_without_naming_the_other_tool() -> None:
    """Paging is stated for this tool alone, not as a contrast with search.

    The rule a model needs here is the direction: a further slice is older,
    which is what makes before_ts and next_before_ts mean what they say. That
    is sayable without mentioning the search tool, and has to be -- this tool's
    own default is disabled and search is switched on separately, so on most
    deployments the contrast would describe a tool that is not mounted.
    """
    toolkit = SlackHistoryToolkit(
        metadata={"slack_channel_id": "C1"}, client=_FakeClient({})
    )
    description = toolkit.get_tools()[0]._card.description
    assert "Paging walks backwards in time" in description
    assert "older than the one before it, never newer" in description
    for sibling_claim in ("The two Slack tools", "search_slack_workspace"):
        assert sibling_claim not in description, sibling_claim


def test_the_card_describes_the_tool_and_leaves_the_task_to_the_skill() -> None:
    """A card says what a tool is; a skill says what to do with it.

    The card used to carry digest instructions -- write it yourself, in
    Markdown, link each claim to its evidence -- all of which the digest skill
    already said, more fully and where the task actually lives. A card is
    permanent context on every turn that mounts the tool, including every turn
    that is not writing a digest, so task policy there is paid for constantly
    and read by the wrong callers.

    What stays is the half that was capability wearing task clothing: a
    permalink returned here is authoritative and a link assembled from parts is
    a guess, which is true of every use of this tool and of no particular task.
    """
    toolkit = SlackHistoryToolkit(
        metadata={"slack_channel_id": "C1"}, client=_FakeClient({})
    )
    description = toolkit.get_tools()[0]._card.description

    for policy in (
        "For a channel digest",
        "write the digest yourself",
        "in Markdown",
        "Link a claim to its evidence",
    ):
        assert policy not in description

    # And the capability half is still said, because nothing else says it.
    assert "Copy a permalink verbatim from this result" in description
    assert "building a Slack link from parts" in description


def test_the_digest_policy_survives_where_the_task_lives() -> None:
    """Deleted from the card only because the skill already said all of it.

    Pinned so that a later trim of the skill cannot quietly drop a rule that no
    longer has a second home.
    """
    skill = (
        Path(__file__).resolve().parents[3]
        / "local_skills"
        / "slack-channel-digest"
        / "SKILL.md"
    ).read_text()

    assert "Write the digest yourself, in Markdown" in skill
    assert "Link every claim to its evidence" in skill
    assert "Never assemble a Slack link from a channel ID and a timestamp" in skill


def test_the_digest_skill_calls_the_tool_by_the_name_the_card_declares() -> None:
    """A renamed tool and a skill that still calls the old name fail silently.

    ``slack-channel-digest`` names the tool in prose, which no import resolves
    and no type checker sees. Renaming the tool leaves the skill asking for a
    tool that is not mounted -- and the failure surfaces as a model improvising
    around a missing tool on the next cron run, not as anything red.

    Read off the card rather than compared to a literal, so that the next rename
    fails here instead of shipping.
    """
    toolkit = SlackHistoryToolkit(metadata={"slack_channel_id": "C1"}, client=_FakeClient({}))
    name = toolkit.get_tools()[0]._card.name
    skill = (
        Path(__file__).resolve().parents[3]
        / "local_skills"
        / "slack-channel-digest"
        / "SKILL.md"
    ).read_text()

    assert f"`{name}`" in skill, f"the digest skill does not call {name}"
    # The argument travels with the name: a skill that passes the old spelling
    # would have it ignored rather than refused, and silently read the wrong
    # conversation is the one outcome this whole gate exists to prevent.
    assert "channel_id" not in skill


@pytest.mark.asyncio
async def test_rejects_multipart_direct_message_context() -> None:
    client = _FakeClient({})
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "G1",
            "slack_channel_type": "mpim",
            "slack_history_policy": "origin",
        },
        client=client,
    )

    result = json.loads(await toolkit.read_slack_conversation())

    assert result["ok"] is False
    assert result["error"] == "trusted_slack_channel_context_required"
    assert not client.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", [float("nan"), float("inf"), float("-inf")])
async def test_rejects_non_finite_hours(hours: float) -> None:
    client = _FakeClient({})

    result = json.loads(
        await _toolkit(client).read_slack_conversation(hours=hours)
    )

    assert result == {
        "ok": False,
        "error": "hours_must_be_finite",
        "messages": [],
    }
    assert not client.calls


@pytest.mark.asyncio
async def test_client_receives_token_only_from_resolved_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [{"messages": []}],
        }
    )
    captured: dict[str, str] = {}

    def client_factory(*, token: str) -> _FakeClient:
        captured["token"] = token
        return client

    monkeypatch.setattr(slack_history, "AsyncWebClient", client_factory)
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C1",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        now=lambda: 200_000.0,
        max_user_lookups=0,
    )

    result = json.loads(await toolkit.read_slack_conversation())

    assert result["ok"] is True
    assert captured == {"token": "xoxb-config-secret"}
    assert "xoxb-config-secret" not in json.dumps(result)


@pytest.mark.asyncio
async def test_undocumented_history_limit_config_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda: {
            "channels": {
                "slack": {
                    "bot_token": "xoxb-config-secret",
                    "history_digest_max_messages": 1,
                    "history_digest_max_api_calls": 1,
                }
            }
        },
    )
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [
                {
                    "messages": [
                        {"ts": "199999.0", "user": "U1", "text": "first"},
                        {"ts": "199998.0", "user": "U2", "text": "second"},
                    ]
                }
            ],
        }
    )

    result = json.loads(await _toolkit(client).read_slack_conversation())

    assert result["ok"] is True
    assert result["coverage"]["status"] == "complete"
    assert result["coverage"]["messages_returned"] == 2
    assert result["coverage"]["api_calls"] == 2


@pytest.mark.asyncio
async def test_metadata_provider_isolates_concurrent_channel_requests() -> None:
    current_metadata: ContextVar[dict[str, Any] | None] = ContextVar(
        "slack_history_test_metadata", default=None
    )
    client = _ConcurrentClient()
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C-FALLBACK",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        metadata_provider=current_metadata.get,
        client=client,
        now=lambda: 200_000.0,
        max_user_lookups=0,
    )

    async def read_channel(channel_id: str) -> dict[str, Any]:
        token = current_metadata.set(
            {
                "slack_channel_id": channel_id,
                "slack_channel_type": "channel",
                "slack_history_policy": "origin",
            }
        )
        try:
            return json.loads(await toolkit.read_slack_conversation())
        finally:
            current_metadata.reset(token)

    first, second = await asyncio.gather(read_channel("C1"), read_channel("C2"))

    assert first["chat_id"] == "C1"
    assert first["messages"][0]["text"] == "from C1"
    assert second["chat_id"] == "C2"
    assert second["messages"][0]["text"] == "from C2"
    assert sorted(client.history_channels) == ["C1", "C2"]


@pytest.mark.asyncio
async def test_scan_deadline_returns_partial_and_keeps_messages_on_name_lookup() -> (
    None
):
    ticks = iter([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 91.0])
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [
                {"messages": [{"ts": "199999.0", "user": "U1", "text": "hi"}]}
            ],
            "users_info": [
                {
                    "user": {
                        "id": "U1",
                        "profile": {"display_name": "Alice"},
                    }
                }
            ],
        }
    )
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C1",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        client=client,
        now=lambda: 200_000.0,
        monotonic=lambda: next(ticks, 91.0),
        scan_timeout_seconds=90,
        max_user_lookups=10,
    )

    result = json.loads(await toolkit.read_slack_conversation())

    assert result["ok"] is True
    assert result["coverage"]["status"] == "partial"
    assert "scan_time_limit" in result["coverage"]["partial_reasons"]
    assert result["messages"][0]["author_user_id"] == "U1"
    assert result["messages"][0]["author_name"] == "U1"


@pytest.mark.asyncio
async def test_paginates_roots_and_includes_recent_reply_to_old_root() -> None:
    client = _FakeClient(
        {
            "auth_test": [
                {
                    "ok": True,
                    "user_id": "U-BOT",
                    "bot_id": "B-BOT",
                    "url": "https://example.slack.com/",
                }
            ],
            "conversations_history": [
                {
                    "ok": True,
                    "messages": [
                        {
                            "ts": "190000.000000",
                            "user": "U1",
                            "text": "old design discussion",
                            "reply_count": 1,
                            "latest_reply": "199000.000000",
                        },
                        {
                            "ts": "198500.000000",
                            "user": "U-BOT",
                            "bot_id": "B-BOT",
                            "text": "Received. Analyzing…",
                        },
                    ],
                    "response_metadata": {"next_cursor": "page-2"},
                },
                {
                    "ok": True,
                    "messages": [
                        {
                            "ts": "198000.000000",
                            "user": "U2",
                            "text": "new root",
                        }
                    ],
                    "response_metadata": {"next_cursor": ""},
                },
            ],
            "conversations_replies": [
                {
                    "ok": True,
                    "messages": [
                        {
                            "ts": "190000.000000",
                            "user": "U1",
                            "text": "old design discussion",
                        },
                        {
                            "ts": "195000.000000",
                            "thread_ts": "190000.000000",
                            "user": "U3",
                            "text": "old reply outside the window",
                        },
                        {
                            "ts": "199000.000000",
                            "thread_ts": "190000.000000",
                            "user": "U2",
                            "text": "decision made",
                        },
                    ],
                    "response_metadata": {"next_cursor": ""},
                }
            ],
        }
    )

    result = json.loads(
        await _toolkit(client).read_slack_conversation(hours=1)
    )

    assert result["ok"] is True
    assert result["coverage"]["status"] == "complete"
    assert result["coverage"]["scope_note"].startswith(
        "Coverage describes Slack-accessible history"
    )
    assert result["window"]["cutoff_iso_utc"] == "1970-01-03T06:33:20Z"
    assert result["window"]["snapshot_iso_utc"] == "1970-01-03T07:33:20Z"
    assert result["coverage"]["history_pages"] == 2
    assert result["coverage"]["thread_pages"] == 1
    assert [message["ts"] for message in result["messages"]] == [
        "190000.000000",
        "198000.000000",
        "198500.000000",
        "199000.000000",
    ]
    assert result["messages"][0]["outside_window_context"] is True
    assert result["messages"][2]["is_own_bot_message"] is True
    assert result["messages"][3]["is_thread_reply"] is True
    assert result["messages"][3]["is_own_bot_message"] is False
    assert result["coverage"]["context_root_messages_returned"] == 1
    assert result["coverage"]["threads_returned"] == 1
    assert "thread_ts=190000.000000" in result["messages"][3]["permalink"]
    assert result["messages"][0]["source_mrkdwn"] == (
        f"<{result['messages'][0]['permalink']}|source>"
    )
    assert result["messages"][3]["source_mrkdwn"] == (
        "<https://example.slack.com/archives/C-RESEARCH/p199000000000"
        "?thread_ts=190000.000000&cid=C-RESEARCH|source>"
    )
    assert client.calls["conversations_history"][1]["cursor"] == "page-2"
    # Windowed thread scans intentionally omit `oldest` from root history so
    # older roots with recent replies remain discoverable.
    assert "oldest" not in client.calls["conversations_history"][0]
    # Slack can omit valid replies when conversations.replies receives a
    # non-zero `oldest`; replies are fetched without it and filtered locally.
    assert "oldest" not in client.calls["conversations_replies"][0]


@pytest.mark.asyncio
async def test_reports_partial_when_expected_thread_replies_are_not_returned() -> None:
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [
                {
                    "messages": [
                        {
                            "ts": "198000.0",
                            "user": "U1",
                            "text": "design proposal",
                            "reply_count": 4,
                            "latest_reply": "199500.0",
                        }
                    ]
                }
            ],
            # Some Slack responses contain only the root even though history
            # metadata declares replies. Coverage must not be called complete.
            "conversations_replies": [
                {
                    "messages": [
                        {
                            "ts": "198000.0",
                            "user": "U1",
                            "text": "design proposal",
                        }
                    ]
                }
            ],
        }
    )

    result = json.loads(await _toolkit(client).read_slack_conversation())

    assert result["coverage"]["status"] == "partial"
    assert "thread_replies_not_returned" in result["coverage"]["partial_reasons"]
    assert result["coverage"]["thread_replies_returned"] == 0
    assert result["coverage"]["threads_returned"] == 0


@pytest.mark.asyncio
async def test_preserves_bot_root_and_replies_and_deduplicates_pages() -> None:
    client = _FakeClient(
        {
            "auth_test": [
                {
                    "user_id": "U-BOT",
                    "bot_id": "B-BOT",
                    "url": "https://x.slack.com",
                }
            ],
            "conversations_history": [
                {
                    "messages": [
                        {
                            "ts": "198000.0",
                            "user": "U-BOT",
                            "bot_id": "B-BOT",
                            "text": "substantive bot analysis",
                            "reply_count": 3,
                            "latest_reply": "199500.0",
                        }
                    ]
                }
            ],
            "conversations_replies": [
                {
                    "messages": [
                        {
                            "ts": "198000.0",
                            "user": "U-BOT",
                            "bot_id": "B-BOT",
                            "text": "substantive bot analysis",
                        },
                        {
                            "ts": "199000.0",
                            "user": "U2",
                            "text": "useful",
                        },
                        {
                            "ts": "199100.0",
                            "user": "U-BOT",
                            "text": "generated output",
                        },
                    ],
                    "response_metadata": {"next_cursor": "more"},
                },
                {
                    "messages": [
                        {
                            "ts": "199000.0",
                            "user": "U2",
                            "text": "useful duplicate",
                        },
                        {"ts": "199500.0", "user": "U3", "text": "follow-up"},
                    ]
                },
            ],
        }
    )

    result = json.loads(await _toolkit(client).read_slack_conversation())

    assert [message["ts"] for message in result["messages"]] == [
        "198000.0",
        "199000.0",
        "199100.0",
        "199500.0",
    ]
    assert result["messages"][0]["is_own_bot_message"] is True
    assert result["messages"][1]["is_own_bot_message"] is False
    assert result["messages"][2]["is_own_bot_message"] is True
    assert result["messages"][3]["is_own_bot_message"] is False
    assert client.calls["conversations_replies"][1]["cursor"] == "more"


@pytest.mark.asyncio
async def test_retries_429_using_retry_after() -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    rate_limited = _FakeSlackError(
        _FakeResponse(
            status_code=429,
            data={"ok": False, "error": "ratelimited"},
            headers={"Retry-After": "2"},
        )
    )
    client = _FakeClient(
        {
            "auth_test": [rate_limited, {"user_id": "U-BOT"}],
            "conversations_history": [{"messages": []}],
        }
    )
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C1",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        client=client,
        sleep=fake_sleep,
        now=lambda: 200_000.0,
        max_user_lookups=0,
    )

    result = json.loads(await toolkit.read_slack_conversation())

    assert result["ok"] is True
    assert sleeps == [2.0]
    assert len(client.calls["auth_test"]) == 2


@pytest.mark.asyncio
async def test_redacts_secrets_and_reports_partial_size_limit() -> None:
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [
                {
                    "messages": [
                        {
                            "ts": "199999.0",
                            "user": "U1",
                            "text": (
                                "token=xoxb-config-secret "
                                "Authorization: Bearer abcdefghijklmnop "
                                "OPENAI_API_KEY=top-secret "
                                "DATABASE_PASSWORD=hunter2 "
                                "OAUTH_CLIENT_SECRET=client-value "
                                "SIGNING_PRIVATE_KEY=private-value "
                                "ALT_SLACK_TOKEN=xoxc-alternate-secret"
                            ),
                        },
                        {"ts": "199998.0", "user": "U2", "text": "second"},
                    ]
                }
            ],
        }
    )

    result = json.loads(
        await _toolkit(client, max_messages=1).read_slack_conversation()
    )
    serialized = json.dumps(result)

    assert result["coverage"]["status"] == "partial"
    assert "message_limit" in result["coverage"]["partial_reasons"]
    assert result["coverage"]["redacted_count"] >= 7
    assert "xoxb-config-secret" not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert "top-secret" not in serialized
    assert "hunter2" not in serialized
    assert "client-value" not in serialized
    assert "private-value" not in serialized
    assert "xoxc-alternate-secret" not in serialized


@pytest.mark.asyncio
async def test_users_read_failure_falls_back_to_user_ids() -> None:
    missing_scope = _FakeSlackError(
        _FakeResponse(
            status_code=200,
            data={"ok": False, "error": "missing_scope"},
        )
    )
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [
                {"messages": [{"ts": "199999.0", "user": "U1", "text": "hi"}]}
            ],
            "users_info": [missing_scope],
        }
    )
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C1",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        client=client,
        now=lambda: 200_000.0,
        max_user_lookups=10,
    )

    result = json.loads(await toolkit.read_slack_conversation())

    assert result["messages"][0]["author_name"] == "U1"
    assert "users_read_scope_unavailable_using_ids" in result["coverage"]["warnings"]


@pytest.mark.asyncio
async def test_every_name_lookup_warning_is_keyed_on_the_field_it_is_about() -> None:
    """One concept, one word, including in the warnings.

    The three codes below said ``user_name`` while the field they describe is
    ``author_name``. Left alone they would have rebuilt the collision the rename
    removed, one remove away: a reader told ``user_name_lookup_limit`` about a
    snapshot with no ``user_name`` in it has to work out that the two are the
    same thing.

    ``users_read_scope_unavailable_using_ids`` deliberately keeps Slack's word.
    ``users:read`` is Slack's scope, and an operator sent looking for
    ``authors:read`` would find nothing.
    """
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [
                {
                    "messages": [
                        {"ts": "199999.0", "user": "U1", "text": "one"},
                        {"ts": "199998.0", "user": "U2", "text": "two"},
                    ]
                }
            ],
            "users_info": [{"user": {"name": "alice"}}],
        }
    )
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C1",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        client=client,
        now=lambda: 200_000.0,
        # Two distinct authors, one lookup allowed: the cap is reported rather
        # than silently applied.
        max_user_lookups=1,
    )

    warnings = json.loads(await toolkit.read_slack_conversation())["coverage"]["warnings"]

    assert "author_name_lookup_limit" in warnings
    assert not [word for word in warnings if word.startswith("user_name")]


@pytest.mark.asyncio
async def test_a_name_lookup_stopped_by_the_call_budget_says_so_as_author_name() -> None:
    """The other half of the same vocabulary, on the other reason it stops."""
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [
                {"messages": [{"ts": "199999.0", "user": "U1", "text": "one"}]}
            ],
            "users_info": [],
        }
    )
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C1",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        client=client,
        now=lambda: 200_000.0,
        # auth.test and conversations.history spend the budget, so the name
        # lookup never gets a call of its own.
        max_api_calls=2,
        max_user_lookups=10,
    )

    warnings = json.loads(await toolkit.read_slack_conversation())["coverage"]["warnings"]

    assert "author_names_not_resolved_api_limit" in warnings
    assert not [word for word in warnings if word.startswith("user_name")]


def _app_post(ts: str, display_name: str, text: str) -> dict[str, Any]:
    """Build a message shaped like the one Slack sends for an app-posted message.

    An app post carries no ``user``: the account fields are replaced by
    ``bot_id``, the name the app posted under in ``username``, and the
    installed app's own profile.
    """
    return {
        "ts": ts,
        "subtype": "bot_message",
        "bot_id": "B0BUILDBOT",
        "username": display_name,
        "bot_profile": {
            "id": "B0BUILDBOT",
            "name": display_name,
            "app_id": "A0BUILDBOT",
        },
        "text": text,
    }


@pytest.mark.asyncio
async def test_app_display_name_is_never_looked_up_as_a_user_id() -> None:
    """A display name is a label, so users.info must never be asked for one.

    ``users.info`` answers an unknown identifier with ``user_not_found``, which
    costs a lookup out of the configured budget, can crowd real accounts out of
    it, and reports a failure that never had a cause.
    """
    user_not_found = _FakeSlackError(
        _FakeResponse(
            status_code=200,
            data={"ok": False, "error": "user_not_found"},
        )
    )
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT", "bot_id": "B-BOT"}],
            "conversations_history": [
                {
                    "messages": [
                        _app_post("199999.0", "Uptime Robot", "deploy finished"),
                        {"ts": "199998.0", "user": "U1", "text": "thanks"},
                    ]
                }
            ],
            "users_info": [
                {"user": {"id": "U1", "profile": {"display_name": "Alice"}}},
                user_not_found,
            ],
        }
    )
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C1",
            "slack_channel_type": "channel",
            "slack_history_policy": "origin",
        },
        client=client,
        now=lambda: 200_000.0,
        max_user_lookups=10,
    )

    result = json.loads(await toolkit.read_slack_conversation())

    app_post = result["messages"][1]
    assert app_post["ts"] == "199999.0"
    assert app_post["author_user_id"] == ""
    assert app_post["author_name"] == "Uptime Robot"
    assert result["messages"][0]["author_name"] == "Alice"
    assert [call["user"] for call in client.calls["users_info"]] == ["U1"]
    assert "author_name_lookup_failed" not in result["coverage"]["warnings"]


@pytest.mark.asyncio
async def test_app_display_name_is_redacted_like_message_text() -> None:
    """The name an app posts under is author-supplied text on the same footing."""
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT", "bot_id": "B-BOT"}],
            "conversations_history": [
                {
                    "messages": [
                        _app_post("199999.0", "deploy xoxb-leaked-secret", "done")
                    ]
                }
            ],
        }
    )

    result = json.loads(
        await _toolkit(client).read_slack_conversation(include_threads=False)
    )

    assert "xoxb-leaked-secret" not in json.dumps(result)
    assert result["messages"][0]["author_name"] == "deploy [REDACTED_SLACK_TOKEN]"
    assert result["coverage"]["redacted_count"] >= 1
    assert "sensitive_values_redacted" in result["coverage"]["warnings"]


@pytest.mark.asyncio
async def test_without_threads_uses_server_side_time_filter() -> None:
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [{"messages": []}],
        }
    )

    result = json.loads(
        await _toolkit(client).read_slack_conversation(
            hours=2, include_threads=False
        )
    )

    assert result["coverage"]["status"] == "complete"
    assert client.calls["conversations_history"][0]["oldest"] == "192800.0"
    assert not client.calls["conversations_replies"]


@pytest.mark.asyncio
async def test_messages_and_coverage_carry_human_readable_utc_dates() -> None:
    """Regression: a model reported a message four days after it was sent.

    ts is a Slack identifier that merely looks like a Unix epoch. The payload used
    to expose it raw with no readable equivalent, leaving the model to do the
    conversion itself, which it got wrong by four days. The pair below is five
    days apart, which is what the conversion has to keep.
    """
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [
                {
                    "messages": [
                        {"ts": "1712777678.062809", "user": "U1", "text": "latest"},
                        {"ts": "1712345678.188269", "user": "U1", "text": "earliest"},
                    ]
                }
            ],
        }
    )

    result = json.loads(
        await SlackHistoryToolkit(
            metadata={
                "slack_channel_id": "D0DIRECT01",
                "slack_channel_type": "im",
                "slack_history_policy": "origin",
            },
            client=client,
            now=lambda: 1_712_777_800.0,
            max_user_lookups=0,
        ).read_slack_conversation(all_history=True, include_threads=False)
    )

    by_ts = {message["ts"]: message for message in result["messages"]}
    assert by_ts["1712345678.188269"]["ts_iso_utc"] == "2024-04-05T19:34:38.188269Z"
    assert by_ts["1712777678.062809"]["ts_iso_utc"] == "2024-04-10T19:34:38.062809Z"

    coverage = result["coverage"]
    # The raw identifiers stay untouched: source_ids and the renderer depend on them.
    assert coverage["earliest_message_ts"] == "1712345678.188269"
    assert coverage["earliest_message_iso_utc"].startswith("2024-04-05T19:34:38")
    assert coverage["latest_message_iso_utc"].startswith("2024-04-10T19:34:38")


def _slack_file(
    file_id: str,
    name: str,
    mimetype: str,
    size: int,
    **extra: Any,
) -> dict[str, Any]:
    """Build a file object shaped like the ones Slack embeds in a message.

    Slack repeats the name in the title and serves the bytes from url_private;
    both are reproduced here so the tests exercise what a real payload carries
    rather than a convenient subset of it.
    """
    return {
        "id": file_id,
        "name": name,
        "title": name,
        "mimetype": mimetype,
        "filetype": mimetype.split("/")[-1],
        "size": size,
        "url_private": f"https://files.slack.com/files-pri/T1-{file_id}/{name}",
        "url_private_download": (
            f"https://files.slack.com/files-pri/T1-{file_id}/download/{name}"
        ),
        "permalink": f"https://example.slack.com/files/U1/{file_id}/{name}",
        **extra,
    }


async def _history_with(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT", "url": "https://example.slack.com/"}],
            "conversations_history": [{"messages": messages}],
        }
    )
    return json.loads(
        await _toolkit(client, **kwargs).read_slack_conversation(
            include_threads=False
        )
    )


@pytest.mark.asyncio
async def test_message_with_one_file_carries_the_attachment() -> None:
    result = await _history_with(
        [
            {
                "ts": "199999.0",
                "user": "U1",
                "subtype": "file_share",
                "text": "What is this file? Can you summarize it?",
                "files": [
                    _slack_file(
                        "F0FILE0001", "paper.pdf", "application/pdf", 2_215_244
                    )
                ],
            }
        ]
    )

    message = result["messages"][0]
    assert message["text"] == "What is this file? Can you summarize it?"
    assert message["files"] == [
        {
            "name": "paper.pdf",
            "id": "F0FILE0001",
            "mimetype": "application/pdf",
            "permalink": "https://example.slack.com/files/U1/F0FILE0001/paper.pdf",
            "size_bytes": 2_215_244,
        }
    ]
    # The title repeats the name, so it earns no field of its own.
    assert "title" not in message["files"][0]
    assert "files_truncated" not in message


@pytest.mark.asyncio
async def test_file_only_message_is_not_an_empty_event() -> None:
    """A bare upload carries no comment, and used to normalize to nothing."""
    result = await _history_with(
        [
            {
                "ts": "199998.0",
                "user": "U1",
                "subtype": "file_share",
                "text": "",
                "files": [
                    _slack_file(
                        "F0FILE0002", "screenshot.jpg", "image/jpeg", 1_380_602
                    )
                ],
            }
        ]
    )

    assert result["coverage"]["messages_returned"] == 1
    message = result["messages"][0]
    assert message["text"] == ""
    assert [entry["name"] for entry in message["files"]] == ["screenshot.jpg"]
    assert message["files"][0]["mimetype"] == "image/jpeg"


@pytest.mark.asyncio
async def test_message_with_several_files_keeps_every_attachment() -> None:
    result = await _history_with(
        [
            {
                "ts": "199997.0",
                "user": "U1",
                "subtype": "file_share",
                "text": "the batch",
                "files": [
                    _slack_file("F0FILE0004", "one.jpg", "image/jpeg", 1_147_660),
                    _slack_file("F0FILE0005", "two.jpg", "image/jpeg", 1_637_190),
                    _slack_file("F0FILE0003", "notes.txt", "text/plain", 2_629),
                ],
            }
        ]
    )

    files = result["messages"][0]["files"]
    assert [entry["name"] for entry in files] == ["one.jpg", "two.jpg", "notes.txt"]
    assert [entry["size_bytes"] for entry in files] == [1_147_660, 1_637_190, 2_629]


@pytest.mark.asyncio
async def test_attachments_beyond_the_cap_are_reported_not_dropped_silently() -> None:
    result = await _history_with(
        [
            {
                "ts": "199996.0",
                "user": "U1",
                "subtype": "file_share",
                "text": "",
                "files": [
                    _slack_file(f"F{index:010d}", f"file-{index}.txt", "text/plain", 10)
                    for index in range(slack_history._MAX_FILES_PER_MESSAGE + 3)
                ],
            }
        ]
    )

    message = result["messages"][0]
    assert len(message["files"]) == slack_history._MAX_FILES_PER_MESSAGE
    assert message["files_truncated"] is True


@pytest.mark.asyncio
async def test_message_without_files_is_unchanged() -> None:
    result = await _history_with(
        [{"ts": "199995.0", "user": "U1", "text": "just words"}]
    )

    message = result["messages"][0]
    assert message["text"] == "just words"
    assert "files" not in message
    assert "files_truncated" not in message


@pytest.mark.asyncio
async def test_attachment_never_exposes_the_authenticated_download_url() -> None:
    """url_private needs a bearer token, so it would read as a link to nothing."""
    result = await _history_with(
        [
            {
                "ts": "199994.0",
                "user": "U1",
                "subtype": "file_share",
                "text": "",
                "files": [_slack_file("F0FILE0003", "notes.txt", "text/plain", 2_629)],
            }
        ]
    )

    entry = result["messages"][0]["files"][0]
    assert entry["permalink"].startswith("https://example.slack.com/files/")
    assert "url_private" not in entry
    assert "files.slack.com" not in json.dumps(result)


@pytest.mark.asyncio
async def test_bot_uploaded_file_is_still_attributed_to_the_bot() -> None:
    """Slack announces a bot token upload as a file_share by the bot user."""
    result = await _history_with(
        [
            {
                "ts": "199993.0",
                "user": "U-BOT",
                "subtype": "file_share",
                "text": "",
                "files": [_slack_file("F0FILE0004", "report.csv", "text/csv", 4_096)],
            }
        ]
    )

    message = result["messages"][0]
    assert message["is_own_bot_message"] is True
    assert message["files"][0]["name"] == "report.csv"


@pytest.mark.asyncio
async def test_attachment_labels_are_redacted_and_fall_back_when_unnamed() -> None:
    result = await _history_with(
        [
            {
                "ts": "199992.0",
                "user": "U1",
                "subtype": "file_share",
                "text": "",
                "files": [
                    _slack_file(
                        "F0FILE0005",
                        "xoxb-1234567890-abcdefghij.env",
                        "text/plain",
                        128,
                    ),
                    {"id": "F0FILE0002", "name": None, "title": "Untitled dump"},
                    "not a file object",
                ],
            }
        ]
    )

    files = result["messages"][0]["files"]
    assert files[0]["name"] == "[REDACTED_SLACK_TOKEN].env"
    assert "xoxb-" not in json.dumps(result)
    assert result["coverage"]["redacted_count"] >= 1
    # A missing name falls back to the title rather than leaving the entry blank.
    assert files[1]["name"] == "Untitled dump"
    assert "title" not in files[1]
    assert "size_bytes" not in files[1]
    # A malformed entry is skipped instead of failing the scan.
    assert len(files) == 2


@pytest.mark.asyncio
async def test_attachments_are_charged_to_the_total_character_budget() -> None:
    """A window of file shares must not report a size the budget does not bound."""
    result = await _history_with(
        [
            {
                "ts": f"1999{index:02d}.0",
                "user": "U1",
                "subtype": "file_share",
                "text": "",
                "files": [
                    _slack_file(
                        f"F{index:010d}",
                        f"attachment-{index}.pdf",
                        "application/pdf",
                        1,
                    )
                ],
            }
            for index in range(40, 90)
        ],
        max_total_chars=1_000,
    )

    coverage = result["coverage"]
    assert coverage["status"] == "partial"
    assert "total_character_limit" in coverage["partial_reasons"]
    # Text alone is empty everywhere, so only the attachments can have stopped it.
    assert all(message["text"] == "" for message in result["messages"])
    assert coverage["messages_returned"] < 50


@pytest.mark.asyncio
async def test_reactions_are_charged_to_the_total_character_budget() -> None:
    """Reaction names are unbounded workspace text and must be charged too."""
    result = await _history_with(
        [
            {
                "ts": f"1999{index:02d}.0",
                "user": "U1",
                "text": "",
                "reactions": [
                    {
                        "name": f"custom-workspace-emoji-{index}-{slot}",
                        "users": ["U1", "U2"],
                        "count": 2,
                    }
                    for slot in range(20)
                ],
            }
            for index in range(40, 90)
        ],
        max_total_chars=1_000,
    )

    coverage = result["coverage"]
    assert coverage["status"] == "partial"
    assert "total_character_limit" in coverage["partial_reasons"]
    # Text alone is empty everywhere, so only the reactions can have stopped it.
    assert all(message["text"] == "" for message in result["messages"])
    assert coverage["messages_returned"] < 50
    # The records still carry the reactions they were charged for.
    assert len(result["messages"][0]["reactions"]) == 20


@pytest.mark.asyncio
async def test_empty_history_reports_null_iso_dates() -> None:
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [{"messages": []}],
        }
    )

    result = json.loads(
        await _toolkit(client).read_slack_conversation(include_threads=False)
    )

    assert result["coverage"]["earliest_message_iso_utc"] is None
    assert result["coverage"]["latest_message_iso_utc"] is None


class _ChannelClient:
    """A Slack stand-in that honours ``latest``, ``inclusive`` and paging.

    The continuation tests assert that two calls tile the channel rather than
    nesting, which is only meaningful against a server that actually applies the
    bounds the tool sends. A fake that replays canned pages would pass whatever
    the tool did.
    """

    def __init__(
        self,
        roots: list[dict[str, Any]],
        replies: dict[str, list[dict[str, Any]]] | None = None,
        page_size: int = 200,
    ) -> None:
        self.roots = sorted(roots, key=lambda item: float(item["ts"]), reverse=True)
        self.replies = replies or {}
        self.page_size = page_size
        self.history_calls: list[dict[str, Any]] = []

    async def auth_test(self, **kwargs: Any) -> dict[str, Any]:
        return {"user_id": "U-BOT", "bot_id": "B-BOT", "url": "https://x.slack.com"}

    async def conversations_history(self, **kwargs: Any) -> dict[str, Any]:
        self.history_calls.append(dict(kwargs))
        latest = float(kwargs["latest"])
        inclusive = bool(kwargs.get("inclusive"))
        oldest = float(kwargs["oldest"]) if kwargs.get("oldest") else None
        selected = [
            root
            for root in self.roots
            if (
                float(root["ts"]) <= latest if inclusive else float(root["ts"]) < latest
            )
            and (oldest is None or float(root["ts"]) >= oldest)
        ]
        start = int(kwargs.get("cursor") or 0)
        page = selected[start : start + self.page_size]
        next_start = start + self.page_size
        has_more = next_start < len(selected)
        response: dict[str, Any] = {"messages": page, "has_more": has_more}
        if has_more:
            response["response_metadata"] = {"next_cursor": str(next_start)}
        return response

    async def conversations_replies(self, **kwargs: Any) -> dict[str, Any]:
        root_ts = str(kwargs["ts"])
        thread = [{"ts": root_ts}] + list(self.replies.get(root_ts, []))
        return {"messages": thread, "has_more": False}


def _sample_channel() -> _ChannelClient:
    """Ten roots, one of which carries replies newer than every later root.

    That thread is the shape a message-timestamp cursor cannot express: its
    root is among the oldest in the channel while its replies are the newest
    messages in it, so a slice that stops in the middle of the channel by
    message timestamp would strand them.
    """
    roots = [
        {"ts": f"19990{index}.000000", "user": "U1", "text": f"root {index}"}
        for index in range(10)
    ]
    roots[1] = {
        "ts": "199901.000000",
        "user": "U1",
        "text": "root 1",
        "reply_count": 2,
        "latest_reply": "199951.000000",
    }
    replies = {
        "199901.000000": [
            {"ts": "199950.000000", "user": "U2", "text": "late reply a"},
            {"ts": "199951.000000", "user": "U2", "text": "late reply b"},
        ]
    }
    return _ChannelClient(roots, replies)


async def _slice(
    client: _ChannelClient, **kwargs: Any
) -> tuple[dict[str, Any], list[str]]:
    result = json.loads(
        await _toolkit(client).read_slack_conversation(
            all_history=True, **kwargs
        )
    )
    assert result["ok"] is True
    return result, [str(item["ts"]) for item in result["messages"]]


@pytest.mark.asyncio
async def test_call_without_arguments_keeps_todays_behaviour() -> None:
    client = _sample_channel()

    result, returned = await _slice(client)

    assert len(returned) == 12
    assert result["coverage"]["status"] == "complete"
    assert result["coverage"]["max_messages"] == 2_000
    assert result["coverage"]["next_before_ts"] is None
    assert "resume_note" not in result["coverage"]
    assert result["window"]["before_ts"] is None


@pytest.mark.asyncio
async def test_max_messages_returns_fewer_messages_than_an_unbounded_call() -> None:
    unbounded_result, unbounded = await _slice(_sample_channel())
    bounded_result, bounded = await _slice(_sample_channel(), max_messages=4)

    assert unbounded_result["coverage"]["status"] == "complete"
    assert len(unbounded) == 12
    assert len(bounded) == 4
    assert bounded_result["coverage"]["status"] == "partial"
    assert "message_limit" in bounded_result["coverage"]["partial_reasons"]
    assert bounded_result["coverage"]["max_messages"] == 4
    assert set(bounded).issubset(set(unbounded))


@pytest.mark.asyncio
async def test_partial_result_names_an_exclusive_resume_position() -> None:
    result, returned = await _slice(_sample_channel(), max_messages=4)

    coverage = result["coverage"]
    oldest_root = min(str(item["thread_ts"]) for item in result["messages"])
    assert coverage["next_before_ts"] == oldest_root
    assert coverage["next_before_iso_utc"] is not None
    assert "exclusive" in coverage["resume_note"]
    assert coverage["next_before_ts"] in returned


@pytest.mark.asyncio
async def test_resumed_slices_tile_the_channel_without_overlap_or_gap() -> None:
    _, whole = await _slice(_sample_channel())

    walked: list[str] = []
    before_ts: str | None = None
    for _ in range(10):
        result, returned = await _slice(
            _sample_channel(), max_messages=4, before_ts=before_ts
        )
        walked.extend(returned)
        before_ts = result["coverage"]["next_before_ts"]
        if before_ts is None:
            break

    assert before_ts is None
    assert len(walked) == len(set(walked)), "a slice returned a message twice"
    assert sorted(walked) == sorted(whole), "the walk lost or invented a message"
    # The thread whose replies are the newest messages in the channel arrives
    # with its root, in the last slice, rather than with the newest slice.
    assert {"199950.000000", "199951.000000", "199901.000000"}.issubset(set(walked))


@pytest.mark.asyncio
async def test_resuming_from_the_oldest_message_ends_the_walk() -> None:
    result, returned = await _slice(_sample_channel(), before_ts="199900.000000")

    assert returned == []
    assert result["coverage"]["status"] == "complete"
    assert result["coverage"]["next_before_ts"] is None
    assert result["window"]["before_ts"] == "199900.000000"


@pytest.mark.asyncio
async def test_a_thread_is_returned_whole_even_when_it_busts_the_bound() -> None:
    result, returned = await _slice(
        _sample_channel(), max_messages=2, before_ts="199902.000000"
    )

    # The thread is three messages against a bound of two. Splitting it would
    # strand the replies above any later resume position, so it comes back whole.
    assert sorted(returned) == ["199901.000000", "199950.000000", "199951.000000"]
    assert "thread_exceeded_requested_bounds" in result["coverage"]["warnings"]
    assert result["coverage"]["next_before_ts"] == "199901.000000"


@pytest.mark.asyncio
async def test_before_ts_that_is_not_a_slack_timestamp_is_refused() -> None:
    toolkit = _toolkit(_sample_channel())

    result = json.loads(
        await toolkit.read_slack_conversation(before_ts="yesterday")
    )

    assert result["ok"] is False
    assert result["error"] == "before_ts_must_be_a_slack_timestamp"
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_configured_bound_caps_a_call_that_asks_for_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda: {
            "channels": {
                "slack": {
                    "bot_token": "xoxb-config-secret",
                    "history_max_messages": 3,
                }
            }
        },
    )

    result, returned = await _slice(_sample_channel())

    assert len(returned) == 3
    assert result["coverage"]["max_messages"] == 3
    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["next_before_ts"] is not None


@pytest.mark.asyncio
async def test_a_caller_cannot_ask_for_more_than_the_deployment_allows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda: {
            "channels": {
                "slack": {
                    "bot_token": "xoxb-config-secret",
                    "history_max_messages": 3,
                }
            }
        },
    )

    result, returned = await _slice(_sample_channel(), max_messages=500)

    assert len(returned) == 3
    assert result["coverage"]["max_messages"] == 3


# ---------------------------------------------------------------------------
# The redaction pass, which two tools run and only one defines.
#
# ``slack_search`` already imported the regexes by name because they are
# security-critical and a fix to one copy would not reach a second. The pass
# driving them was copied rather than imported, which left exactly the gap the
# import was reasoned about to close. These tests are on the shared function and
# on the one property the two callers do not share.
# ---------------------------------------------------------------------------


def test_both_slack_tools_run_the_same_redaction_pass() -> None:
    """One function, named from both, rather than two that happen to agree."""
    from jiuwenswarm.agents.harness.common.tools import slack_search

    assert slack_search.redact_credentials is slack_history.redact_credentials


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("run xoxb-11-22-abcdef with it", "run [REDACTED_SLACK_TOKEN] with it"),
        ("Bearer abcdefghijkl", "Bearer [REDACTED]"),
        ("api_key=hunter2hunter2", "api_key=[REDACTED]"),
    ],
)
def test_every_credential_shape_is_masked(value: str, expected: str) -> None:
    text, redacted, truncated = slack_history.redact_credentials(value)

    assert text == expected
    assert redacted == 1
    assert truncated is False


def test_the_known_token_is_masked_by_literal_match_before_the_patterns() -> None:
    """The one credential known exactly rather than by shape.

    Masked first, so a token no pattern happens to match is gone anyway.
    """
    text, redacted, _ = slack_history.redact_credentials(
        "token is s3cr3t-not-a-slack-shape", bot_token="s3cr3t-not-a-slack-shape"
    )

    assert text == "token is [REDACTED]"
    assert redacted == 1


def test_a_cap_cuts_and_says_it_cut() -> None:
    text, _redacted, truncated = slack_history.redact_credentials("y" * 40, cap=10)

    assert truncated is True
    assert len(text) == 10
    assert text.endswith("…")


def test_no_cap_means_uncapped_rather_than_a_cap_of_zero() -> None:
    """``None`` is what the search tool passes for a permalink.

    A locator that has been shortened is not a locator, so this is the one
    difference between the two callers and the whole reason the cap is a
    parameter rather than a constant.
    """
    link = "https://example.slack.com/archives/C1/p" + "9" * 400

    text, _redacted, truncated = slack_history.redact_credentials(link)

    assert text == link
    assert truncated is False
