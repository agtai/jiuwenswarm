"""The chat path's routing provider: one surface, every connection's documents."""

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    DocSnapshot, DocSummary, EditResult, ProviderError,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.routing import RoutingProvider


class _Fake:
    def __init__(self, kind, docs, *, address):
        self.kind = kind
        self.docs = docs
        self.address = address
        self.calls = []
        self.receipt_sink = None
        self.receipt_meta = None
        self.kinds = {}

    def parse_doc_ref(self, s):
        s = s.strip()
        if self.kind == "google":
            if "/document/d/" in s:
                return s.split("/document/d/")[1].split("/")[0]
            return s
        for marker in ("/docx/", "/sheets/"):
            if marker in s:
                return s.split(marker)[1].split("?")[0].split("/")[0]
        if "/" in s:
            raise ProviderError("invalid", "not mine")
        return s

    async def read(self, ref):
        self.calls.append(("read", ref))
        if ref not in self.docs:
            raise ProviderError("not_found", f"{self.kind} has no {ref}")
        return DocSnapshot(doc_id=ref, kind="document", revision_id="r", text=f"{self.kind}:{ref}")

    async def edit_batch(self, ref, edits, *, required_revision_id, window=None, highlight=False):
        self.calls.append(("edit", ref))
        return EditResult("applied", new_revision_id="r2", receipt_id=f"rcpt-{self.kind}")

    async def list_accessible_documents(self):
        return [DocSummary(doc_id=d, title=f"{self.kind}-{d}", can_edit=True, kind="document") for d in self.docs]

    async def create_document(self, title):
        return f"new-{self.kind}"

    def note_kind(self, ref, kind):
        self.kinds[ref] = kind


def _rig():
    g = _Fake("google", ["gdoc1", "gdoc2"], address="sa@x.iam")
    f = _Fake("feishu", ["FsTok1"], address="ou_1")
    conns = [("g.json", g), ("f.json", f)]
    docs = {"g.json": ["gdoc1", "gdoc2"], "f.json": ["FsTok1"]}
    return g, f, RoutingProvider(conns, lambda cf: docs.get(cf, []))


@pytest.mark.asyncio
async def test_a_document_is_read_through_the_connection_that_adopted_it():
    g, f, r = _rig()
    assert (await r.read("FsTok1")).text == "feishu:FsTok1"
    assert (await r.read("gdoc2")).text == "google:gdoc2"
    assert g.calls == [("read", "gdoc2")] and f.calls == [("read", "FsTok1")]


def test_a_pasted_link_routes_by_the_adopted_list_before_the_host():
    g, f, r = _rig()
    assert r.parse_doc_ref("https://x.feishu.cn/docx/FsTok1?from=chat") == "FsTok1"
    assert r.parse_doc_ref("https://docs.google.com/document/d/gdoc1/edit") == "gdoc1"
    # A link nobody lists routes by the platform it names, then is remembered.
    assert r.parse_doc_ref("https://x.feishu.cn/docx/Unknown9") == "Unknown9"
    assert r.owner("Unknown9") is f
    # A bare token nobody lists goes to the first connection, as before.
    assert r.owner("mystery") is g


@pytest.mark.asyncio
async def test_listings_are_the_union_and_creation_goes_to_the_first_connection():
    g, f, r = _rig()
    titles = sorted(s.title for s in await r.list_accessible_documents())
    assert titles == ["feishu-FsTok1", "google-gdoc1", "google-gdoc2"]
    assert await r.create_document("t") == "new-google"
    assert r.owner("new-google") is g


@pytest.mark.asyncio
async def test_receipt_plumbing_reaches_every_child():
    g, f, r = _rig()
    sink = object()
    r.receipt_sink = sink
    r.receipt_meta = {"executor": "chat"}
    assert g.receipt_sink is sink and f.receipt_sink is sink
    assert g.receipt_meta == {"executor": "chat"} and f.receipt_meta == {"executor": "chat"}
    r.receipt_meta = None
    assert g.receipt_meta is None and f.receipt_meta is None
    out = await r.edit_batch("FsTok1", [("a", "b")], required_revision_id="r")
    assert out.receipt_id == "rcpt-feishu"


def test_format_priming_lands_on_the_owner():
    g, f, r = _rig()
    r.note_kind("FsTok1", "spreadsheet")
    r.note_kind("gdoc1", "presentation")
    assert f.kinds == {"FsTok1": "spreadsheet"} and g.kinds == {"gdoc1": "presentation"}


def test_adoption_is_read_live():
    g, f, _ = _rig()
    docs = {"g.json": ["gdoc1"], "f.json": []}
    r = RoutingProvider([("g.json", g), ("f.json", f)], lambda cf: docs.get(cf, []))
    assert r.owner("LateTok") is g
    docs["f.json"] = ["LateTok"]           # the panel adopts it mid-session
    assert r.owner("LateTok") is f


@pytest.mark.asyncio
async def test_the_format_question_reaches_the_owner():
    g, f, r = _rig()
    g.doc_kind = None  # would raise if consulted for a Feishu token
    async def fk(ref): return "spreadsheet"
    f.doc_kind = fk
    assert await r.doc_kind("FsTok1") == "spreadsheet"


def test_a_platform_choice_names_the_creating_connection():
    g, f, r = _rig()
    assert r.for_platform("feishu") is f and r.for_platform("google") is g
    assert r.for_platform("wps") is None
    r.learn("NewTok", f)
    assert r.owner("NewTok") is f


def test_the_shared_builder_returns_the_plain_provider_for_one_connection():
    from jiuwenswarm.agents.harness.common.tools.clouddoc.routing import build_routed_provider
    g = _Fake("google", ["gdoc1"], address="sa@x.iam")
    built = []
    def build(cf, *, agent_roster=()):
        built.append(cf); return g
    prov, first = build_routed_provider(
        [{"credentials_file": "g.json", "documents": ["gdoc1"]}],
        build=build, live_specs=lambda: [],
    )
    assert prov is g and first == "g.json" and built == ["g.json"]


def test_the_shared_builder_routes_several_connections_and_skips_a_bad_key():
    """The first connection must build (it is the turn's identity); a later one whose
    key cannot be read is skipped so the others stay reachable."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.routing import (
        RoutingProvider, all_adopted_documents, build_routed_provider,
    )
    g = _Fake("google", ["gdoc1"], address="sa@x.iam")
    f = _Fake("feishu", ["FsTok1"], address="ou_1")
    def build(cf, *, agent_roster=()):
        if cf == "bad.json":
            raise RuntimeError("unreadable")
        return {"g.json": g, "f.json": f}[cf]
    specs = [
        {"credentials_file": "g.json", "documents": ["gdoc1"]},
        {"credentials_file": "bad.json", "documents": ["x"]},
        {"credentials_file": "f.json", "documents": ["FsTok1"]},
    ]
    prov, first = build_routed_provider(specs, build=build, live_specs=lambda: specs)
    assert isinstance(prov, RoutingProvider) and first == "g.json"
    assert prov.owner("FsTok1") is f and prov.owner("gdoc1") is g
    assert all_adopted_documents(lambda: specs) == ["gdoc1", "x", "FsTok1"]


def test_the_shared_builder_fails_when_the_first_connection_cannot_build():
    from jiuwenswarm.agents.harness.common.tools.clouddoc.routing import build_routed_provider
    def build(cf, *, agent_roster=()):
        raise RuntimeError("unreadable")
    with pytest.raises(RuntimeError):
        build_routed_provider([{"credentials_file": "g.json", "documents": []}],
                              build=build, live_specs=lambda: [])
