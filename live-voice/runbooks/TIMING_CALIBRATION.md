# 首音计时与录音校准 / First-audio timing and acoustic calibration

该流程读取普通 Live Voice 的被动诊断及用户明确提供的录音。
诊断本身不改变播放、打断、任务、模型、VAD 或权限；常规日志不保存音频或文字内容。

## 三种读数 / Three different endpoints

| 名称 / Name | 起点 → 终点 | 含义与限制 |
| --- | --- | --- |
| 软件轮次交接 / Software turn handoff | 浏览器接收 EOT → 播放时钟轮询观察到首个 PCM 开始 | 同一浏览器时钟内实测；不是人最后音素 → 耳机首音，也不是完整回答时长 |
| 信号到设备估计 / Processed signal to device estimate | 浏览器处理后输入能量尾部 → 输出首个信号的设备时间戳估计 | 输入 10 ms 窗、−45/−55 dBFS；输出 5 ms 窗、−50 dBFS。能量不等于语音，阈值不等于听觉阈值。包含输入处理/噪声和时钟映射误差 |
| 录音实测 / Shared-recording acoustic interval | 同一录音中用户最后音素 → 耳机回答起声 | 样本差 ÷ 采样率；标注须结合波形和试听。记录标注不确定度及传播/通道时差，不能以 EOT、文件结束或 UI 代替 |

软件估计使用 `getOutputTimestamp()` 映射 AudioContext 与 performance 时钟。
`baseLatency`、`outputLatency` 单独报告，不再叠加到该映射，避免重复计算。
它是输出设备时间估计，不证明耳机单元已经发声，也不代表听者实际感知。
不支持、过期、未启动的时钟保持缺失。

输入估计只在当前 capture 有新鲜记录、两个能量阈值的尾部接近且顺序合理时展示。
报告中的 250 ms 新鲜度、5 s 尾部年龄和 100 ms 阈值分歧上限只是诊断筛选，**不是精度保证**，
更不会参与 VAD/轮次决策。噪声、其他人说话、回声或较弱末音素仍可能造成偏差。
停止发生在估计输出之前时，不报告该信号已经输出。

## A–H 与模块覆盖 / Stages and coverage

| 区段 / Stage | 可观测内容 / Available observations | 仍不可直接测得 / Unavailable |
| --- | --- | --- |
| A→B 麦克风→浏览器 / Capture | 处理后帧采样位置、AudioContext 时间、回调时间、输入能量尾部 | 嘴边最后音素、麦克风硬件和 AEC/NS/AGC 各自时延 |
| B→C 浏览器→Gateway / Uplink | 帧序号、队列、Socket 写入、ACK、拥塞、周期性 capture 时钟样本 | 未同步时钟的单向网络时延；不会用两台机器墙钟相减 |
| C→D Gateway→Realtime 轮次结束 / Endpointing | Provider 输入采样范围、EOT、commit、发送锁与 Socket 阶段 | Provider 内部接收/编码/VAD/排队分账；尾部静音不能冒充全部 VAD 耗时 |
| D→E 回答请求与生成 / Response | EOT→请求发送，请求发送→created，created→首 PCM；参数流首段→完整参数 | 纯模型计算时间与网络/Provider 排队的精确分离 |
| E→F 准入与下行 / Admission and downlink | 首音→准入完成、准入→首帧发送、发送循环、连接/绑定、锁等待 | 没有独立时间戳的内部子步骤不补零 |
| F→G 下行与浏览器 / Browser receive | Socket 消息回调→PCM 接受、接受→排程、排程→渲染轮询、轮询晚观察量、前导静音与设备输出估计 | 未同步时钟的 Gateway→浏览器单向网络；排程不证明输出 |
| G→H 设备与耳机 / Physical output | 浏览器设备估计；独立录音中的耳机声学起点 | 软件不能分别测出 OS、USB、DAC、耳机单元和人的感知时延 |

后台任务不使用一个“首音”替代全部操作：工具前口头反馈、参数完成、业务受理、回执、
后台执行、完成通知准备/等待/播放分别看。`response_kind` 区分 direct、continuation 和
work_notification；关联完整响应 ID、generation、activation、turn、call、Task/attempt。

