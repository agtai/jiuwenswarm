# 前台时延优化方向的源码验证 — 2026-09-06

> 状态：只读源码验证（Tier 0 文档），基线 `hx/0812_live_voice_w3@7c7aad7b8`。输入是 demo 期间
> 11 次前台回答的 profiling 汇总（语义判断 33.7 s、Agent 回答及工具 48.7 s、输入准备 6.9 s、
> 任务路由与分发 5.4 s、回答交付 6.4 s、ASR 收尾 4.8 s、TTS 初始化 0.5 s、TTS 首段 8.4 s、音频
> 缓冲 3.9 s）。本文逐条核对此前提出的优化方向是否被代码支持，没有做任何改动或实测。

## 1. 结论先行

| 方向 | 验证结果 | 证据要点 |
|---|---|---|
| 语义判断：每次请求体量大 | **成立** | system message 每次约 26.4K 字符：`_INSTRUCTIONS` 13,188 字符 + 每次重新生成的 JSON Schema 13,142 字符（`committed_input` 相位、无 pending/history 时）；user message 是输入 ≤8 KB 加上下文 ≤96 KB |
| 语义判断：模型客户端每次重建 | **成立，此前未列出** | `TaskSemanticResolver.resolve` 调 `self._model_resolver.resolve(None, instantiate=True)`，`ServerModelCatalogResolver.resolve` 在 `instantiate` 时每次执行 `self._model_builder(...)`，没有缓存；跑在 `asyncio.to_thread` 里，span 名 `semantic.model_configuration` |
| 语义判断：结构化重试翻倍 | **成立** | `for final_attempt in range(2)`，仅当第一次结果 `SEMANTIC_OUTPUT_INVALID` 时用 `_structural_feedback` 重发一次；上限 2 次模型调用 |
| 语义判断：每次尝试前的校验开销 | **成立，此前未列出** | 每次尝试前 `await before_invoke()` = `to_thread(validate_context)` → `_resolve_production_input_authority(operation="task.list", require_clean=False)` → 权威解析里的 `_read_revision` 同步 `subprocess.run(["git","rev-parse","--show-toplevel","HEAD"])`，再加 `context.require_usable` |
| 语义判断：换更快模型 / 调 reasoning 档位 | **可行，且档位是首要杠杆** | 语义判断取目录默认项（`resolve(None)`）。默认项因实例而异：用户主配置与 2026-08-21 的 batch-off demo 数据目录是 `deepseek-v4-flash`；正式验证数据目录（`jiuwenswarm-data-live-voice-p3-9-acceptance-20260831-215317`）自 2026-09-05 起默认 `gpt-5.6`（OpenAI，`reasoning_effort: low`，备份文件显示先试过 none 再改为 low），与 demo profiling 记录的 `gpt-5.6#0` 一致。`bounded_semantic_request_options` 只对 DeepSeek 官方端点关闭思考，对 OpenAI 模型不做任何 reasoning 约束，语义调用继承目录里的 `low`。`_select` 支持按 identity/模型名/别名选择，只需目录加一项并传 intent，即可给语义判断单独配更低的 reasoning 档位或更快模型 |
| Agent 工具串行 | **不成立** | 已安装 `ReActAgentConfig.parallel_tool_calls` 默认 `True`，`ToolCard.parallel_safe` 默认 `True`，`_execute_parallel_tool_tasks` 用 `asyncio.gather` 并发执行 parallel-safe 工具；jiuwenswarm 未改这两个默认。真正的杠杆是让模型在一轮里发出多个 tool_calls，而不是改 harness |
| 回答长度写进指令 | **部分成立，受 D-115 约束** | D-115 禁止 Live Voice 限制或改写 Agent 输出，只允许“软性输入引导”；`FORMAL_VOICE_PRESENTATION_INSTRUCTIONS` 已含 “This is a spoken conversation. Adapt explanation and detail to the current …”。可以加强软引导，不能加硬性字数门 |
| no-tool 缓冲扣住首句 | **只影响无工具轮** | `jiuwenswarm_round_harness` 在 `execution.allow_tools` 为假时把全部 `chat.delta` 存进 `pending_no_tool_text`（上限 32 KB）直到 `chat.final`；但 registry 里 `allow_tools = decision.route == "dialogue" and continuation_action != "decline"`，普通对话轮允许工具，delta 正常流出；受影响的是 decline/委托回执等无工具轮 |
| TTS 每次新建连接 | **成立** | `openai_streaming_speech._default_sse_factory` 每次合成新建 `httpx.AsyncClient(timeout=None)`，随响应一起 `aclose`；没有连接复用，每个回答重新付 TCP/TLS 握手 |
| TTS 按句首段 | **未追踪到** | Gateway 的 `product_streaming_synthesis` 与 `streaming_synthesis_route` 里没有句级切分逻辑；对话 delta 如何汇成合成单元本轮没有完整追到，留作实测项 |
| 前台每轮跑 `git status` | **不成立** | `_require_admissible_worktree`（含 `git status --porcelain --untracked-files=all`）只在 `require_clean=True` 时执行，而该参数只在 Task dispatch 路径为真；语义与对话路径三处调用全部传 `require_clean=False` |
| 前台每轮跑 `git rev-parse` | **成立，此前未列出** | `ServerSessionProjectAuthorityResolver.resolve` 每次都调 `_read_revision`，同步 `subprocess.run(["git","rev-parse","--show-toplevel","HEAD"])`；一轮提交里权威解析发生多次（每次模型尝试前的 `validate_context`、`read_task_control_snapshot` 三次、`resolve_production_semantics` 本身） |
| SQLite 每操作开连接 | **成立，幅度未测** | `SqliteUnifiedCommittedInputJournal._connect` 每次 `sqlite3.connect` 并设两条 PRAGMA；`_run_unified_submit_decided` 内有 35 处 `to_thread`、至少 8 次 journal/continuity 操作和 3 次 `read_task_control_snapshot` |
| 回答交付段的组成 | **未定位** | 历史写入 `persist_assistant` 发生在浏览器 ACK 之后（`acknowledge_presentation_with_history` 内），影响回合收尾而非首字可用；“模型结束到文本可用”之间的 fence/ledger/E2A 往返本轮没有实测证据 |

