# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Process-local Executor checkpoint binding; never supplied by a model/request."""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BackgroundTaskCheckpoint:
    session_id: str
    adopt: Callable[[Any], Awaitable[None]]
    closed: bool = False


_current: ContextVar[BackgroundTaskCheckpoint | None] = ContextVar(
    "background_task_model_checkpoint", default=None
)


@contextmanager
def background_task_checkpoint(session_id: str, adopt: Callable[[Any], Awaitable[None]]) -> Iterator[None]:
    owner = BackgroundTaskCheckpoint(session_id, adopt)
    token = _current.set(owner)
    try:
        yield
    finally:
        owner.closed = True
        _current.reset(token)


def current_background_task_checkpoint(session_id: str) -> BackgroundTaskCheckpoint | None:
    owner = _current.get()
    if owner is not None and (owner.closed or owner.session_id != session_id):
        raise RuntimeError("BACKGROUND_TASK_CHECKPOINT_BINDING_MISMATCH")
    return owner
