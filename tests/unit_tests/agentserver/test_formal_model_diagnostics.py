"""Passive model seam oracles; no external model calls or prompt logging."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.runtime.agent_adapter import formal_model_diagnostics as diag


def envelope(answer="PRIVATE_PREVIOUS_ANSWER"):
    return json.dumps(
        {
            "selected_context": [
                {
                    "context_ref": {"source": "live_voice.cr_presented_assistant"},
                    "content": answer,
                }
            ],
            "committed_turn": {"text": "PRIVATE_CURRENT_QUESTION"},
        }
    )


class Client:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def invoke(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(content="PRIVATE_PREVIOUS_ANSWER")

    async def stream(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        try:
            for part in ["PRIVATE_", "PREVIOUS_ANSWER"]:
                yield SimpleNamespace(content=part)
        finally:
            self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False])
async def test_exact_model_boundary_and_history_repeat_without_content(
    monkeypatch, streaming
):
    records = []
    monkeypatch.setattr(
        diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f))
    )
    client = Client()
    wrapped = diag.FormalModelDiagnostics(
        client, envelope=envelope(), request_id="request-a", session_id="session-a"
    )
    messages = [
        {"role": "system", "content": "PRIVATE_SYSTEM"},
        {"role": "user", "content": envelope()},
    ]
    kwargs = {
        "messages": messages,
        "tools": [{"secret": "PRIVATE_TOOL"}],
        "temperature": 0.95,
    }
    if streaming:
        assert (
            "".join([c.content async for c in wrapped.stream(**kwargs)])
            == "PRIVATE_PREVIOUS_ANSWER"
        )
        assert client.closed
    else:
        assert (await wrapped.invoke(**kwargs)).content == "PRIVATE_PREVIOUS_ANSWER"
    assert client.calls == [((), kwargs)]
    assert client.calls[0][1]["messages"] is messages
    request, result = records
    assert request[1]["current_envelope_count"] == 1
    assert request[1]["current_envelope_in_last_user"] is True
    assert result[1]["repeats_selected_assistant"] is True
    assert result[1]["outcome"] == "complete"
    assert "PRIVATE_" not in repr(records)


@pytest.mark.asyncio
async def test_missing_and_non_last_current_input_are_distinguished(monkeypatch):
    records = []
    monkeypatch.setattr(
        diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f))
    )
    wrapped = diag.FormalModelDiagnostics(
        Client(), envelope=envelope(), request_id="a", session_id="a"
    )
    await wrapped.invoke(messages=[{"role": "user", "content": "old question"}])
    await wrapped.invoke(
        messages=[
            {"role": "user", "content": envelope()},
            {"role": "user", "content": "subsequent framework input"},
        ]
    )
    requests = [f for e, f in records if e == "formal_model_request"]
    assert [f["current_envelope_count"] for f in requests] == [0, 1]
    assert all(f["current_envelope_in_last_user"] is False for f in requests)


@pytest.mark.asyncio
async def test_observation_bounds_do_not_bound_model_calls_and_sink_failure_is_passive(
    monkeypatch,
):
    records = []
    monkeypatch.setattr(
        diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f))
    )
    client = Client()
    wrapped = diag.FormalModelDiagnostics(
        client, envelope=envelope(), request_id="a", session_id="a"
    )
    for _ in range(20):
        await wrapped.invoke(messages=[])
    assert len(client.calls) == 20 and len(records) == 32

    def fail(*args, **kwargs):
        raise OSError("PRIVATE_SINK")

    monkeypatch.setattr(diag, "record_audio_diagnostic", fail)
    other = diag.FormalModelDiagnostics(
        client, envelope="invalid", request_id="b", session_id="b"
    )
    assert (await other.invoke(messages=[])).content == "PRIVATE_PREVIOUS_ANSWER"


@pytest.mark.asyncio
async def test_cancellation_and_early_close_propagate_and_close_exact_stream(
    monkeypatch,
):
    records = []
    monkeypatch.setattr(
        diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f))
    )
    client = Client()
    wrapped = diag.FormalModelDiagnostics(
        client, envelope=envelope(), request_id="a", session_id="a"
    )
    stream = wrapped.stream(messages=[])
    await anext(stream)
    await stream.aclose()
    assert client.closed and records[-1][1]["outcome"] == "cancelled"

    async def cancel(**kwargs):
        raise asyncio.CancelledError()

    client.invoke = cancel
    with pytest.raises(asyncio.CancelledError):
        await wrapped.invoke(messages=[])
    assert records[-1][1]["outcome"] == "cancelled"


@pytest.mark.asyncio
async def test_concurrent_calls_keep_identity_and_model_instances_isolated(monkeypatch):
    records = []
    monkeypatch.setattr(
        diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f))
    )
    original = SimpleNamespace(_client=Client())
    owned = SimpleNamespace(_client=Client())
    diag.observe_formal_model(
        owned, envelope=envelope(), request_id="a", session_id="a"
    )
    other = diag.FormalModelDiagnostics(
        Client(), envelope=envelope("different"), request_id="b", session_id="b"
    )
    await asyncio.gather(owned._client.invoke(messages=[]), other.invoke(messages=[]))
    assert not original._client.calls
    results = {f["request_id"]: f for e, f in records if e == "formal_model_result"}
    assert results["a"]["repeats_selected_assistant"] is True
    assert results["b"]["repeats_selected_assistant"] is False


@pytest.mark.asyncio
async def test_unsupported_or_oversize_messages_are_unknown_not_complete(monkeypatch):
    records = []
    monkeypatch.setattr(
        diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f))
    )
    wrapped = diag.FormalModelDiagnostics(
        Client(), envelope=envelope(), request_id="a", session_id="a"
    )
    for content in [
        [{"type": "image", "data": "PRIVATE_IMAGE"}],
        "x" * (diag._MAX_TEXT + 1),
    ]:
        await wrapped.invoke(messages=[{"role": "user", "content": content}])
        assert records[-2][1]["diagnostic_complete"] is False
    assert "PRIVATE_IMAGE" not in repr(records)


@pytest.mark.asyncio
async def test_stream_failure_is_not_success_and_is_not_retried(monkeypatch):
    records = []
    monkeypatch.setattr(
        diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f))
    )
    failure = OSError("PRIVATE_NETWORK_ERROR")

    class FailedClient(Client):
        async def stream(self, **kwargs):
            self.calls.append(kwargs)
            yield SimpleNamespace(content="PRIVATE_PARTIAL")
            raise failure

    client = FailedClient()
    wrapped = diag.FormalModelDiagnostics(
        client, envelope=envelope(), request_id="a", session_id="a"
    )
    with pytest.raises(OSError) as caught:
        _ = [chunk async for chunk in wrapped.stream(messages=[])]
    assert caught.value is failure and len(client.calls) == 1
    assert records[-1][1]["outcome"] == "failed"
    assert "PRIVATE_" not in repr(records)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_actual_model_uses_observed_client_without_extra_calls(
    monkeypatch, streaming
):
    from openjiuwen.core.foundation.llm import Model

    records = []
    monkeypatch.setattr(
        diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f))
    )
    # Exercise the installed Model's actual invoke method without constructing
    # credentials or contacting a Provider. Only its transport client is fake.
    model = object.__new__(Model)
    model.model_client_config = None
    model.model_config = None
    client = Client()
    model._client = client
    diag.observe_formal_model(
        model, envelope=envelope(), request_id="a", session_id="a"
    )
    messages = [{"role": "user", "content": envelope()}]
    if streaming:
        result = "".join(
            [chunk.content async for chunk in model.stream(messages, tools=[])]
        )
    else:
        result = (await model.invoke(messages, tools=[])).content
    assert result == "PRIVATE_PREVIOUS_ANSWER" and len(client.calls) == 1
    assert client.calls[0][1]["messages"] is messages
    assert records[0][1]["current_envelope_in_last_user"] is True


@pytest.mark.asyncio
async def test_supported_iterator_without_aclose_is_not_rejected():
    class Iterator:
        def __init__(self):
            self.done = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.done:
                raise StopAsyncIteration
            self.done = True
            return SimpleNamespace(content="ok")

    client = SimpleNamespace(stream=lambda **kwargs: Iterator())
    wrapped = diag.FormalModelDiagnostics(
        client, envelope=envelope(), request_id="a", session_id="a"
    )
    assert [chunk.content async for chunk in wrapped.stream(messages=[])] == ["ok"]
