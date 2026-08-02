# Live Voice 成功率优先展示脚本

本文负责现场展示话术和失败退场，不替代 V0 放行验收。完整 Gate、固定语料和证据模板见 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md)。

- 当前 V0 放行执行目标：detached `2c700934aa0024a7ab229644bf15934e9e8170e7`；累计分支只用于继续开发
- 展示目标：用 60–90 秒证明“真实语音能够连续驱动真实 Agent 和 Terminal Tool，读取演示机的确切代码快照，并把真实结果完整读回来”
- 展示口径：纵向 Demo，不宣称生产级全双工或稳定性放行
- 环境与启动细节：[E2E_RUNBOOK.md](E2E_RUNBOOK.md)

## 1. 当前 Demo 到底能做什么

### 固定真机已经明确证明

```text
真实麦克风
→ 浏览器显示临时字幕
→ 只提交最终识别结果
→ 现有 JiuwenSwarm Agent
→ 真实 Terminal Tool
→ 当前仓库的真实结果
→ 完整 TTS
→ 自动回到 Listening
```

这不是固定答案：2026-08-01 的真实 E2E 中，Agent 执行了 `git branch --show-current`，得到 `hx/0731_live_voice_ux`；用户确认斜杠、数字和下划线均完整听到。

这次真机运行明确证明了：

- 真实麦克风产生完整 final，并且只提交一个逻辑 Turn；
- `new` session promotion 后 Live Voice 没有错误退出；
- final 进入现有 Agent，Agent 真实调用 Terminal Tool 并读取当前分支；
- 页面保留原始分支名，TTS 完整读出技术标识符；
- 朗读结束后自动回到 Listening，后续循环可以继续；
- 约 8 秒的初始静默窗口没有被 Chrome 更早的自然结束提前截断。

后续两次自动回听证明“同一 Session 的循环还能继续”，但其中 `git` 被识别成“地图”或“史记”，因此准确多轮和上下文继承尚未通过真机 Gate，正是本展示脚本需要继续验证的内容。

### 已实现并通过自动化，但仍需真机专项验收

当前代码还具备：

- 在 Agent 模式进入和退出 Live Voice，并显示 Listening/正在听你说话、Agent is working/Agent 正在工作、Reading the response/正在朗读回答和 Voice is unavailable/语音功能出现问题等状态。
- interim 更新期间不提交请求；逻辑 capture 结束时，当前可见尾段可能被提升为 final，因此用户说半句后长时间停住仍可能形成一个真实 Turn。
- final 复用现有 `chat.send`，由真实 Agent 决定并执行工具，不走演示专用假链路。
- 新建会话从 `new` promotion 到真实 Session 时继续保持 Live Voice。
- Chrome 提前结束单个识别实例时，可在同一逻辑讲话中续启并合并尾段；初始等待约 8 秒，有结果后约 2.2 秒停顿提交。生命周期纯逻辑测试已通过，但不同真实讲话和尾段的稳定性仍需更多真机样本。
- 完整朗读 Agent 回答，并按约 220–300 字分片；普通 TTS 的 500 字上限不会截断 Live Voice 回答。
- 页面保留原文，但朗读副本会把路径、分支、斜杠、下划线、缩写和数字转换成可听形式。
- 回答读完后自动重新 Listening，可继续同一个 Session 的下一轮语音协作；准确多轮上下文尚未正式放行。
- 进入、退出或新 Turn 会停止旧语音并使迟到 TTS 回调失效；Live Voice 激活时也会阻止其他已知 TTS 路径双播。
- 权限、识别或播放失败时显示错误，可 Retry 或退出回文字聊天。

打断/补充的代码路径已经存在：重新开麦会先停止本地朗读；如果 Agent 仍在 processing，新 final 走现有 `supplement`，如果 Agent 已完成、只剩 TTS 在播放，新 final 走普通 `chat.send`。真实 Agent cancel/replacement 尚未完成 10 次端到端验收，因此不放入成功率优先的主演示路径。

## 2. 当前还不能做什么

