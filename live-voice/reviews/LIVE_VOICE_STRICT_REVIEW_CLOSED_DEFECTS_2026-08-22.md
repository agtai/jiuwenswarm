# Live Voice 严格评审已闭合缺陷台账 — 2026-08-22

> 分支 `codex/live-voice-strict-review-20260819`，HEAD `a6b8d14e7`。
> 88 项确认缺陷中 **37 项已闭合**，严重度分布 **30 高 / 6 中 / 1 低**，
> 由 30 个独立复核修复包、87 个提交完成。剩余 51 项全部未激活。

本文件是 `LIVE_VOICE_STRICT_REVIEW_REPAIR_EXECUTION_2026-08-20.md` §7 台账的可读版本，
按根因分组、逐条展开为四段：**此前**（原来怎么坏的）、**后果**（为什么必须修）、
**修法**（改了什么）、**此后**（现在什么样），并附每个修复包的完整提交列表。

原始缺陷描述出自 `LIVE_VOICE_STRICT_REVIEW_REVALIDATION_2026-08-19.md`。

---

## 闭合条件

每一项的闭合流程是固定的，任何一步缺失都不计入分子：

1. **先复现**：在基线源码上跑候选测试必须 RED，且失败必须是**业务断言**而非 `AttributeError`
   ——后者只证明"新 API 不存在"，不证明"缺陷存在"。
2. **最小修复**：限定在 owner 范围内，不新增产品策略、协议字段或 reason code。
3. **独立复核**：由**没有参与实现的人**执行，复核者自己设计变异体、自己复现实现者的每一条声明，
   不采信报告。
4. **集成方合入**：只有集成方能合入，合入后复跑受影响范围。

Wave 12 起增加一条硬性要求（下称 standing evidence rule）：

> **代码注释里声称的每一条安全性质，必须有一个在该性质被变异掉时会失败的测试。**
> 实现者要自己种入变异、验证变红、再改回，并给出确切输出。

这条规则是在连续三次因同一形状被驳回（SRR-24、SRR-26、SRR-27）之后加进契约的。
根因是：写代码的人知道自己为什么这么写，把理由写进注释就觉得交代过了 ——
**但注释拦不住下一个人把它改掉。**

---

## 一、权威完整性与隐私（12 项）

共同点是系统在某个校验点上信任了不该信任的东西，或者把不该外泄的内容写了出去。
审计要求这一类优先于纯可靠性工作，且每条负向路径都必须零副作用。

### A21 — Agent 客户端日志泄漏用户转写 · HIGH

| | |
|---|---|
| **此前** | `agent_client.py` 只脱敏 `auth_token`，在 INFO 级完整记录 unary 与 stream 的载荷。 |
| **后果** | Live Voice 的用户转写文本与标识符随日志落盘，任何能读日志的人都能看到用户说了什么。 |
| **修法** | 复用通用递归隐私投影器；加上无 hook 的物理类型分类、整图投影预算与严格 UTF-8 预检。 |
| **此后** | 敌意对象、超长标识符、循环引用与孤立代理项都无法到达日志、公开异常内容或传输发送；保留了受支持的 OutputSchema / E2A / legacy 线格式行为。142 焦点 + 353 消费方用例通过。 |

```
SRR-02  ·  10 commits
4567becf3  fix(live-voice): redact agent client payload logs
63a86e203  fix(live-voice): harden agent transport log privacy
34a128db0  fix(live-voice): seal agent privacy error surfaces
2586dc4d4  fix(live-voice): detach agent cleanup failure context
05a0baaff  fix(live-voice): harden agent wire privacy boundary
59fbb8031  fix(live-voice): preserve safe agent wire compatibility
19a604f93  fix(live-voice): bound agent legacy wire projection
a0b4b6bf3  test(live-voice): cover bounded normal wire projection
0e98c018e  fix(live-voice): close agent wire privacy seams
4b08240dc  fix(live-voice): reject invalid UTF-8 wire text
```

### C5 — Outbox 观察未与任务绑定 · MEDIUM（历史否决被推翻）

| | |
|---|---|
| **此前** | `task_store.py` 校验一行 outbox，却把返回的**每一条** observation 都应用了；内部校验只验 observation 自身，不验它与那条 outbox 是否匹配。`ExecutorDeliveryResult` 也只绑定 executor 身份。 |
| **后果** | 一个有故障的 executor 可以用任务 B 的 observation 完成任务 A 的 outbox —— 改了 B，还把 A 标成已投递。**这条原本被判为无效，复核时推翻。** |
| **修法** | 在第一次 Store 写入之前做精确的四字段 Executor-observation 绑定。 |
| **此后** | 真实的 Core 混合观察失败且跨任务零副作用，重开重试与重放均正确；219 个模块用例通过。 |

```
SRR-01  ·  2 commits
ec2f7224b  fix(live-voice): bind outbox observations exactly
c8f858dad  test(live-voice): cover mixed executor observations
```

### B9 — Resolver 权威字段只校验第一个 · HIGH

| | |
|---|---|
| **此前** | `voice_task_bridge.py` 只校验第一个为真的 instruction / token / task 字段。 |
| **后果** | resolver 可以同时返回 instruction 和 confirmation token 而不带 operation，直接绕过 token span 校验 —— 复核复现了一次真实的 pending-token 攻击。 |
| **修法** | 每个有值的字段独立校验，并让 instruction 与 token 互斥。 |
| **此后** | 混合字段与错误 span 均失败，且确认 / Task / Tool / 台账副作用全为零；80 Bridge + 150 registry 用例通过。 |

