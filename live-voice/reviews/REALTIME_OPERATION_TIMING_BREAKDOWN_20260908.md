# 逐操作耗时分解 / Per-operation timing breakdown

2026-09-08，历史验收的补充分析 / Supplemental analysis of the recorded acceptance run.

本报告展开 [原验收记录](REALTIME_HUMAN_RECHECK_20260908.md)，不启动新的模型、工具或任务，不修改产品代码或部署。会话为 `web_1a080c762a5_7ff4e1f0095d`，使用匹配的 `11-36-01-252Z` 浏览器导出；`09-47-41-157Z` 属于上一轮，未混用。部署身份为 `fff2fe15b7`、gpt-realtime-2.1、speed 1.25，Jiuwen Agent 为 deepseek-v4-flash#0。

This report expands the same recorded session, not a new benchmark. It uses the matching 11:36 browser export and retained server/Task snapshots. No new Provider, Agent, Tool or Task execution, code change, restart or deployment is involved.

## 口径 / Measurement definitions

- 所有表格单位为秒，显示到小数点后三位；原始计算保留毫秒。四舍五入可能使分项相加有毫秒级差异。All tables use seconds, rounded to three decimals; underlying calculations retain milliseconds, so rounded component sums can differ by a few milliseconds.
- 首音从浏览器收到 Provider EOT（轮次结束）到 `playout_clock_reached_start`。这是诊断播放时钟，不是扬声器声学测量。First audio means browser EOT receipt to the observed AudioContext playback-start clock, not acoustic speaker output.
- 实际说完到 EOT 的采集、上行和 VAD 尾部耗时，以及系统/耳机输出延迟，缺少逐轮声学校准，不能填成零，也不能直接用配置 450 ms 代替实测。Capture/uplink/VAD tail before EOT and physical output delay remain unmeasured per turn. The configured 450 ms is not a measured duration.
- 浏览器和 Gateway 分别在自身单调时钟内计算。下面两张首音表是不同层次，不能横向重复相加；Gateway 与浏览器的差值也不是纯网络时延。Browser and Gateway tables use separate monotonic clocks. They are nested views, not additive totals; their difference is not pure network latency.
- Native Realtime 的输入提交、文本转写、音频生成可并行，不能套成“ASR → 文本模型 → TTS”三个串行固定耗时。`input_committed` 是轮次提交，不代表 ASR 耗时。Native turn commit, transcription and speech generation can overlap; turn commit is not an ASR-duration measurement.
- 回执表示创建/调整请求被受理；文件完成、调整应用和结果被播出是三个独立时间点。Receipt, applied change, finished artifact and played result are separate endpoints.

## 1. 每段语音的首音总账 / Browser first-audio accounting

A = EOT → 浏览器接受第一帧 PCM / EOT to first accepted PCM。
B = 第一帧 PCM → 首帧排入播放 / PCM acceptance to first scheduling。
C = 首帧排入播放 → 播放时钟到达首音 / Scheduling to observed playback start。
每行总计严格采用同一浏览器时钟的 A+B+C。Each total is A+B+C on one browser clock.

| 语音 / Speech | A | B | C | 首音总计 / Total |
| --- | --- | --- | --- | --- |
| R1 介绍深圳 / Introduce Shenzhen | 2.354 | 0.035 | 0.041 | 2.430 |
| R2 深圳靠海吗 / Is Shenzhen coastal? | 1.218 | 0.036 | 0.033 | 1.287 |
| R3 哪里可以看海 / Where to see the sea? | 2.207 | 0.028 | 0.016 | 2.251 |
| R4 周六下午建议 / Saturday afternoon suggestions | 1.236 | 0.034 | 0.033 | 1.304 |
| R6 创建行程及文件：首次反馈 / Create itinerary and file: initial feedback | 1.713 | 0.032 | 0.017 | 1.763 |
| R7 创建回执：播放前中断 / Create receipt: interrupted before playback | — | — | — | — |
| R8 深圳美食 / Food recommendations | 1.629 | 0.092 | 0.034 | 1.755 |
| R9 调整早茶：首次反馈 / Adjust itinerary: initial feedback | 1.461 | 0.050 | 0.034 | 1.545 |
| R10 调整回执 / Adjustment receipt | 9.501 | 0.450 | 0.034 | 9.985 |
| R11 天气：首次反馈 / Weather: initial feedback | 1.228 | 0.042 | 0.017 | 1.287 |
| R12 天气：处理中播报 / Weather: in-progress update | 6.392 | 0.289 | 0.036 | 6.717 |
| R13 天气：正式结果 / Weather forecast | 27.971 | 0.033 | 0.033 | 28.037 |

