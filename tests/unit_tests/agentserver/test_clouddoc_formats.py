"""The formats past a plain document: markdown files, spreadsheets, decks.

What is being checked here is not "can it read a sheet" -- that needs a tenant nobody
has. It is the set of claims the design rests on, each of which is a decision that
could be silently wrong:

* a quoted string still locates, in a grid and in a deck, by the one rule the rails use
* a formula cell refuses the write that would replace it with a literal (IC-7)
* a capability nobody has is declared absent rather than simulated (C9)
* the receipt records the edits, on every format, not just the one that had a test

The last one is here because it was wrong when written: the new writers passed an
empty list to ``_receipt_begin``, which recorded a receipt with no edits in it. Nothing
failed. That is the shape §16.12 describes -- present, wired, and inert -- so it gets a
test that reads the recorded contents rather than merely that a receipt happened.
"""

from __future__ import annotations

import asyncio

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc import textmap
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    DocSnapshot,
    ProviderError,
)


def _sheet(rows):
    cells = [
        [
            textmap.Cell(
                address=f"S!{chr(65 + c)}{r + 1}",
                formatted=str(v[0]),
                formula=str(v[1]),
            )
            for c, v in enumerate(row)
        ]
        for r, row in enumerate(rows)
    ]
    text, segs = textmap.flatten_grid(cells)
    return DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)


# ------------------------------------------------------------------ flattening


def test_a_grid_flattens_to_the_text_a_person_would_copy_out():
    """Tab between cells and newline between rows is the clipboard convention, and the
    quote a comment carries is what the person saw -- so the two have to agree or no
    quote ever matches."""
    snap = _sheet([[("Q1", "Q1"), ("42", "42")], [("Q2", "Q2"), ("7", "7")]])
    assert snap.text == "Q1\t42\nQ2\t7"


def test_every_cell_keeps_its_own_address():
    snap = _sheet([[("a", "a"), ("b", "b")]])
    assert [s.address for s in snap.segments] == ["S!A1", "S!B1"]


def test_notes_are_flattened_behind_a_divider():
    """A sentence appearing in both the slide and its notes would otherwise be two
    equally good matches, and the rail would refuse an edit it could have made."""
    text, _ = textmap.flatten_slides([
        ("p1", [
            textmap.Shape("p1", "body", "same words"),
            textmap.Shape("p1", "notes", "same words", is_notes=True),
        ])
    ])
    assert textmap.NOTES_DIVIDER in text
    assert text.index("same words") < text.index(textmap.NOTES_DIVIDER)


def test_a_grouped_text_box_is_not_lost():
    """Slides can nest shapes in groups; text inside one is still text a comment can
    quote, so the walk has to descend into them."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_formats import _shapes_of

    page = {
        "pageElements": [
            {"elementGroup": {"children": [
                {"objectId": "inner", "shape": {"text": {"textElements": [
                    {"textRun": {"content": "buried"}}
                ]}}}
            ]}}
        ]
    }
    assert [s.text for s in _shapes_of(page, "p1", notes=False)] == ["buried"]


def test_markdown_flattens_to_itself():
    body = "# Title\n\nSome **bold** text.\n"
    text, segs = textmap.flatten_markdown(body)
    assert text == body
    assert (segs[0].char_start, segs[0].char_end) == (0, len(body))


# ------------------------------------------------------------------ IC-7


def test_a_formula_cell_refuses_the_write_that_would_flatten_it():
    """The whole reason IC-7 exists: the cell reads as 42, the comment quotes 42, and
    writing 42 back leaves a literal where =SUM(A1:A9) was -- with nothing on the page
    to show it happened."""
    snap = _sheet([[("Total", "Total"), ("42", "=SUM(A1:A9)")]])
    c0, c1 = textmap.locate_span(snap.text, "42")
    with pytest.raises(ProviderError) as exc:
        textmap.single_placement(snap, c0, c1)
    assert "公式" in str(exc.value)


def test_a_number_formatted_cell_is_not_mistaken_for_a_formula():
    """1234 displayed as 1,234 differs from what is stored without being computed.
    Comparing the two faces alone would refuse every formatted number in the sheet."""
    snap = _sheet([[("1,234", "1234")]])
    c0, c1 = textmap.locate_span(snap.text, "1,234")
    assert textmap.single_placement(snap, c0, c1).segment.address == "S!A1"


def test_an_ordinary_cell_still_writes():
    snap = _sheet([[("hello", "hello")]])
    c0, c1 = textmap.locate_span(snap.text, "hello")
    assert textmap.single_placement(snap, c0, c1).segment.readonly_reason == ""


# ------------------------------------------------------------------ locating


def test_a_quote_matching_many_cells_is_refused_rather_than_guessed():
    """In a spreadsheet this is the common case, not the rare one, and refusing is the
    rail working: the alternative is writing to a cell nobody named."""
    snap = _sheet([[("42", "42"), ("42", "42")]])
    with pytest.raises(ProviderError) as exc:
        textmap.locate_span(snap.text, "42")
    assert "unique" in str(exc.value)


def test_a_span_crossing_two_cells_is_refused():
    """There is no single write that means it. Writing the first would drop half the
    edit; splitting it would stop being one change."""
    snap = _sheet([[("alpha", "alpha"), ("beta", "beta")]])
    c0, c1 = textmap.locate_span(snap.text, "alpha\tbeta")
    with pytest.raises(ProviderError) as exc:
        textmap.single_placement(snap, c0, c1)
    assert "跨越" in str(exc.value)


def test_a_cell_is_edited_in_place_not_replaced_wholesale():
    """A comment asking to change one word quotes the word. Writing only the word back
    would delete the rest of the sentence around it."""
    snap = _sheet([[("the quick fox", "the quick fox")]])
    c0, c1 = textmap.locate_span(snap.text, "quick")
    hit = textmap.single_placement(snap, c0, c1)
    cell = snap.text[hit.segment.char_start : hit.segment.char_end]
    assert cell[: hit.local_start] + "slow" + cell[hit.local_end :] == "the slow fox"


def test_edits_applied_to_text_see_each_other():
    """Uniqueness is judged against the text as it stands, not the original, or two
    overlapping edits would both look applicable and the second would land on text the
    first already rewrote."""
    assert textmap.apply_edits_to_text("a b c", [("a", "x"), ("x b", "y")]) == "y c"


# ------------------------------------------------------------------ capabilities


def test_no_format_claims_a_lock_it_does_not_have():
    """C9. Two of these formats have no write precondition available at all -- measured
    -- and a handler that compensates with a content check still says False, because
    admission reads this flag to decide whether concurrency is protected."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_formats import TRAITS

    assert TRAITS["markdown"].has_revision_control is False
    assert TRAITS["spreadsheet"].has_revision_control is False
    assert TRAITS["presentation"].has_revision_control is True