```
SRR-04  ·  2 commits
6b219bd39  fix(live-voice): validate resolver authority fields
d47ef7e58  test(live-voice): close resolver authority evidence
```

### B10 — 静态 Bearer 认证抛未分类异常 · HIGH

| | |
|---|---|
| **此前** | `StaticBearerAuthenticator` 允许非 ASCII 的配置或候选值，随后 `hmac.compare_digest(str, str)` 抛 `TypeError`。 |
| **后果** | 认证失败以未分类异常的形式出现，而不是一个有类型的认证失败，调用方无法正确处理。 |
| **修法** | 启动时拒绝非 ASCII 配置，候选输入按未认证处理。 |
| **此后** | 两种情况都在比较之前 fail closed，环境工厂零构造，受支持的 ASCII 走 `compare_digest`；101 个模块用例通过。 |

```
SRR-05  ·  2 commits
9b5b9286e  fix(live-voice): reject invalid static bearer input
5a0d04917  test(live-voice): close static bearer evidence
```

### B41 — 开发态 WebSocket 漏脱敏语音文本 · HIGH

| | |
|---|---|
| **此前** | `devWsTrafficPrivacy.ts` 脱敏 `final` 与 `raw` 文本，但漏掉了真正的 `display_text` 与 `spoken_text`，而当时的测试恰好两个都没覆盖。 |
| **后果** | 开发态 WebSocket 会把识别候选与渲染方案里的原文持久化下来。 |
| **修法** | 结构化、畸形与分隔符变体的语音字段一律在持久化之前 fail closed。 |
| **此后** | 包括畸形 JSON 路径在内，原文都不再落盘；严格 TypeScript 33/33、Prettier、`tsc` 与 Live Voice Vite 构建全过。 |

```
SRR-03  ·  2 commits
b200feff7  fix(live-voice): redact websocket speech text
64236924a  fix(live-voice): harden websocket speech redaction
```

### B12 + B13 + B14 — 被取代的 generation 能再次激活 · HIGH

| | |
|---|---|
| **此前** | 三处相关缺陷：progress-generation 准入在容量驱逐时把整个 key 连同 high-water 一起擦掉；高代 P2 替换弹出旧路由却漏掉正常关闭会做的 voice-origin 清理与精确 token 释放；通过闸门的 submit 后来失败时，critical gate 与 generation 条目仍然存活。 |
| **后果** | 一个已被取代的 generation 可以再次激活 —— 复核实测它能**通过后继路由铸出一个可兑付的 `formal` 确认令牌**。 |
| **修法** | 退休标记移进与 P2 fence 相同的保守最大值 Count-Min sketch（碰撞只能 fail closed，精确表仍然优先）；高代替换按精确 commit id 走与正常关闭相同的清理，释放 commit 级闸门证据同时保留后继立即复用的单调输入 fence；确定性失败释放两张精确表与令牌闸门，未知结果与成功派发都保留。 |
| **此后** | 被取代的 generation 永不再激活。**两轮复核**：第一轮驳回，因为释放逻辑在**成功**的默认 Agent 路径上也触发，且 B13 的接受性未被证明；修复后收窄到 task 分支并端到端证明。确定性锁屏障并发、uint64 双侧边界、重启表征与恰好一次订阅证据齐备；161 焦点 + 240 消费方用例通过。 |

```
SRR-20  ·  6 commits
950bb9830  fix(live-voice): fence evicted progress generations
edbed4695  fix(live-voice): drop superseded origins on P2 replacement
10238313d  fix(live-voice): release critical identity on definite submit failure
ec243ab64  style(live-voice): keep the SRR-20 batch lint and format clean
4ee8a278d  fix(live-voice): close the SRR-20 blocking review findings
0a2361f81  test(live-voice): close the SRR-20 evidence gaps
```

### B16 — P3 拒绝路径伪造权威事实 · HIGH

| | |
|---|---|
| **此前** | `_p3_control_manifest` 凭空构造 formal 权威与 runtime 事实，并把它附在未认证、无效、记录缺失的失败上。 |
| **后果** | 拒绝路径反而返回了一个看起来可信的租约和"已观察到的 runtime"，下游据此判断就是错的。 |
| **修法** | manifest 只能由真实观察到的事实构造，未观察到的 owner 一律报 unavailable。 |
| **此后** | 每一条自然语言 P3 拒绝都如实报告权威与 P3 控制不可用，只给出包级 / 无 runtime 的证据。无效 bearer、结构错误、绑定缺失、resolver 失败、重复与并发重放、跨会话、停止与重启探针都保持零禁止副作用；151 registry + 47 真实 AgentServer 路由用例通过。 |

```
SRR-16  ·  1 commit
90865abd4  fix(live-voice): keep rejected P3 manifests unavailable
```

### B36 + L20 + L21 — 前端权威快照能回滚任务副本 · HIGH / MEDIUM / MEDIUM

| | |
|---|---|
| **此前** | 三处前端权威缺陷：`formalTaskControlLeaf.ts` 直接采纳 `task.get` / `task.status` 快照，不校验 attempt、终态与事件头单调性，还把已知事件序号重置为 null；destructive confirmation 先删除持久化 checkpoint、后失效内存记录；legacy `{ok:true,result}` 被接受为 create / cancel / retry 的变更权威。 |
| **后果** | 一个权威快照能把 formal task 副本**回滚**：attempt 回退、身份伪造、终态复活、终态结果被改写。而 journal 删除失败后，`recoverPending` 可以重新认领并**再次授权那个已取消的令牌**。 |
| **修法** | 回滚与复活通过既有的 `validTaskStateTransition` 规则拒绝，不新增策略；取消墓碑在任何 journal 认领或 Gateway 调用之前就让 submit 与 `recoverPending` fail closed，并可重试地结算；legacy 成功保留给查询，变更必须走产品信封。 |
| **此后** | 已消费的事件游标能在"仍描述同一头部"的刷新中存活，不再被重置为 null。复核在重新编译基线后复现全部三个机制（6 条业务断言）；49 焦点 + 418 包级用例通过，唯一那条已披露的挂载面板失败保持不变，typecheck 与构建干净。 |

