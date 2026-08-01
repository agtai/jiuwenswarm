# Live Voice V0 验收手册

- 版本：V0 / Vertical Slice Demo
- 适用分支：`hx/0731_live_voice_ux`
- 最近更新：2026-08-01
- 状态：验收方案已准备；完整真机放行尚未执行

## 1. V0 到底是什么

V0 是“两周核心体验纵向切片”：核心用户旅程完整，但不是所有最终功能完整，也不是生产版。

```text
真实麦克风
→ final 识别文字
→ 真实 JiuwenSwarm Agent
→ 真实只读工具
→ 真实结果
→ 完整浏览器 TTS
→ 自动回听
→ 用户可以在处理中补充，或在朗读时停声并继续
```

当前代码和文档已经形成可恢复的 **V0 Candidate**。只有本文所有 V0 放行 Gate 都通过并留下证据后，才可以写成 **V0 Released / 已冻结**。已有 commit 证明“候选版本已经保存”，不等于“已经通过验收”。

V0 验证的是：这条真实链路能否在受控环境中重复成立，用户是否能感受到语音驱动 Agent、连续协作和及时纠正的价值。它不证明生产级全双工、跨设备稳定、带副作用工具的可靠取消或服务端一致性。

## 2. 本文与其他文档的边界

| 问题 | 权威入口 |
|---|---|
| V0 是否可以放行、如何记录证据 | 本文 |
| 如何从新机器恢复依赖、启动服务和检查健康 | [E2E_RUNBOOK.md](E2E_RUNBOOK.md) |
| 现场展示什么、说什么、失败时如何退场 | [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md) |
| 当前已经完成和未完成什么 | [STATUS.md](STATUS.md) 与 [HANDOFF.md](HANDOFF.md) |
| V0 范围、Shortcut Ledger 和两周计划 | [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) |
| 已接受的路线和技术取舍 | [DECISIONS.md](DECISIONS.md) |
| P1/P2/P3 和最终生产架构 | [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md) |

不要把一次成功录屏当作整体验收，也不要用自动化测试代替真实麦克风、Agent、Tool 和 TTS。

## 3. 验收结果只有四种

- `PASS`：步骤完成，判据全部满足，证据可定位。
- `FAIL`：实际行为不符合判据；保留失败时间线并新建 attempt。
- `NOT RUN`：尚未执行。
- `INCONCLUSIVE`：已经执行但证据不足或无法归属。

`NOT RUN` 和 `INCONCLUSIVE` 都不能按通过处理。

任何失败后的重试都必须保留原 attempt，不能覆盖失败记录。修复代码后形成新的 candidate commit；至少重跑受影响 Gate，涉及生命周期、路由、取消、TTS ownership 或识别提交时应重跑全部真机 Gate。

## 4. Gate 0：候选版本与环境身份

D-030 已结束 D-022 的临时 dirty/stash 窗口。运行本 Gate 时，不要回退或 stash 当前 Post-V0 开发分支；应从 `2c700934aa0024a7ab229644bf15934e9e8170e7` 新建独立 detached checkout/worktree，确认该验收目录工作区干净，并清除 `VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH` 与 `VITE_FEATURE_LIVE_VOICE_TASK_DEMO`。只有这个独立目录才是本文要验收的 V0 Candidate；当前累计分支上的任务、稳定句预读和后续 foundation 提交不得混入 V0 证据。

验收流程以**累计开发分支上的最新版本文**为准；`2c700934` detached 目录中的同名文件只是 Candidate 当时固化的历史副本，不负责描述 D-030 之后的验收隔离方式。所有构建、服务启动和真机命令都在 detached V0 目录执行，验收证据则回写累计开发分支。

在启动服务前记录：

```powershell
git status --short --branch
git status --porcelain
git rev-parse HEAD
git branch --show-current
git rev-parse --short=8 HEAD
git log -1 --pretty=format:%s
git fetch agtai
git merge-base --is-ancestor 2c700934aa0024a7ab229644bf15934e9e8170e7 agtai/hx/0731_live_voice_ux
$LASTEXITCODE
```

通过条件：