完成与打断终点另列如下。Gateway 的“首帧发送 → 完成 ACK”还包含客户端接收和播放，不能当成纯音频时长；浏览器“首音 → 打断”只表示本次实际播放到被停止的区间。Completion/interrupt endpoints follow. Gateway first-frame-send to completion ACK includes client receipt/playback, not pure audio duration; browser start-to-interruption is the observed played interval before stop.

| 语音 / Speech | 首帧发送 → 完成 ACK / Sent to completion ACK (Gateway) | 首音 → 打断 / Start to interrupt (browser) |
| --- | --- | --- |
| R1 | 6.646 | — |
| R2 | — | 3.308 |
| R3 | — | 6.191 |
| R4 | 11.728 | — |
| R6 | 7.538 | — |
| R7 | — | — |
| R8 | — | 9.678 |
| R9 | 5.753 | — |
| R10 | 16.115 | — |
| R11 | 4.017 | — |
| R12 | 14.426 | — |
| R13 | 30.348 | — |

R5 对应最初的长创建请求，随后用户补充“并生成文件”，R5 没有播放。浏览器两个 EOT 相隔 1.718 秒；创建首音从补充语句结束起算为 1.763 秒，从第一段 EOT 起算为 3.481 秒。不能把用户仍在补充要求的时间算成同一轮系统处理。

R5 belongs to the initial creation request and was superseded by “and generate a file” before playback. The browser EOTs are 1.718 s apart. R6 starts 1.763 s after the addendum EOT, or 3.481 s after the first EOT. These are different reference points.

普通聊天 R1/R2/R3/R4/R8：中位数 1.755 秒，均值 1.805 秒，范围 1.287–2.430 秒。R6/R9/R11 是业务操作的先行反馈，不是工具执行结果。

Ordinary chat (R1/R2/R3/R4/R8): median 1.755 s, mean 1.805 s, range 1.287–2.430 s. R6/R9/R11 are initial spoken feedback, not completed business results.

## 2. 首音前服务端分解 / Gateway breakdown before first audio

G1 = Gateway EOT → 回答请求已发送 / EOT to response request sent。
G2 = 请求已发送 → Provider response.created / Request sent to response-created acknowledgement。
G3 = response.created → 收到首段音频 / Created acknowledgement to first PCM observed。
G4 = 首段音频 → 首帧准入调用结束 / First PCM to first-frame admission call settlement。
G5 = 准入调用结束 → 下行首帧发送 / Admission settlement to first downlink frame sent。

G2 含网络、Provider 接收/调度和本地收包；G3 含远端生成、返回传输及本地观测，不能称为纯模型计算或纯 TTS。G5 含媒体通道准备与交付等待，现有节点不能继续拆成独立的网络/缓冲分项。G2/G3 include network and observation overhead, not pure model compute; G5 covers local media readiness/delivery waiting and cannot be fully subdivided with these records.

| 语音 / Speech | G1 | G2 | G3 | G4 | G5 | Gateway 合计 / Total |
| --- | --- | --- | --- | --- | --- | --- |
| R1 介绍深圳 / Introduce Shenzhen | 0.007 | 0.188 | 1.819 | 0.004 | 0.344 | 2.363 |
| R2 深圳靠海吗 / Is Shenzhen coastal? | 0.010 | 0.193 | 0.662 | 0.004 | 0.362 | 1.232 |
| R3 哪里可以看海 / Where to see the sea? | 0.007 | 0.163 | 1.687 | 0.005 | 0.354 | 2.216 |
| R4 周六下午建议 / Saturday afternoon suggestions | 0.007 | 0.158 | 0.742 | 0.005 | 0.335 | 1.248 |
| R6 创建行程及文件：首次反馈 / Create itinerary and file: initial feedback | 0.007 | 0.158 | 1.222 | 0.004 | 0.335 | 1.726 |
| R7 创建回执：播放前中断 / Create receipt: interrupted before playback | 9.265 | 0.155 | 1.431 | 1.338 | — | — |
| R8 深圳美食 / Food recommendations | 0.101 | 0.164 | 0.886 | 0.214 | 0.371 | 1.735 |
| R9 调整早茶：首次反馈 / Adjust itinerary: initial feedback | 0.017 | 0.164 | 0.909 | 0.008 | 0.382 | 1.480 |
| R10 调整回执 / Adjustment receipt | 7.234 | 0.158 | 0.774 | 0.617 | 0.737 | 9.520 |
| R11 天气：首次反馈 / Weather: initial feedback | 0.008 | 0.165 | 0.705 | 0.005 | 0.356 | 1.239 |
| R12 天气：处理中播报 / Weather: in-progress update | 5.258 | 0.164 | 0.609 | 0.018 | 0.353 | 6.403 |
| R13 天气：正式结果 / Weather forecast | 16.177 | 0.258 | 0.862 | 10.280 | 0.405 | 27.983 |

