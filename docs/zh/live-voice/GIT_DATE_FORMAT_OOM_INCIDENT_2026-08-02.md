# Live Voice V0 Gate 3：Git 日期格式 OOM 与重复失败放大事故复盘

- 事故日期：2026-08-02
- 事故范围：V0 Gate 3 Attempt 1 / Turn 3
- 失败候选：`d4c3e32aa34a4d26b346cdf0396788d39930cd6b`
- 当前修复候选：`ee2896a4afb186e693c720476b6de10797e66f72`
- 当前状态：`d4c3e32a` 的 Gate 3 明确 `FAIL`；`ee2896a4` 的 focused hotfix tests 已通过，但完整 Gate 0/1 和新的 Gate 3 尚未重跑，V0 仍未 Released
- 对应决策：[DECISIONS.md](DECISIONS.md) 的 D-037

## 1. 执行摘要

这不是单纯的“语音把一个字听错了”，也不是单纯的“Git 出了一个错误”。完整事故链是：

```text
用户口述日期要求
→ Web Speech 把“年月日”识别成“念月日”
→ 模型选择带中文字面量的 Git 日期格式命令
→ Git for Windows 在该命令上异常扩张内存并 OOM
→ 工具把确定性失败返回给 Agent
→ Agent 没有换策略，连续执行同一命令
→ JiuwenSwarm 当时没有及时熔断
→ 一次平台兼容性失败被放大为 11 次 tool call / 10 次相同失败
```

直接触发 Git OOM 的命令是：

```text
git log -1 --format=%ad --date=format:'%m月%d日'
```

可见错误是：

```text
fatal: Out of memory, realloc failed
```

该命令在 Git for Windows `2.47.1.windows.2` 上可以脱离 Agent 稳定复现；`--date=short` 和只含 ASCII 的格式立即成功。因此，直接故障位于 Git for Windows 的非 ASCII 日期格式处理路径，不是仓库过大，也不是机器原本内存不足。

但 JiuwenSwarm 对事故的放大负有独立责任：同一个用户 Turn 只有一次 `chat.send`，系统却允许模型在相同失败后不断重试。现有通用 Circuit Breaker 当时默认关闭，即使打开，默认阈值对单次高资源失败也过晚。

当前 `ee2896a4` 已补上最小止损：同一 invoke 中，同工具、同语义参数、同完整失败签名连续出现时，前两次允许模型自我恢复，第 3 次完成后只 force-finish 一次，从而阻止顺序执行第 4 次。它解决的是“重复失败放大器”，没有修复 Git，也没有给任意工具子进程提供硬超时、内存/CPU 上限或进程树隔离。

## 2. 发生了什么

### 2.1 Gate 3 前两轮

- Turn 1 正确返回 `d4c3e32a`。
- Turn 2 正确返回提交标题 `fix(live-voice): keep V0 agent runs git-clean`。
- 两轮都通过真实只读 Terminal Tool，不是预设答案。

### 2.2 Turn 3

计划语义是查看最新提交日期。真实 ASR 把“年月日”转写为“念月日”，模型随后生成包含中文“月/日”的 Git 日期格式命令。

Git 子进程返回 OOM 后，模型没有改用 `--date=short`、ASCII format 或其他等价查询，而是在每个失败结果后再次选择同一命令。最终观察到：

- 1 次用户 `chat.send`；
- 11 次 `tool_call`；
- 10 次相同失败 `tool_result`；
- 0 次 Turn 3 `chat.final`；
- 第 11 次调用在途时，由 `chat.interrupt(intent=cancel)` 人工终止；
- 单个异常 Git 子进程曾达到约 8.5 GB Working Set / 49 GB Private Memory；
- 子进程退出后资源恢复；
- 候选工作区仍为 clean，没有产生仓库修改。

这组连续 10 Turn 验收必须整体记为 `FAIL`，不能从 Turn 4 接着累计，也不能覆盖原失败记录。

## 3. “念月日”为什么不是直接异常

“念月日”只是 ASR 输出给模型的自然语言文本，不会直接传给 Git，也没有直接触发 Python 或 JiuwenSwarm 异常。

它在事故中的作用是改变了模型看到的上下文，并与“只回答日期”的要求一起促成了一个脆弱命令选择。但需要避免两个错误结论：

1. **不能说“念月日直接让 Git 崩溃”**：Git 实际收到的是模型生成的 `--date=format:'%m月%d日'`。
2. **不能说只要 ASR 正确就绝不会发生**：即使识别为“年月日”，模型仍有可能主动选择同一中文格式。ASR 偏差是诱因，不是该 Git OOM 的必要或充分条件。

