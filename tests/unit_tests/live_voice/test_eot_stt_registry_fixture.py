# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry,
)
from scripts.live_voice.eot_stt_registry_fixture import EotSttRegistryFixture


@pytest.mark.asyncio
async def test_exact_result_delegates_to_the_real_registry_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = DedicatedMediaProductRegistry.streaming_recognition_result

    async def counted(self: DedicatedMediaProductRegistry, **kwargs: object):
        nonlocal calls
        calls += 1
        return await original(self, **kwargs)

    monkeypatch.setattr(
        DedicatedMediaProductRegistry,
        "streaming_recognition_result",
        counted,
    )
    fixture = EotSttRegistryFixture(local_settlement_ms=50, provider_final_ms=50)
    try:
        assert await fixture.handle({"operation": "open"}) == {"status": "opened"}
        settled = await fixture.handle({"operation": "route_settled"})
        assert settled == {"status": "route_settled", "elapsed_ms": 50}
        provider = await fixture.handle({"operation": "provider_final"})
        assert provider == {"status": "provider_final", "elapsed_ms": 50}
        result = await fixture.handle({"operation": "streaming_result"})
        assert result["status"] == "completed"
        assert result["exact_result"] is True
        result.pop("business_result")
        assert calls == 1
        assert result == {"status": "completed", "exact_result": True}
    finally:
        assert await fixture.handle({"operation": "close"}) == {
            "status": "closed",
            "cleanup_complete": True,
        }


@pytest.mark.asyncio
async def test_closed_operations_reject_unknown_private_extra_and_out_of_order_records() -> (
    None
):
    private_sentinel = "_".join(("PRIVATE", "TRANSCRIPT", "SENTINEL"))
    fixture = EotSttRegistryFixture(local_settlement_ms=50, provider_final_ms=50)
    for request in (
        {"operation": "unknown"},
        {"operation": "open", "extra": True},
        {"operation": "open", "transcript": private_sentinel},
        {"operation": "streaming_result"},
    ):
        response = await fixture.handle(request)
        assert response == {
            "status": "rejected",
            "reason_id": "EOT_STT_FIXTURE_REQUEST_REJECTED",
        }
        assert private_sentinel not in json.dumps(response)
    assert await fixture.handle({"operation": "close"}) == {
        "status": "closed",
        "cleanup_complete": True,
    }


def test_json_line_process_keeps_identity_and_transcript_off_inherited_output() -> None:
    script = Path("scripts/live_voice/eot_stt_registry_fixture.py").resolve()
    commands = (
        "\n".join(
            json.dumps({"operation": operation})
            for operation in (
                "open",
                "route_settled",
                "provider_final",
                "streaming_result",
                "close",
            )
        )
        + "\n"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--local-settlement-ms",
            "50",
            "--provider-final-ms",
            "50",
        ],
        input=commands,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=5,
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [response["status"] for response in responses] == [
        "opened",
        "route_settled",
        "provider_final",
        "completed",
        "closed",
    ]
    result = responses[3]
    assert result["exact_result"] is True
    result.pop("business_result")
    # The harness captured both pipes. Only the exact in-memory business
    # result may contain text; content-free records and stderr never do.
    content_free = [
        {key: value for key, value in response.items() if key != "business_result"}
        for response in responses
    ]
    snapshot = json.dumps(content_free, sort_keys=True)
    assert "benchmark recognition" not in snapshot
    assert "session-" not in snapshot
    assert "capture-" not in snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["abort", "owner", "diagnostics"])
async def test_cleanup_failure_is_truthful_and_retries_only_unfinished_stage(
    stage: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = EotSttRegistryFixture(local_settlement_ms=50, provider_final_ms=50)
    calls = 0

    if stage == "abort":
        fixture._opened = True
        fixture._record = object()

        async def abort_once(_record: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("PRIVATE_ABORT_FAILURE")

        monkeypatch.setattr(
            fixture.registry,
            "abort_streaming_recognition",
            abort_once,
        )
    elif stage == "owner":

        async def owner_once() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("PRIVATE_OWNER_FAILURE")

        monkeypatch.setattr(fixture._owner, "close", owner_once)
    else:

        def diagnostics_once() -> bool:
            nonlocal calls
            calls += 1
            return calls > 1

        monkeypatch.setattr(
            fixture.registry,
            "close_streaming_diagnostics",
            diagnostics_once,
        )

    first = await fixture._close()
    assert first == {"status": "closed", "cleanup_complete": False}
    second = await fixture._close()
    assert second == {"status": "closed", "cleanup_complete": True}
    assert calls == 2


def test_oversized_json_line_drains_valid_operation_tail_without_execution() -> None:
    script = Path("scripts/live_voice/eot_stt_registry_fixture.py").resolve()
    oversized_with_open_tail = (
        b"x" * 4097 + json.dumps({"operation": "open"}).encode("utf-8") + b"\n"
    )
    close = json.dumps({"operation": "close"}).encode("utf-8") + b"\n"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--local-settlement-ms",
            "50",
            "--provider-final-ms",
            "50",
        ],
        input=oversized_with_open_tail + close,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
    )
    assert completed.returncode == 0
    assert completed.stderr == b""
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert responses == [
        {
            "status": "rejected",
            "reason_id": "EOT_STT_FIXTURE_REQUEST_REJECTED",
        },
        {"status": "closed", "cleanup_complete": True},
    ]


@pytest.mark.parametrize("delay", [-1, 0, 49, 51, 499, 501, float("inf")])
def test_fixture_delays_are_closed_to_the_exact_50_and_500_ms_values(
    delay: float,
) -> None:
    with pytest.raises(ValueError, match="EOT_STT_FIXTURE_ARGUMENT_INVALID"):
        EotSttRegistryFixture(local_settlement_ms=delay, provider_final_ms=50)
