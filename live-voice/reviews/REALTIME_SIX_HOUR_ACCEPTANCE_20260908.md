# Live Voice 六小时修复验收记录

执行窗口：2026-09-08 01:55:37–07:55:37（Europe/Paris）。六小时交付快照，保留所有未达标项。
当前仓库为 `C:\Users\admin\Desktop\live voice hx`；不是输入文档中的旧机器路径。
执行边界、逐次失败和检查记录见 [执行记录](REALTIME_SIX_HOUR_REPAIR_20260908.md)。

## 当前判定：PARTIAL

已实际改代码、运行受影响测试、独立审查，并多次完成受控本地部署和真实
Provider → Jiuwen Agent → Task → 项目文件链路。仍有内容、首音时延、文件名和长任务
收敛问题；没有真人麦克风、浏览器播放和耳机验收，不能宣称撕裂和等待
已经全部消失。收包和生成文字都不等于用户听到。

所有下述 CLI 音频使用真实合成输入与实际 Realtime 会话，不替代 Jiuwen Agent。
录音端只确认收到并解码的媒体帧，没有伪造实际播放 ACK、STOP 播放回执或 heard
history。未控制浏览器、鼠标、键盘和设备。原问题视频及原 Provider PCM 在此
机器不可用，没有重新听过原视频的证明。

原片 15 个标记均缺本机原始媒体，不能逐点确认成因；A–D 证明的是可复现的同类
供给、诊断和调度机制，没有把这些证据冒充为原片 15 处均已修复。

## A–H 实际修改与边界

| 组 | 有证据的问题与修复 | 检查及剩余限制 |
|---|---|---|
| A prepared 供给 | 相对逐帧等待会积累处理耗时；改用真实样本数和绝对截止时间，最大追赶信用 320 ms；单 Provider reader 优先处理 STOP，去除每事件额外接收任务 | 同字节/同顺序/取消检查通过；真实设备连续消费尚未验收 |
| B 诊断竞争 | 敏感键正则在长 ID 中反复尝试后缀，六个 handler 重复清洗同一记录；保留脱敏，优化键边界扫描和精确 LogRecord 内复用 | 5,000 个旧新脱敏输入零差异；生产日志开启的受控供给明显改善，详见下表；不把关日志当解决方案 |
| C 准入与共享锁 | notification 的外部授权读取占用 Registry 全局锁；移到锁外准备，锁内精确复验路由/代次/重放身份 | 九个锁/取消/替换/重放交错检查通过；未去掉逐批媒体准入与权限门禁 |
| D 及时通知 | 首批 Native 音频已入队时，现有业务 poll 仍可能等待；增加精确私有 wake，使原消费者及时返回 keepalive 并取已排队描述符 | 不新增消费者、不消耗业务通知；每响应幂等、每会话最多八个待唤醒；378 个边界检查通过 |
| E 端点与配置 | 原主机实际为 gpt-realtime-2，不能冒认 2.1；实现并由 Provider 确认 2.1、语速 1.25、reasoning effort 及关闭自动响应的端点预设 | 实测 semantic / server 300、450；600 仅有配置边界检查，未做真实延迟组；保留 gpt-realtime-2.1 与 deepseek-v4-flash；物理停顿/打断代价未验收 |
| F 真实 Task 接单续答 | durable 接单以后仍等待非必要完整上下文；只对已落账的 task.create/create_successor 使用真实回执续答 | 下一业务操作仍须 context.get 和新权限/版本；不提前确认接单、不生成占位语音；实际首音仍超 3 秒目标 |
| G 参数与上下文 | 模型复制大上下文 ID、文件名分隔符漂移、显式源文件操作前多做无用查询；服务器冻结已提交输入和已发送上下文，13 个 bound 工具只接完整 request_text 与真实目标 ID/版本 | schema 不主动删去业务字段，不引入分类器；模型仍会漂移金额/时间/字面路径，最终发现 D→C 覆盖反例，不能承诺约束不丢失 |
| H 后台非终态反馈 | 已真实接受的 work.start 仍等待 Engine 上下文刷新；仅对未完成、精确身份/版本的回执优化续答，发送前再次复验 | Router 完整上下文保持；终态/新版本恢复完整上下文；316 个相关检查和独立竞态复审通过；1–1.5 秒反馈目标尚未获得实测通过 |

