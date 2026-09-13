"""Provider receipt string encoding preserves complete facts and source grammar."""

import json
from decimal import Decimal

import pytest

from jiuwenswarm.server.live_voice.native_business_encoding import compact_native_business_output
from jiuwenswarm.server.live_voice.openai_realtime_session import _encode_client_event


@pytest.mark.parametrize("text", [
    "中文事实完整保留，结论在尾部。",
    "已完成 🚀 😀 𠀀",
    '引号 " 反斜杠 \\ 换行\n制表\t空字节\x00',
    "家庭 👩\u200d👩\u200d👧\u200d👦；格式\u200b\u200e\ufeff；分隔\u2028\u2029",
    r"中文后面的字面转义 \u4e2d 和 \\u6587 保持字面含义",
])
def test_complete_multilingual_string_facts_round_trip_without_truncation(text):
    facts = {"operation": "work.get", "work": {"result_text": text, "tail": "完整尾部"},
             "context": {"history": [{"content": text}], "empty": "", "truth": True, "nil": None}}
    original = json.dumps(facts, ensure_ascii=True, separators=(",", ":"))
    compact = compact_native_business_output(original)
    assert json.loads(compact) == facts
    assert len(compact.encode("utf-8")) < len(original.encode("utf-8"))
    assert "完整尾部" in compact
    assert compact_native_business_output(compact) == compact


def test_only_string_tokens_change_with_duplicate_keys_numeric_precision_and_spacing():
    original = (' { "label" : "\\u4e2d", "n":-0, "n":1.234567890123456789, '
                '"huge":1e999, "integer":9007199254740993, "exponent":1.00E-003, '
                '"\\u540d":"first", "名":"second", "nested":["\\u6587",false,null] } ')
    compact = compact_native_business_output(original)
    expected = original.replace('"\\u4e2d"', '"中"').replace('"\\u540d"', '"名"').replace('"\\u6587"', '"文"')
    assert compact == expected
    parse = dict(object_pairs_hook=lambda pairs: pairs, parse_float=Decimal, parse_int=Decimal)
    assert json.loads(compact, **parse) == json.loads(original, **parse)


@pytest.mark.parametrize("original", [
    '{"text":"\\u4e2d","number":NaN}',
    '{"text":"\\u4e2d","number":Infinity}',
    '{"text":"\\u4e2d","number":-Infinity}',
    '{"text":"\\u4e2d",}',
    '{"text":"\\uZZZZ"}',
    '{"text":"\\u4e2d"} trailing',
    '{"text":"\\u4e2d\\ud800"}',
    '{"text":"\\udc00\\u4e2d"}',
    '{"text":"\\u4e2d\ud800"}',
    '{"text":"\\u4e2d\n"}',
    "[" * 2000 + '"\\u4e2d"' + "]" * 2000,
])
def test_unsafe_or_unsupported_input_falls_back_to_exact_original(original):
    assert compact_native_business_output(original) is original


@pytest.mark.parametrize("original", [
    '{"text":"already plain ASCII","number":1.5}',
    '{"text":"already 中文 🚀"}',
    r'{"text":"literal \\u4e2d"}',
    r'{"text":"\u0000\u001f"}',
    "not JSON",
    "",
])
def test_non_smaller_or_ineligible_input_returns_exact_original(original):
    assert compact_native_business_output(original) is original


@pytest.mark.parametrize("size", [524_287, 524_288, 524_289])
def test_original_utf8_bound_is_not_bypassed_by_a_smaller_possible_output(size):
    prefix, suffix = '{"text":"\\u4e2d', 'TAIL"}'
    original = prefix + "x" * (size - len(prefix) - len(suffix)) + suffix
    assert len(original.encode("utf-8")) == size
    compact = compact_native_business_output(original)
    if size > 524_288:
        assert compact is original
    else:
        assert len(compact.encode("utf-8")) < size
        assert json.loads(compact) == json.loads(original)
        assert json.loads(compact)["text"].endswith("TAIL")


def test_actual_session_wire_serializer_preserves_complete_provider_visible_facts():
    facts = {"operation": "work.get", "work": {"result_text": "中文结果，含家庭 👩\u200d👩\u200d👧\u200d👦。" * 32 + "完整尾部"}}
    original = json.dumps(facts, ensure_ascii=True, separators=(",", ":"))
    compact = compact_native_business_output(original)

    def event(output):
        return {"type": "conversation.item.create", "event_id": "encoding-test", "item": {
            "type": "function_call_output", "call_id": "call-1", "output": output}}

    before = _encode_client_event(event(original))
    after = _encode_client_event(event(compact))
    assert json.loads(after)["item"]["output"] == compact
    assert json.loads(json.loads(after)["item"]["output"]) == facts
    assert json.loads(json.loads(before)["item"]["output"]) == facts
    assert len(after.encode("utf-8")) < len(before.encode("utf-8"))
    assert original == json.dumps(facts, ensure_ascii=True, separators=(",", ":"))
