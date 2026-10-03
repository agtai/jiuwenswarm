"""Shared fixtures for the co-scribe unit tests."""

from __future__ import annotations

import logging
from typing import Generator

import pytest


@pytest.fixture(autouse=True)
def _clouddoc_config_is_not_the_developers(monkeypatch):
    """No test result may depend on the machine's own ``config.yaml``.

    Several modules read ``clouddoc.enabled`` and ``clouddoc.mode`` live, so a test
    that does not patch the configuration itself would inherit whatever the developer
    has configured and answer differently on two machines. A deployment with the
    feature on, in the only mode that has an unattended path; a test that needs
    another mode patches ``get_config`` itself, and that patch is applied after this
    one, so it wins.
    """
    from jiuwenswarm.common import config as config_mod

    monkeypatch.setattr(
        config_mod,
        "get_config",
        lambda: {"clouddoc": {"enabled": True, "mode": "mandate"}},
    )
    yield


@pytest.fixture(autouse=True)
def _jiuwenswarm_logs_reach_caplog(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Let ``caplog`` see records from the ``jiuwenswarm`` logger tree.

    ``jiuwenswarm.common.utils`` calls ``setup_logger()`` at import time, which sets
    ``propagate = False`` on the ``jiuwenswarm`` logger; ``caplog`` listens on the
    root logger, so nothing reaches it. Propagation is restored only for tests that
    ask for ``caplog``: it also feeds pytest's live-log handler, which reinstalls its
    own ``sys.stderr`` over one a test has replaced.
    """
    if "caplog" not in request.fixturenames:
        yield
        return
    logger = logging.getLogger("jiuwenswarm")
    previous = logger.propagate
    logger.propagate = True
    try:
        yield
    finally:
        logger.propagate = previous


_WRITE_TOOL_TESTS = frozenset({
    "test_apply_direct.py",
    "test_lifecycle.py",
    "test_structure.py",
    "test_toolkit.py",
    "test_feishu_provider.py",
    "test_google_formats.py",
    "test_feishu_formats.py",
    "test_formats_tools.py",
})


@pytest.fixture(autouse=True)
def _ask_channel_present(request, monkeypatch):
    """Run every write-tool test in the attended world unless it says otherwise.

    The write tools consult the session's confirmation channel; these tests were
    written against a world where the ask machinery exists, and re-stating that per
    test would be dozens of copies of one line. Tests that exercise the Full Access
    floor override this with ``False`` explicitly.
    """
    if request.path.name not in _WRITE_TOOL_TESTS:
        yield
        return
    import jiuwenswarm.clouddoc.tools.toolkit as ct

    monkeypatch.setattr(ct, "_ask_channel_available", lambda: True)
    yield
