from __future__ import annotations

from openjiuwen.core.foundation.tool.exposure import ToolExposure
from openjiuwen.core.single_agent.ability_manager import (
    DEFAULT_TOOL_CALL_TIMEOUT,
    AbilityManager,
)

from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_ingest, wiki_query


def test_ingest_and_query_are_exempt_from_the_default_call_timeout():
    """A wiki ingest runs for minutes; the 300 s default was killing it mid-write.

    Asserted through the kernel's own resolver rather than by reading the dict, so
    the test fails if the contract that reads these properties ever changes.
    """
    for tool in (wiki_ingest, wiki_query):
        resolved = AbilityManager._resolve_call_timeout(tool.card)
        assert resolved is None, f"{tool.card.name} resolved to {resolved}"


def test_a_tool_without_the_declaration_still_gets_the_default():
    """Guards the assertion above against a resolver that returns None for everything."""
    from jiuwenswarm.agents.harness.common.tools.pdf_tools import read_pdf

    assert AbilityManager._resolve_call_timeout(read_pdf.card) == DEFAULT_TOOL_CALL_TIMEOUT


def test_ingest_and_query_stay_directly_exposed_under_progressive_tools():
    """The timeout exemption is void unless the tool is called directly.

    Under progressive tools a deferred tool is reached through the model-visible
    ``tool_call`` wrapper, and the wrapper's own call carries the default timeout --
    so exempting only the target would still be killed by its parent. Declaring the
    exposure is what keeps the registration policy from deferring these two.
    """
    for tool in (wiki_ingest, wiki_query):
        assert tool.card.exposure == ToolExposure.DIRECT
        assert tool.card.get_exposure_declared() is True


def test_registration_policy_cannot_defer_them():
    """The declaration survives a progressive registration policy, not just a read."""
    manager = AbilityManager()
    manager.set_tool_exposure_policy(progressive_tool_enabled=True)
    for tool in (wiki_ingest, wiki_query):
        assert manager._apply_tool_exposure_policy(tool.card) == ToolExposure.DIRECT
