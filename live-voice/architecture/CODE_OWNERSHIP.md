# Live Voice 的正式代码归属

本页描述 2026-09-11 瘦身后的实现落位；当前执行状态由 [STATUS](../STATUS.md#current-execution-packet) 管理。原始逐模块审计、16 个提交评估见 [审计](../reviews/LIVEVOICE_CODE_REUSE_AUDIT_20260911.md)，实际代码量见 [迁移后清单](../reviews/SLIMMING_CODE_INVENTORY_20260911.md)。

## 三层职责

| 宿主 | 当前归属 | 应保留的边界 |
|---|---|---|
| AgentCore | 模型调用 guard、后台任务真正 settlement、Goal/output admission、精确 pending input、Team/Native source 与 checkpoint 原语 | 不依赖 JiuwenSwarm 项目授权、私有 Store、WebSocket 或音频 ACK |
| JiuwenSwarm runtime | 配置解析、共享 Session 执行、不可变 work/model/tool/source 上下文、Team/SwarmFlow 接入、正式 Task/Executor 与持久化恢复 | 管理应用会话、配置、文件副作用和持久化；供 Voice 与已有文字入口消费 |
| JiuwenSwarm Live Voice | 麦克风/音频、ASR/TTS、Realtime、turn/response、已播放历史、语音来源校验、语音业务映射与装配 | Agent 完成不等于用户已听到；播放 ACK、打断、重播、声音状态不可由 SDK 执行状态替代 |

语音不是第三个独立 Agent 框架。当前 Live Voice 本来就在 JiuwenSwarm 仓库内；本次把其中通用执行从 `server/live_voice` 归回 `server/runtime`。SDK 原语直接来自固定的 AgentCore 源码，没有把 SDK patch 镜像到 Voice。

## 代码、测试、配置与文档落位

| 内容 | 当前位置 / 正式合入位置 |
|---|---|
| 通用 Session producer、保留/回放、输出归属与关闭 | `jiuwenswarm/server/runtime/session_execution.py` |
| 工作上下文、Agent 配置和模型调用边界 | `server/runtime/execution_context.py`、`agent_resolution.py`、`agent_adapter/` |
| 既有 Team/SwarmFlow 执行、回复、查询 | `server/runtime/team_execution*.py`、`team_workflow_capabilities.py`、`workflow_queries.py` |
| 正式 Task、Store、调整队列、Direct 文件 Executor | `jiuwenswarm/server/runtime/formal_tasks/` |
| checkpoint/effect/authority/recovery receipt | `jiuwenswarm/server/runtime/durability/` |
| Voice 语义、Provider、会话和播放账本 | `jiuwenswarm/server/live_voice/` |
| 音频数据面、注册和媒体传输 | `jiuwenswarm/gateway/live_voice/` |
| Web 语音交互 | `jiuwenswarm/channels/web/frontend/src/features/live-voice/` 与 `src/components/ChatPanel/` |
| 公共 wire 类型 | `jiuwenswarm/common/schema/` 与 Web 端契约；保留 wire 版本和严格校验 |
| fakes、旧 prototype、旧 TaskCore/Executor、scripted Cascade | 后端 `tests/support/live_voice/`，Web `frontend/tests/support/live_voice/`，退出生产 imports |
| 回归与私有场景 oracle | 现有 `tests/unit_tests/live_voice/`、`tests/integration_tests/` 和 Web tests；直接 import 新模块，保留已有 fixture 身份与命令 |
| 默认配置和应用启动 | 应用 configuration/resources、`pyproject.toml`/`uv.lock`；启动选择随显式 configuration directory |
| 私有配置、项目、SQLite、音频、凭据 | 留在用户当前运行目录；不复制进两个仓库，不因改路径迁移数据库 |
| 使用/架构/运维文档 | `live-voice/README.md` 路由到 STATUS、当前架构和 runbooks；无需把整个文档文件夹打包进 AgentCore |
| 历史 review、evidence、阶段 runner | 仍有现行引用/独有 oracle 的保留；Git 负责历史恢复，不把这些内容搬入 SDK 或恢复已退役 W2 Gate |

根 `pyproject.toml` 的包发现限定 JiuwenSwarm/jiuwenbox；Web 发布资产来自 `frontend/dist`。测试支撑不是生产模块，前端移动的支撑只由测试命令构建。本次未生成新发布包或覆盖运行中的 dist。

## 已消除的重复维护

- Native Work/Agent delegate 与 Web chat 使用 Host 共享执行服务，取消 Voice 私有 producer 和执行器缓存。
- Agent 输出校验与 SDK settlement 使用现有共同实现，退出 Voice 的重复缓冲/等待逻辑。
- 配置化 Agent、model/tool/source 的绑定由 Host/SDK 负责，Voice 保留语音投影与 journal。
- 删除 Responses-only SDK patch 和独立 wheel builder；依赖锁定远端不可变提交，避免同版本号掩盖源码差异。
- Task Store、durability、Direct Executor 只有新的 Host 路径；没有兼容转发副本或第二数据库。

拆文件本身不减少实现量。Web 已分离无状态操作和诊断视图，Registry 已分离结果上下文 codec 与诊断投影；原 controller/Registry 继续统一持有状态。当前仍有大文件，不能宣称所有类已经拆成小模块。

## 保留项的具体原因

1. Host `formal_tasks` 对 `live_voice_contract_v2` 和 `native_task_source` 的兼容依赖仍存在。前者保存当前 wire/持久化身份，后者验证实际 Native 语音来源。要完全解除反向依赖，应先规定通用 source-evidence 接口，再注入 Voice 校验器；本次没有用弱类型或跳过验证来制造“完全解耦”。
2. P1、Cascade、Native、flag-off 和仍支持的入口不是死代码。当前没有取消这些产品能力，因此保留其适配器、播放边界和测试。
3. Python/TypeScript 的严格验证位于不同信任边界，不因形似而删除。单一 schema/codegen 必须先定义表达 unknown-field/version/operation 差异的规范，不能自动把两个 allowlist 合并。
4. 旧 runner 保有独有失败场景；移出生产的 fake 仍用于测试。删掉它们只会减少测试资产，不会让实际运行代码更轻。
5. 未纳入候选分支新增的 Core Workflow bootstrap、新 Agent-input RPC，以及新的 Native Goal/Team/Workflow 操作；本次没有借重构扩展产品范围。

以上不是阻止已授权工作的额外审批流程，而是本次兼容性重构的保留理由。进一步改变来源契约、支持范围或公共协议应作为可说明收益的独立改动；不能宣称在本次已经完成。

## 合入与部署准备

AgentCore 已有的 12 个提交按 `ffeb1abcc5cc0bc72b5c813a3316d4334d39e15f` 直接消费；Host 四个候选提交按职责适配，保留当前分支后续 result/adjustment/file 修复。依赖来源和恢复说明见 [固定 SDK](../runbooks/AGENTCORE_SOURCE.md)。

本地提交按模块组织，包含迁移消费者、测试和记录。合入目标仓库时，AgentCore 接收通用 SDK 原语，JiuwenSwarm 接收本地 Host/Voice/Web/config/test/doc 改动；不要把整个 `live-voice/` 文件夹复制进 AgentCore。未来上游正式版本可以替换固定 SHA，但必须对应同等源码身份与能力。

本次证据覆盖受影响实现边界，详见 [执行记录](../reviews/SLIMMING_EXECUTION_20260911.md)。它不是整个产品 feature-complete、运行服务已重载或声音验收的证明。没有 push、远端分支更新、发布或重启服务；现有未完成的产品问题仍由 STATUS 管理。