R7/R10/R12/R13 的 G1 包含前序业务及等待，不能理解为单纯请求发送。下节展开这些部分。R7 的 G4 是失败的准入调用耗时，未产生可播放首帧。

G1 for R7/R10/R12/R13 includes prior business work/waiting, not just request transmission. R7's G4 is a failed admission call; no playable frame was sent.

首次反馈 R1/R2/R3/R4/R6/R8/R9/R11 的 G1 中，轮次提交分别为：R1=0.004 s、R2=0.005 s、R3=0.004 s、R4=0.005 s、R6=0.005 s、R8=0.096 s、R9=0.012 s、R11=0.005 s.

These are EOT-to-turn-commit intervals inside G1, not ASR durations.

首帧 Registry 等锁：R8 0.199 秒，R10 0.594 秒，R13 1.284 秒；未播出的 R7 等锁 1.332 秒。其他首次反馈首帧的同一锁等待约 0.010–0.015 毫秒。锁等待已包含在 G4 中，不重复加总。

First-frame Registry lock waits are 0.199 s (R8), 0.594 s (R10), 1.284 s (R13), and 1.332 s for failed R7. Other initial-feedback first frames wait about 0.010–0.015 milliseconds. These waits are already inside G4.

## 3. 创建、调整、天气调用及回执 / Business calls and receipts

以下每行是 Gateway 同一时钟上的串行增量，并附自本轮 EOT 的累计时间。先行语音与工具执行并行，不另外加上其 1.3–1.8 秒首音。

Each row is a sequential Gateway interval with cumulative time from that turn's EOT. Initial speech and tool execution overlap; do not add initial-feedback latency again.

### 创建行程 / Create itinerary

| 阶段 / Stage | 本段 / Increment | 累计 / Since EOT |
| --- | --- | --- |
| 等待第一个工具参数片段 / Wait for first tool-argument delta | 3.147 | 3.147 |
| 工具参数流完成 / Complete argument stream | 1.589 | 4.736 |
| 执行与往返，发送真实回执 / Execute/round trip and send real receipt | 1.317 | 6.053 |
| 等待前序播报 ACK 后启动回执回答 / Wait for predecessor playback ACK | 3.212 | 9.265 |
| 发送回执回答请求 / Send successor request | 0.001 | 9.265 |
| 收到 Provider 回答确认 / Receive response-created acknowledgement | 0.155 | 9.420 |
| 收到回执回答首段 PCM / Receive successor first PCM | 1.431 | 10.851 |

服务端内部 span（嵌套或并行，不能全部相加）/ Server spans (nested or concurrent; do not sum all rows):

| 阶段 / Stage | 耗时 / Duration |
| --- | --- |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.207 |
| 原始语音来源就绪 / Original utterance source wait (`native.task_source_wait`) | 0.002 |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.050 |
| 签发确认凭据 / Issue confirmation evidence (`task_intent.confirmation_issue`) | 0.024 |
| 正式任务调用 / Invoke formal Task operation (`task_intent.formal_invoke`) | 0.358 |
| 消费确认凭据 / Consume confirmation evidence (`task_intent.confirmation_consume`) | 0.388 |
| 任务意图与授权处理 / Task intent and authorization processing (`native.task_intent`) | 0.678 |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.054 |
| 业务处理主体 / Business handler (`native.business`) | 1.301 |

### 调整早茶 / Adjust itinerary