以下内容不能在台上描述成“已经完成”或“已经稳定”：

- 尚未通过连续 10 个准确语音 Turn、分阶段 10 次用户可感知打断、20 分钟或 20 Turn soak、主演示脚本连续成功 3 次。
- Web Speech 对中文句子中的英文技术词不稳定，真实出现过把 `git` 识别成“地图”或“史记”。
- 不是生产级持续双向音频。当前主要是“听一轮 → Agent 工作 → 读一轮 → 再听”，不是边听、边生成、边说的全双工媒体流。
- 不是自然免手插话。主链依靠重新开麦或点击进行确定性控制，没有正式 AEC、误打断恢复和扬声器回声基线。
- 不是服务端流式 STT/TTS。浏览器负责语音输入输出，Agent 中间仍走现有文字 WebSocket；完整回答形成后才开始分片朗读。
- 用户是否说完由固定静默窗口判断，不是声音、语义和上下文联合判断。
- 识别 final 会在固定静默后自动提交，当前没有“先确认/编辑识别文字再提交”的正式步骤；技术词误识别会直接影响 Agent 请求。
- 前端能停止旧声音并隔离多类旧 UI 输出，但服务端 supplement ACK 早于 cancel/replacement 完成；已经发生的工具副作用没有生产级 generation fence。
- Desktop/WebView2、Team、多语言、移动端、设备切换、热插拔、断线恢复和跨重启恢复尚未验证。
- V0 主展示不包含后台任务。Post-V0 已有一个默认关闭、单 Session 内存态的受限 AutoHarness 路径，但尚未做真实副作用 E2E；在 [E2E_RUNBOOK.md](E2E_RUNBOOK.md) 的独立受控验收通过前，不要展示，更不能称为通用语音 Task Control。

## 3. Demo 与最终版的区别

| 方面 | 当前 Demo | 最终版 |
|---|---|---|
| 核心价值 | 证明语音能真实驱动 Agent/Tool 并把结果读回来 | 成为可长期使用的实时语音工作入口 |
| 交互节奏 | 一轮听完再提交，回答完成后朗读，随后自动回听 | 上下行媒体持续并发；Agent 生成或播放期间仍能接收新输入，并停止或修订正确回答。首版采用 Cascade Engine，不要求同一个模型原生同时听和说，Native 模型是可替换路线 |
| 语音底层 | 固定 Windows + Chrome + `zh-CN` + 默认设备 | Windows Desktop/WebView2 产品化，可替换 Speech Provider，多设备、多语言 |
| 判断说完 | 固定 8 秒初始窗口和 2.2 秒尾部停顿 | VAD、语义和上下文联合 EOT，并能恢复误判断 |
| 提交前确认 | final 在固定静默后自动提交，partial 不产生副作用 | final 可确认、编辑或取消后再提交，继续保证 partial 永不触发 Agent/Task |
| 回答朗读 | 浏览器 TTS，完整文本按句分片 | 服务端流式 TTS、音频分片、背压、播放确认和正式发音词典 |
| 打断与历史 | 本地先静音，前端 epoch/owner/quarantine 防止主要路径串音 | 客户端与服务端共享 response ID、cancel ACK、generation fence 和 presented history；明确区分“只停声音、取消回答、取消当前工作、取消后台任务”，插话不误取消无关工作 |
| Agent 工作 | 单 Agent Session，复用当前 Chat/Tool 链 | 非阻塞 Agent Bridge、结构化工作进度、慢工具与前台语音互不冻结 |
| 后台任务 | V0 主 Demo 不包含；Post-V0 可选切片固定 side-effecting AutoHarness、确认口令、真实 task card/target、稳定 command ID、同-key retry、strict exact-key reconciliation 和单用户 request owner+project 一致性 scope（非生产鉴权）；投影仍只在当前页面/Session，尚无持续 monitor | P3α 先提供幂等 create、稳定 `task_id`、get/list/status/cancel/events、每任务不可变上下文和 D0：语音/Session 断开后，只要应用与 Executor 仍存活，任务继续；进程重启后只协调并报告真实状态，不承诺续跑。完整 P3 再增加补充输入、修改、调优先级、暂停/恢复，以及按 Executor 能力提供 checkpoint 恢复或副作用协调；歧义和破坏性操作需要澄清/确认 |
| 故障处理 | 可见错误、Retry、退出回文字聊天 | 自动重连、状态恢复、重复抑制、故障注入和量化服务指标 |