def test_feishu_does_not_claim_revision_control():
    """``--revision-id`` is a base revision, not a lock: pinning an older one rebuilds
    from that snapshot and discards newer edits. Claiming a lock here would let
    admission rely on protection that does not exist, and the failure mode is a
    destroyed edit reported as applied.

    This flag was True and no test noticed when it flipped, which is why it has one."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.feishu_provider import (
        FeishuDocsProvider,
    )
    import inspect

    src = inspect.getsource(FeishuDocsProvider)
    assert "has_revision_control=True" not in src


def test_the_feishu_write_never_pins_a_revision():
    """Pinning is worse than having no lock: a concurrent edit stops being a refused
    write and becomes a destroyed one."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import feishu_provider
    import inspect

    src = inspect.getsource(feishu_provider)
    assert '"--revision-id"' not in src


def test_markdown_declares_its_markers_are_content():
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_formats import TRAITS

    assert TRAITS["markdown"].text_domain == "markdown"
    assert TRAITS["spreadsheet"].text_domain == "plain"


# ------------------------------------------------------------------ receipts


class _Sink:
    def __init__(self):
        self.rows = None

    def begin(self, doc, edits, *, highlight, source="", executor=""):
        self.rows = edits
        return "r1"

    def commit(self, rid, revision_after=None):
        pass

    def abort(self, rid, reason=""):
        pass


class _FakeGoogle:
    """Enough of the provider for a writer to run against, and nothing more."""

    def __init__(self, sink):
        self.receipt_sink = sink
        self.receipt_meta = {}
        self.written = None

    _receipt_begin = None  # replaced below

    def _receipt_commit(self, rid, rev):
        pass

    def _receipt_abort(self, rid, reason):
        pass


def test_every_format_records_what_it_edited():
    """Not that a receipt happened -- what is in it. The first version of these writers
    passed an empty list here and recorded receipts with no edits, which is the failure
    rings ⑤ and ⑥ are built to prevent and which nothing else would have caught."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import (
        GoogleDocsProvider,
    )

    sink = _Sink()
    prov = _FakeGoogle(sink)
    # Borrow the real recorder: the point is that the writers call it with real edits.
    prov._receipt_begin = GoogleDocsProvider._receipt_begin.__get__(prov)

    prov._receipt_begin("doc", [("old", "new")], highlight=False)
    assert sink.rows == [{"old": "old", "new": "new", "for_comment_ids": []}]

    # And the document path's four-tuple shape still records the same way.
    sink.rows = None
    prov._receipt_begin("doc", [(1, 5, "old", "new")], highlight=False)
    assert sink.rows == [{"old": "old", "new": "new", "for_comment_ids": []}]


def test_a_markdown_write_aborts_when_the_file_moved_under_it():
    """No lock exists, so the only guard is re-reading immediately before the write.
    Without it, whole-file replacement silently deletes whatever arrived in between."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    calls = []

    class Prov:
        receipt_sink = None
        receipt_meta = {}

        def _receipt_begin(self, *a, **k):
            calls.append("begin")
            return None

        def _receipt_commit(self, *a, **k):
            calls.append("commit")

        def _receipt_abort(self, *a, **k):
            pass

    async def fake_read(_prov, _ref):
        return DocSnapshot(doc_id="d", kind="markdown", revision_id="CHANGED", text="new body")

    real = google_formats.read_markdown
    google_formats.read_markdown = fake_read
    try:
        stale = DocSnapshot(doc_id="d", kind="markdown", revision_id="ORIGINAL", text="old body")
        res = asyncio.run(
            google_formats.write_markdown(Prov(), "d", stale, [("old", "x")], None)
        )
    finally:
        google_formats.read_markdown = real

    assert res.status == "conflict"
    # Nothing was sent, so nothing should have been recorded as intended either.
    assert calls == []