| 阶段 / Stage | 本段 / Increment | 累计 / Since EOT |
| --- | --- | --- |
| 等待第一个工具参数片段 / Wait for first tool-argument delta | 2.352 | 2.352 |
| 工具参数流完成 / Complete argument stream | 1.019 | 3.372 |
| 执行与往返，发送真实回执 / Execute/round trip and send real receipt | 2.300 | 5.671 |
| 等待前序播报 ACK 后启动回执回答 / Wait for predecessor playback ACK | 1.562 | 7.233 |
| 发送回执回答请求 / Send successor request | 0.001 | 7.234 |
| 收到 Provider 回答确认 / Receive response-created acknowledgement | 0.158 | 7.393 |
| 收到回执回答首段 PCM / Receive successor first PCM | 0.774 | 8.166 |

服务端内部 span（嵌套或并行，不能全部相加）/ Server spans (nested or concurrent; do not sum all rows):

| 阶段 / Stage | 耗时 / Duration |
| --- | --- |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.064 |
| 原始语音来源就绪 / Original utterance source wait (`native.task_source_wait`) | 0.001 |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.065 |
| 签发确认凭据 / Issue confirmation evidence (`task_intent.confirmation_issue`) | 0.045 |
| 正式任务调用 / Invoke formal Task operation (`task_intent.formal_invoke`) | 0.249 |
| 消费确认凭据 / Consume confirmation evidence (`task_intent.confirmation_consume`) | 0.411 |
| 任务意图与授权处理 / Task intent and authorization processing (`native.task_intent`) | 0.747 |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.141 |
| 业务处理主体 / Business handler (`native.business`) | 1.199 |

### 查询天气 / Start weather lookup

| 阶段 / Stage | 本段 / Increment | 累计 / Since EOT |
| --- | --- | --- |
| 等待第一个工具参数片段 / Wait for first tool-argument delta | 1.647 | 1.647 |
| 工具参数流完成 / Complete argument stream | 0.372 | 2.019 |
| 执行与往返，发送真实回执 / Execute/round trip and send real receipt | 0.810 | 2.829 |
| 等待前序播报 ACK 后启动回执回答 / Wait for predecessor playback ACK | 2.428 | 5.257 |
| 发送回执回答请求 / Send successor request | 0.002 | 5.258 |
| 收到 Provider 回答确认 / Receive response-created acknowledgement | 0.164 | 5.422 |
| 收到回执回答首段 PCM / Receive successor first PCM | 0.609 | 6.031 |

服务端内部 span（嵌套或并行，不能全部相加）/ Server spans (nested or concurrent; do not sum all rows):

| 阶段 / Stage | 耗时 / Duration |
| --- | --- |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.069 |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.073 |
| 取得 Agent 会话 / Acquire Agent session (`agent.session_acquire`) | 0.242 |
| Agent 运行配置 / Configure Agent runtime (`agent.runtime_configuration`) | 0.010 |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.076 |
| 读取业务上下文 / Read business context (`native.context_read`) | 0.420 |
| 权限复核 / Authority revalidation (`native.authority_reread`) | 0.081 |
| 业务处理主体 / Business handler (`native.business`) | 0.782 |
| 完整 Agent 轮次 / Complete Agent round (`agent.round`) | 12.674 |

创建的真实回执在 EOT 后 6.053 秒已返回；之后等前序播报 ACK 3.212 秒，回执回答首段音频在 10.851 秒到达 Gateway，但随后中断异常，因此没有正式确认首音。文件任务继续执行。

Create receipt returned at 6.053 s. It then waited 3.212 s for predecessor playback ACK; confirmation PCM reached the Gateway at 10.851 s but was interrupted before playback. The file task continued.

调整回执 5.671 秒已返回，而浏览器 9.985 秒才开始播放回执。其中参数流 1.019 秒；参数完成到回执 2.300 秒，AgentServer 的 native.business 主体只有 1.199 秒。剩余约 1.100 秒在主体之外，日志显示本轮输出在参数完成约 1.092 秒后才收束，随后才进入主体。回执之后还等前序播报 ACK 1.562 秒；R10 首帧准入 0.617 秒、下行等待 0.737 秒、浏览器接受 PCM 后到开始 0.484 秒。以上有包含关系，参照表格串行总账，不能重复加。

