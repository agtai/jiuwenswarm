# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""Unit tests for the request-scoped Slack history toolkit."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
from collections import defaultdict
from typing import Any

import pytest

from jiuwenswarm.agents.harness.common.tools import slack_history
from jiuwenswarm.agents.harness.common.tools.slack_history import SlackHistoryToolkit


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
        slack_history,
        "get_config",
        lambda: {"channels": {"slack": {"bot_token": "xoxb-config-secret"}}},
    )


def _toolkit(client: _FakeClient, **kwargs: Any) -> SlackHistoryToolkit:
    return SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "C-RESEARCH",
            "slack_channel_type": "channel",
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

    result = json.loads(await toolkit.get_current_slack_channel_history())

    assert result == {
        "ok": False,
        "error": "trusted_slack_channel_context_required",
        "messages": [],
    }
    assert not client.calls
    card = toolkit.get_tools()[0]._card
    assert card.name == "get_current_slack_channel_history"
    assert "channel_id" not in card.input_params["properties"]


@pytest.mark.asyncio
async def test_rejects_multipart_direct_message_context() -> None:
    client = _FakeClient({})
    toolkit = SlackHistoryToolkit(
        metadata={
            "slack_channel_id": "G1",
            "slack_channel_type": "mpim",
        },
        client=client,
    )

    result = json.loads(await toolkit.get_current_slack_channel_history())

    assert result["ok"] is False
    assert result["error"] == "trusted_slack_channel_context_required"
    assert not client.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", [float("nan"), float("inf"), float("-inf")])
async def test_rejects_non_finite_hours(hours: float) -> None:
    client = _FakeClient({})

    result = json.loads(
        await _toolkit(client).get_current_slack_channel_history(hours=hours)
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
        },
        now=lambda: 200_000.0,
        max_user_lookups=0,
    )

    result = json.loads(await toolkit.get_current_slack_channel_history())

    assert result["ok"] is True
    assert captured == {"token": "xoxb-config-secret"}
    assert "xoxb-config-secret" not in json.dumps(result)


@pytest.mark.asyncio
async def test_undocumented_history_limit_config_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        slack_history,
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

    result = json.loads(await _toolkit(client).get_current_slack_channel_history())

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
            }
        )
        try:
            return json.loads(await toolkit.get_current_slack_channel_history())
        finally:
            current_metadata.reset(token)

    first, second = await asyncio.gather(read_channel("C1"), read_channel("C2"))

    assert first["channel_id"] == "C1"
    assert first["messages"][0]["text"] == "from C1"
    assert second["channel_id"] == "C2"
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
        },
        client=client,
        now=lambda: 200_000.0,
        monotonic=lambda: next(ticks, 91.0),
        scan_timeout_seconds=90,
        max_user_lookups=10,
    )

    result = json.loads(await toolkit.get_current_slack_channel_history())

    assert result["ok"] is True
    assert result["coverage"]["status"] == "partial"
    assert "scan_time_limit" in result["coverage"]["partial_reasons"]
    assert result["messages"][0]["user_id"] == "U1"
    assert result["messages"][0]["user_name"] == "U1"


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
        await _toolkit(client).get_current_slack_channel_history(hours=1)
    )

    assert result["ok"] is True
    assert result["coverage"]["status"] == "complete"
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

    result = json.loads(await _toolkit(client).get_current_slack_channel_history())

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

    result = json.loads(await _toolkit(client).get_current_slack_channel_history())

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
        },
        client=client,
        sleep=fake_sleep,
        now=lambda: 200_000.0,
        max_user_lookups=0,
    )

    result = json.loads(await toolkit.get_current_slack_channel_history())

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
        await _toolkit(client, max_messages=1).get_current_slack_channel_history()
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
        },
        client=client,
        now=lambda: 200_000.0,
        max_user_lookups=10,
    )

    result = json.loads(await toolkit.get_current_slack_channel_history())

    assert result["messages"][0]["user_name"] == "U1"
    assert "users_read_scope_unavailable_using_ids" in result["coverage"]["warnings"]


@pytest.mark.asyncio
async def test_without_threads_uses_server_side_time_filter() -> None:
    client = _FakeClient(
        {
            "auth_test": [{"user_id": "U-BOT"}],
            "conversations_history": [{"messages": []}],
        }
    )

    result = json.loads(
        await _toolkit(client).get_current_slack_channel_history(
            hours=2, include_threads=False
        )
    )

    assert result["coverage"]["status"] == "complete"
    assert client.calls["conversations_history"][0]["oldest"] == "192800.0"
    assert not client.calls["conversations_replies"]