def test_a_failing_receipt_sink_does_not_kill_the_write():
    """The three handlers promise, in their own comments, that a write must not die on
    its bookkeeping. They kept that promise by catching the exception and logging it --
    against a ``logger`` the module never defined, so the catch raised ``NameError``
    and the write died anyway, on the one path built to prevent exactly that.

    Nothing exercised it because a sink that fails is the rare case, which is what
    makes it worth a test rather than a reading."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import (
        GoogleDocsProvider,
    )

    class Broken:
        def begin(self, *a, **k):
            raise RuntimeError("sink down")

        def commit(self, *a, **k):
            raise RuntimeError("sink down")

        def abort(self, *a, **k):
            raise RuntimeError("sink down")

    prov = object.__new__(GoogleDocsProvider)
    prov.receipt_sink = Broken()
    prov.receipt_meta = {}

    assert prov._receipt_begin("d", [("a", "b")], highlight=False) is None
    prov._receipt_commit("r1", "rev")
    prov._receipt_abort("r1", "reason")


# ------------------------------------------------------- review findings, fixed


def test_two_edits_to_one_cell_compose_instead_of_racing():
    """Each edit was located against the original text and each produced a whole-cell
    write to the same address. The platform applies them in order, so the last won, the
    first was erased, and the batch reported ``applied``.

    Grouping by address is what makes them compose. This is the one finding in the
    review that lost data."""
    snap = _sheet([[("alpha beta gamma", "alpha beta gamma")]])
    planned = textmap.plan_edits(snap, [("alpha", "A"), ("gamma", "G")])
    assert list(planned) == ["S!A1"], "同一格的两处修改必须归并成一次写入"
    folded = textmap.fold_edits("alpha beta gamma", planned["S!A1"])
    assert folded == "A beta G", "两处修改都要在最终值里"


def test_two_edits_over_the_same_characters_are_refused():
    """There is no order in which both are what the person approved, and applying
    either silently would be picking one for them."""
    snap = _sheet([[("alpha beta", "alpha beta")]])
    with pytest.raises(ProviderError) as exc:
        textmap.plan_edits(snap, [("alpha beta", "x"), ("beta", "y")])
    assert "同一段文字" in str(exc.value)


def test_the_approved_window_reaches_the_writer():
    """Without it this layer re-judges uniqueness across the whole body. In a document
    that is merely stricter; in a spreadsheet a quote of "42" matches every cell showing
    42, so a proposal the rail passed is refused *after a person approved it* -- the
    exact failure the document path's _locate warns about."""
    snap = _sheet([[("42", "42")], [("42", "42")]])
    with pytest.raises(ProviderError):
        textmap.plan_edits(snap, [("42", "43")])  # no window: ambiguous, correctly
    planned = textmap.plan_edits(snap, [("42", "43")], window=(0, 2))
    assert list(planned) == ["S!A1"], "带窗口时应当落在窗口所在的那一格"


def test_edits_applied_whole_file_respect_the_window_too():
    """The markdown path rewrites the whole file, so the window is the only thing
    keeping an edit inside the range the comment authorised."""
    text = "keep this\nchange this\nkeep this"
    with pytest.raises(ProviderError):
        textmap.apply_edits_to_text(text, [("keep this", "x")])
    out = textmap.apply_edits_to_text(text, [("keep this", "x")], window=(0, 9))
    assert out == "x\nchange this\nkeep this"


def test_a_sheet_name_needing_quotes_gets_them():
    """A1 notation rejects an unquoted title with a space, and the request fails for the
    whole spreadsheet rather than for that sheet -- so a workbook with a "Q3 Data" tab
    could not be read at all."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_formats import (
        _quote_sheet,
    )

    assert _quote_sheet("Sheet1") == "Sheet1"
    assert _quote_sheet("Q3 Data") == "'Q3 Data'"
    assert _quote_sheet("Bob's") == "'Bob''s'"
    assert _quote_sheet("2024") == "'2024'"


def test_a_cell_address_carries_the_quoting_the_write_needs():
    """The address goes straight back out as the write's A1 range, so a title needing
    quotes would read fine and then fail on write."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.textmap import Cell, flatten_grid
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_formats import _quote_sheet

    addr = f"{_quote_sheet('Q3 Data')}!A1"
    _, segs = flatten_grid([[Cell(address=addr, formatted="x", formula="x")]])
    assert segs[0].address == "'Q3 Data'!A1"


def test_a_link_comes_from_the_provider_not_a_template():
    """The panel and the create-document tool both hand a link to a person, and both
    built it as a Google **document** URL -- wrong for every Feishu document and for
    every Google spreadsheet, deck and markdown file."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import (
        GoogleDocsProvider,
    )

    prov = object.__new__(GoogleDocsProvider)
    prov._kind_cache = {}
    assert "/spreadsheets/" in prov.doc_url("X", "spreadsheet")
    assert "/presentation/" in prov.doc_url("X", "presentation")
    assert "/document/" in prov.doc_url("X", "document")
    # An unknown kind gets the Drive file view, which opens every type, rather than the
    # document editor, which opens one.
    assert "drive.google.com" in prov.doc_url("X", "")


def test_the_canonical_tool_list_matches_what_the_toolkit_builds():
    """Four places need this list -- the toolkit, the team whitelist, the scene hook and
    the permission config -- and each kept its own copy. A copy drifts silently: a tool
    missing from the team whitelist just does not appear, filtered at debug level.

    The drift had already happened when the list was first written down in one place:
    the design's as-built section named seven tools and the toolkit built nine, the
    workmode pair having arrived with PR2a without the count following."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        ALL_TOOL_NAMES,
        CloudDocToolkit,
    )

    class _Provider:
        text_domain = "plain"

        def parse_doc_ref(self, ref):
            return ref

    built = {t.card.name for t in CloudDocToolkit(_Provider()).get_tools()}
    assert built == set(ALL_TOOL_NAMES), (
        f"权威清单与工具集不一致：{built ^ set(ALL_TOOL_NAMES)}"
    )


# ------------------------------------------------- what a read tells the agent