The adjustment receipt returned at 5.671 s but playback began at 9.985 s. Argument generation took 1.019 s. Of the 2.300 s argument-complete-to-receipt interval, the AgentServer business span was 1.199 s; about 1.100 s lies outside it. The current response settled about 1.092 s after argument completion before business dispatch. Receipt speech then waited 1.562 s for predecessor ACK, with 0.617 s first-frame admission, 0.737 s local downlink waiting and 0.484 s browser PCM-to-start latency. Nested intervals must not be counted twice.

天气的 0.810 秒是启动只读 Agent 工作并取得回执，不是完成天气查询。6.717 秒播出的仍是“处理中”；正式天气结果首音是 28.037 秒。

The weather call's 0.810 s is work-start receipt latency, not forecast completion. The update at 6.717 s still says the work is in progress; the forecast begins at 28.037 s.

## 4. 后台行程执行 / Background itinerary execution

| 阶段 / Stage | 耗时 / Duration |
| --- | --- |
| 受理 → running / Accepted to running | 1.325 |
| running → 首次模型调用 / Running to first model call (UTC approximate) | 2.633 |
| 16 次模型调用，占用时间去重 / 16 model calls, interval union | 72.712 |
| 27 次工具调用，占用时间去重 / 27 tool calls, interval union | 2.248 |
| 模型循环内其余间隙 / Other gaps inside model/tool loop | 1.436 |
| 末次模型结束 → 完成事件 / Last model end to completed (UTC approximate) | 6.472 |
| 受理 → 完成，总计 / Accepted to completed, total | 86.828 |

首尾涉及数据库 UTC 与诊断 UTC 的分段是近似值；模型和工具自身用单调时钟。并行工具原始耗时相加为 3.329 秒，去重后占用 2.248 秒。不能把并行时间都加到 86.828 秒上。

Database/diagnostic UTC boundary segments are approximate; model/tool intervals use monotonic time. Tool durations sum to 3.329 s, but their interval union is 2.248 s because some overlap.

调整请求入库 → 实际应用为 6.325 秒（11:31:04.256173 → 11:31:10.580689 UTC）；从调整语句 Gateway EOT 起算，应用约发生在 11.473 秒。它包含在后台任务执行期内，不能额外加到 86.828 秒。完成前的 artifact_diff=0.590、artifact_collect=0.097、prepare_d2_project_effect=0.821、settle_d2_project_effect=1.470 秒是末尾执行区间内部的已记录 span。完成后的资源清理约 0.774 秒。

Adjustment request persistence to application took 6.325 s, approximately 11.473 s after the adjustment Gateway EOT. This overlaps task execution. Recorded finalization spans include artifact diff 0.590 s, artifact collection 0.097 s, effect preparation 0.821 s and effect settlement 1.470 s. Cleanup after completion took about 0.774 s.

## 5. 天气 Agent 与正式播报 / Weather Agent and forecast delivery

| Agent 阶段 / Agent stage | 耗时 / Duration |
| --- | --- |
| 3 次模型调用 / Three model calls | 7.994 |
| 3 次网页读取，占用去重 / Three fetches, interval union | 4.019 |
| 初始化及调用间隙等 / Setup and other inter-call gaps | 0.661 |
| Agent round 总计 / Agent round total | 12.674 |

Agent 的模型调用分别为 1.938、2.056、3.999 秒；网页读取为 1.923 秒，然后并行 2.096 / 0.129 秒。Agent round 于 11:31:46.399 UTC 结束。模型/工具明细见附录。

Model calls took 1.938, 2.056 and 3.999 s. Fetches took 1.923 s, then parallel 2.096/0.129 s. The Agent round ended at 11:31:46.399 UTC.

正式结果到播放还经过这些节点（Gateway 时钟，累计从天气 EOT 起算）/ Forecast delivery milestones, measured on the Gateway clock from weather EOT:

| 节点 / Milestone | 距上一节点 / Increment | 距 EOT / Since EOT |
| --- | --- | --- |
| 开始刷新完成结果 / Begin result-context refresh | 15.582 | 15.582 |
| 完成结果刷新 / Result-context refreshed | 0.590 | 16.172 |
| 发送结果播报请求 / Forecast response request sent | 0.005 | 16.177 |
| 候选回答已创建 / Prepared response created | 0.258 | 16.436 |
| 收到候选首段 PCM / First prepared PCM received | 0.862 | 17.298 |
| 候选回答生成完毕 / Prepared response generation done | 7.731 | 25.028 |
| 候选回答获准交付 / Prepared response promoted | 1.000 | 26.028 |
| 首帧准入调用结束 / First-frame admission settled | 1.549 | 27.578 |
| 首帧下行已发 / First frame sent | 0.405 | 27.983 |