```
SRR-21  ·  2 commits
155c15b36  fix(live-voice): bind formal task snapshot and mutation authority
b0341f41b  fix(live-voice): fence an unsettled formal task intent cancellation
```

---

## 二、无界生命周期状态导致永久拒绝（8 项）

本次评审最贵的模式：一张只增不减的台账，加上一个"满了就永久拒绝"的上限。
仓库对它有既定答案 —— **释放重状态，但保留一个独立的、有界的防重放 fence**。
执行契约 §2 明确排除普通 LRU：那只是把缺陷推迟到 fence 装满。

标准形状是保守最大值 Count-Min sketch：写入时每行取 `max`，读取时跨行取 `min`；
固定内存、永不驱逐、碰撞只会抬高格子因而只会 fail closed、精确层优先于 sketch、
未记录的 key 读作缺失而非 generation 0。

### A1 — 一致性身份台账 64 条上限 · HIGH

| | |
|---|---|
| **此前** | conformance 实例把 generation / response 身份保留终身，终态回收只清活跃状态、不动那张 64 条的身份台账。 |
| **后果** | 默认 Provider 与产品 TTS 在**第 64 个不同的流之后彻底失去 streaming**，且该 owner 终身不恢复。 |
| **修法** | 不再持有活跃流的身份交出精确条目，只留一个紧凑墓碑：fail-closed 准入位图 + 保守最大值 generation sketch，每实例 1.25 MiB。LRU 只决定谁交出精确条目，**不遗忘任何东西**。Provider 身份预算沿用路由既有的 256 而不是另发明一个数字，并有测试钉住两个常量相等。 |
| **此后** | 两道 fence 只升不降，过期重放仍以原本的确切原因被拒。附带修掉一处继承来的顺序缺陷：被拒绝的 start 会白占一个台账槽位，因为释放跑在一个可能抛异常的时钟读取之前。**两轮复核** —— 第一轮驳回，因为 `RESPONSE_IDENTITY_CAPACITY_EXHAUSTED` 的唯一断言随一个退休的测试被删掉，活的 raise 点无人测试。71 一致性 + 95 Provider + 44 媒体 + 185 网关缝用例通过。 |

```
SRR-24  ·  3 commits
d5559d514  fix(live-voice): release retired conformance identities into a bounded fence
6c742e4e8  fix(live-voice): align the streaming Provider identity budget with the route
05b59e317  test(live-voice): restore the response identity exhaustion oracle
```

### A17 — 合成路由 256 个 binding 墓碑永久保留 · HIGH

| | |
|---|---|
| **此前** | 合成路由永久保留 256 个 binding 墓碑，且容量耗尽时抛出裸失败，绕过正常的 batch-eligible 回退。 |
| **后果** | 产品 TTS 在每个通道 256 个流之后死掉。这是评审从 A1 里拆出来的**第二道限制** —— 只修 A1 并不能让端到端真正解除。 |
| **修法** | 有界身份退休 + 紧凑墓碑（准入位图 + 保守最大值 sketch）；容量耗尽改为返回相邻两堵墙已经在用的那个有类型的 batch-eligible 结果。**没有新增任何 reason code**——新增就是协议变更，必须停下来重新定范围。 |
| **此后** | 超过 256 个流后产品正常回退而不是 handler 失败，过期 binding 仍被 fence 拦住。复核通过构造"只含改动一"的反事实源码树证明两处改动正交，强制制造完整摘要碰撞确认 fence 只会 fail closed，并实测：只修 bindings 会让另一张表在 5000 流时涨到 5000 条。49 焦点 + 1002 网关用例通过。 |

```
SRR-25  ·  2 commits
7deae50a6  fix(live-voice): retire streaming synthesis route bindings under a bound
76817c34c  fix(live-voice): fall back to batch when route identities are exhausted
```

### A25 — P3 确认容量跨重启永久耗尽 · HIGH

| | |
|---|---|
| **此前** | `p3_confirmation.py` 把每一行 SQLite 记录都算进 4096 上限，且只标记"已消费"，从不删除。 |
| **后果** | 已消费与已过期的确认永久占用容量，**破坏性操作确认跨重启永久不可用**。 |
| **修法** | 在准入之前事务性地压紧已消费 / 已过期的重记录，只保留策略真正需要的重放数据。 |
| **此后** | 已消费与已过期的行回收容量、活跃行不回收；精确的保留重放与稳定过期仍然如实，被驱逐的令牌永不授权，并发重开的 issuer 无法超过容量，清理或插入失败会回滚而不留部分回收，全部禁止的 Task 变更保持为零；45 主用例 + 349 受影响用例通过。 |

```
SRR-17  ·  1 commit
09d2239ff  fix(live-voice): reclaim P3 confirmation capacity
```

### A13 — 已接受的 commit 占满 128 槽台账 · HIGH

