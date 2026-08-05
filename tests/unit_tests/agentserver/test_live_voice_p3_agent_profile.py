# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import os
from pathlib import Path

import pytest

from jiuwenswarm.server.runtime.agent_manager import AgentManager


class _Agent:
    def __init__(self) -> None:
        self.cleanup_calls = 0
        self.cancel_calls = 0

    async def cleanup(self) -> None:
        self.cleanup_calls += 1

    async def cancel_inflight_work(self, _reason: str) -> None:
        self.cancel_calls += 1


@pytest.mark.asyncio
async def test_formal_task_agent_uses_dedicated_clean_profile_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = AgentManager()
    agent = _Agent()
    creates: list[dict[str, object]] = []

    async def create(
        agent_key,
        mode="agent",
        config=None,
        sub_mode=None,
        cache_key=None,
    ):
        creates.append(
            {
                "agent_key": agent_key,
                "mode": mode,
                "config": dict(config or {}),
                "sub_mode": sub_mode,
                "cache_key": cache_key,
            }
        )
        manager.agents.setdefault(agent_key, {})[cache_key] = agent
        manager._agent_create_params.setdefault(agent_key, {})[cache_key] = {
            "mode": mode,
            "sub_mode": sub_mode,
            "config": dict(config or {}),
            "cache_key": cache_key,
        }
        return agent

    monkeypatch.setattr(manager, "_create_agent", create)

    first = await manager.get_live_voice_formal_task_agent(str(tmp_path))
    second = await manager.get_live_voice_formal_task_agent(str(tmp_path))

    assert first is agent
    assert second is agent
    assert len(creates) == 1
    assert creates[0]["agent_key"] == "live_voice_formal_task"
    assert creates[0]["mode"] == "code"
    assert creates[0]["config"] == {
        "project_dir": os.path.normcase(str(tmp_path.resolve())),
        "project_clean_runtime_support": True,
    }
    assert "formal_task" in str(creates[0]["cache_key"])

    await manager.cleanup_live_voice_formal_task_agents()
    await manager.cleanup_live_voice_formal_task_agents()

    assert agent.cleanup_calls == 1
    assert "live_voice_formal_task" not in manager.agents


@pytest.mark.asyncio
async def test_gateway_disconnect_never_cancels_formal_task_agent() -> None:
    manager = AgentManager()
    interactive = _Agent()
    formal = _Agent()
    manager.agents = {
        "web": {"agent": interactive},
        "live_voice_formal_task": {"formal": formal},
    }

    await manager.cancel_all_inflight_work("gateway disconnected")

    assert interactive.cancel_calls == 1
    assert formal.cancel_calls == 0
