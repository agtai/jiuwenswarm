# 中断异常与查询持锁：根因确认和处理设计

## 本轮边界

用户要求先确定根因，再分析应如何处理。本轮完成源码追踪、隔离因果复现和
修复边界设计；未改生产代码、配置或运行服务，未触发真实 Agent、Tool、Task。
这不是修复完成或新版本验收。生产修复和部署仍待执行。

基线为 `224c6753c65ce0c7dc3b6768f15a443ff95bf060`，工作区起始干净，分支
`hx/0812_live_voice_w3`，相对 upstream 为 1 ahead / 0 behind。线上本地部署
仍是 `fff2fe15b7`。主要证据来自
[新浏览器验收记录](REALTIME_HUMAN_RECHECK_20260908.md)以及私有目录
`logs/root-cause-20260908/` 中的 `probe.py`、`probe-results.json`、`probe-run.txt`。
复现使用当前真实 Registry、Native Runtime Owner、Conversation Runtime；
权限/任务数据使用测试夹具，磁盘状态隔离到该目录。复现不代表物理播放验收。

## 根因一：中断只更新了一层响应状态

这不是单纯的错误码不匹配。停止工具回执响应时，两层状态发生分歧：

- Conversation Runtime 是输出权限的最终所有者；它已将该响应 fenced，禁止继续输出。
- NativeInteractionRuntimeOwner 维护 Provider 响应与音频序列的接收状态；
  它的 `_RuntimeResponse.cancelled` 仍为 false，响应还被视为可接收音频。

源码路径：

1. Registry 的 Native STOP 调用
   `NativeInteractionRuntimeOwner.interrupt_delegate_source`。
2. 该函数找到 delegate source 和已分配的 successor，清除 delegate hold，
   并调用 `ConversationRuntimeLoop.cancel_response_if_running`。
3. 但它没有同步更新 successor 的 Native 接收状态。
4. 迟到音频批次通过 Native 层的 current / cancelled / done 检查，继续调用
   `transition_response` 或 `produce_unit`，才被底层 fenced 检查拒绝。
5. 这个未分类的底层异常穿过 Registry，导致 Gateway 的音频 delivery task 失败；
   `_consume_native_task` 随后关闭整个媒体 Session。

正常的 `fence_response` / `barge_in` 路径会同步 Native 的 cancelled 状态。
问题集中在 delegate 中断路径没有遵守同一生命周期规则。

### 隔离复现结果

先正常创建 source、准备回执并分配 successor，然后分别在首帧前、首帧后停止。
停止后再向同一 successor 提交两个连续音频观察。没有修改被测生产函数。

| 停止入口 | 已接收帧数 | Runtime fenced | Native cancelled | 迟到音频结果 |
| --- | ---: | --- | --- | --- |
| interrupt_delegate_source | 0 | true | **false** | FENCED_RESPONSE_NONTERMINAL_TRANSITION |
| interrupt_delegate_source | 1 | true | **false** | **STALE_RESPONSE_OUTPUT** |
| fence_response（对照） | 0 | true | true | 正常返回“不接收”，无异常 |
| fence_response（对照） | 1 | true | true | 正常返回“不接收”，无异常 |

四个样本均没有新增音频或历史效果。错误路径的首帧后样本还错误地报告
`has_current_admitted_audio == true`，证明状态不一致也影响当前音频判断，
并非只影响日志文本。这个 helper 本身不授予播放权限。

复现和真实日志一致：R7 首帧 admission 等锁约 1.332 秒；Provider 在此期间
报告 speech_started；STOP 使 R7 被中断，随后队列里的批次抛出
STALE_RESPONSE_OUTPUT。媒体关闭后出现 session_closed / uplink consumer
failed，属于同一故障链的后果。是否是用户有意说话或环境声触发 speech_started，
现有诊断无法判定；无论哪种输入，已中断响应的迟到帧都不应关闭健康会话。

### 应如何处理

修复应在 Native Runtime Owner 的响应生命周期边界：

1. 由同一入口完成“撤销该响应的音频接收资格”和“撤销 Runtime 输出资格”，
   并使 delegate 中断、带播放游标的打断、无游标停止保持一致。
2. 精确限定 source / successor 集合；停止回执播报不得取消已接受的后台 Task，
   不得影响新一轮响应，也不得撤销已完整播放的历史。
3. 在 Native Owner 的串行边界内同步状态；迟到音频、done、ACK、通知唤醒
   都读取一致的停止事实，正常返回不可接收或按已有契约拒绝。
4. 保留对错误目标、非法序列和越权输入的严格拒绝。Gateway 只处理已证实的
   exact-response 中断竞态，不把未知异常转成成功。

不能只在 Gateway 增加 `except STALE_RESPONSE_OUTPUT: pass`：
首帧前会抛另一个错误；接收层的有效响应判断仍错误；宽泛忽略还会掩盖真正的
跨响应或协议问题。也不应通过关掉打断、延后 STOP 或增大缓冲来躲开竞态。

## 根因二：只读查询的整个生命周期占用了语音共享锁

`handle_p3_query` 在 `async with self._lock` 内等待完整的
`_handle_p3_query_locked`。该锁是 Registry 的 `product_composition` 总锁，
Native 音频 admission、STOP、播放 ACK 和通知相关状态访问也需要它。

查询内包含以下工作：

- 解析并验证路由、鉴权和当前 Session / Project Context；
- Task Core 查询及上下文重新校验；
- task.status 额外读取 production authority、retry admission、task fact、
  durability diagnostics，以及 adjust / cancel 等候选操作权限；
- 当 task event head 在多次读取之间前进时，最多进行三轮一致性读取；
- 格式投影、诊断发布和临时 composition lease 清理。