额外修复包括：前台路由关闭/重连的精确所有者清理、Voice off 后 P3 Task 状态延续；
显式复述与默认简短提示的冲突（含四个独立回执续答入口）；实际结果回执已有金额时
不得称其不存在；后台连续六轮完全相同的有界 read_file 批次在下一模型调用前失败，
避免重复读数百次并确保失败不应用隔离目录中的部分文件。这个防循环检测不覆盖
所有模型不收敛轨迹，也不把控制消息夹具冒称为实际文件工具运行。

## 分段测量与连续性

以下首音列实际为“输入声学结束 → CLI 录音接收的第一帧”，不是扬声器首音，
也不能给无意义回答以“有内容首音”通过信用。P95 使用 nearest rank。配置或
源代码不同的组不是严格单变量因果比较；所有失败样本保留。

| 版本/配置 | 普通样本 N | 接收首帧 P50 / P95 / 最大值（ms） | 后台/工具观察 |
|---|---:|---:|---|
| 初始 d8ee9e6d / gpt-realtime-2 | 1 | 2759.43 / 2759.43 / 2759.43 | 创建确认 10097.71 ms；文件名与请求不符 |
| a8b0c3a0 / 2.1 low semantic-auto | 6 | 1809.312 / 1901.878 / 1901.878 | 天气样本 11678.381 ms，存在重复 work.get 等待 |
| 5b0f816d / minimal semantic-auto | 6 | 1868.563 / 1994.313 / 1994.313 | 四个新 Work 首包 3280.662–3811.511 ms，未再循环 work.get |
| 426637c1 / minimal semantic-high | 6 | 1611.144 / 1772.316 / 1772.316 | 新天气查询 3633.422 ms |
| 5cf391d6 / minimal server450 | 6 | 1610.075 / 1737.336 / 1737.336 | 下划线派生文件正确，首包 9560.550 ms；无用查询随后修复 |
| 5cf391d6 / minimal server300 | 6 | 1522.832 / 1598.577 / 1598.577 | 冲突派生任务实际循环失败；不是完整体验通过 |
| 1f499b8f / minimal server450 | 30 | 1612.609 / 1977.534 / 2311.174 | 声学结束附近有实际 Task 在跑的 10 轮；一轮复述输出无关短词，另一轮早餐未给出所要求主食 |
| 90955111 / minimal server450 | 32 | 1666.455 / 2199.960 / 2220.127 | 10 轮声学结束附近 Task 状态确为 running；六个新 Task 实际完成；五次结果查询 |
| 2a78ecf9 / minimal server300 | 30 | 1474.903 / 1809.810 / 1881.038 | 14 轮有真实 running Task；45 个完整旅程，含 12 个创建/调整/结果查询；文件覆盖、篇幅及查询失败见后文 |

1f499b8f 的 41 个可关联响应，按首帧 Native response / generation 和 Provider
source_event_id 精确连接，同一 Gateway 单调时钟测得原始首 PCM → 首帧发出：
P50 **27.678 ms**，P95 **56.322 ms**，最大 **79.814 ms**。包含主动在接单时关闭
语音的创建样本，不把未收音频算成零延迟。该指标达到 ≤200 ms 的服务器目标，
不能替代浏览器接收、缓冲、实际起播或用户听感。

90955111 的 44 个旅程中，43 个有首帧可精确关联，原始首 PCM → 发帧：
P50 **25.746 ms**、P95 **37.521 ms**、最大 **49.972 ms**。32 个普通回答均收到，
seq/cursor 缺口零，选中诊断链路的丢弃数零。按初始 250 ms 储备模拟没有预计
欠载，但最长包间隔为 672.449 ms；这只是接收侧储备模型，不能证明浏览器没欠载。