前序“处理中”播报的 ACK 在 11:31:52.091；候选天气回答直到 11:31:56.291 才生成完毕。源码要求前序 ACK 与候选生成终止都满足后，再刷新权限并交付，因此 48.559 → 57.290 的 8.731 秒不能全部归因于等锁或旧语音。其后首帧准入包含 1.284 秒 Registry 等锁。浏览器在 59.311 开始正式播报，30.284 秒后回到监听。

The in-progress speech was acknowledged at 11:31:52.091, but the prepared forecast did not finish generation until 11:31:56.291. Promotion requires both predecessor ACK and prepared-output termination, followed by revalidation. Thus the 8.731 s from first prepared PCM to promotion is not all lock wait or preceding speech. Subsequent admission includes a 1.284 s Registry lock wait. Forecast playback starts at 59.311 and the browser returns to listening 30.284 s later.

## 6. 完成通知逐段分解 / Completion-notification breakdown

任务完成 → 天气播完/恢复监听约 40.950 秒；之后通知首音再等 3.916 秒；合计约 44.866 秒。首段跨数据库与浏览器 UTC，按近似墙钟间隔报告。

Task completion to foreground-idle is approximately 40.950 s; notification first audio then takes 3.916 s, totaling about 44.866 s. The first segment crosses database/browser UTC and is approximate.

| 阶段结束点 / Stage endpoint | 本段 / Increment | 自空闲累计 / Since idle |
| --- | --- | --- |
| 取得通知呈现结果 / Notification presentation available | 1.462 | 1.462 |
| 能力确认与启动合成 / Capability check and start synthesis request | 0.019 | 1.481 |
| 合成准备返回 / Synthesis preparation returned | 2.005 | 3.485 |
| 领取播报权限 / Claim prepared speech | 0.005 | 3.490 |
| 首帧到浏览器 / First browser PCM | 0.322 | 3.812 |
| 首帧排入播放 / First scheduling | 0.087 | 3.899 |
| 播放时钟到达首音 / Playback clock starts | 0.017 | 3.916 |

其中服务端 `notification.prepare` 为 1.337 秒：读取未消费事件、结果、元数据并准备呈现权限；它包含在第一行 1.462 秒内，**不是 TTS 耗时**。实际 `synthesis.first_audio` 为 1.998 秒，包含在浏览器合成 RPC 的 2.005 秒内。对应 HTTP：TCP 0.032 秒、TLS 0.031 秒、等响应头 1.891 秒；发送请求头/体在该 trace 分辨率内为 0 ms，其余约 0.044 秒为初始化、首块读取和本地处理，不能假定物理零耗时。

The server's 1.337 s notification.prepare covers unread/result/metadata reads and presentation preparation, nested in the 1.462 s first row; **it is not TTS duration**. Actual synthesis.first_audio is 1.998 s inside the 2.005 s browser synthesis RPC. HTTP tracing reports TCP 0.032 s, TLS 0.031 s and response-header wait 1.891 s; request sends round to zero at that trace resolution, with about 0.044 s for remaining initialization/first-body/local processing.

通知首音 → 浏览器恢复监听 6.764 秒；约 0.001 秒后发播放 ACK，ACK RPC 0.301 秒，之后约 0.001 秒记录确认。首音 → 最终浏览器 ACK 总计 7.067 秒。服务端也存在 voice 消费记录，未被 text 消费替代。

Notification start to browser-idle takes 6.764 s, followed by approximately 0.001 s to issue ACK, a 0.301 s ACK RPC and approximately 0.001 s to record acknowledgement. Start-to-final-browser-ACK totals 7.067 s. Durable consumption is voice, not a text fallback.

## 7. 查询、异常与测量缺口 / Queries, errors and missing measurements

本轮没有语音 task.status 操作；以下只统计右侧面板的查询 RPC，不能替代“说完查询命令 → 播出状态”的体验数据。

No voice task.status operation occurred. These are right-panel query RPCs, not voice-command-to-spoken-status latency.

