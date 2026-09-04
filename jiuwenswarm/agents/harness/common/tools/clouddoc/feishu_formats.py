"""The formats beyond a Feishu docx: markdown files and spreadsheets.

Same split as the Google side (§18.3) and for the same reason: a connection reaches
documents of several kinds, so the format belongs to the document rather than to the
provider. Each handler answers only how to flatten and how to write back; the rails
above are shared and untouched.

**Slides joined on live evidence (2026-09-02, overturning the earlier refusal).**
The old verdict rested on ``+update-slide`` being the only write ("elements omitted
here are removed") plus zero tenant runs. Both legs fell: ``+replace-slide`` performs
**element-level** replacement (measured: the target shape changes, siblings and their
ids stay), and six live shots on a bot-owned deck closed the question (§28 addendum
VIII). Writes here go through the region form only -- a shape is an address, exactly
the Google presentation shape (D18) -- and the text-replacement path refuses with
directions rather than falling through to the docx update.

The larger correction this module carries is not about formats at all. See
``has_revision_control`` in the provider: ``--revision-id`` is not an optimistic lock.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from jiuwenswarm.agents.harness.common.tools.clouddoc import textmap

# The A1 helpers and the region receipt/verify plumbing are format-neutral: they work
# over parse results and snapshot segments, never over a platform client. They live
# with the format module that first needed them and are shared rather than duplicated,
# so the receipt form of a region's content stays one convention across providers.
from jiuwenswarm.agents.harness.common.tools.clouddoc.google_formats import (
    _col_index,
    _grid_flat,
    _region_current_flat,
    _region_current_grid,
    _verify_written_regions,
    parse_a1_region,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    DocRef,
    DocSnapshot,
    EditResult,
    ProviderError,
)

# What ``drive +list-files`` calls each type. A markdown file is its own type here,
# unlike Drive where it is a plain file that happens to be named .md.
TYPE_DOCX = "docx"
TYPE_SHEET = "sheet"
TYPE_MARKDOWN = "markdown"
TYPE_SLIDES = "slides"

KIND_BY_TYPE = {
    TYPE_DOCX: "document",
    TYPE_SHEET: "spreadsheet",
    TYPE_MARKDOWN: "markdown",
    TYPE_SLIDES: "presentation",
}

# Reported to a person as something co-scribe can see but not work on, with the reason
# attached rather than left to be guessed. Slides left this list on 2026-09-02:
# element-level replacement was measured live and the format is served above.
UNSUPPORTED_REASON: dict[str, str] = {}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------- markdown


async def read_markdown(prov: Any, doc_ref: DocRef) -> DocSnapshot:
    data = await prov._cli.json(["markdown", "+fetch", "--file-token", doc_ref])
    body = _content_of(data)
    return DocSnapshot(
        doc_id=doc_ref,
        kind="markdown",
        # The content hash, standing in for a revision the platform does not offer.
        # Not a revision id: capabilities says has_revision_control=False and that is
        # the declaration the admission check reads (C9).
        revision_id=_digest(body),
        text=body,
        segments=textmap.flatten_markdown(body)[1],
    )


def _content_of(data: Any) -> str:
    """The markdown body out of whatever shape the CLI wrapped it in.

    Tried in order rather than assumed: the envelope is unwrapped by ``LarkCli.json``
    already, and what remains is either the string itself or an object holding it
    under one of a few plausible names. A shape that matches none of them raises,
    because returning "" would read as an empty document and an edit against an empty
    document appends to it.
    """
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("content", "markdown", "text", "body"):
            got = data.get(key)
            if isinstance(got, str):
                return got
            if isinstance(got, dict):
                inner = got.get("content")
                if isinstance(inner, str):
                    return inner
    raise ProviderError(
        "unknown",
        f"markdown +fetch 的返回形状无法识别：{json.dumps(data, ensure_ascii=False)[:200]}",
    )


async def write_markdown(
    prov: Any,
    doc_ref: DocRef,
    snap: DocSnapshot,
    edits: list[tuple[str, str]],
    _revision: str | None,
    window: tuple[int, int] | None = None,
) -> EditResult:
    """Apply the edits to the text and overwrite the file.

    Whole-file replacement, which makes the batch atomic and loses any concurrent
    edit in the same breath -- ``+overwrite`` takes no revision and there is nothing
    to pin even if it did. The file is re-fetched and compared first, which narrows
    the window to one round trip without closing it (D11).
    """
    fresh = await read_markdown(prov, doc_ref)
    if fresh.revision_id != snap.revision_id:
        return EditResult(
            status="conflict",
            detail="文件在读取之后被改动过。该格式只能整文件覆盖且没有乐观锁，"
            "继续写入会抹掉别人的修改，因此中止。请重新读取后再提。",
        )
    updated = textmap.apply_edits_to_text(snap.text, edits, window)
    receipt = prov._receipt_begin(doc_ref, edits, highlight=False)
    try:
        await prov._cli.json([
            "markdown", "+overwrite", "--file-token", doc_ref, "--content", updated,
        ])
    except ProviderError as exc:
        prov._receipt_abort(receipt, f"{exc.kind}: {exc}")
        raise
    new_rev = _digest(updated)
    prov._receipt_commit(receipt, new_rev)
    return EditResult("applied", new_revision_id=new_rev, receipt_id=receipt)


# ---------------------------------------------------------------- spreadsheet


async def read_spreadsheet(prov: Any, doc_ref: DocRef) -> DocSnapshot:
    """Flatten every sheet, reading value and formula together.

    ``+cells-get --include value,formula`` returns both faces in one call, which is
    what IC-7 compares: a cell whose stored formula differs from its displayed value
    is computed, and writing the displayed value back would replace the formula with a
    literal that looks identical.
    """
    meta = await prov._cli.json(
        ["sheets", "+workbook-info", "--spreadsheet-token", doc_ref]
    )
    rows: list[list[textmap.Cell]] = []
    for name, last_row, last_col in _sheets_of(meta):
        # ``--range`` is required, so the extent has to come from the workbook
        # listing; there is no "whole sheet" form. Verified against the binary: without
        # it the CLI answers ``validation`` / ``required flag(s) "range" not set``.
        got = await prov._cli.json([
            "sheets", "+cells-get",
            "--spreadsheet-token", doc_ref,
            "--sheet-name", name,
            "--range", f"A1:{_a1(last_col - 1)}{last_row}",
            "--include", "value,formula",
        ])
        rows.extend(_cells_of(got, name))
    text, segments = textmap.flatten_grid(rows)
    return DocSnapshot(
        doc_id=doc_ref,
        kind="spreadsheet",
        # ``sheets +revision-get`` reports one, and it is read for the check the write
        # makes before overwriting -- but no write command accepts it, so there is no
        # way to make the platform enforce it. Left out of the snapshot for the same
        # reason capabilities says False: a revision that cannot gate a write is not
        # revision control, and returning it here invites someone to treat it as such.
        revision_id=None,
        text=text,
        segments=segments,
    )


def _sheets_of(data: Any) -> list[tuple[str, int, int]]:
    """Each sub-sheet as (title, row count, column count).

    ``+workbook-info`` is documented as returning sheet_id, title and dimensions; the
    exact nesting of the dimensions is read defensively because no tenant has ever
    answered this call from here. A sheet whose extent cannot be read is skipped with
    its name kept out of the flattening rather than guessed at -- reading a range
    larger than the sheet returns padding that would become phantom cells in the flat
    text, and an edit could then be located in one.
    """
    items = data
    if isinstance(data, dict):
        for key in ("sheets", "items", "data"):
            got = data.get(key)
            if isinstance(got, list):
                items = got
                break
    if not isinstance(items, list):
        return []
    out: list[tuple[str, int, int]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("title") or item.get("name") or item.get("sheet_name")
        if not name:
            continue
        dims = item.get("grid_properties") or item.get("dimensions") or item
        rows = dims.get("row_count") or dims.get("rowCount") or dims.get("rows")
        cols = dims.get("column_count") or dims.get("columnCount") or dims.get("columns")
        try:
            rows_i, cols_i = int(rows), int(cols)
        except (TypeError, ValueError):
            continue
        if rows_i > 0 and cols_i > 0:
            out.append((str(name), rows_i, cols_i))
    return out


def _cells_of(data: Any, sheet: str) -> list[list[textmap.Cell]]:
    """One sheet's grid, as rows of cells carrying both faces.

    The CLI returns rows of cells; a cell is either a bare scalar or an object holding
    ``value`` and ``formula``. Both are handled because ``--include`` decides which,
    and a scalar simply means the two faces are the same.

    TENANT-VERIFY (2026-09-02, cli 1.0.89): the reply nests the grid one level
    deeper than documented -- ``ranges`` is a list of range objects, each holding its
    ``cells`` plus the ``actual_range`` the platform really answered. The caller asks
    one range per call, so the first entry is the answer, and its start anchors the
    cell addresses: assuming A1 would misaddress every cell of a clipped reply.
    """
    grid = data
    r0 = c0 = 0
    if isinstance(data, dict):
        ranges = data.get("ranges")
        if isinstance(ranges, list) and ranges and isinstance(ranges[0], dict):
            data = ranges[0]
            got_range = str(data.get("actual_range") or data.get("range") or "")
            m = re.match(r"^\$?([A-Z]+)\$?(\d+)", got_range.rpartition("!")[2])
            if m:
                c0, r0 = _col_index(m.group(1)), int(m.group(2)) - 1
        for key in ("cells", "values", "rows", "data"):
            got = data.get(key)
            if isinstance(got, list):
                grid = got
                break
    if not isinstance(grid, list):
        return []
    out: list[list[textmap.Cell]] = []
    for ri, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        cells = []
        for ci, raw in enumerate(row):
            if isinstance(raw, dict):
                shown = raw.get("value")
                stored = raw.get("formula")
            else:
                shown, stored = raw, None
            shown_s = "" if shown is None else str(shown)
            cells.append(
                textmap.Cell(
                    address=f"{sheet}!{_a1(c0 + ci)}{r0 + ri + 1}",
                    formatted=shown_s,
                    formula=shown_s if stored in (None, "") else str(stored),
                )
            )
        out.append(cells)
    return out


def _a1(col: int) -> str:
    out = ""
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


async def write_spreadsheet(
    prov: Any,
    doc_ref: DocRef,
    snap: DocSnapshot,
    edits: list[tuple[str, str]],
    _revision: str | None,
    window: tuple[int, int] | None = None,
) -> EditResult:
    """Rewrite one cell per edit, one command per cell.

    One command per cell, not a batch: the CLI's own batch says it is "fail-fast on
    the first failing sub-op (already-applied sub-ops are NOT rolled back)", so a
    multi-cell write is not atomic. That is why ``atomic_batch`` is False for this
    provider and why a multi-edit batch never reaches here -- the toolkit refuses it
    with a reason first (C9). A single edit is all this has to serve.
    """
    if not edits:
        return EditResult("applied")
    if len(edits) > 1:
        # Defence in depth: the refusal belongs upstream, and arriving here anyway
        # would mean writing cells one at a time with no way to undo the first if the
        # second fails -- on a document other people are looking at.
        return EditResult(
            "refused",
            detail="飞书表格的批量写入不是原子的（先失败即停，已写入的不回滚），"
            "因此一次只接受一处修改。",
        )
    planned = textmap.plan_edits(snap, edits, window)
    address, group = next(iter(planned.items()))
    by_address = {
        seg.address: snap.text[seg.char_start : seg.char_end] for seg in snap.segments
    }
    value = textmap.fold_edits(by_address[address], group)
    # rpartition, not partition: a sheet name may itself contain "!", while the A1
    # part after the last one never does. Splitting on the first would send the write
    # at a sheet that does not exist.
    sheet, _, a1 = address.rpartition("!")

    receipt = prov._receipt_begin(doc_ref, edits, highlight=False)
    try:
        await prov._cli.json([
            "sheets", "+cells-set",
            "--spreadsheet-token", doc_ref,
            "--sheet-name", sheet,
            "--range", f"{a1}:{a1}",
            "--cells", json.dumps([[{"value": value}]], ensure_ascii=False),
        ])
    except ProviderError as exc:
        prov._receipt_abort(receipt, f"{exc.kind}: {exc}")
        raise
    prov._receipt_commit(receipt, None)
    return EditResult("applied", new_revision_id="", receipt_id=receipt)


async def read_regions_spreadsheet(
    prov: Any, doc_ref: DocRef, regions: list[str]
) -> list[str]:
    """Each region's current content in receipt form, for the revert anchor check."""
    snap = await read_spreadsheet(prov, doc_ref)
    return [_region_current_flat(snap, r) for r in regions]