800235d9 的 11 个补充旅程则为 P50 **27.504 ms**、P95/最大 **216.729 ms**，
该小组未达到 ≤200 ms。异常值发生在真实文件分析 Work 首反馈：Registry 准入
0.217 ms、锁等待 0.008 ms；Gateway 准入完成到 source_ready 约 212 ms，随后
发送队列 0.211 ms、socket 发送 0.160 ms。尾延迟仍位于媒体接入/准备路径，现有
证据不足以归因全局锁或网络。不能合并较快样本稀释这个失败组。

最终 2a78ecf9/server300 的 45 个旅程中 44 个有首帧精确关联，原始 PCM→发帧
P50 **27.715 ms**、P95 **36.595 ms**、最大 **57.357 ms**。30 轮普通问答均收到，
seq/cursor 缺口零，14 轮真实 Task running。300 较 450 的输入拆句更多：同字节
普通03为7段对4段、06为6对3、12为5对3；背景任务发生“写约→解约”，并有
正确转写D却委派C路径的独立错误。最终恢复 server450；这是当前观察下的取舍，
不是证明450能消除这些语义错误，也没有把不同版本/负载的全部差异归因于端点。

真实工具分段使用精确 call ID，各列在各自服务器的同一时钟中测量，不跨机器
时钟相减。90955111 的结果如下（P50/P95，ms）：

| 操作 | N | 参数流开始→结束 | 参数结束→回执发出 | delegate 准入→封存回执 |
|---|---:|---:|---:|---:|
| task.create | 6 | 1038.463 / 1520.778 | 778.356 / 931.295 | 564.432 / 714.623 |
| task.adjust | 1 | 710.219 / 710.219 | 1196.741 / 1196.741 | 1000.161 / 1000.161 |
| task.result | 3 | 509.667 / 603.599 | 1140.035 / 1426.223 | 906.451 / 1197.264 |
| task.status | 1 | 458.239 / 458.239 | 896.516 / 896.516 | 664.154 / 664.154 |
| context.get | 4 | 755.503 / 825.537 | 752.154 / 802.079 | 199.385 / 204.264 |

最后一列包含于前一列，不可当独立段累加；delegate 准入也不是 durable Task
接单时刻。端点→首次 response.create 的 P50/P95 为 6.967/9.559 ms，多端点
样本不可拿首次请求冒充最终声学端点。1f499b8f 的两次收音创建确认为 4553.208、
4775.356 ms；90955111 的五次查询为 4665.743、4909.243、5483.861、4691.504、
4218.382 ms。800235d9 三个真实 work.start 首反馈分别为 **3273.728、4488.186、
3621.916 ms**，创建确认为 **4275–5324 ms**。这些实际值仍未达到目标。

接单里程碑单列如下。第一列是客户端收到已落账 Task 关联的时刻，相对客户端
声学结束；它是 durable 接单的可观察上界，不是服务器落账瞬间。实际 TaskCore
created_at/terminal UTC 与精确 Task ID 全部保存于 `task-milestones.json`，没有拿
秒精度的客户端 UTC 与服务端时间戳相减。Task 生命周期不是语音时延。

| 创建组 | N | durable 回执到达 P50/P95/最大 ms | 接单语 PCM 到达 N；P50/P95/最大 ms | 接单→Task 终态 P50/P95/最大 ms |
|---|---:|---:|---:|---:|
| 1f499b8f | 5 | 4214.985 / 4767.548 / 4767.548 | 2；4664.282 / 4775.356 / 4775.356 | 40676.743 / 45602.141 / 45602.141 |
| 90955111 | 6 | 4007.349 / 4359.351 / 4359.351 | 5；6578.265 / 7124.388 / 7124.388 | 36498.819 / 65584.282 / 65584.282 |
| 800235d9 | 4 | 3971.362 / 4002.518 / 4002.518 | 4；4738.653 / 5324.462 / 5324.462 | 42458.106 / 118602.204 / 118602.204 |
| 2a78ecf9/server300 | 6 | 3839.420 / 4243.407 / 4243.407 | 5；7757.040 / 8127.808 / 8127.808 | 71698.596 / 86358.147 / 86358.147 |

