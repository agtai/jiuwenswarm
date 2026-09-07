"""Gateway-only observation validation and reordered refresh regression tests."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.e2a.wire_codec import encode_agent_response_for_wire, parse_agent_server_wire_unary
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.gateway.live_voice.dedicated_media_registration import DedicatedMediaProductRegistry
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import (
    GatewayNativeInteractionRuntimeClient, NativeRuntimeClientError, NATIVE_GATEWAY_DESCRIPTOR_KEY,
)
from jiuwenswarm.server.live_voice.native_business_contract import NATIVE_BUSINESS_CONTRACT_VERSION
from jiuwenswarm.server.live_voice.native_business_observation import NATIVE_BUSINESS_OBSERVATION_VERSION
from tests.unit_tests.gateway.test_native_interaction_runtime_client import (
    FakeAgentClient, activation_payload, business_context_result, BINDING, SCOPE,
)


def observation(*, epoch="a" * 32, sequence=1, read_sequence=1):
    result = business_context_result()
    result.update(kind="business_observation", contract_version=NATIVE_BUSINESS_OBSERVATION_VERSION,
                  cursor={"epoch": epoch, "sequence": sequence, "read_sequence": read_sequence})
    return result


def observed(agent):
    client = GatewayNativeInteractionRuntimeClient(agent, native_model="unchanged-model", timeout_seconds=.2)
    payload = activation_payload()
    payload["result"][NATIVE_GATEWAY_DESCRIPTOR_KEY].update(
        business_contract_version=NATIVE_BUSINESS_CONTRACT_VERSION,
        observation_contract_version=NATIVE_BUSINESS_OBSERVATION_VERSION)
    clean = client.observe_activation_response(payload, routed_session_id=SCOPE.session_id,
        connection_id="connection", request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value)
    activation = client.activation_for(session_id=SCOPE.session_id, interaction_id=BINDING.interaction_id,
                                       connection_id="connection")
    return client, activation, clean


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", [None, "extra", "boolean", "epoch", "large", "version"])
async def test_serialized_observation_is_closed_and_private(defect):
    class Serialized(FakeAgentClient):
        async def send_request(self, envelope):
            response = await super().send_request(envelope)
            return parse_agent_server_wire_unary(json.loads(json.dumps(encode_agent_response_for_wire(
                response, response_id=response.request_id))))
    agent = Serialized()
    client, activation, clean = observed(agent)
    assert NATIVE_GATEWAY_DESCRIPTOR_KEY not in clean["result"]
    assert "observation_contract_version" not in json.dumps(clean)
    result = observation()
    if defect == "extra":
        result["extra"] = True
    elif defect == "boolean":
        result["cursor"]["sequence"] = True
    elif defect == "epoch":
        result["cursor"]["epoch"] = "A" * 32
    elif defect == "large":
        result["context"]["history"][0]["content"] = "x" * 524288
    elif defect == "version":
        result["contract_version"] = "unnegotiated-version"
    agent.result_override = result
    if defect is None:
        assert await client.observe_business_context(activation, request_id="observation") == observation()
    else:
        with pytest.raises(NativeRuntimeClientError):
            await client.observe_business_context(activation, request_id="observation")
    assert len(agent.requests) == 1


@pytest.mark.asyncio
async def test_client_rechecks_activation_after_observation_completion():
    entered, release = asyncio.Event(), asyncio.Event()
    class Delayed(FakeAgentClient):
        async def send_request(self, envelope):
            entered.set()
            await release.wait()
            return await super().send_request(envelope)
    agent = Delayed()
    agent.result_override = observation()
    client, activation, _ = observed(agent)
    waiting = asyncio.create_task(client.observe_business_context(activation, request_id="delayed"))
    await entered.wait()
    client._activations[(SCOPE.session_id, BINDING.interaction_id)] = replace(activation, connection_id="replaced")
    release.set()
    with pytest.raises(NativeRuntimeClientError):
        await waiting


def coordinator(monkeypatch, observer):
    session = SimpleNamespace(closed=False, business_read_ticket=0, business_applied_ticket=0,
        business_observation_cursor=None, business_context_result=None, business_refresh_task=None,
        activation=SimpleNamespace(observation_contract_version=NATIVE_BUSINESS_OBSERVATION_VERSION))
    registry = DedicatedMediaProductRegistry(enabled=True)
    registry._native_runtime_client = SimpleNamespace(observe_business_context=observer)
    monkeypatch.setattr(registry, "_native_request_id", lambda *args: "context-request")
    monkeypatch.setattr(registry, "_profile_native_business_context", lambda *args: None)
    published = []
    monkeypatch.setattr(registry, "_publish_native_work_state", lambda session, result: published.append(result))
    return registry, session, published


@pytest.mark.asyncio
async def test_gateway_coalesces_immediate_reads_and_cancellation_preserves_shared_read(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []
    async def observer(*args, **kwargs):
        requests.append(kwargs)
        entered.set()
        await release.wait()
        return observation()
    registry, session, published = coordinator(monkeypatch, observer)
    first = asyncio.create_task(registry._refresh_native_business_context(session))
    second = asyncio.create_task(registry._refresh_native_business_context(session))
    await entered.wait()
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    assert len(requests) == 1 and not second.done()
    release.set()
    assert await second == observation()
    await asyncio.sleep(0)
    assert session.business_refresh_task is None and len(published) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("older", [observation(read_sequence=1), observation(sequence=1, read_sequence=2),
                                  observation(epoch="b" * 32, read_sequence=100)])
async def test_delayed_observation_cannot_overwrite_newer_snapshot_or_epoch(monkeypatch, older):
    entered, release = asyncio.Event(), asyncio.Event()
    async def observer(*args, wait_ms, **kwargs):
        if wait_ms:
            entered.set()
            await release.wait()
            return older
        return observation(sequence=2, read_sequence=2)
    registry, session, published = coordinator(monkeypatch, observer)
    slow = asyncio.create_task(registry._read_native_business_context(session, wait_ms=1000))
    await entered.wait()
    newer = await registry._refresh_native_business_context(session)
    release.set()
    assert await slow == newer
    assert session.business_context_result == newer and len(published) == 1


@pytest.mark.asyncio
async def test_closed_gateway_observer_releases_no_work_state(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    async def observer(*args, **kwargs):
        entered.set()
        await release.wait()
        return observation()
    registry, session, published = coordinator(monkeypatch, observer)
    waiting = asyncio.create_task(registry._refresh_native_business_context(session))
    await entered.wait()
    session.closed = True
    release.set()
    with pytest.raises(Exception) as error:
        await waiting
    assert error.value.reason_id == "MEDIA_NATIVE_SESSION_CLOSED"
    assert not published and session.business_context_result is None