其中多次 `asyncio.to_thread` 涉及文件读取、SQLite、项目状态和 Git revision。
它们释放了事件循环，**没有释放调用者持有的 Registry 锁**。因此查询在等外部
读取时，音频帧即使已到 Gateway，也无法进入 Runtime。锁还承担了查询结束前
阻止 shutdown 清理的职责，使“资源生命周期”和“互斥访问”混在一起。

### 因果证据和证据边界

- 本轮真实查询 `handle_p3_query` 持锁最大 1.928 秒。
- 浏览器 R9/R10 的四次调度间隙，对应 exact response / frame 的 admission
  等锁分别为 1.282、1.266、0.943、0.336 秒。
- 隔离复现把已获授权的 task.status 读取停在一个可控制的等待点，再提交真实
  Registry Native audio proposal。查询未释放时，音频始终不完成；释放后，
  查询和音频均正常返回。控制等待约 159 ms，音频 admission 日志等锁约 161 ms。
- 这个复现证明了慢查询向媒体传播等待的因果关系。真实日志没有把每次查询的
  所有内部读取逐一计时，不能宣称该 1.928 秒全部来自 Git 或某个 SQLite 调用。
  以前的 Windows ProjectStore 文件锁测量也不能替代本次样本的直接归因。

锁延长了中断与迟到音频交错的窗口，但不是第一个 bug 的必要条件：
Native 两层状态不一致在没有慢查询时也能稳定复现。两处需要分别闭环。

### 应如何处理

先纠正查询与媒体的并发边界，再压缩重复读取。不能只删掉最外层锁。

**查询生命周期与短临界区分开。**

1. 在 Registry 短锁内检查 running 状态，登记查询的在途所有权，取得该请求
   必需的稳定引用；不在这里等待文件、数据库或 Git。
2. 锁外完成鉴权、查询和投影；权限校验仍由现有 P3 所有者执行，依然绑定
   exact Session / Project / Task / attempt / event head。
3. 只有访问共享路由、发布诊断、登记清理等需要互斥的步骤，才短暂重新进入锁。
   原始 Task 状态与可操作性投影不一致时保留现有有限重读与失败关闭规则。
4. shutdown 先禁止新查询，再等待已登记查询及其工作线程真正结束，最后清理
   所依赖的资源。客户端取消不能让还在运行的线程失去所有权，也不能把一条
   查询的取消传播到媒体会话。

这保留了现有 `test_stop_waits_for_inflight_query_before_closing_registry` 的
资源安全意图，同时不再依靠长时间独占总锁实现它。P3 composition 已有
`_enter_operation` / `_leave_operation` / `_run_blocking` 的生命周期设计可借鉴；
需核对 Registry 查询专有资源，不能假设下层计数自动覆盖整条上层查询。

**减少请求内部重复读取。**

在完成锁边界修复后，对同一状态请求中的完整读取链做阶段测量。把展示状态和
可操作性判断使用的 Task / attempt / event-head 事实收敛为一致快照，并复用
同一请求内已经验证的输入；实际创建、调整、取消执行前仍独立重新鉴权和验证。
若需要新增跨模块快照契约，再单独记录该接口和风险边界，不静默扩大本次修改。

不采用跨请求 TTL 缓存权限来换时延；不削弱 event-head / scope 检查；不靠
减少页面轮询或把音频缓冲调大来掩盖媒体仍被业务查询阻塞的问题。轮询合并可
在核心边界修正后按实测需要处理，不是本次根因修复的前提。

## 实施和验收边界

建议作为两个可审查的并发修复提交：

| 模块 | 主要源代码与测试所有者 | 风险及必须保持的行为 |
| --- | --- | --- |
| 中断状态统一 | Native Runtime Owner、必要的 Registry/Gateway 串行交界；Native Runtime / Registry / dedicated media 测试 | Tier 2，触及现有 fence 身份边界的集成按 Tier 3 检验；旧音频零副作用，后台 Task 和新响应不受影响 |
| 查询生命周期与锁范围 | ProductCompositionRegistry、现有 P3 查询/鉴权接缝及对应测试 | Tier 2 并发/停机，权限投影接缝按 Tier 3 检验；未授权零效果、投影一致、线程和清理所有权不丢失 |

必须验证的正反场景：

- successor 首帧前、首帧后、批次已排队、provider done 前后停止；重复停止、
  延迟 done / ACK 和新一轮输入交错。旧音频不继续输出，不产生假播放历史，
  下一轮仍可接收并播放；已接受 Task 不被撤销或重复创建。
- 错误 response / generation / scope、改变内容的重复帧等仍严格拒绝，不能因
  “容忍迟到音频”变成成功；完整播放的历史也不能被追溯撤销。
- 控制住慢查询的读取，让 Native 音频、STOP、ACK 和合格通知在查询释放之前
  就完成各自处理。以事件顺序作主要 oracle，避免依靠脆弱的毫秒断言。
- 查询过程中 Task 更新、权限变化、路由关闭、客户端取消和服务 stop；
  查询不发布越权/混合快照，stop 等待真实线程结束，媒体不承担查询等待。
- 根据真实查询阶段测量决定后续消除哪些重复读取；总延迟与 Registry 等锁
  分开报告，不把“音频不再被锁住”误报成“查询本身已足够快”。
- 完成受影响模块检查、冷读完整 diff 和独立边界审查后，才做受控部署和真实
  浏览器回归；至少覆盖后台任务运行时普通聊天、查询、打断回执、完成通知。
  自动化通过不能替代听感与首音/停顿复测。

本轮未引入新协议、缓存策略或模块所有者；也不处理英文回执、上下文辅助文件
缺失、天气真实性、Task 意图语义等相邻问题。文档验证为本地链接解析和
`git diff --check`，隔离复现输出另行保留。修复实施尚未开始。
