# D110 Alpha 自动化验证与环境阻塞记录 — 2026-08-12

> 本文是一次性验证记录，记录在 `hx/0812_live_voice_w3` 上执行 S6 环境关闭尝试的
> 结果：自动化面已完整跑通并定位/修复一个缺陷，真实路径因外部条件缺失无法执行。
> 当前可变状态仍只由 [STATUS.md](STATUS.md) 拥有。本文**不产生**新的 Alpha 验收结论。

## 1. 结论

本批次**未关闭 S6**，因此未进入 S7，也未执行 S8。按
[ALPHA_ACCEPTANCE.md](validation/ALPHA_ACCEPTANCE.md) §8 的定义，本次结果为
**`BLOCKED` — required external condition is unavailable**。

不受阻的自动化验证已全部完成并绑定到确切候选，其中发现并修复了 1 个 Alpha 引入的
测试缺陷。除该项外，Alpha 归因的自动化失败为 0。

## 2. 候选身份

| 项 | 值 |
|---|---|
| 验证候选 | `07cd6df86`（本记录中的修复提交） |
| 修复前候选 | `cf67bbc28d245730353104813e8855f5346e0139` |
| 对比基线 | `2a69c2b87d0ee080a4a30421cbcbcdf93183f340` |
| develop 基线 | `3f3cdbb7f45fdd29e7d03deafa5bca10e363434e` |
| 分支 / upstream | `hx/0812_live_voice_w3` / `agtai/hx/0812_live_voice_w3` |
| agent-core pin | `94e10cb6102c36fe78a64547957c0def97299273`（与 develop tip 相同） |
| Python / Node / Chrome | 3.12.11 / v24.18.1 / 151.0.7922.109 |
| 工作区 | `D:\XGG AI\openjiuwen\jiuwenswarm-w3`（独立 worktree） |

共享工作区 `jiuwenswarm` 仍在 `hx/0803_live_voice`，本批次未触碰。

## 3. 开始前检查的偏差

以下与常见预期不符，已核对但**未做任何修改**：

1. `origin/hx/0812_live_voice_w3` **不存在**。`origin` 是 atomgit 上游，W3 只推到过
   `agtai`。STATUS「Resume capsule」写的 `origin/…` 是错的，本次已随 STATUS 更正。
   这是 push 事故风险面，虽然本批次不推送。
2. worktree `jiuwenswarm-lv-parallel-integration`（`codex/lv-parallel-integration`）
   为脏：28 改 + 14 未跟踪，停在 2026-08-05/06。其 12 个未跟踪文件在 W3 中均已存在，
   判定为已被取代的脚手架。未吸收、未删除、未触碰。
3. 仓库共 65 个 worktree，另有 3 个 stash 与 1 个 prunable 记录。均未纳入候选。

## 4. 环境 preflight

只记录存在性，不记录任何凭据值、长度或散列。

| §四 项 | 结果 |
|---|---|
| A. Speech 六个变量 | **全部缺失**。仓库无 `.env`，仅有 `.env.template`；用户配置目录中亦无 |
| B. JiuwenSwarm Agent | **可用**。`~/.jiuwenswarm/config` 存在 Provider/model 配置结构 |
| C. Chrome | **可用**，151.0.7922.109 |
| C. 麦克风 / 输出设备 / 听感 | 需用户物理参与，未执行 |
| D. 私有 HTTPS/WSS | **缺失**。无 caddy/nginx/traefik/mkcert；443/8443 无监听 |
| E. 隔离运行环境 | 未创建（依赖 A/D，创建了也无法完成真实路径） |
| — W3 树 Python 环境 | originally 缺失，本次以 `uv sync --frozen` 建立 |

D-078 冻结的 Streaming 目标在源码中确实存在：`openai_streaming_speech.py` 内
`DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe-2025-12-15"`、
`DEFAULT_TTS_MODEL = "gpt-4o-mini-tts-2025-12-15"`、`DEFAULT_TTS_VOICE = "marin"`。
实现目标存在，缺的只是凭据与私有拓扑。

## 5. 已执行的验证

全部在候选树上运行，命令与结果如下。

| 检查 | 结果 |
|---|---|
| `pytest` live_voice + agentserver + gateway + channel + auto_harness + server | **4731 passed, 13 failed, 4 skipped**（254s） |
| `pytest tests/unit_tests/live_voice tests/integration/live_voice` | **1494 passed**（202s，在 `cf67bbc28` 上） |
| 前端 16 个 `test:live-voice-*` | **16/16 脚本通过，713 tests passed** |
| 前端 `tsc && vite build` | **PASS**，38.63s |
| `git diff --check` | clean |
| live-voice Markdown 相对链接 | **283 条检查，0 断链** |
| agent-core 符号解析 | `ModelAnomalyDetectionRail` / `get_agent_history_root` 均可解析 |

第 6 节说明 13 个失败的归属。

## 6. 唯一 Alpha 缺陷及修复

`tests/unit_tests/gateway/test_streaming_synthesis_route.py::`
`test_post_validation_failures_capture_no_request_text` 失败。