| | |
|---|---|
| **此前** | 容量驱逐会移除已完成的 P2 操作，但退休逻辑只处理 unknown 状态的 commit，不处理 accepted 的；关闭路由与活跃路由关停走的辅助函数同样留下 accepted commit。 |
| **后果** | 反复"成功提交任务来源 → 不做 P3 create 就关闭路由"会在 registry 运行期内填满 128 个 accepted 条目。 |
| **修法** | 被放弃的来源保留一个有界的、按次数计的迟到创建宽限期；过了宽限，最老的通过既有的精确 commit-id 退休交出重状态，紧凑重放 fence 仍能拒绝它。宽限期是 registry 全局的，与它保护的那张共享 128 槽台账相匹配。 |
| **此后** | 同包附带、仅记入 §6.1 路由项：被取代的身份改在**路由重新发布时**退休。复核确认这是对既定方向的**正确偏离** —— 关闭不该退休，因为一个 accepted 来源合法地比关闭活得更久（P3 create 还要用）——并且是**完整的**偏离，因为整个文件只有一处 `_p2_routes[key]` 赋值，三条移除路径都汇回它。复核真跑了 128 路由耗尽，并独立探测中途退休场景确认"至多一次"仍成立；167 焦点 + 240 消费方 + 2061 live_voice 用例通过。 |

```
SRR-23  ·  2 commits
323e38dd5  fix(live-voice): bound abandoned composition origin lifetime
1c860f980  fix(live-voice): retire superseded origins at route republication
```

### A15 — P2 交互租约无上限无终态回调 · HIGH

| | |
|---|---|
| **此前** | `_leases` 既没有上限也没有终态回调，只有同一个 key 的更高 generation 才会移除一个已关闭的租约。 |
| **后果** | 那个更高 generation 可能永远不来，于是已关闭的租约无限累积。 |
| **修法** | 在终态通知时释放重租约，generation 存进有界墓碑。**FAILED 的拆除故意保留租约** —— 那个 runtime 确实没有被回收，拒绝一切后继才是 fail-closed 的真相。 |
| **此后** | **两轮复核。**第一轮驳回，因为 uint64 饱和钳位是 **fail-open** 的：饱和的格子报出低于真实 generation 的 fence，于是过期重放被放行并分配了新 runtime；而且"保守最大值"这条不变式**没有 oracle** —— 语料全用同一个 generation，`max` 与直接赋值不可区分。修复保留顶格值作饱和哨兵、读作无界 fence（有限整数无法界定无界 generation），并加了共享格排序 oracle 与正向对照。七个变异体（含哨兵比较的 off-by-one）被行为断言杀死。同包附带、仅记入 §6.1：该文件自身测试的墙钟 flake，改为在急切任务调度下跑回滚使超时结构性不可达，靠注入诊断出的停顿而非重复运行来证明。56 焦点 + 274 消费方用例通过。 |

```
SRR-26  ·  3 commits
e10a433e9  fix(live-voice): release closed P2 interaction leases into a bounded fence
6ea9a2bba  test(live-voice): settle the P2 rollback tests without the wall clock
8ce7a3645  fix(live-voice): fence saturating P2 generations closed instead of open
```

### A6 + B4 — 关键通知预留从不释放，且一次异常杀死消费者 · HIGH / MEDIUM

| | |
|---|---|
| **此前** | `_critical_keys` 同时是唯一性台账和容量计数器，且从不释放；publication 异常会逃出唯一的 bridge consumer；progress 没有独立终态配额。 |
| **后果** | 一次重复或一次配额耗尽就能**杀死后续全部 Agent / progress 消费**。而那个逃逸的违规还会让拆除跳过 Harness 与 CR 的关闭。 |
| **修法** | 容量改由排队条目计量、两条移除路径都归还；释放的身份进入按 lane 分的精确有界墓碑，只有被墓碑驱逐的才折进保守成员 sketch；progress 终态获得独立预留。publication 失败被记为可归因的诊断而不是终止长生命周期的 consumer。 |
| **此后** | 驱逐永远不会丢掉 fence，碰撞只能拒绝一个从未发布过的身份；progress 终态不再能饿死呈现或终态投递；拆除得以完成关闭原先被逃逸违规跳过的 Harness 与 CR。复核复现六条业务 RED，确认实现者自己声明的"另两个测试是 API 缺失而非缺陷复现"属实，并杀掉六个定向变异体（含一个普通 LRU 变体）；107 焦点 + 487 消费方用例通过。 |

```
SRR-22  ·  1 commit
935a4f74e  fix(live-voice): separate critical reserve capacity from replay identity
```

### B42 — 控制命令台账无界，且保留原始异常与 traceback · HIGH

| | |
|---|---|
| **此前** | 六张 barge / cancel 的指纹、结果与错误表没有生命周期容量，且保留**原始 `Exception` 对象与 traceback**；队列的 `control_capacity` 并不约束已完成的命令。 |
| **后果** | 已完成的控制命令在 loop 的整个生命周期里累积。更严重的是隐私 —— 复核实测：**用户转写、主体身份与呈现内容通过 traceback 帧局部变量到达了一个被重放的异常**。这与 SRR-02 / A21 关掉的是同一个内容暴露家族。 |
| **修法** | 六张表变成两张有界精确台账，背后是一个共享的 fail-closed 重放 fence；保留的失败只留稳定的 code、reason 与 message，原始异常对象、traceback 与 cause 链全部丢弃。分类使用物理类型同一性，绝不对无法识别的对象调用钩子。C3 是 B42 的审计 ID 别名，随之关闭。 |
| **此后** | 被驱逐的标识符永不再执行。**两轮复核**：源码自始至终是对的，第一轮驳回纯粹因为它自己的变异测试留下六个存活体，其中包括那条中心隐私声明 —— 把 `type(x) is C` 改成 `isinstance` 就能悄悄重开它，而安全类的**子类**能带着攻击者文本原样重放。修复是纯加测试，并额外把整个投影所依赖的隐含契约显式化（三个违规家族携带静态消息），做法是对包内全部 88 个构造点做 AST 遍历。53 焦点 + 168 消费方用例通过，源码零 diff。 |