各组创建文本不同，不构成严格单变量延迟比较。主动关闭的无收音样本不赋零值；
较短观察窗口只保留实际收到的确认开头，不能证明完整播完。`acceptance_spoken`
（物理）全部未测，`first_feedback` 的收包代理值见 Work 表述，`artifact_ready`
必须由完成 Task 的真实封存文件验证。800 的两个失败终态没有 artifact_ready。

受控同 PCM 生产 downlink 与真实日志 handler 的 A/B 各 16 次：缺样本、重复、
错序和诊断丢弃均为零。空载诊断开时首八帧中位数 **136.68 → 20.72 ms**，
50 帧 **292.50 → 106.35 ms**，CPU **257.81 → 46.88 ms**；CPU 负载时首八帧
**124.88 → 23.23 ms**，50 帧 **293.34 → 114.89 ms**。诊断关闭对照约 14/100 ms。
完整 CPU/loop-lag、边界和原始证据入口见 [供给证据](../evidence/REALTIME_SUPPLY_DIAGNOSTICS_20260908.md)。

## 真实 Task 与文件

1f499b8f 最终批次实际创建五个独立 Task，均 completed，分别生成：

| Task ID | 项目相对文件 | 字节数 |
|---|---|---:|
| task-f7d8490cc11e4dca83e490912dd3a37a | 验收输出/最终行程方案.md | 10211 |
| task-c442b76f092f454a87045362d4bad21c | 验收输出/最终客户说明草稿.md | 10473 |
| task-e535a14a782a4ddf857a115d6c07284f | 验收输出/最终预算审计.md | 10847 |
| task-fea5a2c7195b486eaf22881679acf913 | 验收输出/最终时间审计.md | 9242 |
| task-2da0a81ee05648969c298f9dbdce22c0 | 验收输出/最终变更方案.md | 9960 |

实际文件核对包含高铁新增费用 850 元、余量 650 元、增加准备时间后最晚 08:40
出发、未对外发送/退款/订票。查询预算时曾错误否认回执已含的金额；复述同一音频
曾出现无关数字回答。修复后同音频三次完整，但不能据此宣称所有内容错误已解决。

客户草稿的调整发生在 Executor 已完成、TaskCore 尚未同步的窗口。调整随后被
`TASK_TERMINAL_BEFORE_ADJUSTMENT` 拒绝、outbox suppressed、未投递 Executor。
原文件没有要求的开头标记，不能称为已调整成功。800235d9 已在首次调整回执封存前
读取同 Task/Attempt/adjustment 的现有授权快照，附带 as-of 状态；旧封存回执保持
字节一致重放，不重新执行命令。251 个相关检查含真实 SQLite 终态竞态及并发重放，
独立审查通过；新的真实调整明确说“等待应用，不能确认已写入”，没有虚报完成。

此前实际正确派生 `深圳出差行程_海边版.md`，源文件和旧连字符版本均保留。
另一个严格第二晚改写 Task 因 100 轮重复读取失败，失败证据保留。

90955111 又完成六个真实 Task，但五次指定“复核”文件名中的四次实际路径不符：
`综合行程方案.md`（14025 bytes）、`综合客户说明草稿.md`（8147）、
`复合预算审计.md`（10941）、`复合时间审计.md`（8035）；只有
`复核变更方案.md`（12207）符合这一前缀。至少两次输入转写含正确“复核”，
因此不能把所有路径错误都归咎于听写同音字。第六个跨文件审计为
`交叉一致性审计.md`（17521）。文件名均在 `验收输出/` 下。新的预算查询正确
报告 850/650 元，时间查询正确说 08:40；第一条状态查询却因任务名字漂移反问，
正向查询仍未全部成功。32 轮中的完整复述、早餐和合计问题本轮已答对。

800235d9 四个文件旅程由独立审查直接核对真实 Task、Executor 日志和 artifact：