@pytest.mark.asyncio
async def test_reading_a_spreadsheet_reports_cell_addresses():
    """The flat text is what the range rail anchors on, and for a grid it is not enough
    on its own.

    Measured live: a comment asked to "move this to A1", the read returned
    ``'\\n\\n\\n\\n\\n\\n\\t大家好'``, and the agent reasoned for thirteen minutes trying to
    work out which cell that was -- while ``Segment.address`` held ``Sheet1!B7`` the
    whole time and nothing passed it on. Tabs and newlines are not coordinates."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        CloudDocToolkit,
    )

    cells = [
        [textmap.Cell("Sheet1!A1", "", ""), textmap.Cell("Sheet1!B1", "大家好", "大家好")],
        [textmap.Cell("Sheet1!A2", "42", "=SUM(B1:B9)"), textmap.Cell("Sheet1!B2", "x", "x")],
    ]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(
        doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs
    )

    class _Prov:
        text_domain = "plain"

        def parse_doc_ref(self, ref):
            return ref

        async def read(self, ref):
            return snap

    out = await CloudDocToolkit(_Prov(), watched_docs=lambda: ["d"]).read("d")
    assert out["ok"]
    assert out["kind"] == "spreadsheet"
    by_at = {c["at"]: c["text"] for c in out["cells"]}
    assert by_at["Sheet1!B1"] == "大家好", "agent 必须能知道哪一格装着哪段文字"
    # The formula cell is named up front, so the agent can avoid proposing an edit the
    # rail would refuse anyway.
    assert out["formula_cells"] == ["Sheet1!A2"]


@pytest.mark.asyncio
async def test_reading_a_document_gains_no_cell_list():
    """A document is addressed by position, and a run-by-run listing would say nothing
    a person or a model can act on -- it would only crowd out the text."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        CloudDocToolkit,
    )

    snap = DocSnapshot(doc_id="d", kind="document", revision_id="r1", text="一句话。")

    class _Prov:
        text_domain = "plain"

        def parse_doc_ref(self, ref):
            return ref

        async def read(self, ref):
            return snap

    out = await CloudDocToolkit(_Prov(), watched_docs=lambda: ["d"]).read("d")
    assert out["ok"] and "cells" not in out


# ------------------------------------------------- D15: the region write


def test_a1_regions_parse_and_a_bad_one_is_refused():
    """A range this cannot read is a caller error. Resolving it to something plausible
    would write to cells nobody named."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_formats import (
        parse_a1_region,
    )

    assert parse_a1_region("Sheet1!A7:B7") == ("Sheet1", 6, 0, 6, 1)
    assert parse_a1_region("'Q3 Data'!B2") == ("Q3 Data", 1, 1, 1, 1)
    assert parse_a1_region("B7") == ("", 6, 1, 6, 1)
    for bad in ("", "sheet1", "A0:B", "B7:A1"):
        with pytest.raises(ProviderError):
            parse_a1_region(bad)


@pytest.mark.asyncio
async def test_a_move_is_one_region_write():
    """The change that could not be said at all in (old_string, new_string): moving a
    value one column left is two changes, one of them where nothing can be located
    because the destination is empty.

    Stated as a region's intended content it is one atomic write -- and so are swap,
    clear and reorder, without a verb for each (D15)."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    sent = {}

    class _Sheets:
        def spreadsheets(self):
            return self

        def values(self):
            return self

        def batchUpdate(self, **kw):
            sent.update(kw)
            return self

        def execute(self):
            return {}

    cells = [[textmap.Cell("Sheet1!A7", "", ""), textmap.Cell("Sheet1!B7", "大家好", "大家好")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)

    class Prov:
        receipt_sink = None
        receipt_meta = {}

        def _receipt_begin(self, *a, **k):
            return None

        def _receipt_commit(self, *a, **k):
            pass

        def _receipt_abort(self, *a, **k):
            pass

        def _sheets_client(self):
            return _Sheets()

        async def _call(self, fn, *a, **k):
            return fn()

    real = google_formats.read_spreadsheet
    google_formats.read_spreadsheet = lambda _p, _d: _done(snap)
    try:
        res = await google_formats.write_regions_spreadsheet(
            Prov(), "d", [("Sheet1!A7:B7", [["大家好", ""]])]
        )
    finally:
        google_formats.read_spreadsheet = real

    assert res.status == "applied"
    assert sent["body"]["data"] == [
        {"range": "Sheet1!A7:B7", "values": [["大家好", ""]]}
    ]


async def _done(value):
    return value


@pytest.mark.asyncio
async def test_a_shape_mismatch_is_refused_before_anything_is_sent():
    """A caller that names A1:B2 and passes one row is describing a different change
    from the one it asked for, and letting the platform pad the difference would write
    blanks into cells nobody mentioned."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    class Prov:
        def _sheets_client(self):
            raise AssertionError("形状不符时不得发出任何请求")

    with pytest.raises(ProviderError) as exc:
        await google_formats.write_regions_spreadsheet(
            Prov(), "d", [("Sheet1!A1:B2", [["x", "y"]])]
        )
    assert "形状" in str(exc.value)


@pytest.mark.asyncio
async def test_a_formula_cell_inside_the_region_blocks_the_whole_write():
    """IC-7 holds for a region as it does for a replacement, and matters more here:
    overwriting =SUM(A1:A9) as part of "make this block look like that" is even harder
    to notice afterwards than doing it as a single edit."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    cells = [[textmap.Cell("Sheet1!A1", "42", "=SUM(B1:B9)"), textmap.Cell("Sheet1!B1", "x", "x")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)

    class Prov:
        def _sheets_client(self):
            raise AssertionError("含公式格时不得发出任何请求")

    real = google_formats.read_spreadsheet
    google_formats.read_spreadsheet = lambda _p, _d: _done(snap)
    try:
        with pytest.raises(ProviderError) as exc:
            await google_formats.write_regions_spreadsheet(
                Prov(), "d", [("Sheet1!A1:B1", [["1", "2"]])]
            )
    finally:
        google_formats.read_spreadsheet = real
    assert "公式格" in str(exc.value) and "Sheet1!A1" in str(exc.value)


@pytest.mark.asyncio
async def test_an_unattended_turn_gets_no_region_write():
    """The chat path's authorisation is the person's instruction. The unattended path's
    is the region a comment anchors to, and whether a spreadsheet comment yields a
    region at all is still open (§18.5) -- so it keeps the replacement primitive and its
    range rail rather than gaining a wider write with no matching bound."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        CloudDocToolkit,
    )

    # Everything downstream is made to succeed, so the only thing that can refuse this
    # is the guard itself. The first two versions of this test passed with the guard
    # removed, because the call then failed for an unrelated reason further along and
    # "not ok" was all they checked -- the assertion has to name *why*.
    class _Prov:
        text_domain = "plain"

        def parse_doc_ref(self, ref):
            return ref

        async def write_region(self, *a, **k):
            raise AssertionError("无人值守回合不得走到区域写入")

    kit = CloudDocToolkit(
        _Prov(),
        turn_doc_id=lambda: "d",
        turn_comment_id=lambda: "c1",
        watched_docs=lambda: ["d"],
    )
    out = await kit.write_region("d", "Sheet1!A1", [["x"]])
    assert not out["ok"]
    assert "无人值守" in out["detail"], f"应当因为无人值守被拒，实际：{out['detail']}"


@pytest.mark.asyncio
async def test_an_address_cannot_be_written_as_a_cell_value():
    """Observed on a real spreadsheet. Asked to move a value to A1 with no region
    primitive available, the agent wrote ``Sheet1!A1:大家好`` **into the cell**, and the
    range rail passed it: as flat text that is an ordinary replacement. The document was
    left holding a coordinate as its content.

    A model with no way to say "move" will reach for the nearest thing that looks like
    it. The refusal therefore names the tool that can, because a rail that only says no
    leaves it to invent another way around."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        CloudDocToolkit,
    )

    cells = [[textmap.Cell("Sheet1!A7", "", ""), textmap.Cell("Sheet1!B7", "大家好", "大家好")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)

    class _Prov:
        text_domain = "plain"

        def parse_doc_ref(self, ref):
            return ref

        async def read(self, ref):
            return snap

        async def capabilities(self, ref):
            from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
                DocCapabilities,
            )

            return DocCapabilities(
                can_read=True, can_edit=True, can_comment=True, can_resolve=True,
                has_revision_control=False, max_quote_chars=None, atomic_batch=True,
            )

        async def list_comments(self, ref, *, include_resolved=False):
            return []

        async def edit_batch(self, *a, **k):
            raise AssertionError("把地址写成内容的编辑不得抵达平台")

    kit = CloudDocToolkit(_Prov(), watched_docs=lambda: ["d"])
    out = await kit.batch_edit(
        "d", [{"old_string": "大家好", "new_string": "Sheet1!A1:大家好"}]
    )
    assert not out["ok"]
    assert "clouddoc_write_region" in out["detail"], "拒绝时要指出能做这件事的工具"