```
SRR-27  ·  3 commits
808d6cd4d  fix(live-voice): bound the conversation loop control command ledger
bae5fa5b3  fix(live-voice): keep only content-free control failure facts
799c6b407  test(live-voice): pin the SRR-27 control-command safety properties
```

---

## 三、取消、关停与后继顺序（10 项）

审计给出的共同模式很直接：**发布一个 generation fence，在 `finally` 里结算每一个自己拥有的
子任务，保留业务结果，并在总超时到期时保留清理真相。**
这一类里最常见的坏法是"第一个错误跳过后面全部"。

### A2 + B2 — 已入队终态时取消，Provider 流永不关闭 · HIGH / MEDIUM

| | |
|---|---|
| **此前** | 取消时先调 conformance、后做本地退休。如果 COMPLETED / FINAL 已入队但尚未消费，就会抛 `SYNTHESIS_ALREADY_TERMINAL` / `RECOGNITION_ALREADY_TERMINAL`。识别侧同理，且完成路径已经关掉了 socket。 |
| **后果** | Provider 流与传输的关闭、本地退休**永远到不了**，敏感转写与 PCM 队列滞留，而路由把这次取消失败吞掉了。**当时的活跃流取消测试根本没覆盖这个竞态。** |
| **修法** | 把本地终态当作幂等退休处理：释放敏感转写 / PCM 队列、清空 `partial_text`、收敛会话与传输，**不再发一次 Provider 取消，也不改写终态真相**。活跃取消路径保持不变，未知、过期、错代与已退休的引用仍然拒绝。 |
| **此后** | 出队与取消、重复取消在一次同步认领上线性化，只有一个赢家报告成功；取消发生在退休中途时，留下的是一个真正 pending 的保留 owner，而不是伪造的完成；provider 关闭在普通、取消与进程控制失败下继续清理邻近会话、传输、队列、映射与 owner，同时保留按时间顺序的首个失败真相与无内容身份。94 Provider + 155 一致性 / 路由用例在 asyncio debug 下通过。 |

```
SRR-10  ·  4 commits
ea55258ff  fix(live-voice): retire queued terminal speech
8ecd38267  fix(live-voice): own terminal speech retirement
90a5f17ad  fix(live-voice): retain terminal dequeue retirement
b5e6dd6e7  fix(live-voice): settle terminal retirement failures
```

### A7 — 五个关停 owner 共用一个 try · HIGH

| | |
|---|---|
| **此前** | 关停把 bridge、consumer、harness、conversation runtime、notification cleanup 五个 owner 包在**同一个 `try`** 里。 |
| **后果** | 第一个错误跳过其后每一个 owner —— 该关的没关，该结算的没结算。 |
| **修法** | 改成有序、各自独立守护的阶段，聚合失败并保留权威的那一个；拆除失败仍然交出 close-drain 租约而不是把它搁浅。 |
| **此后** | **三轮复核，第一轮之后全是纯加测试，没有任何一轮在源码里找到缺陷。**后两轮找到的是模块在自己 docstring 里声称、却无任何测试守护的性质。这些性质只在敌意注入下可达，但都只有一行之遥 —— Ruff 会主动报那三处守卫所需的 `BLE001` 抑制，所以把 `BaseException` 改窄成 `Exception`、或把 `type(x) is str` 改成 `isinstance`，都是很平常的后续编辑。**其中一条改窄会让 A7 缺陷本身复活**：名字查找从它所在的 guard 里抛出去，后面的 owner 一个都不跑。127 焦点 + 373 相邻用例通过，全 live_voice 2142 通过。 |

```
SRR-28  ·  4 commits
51a501339  fix(live-voice): isolate the conversation runtime shutdown phases
9a33b292b  test(live-voice): pin the SRR-28 teardown owner properties
4b1d4de28  test(live-voice): pin the SRR-28 claimed teardown safety properties
deb805e0d  test(live-voice): pin the teardown guards a narrowed except still escapes
```

### A8 + B6 — 清理失败覆盖业务终态，保留清理永不超时 · HIGH / HIGH

| | |
|---|---|
| **此前** | Harness 可以先设好正确的 completed / cancelled 业务结果，然后在 `aclose()` 抛错时把它**覆盖成 FAILED**；而保留清理会永远重复五秒一轮的切片。 |
| **后果** | 一次清理失败就抹掉了真实的业务终态；一个永不返回的 `aclose` 能无限期阻塞终态发布。 |
| **修法** | 业务终态真相与流清理处置分开记录，只在没有业务结果时才创建 FAILED；设总清理截止时间，把未完成的工作移交给一个保留清理 owner，并发布准确的 pending / unknown 清理真相。 |
| **此后** | 已知的 completed / cancelled 真相能在清理失败中存活，unknown + 失败才变 failed；公开 close 恰好一次地接管被放弃的流清理，在被阻塞时保持 pending，且只移除已结算的放弃记录；真实的终态 owner 取消得以传播，不再伪造终态 / `_END`。99 Harness + 79 消费方用例与 10 轮竞态探针通过。 |