- **根因**：该测试沿 traceback 找「路由模块栈帧」的条件是
  `co_filename.endswith("streaming_synthesis_route.py")`。测试文件自身名为
  `test_streaming_synthesis_route.py`，**也满足该后缀**，于是走查在调用方（测试）栈帧
  即停止；随后 `capture_locals=True` 捕获的是测试自己的 canary 局部变量，断言必然失败。
  该失败与环境无关，任何 checkout 下都会发生。
- **产品侧无缺陷**：独立探针以正确栈帧走查复验，路由帧不含请求正文。
  `begin()` 中既有的 `request = None  # raw text leaves throwing frames` 与
  `_PreparedSynthesisRequest._payload = field(repr=False)` 两道擦除均有效。
- **修复**：改用 basename 精确比较匹配模块帧。修复后该文件 **40 passed**。
- **为何此前未暴露**：该文件位于 `tests/unit_tests/gateway/`，不在
  D107 使用的 `tests/unit_tests/live_voice` + `tests/integration/live_voice`
  验证路径内，属新增即未被跑到。**后续验证必须覆盖 gateway 下的 live-voice 测试。**

## 7. 13 个失败的归属判定

在 `D:/lvbase` 建立 `3f3cdbb7f` 纯 develop 基线 worktree（零 live-voice 代码），
用同一解释器跑同样 5 个文件作对照，验毕已移除：

| 树 | 同一 5 个文件的失败数 |
|---|---|
| develop 基线 `3f3cdbb7f` | **14** |
| W3 候选 | **13** |

即这 13 项**全部在 develop 上先行存在**，且 W3 比基线少 2 项
（`test_assemble_run_answer_*` 在 W3 通过，得益于 agent-core pin 提升）。
典型根因为库侧 API 漂移，例如
`openjiuwen.agent_teams.observability.span_context` 无 `_team_span_ctx`，
与 `LLMRetryRail` → `ModelAnomalyDetectionRail` 改名同类。

**Alpha 归因的自动化失败为 0。** 这 13 项不属 Live Voice 范围，本批次不修。

## 8. 静态检查观察

仓库无 `[tool.ruff]` 配置、无 CI workflow、无 pre-commit；仓库级 `ruff check` 报
520 error、843 文件待格式化，说明 ruff 非强制门禁。收窄到本次 Alpha 触及的 55 个
`.py` 文件为 21 error（17 个 E402、2 个 F841、1 个 F821、1 个 F541），集中在
`app_gateway.py` / `app_web.py` / `agent_ws_server.py` 这三个共享文件。

其中 `app_gateway.py:974` 的 F821 `Undefined name RoutingTarget` 由 develop 提交
`8f54b26a7 feat(team)` 引入，在 `3f3cdbb7f`、`2a69c2b87`、develop tip 均存在；因
`from __future__ import annotations`，字符串注解不在运行期求值，故不引发运行错误，
但类型检查无法解析。**非本次引入，本批次不修。**

## 9. S6 逐项判定

| 任务 | 判定 | 依据 |
|---|---|---|
| S6-01 | `SATISFIED` | 源码与确定性自动化通过，无 Alpha 归因失败 |
| S6-02 | `ENVIRONMENT` | Speech 凭据完全缺失，真实 Streaming STT/TTS 一次都未执行 |
| S6-03 | `ENVIRONMENT` | Agent 配置可用，但真实设备、听感与真实 Agent 测量未执行 |
| S6-04 | `SATISFIED` | 同 S6-01 |
| S6-05 | `ENVIRONMENT` | 无私有 HTTPS/WSS 拓扑；benchmark/privacy 自动化层已就位并跑通 |
| S6-06 | `ENVIRONMENT` | 依赖 S6-02 与 S6-05 的真实路径 |

`alpha_benchmark.py` 确实产出 `p50_ms` / `p95_max_ms` / `observed_failure_count` /
`min_sample_count` / `failure_class`，S6-05 的 benchmark oracle 名副其实；缺的是把它
跑在真实链路上。

**S6 未满足退出条件**，故本批次不进入 S7-01，不冻结 A2 候选，不进行 S8。

## 10. 已完成的 S7 前置工作（不构成阶段进入）

以下工作不依赖真实环境，已完成并绑定候选，待 S6 关闭后可直接复用：

- S7-01 的身份冻结事实已采集（第 2 节）。
- S7-02 的自动化部分已完成（第 5 节）；真实路径部分未执行。
- S7-03 的部分审查已执行：确认 streaming 测试全部使用 fake 且**未冒充真实 Provider**
  （无出网调用，`api.openai.com` 仅作为被断言的构造字符串出现）；Alpha diff 中无硬编码
  凭据、无二进制/音频、无机器私有路径。**44,719 行的完整 cold review 与独立 review
  未完成**，不得记为已满足。

## 11. 解除阻塞所需

1. 具备 Realtime transcription / Audio Speech 权限的 OpenAI API access，key 仅注入
   Gateway 的 `LIVE_VOICE_SPEECH_API_KEY`，并按 D-078 配置 base/provider/模型/voice。
2. 私有 same-origin HTTPS/WSS 反代与受信证书（证书信任变更需单独批准）。
3. 用户在真实 Chrome、麦克风与输出设备上参与 S6-02/03/06 的物理与听感确认。

其中任一缺失都不得关闭 S6，也不得据此给出 Alpha PASS。