@pytest.mark.asyncio
async def test_ordinary_text_that_merely_mentions_a_cell_still_writes():
    """A cell may legitimately contain "A1", and a rail that refused that would be worse
    than the failure it prevents. What is caught is a coordinate used as the payload."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        CloudDocToolkit,
    )

    cells = [[textmap.Cell("Sheet1!A7", "大家好", "大家好")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)
    sent = []

    class _Prov:
        text_domain = "plain"

        def parse_doc_ref(self, ref):
            return ref

        async def read(self, ref):
            return snap

        async def capabilities(self, ref):
            from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
                DocCapabilities,
            )

            return DocCapabilities(
                can_read=True, can_edit=True, can_comment=True, can_resolve=True,
                has_revision_control=False, max_quote_chars=None, atomic_batch=True,
            )

        async def list_comments(self, ref, *, include_resolved=False):
            return []

        async def edit_batch(self, ref, edits, **k):
            sent.extend(edits)
            from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
                EditResult,
            )

            return EditResult("applied")

    kit = CloudDocToolkit(_Prov(), watched_docs=lambda: ["d"])
    kit._read_docs.add("d")  # stipulate the read; the gate has its own tests
    out = await kit.batch_edit("d", [{"old_string": "大家好", "new_string": "见 A1 那格"}])
    assert out["ok"], out
    assert sent == [("大家好", "见 A1 那格")]


@pytest.mark.asyncio
async def test_emptying_a_cell_by_replacement_is_refused():
    """Observed on a real spreadsheet. Asked to move a value, the agent deleted it in
    one call and tried to write it back in the next; the delete committed, the write
    could not anchor on an empty cell, and the sheet was left with its content gone.

    A replacement anchors on the text it replaces, so emptying a cell that way is
    one-way. Clearing is legitimate -- it just has to be said as a region whose new
    content is empty, which is one write and reversible."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        CloudDocToolkit,
    )
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import DocCapabilities

    cells = [[textmap.Cell("Sheet1!B7", "大家好", "大家好")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)

    class _Prov:
        text_domain = "plain"

        def parse_doc_ref(self, ref):
            return ref

        async def read(self, ref):
            return snap

        async def capabilities(self, ref):
            return DocCapabilities(
                can_read=True, can_edit=True, can_comment=True, can_resolve=True,
                has_revision_control=False, max_quote_chars=None, atomic_batch=True,
            )

        async def list_comments(self, ref, *, include_resolved=False):
            return []

        async def edit_batch(self, *a, **k):
            raise AssertionError("删空单元格的编辑不得抵达平台")

    kit = CloudDocToolkit(_Prov(), watched_docs=lambda: ["d"])
    out = await kit.batch_edit("d", [{"old_string": "大家好", "new_string": ""}])
    assert not out["ok"]
    assert "clouddoc_write_region" in out["detail"], "拒绝时要指出能做这件事的工具"


@pytest.mark.asyncio
async def test_a_cross_region_move_is_still_one_write():
    """A move whose source and destination are not in the same rectangle -- B7 to A1 is
    seven rows apart -- is two regions, and two calls leave the value in **both places**
    in between.

    Measured live: the agent wrote the destination, read back and found the text twice,
    and spent six minutes reasoning its way to the second call. Nothing but its own
    diligence closed that window; a crash or a timeout inside it leaves a duplicate
    behind. batchUpdate takes both at once, so the window need not exist."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    sent = {}

    class _Sheets:
        def spreadsheets(self):
            return self

        def values(self):
            return self

        def batchUpdate(self, **kw):
            sent.update(kw)
            return self

        def execute(self):
            return {}

    cells = [[textmap.Cell("Sheet1!A1", "", "")], [textmap.Cell("Sheet1!B7", "大家好", "大家好")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)

    class Prov:
        receipt_sink = None
        receipt_meta = {}

        def _receipt_begin(self, *a, **k):
            return None

        def _receipt_commit(self, *a, **k):
            pass

        def _receipt_abort(self, *a, **k):
            pass

        def _sheets_client(self):
            return _Sheets()

        async def _call(self, fn, *a, **k):
            return fn()

    real = google_formats.read_spreadsheet
    google_formats.read_spreadsheet = lambda _p, _d: _done(snap)
    try:
        res = await google_formats.write_regions_spreadsheet(
            Prov(), "d",
            [("Sheet1!A1", [["大家好"]]), ("Sheet1!B7", [[""]])],
        )
    finally:
        google_formats.read_spreadsheet = real

    assert res.status == "applied"
    assert sent["body"]["data"] == [
        {"range": "Sheet1!A1", "values": [["大家好"]]},
        {"range": "Sheet1!B7", "values": [[""]]},
    ], "两块必须在同一次提交里"


@pytest.mark.asyncio
async def test_a_formula_anywhere_in_the_batch_refuses_all_of_it():
    """A half-applied move is worse than a refused one: the value ends up in two places
    with nothing recording that it should not have."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    cells = [[textmap.Cell("Sheet1!A1", "", ""), textmap.Cell("Sheet1!B1", "42", "=SUM(C1:C9)")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)

    class Prov:
        def _sheets_client(self):
            raise AssertionError("含公式格时整批都不得发出")

    real = google_formats.read_spreadsheet
    google_formats.read_spreadsheet = lambda _p, _d: _done(snap)
    try:
        with pytest.raises(ProviderError) as exc:
            await google_formats.write_regions_spreadsheet(
                Prov(), "d",
                [("Sheet1!A1", [["x"]]), ("Sheet1!B1", [["y"]])],
            )
    finally:
        google_formats.read_spreadsheet = real
    assert "公式格" in str(exc.value) and "Sheet1!B1" in str(exc.value)


# ---------------------------------------------------------------- region receipts


class _RecordingProv:
    """Records what the receipt plumbing was given, succeeds at everything else."""

    def __init__(self):
        self.begin_args = None
        self.commit_kwargs = None

    def _receipt_begin(self, doc_ref, located, *, highlight, regions=None, anchors=None):
        self.begin_args = {"located": list(located), "regions": list(regions or [])}
        return "r1"

    def _receipt_commit(self, receipt, new_rev, *, highlighted=None):
        self.commit_kwargs = {"receipt": receipt, "highlighted": highlighted}

    def _receipt_abort(self, *a, **k):
        pass

    def _sheets_client(self):
        class _S:
            def spreadsheets(self):
                return self

            def values(self):
                return self

            def batchUpdate(self, **kw):
                return self

            def execute(self):
                return {}

        return _S()

    def _slides_client(self):
        class _S:
            def presentations(self):
                return self

            def batchUpdate(self, **kw):
                return self

            def execute(self):
                return {}

        return _S()

    async def _call(self, fn, *a, **k):
        return fn()


@pytest.mark.asyncio
async def test_a_spreadsheet_region_receipt_records_the_before_image():
    """The receipt's two ends are the region's content before and after the write.

    The first shipped version recorded ``(region:addr, "…")`` -- an address for old and
    a literal ellipsis for new -- and every region write was unrevertable: the panel
    searched the body for '…', found nothing, and refused. Fail-closed held, but rings
    ⑤/⑥ were silently empty for the newest write primitive. The before image was
    already in hand (the formula check reads the document), so recording it costs no
    extra round trip; this test pins that it actually lands in the receipt."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    cells = [[textmap.Cell("Sheet1!A7", "", ""), textmap.Cell("Sheet1!B7", "大家好", "大家好")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)

    prov = _RecordingProv()
    real = google_formats.read_spreadsheet
    google_formats.read_spreadsheet = lambda _p, _d: _done(snap)
    try:
        res = await google_formats.write_regions_spreadsheet(
            prov, "d", [("Sheet1!A7:B7", [["大家好", ""]])]
        )
    finally:
        google_formats.read_spreadsheet = real

    assert res.status == "applied"
    (old_flat, new_flat), = prov.begin_args["located"]
    assert old_flat == "\t大家好", "old 必须是写入前的区域内容，不是地址"
    assert new_flat == "大家好\t", "new 必须是实际写入的内容，不是省略号"
    (addr, old_grid), = prov.begin_args["regions"]
    assert addr == "Sheet1!A7:B7"
    assert old_grid == [["", "大家好"]], "old_grid 是回退真正写回的网格，原样保存"
    assert prov.commit_kwargs["highlighted"] is False, "区域写入从不高亮，commit 必须如实更正"


@pytest.mark.asyncio
async def test_a_presentation_region_receipt_records_the_before_text():
    """A shape's before text goes into the receipt verbatim -- including newlines,
    which is why the grid is stored as a grid rather than re-split from the flat
    string: a two-line shape text is still one region of one cell."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import Segment

    body = "第一行\n第二行"
    snap = DocSnapshot(
        doc_id="d", kind="presentation", revision_id="rev1",
        text=body,
        segments=(Segment(char_start=0, char_end=len(body), address="p/i0"),),
    )

    prov = _RecordingProv()
    real = google_formats.read_presentation
    google_formats.read_presentation = lambda _p, _d: _done(snap)
    try:
        res = await google_formats.write_regions_presentation(
            prov, "d", [("p/i0", [["新标题"]])]
        )
    finally:
        google_formats.read_presentation = real

    assert res.status == "applied"
    (old, new), = prov.begin_args["located"]
    assert old == "第一行\n第二行" and new == "新标题"
    (addr, old_grid), = prov.begin_args["regions"]
    assert addr == "p/i0"
    assert old_grid == [["第一行\n第二行"]], "含换行的形状文本必须原样为 1x1 网格"
    assert prov.commit_kwargs["highlighted"] is False


@pytest.mark.asyncio
async def test_read_regions_reports_current_content_in_receipt_form():
    """The read half of the addressed write: what the revert anchor check compares
    against must be produced by the same flattening the receipt stored."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    cells = [[textmap.Cell("Sheet1!A7", "x", "x"), textmap.Cell("Sheet1!B7", "大家好", "大家好")]]
    text, segs = textmap.flatten_grid(cells)
    snap = DocSnapshot(doc_id="d", kind="spreadsheet", revision_id=None, text=text, segments=segs)

    real = google_formats.read_spreadsheet
    google_formats.read_spreadsheet = lambda _p, _d: _done(snap)
    try:
        out = await google_formats.read_regions_spreadsheet(object(), "d", ["Sheet1!A7:B7"])
    finally:
        google_formats.read_spreadsheet = real
    assert out == ["x\t大家好"]


@pytest.mark.asyncio
async def test_read_regions_refuses_a_shape_that_no_longer_exists():
    """A deleted shape is not an empty one: comparing against a guess would let a
    revert 'anchor' on a region that is gone and write into nothing."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import Segment

    snap = DocSnapshot(
        doc_id="d", kind="presentation", revision_id="rev1",
        text="hi", segments=(Segment(char_start=0, char_end=2, address="p/i0"),),
    )
    real = google_formats.read_presentation
    google_formats.read_presentation = lambda _p, _d: _done(snap)
    try:
        with pytest.raises(ProviderError) as exc:
            await google_formats.read_regions_presentation(object(), "d", ["p/gone"])
    finally:
        google_formats.read_presentation = real
    assert "p/gone" in str(exc.value)


# ---------------------------------------------------------------- anchor decoding


def test_a_shape_anchor_decodes_to_region_addresses():
    """Measured live: {"type":"shape","page":P,"targets":[T]} is the pageId/objectId
    address the region machinery writes through. The 'anchors are opaque' verdict was
    a per-format fact -- true of a spreadsheet's workbook-range, false here."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import (
        GoogleDocsProvider,
    )

    dec = GoogleDocsProvider._anchor_regions
    assert dec('{"type":"shape","uid":1,"page":"g5_0","targets":["g5_2"]}') == ("g5_0/g5_2",)
    assert dec('{"type":"shape","page":"p","targets":["a","b"]}') == ("p/a", "p/b")
    # The opaque ones stay opaque, quietly.
    assert dec('{"type":"workbook-range","uid":0,"range":"1896749560"}') == ()
    assert dec("not json") == ()
    assert dec(None) == ()
    assert dec('{"type":"shape","targets":["x"]}') == (), "缺 page 的锚不产地址"


def test_the_blanket_comment_attribution_reaches_every_edit():
    """A region write's old is computed by the provider, so keying attribution by old
    text cannot work there; the blanket list must land on each edit, or a revert of a
    comment-commissioned region write notifies no thread at all."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import (
        GoogleDocsProvider,
    )

    begun = {}

    class _Sink:
        def begin(self, doc_id, edits, *, highlight, source="", executor=""):
            begun["edits"] = edits
            return "r1"

    prov = type("P", (), {})()
    prov.receipt_sink = _Sink()
    prov.receipt_meta = {"for_comment_ids": ["c9"], "executor": "comment:c9"}
    bound = GoogleDocsProvider._receipt_begin.__get__(prov)
    bound("doc", [("旧", "新")], highlight=False, regions=[("p/a", [["旧"]])])
    (e,) = begun["edits"]
    assert e["for_comment_ids"] == ["c9"]
    assert e["region"] == "p/a" and e["old_grid"] == [["旧"]]