因此，后续应继续处理 ASR 关键动作词和技术词准确率，但不能用“把验收口令换个说法”代替工具执行保护。

## 4. 触发的到底是什么异常

从 JiuwenSwarm 看到的是 Terminal Tool 的确定性失败结果：Git 子进程以非零退出码结束，并在 stderr 返回 `fatal: Out of memory, realloc failed`。这不是 Git 仓库内容错误，也不是正常的“日期参数不支持”提示。

当前证据最一致的底层机制如下：

```text
Git DATE_STRFTIME 日期模式
→ strbuf_addftime(...)
→ C Runtime strftime(...)
→ 本地环境下持续返回 0
→ Git 把 0 当成“缓冲区仍不够”并继续扩容/重试
→ 缓冲区反复翻倍
→ xrealloc 最终 OOM
```

Git 的日期格式路径会把自定义 `format:` 交给 `strbuf_addftime`。该实现调用 `strftime`；当返回值为 0 时继续扩大缓冲区。Microsoft CRT 文档同时说明，`strftime` 在缓冲区不足时返回 0，非法参数路径也可能返回 0。若非 ASCII/locale 转换在当前 Git for Windows 环境中持续返回 0，而不是在扩容后成功，Git 的重试就可能演变为无界内存增长。

### 证据边界

- **已确认**：问题可由上述命令在指定 Git for Windows 版本独立复现；ASCII/short-date 对照成功；内存异常增长；Git 最终 OOM。
- **源码支持的高概率解释**：`strftime` 持续返回 0，`strbuf_addftime` 持续扩容。
- **尚未确认**：具体是 Microsoft CRT、MSYS/locale 转换还是 Git for Windows 某一适配分支导致持续 0；本次没有用调试器记录每次 `strftime` 的返回、`errno` 和 locale 内部路径。

因此本文把它称为“Git for Windows 非 ASCII 日期格式路径的可复现 OOM”，不把尚未完成的底层定位写成已经确认的单一 upstream defect。

## 5. 责任怎么划分

| 层 | 事故中的作用 | 结论 |
|---|---|---|
| Web Speech / ASR | 把“年月日”识别成“念月日”，增加语义偏差 | 诱因与产品质量问题；不是直接 OOM 根因 |
| 模型 / Agent 决策 | 生成脆弱的非 ASCII Git format；失败后没有改策略 | 直接触发条件之一；模型输出永远不能被当成安全命令保证 |
| Git for Windows | 对该命令异常扩张内存并 OOM | 直接执行层故障；脱离 Agent 仍可复现 |
| JiuwenSwarm Agent loop | 接收确定性失败后连续再次执行相同工具和参数 | 事故放大器；当前 D-037 hotfix 已针对顺序重复失败止损 |
| JiuwenSwarm Tool/Executor 边界 | 没有对单个子进程实施硬超时、内存/CPU 和进程树约束 | 仍未解决的生产级资源保护缺口 |
| V0 验收设计 | 原 Turn 3 允许模型自行选择日期格式，触碰平台缺陷 | oracle 不够跨平台；现已改为明确 `YYYY-MM-DD`，但改题不是安全修复 |

一句话概括：模型点燃了火柴，Git 在该平台路径上异常燃烧，JiuwenSwarm 当时既没有及时熄灭重复执行，也没有把单次火限制在受控容器里。

## 6. 为什么不能归为“Git 的问题，与 JiuwenSwarm 无关”

Agent 产品必须假设以下情况都会发生：

- 模型生成错误、低质量或平台不兼容的命令；
- 工具返回确定性错误；
- 第三方二进制卡死、泄漏、OOM 或派生子进程；
- 用户语音、文字或上下文中出现歧义；
- 同一失败被模型误判为“再试一次可能成功”。

JiuwenSwarm 不需要修复所有第三方工具，但必须做到故障有界。一个外部工具 bug 不应自动升级为 Agent 无限重试、整机内存压力或服务不可用。

同理，也不能把责任全部归给模型。模型策略可以改进，但模型输出本质上是非确定的；安全边界必须由确定性的 Runtime、Rail 和 Executor 执行。

## 7. 当前已经完成的修复

修复候选：`ee2896a4afb186e693c720476b6de10797e66f72`。

### 7.1 精确重复失败熔断

在同一个 invoke 中，只有以下条件全部相同时才累计：

- tool name 相同；
- 去除 `description` 等不影响执行语义的 metadata 后，参数相同；
- `has_error=true`；
- 完整失败签名相同，包括结构化 `success/error/status/result_type/exit_code/nested data`；
- 失败是顺序发生的连续尾段。

默认阈值为 3：