当前 Demo 像一条已经真实跑通的单车道；最终版是在相同方向上增加多车道、护栏、监控、备用路线和全天候运行能力。Demo 验证“值得做、走得通、效果是否成立”，最终版解决“能否安全、稳定、普遍地使用”。

## 4. 主展示用例为什么这样设计

主演示只做三轮短对话：

1. 强制终端查询当前提交的短编号；
2. 强制终端统计工作区未提交文件数量；
3. 根据前两轮结果做一句话总结。

它最大化成功率，同时能证明：

- 输入来自真实麦克风；
- final 只提交一次；
- Agent 真实调用了两次 Terminal Tool；
- 提交编号和工作区状态来自真实 Terminal Tool，不是前端固定答案；
- 技术标识符能够完整朗读；
- TTS 后自动回听；
- 第三轮保留前两轮上下文。

口令故意不说英文单词 `git`，规避已经观察到的技术词误识别；工具仍会真实执行 Git 命令。回答被限制为一行或一句，减少模型延迟、长 TTS 和现场插话的变量。所有操作都是只读的，不会改变仓库。

## 5. 上台前固定环境

推荐固定：

- 同一台 Windows 机器、同一 Chrome profile、同一稳定网络；
- Chrome `150.0.7871.187` 或已经完成同等验收的固定版本；
- Jabra EVOLVE 30 II 或已经完成同等验收的有线耳机和麦克风；
- `zh-CN`、Agent 模式、单一浏览器标签页；
- detached `2c700934aa0024a7ab229644bf15934e9e8170e7`，`git branch --show-current` 为空，工作区干净；
- 模型、项目注册、Gateway、AgentServer 和 Terminal Tool 已预热。

如果观众需要听到声音，首选“有线耳机 + 会议软件共享系统音频”，并提前在同一会议中验证。不要上台后临时切换输入/输出设备。线下扬声器只有在同一房间连续彩排通过后才使用，因为当前 Demo 没有生产级 AEC。

关闭系统通知音、即时通讯弹窗和其他会抢占麦克风的页面。Live Voice 激活后，Presenter 在 Listening 状态只能说脚本口令，不要同时向观众解说，否则解说也会被当作下一轮请求。

## 6. 展示前预检

### 30–60 分钟前

1. 按 [E2E_RUNBOOK.md](E2E_RUNBOOK.md) 启动服务并确认端口与 `connection.ack`。
2. 在 detached V0 仓库中复核不可变候选快照；累计分支的文档提交不会改变该验收 HEAD，但每次彩排/展示前仍必须重新确认 SHA 与 dirty 状态：

   ```powershell
   git branch --show-current
   git rev-parse --short=8 HEAD
   @(git status --porcelain).Count
   ```

   第一条输出必须为空，证明处于 detached V0 候选；短编号必须为 `2c700934`，未提交文件数量必须为 `0`。
3. 用文字先发送：

   > 必须调用终端查看当前提交编号前八位，并统计未提交文件数量，不要根据上下文猜测，只返回编号和数量。

4. 必须看到真实 `chat.tool_call`、`chat.tool_result`，而且结果与第 2 步一致；失败先修项目绑定或工具环境，不要进入语音演示。文字预检使用单独的测试会话，不要污染主演示上下文。
5. 提前创建主演示和备用两个 Agent Session。在主演示 Session 中只用文字执行一次 `git rev-parse --is-inside-work-tree` 完成初始化，不查询提交编号或工作区状态；之后不要再向该 Session 发送主演示前置答案。
6. 在同一麦克风、网络和音频路由下完整彩排主演示脚本。正式上台前应让完整三轮脚本连续成功 3 次，而不是只重跑失败的一轮；未做到时只能称为试演，不能称为已放行。
7. 保留一次同环境、同脚本、带系统音频、完整 Tool 卡和时间戳的真实录屏，作为外部网络或 Provider 故障时的备份。必须明确标记为“最近一次真实运行”，不能冒充现场成功。