| Task ID | 真实结果 |
|---|---|
| task-c9ff25454097421dbd5c0e1099a497a1 | 严格替换原文不存在的第二晚安排：failed / NO_EFFECTIVE_TARGET_CHANGE；一次读取、一次搜索、零写入，目标不存在。这是正确拒绝，不是编辑成功。 |
| task-74fce973fb104ea5986004b778c210e3 | completed；完整副本_可选散步.md 恰为源文件 2963 bytes 原样前缀加指定 51 bytes，合计 3014。SHA256 f03eb3f061acbe8b0a66491e00271acc45bf87c015d1c6de0e0c2736df22c22d，与封存一致。 |
| task-037c2ba3087f403daff2de6e6e3a6136 | 六千字交接报告失败。05:06:56 UTC 同 Task 调整真实 applied，05:07:29 隔离区写过包含指定首行的报告；随后六轮相同窗口自检，05:08:00 以 BACKGROUND_TASK_READ_NO_PROGRESS 失败。真实委派路径交接_check_Adjust.md 不存在（请求check_adjust.md，路径也有漂移），无部分产物应用。 |
| task-4122371f7236492599034e279f2f32b0 | completed；复述条件核对.md 为精确三行“ 两个人 / 9月12日-13日 / 总预算1500元 ”（无外侧空格），43 bytes。SHA256 fc71cf22a58be8c6184b61fac825ae651b0c12b28f6b04654f50525a74dad72a，与封存一致。outbox 尝试三次，实际执行和写入各一次。 |

扣除两个成功新增文件后，项目内容指纹与这些 Task 的执行前指纹一致：既有文件
未改动，两个失败 Task 没有正式文件副作用。长报告不能记为“零进展”或“调整没应用”，
也不能因保护生效计作正向交付成功。2a78ecf9 增补专用后台提示：复用已有源窗口，
资料够用就写，验证满足后完成，只有具体差异才修改重查；六轮保护和输出检查不放宽。
该提示的 14 项模式检查和独立审查通过；下面保留真实复跑的成功与失败边界。

2a78ecf9 的 `task-a39863ea824f42fa807fcd35a6dcde56` 复跑仍失败：24 次工具调用均
只读，零 write/edit，最终 NO_EFFECTIVE_TARGET_CHANGE，check_retry.md 不存在。
它先查不存在的验收资料点.md，后来也读了正确源文件；末轮输出 8192 tokens
但没有工具调用。日志缺 finish_reason，不能断言 token 上限是确定根因，也不能
把它仅归为源文件找不到。

独立真实 Session 改用“名为验收资料的 Markdown 文件”描述源文件后，
`task-c2aade50da3e4611adf2f3e401fb1dbc` completed，真实 `check_final.md` 封存 SHA256
为 `9305f0b573623c7d9aed64c0917eae3fbc5cc7a9d281f1a314c759713b80d91d`。
850/1260 元、650/240 元余量、09:00/08:40 及退款/酒店单列正确，首行标题包含
“仅供内部审阅，未发送”；所有既有源保留。全文 7002 字符、非空白 6219、汉字
3862，不能把含 Markdown 和空白的字符数称为完成六千字要求。该正向例证明能
落盘和完成事实核对，长报告篇幅及稳定收敛仍是 PARTIAL。

909 客户草稿的第二次调整也被 terminal-before-adjustment 拒绝，outbox 零投递，
原文件没有指定首行；SHA256 为 d5111cab46635005d662c24be2d56556dd1ea54a4a63df8bfe9ba17e5ca0a4b6。
跨文件审计正确核对了主要算术和一般未发送声明，但不能替代该首行调整是否应用。

800 的真实插话第二输入注入后仍收到 32 帧旧 PCM，最后一帧比第二
media.speech_start 到达早 109.265 ms；此后至观测结束无旧帧，新回复首 PCM
距第二声学结束 1427.030 ms，重开后 1995.021 ms。服务器已发送 response.cancel，
但录音端没有旧流 STOP/detach 回执，旧流最终由脚本 cleanup 关闭。不能报告
“STOP 后旧 PCM 为零”或物理止声通过。

最后 server300 五个业务 Task 的实际结果：