```
SRR-06  ·  8 commits
a9e3d6ab8  fix(live-voice): retain harness cleanup truth
333280d16  fix(live-voice): fence settled round cleanup cancel
da7ef17db  fix(live-voice): retain harness terminal ownership
076b098ee  fix(live-voice): retain harness owner before startup
ab4500c93  fix(live-voice): retain general awaitable cleanup
ba9456b6a  fix(live-voice): classify retained cleanup cancellation
85ef62cbe  fix(live-voice): preserve terminal owner cancellation
5affa2c8c  fix(live-voice): adopt abandoned round cleanup
```

### A20 — Gateway 关停线性，一个异常跳过全部 · HIGH

| | |
|---|---|
| **此前** | Gateway 关停是线性的，`web_channel.stop()` 的一个异常会跳过所有其他通道、调度器、心跳、转发、客户端与重启清理。 |
| **后果** | 一个通道停止失败，整个 Gateway 的关停链就断在那里。 |
| **修法** | 独立守护的有序阶段，尝试每一个 owner 并聚合错误；重启只在必需的安全边界之后进行。动态 owner 身份（飞书 / 小艺）改在**注册时**保留，不再依赖可能失败的关停期发现。 |
| **此后** | 保留按时间顺序的首个失败与调用方取消真相，公开诊断保持无内容，失败清理会阻断重启。描述符 / 进程控制、snapshot+pop+unregister、仅注册表、敌意异常与干净重试五组矩阵全过；90 关停 + 66 ACP 生命周期用例通过。这是 A7 的最近先例。 |

```
SRR-08  ·  8 commits
cf2d1a795  fix(gateway): complete ordered shutdown after failures
e12f9fa8e  fix(gateway): harden shutdown failure diagnostics
7174f44fe  fix(gateway): close shutdown privacy and cancellation gaps
5d1638880  fix(gateway): preserve shutdown ownership order
be3897498  fix(gateway): retain registry-only shutdown owners
e567c2970  fix(gateway): classify shutdown failures without hooks
9f78f1642  fix(gateway): retain dynamic owners before shutdown
5aa2bb18c  fix(gateway): retain dynamic owners at registration
```

### A16 — 媒体叶子的 post-parse 发送在清理之外 · HIGH（部分修复的残留）

| | |
|---|---|
| **此前** | attach 与 receive 边界的发送已有清理处理，但 **post-parse 的 detach 发送与二进制 ACK 在它之外**。 |
| **后果** | 取消会关闭会话，却可能留下 socket、子任务和清理预留。 |
| **修法** | 把预留之后的整个叶子放进一个幂等的外层 `try/finally`。 |
| **此后** | 在四种发送各自阻塞时分别取消，都能关闭确切的会话与 socket 并结算 speech / EOT / 清理归属，且不替换主失败；只剩下边界之前合法的音频 / ACK 副作用，后继路由仍然可用；134 叶子 / 注册用例在 asyncio debug 下通过。 |

```
SRR-15  ·  3 commits
58121cb70  fix(live-voice): settle media leaf send cancellation
0644edb14  fix(live-voice): close media post-parse boundary
75b26f7fc  fix(live-voice): settle media descriptor cancellation
```

### B7 — 释放旧 commit 误伤后继授权 · HIGH

| | |
|---|---|
| **此前** | 释放一个旧 commit 时，会**无条件**弹出该交互的活跃 clarification 与 authorization 索引，哪怕它们已经属于一个后继 commit。 |
| **后果** | 后继 commit 的授权被上一个 commit 的释放动作误伤。 |
| **修法** | 只有当前映射的 ID 与被释放的确切 ID 相等时才弹出。 |
| **此后** | 两种顺序以及一个确定性 RLock 竞态下，后继的澄清与授权都得以保留，旧权威零副作用；60 个模块用例通过。与 B13 的清理配对。 |

```
SRR-09  ·  2 commits
4f62a0d82  fix(live-voice): preserve successor token authority
31dec8c7c  test(live-voice): prove successor token release ordering
```

### B24 — 路由存了调用方自己的 task · HIGH

| | |
|---|---|
| **此前** | 合成路由把**调用方自己的 WebSocket / RPC task** 存成了它的选择或打开工作。 |
| **后果** | 关闭或后继会直接取消它 —— 也就可能杀掉整个连接请求任务。 |
| **修法** | 工作记录改为携带一个事件、一个首因闩锁，以及**只有 owner 自己创建的 task**；取代时发布原因、不取消任何属于调用方的东西，内部信号翻译成既有的 `RESPONSE_SUPERSEDED` / `OWNER_CLOSED`，不出模块。被取代的 open 在被取消的任务内部结算自己的 Provider 流，于是取消方加入那次清理而不是与 close 的 drain 竞争。 |
| **此后** | 零新增 reason code、fallback action 或协议字段 —— 复核用 **AST 级公开 API diff** 证明，并穷举确认没有任何残余路径能取消调用方 task，同时确认 SRR-25 的两条性质仍然存活。调用方取消仍然权威：把它改成取代的变异体杀死了 12 个测试。15 个变异体，12 个被杀，3 个证明为等价的防御守卫；54 焦点 + 232 相邻用例通过。 |

```
SRR-29  ·  2 commits
8bbdc07cc  fix(live-voice): supersede synthesis route work, never its caller
8f3396c1c  test(live-voice): pin the synthesis route caller-task properties
```

### L7 — close() 对外部 FAILED 提前返回 · MEDIUM（部分修复的残留）