async def write_regions_spreadsheet(
    prov: Any,
    doc_ref: DocRef,
    regions: list[tuple[str, list[list[str]]]],
    *,
    required_revision_id: str = "",
) -> EditResult:
    """Make one named rectangle read exactly like its content.

    One region, not several: the platform's only multi-range write is a batch that is
    fail-fast without rollback, so a cross-rectangle move sent as a batch can land its
    first half and lose its second with nothing to undo the first. Declared rather
    than simulated (C9), the same posture as ``write_spreadsheet``'s single-edit
    limit -- and unlike there, a single region still carries every structural change a
    rectangle can hold: clear, fill, reorder within itself.

    ``required_revision_id`` is accepted and unused for the reason ``read_spreadsheet``
    returns no revision: the platform reports one but no write accepts it, so there is
    nothing to pin. The write's own postcondition (read back, compare, demote the
    receipt on drift) is the protection this platform can actually give.
    """
    if not regions:
        return EditResult("applied")
    if len(regions) > 1:
        return EditResult(
            "refused",
            detail="飞书表格没有原子的多区域写入（批量接口先失败即停，已写入的不回滚），"
            "因此一次只接受一个区域；跨矩形的移动请分成两次区域写并逐次核对。",
        )
    region, content = regions[0]
    sheet, r1, c1, r2, c2 = parse_a1_region(region)
    rows_n, cols_n = r2 - r1 + 1, c2 - c1 + 1
    if len(content) != rows_n or any(len(row) != cols_n for row in content):
        got = f"{len(content)}x{len(content[0]) if content else 0}"
        raise ProviderError(
            "invalid",
            f"内容形状 {got} 与区域 {region} 的 {rows_n}x{cols_n} 不符；"
            "形状不符时无法判断该填哪些格。",
        )

    # The formula check reads the document as it stands, not a snapshot the caller may
    # be holding: a cell that became a formula since then must still be protected.
    snap = await read_spreadsheet(prov, doc_ref)
    if not sheet:
        names = sorted({seg.address.rpartition("!")[0] for seg in snap.segments})
        if len(names) != 1:
            raise ProviderError(
                "invalid",
                f"区域 {region!r} 未写明工作表，而该表格有多张工作表：{', '.join(names[:5])}。",
            )
        sheet = names[0]
    a1 = f"{_a1(c1)}{r1 + 1}:{_a1(c2)}{r2 + 1}"
    # The receipt stores the sheet-qualified address: the revert reads it back on a
    # snapshot that always qualifies, and a bare address would anchor on nothing.
    region_full = f"{sheet}!{a1}"

    blocked: list[str] = []
    for seg in snap.segments:
        if not seg.readonly_reason:
            continue
        try:
            s2, rr, cc, _, _ = parse_a1_region(seg.address)
        except ProviderError:
            continue
        if s2 == sheet and r1 <= rr <= r2 and c1 <= cc <= c2:
            blocked.append(seg.address)
    if blocked:
        raise ProviderError(
            "invalid",
            f"区域内有公式格：{', '.join(blocked[:5])}。写入会把公式替换成字面量，"
            "且文档上看不出发生过什么，因此整批拒绝。",
        )

    # The snapshot read for the formula check doubles as the before-image: the
    # receipt's two ends are the region's content before and after, the pair the
    # inverse is materialized from.
    old_grid = _region_current_grid(snap, region_full)
    receipt = prov._receipt_begin(
        doc_ref,
        [(_grid_flat(old_grid), _grid_flat(content))],
        highlight=False,
        regions=[(region_full, old_grid)],
    )
    try:
        await prov._cli.json([
            "sheets", "+cells-set",
            "--spreadsheet-token", doc_ref,
            "--sheet-name", sheet,
            "--range", a1,
            "--cells", json.dumps(
                [[{"value": v} for v in row] for row in content], ensure_ascii=False
            ),
        ])
    except ProviderError as exc:
        prov._receipt_abort(receipt, f"{exc.kind}: {exc}")
        raise
    prov._receipt_commit(receipt, None)
    await _verify_written_regions(prov, doc_ref, [(region_full, content)], receipt)
    return EditResult("applied", new_revision_id="", receipt_id=receipt)