| 查询 / Query | 样本 / N | 最小 / Min | 中位 / Median | 最大 / Max |
| --- | --- | --- | --- | --- |
| list | 17 | 0.174 | 0.311 | 1.547 |
| status | 24 | 0.441 | 1.035 | 2.056 |
| events | 19 | 0.144 | 0.264 | 1.580 |
| result | 15 | 0.208 | 0.327 | 1.323 |

- `handle_p3_query` 单次占 Registry 锁最高 1.928 秒。查询总耗时不等于全程都持锁，也不等于纯数据库耗时。Maximum observed query-held Registry lock is 1.928 s; query RPC time is neither pure lock time nor pure database time.
- 播放中额外供给缺口：R9 seq76=0.328 秒；R10 seq28=0.829、seq44=0.680、seq60=0.059 秒。对应首帧之外的等锁分别为 1.282、1.266、0.943、0.336 秒。它们发生在播放过程中，不能加到首次首音时延上，也不能直接等同用户听见撕裂。Four mid-playback supply gaps are recorded; they are not additional first-audio delays or proof of audible tearing.
- 创建回执 R7：首帧准入等待期间被中断，抛出 STALE_RESPONSE_OUTPUT，媒体关闭；浏览器错误 → 再次捕获约 10.940 秒。不将未播放当作无限/超长首音，也不把任务执行成功等同回执播报成功。R7 failed before playback; recovery from browser error to resumed capture took about 10.940 s. Task success does not prove spoken confirmation.
- 天气 Agent 有 15 条可选上下文文件缺失错误；本报告附录的 tool_boundary complete 只表示观测调用结束，不能据此抹去这些更底层错误。The weather Agent logs 15 missing optional-context-file errors. Boundary completion does not erase lower-level tool errors.
- 首次开口、回执、应用、完成、播放 ACK 各自有独立口径；无声学校准、无本轮语音状态查询、无缺失事件的真实时间，不补造数值。No acoustic calibration or voice-status sample exists for this run, and missing timings are not invented.

## 8. 每次模型和工具调用 / Every observed model and tool call

UTC 时刻用于定位；耗时使用单调时钟。工具阶段可能并行，使用区间并集分析占用，不把各行直接加到总延迟。Tool durations may overlap; use interval unions for elapsed-time attribution.

### 后台行程 / Background itinerary

| 调用 / Call | 开始 UTC / Start UTC | 首输出 / First output | 总时长 / Duration |
| --- | --- | --- | --- |
| 1 | 11:30:25.774 | 0.599 | 1.643 |
| 2 | 11:30:27.461 | 0.904 | 2.282 |
| 3 | 11:30:29.826 | 0.599 | 2.952 |
| 4 | 11:30:32.970 | 0.601 | 3.502 |
| 5 | 11:30:36.635 | 0.616 | 3.487 |
| 6 | 11:30:40.220 | 0.620 | 3.070 |
| 7 | 11:30:43.846 | 0.714 | 4.353 |
| 8 | 11:30:48.371 | 0.710 | 3.948 |
| 9 | 11:30:52.534 | 0.713 | 3.827 |
| 10 | 11:30:56.597 | 0.736 | 2.829 |
| 11 | 11:30:59.530 | 0.739 | 3.593 |
| 12 | 11:31:03.475 | 0.795 | 7.017 |
| 13 | 11:31:10.723 | 0.834 | 10.036 |
| 14 | 11:31:21.082 | 0.928 | 12.728 |
| 15 | 11:31:34.240 | 0.934 | 3.673 |
| 16 | 11:31:38.400 | 0.790 | 3.773 |