| | |
|---|---|
| **此前** | `_run` 已经会关闭自己的 source，但 `close()` 对任何外部引发的 FAILED 都提前返回。 |
| **后果** | 一次失败的 drain 能结算业务原因，而 worker 还停在它先前发起的读上 —— source 挂着，**再无重试路径**。 |
| **修法** | 提前返回只在 source 与 worker 都已结算时适用，否则运行幂等清理并保留已结算的原因。start 尝试的那一刻起就把 source 算作已打开，所以"附着后失败"的 source 仍能被后来的 close 够到。同一个 worker 现在容纳自己的后台失败而不是变成一个无人认领的任务，同时调用方取消仍然传播。 |
| **此后** | **三轮复核，第一轮之后全是纯加测试。**第二轮的驳回值得记：套件里有个用例名字就叫 `..._joins_the_worker_on_close`，**删掉 join 那步它照样通过** —— 它用的替身在 `close()` 之前就已释放停泊读。名字承诺了 join，测试没兑现。第三轮用 **A/B 直证**（同一棵树、同一批变异体、只换测试文件）证明改造没有丢失任何既有杀伤力：两个存活体翻转为被杀，而每一个既有杀手名单逐字未变。54 焦点 + 410 相邻用例通过。 |

```
SRR-30  ·  5 commits
efda829ce  fix(live-voice): close the progress bridge on an unsettled worker
de297b114  fix(live-voice): contain the progress worker background failure
7d607f6ad  test(live-voice): pin the progress worker cancellation and detach properties
1fa519a09  test(live-voice): pin the join and the containment breadth close claims
30a6fe962  test(live-voice): guard the join case against hanging instead of failing
```

---

## 四、阻塞工作下的响应性（2 项）

CPU、SQLite 与文件系统工作不得跑在事件循环或进程级产品锁下面。
这类缺陷不产生错误结果，只是让打断、取消和心跳在最需要它们的时候失灵。

### A4 — 重采样循环阻塞事件循环 · HIGH

| | |
|---|---|
| **此前** | `batch_speech.py` 里纯 Python 的采样循环被异步合成**同步调用**。 |
| **后果** | 大块 PCM 结果会阻塞打断、取消与心跳 —— 用户说"停"的时候系统正忙着算音频。 |
| **修法** | 把有界的批量音频重采样移出事件循环线程，且不改变 DSP 字节或有类型的失败。 |
| **此后** | 确定性的心跳 / 取消屏障、迟到的 worker 完成与错误容纳都已验证；61 模块 + 14 消费方用例与重复调度探针通过。 |

```
SRR-11  ·  1 commit
c255ddcae  fix(live-voice): offload batch audio resampling
```

### A11 — 异步 drain / reconcile 在事件循环上调同步 SQLite · HIGH

| | |
|---|---|
| **此前** | 异步的 `drain_outbox_once` 与 `reconcile` 在事件循环线程上调用同步 SQLite store 方法。 |
| **后果** | 一次 200 ms 的 store 停顿就会延迟心跳与打断控制。 |
| **修法** | 单个 store 操作走既有的阻塞运行器，异步 executor 调用留在自己的 loop 上。 |
| **此后** | 一个保留 owner 能在反复的调用方取消中存活：首次调用方取消胜过普通的 worker / release 失败，进程控制与内层取消仍然权威，精确认领要么被释放要么可持久恢复，重启与后继投递仍是一次性的；12 个 asyncio-debug 用例 + 231 Core + 101 组合用例通过。 |

```
SRR-13  ·  3 commits
0c7db2994  fix(live-voice): isolate task store from event loop
870cb993f  fix(live-voice): retain task store through repeated cancel
73b308362  fix(live-voice): preserve retained store cancellation
```

---

## 五、终态真相、时序与诊断（5 项）

这几条不属于前面任何一类，但都关乎系统对外说的话是否属实 ——
终态标成什么、副作用在校验之前还是之后发生、错误信息读不读得懂。

### A12 — 用户取消被记成系统中断 · HIGH

| | |
|---|---|
| **此前** | `project_code_executor.py` 观察到持久化的 `cancel_requested`、发出了取消确认，却以 **INTERRUPTED** 结束 —— 而紧邻的取消路径用的是 CANCELLED。 |
| **后果** | 用户主动取消被记成了系统中断，重试语义因此不同。 |
| **修法** | 推导出明确的用户取消原因：持久化取消与取消确认都必须结算为 CANCELLED，INTERRUPTED 留给关停与失去归属。 |
| **此后** | journal 写入与内存信号之间加了屏障，断言恰好一个 CANCELLED 终态且重试语义正确；隔离补丁零副作用，精确重放与重开正确，100 个模块用例通过。 |

```
SRR-14  ·  1 commit
bafab7c91  fix(live-voice): preserve persisted user cancellation truth
```

### A3 — 转写规范化在签名之后 · HIGH

| | |
|---|---|
| **此前** | `batch_speech.py` 用 `text.strip()` 判断非空，却发布并签名**原始的带空白文本**。 |
| **后果** | receipt 校验在捕获身份已经被预留**之后**才拒绝它 —— 副作用已经发生了。 |
| **修法** | 在 Provider 边界规范化一次，事件、哈希与 receipt 用同一份文本。 |
| **此后** | ASCII 与 Unicode 前后空白都产生同一个规范 receipt，精确的操作重放不会再次调用 Provider；拒绝零副作用，并发与迟到重放以及真实的 Gateway / 产品消费方都已验证；58 模块 + 18 消费方用例通过。 |

```
SRR-07  ·  1 commit
ec43b0423  fix(live-voice): canonicalize batch transcripts
```

### A23 — Web 操作在持久化之前插入 pending 条目 · HIGH