# ---------------------------------------------------------------- presentation


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _slides_pages_of(xml_text: str) -> list[tuple[str, list[textmap.Shape]]]:
    """Deck XML to (page_id, shapes) pages, in draw order.

    Namespace-agnostic on purpose: a presentation-scope fetch carries the sml xmlns,
    a slide-scope fetch does not, and the parse must not care. Empty text shapes are
    kept -- the Google lesson: their addresses matter even when their text does not.
    A slide's <note> flattens as a notes shape behind the divider, so a sentence in
    both body and note does not become two equally good anchor matches.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    slides = (
        [root] if _local(root.tag) == "slide"
        else [el for el in root.iter() if _local(el.tag) == "slide"]
    )
    pages: list[tuple[str, list[textmap.Shape]]] = []
    for sl in slides:
        sid = sl.get("id") or ""
        shapes: list[textmap.Shape] = []
        for el in sl.iter():
            kind = _local(el.tag)
            if kind not in ("shape", "note"):
                continue
            if any(
                _local(d.tag) in ("shape", "note") and d is not el for d in el.iter()
            ):
                # A group: its text lives in the child shapes, each of which is
                # emitted on its own turn of this loop. Emitting the parent too put
                # every grouped text into the flat twice, and a quote on grouped
                # text then failed the uniqueness anchor -- fail-closed, but it made
                # decks with groups unserviceable (review finding, verified).
                continue
            oid = el.get("id") or ""
            ps = ["".join(pnode.itertext())
                  for pnode in el.iter() if _local(pnode.tag) == "p"]
            shapes.append(textmap.Shape(
                page_id=sid, object_id=oid, text="\n".join(ps),
                is_notes=(kind == "note"),
            ))
        pages.append((sid, shapes))
    return pages


async def read_presentation(prov: Any, doc_ref: DocRef) -> DocSnapshot:
    """Flatten the deck, one run per shape, addressed as page/shape (D18's form)."""
    data = await prov._cli.json(["slides", "+xml-get", "--presentation", doc_ref])
    xml = str(((data or {}).get("xml_presentation") or {}).get("content") or "")
    if not xml:
        raise ProviderError("unknown", "slides +xml-get 未返回 XML 内容。")
    text, segments = textmap.flatten_slides(_slides_pages_of(xml))
    return DocSnapshot(
        doc_id=doc_ref,
        kind="presentation",
        # The platform reports a revision but no write honors it as a lock
        # (measured: a stale value is ignored, not rebuilt-from). Same posture as
        # the spreadsheet: a revision that cannot gate a write is not returned.
        revision_id=None,
        text=text,
        segments=segments,
    )


async def write_presentation(
    prov: Any, doc_ref: DocRef, snap: DocSnapshot,
    edits: list[tuple[str, str]], _revision: str | None,
    window: tuple[int, int] | None = None,
) -> EditResult:
    """The text-replacement form does not exist for a deck; say so with directions.

    Registered so the docx fallback in ``edit_batch`` can never receive a slides
    token -- the platform's own error there talks about documents, which sends the
    caller down the wrong repair.
    """
    return EditResult(
        "refused",
        detail="幻灯片没有文本替换形式；请用区域形式改写形状（地址=页/形状，"
        "来自批注锚定或读取结果）。",
    )


async def read_regions_presentation(
    prov: Any, doc_ref: DocRef, regions: list[str]
) -> list[str]:
    """Each shape's current text, for the revert anchor check. A shape that no longer
    exists refuses rather than reading as empty (the Google presentation rule)."""
    snap = await read_presentation(prov, doc_ref)
    current = {
        seg.address: snap.text[seg.char_start:seg.char_end] for seg in snap.segments
    }
    missing = [r for r in regions if r not in current]
    if missing:
        raise ProviderError(
            "invalid", f"这些区域已不在幻灯片里：{', '.join(missing[:5])}。"
        )
    return [current[r] for r in regions]


async def write_regions_presentation(
    prov: Any,
    doc_ref: DocRef,
    regions: list[tuple[str, list[list[str]]]],
    *,
    required_revision_id: str = "",
) -> EditResult:
    """Make each named shape read exactly like its content, in one request.

    Every region must sit on **one slide**: ``+replace-slide`` takes many parts in a
    single request for a single page, and cross-page writes would be separate
    requests with a half-applied window between them -- refused rather than
    simulated (C9). The shape's full element XML is fetched and only its text nodes
    are swapped: shape-level styling and geometry survive, while run-level styling
    inside the paragraphs (bold spans, per-word colors) is flattened to plain text
    -- disclosed in the receipt reply rather than silently dropped.

    ``required_revision_id`` is accepted and unused: measured live, a stale revision
    is ignored by the platform (not a lock, and -- unlike the docx flag -- not a
    snapshot rebuild either), so there is nothing to pin and nothing to fear.
    """
    import xml.etree.ElementTree as ET

    if not regions:
        return EditResult("applied")
    parsed = []
    for region, content in regions:
        page, _, oid = region.partition("/")
        if not page or not oid:
            raise ProviderError(
                "invalid", f"无法解析区域 {region!r}；幻灯片区域应为 页id/形状id。"
            )
        flat = "\n".join("\t".join(row) for row in content)
        parsed.append((region, page, oid, flat))
    slides_touched = {p for _, p, _, _ in parsed}
    if len(slides_touched) > 1:
        return EditResult(
            "refused",
            detail="一批区域只能落在同一页幻灯片上（跨页写入不是一次请求，无法原子提交）；"
            "请按页拆成多次修改。",
        )
    page_id = next(iter(slides_touched))

    data = await prov._cli.json(
        ["slides", "+xml-get", "--presentation", doc_ref, "--slide-id", page_id]
    )
    slide_xml = str(((data or {}).get("slide") or {}).get("content") or "")
    if not slide_xml:
        raise ProviderError("unknown", f"slides +xml-get 未返回第 {page_id} 页的 XML。")
    root = ET.fromstring(slide_xml)
    by_id = {el.get("id"): el for el in root.iter() if _local(el.tag) in ("shape", "note")}

    located: list[tuple[str, str]] = []
    region_specs: list[tuple[str, list[list[str]]]] = []
    parts: list[dict] = []
    for region, _page, oid, flat in parsed:
        el = by_id.get(oid)
        if el is None:
            raise ProviderError(
                "invalid", f"区域 {region!r} 指向的形状已不在该页上。"
            )
        contents = [c for c in el.iter() if _local(c.tag) == "content"]
        if not contents:
            raise ProviderError(
                "invalid", f"区域 {region!r} 的形状没有可写的文本内容。"
            )
        holder = contents[0]
        direct_ps = [c for c in list(holder) if _local(c.tag) == "p"]
        all_ps = [pn for pn in el.iter() if _local(pn.tag) == "p"]
        if len(contents) > 1 or len(all_ps) != len(direct_ps):
            # The swap writes into the first content's direct <p> children, so the
            # old text must be captured from -- and confined to -- exactly that set.
            # A shape holding text anywhere else (several content elements, <p>
            # nested in containers) would get its new text appended while the old
            # text stayed: visible duplication on a shared slide, and a receipt
            # whose inverse no longer anchors. Refused with the way forward stated
            # (review finding, asymmetry verified by reading both walks).
            raise ProviderError(
                "invalid",
                f"区域 {region!r} 的形状文本结构较复杂（多个 content 或嵌套段落），"
                "暂不支持机械改写；请在飞书中手工修改。",
            )
        old_flat = "\n".join("".join(pn.itertext()) for pn in direct_ps)
        # Swap only the text: drop the existing <p> nodes and write one per line,
        # keeping the content element and every attribute (style, autoFit, type).
        # Run-level styling INSIDE the paragraphs (bold spans etc.) does not
        # survive -- the reply discloses that below.
        ns = holder.tag.rsplit("}", 1)[0] + "}" if "}" in holder.tag else ""
        for pn in direct_ps:
            holder.remove(pn)
        for line in flat.split("\n"):
            pn = ET.SubElement(holder, ns + "p")
            pn.text = line
        parts.append({
            "action": "replace",
            "target_id": oid,
            "shape": ET.tostring(el, encoding="unicode"),
        })
        located.append((old_flat, flat))
        region_specs.append((region, [[old_flat]]))

    receipt = prov._receipt_begin(
        doc_ref, located, highlight=False, regions=region_specs,
    )
    try:
        await prov._cli.json([
            "slides", "+replace-slide",
            "--presentation", doc_ref,
            "--slide-id", page_id,
            "--parts", json.dumps(parts, ensure_ascii=False),
        ])
    except ProviderError as exc:
        prov._receipt_abort(receipt, f"{exc.kind}: {exc}")
        raise
    prov._receipt_commit(receipt, None)
    await _verify_written_regions(
        prov, doc_ref, [(r, c) for r, c in regions], receipt
    )
    return EditResult("applied", new_revision_id="", receipt_id=receipt)


READERS = {
    "markdown": read_markdown,
    "spreadsheet": read_spreadsheet,
    "presentation": read_presentation,
}

WRITERS = {
    "markdown": write_markdown,
    "spreadsheet": write_spreadsheet,
    "presentation": write_presentation,
}

TEXT_DOMAIN = {
    "document": "markdown",
    "markdown": "markdown",
    "spreadsheet": "plain",
    "presentation": "plain",
}

# The formats with an addressed form. A docx and a markdown file have none, and the
# provider answers those with the base class's declared refusal.
REGION_READERS = {
    "spreadsheet": read_regions_spreadsheet,
    "presentation": read_regions_presentation,
}

REGION_WRITERS = {
    "spreadsheet": write_regions_spreadsheet,
    "presentation": write_regions_presentation,
}