| 调用 / Call | 工具 / Tool | 开始 UTC / Start UTC | 耗时 / Duration | 边界状态 / Boundary status |
| --- | --- | --- | --- | --- |
| 1 | list_files | 11:30:27.423 | 0.017 | complete |
| 2 | list_files | 11:30:29.758 | 0.036 | complete |
| 3 | read_file | 11:30:29.766 | 0.032 | complete |
| 4 | read_file | 11:30:32.786 | 0.122 | complete |
| 5 | read_file | 11:30:32.792 | 0.092 | complete |
| 6 | read_file | 11:30:36.486 | 0.108 | complete |
| 7 | read_file | 11:30:36.498 | 0.085 | complete |
| 8 | read_file | 11:30:40.129 | 0.069 | complete |
| 9 | read_file | 11:30:40.135 | 0.019 | complete |
| 10 | read_file | 11:30:43.301 | 0.453 | complete |
| 11 | read_file | 11:30:43.313 | 0.507 | complete |
| 12 | read_file | 11:30:48.230 | 0.037 | complete |
| 13 | read_file | 11:30:48.239 | 0.094 | complete |
| 14 | read_file | 11:30:48.241 | 0.058 | complete |
| 15 | read_file | 11:30:52.326 | 0.111 | complete |
| 16 | read_file | 11:30:52.332 | 0.167 | complete |
| 17 | read_file | 11:30:56.412 | 0.102 | complete |
| 18 | read_file | 11:30:56.417 | 0.103 | complete |
| 19 | read_file | 11:30:59.434 | 0.071 | complete |
| 20 | read_file | 11:30:59.439 | 0.039 | complete |
| 21 | read_file | 11:31:03.131 | 0.250 | complete |
| 22 | read_file | 11:31:03.138 | 0.057 | complete |
| 23 | glob | 11:31:10.503 | 0.038 | complete |
| 24 | glob | 11:31:10.508 | 0.032 | complete |
| 25 | declare_file_effect_plan | 11:31:20.793 | 0.272 | complete |
| 26 | write_file | 11:31:34.193 | 0.023 | complete |
| 27 | read_file | 11:31:37.925 | 0.335 | complete |

### 天气 Agent / Weather Agent

| 调用 / Call | 开始 UTC / Start UTC | 首输出 / First output | 总时长 / Duration |
| --- | --- | --- | --- |
| 1 | 11:31:33.940 | 0.541 | 1.938 |
| 2 | 11:31:37.886 | 0.479 | 2.056 |
| 3 | 11:31:42.117 | 0.570 | 3.999 |

| 调用 / Call | 工具 / Tool | 开始 UTC / Start UTC | 耗时 / Duration | 边界状态 / Boundary status |
| --- | --- | --- | --- | --- |
| 1 | fetch_webpage | 11:31:35.884 | 1.923 | complete |
| 2 | fetch_webpage | 11:31:39.988 | 2.096 | complete |
| 3 | fetch_webpage | 11:31:39.991 | 0.129 | complete |

## 9. 结论与可复算证据 / Conclusions and reproducibility

普通首次反馈主要等待 Realtime 回答生成和约 0.33–0.38 秒的本地下行交付；个别首帧另受锁影响。后台操作的首轮开口已早于回执，但参数生成、前序口头回应 ACK、回执生成和本地播放都会影响正式确认。天气完整结果还受 Agent 处理、候选回答完整生成和播放串行条件影响。任务完成通知这次确实播出，其中空闲后仍有约 1.46 秒呈现准备与 2.00 秒合成准备。

Initial feedback is dominated by Realtime response generation plus roughly 0.33–0.38 s local downlink readiness/delivery, with additional lock waits in some responses. Early speech now precedes business receipts, but argument generation, predecessor playback ACK, receipt generation and local playback still delay confirmation. Forecast delivery additionally waits for Agent work, complete prepared-response generation and serial presentation conditions. The completion notification was played; after foreground-idle it still needed about 1.46 s presentation preparation and 2.00 s synthesis preparation.

这是当前已保留验收样本的分析，不是新的全量性能保证。原先 3.3 秒基线缺少一致端点和样本选择，不计算严格改善百分比；没有用本次数据重新打开已接受的听感验收。

These are measurements of the retained run, not a new performance guarantee. The older 3.3 s baseline lacks aligned endpoints/sample selection, so no strict improvement percentage is calculated. This analysis does not override the user's listening acceptance.

私有原始证据位于 `logs/acceptance-web_1a080c762a5_7ff4e1f0095d/`：`expand_timing.py` 只读取既有快照，生成 `detailed-timings.json`；该 JSON 保留每个节点的 event、clock_id、sequence、UTC 和 monotonic_ms。`render_timing_report.py` 生成本报告。源浏览器导出的 SHA-256 为 `bc757d1d78ae4da7949081b1745bdf64cb829e31ae735d23f4cabdb9a1eb3f5b`。

Private source evidence and reproducible scripts remain in the ignored run directory. The JSON retains event, clock ID, sequence, UTC and monotonic time for each response/call node. Assertions verify same-clock subtraction, nonnegative durations and browser/Gateway interval sums. Documentation checks cover local links and diff formatting; no product tests or fresh physical acceptance are claimed.
