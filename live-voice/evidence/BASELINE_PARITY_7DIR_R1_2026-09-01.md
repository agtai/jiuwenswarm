# 七后端目录基线一致性比对 — Review Cut R1 (2026-09-01)

> 结论:HEAD(R1 = `7b3581b58`)的失败集是净审计基线(`a6843d2d7`)失败集的
> **真子集**;12 个共有失败的测试 ID 逐字相同、六类错误签名计数逐一相等。
> 因此「该自动化范围内零新增失败」成立。本文件归档精确命令、环境与逐条证据。

## 1. 环境

| 项 | 值 |
|---|---|
| 解释器 | 主仓库 venv `D:\XGG AI\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe`,Python 3.12.9 |
| pytest | 9.0.3(仓库 pyproject 配置,`--no-cov` 附加) |
| 操作系统 | Windows 10 Pro 10.0.19045 |
| HEAD 工作区 | `D:\XGG AI\openjiuwen\jiuwenswarm-gen-interrupt-review` @ `7b3581b58` |
| 基线工作区 | 临时 detached worktree @ `a6843d2d766bf004955cdb7704a5eba8820ae23a`(比对后已删除) |

## 2. 精确命令

HEAD(R1):

```
python -m pytest tests/unit_tests/gateway tests/unit_tests/agentserver \
  tests/unit_tests/common tests/unit_tests/e2a tests/unit_tests/auto_harness \
  tests/unit_tests/live_voice tests/unit_tests/channel --no-cov -q
```

基线(唯一记录在案的差异:基线必须剔除在基线上挂死的文件——该挂死本身是
已归因并在 R1 修复的基线缺陷,见 `2612d23ff`/`38620156a`):

```
python -m pytest <同上七目录> --no-cov -q \
  --deselect "tests/unit_tests/agentserver/test_live_voice_p3_route.py"
```

## 3. 结果

| | 净基线 a6843d2d7 | R1 7b3581b58 |
|---|---|---|
| 汇总 | 13 failed, 6815 passed, 4 skipped, 61 deselected (12:22) | 12 failed, 6919 passed, 4 skipped (13:00) |
| p3_route | 整文件挂死,被剔除(61 用例) | 62 用例全部执行并通过 |
| 通过数差解释 | — | 6919 − 6815 − 61 ≈ 43 ≈ 本批新增测试数,账面自洽 |

## 4. 失败测试 ID(12 个共有,逐字相同)

```
tests/unit_tests/agentserver/rails/test_circuit_breaker_repeated_failure.py::test_equivalent_dict_json_and_tool_output_share_a_failure_signature
tests/unit_tests/agentserver/test_agent_manager_session_cleanup.py::test_same_key_creation_waits_for_old_root_cleanup
tests/unit_tests/agentserver/test_debug_trace.py::TestOtelTeamSpanFallback::test_ambiguous_runs_resolve_to_nothing_rather_than_the_wrong_trace
tests/unit_tests/agentserver/test_debug_trace.py::TestOtelTeamSpanFallback::test_fallback_none_when_no_run_and_contextvar_empty
tests/unit_tests/agentserver/test_debug_trace.py::TestOtelTeamSpanFallback::test_fallback_returns_the_running_root_span
tests/unit_tests/agentserver/test_debug_trace.py::TestOtelTeamSpanFallback::test_one_session_closing_does_not_blind_another_still_running
tests/unit_tests/agentserver/test_debug_trace.py::TestOtelTeamSpanFallback::test_patch_is_installed
tests/unit_tests/agentserver/test_debug_trace.py::TestOtelTeamSpanFallback::test_run_is_resolved_by_session_id_when_available
tests/unit_tests/agentserver/test_debug_trace.py::test_llm_span_lookup_falls_back_to_root_span
tests/unit_tests/agentserver/test_debug_trace.py::test_run_output_is_stamped_on_the_root_span
tests/unit_tests/gateway/test_harmonyos_dev.py::test_dev_init_installs_when_devecocli_missing_and_verifies_skills
tests/unit_tests/gateway/test_upload_storage.py::test_safe_upload_filename_strips_unsafe_parts[..\..\evil.md-.._.._evil.md]
```

基线独有(R1 上通过;与本批改动无关联路径,归因运行形状差异或 flaky):

```
tests/unit_tests/gateway/test_agent_mentions.py::TestAtFileExcludesAgentPrefix::test_agent_and_file_in_same_message
```

## 5. 错误签名计数(两日志逐一相等)

| 签名(前缀匹配) | 基线 | R1 |
|---|---:|---:|
| `ModuleNotFoundError: No module named 'openjiuwen.agent_teams` | 6 | 6 |
| `AttributeError: module 'openjiuwen.agent_teams` | 1 | 1 |
| `assert 'evil.md' ==` | 1 | 1 |
| `AssertionError: assert None is` | 1 | 1 |
| `E   assert 1 == 0` | 1 | 1 |
| `E   assert 0 == 1` | 1 | 1 |

## 6. 范围声明

本比对仅覆盖上述七个后端单测目录。另有前端 node --test 套件在 R1 全绿
(integrated-web 536/536、gateway-batch-speech 38/38、隐私 18/18、TTS 租约
7/7 等),但本文件不包含生产构建、完整集成与真实环境验收;那些属于
feature-complete 后迁移树上的重验范围。
