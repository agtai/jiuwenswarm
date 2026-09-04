"""Shared defaults for the agentserver unit tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ask_channel_present(monkeypatch):
    """Run every test in the attended world unless it says otherwise.

    D16 made the write tools consult the session's confirmation channel; the
    pre-D16 tests were all written against a world where the ask machinery exists,
    and re-stating that per test would be four dozen copies of one line. Tests
    that exercise the Full Access floor override this with ``False`` explicitly.
    """
    import jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools as ct

    monkeypatch.setattr(ct, "_ask_channel_available", lambda: True)
    yield
