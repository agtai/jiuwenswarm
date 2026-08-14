# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Compatibility helpers for optional OpenJiuwen context processors."""

from functools import lru_cache
from typing import Any

REASONING_TOOL_LOOP_COMPACT_PROCESSOR = "ReasoningToolLoopCompactProcessor"


@lru_cache(maxsize=32)
def context_processor_preset_supports(
    rail_type: type[Any],
    processor_key: str,
) -> bool:
    """Return whether an SDK rail preset exposes an optional processor key.

    OpenJiuwen rejects configuration overrides whose keys are absent from the
    installed preset. The SDK currently has no public capability query, so this
    compatibility seam probes the preset builder and fails closed when its
    private shape changes.
    """

    if not processor_key:
        return False

    try:
        rail = rail_type(preset=True)
        build_preset = getattr(rail, "_build_preset_processors", None)
        if not callable(build_preset):
            return False
        processors = build_preset()
    except Exception:  # noqa: BLE001 -- an unknown SDK shape is unsupported
        return False

    if not isinstance(processors, (list, tuple)):
        return False
    return any(
        isinstance(entry, (list, tuple))
        and len(entry) >= 1
        and entry[0] == processor_key
        for entry in processors
    )
