"""The formats past a plain document: spreadsheets and decks.

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


import pytest

from jiuwenswarm.clouddoc.providers import textmap
from jiuwenswarm.clouddoc.providers.base import (
    DocSnapshot,
    ProviderError,
)


def test_the_feishu_write_never_pins_a_revision():
    """Pinning is worse than having no lock: a concurrent edit stops being a refused
    write and becomes a destroyed one."""
    from jiuwenswarm.clouddoc.providers.feishu import provider as feishu_provider
    import inspect

    src = inspect.getsource(feishu_provider)
    assert '"--revision-id"' not in src


def test_the_canonical_tool_list_matches_what_the_toolkit_builds():
    """Four places need this list -- the toolkit, the team whitelist, the scene hook and
    the permission config -- and each kept its own copy. A copy drifts silently: a tool
    missing from the team whitelist just does not appear, filtered at debug level.

    The drift had already happened when the list was first written down in one place:
    the design's as-built section named seven tools and the toolkit built nine, the
    workmode pair having arrived with PR2a without the count following."""
    from jiuwenswarm.clouddoc.tools.toolkit import (
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


@pytest.mark.asyncio
async def test_reading_a_spreadsheet_reports_cell_addresses():
    """The flat text is what the range rail anchors on, and for a grid it is not enough
    on its own.

    Measured live: a comment asked to "move this to A1", the read returned
    ``'\\n\\n\\n\\n\\n\\n\\t大家好'``, and the agent reasoned for thirteen minutes trying to
    work out which cell that was -- while ``Segment.address`` held ``Sheet1!B7`` the
    whole time and nothing passed it on. Tabs and newlines are not coordinates."""
    from jiuwenswarm.clouddoc.tools.toolkit import (
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
    from jiuwenswarm.clouddoc.tools.toolkit import (
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


@pytest.mark.asyncio
async def test_a_move_is_one_region_write():
    """The change that could not be said at all in (old_string, new_string): moving a
    value one column left is two changes, one of them where nothing can be located
    because the destination is empty.

    Stated as a region's intended content it is one atomic write -- and so are swap,
    clear and reorder, without a verb for each (D15)."""
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

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
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

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
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

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
    is the region a comment anchors to, and a spreadsheet comment yields at most one
    cell (§18.5, measured 2026-09-10) -- so it keeps the replacement primitive and its
    range rail rather than gaining a wider write with no matching bound."""
    from jiuwenswarm.clouddoc.tools.toolkit import (
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
    from jiuwenswarm.clouddoc.tools.toolkit import (
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
            from jiuwenswarm.clouddoc.providers.base import (
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
    from jiuwenswarm.clouddoc.tools.toolkit import (
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
            from jiuwenswarm.clouddoc.providers.base import (
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
            from jiuwenswarm.clouddoc.providers.base import (
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
    from jiuwenswarm.clouddoc.tools.toolkit import (
        CloudDocToolkit,
    )
    from jiuwenswarm.clouddoc.providers.base import DocCapabilities

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
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

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
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

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
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

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
    assert old_grid == [["", "大家好"]], "old_grid 是写入前的网格，原样保存供审计"
    assert prov.commit_kwargs["highlighted"] is False, "区域写入从不高亮，commit 必须如实更正"


@pytest.mark.asyncio
async def test_a_presentation_region_receipt_records_the_before_text():
    """A shape's before text goes into the receipt verbatim -- including newlines,
    which is why the grid is stored as a grid rather than re-split from the flat
    string: a two-line shape text is still one region of one cell."""
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats
    from jiuwenswarm.clouddoc.providers.base import Segment

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
    """The read half of the addressed write: what the read-back check compares
    against must be produced by the same flattening the receipt stored."""
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

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
    read-back 'match' a region that is gone and call the write verified."""
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats
    from jiuwenswarm.clouddoc.providers.base import Segment

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
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

    body = "写入前"
    snap = DocSnapshot(
        doc_id="d", kind="presentation", revision_id="rev1", text=body,
        segments=(__import__("jiuwenswarm.clouddoc.providers.base",
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
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats
    from jiuwenswarm.clouddoc.providers.base import Segment

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
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats
    from jiuwenswarm.clouddoc.providers.base import Segment

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
    demoted to applied_unverified. Both the before-text and the read-back drop that one
    newline."""
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats
    from jiuwenswarm.clouddoc.providers.base import Segment

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
    """An operand carrying the platform's trailing newline -- copied from an old
    receipt's before-text, say -- is written without it, or the box gains an empty
    paragraph."""
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats
    from jiuwenswarm.clouddoc.providers.base import Segment

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


def test_the_served_list_and_the_unsupported_list_stay_complements():
    """One statement said twice -- once in Drive's vocabulary, once in ours.

    The panel's "shared but not supported" list is built by negating the served
    MIME list, so a format that leaves one arrives on the other in the same edit.
    That is what stops a document being listed by one path and refused by the next,
    which is the half-working state this feature exists to prevent.
    """
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats
    from jiuwenswarm.clouddoc.providers.google.provider import (
        GoogleDocsProvider,
    )
    from jiuwenswarm.clouddoc.providers.base import (
        SUPPORTED_KINDS,
    )

    served = {google_formats.kind_for(m) for m in GoogleDocsProvider._SUPPORTED_MIMES}
    assert served == set(SUPPORTED_KINDS)
    # The formats a markdown file can arrive as, both measured on real uploads.
    for mime in ("text/markdown", "text/x-markdown", "text/plain"):
        assert google_formats.kind_for(mime) == "", mime


@pytest.mark.asyncio
async def test_the_cell_prefix_is_stripped_on_the_watcher_s_cold_path():
    """The format is resolved inside list_comments, not read from a cache it never fills.

    The first version of this fix keyed on the kind cache, which the read path fills.
    The watcher lists comments **before** it reads anything, so on its path the cache
    was empty, a spreadsheet looked like a document, the address prefix stayed on the
    quote, and the anchoring bug survived exactly where it does the most damage --
    unattended, with nobody watching the refusal.
    """
    from jiuwenswarm.clouddoc.providers.feishu import provider as fp

    calls: list[str] = []

    class _P(fp.FeishuDocsProvider):
        def __init__(self):
            super().__init__(profile="p")

        async def doc_kind(self, doc_ref):
            calls.append("doc_kind")
            return "spreadsheet"

        async def _drive_json(self, doc_ref, make_args):
            return {"items": [{
                "comment_id": "c1",
                "quote": "D2 16oAxy",
                "reply_list": {"replies": []},
            }]}

    got = await _P().list_comments("T")
    assert calls == ["doc_kind"], "格式必须在解析引用之前解析出来"
    assert got[0].quoted_text == "16oAxy", got[0].quoted_text


def test_a_new_slide_states_its_layout():
    """A created slide must ask for title-and-body, not take what the platform picks.

    Observed 2026-09-10: with the layout unstated, Google chose a single-placeholder
    slide, so a three-page deck came out with page one holding a title box and a body
    box (it predated the agent) while pages two and three crammed the heading and its
    bullets into one box each -- three pages that read as three different decks.
    """
    import inspect
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

    src = inspect.getsource(google_formats.add_page_presentation)
    assert "slideLayoutReference" in src
    assert "TITLE_AND_BODY" in src


def test_feishu_slide_creation_states_geometry_and_uses_the_object_token():
    """Both facts were learned the hard way and neither is guessable from the docs.

    The platform refuses a ``<shape>`` without geometry -- ``topLeftX is not a valid
    float number`` -- so a page has to be described with real coordinates or it cannot
    be created at all. And every slides verb takes the deck's **object** token, not the
    wiki node that hosts it: a deck adopted by its /wiki/ link answered ``3350002 not
    found`` to every read until the resolution already in hand was actually used.

    The entry existed as an explicit refusal before this -- "this platform does not
    support adding pages" -- written without running ``lark-cli slides --help``, which
    lists ``+add-slide``. A platform limitation asserted rather than measured is a false
    fact that outlives the session it was written in.
    """
    import inspect
    from jiuwenswarm.clouddoc.providers.feishu import formats as feishu_formats

    assert "presentation" in feishu_formats.ADD_PAGE
    src = inspect.getsource(feishu_formats.add_page_presentation)
    for needed in ("topLeftX", "topLeftY", "width=", "height=", "+add-slide"):
        assert needed in src, needed
    assert "_resolved_object_token" in src


class _WikiCli:
    """A lark-cli stand-in that answers the wiki verbs discovery now uses."""

    def __init__(self, *, blocked=False, nodes=None):
        self.blocked = blocked
        self.nodes = nodes or []
        self.calls: list[list[str]] = []

    async def json(self, args):
        from jiuwenswarm.clouddoc.providers.base import ProviderError
        self.calls.append(list(args))
        if args[:2] == ["wiki", "+node-get"]:
            return {"node": {"space_id": "7680656053523975124", "node_token": args[3],
                             "obj_token": "OBJ" + args[3], "obj_type": "slides"}}
        if args[:2] == ["wiki", "+node-list"]:
            if self.blocked:
                raise ProviderError("forbidden", "131006 bot lacks permission for the requested resource")
            # The real envelope: ``has_more`` beside ``nodes`` -- not ``items``.
            return {"has_more": False, "nodes": self.nodes}
        raise AssertionError(f"unexpected verb {args[:2]}")


def _feishu_with(cli, wiki_tokens=()):
    from jiuwenswarm.clouddoc.providers.feishu.provider import FeishuDocsProvider
    p = FeishuDocsProvider(profile="p")
    p._cli = cli
    p._wiki_tokens.update(wiki_tokens)
    p._url_cache["seed"] = "https://tenant.feishu.cn/wiki/seed"
    return p


@pytest.mark.asyncio
async def test_feishu_discovery_walks_the_wiki_space_of_managed_nodes():
    """Enumeration on this platform is a wiki space, derived from what is managed.

    ``drive +list-files`` does not exist and ``drive +search`` answers a bot with
    nothing under every filter (measured 2026-09-10), so the only listing a bot can
    do is ``wiki +node-list`` on a space it belongs to. The space is not configured:
    each managed wiki node names its own space through ``+node-get``.
    """
    cli = _WikiCli(nodes=[
        {"node_token": "N1", "obj_token": "O1", "obj_type": "docx", "title": "甲"},
        {"node_token": "N2", "obj_token": "O2", "obj_type": "sheet", "title": "乙"},
        {"node_token": "N3", "obj_token": "O3", "obj_type": "mindnote", "title": "丙"},
    ])
    p = _feishu_with(cli, wiki_tokens={"SEEDNODE"})
    got = await p.list_accessible_documents()
    assert [(d.doc_id, d.kind) for d in got] == [("N1", "document"), ("N2", "spreadsheet")]
    assert p.discovery_available is True and p.discovery_reason == ""
    # The object token is learned here too, so the slides API is never handed a node.
    assert p._object_tokens["N1"] == "O1"
    assert p._url_cache["N1"] == "https://tenant.feishu.cn/wiki/N1"
    # An unsupported format is reported, not silently dropped.
    assert p._unsupported["N3"] == ("丙", "mindnote")
    assert ["wiki", "+node-list", "--space-id", "7680656053523975124", "--page-all"] in cli.calls


@pytest.mark.asyncio
async def test_feishu_discovery_names_the_space_when_the_bot_is_not_a_member():
    """The degrade says what to do, and which space -- membership is the owner's one step.

    Observed live: a bot with document-level access to three nodes is not a member of
    their space, and the listing answers ``131006``. "The API does not support it"
    was the earlier wording; it was true of a verb that no longer exists and sent
    people to paste links forever.
    """
    p = _feishu_with(_WikiCli(blocked=True), wiki_tokens={"SEEDNODE"})
    assert await p.list_accessible_documents() == []
    assert p.discovery_available is False
    assert "7680656053523975124" in p.discovery_reason
    assert "成员" in p.discovery_reason


@pytest.mark.asyncio
async def test_feishu_discovery_without_any_wiki_node_says_so():
    p = _feishu_with(_WikiCli())
    assert await p.list_accessible_documents() == []
    assert p.discovery_available is False and "wiki" in p.discovery_reason


@pytest.mark.asyncio
async def test_feishu_discovery_on_a_cold_process_starts_from_the_managed_list():
    """No cache, no prior probe: the managed tokens alone are enough to find the space.

    The running service showed the failure this closes: the panel fed stored kinds
    back through ``note_kind`` (no metadata call), the object-token cache stayed empty,
    and the boot-time discovery pass reported "no wiki documents" over a space that
    held three -- silently, until the next 300-second tick or a manual refresh.
    """
    cli = _WikiCli(nodes=[{"node_token": "N1", "obj_token": "O1", "obj_type": "docx", "title": "甲"}])
    p = _feishu_with(cli)                      # nothing seeded in any cache
    got = await p.list_accessible_documents(known=["MANAGED_NODE"])
    assert [d.doc_id for d in got] == ["N1"]
    assert ["wiki", "+node-get", "--node-token", "MANAGED_NODE"] in cli.calls


@pytest.mark.asyncio
async def test_a_created_worksheet_is_answered_in_the_address_form_read_reports():
    """``read`` reports ``'Q3 Data'!A1``; the region writer sends the caller's address to
    the API verbatim. A bare title with a space handed the model an address that failed
    on its first write."""
    from jiuwenswarm.clouddoc.providers.google import formats as google_formats

    class _Sheets:
        def __init__(self, title):
            self.title = title

        def spreadsheets(self):
            return self

        def batchUpdate(self, **kw):
            return self

        def execute(self):
            return {"replies": [{"addSheet": {"properties": {"title": self.title}}}]}

    class _Prov:
        def __init__(self, title):
            self._title = title

        def _sheets_client(self):
            return _Sheets(self._title)

        async def _call(self, fn, *a, **kw):
            return fn(*a, **kw)

    assert await google_formats.add_page_spreadsheet(_Prov("Q3 Data"), "D", "Q3 Data") == "'Q3 Data'"
    assert await google_formats.add_page_spreadsheet(_Prov("Sheet2"), "D", "Sheet2") == "Sheet2"