### 1–2 分钟前

1. 选择一个提前创建、已经完成初始化但没有主演示答案的专用 Agent 会话；不要把 `new` session 冷启动放到台上。
2. 确认 Chrome 麦克风权限为允许，Windows 输入电平有变化。
3. 确认没有其他页面占用麦克风。
4. 先向观众解释展示目标，然后再启用 Live Voice；启用后不再插入旁白。

推荐开场白：

> 接下来三轮输入全部来自麦克风。前两轮会让 Agent 调用真实终端，第三轮验证连续上下文；结果由 Agent 现场读取，不是前端预置回答。

## 7. 60–90 秒主演示脚本

### Turn 1：读取真实候选提交

启用 Live Voice，看到 Listening 后，在 2 秒内清楚说：

> 调用终端查看当前提交编号的前八位，只回答编号。

成功判据：

- interim 字幕可见，final 后只出现一条用户消息；
- UI 进入 Agent is working/Agent 正在工作，而不是立即给出预设答案；
- 出现真实 Terminal Tool 调用，结果为 `2c700934`；
- 页面显示原始编号；
- TTS 完整读出八位技术标识符；
- 朗读结束后自动回到 Listening。

### Turn 2：读取真实工作区状态

看到 Listening 后，在 2 秒内说：

> 继续调用终端，统计当前工作区未提交文件的数量，只回答数字。

成功判据：

- 只新增一个用户 Turn；
- Agent 再次调用 Terminal Tool，而不是复用猜测；
- 命令读取 `git status --porcelain` 或使用等价只读方式；
- 结果为 `0`，与上台前记录一致并被完整朗读；
- 再次自动回到 Listening。

### Turn 3：连续上下文

看到 Listening 后，在 2 秒内说：

> 用一句话说出刚才的提交编号和未提交文件数量。

成功判据：

- Agent 正确引用前两轮的 `2c700934` 和 `0`；
- 回答只有一句并完整朗读；
- 没有重复提交、串入历史回答或双播。

Turn 3 朗读完成并出现 Listening 后，立即点击退出 Live Voice。确认麦克风关闭后再恢复向观众解说。此时可以展开前两轮 Tool 详情，让观众看到实际命令和结果。

推荐收尾：

> 刚才证明的不是语音听写，而是语音输入真实进入现有 Agent，Agent 调用真实工具，结果再通过语音返回，并且同一会话能继续下一轮。

## 8. 可选加分项

主演示已经成功后，可以追加一个低风险的“立即停止”展示：

1. 再次进入 Live Voice；
2. 说：“请用三句话说明刚才完成了什么。”；
3. TTS 开始后点击退出 Live Voice；
4. 声音应立即停止，麦克风关闭，文字聊天仍可用。

这只证明本地 stop/cleanup，不等于生产级语音插话。

另一个独立 Post-V0 加分项是受限 Task Demo，但只有真实 AutoHarness E2E 已按运行手册通过、目标环境可丢弃或已备份、且观众已经看到常驻副作用披露时才允许追加。推荐最短流程是：先核对面板显示的绝对项目 target、来源 Session/Channel 和 fixed pipeline；再说不带“确认”的启动口令证明零请求确认边界，然后确认启动并展示真实 task ID，随后查询真实状态；取消会阻止后续执行但不能撤销已有代码修改。后端已有每任务进程内 context、per-path single-process 幂等 ledger 和单用户 Demo 的 request owner+project 一致性 scope；该 scope 的身份仍来自 Web 请求，不是生产鉴权，不能作为抵御恶意客户端伪造的承诺；Live Voice client 已为一次 committed mutation 固定 command ID，run 结果不明时先以同 key retry 和 strict exact-key list reconciliation 恢复唯一且 identity/target 全匹配的真实记录，无法证明时才保持 `mutation-unknown`。当前仍没有跨刷新持久 command journal、持续 task monitor、跨进程一致性/exactly-once 或重启后的 Agent context 恢复。因此不要在主演示仓库或无法保留后端 Task JSON/日志证据的环境运行。当前没有能在整页刷新后恢复原 Web scope/command identity 的列表入口：演示中不要刷新；若意外刷新，立即把该样本标为 unsupported/`mutation-unknown`、停止后续任务 mutation并保留后端证据供受控核对，绝不能在新 Session/target 中换新 key 盲重试。