| 业务模块 / Business module | 记录与解释 |
| --- | --- |
| Context / 上下文 | 鉴权、任务读取、历史读取、投影恢复；当前/已发布/响应冻结快照 ID；拒绝时保留原请求目标和快照，不用事后刷新的快照冒充原始绑定 |
| Agent / 智能体 | acquisition、stream 总跨度；模型各轮首 chunk/总时长/间隔、工具调用；嵌套和并行跨度不得求和 |
| Task / 后台任务 | 接收、工作树准备、执行、文件/产物、清理、终态；准备失败不等于 Agent 执行失败；未进入的阶段标为未触发 |
| Notification / 通知 | 原任务/事件、准备、前台/前序播放等待、续答、ACK/回退；ACK 是协议事实，不能证明耳机听见 |
| Interrupt / 中断恢复 | 本地停止、远端确认、后继响应；续答拒绝仅记录类型/phase/part 形状；断连记录 close code/已知原因类别/errno，不记录任意错误内容 |

每个耗时都绑定起止记录序号和一个时钟域。跨进程墙钟仅供近似排序。
旧导出可以读取，但缺少精确请求 ID、输入范围或轮次种类时，不按“最近时间”猜配。
逐响应表只呈现具有浏览器响应观测的条目；未产生音频的请求仍在调用时间线和错误表中。

## 一次真人校准 / One recording session

1. 使用完成部署后的页面，先退出 Live Voice，再刷新页面，保持现有有线/USB 耳机、
   输入麦克风和音量。选择安静环境，用独立录音设备同时清楚录到嘴边说话与耳机单元声音。
   一个麦克风或共享同一录音时钟的两个通道均可；不要用两台未同步设备各录一端。
   放置录音设备时尽量不改变 Live Voice 麦克风接收到的耳机回声。
2. 录制一段连续音频，优先原始 PCM WAV。先说“校准第一轮，请用一句话介绍杭州”，
   待回答结束；再说“校准第二轮，深圳靠海吗”；最后说“校准第三轮，用一句话介绍西湖”。
   自然说话，不用刻意拉长尾音；校准普通交接的轮次先不打断。
3. 停止录音，导出同一页面诊断，保留会话 URL。提供本地录音与诊断路径，以及录音麦克风
   到嘴和耳机单元的大致距离；使用不同通道时注明是否有已知通道延迟。
   不需要用户手动算毫秒或填写下面的工程标注。
4. 分析者逐轮试听并检查波形，标出最后音素边界与回答的首个音（不把噪声尖峰当成音素），
   记录样本索引、通道、标注不确定度和精确 response 身份。弱尾音、重叠、削波或录音不清时
   给出范围/不可用，不能强行给“准确到毫秒”的结论。

录音中两端传播差为 `耳机→录音麦克风` 减 `嘴→录音麦克风`；通道时差也计入此差值。
未校正前只叫 **录音拾音点间隔**。`duration_ms` 只在声学录音且明确给出差值及不确定度时
报告校正后的嘴→耳机值；数字 loopback 不升级为声学测量。
采样率是名义值，未独立校准录音设备的时钟精度；标注和传播误差应与结果一起报告。

该总间隔包含用户结束后剩余的输入处理与上传、轮次判断、回答生成及传输、准入/下行、
浏览器缓冲/渲染和设备出声。**用户说话期间已完成的流式工作不会再相加。**
仅凭一次录音不能把这个物理总间隔精确分摊到每个内部模块。

## 离线入口 / Offline report

按 [普通诊断入口](E2E_RUNBOOK.md#77-普通-demo-的性能记录与故障报告) 生成报告。
可选 `--recording-annotations annotations.json` 把已核对的录音结果附到同一响应：

```json
{
  "format": "live-voice.recording-annotations.v1",
  "recording_path": "calibration.wav",
  "sha256": "REPLACE_WITH_RECORDING_SHA256",
  "sample_rate_hz": 48000,
  "recording_kind": "acoustic",
  "annotations": [{
    "session_id": "REPLACE", "interaction_id": "REPLACE",
    "response_id": "REPLACE", "response_generation": 1,
    "user_end_sample": null, "headphone_start_sample": null,
    "user_channel": 0, "headphone_channel": 0,
    "annotation_method": "manual_waveform_and_listening",
    "annotation_uncertainty_ms": null,
    "differential_delay_ms": null,
    "differential_delay_uncertainty_ms": null
  }]
}
```

路径相对于标注文件；哈希、WAV 头、采样范围、通道、身份、重复标注及不确定度全部校验。
示例不是可通过校验的测量结果。录音及标注保存在本机忽略目录，不提交原始声音。