| | |
|---|---|
| **此前** | `productWebActivation.ts` 在持久化冻结与 checkpoint **之前**插入 pending 的 submit / barge / presentation-ACK 条目。 |
| **后果** | UTF-8 字节校验或 journal 失败会留下一个没有结果的幽灵条目，**把重试堵死**。 |
| **修法** | 先冻结并做持久化 checkpoint，再做 pending 保留。 |
| **此后** | 多字节超限与 checkpoint 失败都不留幽灵权威，也不产生网络 / Agent / Task / 媒体 / 呈现副作用，随后的有效操作能成功；精确的并发与重启重放仍是一次性的，128 条边界会保留旧重放直到后继被持久接纳。90 焦点用例与完整的候选 / 基线 Integrated Web 对比通过。 |

```
SRR-18  ·  1 commit
3c85728fd  fix(live-voice): checkpoint Web operations before retention
```

### A18 — 调度使用惰性 Agent 实例 · HIGH

| | |
|---|---|
| **此前** | 调度的 create / run 使用惰性的 `agent.get_instance()`，冷启动时它可能是 `None`。 |
| **后果** | 在持久化与触发之前拿到空实例，调度或任务的副作用已经发生了一半。 |
| **修法** | 改用 `await agent.ensure_instance()`，并在任何调度或任务副作用之前校验它。 |
| **此后** | 冷创建与冷运行会等待既有的 Agent singleflight 再固定目标或做变更；异常与 None 都 fail closed，重试能成功且无陈旧副作用。28 handler / DeepAdapter + 212 受影响用例通过。 |

```
SRR-12  ·  1 commit
3f746fd48  fix(live-voice): initialize scheduled execution agents
```

### L14 — 调度错误文案乱码 · LOW

| | |
|---|---|
| **此前** | auto_harness 的两处用户可见调度错误里是乱码。 |
| **后果** | 用户看到的是一串不可读的字符，无法判断自己哪里做错了。 |
| **修法** | 两处都换成确切的 UTF-8 中文文案，沿用既有的 `TASK_SCOPE_REQUIRED` 错误码。 |
| **此后** | 八个无效范围的用例证明 Store、调度器与保留执行上下文零副作用；auto-harness 全量 129/129 在 Tier-1 仅字面量边界下通过。 |

```
SRR-19  ·  1 commit
7f9dac8fe  fix(auto-harness): repair schedule scope message
```

---

## 剩余 51 项

| 分组 | 数量 | 缺陷 ID |
|---|---:|---|
| 协议 / 状态 / 兼容性 | 29 | B1、B3、B5、B8、B19、B20、B22、B28、B29、B30、B33、B34、B35、B40、L1–L4、L6、L8–L13、L15–L17、L22 |
| generation / 后继 / 权威清理 | 7 | B18、B32、B37、B38、B39、D2、L19 |
| 取消 / 拆除 / 保留清理 | 6 | A19、A22、B21、B23、D1、D3 |
| 容量 / 生命周期 / 重放 | 5 | A5、A9、B11、L5、L18 |
| 事件循环 / 锁 / 文件系统 | 4 | A14、B15、B25、B27 |

队列算术 `7 + 6 + 5 + 4 + 29 = 51`。按历史家族分布为 **5 个 A、25 个 B、18 个 L、3 个 D**。

`B11` 因 `project_code_executor.py` 在 `agtai/hx/0812_live_voice_w3` 上并行修改而排除；
`A22` 因 `productWebActivation.ts` 在 `agtai/hx/0819_live_voice_p1p2` 上并行修改而排除。

---

## 流程本身的账

后期加进契约的 standing evidence rule 把这一轮的每个修复包都至少多拦了一轮，
而**每一次拦下的都不是代码错误，是证据缺口**：源码在第一次提交时就已正确，
六份独立复核报告没有一份在源码里找到缺陷。

但它拦下的东西不是零。其中两条被证明能**让已修好的缺陷复活**：

- 把 SRR-28 的 `except BaseException` 改窄成 `except Exception` —— A7 缺陷本身复活，
  后续 owner 一个都不跑，124 项测试全绿。
- 把 SRR-30 的提前返回上移三行跨过 join —— L7 的核心不变式失效，463 项测试全绿。

而 Ruff 恰好会主动报 `BLE001`，提示下一个人去"清理"前者。这两条不是稻草人。

### 一个出现三次的形状：名字承诺 ≠ 实际守护

| 用例名承诺 | 把机制删掉后 | 为什么还绿 |
|---|---|---|
| `..._joins_the_worker_on_close` | 删 `await shield(worker)` | 替身在 `close()` **之前**就释放了停泊读 |
| `..._does_not_cancel_detach_cleanup` | 删 `shield(close_task)` | 只断言终局 `close_calls == 1`，分不出"清理被保留"和"清理被取消后重做" |
| `..._cannot_escape_the_teardown_guard` | `except BaseException` → `except Exception` | fixture 的敌意类只抛 `RuntimeError` |

共同机制：**名字描述的是机制，断言检查的是终局状态，而终局状态在"机制生效"和
"机制没生效但殊途同归"两种情况下相同。**

诊断办法很简单 —— 把名字点到的那个机制删掉，看这个用例死不死。不死就是名字没兑现。

### 另一条值得记的：敌意对象也会攻击测试框架

SRR-28 的复核给出的修复配方按字面实现会**炸掉整个 pytest session**：
让敌意异常逃逸到 pytest 的失败渲染路径后，`saferepr` 会再读一次 `__name__`，
`_format_repr_exception` 的兜底再读一次，直接 `INTERNALERROR`，127 个用例只跑完 117 个。

这类用例必须在用例内先把逃逸捕获成局部变量再断言，让失败 traceback 里不出现那个实参。