真正的 supplement 插话只在同一机器已经完成 10 次专项验收后展示。候选口令是：

> 停，只用一句话总结。

在该 Gate 通过前，不要把它放在主演示中；当前服务端 cancel/replacement 与工具副作用仍有已知协议风险。

## 9. 现场失败处理

| 现象 | 只做一次的现场动作 | 何时切备份 |
|---|---|---|
| `No speech detected` | 等 UI 进入错误态后点一次 Retry，确认 Listening，再重复同一句 | 第二次仍失败 |
| interim 字幕明显错误、尚未提交 | 立即退出 Live Voice 丢弃本轮，在同一专用会话重新启用并重复纯中文口令；不要改说英文 `git` | 同一句连续错两次 |
| 错误字幕已经提交，Agent 正在工作 | 不要假设退出会取消 Agent；让这个只读回合完成，在同一 Session 用更短口令纠正一次。若要干净重演，先退出再切到提前创建的备用 Session | 纠正或备用 Session 仍失败 |
| Agent 没有调用工具 | 用原口令重试一次；不要替 Agent 口述答案 | 第二次语音仍没有 Tool |
| Agent working 较慢 | 保持页面不动并等待，只用手势指向页面真实状态；不要现场旁白或连点 Retry/发送 | 超过预先彩排的最长时间或 Provider 报错 |
| 页面有结果但没有声音 | 退出 Live Voice，修正固定音频路由，重新进入后把这一整条语音请求再说一次；Retry 不会重播旧回答 | 第二次仍无声 |
| Turn 之间因迟疑进入 no-speech | 点一次 Retry，看到 Listening 后 2 秒内说下一句 | 连续发生两次 |
| 提交编号或未提交文件数量与预检不同 | 停止展示并核对项目绑定、实际 HEAD 与工作区；不得把真实结果说成错误 | 无法在台下恢复到固定代码快照 |

不要在现场反复刷新、快速切换麦克风、临时换模型、修改配置或执行写操作。两次相同失败后应切到已标记的真实录屏和文字 Tool 详情，诚实说明外部环境故障。

## 10. 主展示通过标准

本用例通过需要同时满足：

- 三轮语音都语义正确，且每轮只提交一个 final Turn；
- 前两轮都出现真实 Terminal Tool 调用和真实结果；
- 八位提交技术标识符完整可听；
- 至少两次 TTS 后自动回到 Listening；
- 第三轮正确继承上下文；
- 全程无旧声音恢复、双播或页面刷新；
- 退出后麦克风和声音停止，文字聊天仍可使用。

通过这一个展示用例，能够证明核心纵向体验成立；它不能替代连续 10 Turn、分阶段 10 次打断、soak 和连续 3 次脚本的完整 V0 放行闸门。

## 11. 展示后收尾

1. 确认已经退出 Live Voice，麦克风与 TTS 均停止。
2. 关闭演示标签页，按 [E2E_RUNBOOK.md](E2E_RUNBOOK.md) 第 12 节停止 Vite、WebChannel、Gateway 和 AgentServer。
3. 恢复为 E2E 临时关闭的外部 IM channel 或进程配置；不得把临时密钥、profile 或配置写入 Git。
4. 确认演示端口不再监听，并再次执行 `git status --short --branch`；演示只读脚本不应改变工作区。
5. 记录本次三轮是否通过、ASR 实际文本、Tool 结果、TTS 听感和任何重试；一次成功仍不替代完整放行数据。
