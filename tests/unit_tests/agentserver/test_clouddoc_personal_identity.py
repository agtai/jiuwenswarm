"""Personal identity, library layer (design §13, matrix §S): the CLI seam, the
Feishu provider acting as a person, the factory's two connection kinds, the reply
signature, the toolkit's executor label, and the routing choice.

Negative cases carry the weight: an unsigned personal reply, a signature with no
receipt, a Google personal file, an unknown identity -- each must be refused, not
approximated.
"""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import CloudDocToolkit
from jiuwenswarm.agents.harness.common.tools.clouddoc.factory import (
    build_provider,
    detect_kind,
    detect_vendor,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.feishu_provider import FeishuDocsProvider
from jiuwenswarm.agents.harness.common.tools.clouddoc.lark_cli import LarkCli, LarkResult
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    AgentIdentity,
    DocSnapshot,
    EditResult,
    ProviderError,
    identity_choice_for,
    read_connection_specs,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore
from jiuwenswarm.agents.harness.common.tools.clouddoc.routing import RoutingProvider
from jiuwenswarm.agents.harness.common.tools.clouddoc.signature import (
    DEFAULT_SIGNATURE_TEMPLATE,
    render_signature,
    sign_reply,
    signature_body,
)

DOC = "1AAAAAAAAAAAAAAAAAAAAA"


# ------------------------------------------------------------------ CLI seam


def test_service_cli_still_acts_as_the_bot_by_default():
    args = LarkCli(binary="lark-cli", profile="p")._base_args()
    assert args[args.index("--as") + 1] == "bot"


def test_personal_cli_acts_as_the_user_on_every_command():
    cli = LarkCli(binary="lark-cli", profile="p", identity="user")
    args = cli._base_args()
    assert args[args.index("--as") + 1] == "user"
    assert cli.identity == "user"


def test_an_unknown_identity_is_a_construction_error_not_a_fallback():
    with pytest.raises(ValueError):
        LarkCli(binary="lark-cli", identity="admin")


# ------------------------------------------------------------------ Feishu provider


class _StubCli(LarkCli):
    def __init__(self, replies: dict, *, identity: str = "user") -> None:
        super().__init__(binary="lark-cli", profile="p", identity=identity)
        self.calls: list[list[str]] = []
        self._replies = replies

    @property
    def available(self) -> bool:
        return True

    async def run(self, args, *, timeout=None) -> LarkResult:
        self.calls.append(list(args))
        key = " ".join(args[:3]) if args and args[0] == "api" else " ".join(args[:2])
        payload = self._replies.get(key, self._replies.get(args[0]))
        if isinstance(payload, ProviderError):
            return LarkResult(stdout="", stderr=str(payload), code=1)
        return LarkResult(
            stdout=json.dumps({"ok": True, "identity": self._identity, "data": payload or {}}),
            stderr="", code=0,
        )

    async def json(self, args, *, timeout=None):
        res = await self.run(args, timeout=timeout)
        if not res.ok:
            raise ProviderError("auth", res.stderr)
        return json.loads(res.stdout).get("data")


@pytest.mark.asyncio
async def test_personal_identity_is_the_logged_in_person_by_open_id():
    p = FeishuDocsProvider(profile="p", identity="user")
    p._cli = _StubCli({
        "whoami": {"identity": "user", "available": True, "tokenStatus": "ready"},
        "api GET /open-apis/authen/v1/user_info": {
            "open_id": "ou_me", "name": "张三", "email": "zs@x.com",
        },
    })
    ident = await p.self_identity()
    assert ident == AgentIdentity(display_name="张三", address="ou_me")
    assert p.personal is True
    assert p.identity_address == "ou_me"
    # Written by me -- or by my agent, which is the same identity here.
    assert p._is_self("ou_me") is True
    assert p._is_self("ou_other") is False


@pytest.mark.asyncio
async def test_a_missing_user_login_is_an_auth_error_naming_the_command():
    p = FeishuDocsProvider(profile="p", identity="user")
    p._cli = _StubCli({"whoami": {"identity": "user", "available": False, "tokenStatus": "missing"}})
    with pytest.raises(ProviderError) as exc:
        await p.self_identity()
    assert exc.value.kind == "auth"
    assert "lark-cli auth login" in str(exc.value)


@pytest.mark.asyncio
async def test_personal_capabilities_read_the_persons_own_row_not_the_apps():
    p = FeishuDocsProvider(profile="cli_app", identity="user", self_open_id="ou_me")
    p._cli = _StubCli({
        "drive +member-list": {"items": [
            {"member_id": "cli_app", "member_type": "app", "perm": "full_access"},
            {"member_id": "ou_me", "member_type": "openid", "perm": "view"},
        ]},
    })
    caps = await p.capabilities("T")
    assert caps.can_read is True
    assert caps.can_edit is False, "the person's row says view; the app's row must not answer for them"


# ------------------------------------------------------------------ factory


def _write(tmp_path, name, body):
    f = tmp_path / name
    f.write_text(json.dumps(body))
    return str(f)


def test_a_personal_feishu_file_builds_a_user_identity_provider_without_a_secret(tmp_path):
    f = _write(tmp_path, "personal.json", {
        "kind": "personal", "brand": "feishu", "profile": "cli_x", "open_id": "ou_me", "name": "张三",
    })
    assert detect_kind(f) == "personal"
    assert detect_vendor(f) == "feishu"
    prov = build_provider(f)
    assert prov.personal is True
    assert prov._cli.identity == "user"
    assert prov.identity_address == "ou_me"
    assert "app_secret" not in json.loads(open(f).read())


def test_a_service_file_is_still_a_service_connection(tmp_path):
    f = _write(tmp_path, "app.json", {"app_id": "cli_x", "app_secret": "s", "bot_open_id": "ou_bot"})
    assert detect_kind(f) == "service"
    prov = build_provider(f)
    assert prov.personal is False
    assert prov._cli.identity == "bot"


def test_a_google_personal_file_without_a_token_is_refused_with_the_remedy(tmp_path):
    """Google personal identity is an OAuth user token (test_clouddoc_google_personal);
    a personal file that has none cannot act and says so, naming the fix."""
    f = _write(tmp_path, "gp.json", {"kind": "personal", "brand": "google"})
    with pytest.raises(ProviderError) as exc:
        detect_vendor(f)
    assert exc.value.kind == "auth"
    assert "重新完成 Google 授权" in str(exc.value)
    with pytest.raises(ProviderError):
        build_provider(f)


def test_an_unknown_connection_kind_is_refused(tmp_path):
    f = _write(tmp_path, "k.json", {"kind": "admin", "brand": "feishu"})
    with pytest.raises(ProviderError):
        detect_kind(f)


def test_connection_specs_carry_kind_and_default_to_service():
    specs = read_connection_specs({"connections": [
        {"credentials_file": "/a.json", "documents": ["d1"]},
        {"credentials_file": "/p.json", "documents": ["d1"], "kind": "personal"},
    ]})
    assert [s["kind"] for s in specs] == ["service", "personal"]


def test_identity_choice_defaults_to_service_and_ignores_junk():
    cfg = {"identity_choice": {"d1": "personal", "d2": "admin"}}
    assert identity_choice_for(cfg, "d1") == "personal"
    assert identity_choice_for(cfg, "d2") == "service"
    assert identity_choice_for(cfg, "d3") == "service"
    assert identity_choice_for({"identity_choice": "nope"}, "d1") == "service"


# ------------------------------------------------------------------ signature


def test_signature_body_is_never_empty():
    assert signature_body("", name="张三") == "— 由 张三 的 JiuwenSwarm 代理执行"
    assert signature_body("   ", name="张三") == signature_body(None, name="张三")
    assert signature_body("{name}", name="") == DEFAULT_SIGNATURE_TEMPLATE.replace("{name}", "").strip()


def test_signature_body_is_the_persons_to_word():
    assert signature_body("此回复由 {name} 的代理代发", name="张三") == "此回复由 张三 的代理代发"


def test_receipt_number_is_appended_by_code_and_cannot_be_empty():
    line = render_signature("自定义 {name}", name="张三", receipt_id="abc123")
    assert line == "自定义 张三 · 回执 abc123"
    with pytest.raises(ValueError):
        render_signature("自定义", name="张三", receipt_id="")
    with pytest.raises(ValueError):
        render_signature("自定义", name="张三", receipt_id="   ")


def test_a_template_cannot_smuggle_a_second_line_or_drop_the_tail():
    line = render_signature("第一行\n第二行 回执 fake", name="x", receipt_id="r1")
    assert "\n" not in line
    assert line.endswith("· 回执 r1")


def test_sign_reply_keeps_the_content_and_ends_with_the_signature():
    out = sign_reply("好的，已改。", None, name="张三", receipt_id="r9")
    assert out.startswith("好的，已改。")
    assert out.endswith("— 由 张三 的 JiuwenSwarm 代理执行 · 回执 r9")


# ------------------------------------------------------------------ toolkit


class _Fake:
    """The toolkit slice, with ``personal`` switchable."""

    def __init__(self, *, personal: bool, address: str = "ou_me", name: str = "张三"):
        self.personal = personal
        self.identity_address = address
        self._name = name
        self.replies: list[tuple[str, str, str]] = []
        self.receipt_sink = None
        self.receipt_meta = None
        self.edits: list = []

    @property
    def kind(self):
        return "feishu"

    def doc_url(self, d, kind=""):
        return f"https://x/{d}"

    def parse_doc_ref(self, s):
        return s.strip()

    async def self_identity(self):
        return AgentIdentity(display_name=self._name, address=self.identity_address)

    async def read(self, d):
        return DocSnapshot(doc_id=d, kind="document", revision_id="r1", text="hello world")

    async def list_comments(self, d, *, include_resolved=False):
        return []

    async def reply_comment(self, d, cid, content):
        self.replies.append((d, cid, content))
        return "reply-1"

    async def edit_batch(self, d, pairs, *, required_revision_id=None, window=None, highlight=False):
        self.edits.append((d, list(pairs), dict(self.receipt_meta or {})))
        return EditResult("applied", new_revision_id="r2")

    async def list_accessible_documents(self):
        return []

    async def title(self, d):
        return "T"


def _kit(prov, **kw):
    kit = CloudDocToolkit(prov, watched_docs=lambda: [DOC], **kw)
    kit._read_docs.add(DOC)
    return kit


@pytest.mark.asyncio
async def test_a_personal_reply_is_signed_with_a_receipt_number(tmp_path):
    prov = _Fake(personal=True)
    prov.receipt_sink = ReceiptStore(tmp_path / "r.json")
    kit = _kit(prov, signature_template="由 {name} 的代理代发")
    out = await kit.reply_comment(DOC, "c1", "已改好。")
    assert out["ok"] is True and out["signed"] is True
    rid = out["receipt_id"]
    assert rid
    posted = prov.replies[-1][2]
    assert posted.startswith("已改好。")
    assert posted.endswith(f"由 张三 的代理代发 · 回执 {rid}")
    rec = prov.receipt_sink.get(rid)
    assert rec["op"] == "reply" and rec["status"] == "applied"
    assert rec["executor"] == "chat:ou_me"
    assert rec["subject"]["comment_id"] == "c1"


@pytest.mark.asyncio
async def test_a_personal_reply_is_signed_even_when_the_template_is_empty(tmp_path):
    prov = _Fake(personal=True)
    prov.receipt_sink = ReceiptStore(tmp_path / "r.json")
    kit = _kit(prov, signature_template="")
    out = await kit.reply_comment(DOC, "c1", "hi")
    posted = prov.replies[-1][2]
    assert "— 由 张三 的 JiuwenSwarm 代理执行 · 回执 " + out["receipt_id"] in posted


@pytest.mark.asyncio
async def test_a_personal_reply_without_a_ledger_is_refused_not_posted_bare():
    prov = _Fake(personal=True)          # no receipt_sink
    kit = _kit(prov)
    out = await kit.reply_comment(DOC, "c1", "hi")
    assert out["ok"] is False
    assert prov.replies == [], "nothing may be posted under a person's name unsigned"


@pytest.mark.asyncio
async def test_a_failed_personal_post_aborts_its_receipt(tmp_path):
    prov = _Fake(personal=True)
    prov.receipt_sink = ReceiptStore(tmp_path / "r.json")

    async def boom(d, cid, content):
        raise ProviderError("forbidden", "no")

    prov.reply_comment = boom
    kit = _kit(prov)
    out = await kit.reply_comment(DOC, "c1", "hi")
    assert out["ok"] is False
    rows = prov.receipt_sink.list_for(DOC)
    assert rows and rows[0]["status"] == "aborted"


@pytest.mark.asyncio
async def test_a_service_reply_is_unchanged_unsigned_and_unreceipted(tmp_path):
    prov = _Fake(personal=False)
    prov.receipt_sink = ReceiptStore(tmp_path / "r.json")
    kit = _kit(prov, signature_template="由 {name} 的代理代发")
    out = await kit.reply_comment(DOC, "c1", "hi")
    assert out == {"ok": True, "detail": "", "reply_id": "reply-1"}
    assert prov.replies[-1][2] == "hi"
    assert prov.receipt_sink.list_for(DOC) == []


@pytest.mark.asyncio
async def test_executor_names_the_person_under_a_personal_identity_and_chat_otherwise():
    personal = _kit(_Fake(personal=True, address="ou_me"))
    assert personal._executor_for(DOC) == "chat:ou_me"
    service = _kit(_Fake(personal=False))
    assert service._executor_for(DOC) == "chat"
    mcp = _kit(_Fake(personal=False), executor_label="mcp:cli")
    assert mcp._executor_for(DOC) == "mcp:cli"


@pytest.mark.asyncio
async def test_a_personal_edit_records_the_person_as_executor(monkeypatch):
    prov = _Fake(personal=True, address="ou_me")
    kit = _kit(prov, ask_channel=False, harness_mode="direct")
    out = await kit.batch_edit(DOC, edits=[{"old_string": "hello", "new_string": "hi"}])
    assert out["ok"] is True, out
    assert prov.edits[-1][2]["executor"] == "chat:ou_me"


# ------------------------------------------------------------------ routing


class _R:
    def __init__(self, kind, personal, address):
        self.kind, self.personal, self.identity_address = kind, personal, address
        self.receipt_sink = None
        self.receipt_meta = None

    def parse_doc_ref(self, s):
        return s


def _rig(choice):
    svc = _R("feishu", False, "ou_bot")
    me = _R("feishu", True, "ou_me")
    docs = {"svc.json": ["D"], "me.json": ["D", "MINE"]}
    return svc, me, RoutingProvider(
        [("svc.json", svc), ("me.json", me)], lambda cf: docs[cf], choice
    )


def test_overlap_routes_to_the_service_identity_by_default():
    svc, me, r = _rig(lambda d: "service")
    assert r.owner("D") is svc
    assert r.owner("MINE") is me, "a document only the person adopted goes to the person"


def test_overlap_routes_to_the_person_when_they_chose_so():
    svc, me, r = _rig(lambda d: "personal" if d == "D" else "service")
    assert r.owner("D") is me


def test_no_choice_function_means_service():
    svc, me, r = _rig(None)
    assert r.owner("D") is svc
