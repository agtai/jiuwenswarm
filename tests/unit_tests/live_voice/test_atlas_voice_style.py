import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.atlas_voice_style import spoken_language
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    OpenAIRealtimeNativeInteractionEngine,
)


@pytest.mark.parametrize("texts, expected", [
    (["帮我报销巴黎出差费用", "OK"], "Mandarin Chinese"),
    (["帮我报销", "不要用英文回答"], "Mandarin Chinese"),
    (["帮我报销", "Do not speak in English"], "Mandarin Chinese"),
    (["帮我买咖啡", "Harbour Lane"], "Mandarin Chinese"),
    (["帮我报销", "请用英文回答"], "English"),
    (["Expense the Paris trip", "用中文说"], "Mandarin Chinese"),
    ([], None),
])
def test_language_comes_from_user_speech(texts, expected):
    assert spoken_language(texts) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("capabilities", [[], ["expense"], ["repurchase", "expense"]])
async def test_isolated_english_result_keeps_chinese_and_does_not_mutate_request(capabilities):
    sent = []
    async def send(event, payload):
        sent.append((event, payload))
        return "sent"
    # Exercise the actual response transport boundary with one exact committed turn.
    engine = object.__new__(OpenAIRealtimeNativeInteractionEngine)
    engine._business_context = {"context_id": "ctx", "capabilities": capabilities}
    engine._input_commits_by_item = {"u": SimpleNamespace(turn_id="turn")}
    engine._input_transcripts_by_item = {"u": SimpleNamespace(transcript="帮我报销巴黎出差费用")}
    engine._sent_business_context_id = "ctx"
    engine._profile_business = lambda *args, **kwargs: None
    engine._session = SimpleNamespace(send_event=send)
    payload = {"response": {"instructions": "Summarize the result", "tool_choice": "none",
        "input": [{"text": "Expense the Paris trip. Mock claim submitted."}]}}
    before = json.dumps(payload)
    request = SimpleNamespace(turn_id="turn", payload=payload)
    await engine._send_response_request_locked(request)
    actual = sent[0][1]["response"]
    assert ("Speak entirely in Mandarin Chinese" in actual["instructions"]) == bool(capabilities)
    assert actual["tool_choice"] == "none"
    assert actual["input"] == payload["response"]["input"]
    assert json.dumps(payload) == before