| Task | 实际产品结果 |
|---|---|
| task-ac95b7d8ddf541929aabc31176012c1c | A completed，vad300_a.md，2582汉字，约四千字要求偏短 |
| task-97877ecc226f4efca0593a038af947ce | B completed，vad300_b.md，3754汉字；同Task调整真实applied且只投递一次，首行正确 |
| task-cf08214839224becb4d06fd0e9d449c6 | C completed，原vad300_c.md为4064汉字；“写约”转写为“解约”，报告出现非原始要求的合同终止主题；其后被D覆盖 |
| task-1f4b911f843148aa93424e7e55593eff | D Core为completed但产品失败：输入明确D，工具指令写C，覆盖了已有C；原要求vad300_d.md当时没有生成 |
| task-5576d9d9f0bf4b1eb0da2c5707a0e832 | E failed / NO_EFFECTIVE_TARGET_CHANGE，10次工具调用全部只读，vad300_e.md不存在 |

五次查询首 PCM 分别为 4892.861、7413.467、5278.088、5148.740、6528.999 ms。
01/03/04/05与实际状态、08:40、未发送及失败事实对应；02只返回“正在分析”，
没有回答850/650，正向结果查询失败。30轮中的15/18/21/30生成内容正确，15/18/30
录音二次转写也完整；二次转写误词不能独立判断实际发音。停顿复述完整，插话后
新问题可答，仍无旧流STOP回执或物理止声信用。

最后的 D 覆盖触发即时维护恢复：先保全 D 全字节到 ignored 证据及原本不存在的
vad300_d.md，再从项目Git blob `50d736d3d7a48ef69b8b1324f8e577e25b862611`
恢复 C。C恢复SHA256 `16ba045fd856abec5e759c1e416582d482d483b24ecbd6d2227c09937bbb1f1c`；
D保全SHA256 `6caa9610e146c3543832f4b11c68c8940cac4d53fa52d256bb0fa6b400415d8c`。
两者没有丢失，但此举属于维护修复，**不计作原Task成功，不回写历史artifact路径或状态**。

d13c73bb 追加专用后台提示：已有精确目标且要求保留该文件/全部文件、未明确授权
编辑该目标时，报告冲突且不覆盖、不自改路径；显式编辑目标仍可进行。14项模式
检查和独立审查通过。这只是提示约束，不是原子防覆盖保证。当前仍缺后端结构化
保存约束对抗模型路径漂移的可靠证明，保留文件能力不能关闭为PASS。

最终 d13c73bb/server450 真实保护复验：Task
`task-1d6b5cdbdcb04dfba807bef8f6db3ece` 于05:52:09接单、05:52:41终态failed。
它被要求在保留全部已有文件的同时另写到已有C路径；复验后C的原封存哈希不变。
独立审查确认10次只读调用、零write/edit、零artifact，结构化原因为
NO_EFFECTIVE_TARGET_CHANGE。源又被委派为不存在的验收资料点.md，存在缺源混杂，
故不能独立证明失败只由新冲突提示造成，也不能证明原子防覆盖。新激活的完整条件复述仍可用，
全部原始结果见 `preservation-final-*.json`。

## 六项产品验收

| 验收 | 当前结果 | 实际证据和缺口 |
|---|---|---|
| A 长回答完整性 | PARTIAL | 909 的 32 轮中复述/早餐/合计正向例正确，复合 Task 接单也完整复述三条件；0.30 秒停顿输入完整保留转折与尾条件；无物理尾音验收 |
| B 开头与连续性 | PARTIAL | 两组 30/32 轮各有 10 轮 Task 真在 running，均无 seq/cursor 缺口；没有连续五次人工对话、扬声器欠载和吞字听感证明 |
| C 打断 | PARTIAL | 实际 CLI 第二输入打断旧生成，并收到完整新彩虹回答；模块负向检查通过；不能替代四种播放阶段的物理 STOP、队列清空和新问题验收 |
| D 文件创建与派生 | PARTIAL | dirty 项目真实文件/Task/哈希已有证据；literal 下划线正确；冲突任务失败、终态竞态调整未应用，须分别列明 |
| E 状态与通知 | PARTIAL | Voice off 后 Task 实际继续完成；实际调整先 pending 后 adopted，最终 Task 失败均保留；真实面板自动更新/断网/重复通知未验收 |
| F 停止、退出、重开 | PARTIAL | 实际新 P2 reopen 正常收到完整新回答；精确取消、重放、跨范围负向检查通过；没有真实麦克风释放及设备重开证明 |