- `HEAD` 精确等于 `2c700934aa0024a7ab229644bf15934e9e8170e7`；
- `git branch --show-current` 输出为空，确认这是 detached V0 验收目录，而不是累计开发分支；
- `git status --porcelain` 输出为空；
- `git merge-base --is-ancestor ...` 返回 0，确认共享累计分支仍包含该不可变 Candidate；远端分支可以已经包含后续 Post-V0 提交，不要求与 V0 `HEAD` 的差异为 `0 0`；
- 全部结果记录在同一个 candidate SHA 下；
- Windows、Chrome、Node、Python、模型标签、`zh-CN`、麦克风、耳机和网络标签已经记录；
- 单用户、单 Chrome 标签页、Agent 模式，没有待确认问题、演进流程或无关后台 Agent 任务；
- 两个 Post-V0 feature flag 均未设置；
- 模型配置只验证存在和可用，不把 API key、完整 API base 或用户配置写入证据。

新机器必须从 `uv.lock` 和 `package-lock.json` 重建依赖，禁止复制其他机器的 `.venv` 或 `node_modules`。详细命令和私有配置边界见 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。

## 5. Gate 1：自动化、构建与文字主链

先执行 [README.md](README.md#直接验证) 中的完整命令集合。最低通过线：

- Live Voice 纯逻辑 **47/47**；
- 相关既有回归 **22/22**；
- TypeScript `tsc --noEmit`；
- Vite production build；
- Python `ruff`；
- `git diff --check`。

随后按 [E2E_RUNBOOK.md](E2E_RUNBOOK.md) 启动服务。浏览器必须真实收到 `connection.ack`，并先用文字请求确认：

```text
必须调用终端查看当前分支，不要根据上下文猜测，只回答分支名。
```

必须能定位 `chat.send → chat.tool_call → chat.tool_result → chat.final`，工具结果与候选仓库真实状态一致。文字主链失败时停止语音验收，先修复 Agent、项目注册、模型、工具或连接问题。

## 6. Gate 2：真实语音主链冒烟

在一个新 Agent Session 中进入 Live Voice，说：

> 调用终端查看当前分支，只回答分支名。

通过条件：

- 真实麦克风产生语义正确的 final；
- interim 只更新字幕，不产生用户消息、Agent 请求或工具副作用；
- final 只产生一个用户 Turn 和一次 `chat.send`；
- Agent 真实调用只读 Terminal Tool，结果是当前分支；
- assistant 完整回答从耳机实际朗读，技术标识符未截断；
- TTS 后自动回到 `Listening`；
- 至少一个样本覆盖 `new` Session promotion，Live Voice 没有退出；
- 无双播、旧声音、Retry、刷新或文字修正。

## 7. Gate 3：连续 10 个准确语音 Turn

### 7.1 开始前预取答案

验收者先在终端用只读命令记录当前 candidate 的预期值；不要把旧 commit 的固定答案写进脚本：

```powershell
git branch --show-current
git rev-parse --short=8 HEAD
git log -1 --pretty=format:%s
git log -1 --date=short --pretty=format:%ad
@(git status --porcelain).Count
@(git branch --format='%(refname:short)').Count
git rev-list --count HEAD
git rev-parse --abbrev-ref --symbolic-full-name '@{u}'
Split-Path -Leaf (git rev-parse --show-toplevel)
Get-Date -Format 'HH:mm'
```

### 7.2 固定中文语料

在同一个 Live Voice Session 连续执行。每轮必须等完整 TTS 结束并自动回到 `Listening` 后再说下一句。

| Turn | 固定口令 | 预期 |
|---:|---|---|
| 1 | 调用终端查看当前分支，只回答名称。 | 当前分支名 |
| 2 | 继续调用终端，查看最新提交编号的前八位，只回答编号。 | 预取的 8 位编号 |
| 3 | 继续调用终端，查看最新一次代码提交的标题，只回答标题。 | 预取的标题 |
| 4 | 继续调用终端，查看最新一次代码提交的日期，只回答年月日。 | 预取的日期 |
| 5 | 继续调用终端，统计当前工作区未提交文件的数量，只回答数字。 | `0` |
| 6 | 继续调用终端，统计当前仓库本地分支的数量，只回答数字。 | 预取的数量 |
| 7 | 继续调用终端，统计当前分支包含的代码提交数量，只回答数字。 | 预取的数量 |
| 8 | 继续调用终端，查看当前分支正在跟踪的远程分支，只回答名称。 | `agtai/hx/0731_live_voice_ux` |
| 9 | 继续调用终端，查看当前代码仓库根目录的名称，只回答名称。 | `jiuwenswarm` |
| 10 | 继续调用终端，查看电脑当前时间，只回答小时和分钟。 | 与系统时间相差不超过 1 分钟 |

选择中文“当前分支/最新提交”等说法，是为了避免已知的英文技术词 ASR 误识别；Agent 结果仍然必须是真实工具结果，不得写死。

### 7.3 每轮和整组判据

每轮都必须满足：

- final transcript 与口令语义一致；
- 恰好新增一个用户 Turn、一次 `chat.send`，partial 请求和重复提交均为 0；
- 出现预期的真实只读工具调用，结果与预取值一致；
- 最终回答完整可听，无截断、双播或旧回答串入；
- 自动回到 `Listening`；
- 没有 Retry、刷新、文字修正或手工补发。

任一轮失败，整组“连续 10 Turn”判为 `FAIL`。继续完成剩余轮次可以收集诊断数据，但不能从失败后的下一轮重新计算连续成功。

## 8. Gate 4：10 次分阶段打断

### 8.1 必须先区分两种真实行为

当前 V0 在 final transcript 提交时按实际 processing 状态路由：

| 场景 | final 时状态 | 当前真实路由 | 本项证明什么 |
|---|---|---|---|
| thinking 中开麦，用户说完时 Agent 仍在处理 | `processing=true` | `chat.interrupt(intent=supplement)` | 真实 processing supplement |
| tool 运行中开麦，用户说完时 Agent 仍在处理 | `processing=true` | `chat.interrupt(intent=supplement)` | 真实 processing supplement 和旧工具风险 |
| thinking/tool 时开麦，但用户说完前 Agent 已结束 | `processing=false` | 普通 `chat.send` | 只能重分类，不能计入 supplement |
| 回答已完成、只剩本地 TTS 在朗读 | `processing=false` | 立即停播；新 final 走普通 `chat.send` | 用户可感知的朗读中止和下一轮 |

因此，V0 的“10 次打断”固定为 **3 次 thinking + 4 次 tool + 3 次 speaking**：前 7 次必须是真实 supplement，后 3 次必须是本地停声后的普通新 Turn。最终报告必须分别写 `true_supplement_pass_count` 和 `speaking_playback_stop_pass_count`，不能笼统写成“10 次 supplement”。

### 8.2 I01–I03：thinking 阶段

每次使用一个独立 Session。原口令：

> 调用终端查看最近三十次代码提交，按月份统计数量并逐月说明。

一看到 `Agent is working` 且尚未出现 Terminal Tool 卡片，立即点击“打断并说话”，说：

> 停止并放弃刚才的检查，改为查看当前分支，只回答分支名。

通过条件：新 final 到达时仍是 `processing=true`；实际发送 `chat.interrupt(intent=supplement)`；收到对应的 `chat.interrupt_result`；替代回答只回答当前分支；旧 final 和旧 TTS 不出现。

### 8.3 I04–I07：tool 阶段

为了稳定制造可观察的只读慢工具，原口令：

> 调用终端执行一个只读测试：先等待八秒，再查看最新提交编号的前八位，只回答编号。

确认 Terminal Tool 正在执行且页面仍为 `Agent is working` 后，点击“打断并说话”，说：

> 停止并放弃刚才的检查，改为查看当前分支，只回答分支名。

只有实际工具调用确实包含等待且新 final 到达时仍为 `processing=true`，本次才可计数。通过条件：

- 实际发送 `chat.interrupt(intent=supplement)` 并收到对应 ACK；
- 替代请求只调用只读工具并回答当前分支；
- 记录旧 `chat.tool_result` 是 cancelled、success、error 还是没有到达；
- 记录 Gateway cancel warning、迟到 tool result 和真实副作用；
- 旧 final、旧 TTS 和旧 tool call/update 不得成为当前替代回答；迟到 `chat.tool_result` 可以保留在明确的旧工具记录中，但必须记录且不能触发当前回答或 TTS；
- 旧工具即使已经完成，也不能成为当前最终回答。

V0 打断验收只能使用读取、等待和统计等无副作用工具。出现写文件、删除、安装、推送、发消息或外部网络动作时立即终止并记为安全失败。

Gateway cancel warning 必须进入证据。warning 本身不能证明旧工作已经停止，也不自动证明用户可感知路径失败：只有在完整时间线能证明替代回答正确、旧输出未进入当前 UI/TTS、旧工具只读且没有额外副作用时，V0 样本才可通过并保留该已知限制；无法证明隔离时记为 `INCONCLUSIVE`，出现污染或副作用时记为 `FAIL`。生产版仍必须由 generation fence 解决。

### 8.4 I08–I10：speaking 阶段

原口令：

> 调用终端查看最近五次代码提交，然后逐条用一句话说明。

等状态为 `Speaking` 且耳机已听到第一句后，点击“打断并说话”，说：

> 停止朗读，改为调用终端查看最新提交日期，只回答年月日。

通过条件：

- 点击后旧声音在目标 `<300ms` 内停止，且永不恢复；
- 新要求只生成一个用户 Turn；
- 实际路由是一次普通 `chat.send`，不得伪报成 supplement；
- 新请求真实调用只读工具并只朗读最新提交日期；
- 完成后自动回到 `Listening`。

### 8.5 整组通过条件

- 10 次用户可感知打断均通过，旧声音恢复总数为 0；
- thinking 3/3 和 tool 4/4 均有真实 supplement 路由证据；
- speaking 3/3 均有本地静音和普通 `chat.send` 路由证据；
- partial 请求、重复新要求、旧 final 串入和非只读副作用均为 0；
- 任何 final 时已经不 processing 的 thinking/tool 样本必须重分类并另开 attempt，不能填充 7 次 supplement；
- 缺少 WebSocket/日志路由证据的样本为 `INCONCLUSIVE`，不能通过。

## 9. Gate 5：稳定性、失败降级和退出

### 9.1 Soak

按已经接受的 V0 标准，在执行前固定选择“连续至少 20 分钟”或“连续至少 20 Turn”，中途不能改口径。更强的最终彩排建议同时满足两者。

全程同一个 Session，不刷新、不重启服务、不切模型、设备或网络。通过条件：

- 重复提交、旧 TTS 恢复、双播、错误卡死和页面刷新均为 0；
- 每个成功 Turn 都完整朗读并自动回到 `Listening`；
- 浏览器响应没有持续恶化；
- 失败必须保留原时间线，不能通过延长时间或成功录屏掩盖。

### 9.2 失败与文字降级

至少验证：

- 初始静默直到可见 `no-speech`；
- 麦克风权限拒绝或可控的识别失败；
- 错误原因可见，可执行一次可解释的 Retry；
- 失败后退出 Live Voice，文字聊天仍正常；
- 退出后麦克风和所有声音均停止。

### 9.3 主展示脚本连续 3 次

严格执行 [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md) 的三轮主演示。使用同一个 candidate SHA 和固定环境，完整脚本连续成功 3 次。任一完整 run 失败，连续计数清零；保存失败证据并从新的完整 Run 1 开始，不能只补跑失败的一轮。

## 10. Gate 6：新机器与新 Codex 会话恢复

这个 Gate 验证“Git 能恢复代码、范围、状态和下一步”，不假装 Git 能携带密钥、浏览器权限、硬件选择或网络状态。

### 10.1 冷 clone

在新的目录或另一台机器执行：

```powershell
git clone --origin agtai https://github.com/agtai/jiuwenswarm.git
Set-Location jiuwenswarm
git switch --track agtai/hx/0731_live_voice_ux
git rev-parse HEAD
git rev-list --left-right --count HEAD...agtai/hx/0731_live_voice_ux
git status --porcelain
uv sync --python 3.12.9 --frozen
Set-Location jiuwenswarm\channels\web\frontend
npm ci
Set-Location ..\..\..\..

$expectedV0Sha = '2c700934aa0024a7ab229644bf15934e9e8170e7'
$v0AcceptanceDir = Join-Path (Split-Path -Parent (Get-Location)) 'live-voice-v0-acceptance'
git worktree add --detach $v0AcceptanceDir $expectedV0Sha
git -C $v0AcceptanceDir rev-parse HEAD
git -C $v0AcceptanceDir status --porcelain
git merge-base --is-ancestor $expectedV0Sha agtai/hx/0731_live_voice_ux
$LASTEXITCODE
```

预期：累计开发分支与远端差异 `0 0`、工作区为空，可以仅依赖 Git 和 lockfile 恢复最新代码与项目事实；独立 V0 目录的 `HEAD` 精确等于 `2c700934...`、工作区为空，并且该 SHA 仍是累计远端的祖先。累计分支的 Foundation 自动化在累计分支目录执行；本文 Gate 1 以及后续 V0 服务和真机验收只在 detached V0 目录按其 lockfile 独立重建依赖后执行，不能复制累计目录的 `.venv` 或 `node_modules`。

### 10.2 无旧对话的 Codex 理解测试

打开全新的 Codex session，只提供刚 pull 的仓库，不提供旧聊天，发送：

```text
请先读取根 AGENTS.md，并按其中顺序阅读 docs/zh/live-voice/README.md、HANDOFF.md、STATUS.md、TWO_WEEK_DEMO.md、POST_V0_DELIVERY_ROADMAP.md、POST_V0_STASH_HANDOFF.md、V0_ACCEPTANCE.md、DECISIONS.md。在不启动服务和不修改文件的情况下，说明：当前累计分支与不可变 V0 Candidate 的关系；已经真实证明和只通过自动化的内容；V0 放行条件；三类打断的真实路由；下一项开发任务；禁止提前做的内容；哪些机器私有条件无法从 Git 恢复。
```

正确回答至少必须包含：

- 共享累计分支同时保存不可变的 `2c700934` V0 Candidate 和后续已提交、已推送的 Post-V0 Task Foundation；V0 仍不是 Released；
- 真实主链只在固定环境贯通一次；47/47 和 22/22 是 V0 Candidate 的历史自动化，最新 Foundation 的自动化必须与 `STATUS.md` / `HANDOFF.md` 分开报告；
- 尚缺连续 10 Turn、分阶段 10 次打断、soak 和主演示连续 3 次；
- processing 中 final 才走 supplement；只剩 TTS 时先停声再走普通 `chat.send`；
- Web Speech 技术词误识别，以及 supplement ACK 不等于旧 Agent/工具已确定停止；
- 当前 V0 验收工作只在 detached `2c700934` 目录继续执行，不在该目录开发新功能；累计开发分支的下一窄切片是 D-031 poll-backed 非阻塞任务监控，不扩成 Team、真全双工、完整 TaskEvent/P3 或生产架构；
- key、完整 API base、浏览器权限、默认设备和网络状态不能从 Git 恢复。

### 10.3 私有配置边界

新机器的真实 E2E 仍需要从受控渠道注入可用的默认模型配置，并在浏览器中授予麦克风权限。缺少 API base、API key、model name 或 provider/client 任一字段时，停止外部模型和真机验收；不要打印字段值，也绝不能通过提交密钥解决。

只有“新 Codex 正确复述状态 + 冷依赖构建通过 + 私有配置注入后真实链路通过”，才能写成跨机器、无旧聊天恢复完成。

## 11. 证据记录模板

建议每次正式验收新建 `docs/zh/live-voice/evidence/V0_<日期>_<candidate短SHA>.md`，只提交脱敏文本摘要；原始录屏和日志留在受控位置。

```text
【运行信息】
日期/时间：
验收者：
Run ID / Attempt：
Gate / Case ID：
Git branch / candidate SHA / upstream diff / dirty：
Windows / Chrome / Node / Python：
语言 / 麦克风 / 耳机 / 网络标签：
模型标签（无 key/base）：
Session ID（可脱敏）：

【口述与识别】
计划口令：
实际 final transcript：
interim 是否触发请求：
用户消息新增数量 / final 数量 / 是否重复：

【状态与路由】
目标阶段 / 实际阶段：
开麦时 processing / final 时 processing：
实际路由：chat.send / chat.interrupt(supplement)：
interrupt_result / cancel warning：

【工具】
预期只读目的 / 实际工具与参数摘要：
预期结果 / 实际结果：
迟到 tool_result / 可观察副作用：

【声音】
TTS 开始 / 停止：
本地停声延迟：
旧声音恢复 / 双播 / 截断：
是否自动回 Listening：

【结论与证据】
PASS / FAIL / NOT RUN / INCONCLUSIVE：
首个异常和完整时间线：
脱敏截图、日志、录屏时间点：
```

汇总必须单独列出：

```text
normal_turn_pass_count: __ / 10
true_supplement_pass_count: __ / 7
speaking_playback_stop_pass_count: __ / 3
old_audio_recovery_count: __
partial_side_effect_count: __
duplicate_submit_count: __
soak: PASS / FAIL / NOT RUN
showcase_consecutive_runs: __ / 3
cold_environment_recovery: PASS / FAIL / NOT RUN
```

## 12. 最终放行规则

只有 Gate 0–6 全部为 `PASS`，才能：

1. 在 [STATUS.md](STATUS.md) 和 [HANDOFF.md](HANDOFF.md) 将状态改为 `V0 Released / 已冻结`；
2. 记录准确 candidate SHA 和脱敏证据文件；
3. 可选创建明确的 V0 tag；
4. 开始 V1/P1 工程化。

如果任一 Gate 未通过，当前版本仍是 `V0 Candidate`。这不否定主链已经走通，只表示稳定性、打断或跨环境证据还不足以放行。
