"""Observation failures cannot mint facts or tear down independent media."""
from types import SimpleNamespace

import pytest

from jiuwenswarm.gateway.live_voice import dedicated_media_registration as media
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import NativeRuntimeClientError


@pytest.mark.asyncio
async def test_observation_timeouts_retry_without_applying_stale_context_or_closing_media(monkeypatch):
    monkeypatch.setattr(media, "_NATIVE_BUSINESS_POLL_SECONDS", .001)
    calls, applied, effects = [], [], []
    session = SimpleNamespace(closed=False, activation=SimpleNamespace(observation_contract_version="v1",
        binding=SimpleNamespace(scope=SimpleNamespace(session_id="session-1"))))

    async def read(owner, *, wait_ms):
        assert owner is session and not owner.closed and wait_ms == 1000
        calls.append(wait_ms)
        if len(calls) <= 3:
            raise NativeRuntimeClientError("NATIVE_RUNTIME_TIMEOUT", "slow read")
        return {"context": {"fresh": True}, "work_events": []}

    async def update(context, events):
        applied.append((context, events))
        session.closed = True  # End after the successful retry, not on timeout.
        return []

    async def forbidden(*args):
        effects.append(args)
        raise AssertionError("No Task/audio/close effects from an observation timeout")

    session.engine = SimpleNamespace(update_business_context=update)
    service = SimpleNamespace(_read_native_business_context=read, _refresh_native_business_context=forbidden,
                              _handle_native_event=forbidden)
    await media.DedicatedMediaProductRegistry._run_native_business_poll(service, session)
    assert len(calls) == 4 and applied == [({"fresh": True}, [])] and effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["NATIVE_RUNTIME_CAPABILITY_REJECTED", "NATIVE_RUNTIME_SESSION_CLOSED"])
async def test_observation_authority_failures_remain_fatal(reason):
    async def read(*args, **kwargs):
        raise NativeRuntimeClientError(reason, "authority lost")
    session = SimpleNamespace(closed=False, activation=SimpleNamespace(observation_contract_version="v1"))
    service = SimpleNamespace(_read_native_business_context=read)
    with pytest.raises(NativeRuntimeClientError) as error:
        await media.DedicatedMediaProductRegistry._run_native_business_poll(service, session)
    assert error.value.reason == reason


@pytest.mark.asyncio
async def test_retired_observer_exits_when_its_revoked_rpc_returns():
    session = SimpleNamespace(closed=False, activation=SimpleNamespace(observation_contract_version="v1"))
    async def read(*args, **kwargs):
        session.closed = True  # Exact owner retired while the RPC was in flight.
        raise NativeRuntimeClientError("NATIVE_RUNTIME_CAPABILITY_REJECTED", "owner retired")
    service = SimpleNamespace(_read_native_business_context=read)
    await media.DedicatedMediaProductRegistry._run_native_business_poll(service, session)