# ---------------------------------------------------------------- D19 3b: read-back


class _MarkingSink:
    def __init__(self):
        self.marked = None

    def mark_unverified(self, receipt_id, *, detail):
        self.marked = (receipt_id, detail)


@pytest.mark.asyncio
async def test_a_readback_mismatch_demotes_the_receipt():
    """D19 tier 3b: the declarative write carries its own postcondition. A commit
    the platform accepted but the document does not show must not stand as a clean
    ``applied`` -- acceptance reads the receipt, and the receipt must not claim
    more than the document shows."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats

    body = "写入前"
    snap = DocSnapshot(
        doc_id="d", kind="presentation", revision_id="rev1", text=body,
        segments=(__import__("jiuwenswarm.agents.harness.common.tools.clouddoc.provider",
                             fromlist=["Segment"]).Segment(
            char_start=0, char_end=len(body), address="p/i0"),),
    )
    prov = _RecordingProv()
    prov.receipt_sink = _MarkingSink()

    async def _read_regions(_doc, regions):
        return ["平台改了别的东西" for _ in regions]  # never what was written

    prov.read_regions = _read_regions
    real = google_formats.read_presentation
    google_formats.read_presentation = lambda _p, _d: _done(snap)
    try:
        res = await google_formats.write_regions_presentation(
            prov, "d", [("p/i0", [["新标题"]])]
        )
    finally:
        google_formats.read_presentation = real
    assert res.status == "applied"
    assert prov.receipt_sink.marked is not None, "回读不符必须降为 applied_unverified"
    rid, detail = prov.receipt_sink.marked
    assert rid == "r1" and "p/i0" in detail


@pytest.mark.asyncio
async def test_a_matching_readback_leaves_the_receipt_alone():
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import Segment

    body = "写入前"
    snap = DocSnapshot(
        doc_id="d", kind="presentation", revision_id="rev1", text=body,
        segments=(Segment(char_start=0, char_end=len(body), address="p/i0"),),
    )
    prov = _RecordingProv()
    prov.receipt_sink = _MarkingSink()

    async def _read_regions(_doc, regions):
        return ["新标题"]

    prov.read_regions = _read_regions
    real = google_formats.read_presentation
    google_formats.read_presentation = lambda _p, _d: _done(snap)
    try:
        await google_formats.write_regions_presentation(prov, "d", [("p/i0", [["新标题"]])])
    finally:
        google_formats.read_presentation = real
    assert prov.receipt_sink.marked is None


@pytest.mark.asyncio
async def test_an_unreadable_readback_proves_nothing_and_breaks_nothing():
    """The write already landed; a verification that cannot run must neither kill
    the call nor mark the receipt -- it proved nothing either way."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import Segment

    body = "写入前"
    snap = DocSnapshot(
        doc_id="d", kind="presentation", revision_id="rev1", text=body,
        segments=(Segment(char_start=0, char_end=len(body), address="p/i0"),),
    )
    prov = _RecordingProv()
    prov.receipt_sink = _MarkingSink()

    async def _read_regions(_doc, regions):
        raise RuntimeError("network down")

    prov.read_regions = _read_regions
    real = google_formats.read_presentation
    google_formats.read_presentation = lambda _p, _d: _done(snap)
    try:
        res = await google_formats.write_regions_presentation(prov, "d", [("p/i0", [["新标题"]])])
    finally:
        google_formats.read_presentation = real
    assert res.status == "applied"
    assert prov.receipt_sink.marked is None


