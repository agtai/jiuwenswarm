"""The toolkit's specs as openjiuwen tools."""

from __future__ import annotations

import json
from typing import Any

from jiuwenswarm.extensions.blackboard.client.toolkit.tools import ToolSpec


def to_openjiuwen(specs: list[ToolSpec], owner: str) -> list[Any]:
    """`owner` makes the card ids unique per session; the names are what the model sees.

    The tools are declared DIRECT so progressive tool disclosure does not hide them behind tool_search,
    and their results reach the model as JSON rather than a Python repr.
    """
    from openjiuwen.core.foundation.tool import ToolExposure
    from openjiuwen.core.foundation.tool.base import ToolCard
    from openjiuwen.core.foundation.tool.function.function import LocalFunction

    return [
        LocalFunction(
            card=ToolCard(
                id=f"{spec.name}.{owner}",
                name=spec.name,
                description=spec.description,
                input_params=spec.parameters,
                exposure=ToolExposure.DIRECT,
            ),
            func=spec.func,
            render=_as_json,
        )
        for spec in specs
    ]


def _as_json(output: Any) -> str:
    return json.dumps(output, ensure_ascii=False)
