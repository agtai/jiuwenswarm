import asyncio

import pytest

from jiuwenswarm.common import live_voice_lock_diagnostics as diagnostics


@pytest.mark.asyncio
async def test_holder_wait_chain_and_cancel_preserve_lock_ownership(monkeypatch):
    events = []
    monkeypatch.setattr(diagnostics, "record_audio_diagnostic", lambda event, **fields: events.append(fields))
    lock = diagnostics.ObservedAsyncLock("registry")
    async with lock:
        cancelled = asyncio.create_task(lock.acquire())
        next_owner = asyncio.create_task(lock.acquire())
        await asyncio.sleep(.025)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert lock.locked() and not next_owner.done()
    await next_owner
    assert lock.locked()
    lock.release()
    holds = [e for e in events if e["stage"] == "hold"]
    waits = [e for e in events if e["stage"] == "wait"]
    assert holds and waits and waits[0]["parent_span_id"] == holds[0]["span_id"]
    assert waits[0]["lock_owner"] == "test_holder_wait_chain_and_cancel_preserve_lock_ownership"
    assert not lock.locked()
    with pytest.raises(RuntimeError):
        lock.release()


@pytest.mark.asyncio
async def test_throwing_diagnostics_cannot_strand_lock(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("sink unavailable")
    monkeypatch.setattr(diagnostics, "record_audio_diagnostic", fail)
    lock = diagnostics.ObservedAsyncLock("registry")
    async with lock:
        await asyncio.sleep(.025)
    assert not lock.locked()
    async with lock:
        assert lock.locked()