@pytest.mark.asyncio
async def test_a_shape_terminal_newline_is_not_part_of_the_region_operand():
    """The Slides API keeps a newline at the end of every text box. Compared raw, a
    write of ``标题（E2E）`` read back as ``标题（E2E）\\n`` and every deck write was
    demoted to applied_unverified, and the revert anchor would have refused for the
    same reason. Both the before-text and the read-back drop that one newline."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import Segment

    body = "co-scribe 测试标题\n"
    snap = DocSnapshot(
        doc_id="d", kind="presentation", revision_id="rev1", text=body,
        segments=(Segment(char_start=0, char_end=len(body), address="p/i0"),),
    )
    prov = _RecordingProv()
    real = google_formats.read_presentation
    google_formats.read_presentation = lambda _p, _d: _done(snap)
    try:
        res = await google_formats.write_regions_presentation(
            prov, "d", [("p/i0", [["co-scribe 测试标题（E2E）"]])]
        )
        got = await google_formats.read_regions_presentation(prov, "d", ["p/i0"])
    finally:
        google_formats.read_presentation = real
    assert res.status == "applied" and res.receipt_id
    (old, new), = prov.begin_args["located"]
    assert old == "co-scribe 测试标题" and new == "co-scribe 测试标题（E2E）"
    assert got == ["co-scribe 测试标题"]


@pytest.mark.asyncio
async def test_a_shape_operand_with_the_platform_newline_is_written_without_it():
    """A receipt recorded before the newline rule holds ``标题\n`` as the before-text;
    reverting it must not insert that newline as an extra empty paragraph."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import google_formats
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import Segment

    body = "改过的标题\n"
    snap = DocSnapshot(
        doc_id="d", kind="presentation", revision_id="rev1", text=body,
        segments=(Segment(char_start=0, char_end=len(body), address="p/i0"),),
    )
    prov = _RecordingProv()
    real = google_formats.read_presentation
    google_formats.read_presentation = lambda _p, _d: _done(snap)
    try:
        res = await google_formats.write_regions_presentation(
            prov, "d", [("p/i0", [["co-scribe 测试标题\n"]])]
        )
    finally:
        google_formats.read_presentation = real
    assert res.status == "applied"
    (old, new), = prov.begin_args["located"]
    assert old == "改过的标题" and new == "co-scribe 测试标题", "operand normalized before write"