## 2. 修正后的优先级

1. **语义判断（3.1 s/次）**：(a) 为语义调用单独配置 reasoning 档位（gpt-5.6 当前继承 `low`，闭合 schema 分类可试 minimal/none，需与 09-05 曾回退 none 的原因对照）；(b) 缩小 26K 字符的 system 段（本地字符串构造只约 0.3 ms，收益在 token 与 Provider 缓存，不在本地缓存）；(c) 模型包装对象每次重建实测约 28 ms，按需缓存；(d) 把每次尝试前的 `git rev-parse` 改为按轮缓存或按需读取；(e) 目录加一项更快候选并按语义准确性对照。
2. **Agent 回答（4.4 s/次）**：并行工具已是默认，改为核对真实 trace 里模型是否一轮发多个 tool_calls，以及 LiveVoice rail 的 tool hold 是否在释放后引入串行；回答长度只加软引导，遵守 D-115。
3. **TTS 首段（0.76 s/次）**：合成用长生命周期的 `httpx.AsyncClient` 复用连接；按句首段先实测对话 delta 到合成单元的粒度再决定。
4. **代码层四项（约 2 s/次）**：先把 `_read_revision` 的子进程调用改为按轮缓存并确认它没有在事件循环线程上执行；journal 改为每轮一个连接或连接池；这两项与 B2b 的授权 owner 合并同向，不新增状态机。回答交付段先用 span 定位，不猜。

## 3. 本文没有做的

没有运行 profiling 或任何测试；没有追完对话 delta 到合成单元的路径；没有量化 SQLite 与子进程各自的耗时占比。这些是动手前的第一步实测项。