```text
第 1 次相同失败：允许模型恢复
第 2 次相同失败：允许模型恢复
第 3 次相同失败：force-finish 一次
第 4 次顺序执行：不得发生
```

旧通用循环检测器仍可保持关闭；新的精确 repeated-failure detector 默认开启，也支持显式关闭和自定义阈值。

### 7.2 已完成验证

- repeated-failure focused tests：`20/20 PASS`；
- 受影响 adapter test：`1/1 PASS`；
- 默认、disabled、自定义 threshold 和两份 YAML 接线冒烟：`PASS`；
- changed-file Ruff、`py_compile`、`git diff --check`：`PASS`。

覆盖的关键正反场景包括：

- 第 3 次相同失败只 force-finish 一次；
- fake 顺序 loop 确认 executor 只执行 3 次；
- `description` 变化不绕过保护；
- 工具、语义参数、错误内容、nested data 或 exit code 变化时不误杀；
- 成功会重置连续失败尾段；
- dict、JSON、`ToolOutput` 和异常路径能形成稳定、可区分的失败签名；
- invoke/conversation/session 隔离和 cleanup；
- disabled 时零新增行为；
- 自定义阈值精确生效，非法阈值被拒绝。

## 8. 当前修复没有解决什么

这是最重要的边界。当前 guard 只限制**顺序的相同失败重试次数**，没有让单次工具执行变安全。

| 缺口 | 当前后果 |
|---|---|
| 单个工具 wall-clock 硬超时 | 一个命令仍可能无限挂起 |
| 子进程内存硬上限 | 第 1 次执行仍可能像本次一样消耗数十 GB virtual/private memory |
| CPU 配额 | 忙循环仍可能长期占用 CPU |
| 进程树所有权与 kill | 工具派生的孙进程可能在父命令取消后残留 |
| stdout/stderr 上限与背压 | 无限输出仍可能耗尽内存、磁盘或 WebSocket 队列 |
| 同一模型响应中的并行工具批次取消 | after-tool rail 不能追溯阻止已经并发发出的同批调用 |
| 平台危险参数兼容策略 | Git 的非 ASCII format 路径仍然存在，换成安全语料只是绕开 |
| 资源与熔断可观测性 | 仍需统一记录 command identity、attempt、耗时、峰值资源、kill reason 和用户可见终态 |

所以，`ee2896a4` 不能被描述成“已经解决工具资源安全”。它解决了这次明确暴露的重复失败放大器。

## 9. 对 V0 和正式版分别意味着什么

### 9.1 对 V0

- `d4c3e32a` 的 Gate 3 已经失败，不能 Released。
- Turn 3 改为明确要求 `YYYY-MM-DD`，使用 `--date=short` 或等价 ASCII oracle，避免验收本身依赖已知平台缺陷。
- `ee2896a4` 必须先重跑 Gate 0/1，再从全新 Session 的 Turn 1 重跑 Gate 3，不能从旧 Turn 4 续算。
- 在固定机器、只读工具、安全语料和新精确熔断下，硬进程沙箱不是当前 V0 Gate 的新增前置条件；但任何再次出现高资源命令、重复失败保护未生效或人工无法及时停止的情况，都必须记为新 `FAIL`。

换言之：该问题可以被控制后继续 V0 验收，但不能被删除记录或解释成“只是验收口令写得不好”。

### 9.2 对正式交付版

生产环境不能依赖安全语料、人工盯屏或“模型通常会换命令”。正式 Executor/Tool boundary 至少需要：

1. 每次工具执行的硬 wall-clock deadline；
2. 按工具/权限档位配置的内存和 CPU 上限；
3. 可验证的 process-tree kill 与取消 ACK；
4. stdout/stderr 大小和速率上限；
5. 取消、超时、OOM、熔断后的唯一 terminal outcome；
6. 对已发并行批次的停止/隔离策略；
7. command/failure fingerprint、attempt、峰值资源和 kill reason 的结构化 trace/metric；
8. Windows、Linux 及关键工具版本的兼容和故障注入矩阵。

这属于完整方案中的 Agent Bridge、Executor & Durability、Error & Observability 和 X-E2E/X-OBS 交叉责任，不应只塞进 Live Voice 前端。

## 10. 测试与验收矩阵

### 10.1 当前 D-037 hotfix 必须保持的自动化