## 测试、审查与部署交付

检查按受影响边界选取，各批数量有重叠，不相加伪造总覆盖率。后台 Executor/
checkpoint 161 passed、2 skipped；两项 skip 为 Windows 无文件/目录 symlink 权限
（WinError 1314），junction 检查通过。14 个后台模式检查通过。显式回复最终
223 个 Engine/bound-tool 检查通过，独立审查关闭四个覆盖提示冲突。

完整历史套件没有全绿：重跑曾有 Registry 286 passed/7 failed（旧 Native 业务
能力夹具），mounted Web 140 passed/11 failed/1 skipped（十项旧 Task-intent UI
夹具加一项已修复 Exit 夹具）。这些结果和原因保留在执行记录，不以旧基线豁免
受影响失败，也不冒称新完整套件通过。

最终产品代码为 `d13c73bbf65dd19a4fc44be8e0b0dd9e7f186d8c`。随后交付提交只更新
本记录、STATUS 和当前验收路由，运行代码与最终 Git 文档提交的差别会明确列出。
分支 `hx/0812_live_voice_w3`，本次没有更新任何远端 ref；既有用户数据和原始失败
证据均保留，没有删除失败测试或回写旧 Task 为成功。

实际访问入口：[http://localhost:5173](http://localhost:5173)。绑定的本机独立项目：
`C:\Users\admin\AppData\Local\Temp\jiuwenswarm-realtime-p3-project-c99a45f0309a4867bcb37aa235204928`；
数据目录为同级 `jiuwenswarm-realtime-p3-data-c99a45f0309a4867bcb37aa235204928`，原验收
Session 为 `web_1a07e8a349d_c4fbb8e33c1f`，另保留一个长报告独立 Session。
配置绑定文件为 `C:\Users\admin\.jiuwenswarm\config\live-voice-formal-web-validation.json`。
最终部署日志为 `logs/swarm-20260908-074955.log`；runtime source 为 d13c73bbf6，
启动时 tracked dirty count=0，endpoint=server-vad-450。端口/PID快照：5173/7708、
18092/24908、19000与19001/24888；完整无密钥快照为 `delivery-runtime.json`。
运行合同 `logs/live_voice_runtime_contract.json` 不含密钥；Provider 为真实 OpenAI
Native，模型 gpt-realtime-2.1、speed 1.25、reasoning minimal，Agent 保持
deepseek-v4-flash，model config version e3ed8c0f9de4aeed889885737122a54fccf82632423bd9ca9592239d2c3af2b6。

最新实际前端资源 `/assets/index-DrD28158.js`，SHA256
`583ad968107e7683a18b97a5cef2555d54c81438fd3b26f51f0ca3fcd5a19f6a`。
正式 launcher 每次执行 tsc/Vite 构建、四端口就绪、真实 TTS→STT 和身份/伪造 claim
拒绝检查；没有跳过校验复用过期编译缓存。脚本内部后续 start_services 的
`--skip-build` 是复用同次刚完成的构建，不是省略上述构建。

原始 JSON、选中诊断、WAV、ASR、Task/文件哈希和完整命令输出保存在本机
`logs/repair-20260908/`（Git ignored），主日志按部署保留在 `logs/swarm-*.log`。
复核命令在仓库根运行，先设置 PYTHONUTF8=1 和 PYTHONPATH 为仓库根：

```powershell
.venv/Scripts/python.exe logs/repair-20260908/inspect_final_progress.py native300 --texts
.venv/Scripts/python.exe logs/repair-20260908/calculate_server_segments.py native300
.venv/Scripts/python.exe logs/repair-20260908/collect_task_milestones.py
.venv/Scripts/python.exe logs/repair-20260908/audit_project_preservation.py
```

供给 A/B 的完整复现命令在前述供给证据页，实际链路脚本为
`real_audio_journey.py`、`run_final_batch.py`、`run_verification_batch.py`、
`run_remaining_acceptance.py`、`run_native300_batch.py`，各次输入 WAV 用内容 hash
关联；运行这些链路脚本会创建真实 Task/文件，应使用保留的专用验收项目。

配置回退使用现有 launcher，在后台 Task 均终态后保留相同项目/data，仅选择
`-NativeEndpointMode server-vad-450` 或原 `semantic-vad`；模型和语速保持上述值。
具体可执行命令如下，未在此步骤清理任何项目/data：

```powershell
$repairConfig = Get-Content -Raw -LiteralPath C:/Users/admin/.jiuwenswarm/config/live-voice-formal-web-validation.json | ConvertFrom-Json
& scripts/live_voice/start_hands_free_demo.ps1 -RuntimeProfile formal-web-validation -ExpectedSourceBranch hx/0812_live_voice_w3 -ProjectPath $repairConfig.project_path -ProjectId $repairConfig.project_id -DataDir $repairConfig.data_dir -InteractionEngine openai-realtime-native -NativeRealtimeModel gpt-realtime-2.1 -NativeAudioSpeed 1.25 -NativeReasoningEffort minimal -NativeVadEagerness auto -NativeEndpointMode server-vad-450 -GenerationInterruption -AllowDirtyProject -RestartExisting -NoBrowser -SaveConfiguration
```

若需撤回最后的保留冲突提示修复，确认工作区干净后 `git revert --no-edit d13c73bb`
生成一个新的本地回退提交，再用上面的 launcher 构建部署。它只撤回该独立模块，
不撤销其他供给/锁/回执修复，不删除数据。出现 Git 冲突时先处理该冲突，不使用
hard reset 覆盖工作区；远端仍不自动推送。

## 尚需的最小后续工作

已有证据关闭的是具体模块修复和受影响检查，以及上述正向/负向真实 Task 边界。
尚未解决：实际首音中位数与真实接单/非终态反馈目标、首 PCM 后 216.729 ms 尾值、
转写及字面文件名漂移、原文件保留的可靠保证、长报告篇幅与稳定收敛、部分查询/调整正向结果。下一步须
分别围绕这些保留的失败样本复现和改动，再复验，不可将它们统称为“只差真人”。

物理阻塞单独存在：需要真实耳机/麦克风/浏览器的连续五轮，以及四个播放阶段的
打断、Stop/Exit 麦克风释放、Voice off 面板刷新与断网恢复。人工脚本已提前放在
`logs/repair-20260908/PHYSICAL_ACCEPTANCE.md`。CLI 每轮新建 P2，合成输入与记录
ACK 不能替代连续真人麦克风消费，也没有设备延迟或扬声器欠载/听感证据。

## 本次本地产品/修复提交

以下20个本地提交未推送，包含一次明确的输入基线集成；随后只提交验收文档。

```text
f2d3cdc7 fix(live-voice): remove prepared pacing drift and diagnostic contention
96750547 fix(live-voice): release Registry lock during notification authorization
ce8d8693 merge(live-voice): integrate supplied Shenzhen repair baseline
aa0df2dc fix(live-voice): wake exact notification poll when Native audio is ready
eaf53820 fix(live-voice): return durable Task acceptance before optional context refresh
ba4f8524 feat(live-voice): expose controlled reasoning effort and confirmed session settings
a8b0c3a0 fix(live-voice): preserve exact foreground and unread event recovery
f45a2c9f perf(live-voice): bind response context and generate one complete business intent
5b0f816d fix(live-voice): request truthful feedback while actual analysis runs
426637c1 fix(live-voice): preserve speech and retire exact recovery owners
992ee916 feat(live-voice): add controlled Native endpoint presets
5cf391d6 fix(live-voice): retain literal artifact paths in delegated instructions
427685f2 fix(live-voice): dispatch explicit file requests without redundant lookup
1f499b8f perf(live-voice): acknowledge admitted work without redundant context refresh
192d2151 fix(live-voice): fail stalled background file reads without applying partial output
082b64a2 fix(live-voice): preserve requested restatements and explicit result facts
90955111 fix(live-voice): retain explicit content in receipt continuations
800235d9 fix(live-voice): report exact adjustment outcome before sealing receipt
2a78ecf9 fix(live-voice): finish background output checks without repeated read cycles
d13c73bb fix(live-voice): reject output conflicts with explicit file preservation
```
