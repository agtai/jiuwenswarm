"""Native answer policy preserves facts, stronger authority and final-output truth."""

import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ContextRef, TurnCommit
from jiuwenswarm.server.live_voice.p3_model_resolution import ServerModelCatalogResolver
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalAgentExecution, FormalContextEntry, FormalContextSnapshot,
    NATIVE_ANALYSIS_PRESENTATION_INSTRUCTIONS,
)
from tests.unit_tests.agentserver.test_formal_live_voice_adapter import (
    FormalInstance, OutputLease, RawChunk, adapter_with, formal_request,
)
from tests.unit_tests.agentserver.test_native_work_formal_policy import catalog, model
from tests.unit_tests.live_voice.test_agent_conversation_runtime import scope


def execution(*, native=True, source="project.document", selected_result=False):
    ref = ContextRef.from_dict({
        "source": source, "stable_id": "source-1", "uri": "context://source-1",
        "revision": {"kind": "unversioned"}, "scope": scope().to_dict(),
        "permissions": ["context.read"], "expires_at": None,
        "redaction": {"policy_id": "test", "redacted": False, "fields": []}, "extensions": {},
    })
    text = "详细计算两个安排的余量，保留限制、单位及文件名。"
    selected = "会议室 09:10；仓库 09:40；到达 09:00。文件名：现场 安排 v2.md。旧记录 08:50 已失效。"
    commit = TurnCommit.from_dict({
        "contract_version": "live-voice.contract.v2", "commit_id": "commit-1", "turn_id": "turn-1",
        "interaction_id": "interaction-1", "text": text, "hypothesis_provenance": {"provider": "test"},
        "scope": scope().to_dict(), "context_refs": [ref.to_dict()], "committed_at": "2026-09-07T08:00:00Z",
    })
    return FormalAgentExecution(
        "request-1", "web", "lv-formal-analysis", commit,
        FormalContextSnapshot(scope(), (FormalContextEntry(ref, selected),)),
        allow_tools=not selected_result, answer_from_selected_task_result=selected_result,
        read_only_tools=native, model_identity="second-model#0" if native else None,
        model_config_version="version-1" if native else None,
    )


@pytest.mark.parametrize("native", [True, False])
def test_answer_policy_preserves_complete_committed_text_and_selected_source(native):
    request = execution(native=native)
    payload = json.loads(request.prompt_content())
    assert payload["committed_turn"]["text"] == request.commit.text
    assert payload["selected_context"] == [{
        "usage": "context_only_not_current_instructions", "context_ref": request.context.entries[0].ref.to_dict(),
        "content": request.context.entries[0].content,
    }]
    if native:
        assert payload["answer_contract"]["mode"] == "grounded_native_analysis"
    else:
        assert "answer_contract" not in payload


@pytest.mark.parametrize("source,selected_result,mode", [
    ("live_voice.task_result", True, "direct_answer_from_selected_task_result"),
    ("live_voice.task_result", False, "direct_answer_from_selected_task_result"),
    ("live_voice.task_control_receipt", False, "explain_authoritative_task_receipt"),
])
def test_native_analysis_keeps_stronger_task_contract_exactly(source, selected_result, mode):
    native = json.loads(execution(source=source, selected_result=selected_result).prompt_content())
    cascade = json.loads(execution(native=False, source=source, selected_result=selected_result).prompt_content())
    assert native["answer_contract"]["mode"] == mode
    assert native["answer_contract"] == cascade["answer_contract"]


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [True, False])
@pytest.mark.parametrize("language,output_policy", [
    ("en", "For Native read-only speech, start the final answer"),
    ("cn", "本轮为 Native 只读语音分析：最终回答第一句直接给出结论"),
])
async def test_trusted_policy_is_execution_scoped_and_final_answer_remains_exact(monkeypatch, native, language, output_policy):
    from openjiuwen.harness.prompts import SystemPromptBuilder
    final = "会议室余量 10 分钟，仓库余量 40 分钟；以《现场 安排 v2.md》为准。\n详细计算：09:10−09:00=10 分钟。"
    instance = FormalInstance(OutputLease([RawChunk("answer", {"output": {"output": final}})]))
    instance.system_prompt_builder = SystemPromptBuilder(language=language)
    adapter = adapter_with(instance)
    request, inputs = formal_request()
    if native:
        resolver = ServerModelCatalogResolver(catalog_reader=catalog, model_builder=lambda client, _: model(client["model_name"]))
        selected = resolver.resolve("Second")
        monkeypatch.setattr(adapter, "_formal_model_resolver", lambda: resolver)
        instance._react_agent = SimpleNamespace(set_llm=lambda value: None, _config=SimpleNamespace())
        request.metadata.update(formal_live_voice_read_only_tools=True,
            formal_live_voice_model_identity=selected.identity, formal_live_voice_model_config_version=selected.config_version)
    chunks = [chunk async for chunk in adapter.process_formal_live_voice_stream_impl(request, inputs)]
    assert chunks[-1].payload["content"] == final
    assert (NATIVE_ANALYSIS_PRESENTATION_INSTRUCTIONS in instance.observed_prompt) is native
    assert (output_policy in instance.observed_prompt) is native
    assert output_policy not in instance.system_prompt_builder.build()
    assert NATIVE_ANALYSIS_PRESENTATION_INSTRUCTIONS not in instance.system_prompt_builder.build()
    assert len(instance.sent) == 1 and not adapter._stream_event_rail._formal_read_only_sessions
