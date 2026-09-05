# Live Voice 指令、技能与文档审计 — 2026-09-05

> 审计基线：`ebd2b457525b58e90380603f1ee6ce560ee77db9`。开始时工作区干净，分支与 upstream ahead/behind 为 `0/0`。
> 本文是按用户要求生成的条件审计记录，不是新执行包、默认必读入口或产品验收结果。建议尚未实施；当前项目判断仍由 [STATUS](../STATUS.md) 管理。

## 依据、范围与方法

已读取 Eric Provencher 的 [Rethinking skills and prompts for GPT-6 Astra](https://x.com/pvncher/status/2095991462416490862)，发布时间为 2026-09-04 21:44 UTC。X 页面直接读取返回 403；通过公开文章数据读取正文，并用 X 的 syndication 数据核对作者、标题、原帖及文章关联。文章的主要建议是收窄技能触发、按需读取、减少过细流程，重新审视多余确认与过早停止，并明确任务完成边界。

同时核对官方 [技能加载说明](https://learn.chatgpt.com/docs/build-skills)、[AGENTS.md 加载规则](https://learn.chatgpt.com/docs/agent-configuration/agents-md)和 [模型指令遵循说明](https://developers.openai.com/api/docs/guides/latest-model)。技能目录元数据与选中后读取的正文应区分；没有证据表明本次目录实际发生截断，也不能把所有技能正文长度当作每轮输入量。

覆盖分为三层：

- 开发指令：根目录及前端两份 AGENTS.md、README、STATUS、TESTING、文档规则、索引、当前验收/演示/runbook 和发现冲突所需的决策、旧计划章节。
- 技能与业务 Agent：本次会话目录中的 31 个 Codex 技能入口；仓库 21 个内置业务技能入口、UI E2E 技能和中英文 AGENT 模板；抽查实际加载路径。
- 文档结构：对基线下全部 180 份 Live Voice Markdown 及相关根入口检查显式 Markdown 本地链接。语义审查聚焦当前权威及冲突路径，没有逐段重审全部历史证据。

本机全局 `~/.codex/AGENTS.md` 为零字节，未发现其 override；仓库业务技能目录不等于 Codex 当前技能目录。其他 worktree、临时测试数据副本、未列入本次目录的缓存技能、私人运行目录中的既有 Agent/技能副本不冒充已审计的当前生效指令。没有读取凭据、修改配置、启动服务或执行真实 Agent/音频任务。

## 主要发现

以下 P2 表示应修复的指令或文档问题，P3 表示较低优先级的维护问题；它们不是产品运行故障的严重度判定。

### F01 · P2：通用技能形成过宽触发和重复批准链

位置：本机 `superpowers/6.3.0/skills/using-superpowers/SKILL.md:11–27`、`brainstorming/SKILL.md:14–19,35–61,87–103`、`writing-plans/SKILL.md:155–169`。

`using-superpowers` 把“1% 可能适用”也设为必须调用；brainstorming 的描述覆盖任何行为修改，并要求有明确范围的一文件修复也先提出设计、停止并等待新的 yes。它还规定不确定时只升级流程，不能降级。后续计划流程再要求选择执行方式。

对已经明确授权的局部修复，这会产生额外用户往返；对已经有接受设计/执行包的任务，会重复设计批准。不能因此推断过去某次停顿就是这些文件导致：这里只证明当前文本存在该行为诱因。

建议：把探索性设计与现有范围内的实现分开；尊重已经给出的授权和接受包，只有新产品决策、范围扩张或真正的外部权限边界才暂停。技能只按实际任务适用，不通过极低概率触发链加载。修改对象应是可维护的技能来源或项目兼容规则，不能把直接改插件缓存当作持久方案。

### F02 · P2：技能测试/审查要求与仓库按风险闭环冲突

位置：`superpowers/.../finishing-a-development-branch/SKILL.md:14–24`、`writing-plans/SKILL.md:38–52`；仓库 [TESTING](../../TESTING.md) `:69–89,115–147` 和 [AGENTS](../../AGENTS.md) `:5,48–55`。

分支收尾技能要求完整项目测试全部绿后才继续；计划技能偏向每任务独立测试/审查和细粒度提交。Live Voice 已有更具体的规则：风险按实际变更边界分配；无关矩阵维度排除；独立审查在 Tier 2/3 的连贯模块边界发生；已知无关失败要分类，不能自动扩大本批范围。

建议：由 TESTING 定义所需检查和停止条件。保留有意义的回归、独立审查和真实边界验证；取消重复全量测试及按小步骤创建提交的暗示。不得据此忽略变更引入的失败或仍然适用的安全证据。

### F03 · P2：强制读取的 STATUS 已偏离简短状态入口

位置：[AGENTS](../../AGENTS.md) `:29–35`、[README](../README.md) `:3–5`、[STATUS](../STATUS.md) `:76–149`；[文档规则](../DOCUMENTATION_RULES.md) `:51–60`。

README 为 37 行、2,701 字符，路由结构合理。但 STATUS 为 229 行、19,437 字符；根 AGENTS + README + STATUS 共约 30,345 字符，每个 Live Voice 任务都要读取。单是 STATUS `:86–134` 就有约 3,721 字符的多次采样、时间、RMS 和故障调查过程。

“当前执行包”开始描述被动 Observability、保持 capture/presentation 权限不变，随后放入新的耳机暂停/恢复行为修复，再宣布 instrumentation 已关闭；读者难以迅速确定下一项授权工作。Observability 能力行仍有 deployment 未完成的表述，正文却描述了已部署样本。

建议：保留当前判断、能力矩阵、当前最小执行包、剩余证据和依赖；把已有排障过程保留在相应 evidence，仅从 STATUS 链接。以最新耳机修复的 owner、风险、实现状态、下一验收和排除项表达当前工作，避免重复做已关闭 instrumentation。按任务需要读取相关状态章节；不要为了缩短文档删掉未完成事实。

### F04 · P2：旧候选 PASS 仍被标为当前结果

位置：[验收合同](../validation/PRODUCT_READINESS_ACCEPTANCE.md) `:181–198` 与 [STATUS](../STATUS.md) `:9–10,30–32`。

合同 §10 标题仍是 “Current bounded result”，正文展示 `83fde562…` 的 PASS、审查和测试数字。STATUS 已明确当前候选 PARTIAL，且该旧结果只具有历史、精确源码信用。前置指向 STATUS 的链接降低了误读风险，但没有消除两个“当前”描述的冲突。

建议：把 §10 变为明确的历史指针，保留既有 evidence 的旧 PASS；当前结论只保留在 STATUS。不得把这项文档清理记作产品进展，也不应推翻旧源码的真实验收。

### F05 · P2：生成期打断的可用配置没有进入 runbook

位置：[runbook](../runbooks/E2E_RUNBOOK.md) `:364–370,622–635`；[启动器](../../scripts/live_voice/start_hands_free_demo.ps1) `:3–11,513–525`；[前端入口](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx) `:6328–6334,7448–7477`。

源码已实现生成期监听和精确 response/round 的 interruption，但启动器默认关闭。`-GenerationInterruption` 只允许与 `formal-web-validation` 组合；省略时还会清除继承的 feature 环境值。runbook 一概写“生成期间不保持 capture”，没有说明已实现的 opt-in 入口。其 §9 又在未限定历史范围的“真实 Live Voice 验收”标题下要求 V0 thinking/tool supplement 和连续三次旧展示。

因此，用户 9 月 5 日预演脚本第 3 步不能仅凭代码存在就认定当前运行环境满足前提；也不能用 V0 supplement 代替新 generation interruption。静态实现检查不证明实际部署、麦克风、TTS 或完整旅程通过。

建议：明确默认关闭与显式开启两条路，文档化所需 profile/switch 和真实采样要求；把 §9 的 V0 流程标为历史并从历史路径进入。此次审计没有切换任何运行配置。

### F06 · P2：当前人工脚本与候选扩展范围不一致，并暗示重复口头确认

位置：[showcase](../demo/PRODUCT_READINESS_SHOWCASE.md) `:58–92`、[验收合同](../validation/PRODUCT_READINESS_ACCEPTANCE.md) `:126–140`、[STATUS](../STATUS.md) `:179–184,193–196`、[D-112](../decisions/DECISIONS.md) `:1773–1784`。

被称为“当前完整人工旅程”的 showcase 仍只覆盖单个 detached Task，创建要求 “Commit and confirm”，修改要求检查 clarification/confirmation。当前缺失证据则明确包含 A/B 分别管理、取消 B、A 离线完成、通知确认/刷新去重、保留 A 并创建 A2；D-109/D-112 已允许明确的本地创建/修改意图提供同意，不要求额外口头 yes。

建议：区分稳定的受控候选最小合同与本次候选的已接受扩展，给出唯一的当前场景入口。把用户明确意图与后台 durable confirmation 校验区分开；只有歧义或实际另行授权边界要求澄清。保留 pending/applied、取消前未完成、离开前未完成及原版不覆盖等实际核验。单任务旧合同的历史 PASS 不因新版场景扩展而被撤销。

### F07 · P2：条件历史路径仍可重新引入过时执行要求

位置：[REFERENCE_INDEX](../REFERENCE_INDEX.md) `:36`、[Web Alpha matrix](../roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md) `:180–192`、[完整 P3 计划](../roadmap/FULL_P3_EXECUTION_PLAN.md) `:965–973`、[D-093](../decisions/DECISIONS.md) `:1052–1053`。

索引仍把完整 P3 计划称为 live package gates；旧 matrix 要求读取 active S5–S8 执行计划；旧 P3 表的 “Current accepted decision” 仍写当前 Direct 的真实 D1/D2 路径。更新的 D-093 和 STATUS 已限制可构造 profile 为 D0/D2，D1 被拒绝；D2 内部 checkpoint/recovery 行为不能等同于可用 D1 profile。

建议：在被当前路径引用的旧章节入口限定历史身份，当前执行选择指向 README/STATUS 和后续决策。保留仍适用的契约和恢复证据，不恢复旧阶段队列或未经接受的 D1 能力。

### F08 · P3：三处本地章节锚点失效

扫描基线 180 份 Live Voice Markdown 及相关入口，共识别 675 个显式本地 Markdown 链接；目标文件均存在。三处锚点不存在，并已核对实际标题：

| 来源 | 旧锚点/问题 | 建议 |
|---|---|---|
| `D101_W2_NEW_ENVIRONMENT_MANUAL_HANDOFF_2026-08-11.md:22` | runbook 的 `validation-ready-before-signing` 已消失 | 指向保存该历史流程的真实证据，或明确段落已退役 |
| `decisions/DECISIONS.md:1225` | `55-d-100-response-scoped-streaming-correction-overlay` | 实际标题为 D-103，对齐锚点 |
| `evidence/P3_TERMINAL_NOTIFICATION_RECOGNITION_REPAIR_20260902.md:4` | STATUS 的旧 `reopened-terminal-task-notification-presentation-repair` | 改为合适的稳定历史证据入口，避免依赖可变状态标题 |

链接检查不覆盖所有代码片段内路径、裸路径、动态生成链接或全部历史事实；不能由“无缺失文件”推导文档一致。

## 应保留的规则

- 远程引用更新必须获得精确授权、保护无关用户改动及并行单写者规则属于已明确的用户边界。
- 根 AGENTS 已允许连贯局部提交；TESTING 已按风险和模块闭环，前端 AGENTS 已限定只约束新改代码，均不应被通用技能改成全仓迁移或重复批准。
- 真 Agent/Tool 执行、精确 Task/Attempt 目标、失败路径零越权副作用、pending 与 applied 的区分、不可变结果和物理音频验收属于产品契约。
- README 的条件路由、避免递归读取历史、Git 与运行事实优先于旧文档值得保留。

根 AGENTS `:9,17,25` 的远程审批重复可以去重；“exactly one route” 可以在将来的文档修改中明确为一个主路由加受影响边界所需小节。这些是表达改进，不构成绕过已授权边界的理由。

## 其余技能发现与生效边界

### F09 · P2：内置技能把普通任务扩大为另一套维护/批准流程

内置技能路径前缀为 `jiuwenswarm/resources/agent/workspace/skills/`。

- `project-maintainer/SKILL.md:3,43–64,229–236,353–359`：描述涵盖普通代码探索、修复和仓库分析；进入后可要求建立签名 key、读取五个维护索引、每符号一个审计 Agent，并分割超限维护文件。该根文件为 44,249 字符。已有“不是主调试流程”的限制，但通用触发及 preflight 仍会扩大普通阅读的成本。应限定为用户需要 `.doc_project_maintainer` 产物时使用，另设只读、按模块取上下文的轻路径。这套签名机制也不等于 Live Voice 已退役的 W2 Gate。
- `skill-creator/SKILL.md:65–151,178–185,290,432–435,509–519`：611 行、41,586 字符，要求先找社区参考、下载完整技能、目录树确认、成批 baseline/skill 执行及多次用户复核；还以 Claude 容易漏触发为由建议 pushy 的泛化描述。应使用适配当前宿主的 author/edit/evaluate 小路由，按变化范围验证。这项比冷门内置技能优先，因为默认安装列表包含它。
- `doc-update/SKILL.md:13–17,23,27–31`：把代码称为唯一真相，忽略已接受设计/政策与代码的差异；另外固定要求范围/结构/翻译确认和 1–3 个文件读取上限。应区分实现事实与意图权威，按实际依赖读取；只对有实质影响的未决范围提问。

### F10 · P2：过早停止、跨会话检索和外部优化触发需收窄

- `openJiuwen-DeepSearch/SKILL.md:3,10,15–16`：要求每次完整重读；启动后台进程并拿到 PID 后必须结束当前轮次，直到用户再次询问才检查报告。应以真实报告交付作为完成条件，在已授权运行中跟踪自己启动的任务；保留缺失配置由用户在本地补齐、不得索要密钥的规则。
- `cross-channel-history-retrieval/SKILL.md:4,14–17,31,66`：描述把任何历史事件、日期、人物问题都纳入触发，正文却是找用户过往对话；未指定频道时扫描全部会话，再粘贴命中原文。应只对明确或上下文清楚的“我的过往对话”使用，并限定所需会话及摘录。这里是静态指令风险，没有证明本次 Live Voice 访问过这些历史。
- `skvm-jit/SKILL.md:3,16–21,79–95`：任何技能失败/困惑后都要求外部 optimizer，默认模型为 OpenRouter 路径；`skvm-general/SKILL.md:24,143` 还要求向用户索要 API key。应把外部优化变成明确请求或已有精确授权下的任务；缺凭据时要求本地配置，不在聊天中索取。保留接受 proposal 后才部署的现有边界。

### F11 · P2/P3：正文中的刚性配方、过时命令和相互矛盾规则

| 技能/文件位置 | 已核实问题 | 修订方向 |
|---|---|---|
| `ppt-creation/SKILL.md:67–76,136,165–194` | 一处拒绝固定字数硬门槛，另一处要求 400–700 的视觉文字量；固定 Hero 页数、每页读版式和全读目录 | 根据用户选定模板应用风格约束；保留可编辑性、来源与布局检查 |
| `skill-omni-creation/SKILL.md:19–44,125,134–140,420–422` | 无图片也走五阶段；可选浏览器依赖失败禁止降级；禁止定点补读省略证据 | 分开网页/视频/代码路线，允许有依据的替代工具和必要补读 |
| `akg-agents/SKILL.md:17,58–70,101,126–143` | 未先区别已有配置就要求配置流程；指定脚本失败被视为整体终止；长合规汇报 | 验证现有环境，区分可修复调用失败与真实不支持边界 |
| `advanced-daily-report/SKILL.md:77,88–100,128,200` | 脚本路径写 `skills/daily-report/`，实际目录为 `advanced-daily-report`；绑定个人磁盘目录 | 从当前技能目录及授权项目推导路径 |
| `cross-channel-history-retrieval/SKILL.md:27`、`delayed-restart-app/SKILL.md:21` | Windows 示例遗漏 `agent/workspace/` 中的 `workspace` | 对齐真实安装路径；重启仍需用户意图及精确进程身份 |
| `swarmskill-creator/SKILL.md:6–7` | 英文指向不存在的 bundled `create-skill`，中文指向 `skill-creator` | 统一有效路由 |
| `llm-wiki/SKILL.md:30` | 查询段落误写 `wiki_lint` | 对齐该段真实查询工具 |
| `ascend-moe-optimizer-auto-trace/SKILL.md:26,201` | 一处要求全文参考，一处称仅完整示例时需要 | 统一为契约必需小节和可选完整参考 |

### F12 · P2：宿主技能适配和审查停止条件存在冲突

本机可复现位置以当前安装的 Superpowers 6.3.0 等版本为准；以下没有被当作要立即执行的工作流。

- `superpowers/.../using-superpowers/references/codex-tools.md:21–23` 声称 full-history fork 可以覆盖 model/effort，而当前工具 schema 明确不允许；`:51–55` 固定长等待和 `:64–78` 自动提出机器配置修改，也不应优先于当前工具与权限。应按实际工具 schema 适配。
- `superpowers/.../receiving-code-review/SKILL.md:43–56` 要求任一反馈不清楚就停止所有实现；`systematic-debugging/SKILL.md:195–210` 按固定失败次数强制升级。应继续不依赖该疑点的授权工作，只暂停受阻边界。
- `superpowers/.../subagent-driven-development/SKILL.md:372–438` 把反馈裁决推迟到循环上限，再允许带 parked findings 标记完成。应收到反馈就按接受范围分类；循环次数不决定未满足接受条件是否完成。相关 implementer 模板中的自动 commit 还须服从本仓库 shared-worktree 单写者规则。
- `superpowers/.../writing-skills/SKILL.md:374–393,575–645` 对技能编辑也强制先失败测试、行为措辞至少五次/variant 及部署流程；本机系统 `skill-creator/SKILL.md:149–161,203–219` 已按复杂度/风险分层。应采用一个一致的维护流程，保留复杂行为改动的有效实验，不把所有文字编辑变成同等实验。
- 本机系统 `openai-docs/SKILL.md:12` 的 web-first 与当前宿主对 OpenAI 产品问题的 local-first 规则冲突；`visualize/1.0.29/skills/visualize/SKILL.md:22–33` 禁止进度说明并要求每次压缩后完整重读，与宿主沟通/按需读取规则冲突。宿主规则优先。
- Computer Use `docs/confirmations.md:34–36,68` 的“即使预先批准也重问”和仅承认最初 prompt，未正确表达会话后续明确授权可以持续有效。此问题只在其原生 UI 适用域内，不外推为 shell 操作规则。

Sites 的建站/hosting、插件安装、Word/PPT/PDF/表格技能有各自领域约束，不应因 Live Voice 有 Web 前端或 Markdown 文档就自动引入发布、安装或文档渲染流程。Sites 是否适用于本仓库没有在本次确认；其通用 push 指令也不能代替本仓库精确 remote/ref/commits/mode 的授权。

### F13 · P2：修改模板不等于修复现有运行时指令

已核实的静态加载关系：

| 层 | 源码证据 | 可得结论 |
|---|---|---|
| Codex 开发指令 | 本次会话技能目录；根/前端 AGENTS | 31 个宿主技能与 21 个产品内置技能是两个目录 |
| 产品 AGENT 模板 | [AGENT_EN](../../jiuwenswarm/resources/agent/workspace/AGENT_EN.md)、[AGENT_ZH](../../jiuwenswarm/resources/agent/workspace/AGENT_ZH.md) 各 30 行；[utils](../../jiuwenswarm/common/utils.py) `:1158–1192` | skills 排除在普通模板复制之外；AGENT.md 等仅在目标不存在时复制，不自动覆盖已有运行副本 |
| 产品技能安装 | `utils.py:632,652–666` | 默认只安装 skill-creator/swarmskill-creator；存在的副本默认跳过 |
| 产品 Agent 技能 | [interface_deep](../../jiuwenswarm/server/runtime/agent_adapter/interface_deep.py) `:3678–3716,4283–4295` | SkillUseRail 读取安装目录及禁用列表，不直接把全部 bundled 正文注入 |
| 内置技能检索元数据 | [skill_toolkits](../../jiuwenswarm/agents/harness/common/tools/skill_toolkits.py) `:100–150` | 内置技能发现另有 80 字符 description 截取；限定适用条件不宜埋在长描述尾部 |
| 可选技能检索 | [skill_retrieval_prompt_rail](../../jiuwenswarm/agents/harness/common/rails/skill_retrieval_prompt_rail.py) `:65–104` | 有索引检索 prompt 时会抑制原生列表；已有渐进读取机制应保留 |
| Live Voice 前台 | [product_composition_registry](../../jiuwenswarm/server/live_voice/product_composition_registry.py) `:4653–4669`；`interface_deep.py:9308–9337,9397–9436` | 使用隔离的 Agent-profile facade、关闭 memory/交互工具并注入口语约束；不能据此证明具体 AGENT/技能正文已注入 |
| 后台 Code Task | [interface_code](../../jiuwenswarm/server/runtime/agent_adapter/interface_code.py) `:1210–1245,1369–1393`；[project_memory_rail](../../jiuwenswarm/agents/harness/common/rails/project_memory_rail.py) `:37–48` | 保留 ProjectMemoryRail，移除 coding memory/LSP/subagents；读取的是 JIUWENSWARM.md 等项目规则源，不能与 AGENT 模板混称 |

外部 openjiuwen 的 SkillUseRail 正文加载实现、机器私有安装/启用状态及实际 prompt 捕获未验证。因此不能把静态风险写成当前 Demo 已发生的误操作或延迟根因。若后续要求修复并部署，须先核对实际副本和受影响 owner；单改模板/插件缓存不构成运行闭环。

AGENT_EN/ZH 的按需技能指针可保留。心跳中“发现有趣内容/超过八小时没说话就联系”的示例应服从用户配置的通知偏好；模板也可用一句话补足“完成已授权交付与验证，只有真实阻塞才暂停”的边界。条件引用 BOOTSTRAP 不代表项目实际存在或每轮必须执行该文件。

## 完整入口盘点

“保留”表示在其实际适用域内保留，不代表无须维护或默认启用；“调整”是审计建议，没有执行卸载、配置或正文变更。

### 本次目录的 31 个 Codex 技能

入口位于本机 Codex skills/plugin cache。系统技能为 `.codex/skills/.system`；Superpowers 为 `openai-curated-remote/superpowers/6.3.0`；primary-runtime 的文档类技能版本均为 `26.903.11726`。31 个入口合计 6,969 行；原始 `description:` 行合计 7,990 字符（含 YAML 前缀/引号），不代表实际加载 token 或截断情况。

| 技能 | 行数 | 处理建议 |
|---|---:|---|
| imagegen | 315 | 位图资产任务按需使用；CLI 细节可移出入口 |
| openai-docs | 38 | 对齐宿主来源优先级，保留单主路由 |
| plugin-creator | 249 | 保留显式插件创建/维护触发 |
| skill-creator（系统） | 229 | 保留，作为按风险维护技能的参考 |
| skill-installer | 58 | 保留安装触发，适配当前不可升级审批策略 |
| superpowers:brainstorming | 250 | 收窄触发和强制再次批准 |
| superpowers:dispatching-parallel-agents | 167 | 保留独立任务划分，按风险检查及 writer 权限 |
| superpowers:executing-plans | 64 | 调整自动串联和全局停止条件 |
| superpowers:finishing-a-development-branch | 225 | 调整全量测试/菜单/授权默认值 |
| superpowers:receiving-code-review | 205 | 保留技术核验，移除全局一刀切停止 |
| superpowers:requesting-code-review | 95 | 按 TESTING 的模块与风险路由 |
| superpowers:subagent-driven-development | 568 | 收窄重复审查/循环上限规则，保留受影响复验 |
| superpowers:systematic-debugging | 283 | 保留证据方法，调整固定升级配方 |
| superpowers:test-driven-development | 320 | 按行为风险保留有效回归，移除逐函数/删除重做规定 |
| superpowers:using-git-worktrees | 167 | 实际需要隔离时用；调整强制 setup/baseline/确认 |
| superpowers:using-superpowers | 63 | 移除通用会话触发和 1% 规则 |
| superpowers:verification-before-completion | 120 | 保留证据优先，允许复用未变化源码的有效证据 |
| superpowers:writing-plans | 171 | 保留复杂工作计划，减少细步骤/整段代码重复/交接暂停 |
| superpowers:writing-skills | 679 | 与系统 skill-creator 对齐，实验按风险触发 |
| computer-use:computer-use（26.901.31953） | 29 | 原生 Windows UI 按需；修正持续授权表述 |
| visualize:visualize（1.0.29） | 514 | 保留解释/交互图用途；调整通信规则、强制重读及长正文 |
| sites:sites-building（0.1.57） | 233 | 限定真实 Sites 任务，不泛化为任意 Web 代码 |
| sites:sites-hosting（0.1.57） | 51 | 发布域按需，叠加项目精确远程授权 |
| deep-research-work:deep-research（0.1.14） | 183 | 保留明确 Deep Research 触发 |
| plugin-management:plugin-management（0.1.0） | 58 | 对齐实际可调用 discovery/安装工具 |
| documents:documents | 537 | DOCX 按需；可按布局传播范围复验，勿用于 Markdown |
| pdf:pdf | 150 | 保留 PDF/表单限定及真实表单校验 |
| presentations:Presentations | 230 | 将通用措辞/装饰禁令改为上下文默认值 |
| template-creator:template-creator | 206 | 保留显式可复用模板触发 |
| spreadsheets:Spreadsheets | 218 | 保留文件表格限定及比例适当的验证 |
| spreadsheets:excel-live-control | 294 | 保留明确 live Excel 会话限定 |

本机另外存在未列入本次目录的 `.system/review-agent/SKILL.md`，只记录其存在，没有假定它能被本次调用。工具发现/安装类建议须服从当前 callable schema，不能仅凭技能里的旧工具名称执行。

### 仓库 21 个业务技能与一个 UI 测试技能

下面的行数及字符数包含 frontmatter；字符数按 Unicode 码点计，含原文件 CRLF。21 个业务入口合计 4,235 行、240,944 字符。这是存储规模，不是单轮实际上下文。

| 内置目录名 | 行数 | 字符数 | 处理建议 |
|---|---:|---:|---|
| advanced-daily-report | 296 | 5,783 | 修正脚本/项目路径；样例/API/变更记录移至参考 |
| akg-agents | 143 | 3,688 | 简短触发，条件化配置/恢复及合规报告 |
| ascend-moe-optimizer-auto-trace | 218 | 19,859 | ABI/工程步骤移参考；统一必读条件 |
| ascend-moe-optimizer-trace-analyzer | 217 | 7,426 | 保留 trace-only/指标限制；输出 schema/样例按需读 |
| cross-channel-history-retrieval | 67 | 2,295 | 收窄个人对话回溯和范围；修 Windows 路径 |
| deepep-to-cam-converter | 168 | 5,735 | 保留兼容/损失决策，移除已有上下文下的重复访谈 |
| delayed-restart-app | 38 | 1,095 | 修正路径；保留用户重启意图和进程核验 |
| doc-update | 96 | 2,040 | 区分实现/设计权威，减少不必要暂停 |
| financial-document-parser | 162 | 3,098 | 保留精确性与来源；API/示例按需读 |
| gitcode-api | 92 | 2,422 | 保留条件参考，触发限定 GitCode |
| harmonyos-dev-suite | 61 | 5,162 | 保留轻路由，收窄 App/emulator 泛关键词 |
| llm-wiki | 41 | 3,278 | 限定 wiki 而非所有文档，修查询工具名 |
| openJiuwen-DeepSearch | 173 | 4,915 | 交付报告前不提前结束；去强制全文重读 |
| ppt-creation | 239 | 8,462 | 拆创建/编辑/阅读路线，统一风格约束 |
| project-maintainer | 361 | 44,249 | 优先重构为明确产物维护及小范围上下文路线 |
| skill-creator（产品） | 611 | 41,586 | 优先适配宿主、缩短路由/描述，实验按风险执行 |
| skill-gen-4-enterprise-doc | 56 | 8,425 | 描述去流程；密集安装/降级配方按需读 |
| skill-omni-creation | 520 | 16,168 | 拆工作流和模板；允许必要证据补读/工具替代 |
| skvm-general | 144 | 9,978 | 限定 SkVM 请求；CLI 移参考，不索要聊天密钥 |
| skvm-jit | 142 | 11,794 | 外部优化需明确范围/授权，细节按需读 |
| swarmskill-creator | 390 | 33,486 | 保留输出形态/validator 路由；阶段配方移参考，修无效路由 |
| tests/ui_e2e/SKILL.md（单列） | 95 | — | 现有 Todo/Cron 场景按需复用；不作为 Live Voice 音频验收入口 |

其他跟随 AGENT 模板的 SOUL/IDENTITY/HEARTBEAT/USER 也检查了用途：SOUL 已提示先看上下文再问；IDENTITY 是首次自定义表；HEARTBEAT 是注释示例；USER 为空。它们不构成 Live Voice 每轮强制全文读取列表。

## 建议处理顺序与验证边界

1. **预演文档修复**：先对齐生成期打断的 profile、旧 PASS 标签、当前扩展场景和明确本地意图的同意语义。验收状态仍保持当前真实判断。
2. **开发指令兼容**：保留项目 Git/权限/风险规则，明确已有授权与接受包优先；收窄 Superpowers 触发、审批、全量测试和审查循环。插件来源修订与本机设置变更分开评估。
3. **默认路径技能**：先修默认安装的产品 skill-creator/swarmskill-creator，再按真实使用情况处理其他技能；修好模板后核对实际运行副本，不假定自动覆盖。
4. **按需资料整理**：压缩 STATUS；把较长技能入口改成小路由；修三个历史锚点。不得删除仍有消费者的契约/证据，也不把本文加入默认必读链。

本批只新增这份审计报告，风险 Tier 0。验证是基线 Git 核验、入口盘点、当前权威交叉核对、重点源码/加载路径抽查、Markdown 链接/锚点检查和差异检查。没有运行 pytest、完整前端测试、模型评估、真实后台任务或物理音频验收，因为本批未改变这些行为；不授予任何产品能力或性能改进信用。
