"""Matrix ⑬ — the workmode subsystem (PR2a).

The style layer's whole contract: missing/unreadable/oversized file behavior,
re-read per dispatch, unique-match editing, the ①②③ injection order, and the
unattended refusal of both workmode tools. Style never carries authority, so the
tests here guard mechanics, not semantics — the permission table and closed set
are what keep a workmode sentence from granting anything.
"""

from __future__ import annotations

import os


from jiuwenswarm.clouddoc.workmode import (
    WORKMODE_MAX_BYTES,
    builtin_template,
    edit_workmode,
    load_workmode,
    prefer_zh_from_words,
    resolve_workmode_path,
)


def test_missing_file_falls_back_to_builtin_without_error(tmp_path):
    wm = load_workmode(str(tmp_path / "absent.md"))
    assert wm.source == "builtin"
    assert wm.error is None
    assert wm.text == builtin_template(prefer_zh=True)


def test_builtin_template_language_follows_prefer_zh(tmp_path, monkeypatch):
    assert "工作方式" in builtin_template(prefer_zh=True)
    assert "working style" in builtin_template(prefer_zh=False)
    # ``None`` resolves to the deployment's default file; point it at an absent one so
    # a working-style file on the developer's machine cannot decide the outcome.
    import jiuwenswarm.clouddoc.workmode as wm
    monkeypatch.setattr(wm, "resolve_workmode_path", lambda c: tmp_path / "absent.md")
    assert load_workmode(None, prefer_zh=False).text == builtin_template(prefer_zh=False)


def test_existing_file_is_read_as_is(tmp_path):
    f = tmp_path / "wm.md"
    f.write_text("# 自定义\n- 简短回复\n", encoding="utf-8")
    wm = load_workmode(str(f))
    assert wm.source == "file"
    assert wm.text == "# 自定义\n- 简短回复\n"
    assert not wm.truncated


def test_empty_file_is_respected_not_replaced_by_template(tmp_path):
    # A deployer who emptied the file asked for no style text, not the template back.
    f = tmp_path / "wm.md"
    f.write_text("", encoding="utf-8")
    wm = load_workmode(str(f))
    assert wm.source == "file"
    assert wm.text == ""


def test_unreadable_file_falls_back_to_builtin_with_error(tmp_path):
    f = tmp_path / "wm.md"
    f.write_text("x", encoding="utf-8")
    os.chmod(f, 0o000)
    try:
        wm = load_workmode(str(f))
    finally:
        os.chmod(f, 0o644)
    assert wm.source == "builtin"
    assert wm.error is not None


def test_oversized_file_truncates_on_line_boundary(tmp_path):
    line = "规则" * 40 + "\n"  # ~240 bytes per line in UTF-8
    f = tmp_path / "wm.md"
    f.write_text(line * 200, encoding="utf-8")  # ~48KB > 16KB
    wm = load_workmode(str(f))
    assert wm.truncated
    assert len(wm.text.encode("utf-8")) <= WORKMODE_MAX_BYTES
    # Line boundary: no half line survives.
    for ln in wm.text.split("\n"):
        assert ln == "" or ln == line.rstrip("\n")


def test_single_giant_line_is_clipped_not_dropped(tmp_path):
    f = tmp_path / "wm.md"
    f.write_text("字" * 20000, encoding="utf-8")  # one line, ~60KB
    wm = load_workmode(str(f))
    assert wm.truncated
    assert wm.text  # not silently emptied
    assert len(wm.text.encode("utf-8")) <= WORKMODE_MAX_BYTES


def test_reread_per_dispatch_sees_the_edit_immediately(tmp_path):
    f = tmp_path / "wm.md"
    f.write_text("回复要长。\n", encoding="utf-8")
    assert "回复要长" in load_workmode(str(f)).text
    r = edit_workmode(str(f), "回复要长。", "回复要短。")
    assert r["ok"], r
    assert "回复要短" in load_workmode(str(f)).text


def test_edit_materializes_builtin_on_first_edit(tmp_path):
    # What workmode_get displayed is exactly what old_string matches against.
    f = tmp_path / "wm.md"
    anchor = "编辑最小化：只改被要求的那处，不顺手优化。"
    assert anchor in builtin_template(prefer_zh=True)
    r = edit_workmode(str(f), anchor, "编辑最小化，且逐条说明理由。")
    assert r["ok"], r
    assert f.is_file()
    assert "逐条说明理由" in f.read_text(encoding="utf-8")


def test_edit_zero_match_refuses(tmp_path):
    f = tmp_path / "wm.md"
    f.write_text("abc\n", encoding="utf-8")
    r = edit_workmode(str(f), "不存在的原文", "x")
    assert not r["ok"]
    assert "找不到" in r["detail"]


def test_edit_multi_match_refuses_with_count(tmp_path):
    f = tmp_path / "wm.md"
    f.write_text("规则A\n规则A\n", encoding="utf-8")
    r = edit_workmode(str(f), "规则A", "规则B")
    assert not r["ok"]
    assert "2" in r["detail"]
    assert f.read_text(encoding="utf-8") == "规则A\n规则A\n"  # untouched


def test_edit_empty_old_string_refuses(tmp_path):
    r = edit_workmode(str(tmp_path / "wm.md"), "", "x")
    assert not r["ok"]


def test_edit_over_limit_warns_but_applies(tmp_path):
    f = tmp_path / "wm.md"
    f.write_text("小段。\n", encoding="utf-8")
    r = edit_workmode(str(f), "小段。", "长" * 20000)
    assert r["ok"]
    assert str(WORKMODE_MAX_BYTES) in r["detail"]


def test_resolve_path_empty_uses_workspace_default():
    p = resolve_workmode_path("")
    assert p.name == "clouddoc-workmode.md"
    assert p.parent.name == "config"


def test_prefer_zh_from_words():
    assert prefer_zh_from_words(("同意", "approve")) is True
    assert prefer_zh_from_words(("approve",)) is False
    assert prefer_zh_from_words(None) is True
