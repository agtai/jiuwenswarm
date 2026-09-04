"""Browser end-to-end coverage for the co-scribe product surfaces.

These tests drive the served web app (default http://127.0.0.1:5173) with
Playwright against the deployment's own running services -- no mocks, the same
loop a person operates. They skip, stating why, when the stack is not up.

Covered here:
- the app shell loads with the Docs entry visible when a connection exists;
- the Docs panel renders connections and managed documents;
- the built-in Co-Scribe template and the doc-crew group are listed by the
  extension manager (through the same resolution the UI uses);
- the session reference chip flow's wiring: the openDocSignal latch, the
  chip's jump, and the panel's auto-opened history (exercised when a session
  with clouddoc turns exists; the write half needs a live agent turn and runs
  in the scripted campaign, not here).
"""

from __future__ import annotations

import os

import pytest

BASE_URL = os.environ.get("CO_SCRIBE_E2E_URL", "http://127.0.0.1:5173")

playwright_api = pytest.importorskip(
    "playwright.async_api", reason="playwright is not installed in this environment"
)


@pytest.fixture()
async def page():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page()
        try:
            resp = await pg.goto(BASE_URL, wait_until="networkidle", timeout=15000)
        except Exception:
            pytest.skip(f"web app not reachable at {BASE_URL}")
        if resp is None or not resp.ok:
            pytest.skip(f"web app not healthy at {BASE_URL}")
        await pg.wait_for_timeout(2000)
        yield pg
        await browser.close()


NAV = '[data-testid="session-sidebar-nav-item"]'


def nav_item(page, key: str):
    """A navigation entry by its key, not by its label.

    These tests used to locate by visible text ("Tasks", "Docs", "Connections").
    The interface is bilingual and this deployment renders Chinese, so every such
    locator found nothing: one test failed and the Docs one *skipped itself* with
    "no cloud-doc connection on this deployment" while three connections were
    configured. A suite that reports "nothing to test" when the label language
    changes provides no coverage and says so in the voice of a pass.
    """
    return page.locator(f'{NAV}[data-variant="{key}"]')


@pytest.mark.asyncio
async def test_shell_loads_without_page_errors(page):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.wait_for_timeout(1000)
    assert await page.locator('[data-testid="session-sidebar-rail"]').count() == 1
    assert await page.locator(NAV).count() >= 1, "导航栏一个入口都没渲染"
    assert not errors, errors


@pytest.mark.asyncio
async def test_docs_panel_renders_connections_and_documents(page):
    docs_nav = nav_item(page, "docs")
    if await docs_nav.count() == 0:
        pytest.skip("no cloud-doc connection on this deployment; Docs nav hidden by design")
    await docs_nav.first.click()
    await page.wait_for_selector('[data-testid="docs-add-conn-select"]', timeout=30000)
    conns = await page.locator('[data-testid="docs-add-conn-select"] option').count()
    assert conns >= 1, "连接下拉是空的"
    rows = await page.locator('[data-testid="docs-table-row"]').count()
    assert rows >= 1, "纳管文档一行都没有"


@pytest.mark.asyncio
async def test_reference_chip_jumps_to_the_documents_history(page):
    """The A5 loop on an existing session: chip -> Docs -> history dialog.

    The chips belong to a session, and a fresh page load starts an empty one, so
    this walks the conversation list for a session whose turns touched a document.
    Without one it skips -- the campaign script creates it.
    """
    await nav_item(page, "chat").first.click()
    await page.wait_for_timeout(2000)
    strip = page.locator('[data-testid="doc-references-strip"]')
    rows = page.locator('[data-testid="multi-session-conversation-list-item"]')
    for i in range(min(await rows.count(), 8)):
        if await strip.count():
            break
        await rows.nth(i).click()
        await page.wait_for_timeout(3000)
    if await strip.count() == 0:
        pytest.skip("no session with clouddoc turns; run the campaign first")
    await page.locator('[data-testid^="doc-ref-chip-"]').first.click()
    # The chip lands in the document workbench (release §14.5a): the document's
    # tab plus the receipts rail, not the old panel history dialog.
    await page.wait_for_selector('[data-testid="doc-workbench"]', timeout=30000)
    assert await page.locator('[data-testid="doc-workbench-tab"]').count() >= 1, (
        "the chip must open the document's workbench tab"
    )
    assert await page.locator('[data-testid="doc-workbench-rail"]').count() == 1, (
        "the receipts rail must be beside the document"
    )


def test_builtin_assets_resolve():
    """The persona card retired with the 甲-plan: co-scribe is the deployment's
    own harnessed editing (Settings wires it, Docs switches it), not a
    marketplace identity. The team formation stays."""
    epm = pytest.importorskip("jiuwenswarm.server.runtime.extension_package_manager")
    grp = epm.show_agent_group("doc-crew")
    assert grp and grp.get("memberCount") == 3
    assert epm.show_agent_template("co-scribe") is None, "人设卡已退役"