| 场景 | 期望 |
|---|---|
| 同工具、同参数、同失败连续 3 次 | 第 3 次 force-finish 一次，顺序第 4 次执行为 0 |
| 前两次相同失败后改用成功命令 | 不熔断，成功重置尾段 |
| 相同工具但命令不同 | 不熔断 |
| 相同命令但 error/nested data/exit code 不同 | 不熔断 |
| `description` 不同但执行参数相同 | 仍识别为相同重试 |
| dict/JSON/ToolOutput/exception 等价表示 | 生成稳定等价签名 |
| conversation/invoke/session 交错 | 状态完全隔离 |
| cleanup/after-invoke/在途 callback | 不泄漏、不误 force-finish |
| feature disabled | 零新增行为 |
| 自定义和非法 threshold | 精确生效或明确拒绝 |

### 10.2 V0 仍需执行

- detached `ee2896a4` 的 Gate 0；
- Gate 1 固定自动化、build、Ruff、diff-check 和真实文字 Agent/Tool smoke；
- 新 Session 从 Turn 1 开始的 Gate 3 连续 10 Turn；
- 后续 Gate 4–6。

### 10.3 正式资源保护后必须新增

- 单命令超时后，进程树全部退出且只产生一个 terminal outcome；
- 内存/CPU 超限被确定性终止，Agent 不继续重试同一高资源失败；
- stdout/stderr 超限时截断有标记、无内存/队列失控；
- 取消与超时竞态、父子/孙进程、Windows/Linux 差异；
- 同一模型响应已经发出的并行工具批次；
- Tool crash、OOM、hang、无限输出、拒绝取消和孤儿进程故障注入；
- 资源释放后的下一正常请求可以成功，文字聊天和 Live Voice 不需要重启恢复。

## 11. 后续行动优先级

| 优先级 | 行动 | 当前状态 |
|---:|---|---|
| P0 | 保留失败历史，不放行 `d4c3e32a` | 已完成 |
| P0 | 精确重复确定性失败第 3 次熔断 | `ee2896a4` 已实现，focused tests PASS |
| P0 | Gate 3 使用明确 `YYYY-MM-DD` 的跨平台安全 oracle | 文档已更新，待新 Candidate 实跑 |
| P0 | 在 `ee2896a4` 先重跑 Gate 0/1，再重跑 Gate 3 | 未执行 |
| P1 | 设计并实现通用 Tool subprocess resource envelope | 未开始；正式交付必需 |
| P1 | 补齐真实 Agent/Gateway 熔断与终态 integration evidence | 未执行 |
| P1 | 建立工具资源、熔断、取消和 kill reason 观测 | 未开始 |
| P2 | 继续量化 ASR 关键动作词/技术词准确率并评估 Provider fallback | 持续项 |
| P2 | 向 Git for Windows 提交最小复现或继续底层调试 | 可独立推进；不替代 JiuwenSwarm 防护 |

## 12. 结论

该事故暴露了三个不同层次的问题：

1. **输入质量**：ASR 可能误识别，模型也可能选择平台不兼容命令。
2. **执行可靠性**：Git for Windows 的该非 ASCII 日期格式路径可触发异常内存增长和 OOM。
3. **系统安全性**：JiuwenSwarm 必须让单次执行和重复执行都保持有界。

当前 D-037 修复已经堵住“相同确定性失败被顺序无限放大”这一基础门槛，足以让 V0 在安全语料和受控环境下继续验收；但它没有关闭生产级工具资源治理。后续正式版必须把“模型和外部工具都可能失败”当作正常输入，在 Runtime/Executor 层用确定性的资源、取消和终态契约兜底。

## 13. 参考

### 仓库内事实来源

- [STATUS.md](STATUS.md)：当前 Candidate、真实资源数据、D-037 测试闭环与下一步。
- [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md)：Gate 3 失败判定、重跑规则和 V0 放行边界。
- [E2E_RUNBOOK.md](E2E_RUNBOOK.md)：固定环境、真实时间线和服务恢复事实。
- [DECISIONS.md](DECISIONS.md)：D-037 的 Accepted 决策。
- [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md)：Agent Bridge、Executor、Error/Observability 和故障注入的长期边界。
- `tests/unit_tests/agentserver/rails/test_circuit_breaker_repeated_failure.py`：本事故命令和 OOM 结果的 focused regression tests。

### 上游实现与平台文档

- [Git `date.c`](https://github.com/git/git/blob/master/date.c)：自定义日期格式进入 `strbuf_addftime` 的路径。
- [Git `strbuf.c` 官方镜像](https://kernel.googlesource.com/pub/scm/git/git/+/a066a90db68da5262e81e74a50d18eaeddc6783f/strbuf.c)：`strbuf_addftime` 的 `strftime` 与缓冲区扩容逻辑。
- [Microsoft `strftime` / `wcsftime`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/strftime-wcsftime-strftime-l-wcsftime-l?view=msvc-170)：返回值、缓冲区不足和非法参数行为。
