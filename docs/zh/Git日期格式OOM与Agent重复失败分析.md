# Git for Windows 非 ASCII 日期格式 OOM 与 Agent 重复失败放大分析

## 1. 问题摘要

在 Windows 环境中执行以下 Git 命令时，Git 子进程会异常扩张内存并最终 OOM：

```text
git log -1 --format=%ad --date=format:'%m月%d日'
```

可见错误为：

```text
fatal: Out of memory, realloc failed
```

该问题在 Git for Windows `2.47.1.windows.2` 上可以脱离 Agent 稳定复现。使用 `--date=short` 或只包含 ASCII 字符的日期格式时立即成功，因此它不是仓库过大、提交历史异常或机器原本内存不足造成的普通 OOM。

在 Agent 场景中，这个执行层故障还暴露出第二个独立问题：模型收到相同错误后没有改变策略，而是重复执行同一命令；Agent Runtime 没有及时终止确定性失败，最终把一次 Git 兼容性问题放大成多次高资源工具调用。

需要把两个问题分开处理：

1. **单次执行异常**：Git for Windows 在非 ASCII 日期格式路径上发生异常内存增长。
2. **重复执行放大**：Agent 对同工具、同参数、同失败连续重试，使资源风险成倍增加。

## 2. 最小复现与对照

### 2.1 异常命令

```text
git log -1 --format=%ad --date=format:'%m月%d日'
```

### 2.2 安全对照

```text
git log -1 --format=%ad --date=short
git log -1 --format=%ad --date=format:'%Y-%m-%d'
```

已观察到的差异：

| 项目 | 非 ASCII format | `--date=short` / ASCII format |
|---|---|---|
| 是否返回日期 | 否 | 是 |
| 进程内存 | 异常持续增长 | 正常 |
| 最终结果 | `fatal: Out of memory, realloc failed` | 立即成功 |
| 是否依赖 Agent | 否，独立执行也能复现 | 否 |

异常样本中，单个 Git 子进程曾达到约 8.5 GB Working Set / 49 GB Private Memory。进程退出后资源恢复，命令没有修改仓库内容。

## 3. Agent 场景中的完整故障链

一次自然语言日期查询最终演变为：

```text
用户请求查看提交日期
→ 模型生成带中文字面量的 Git 日期格式命令
→ Git for Windows 异常扩张内存并 OOM
→ Terminal Tool 返回确定性失败
→ 模型没有改用安全格式或其他查询方式
→ Agent 再次执行同一工具和参数
→ 相同高资源失败被连续放大
```

实际观察到：

- 用户只提交了 1 次请求；
- Agent 产生 11 次 `tool_call`；
- 其中 10 次返回相同失败结果；
- 始终没有形成最终回答；
- 第 11 次调用在途时才被人工取消。

这说明“工具本身有 bug”和“Agent 缺少及时止损”同时存在。修复任意一层都能降低本次事故，但生产系统必须同时约束单次执行和重复执行。

## 4. 自然语言或识别偏差不是直接异常

问题出现前，自然语言输入中曾发生“年月日”被识别为“念月日”的偏差。这类文本只会影响模型的命令选择，不会直接传给 Git，也不会直接触发 OOM。

Git 实际收到的是：

```text
--date=format:'%m月%d日'
```

因此：

- 识别偏差是可能的诱因，不是直接根因；
- 即使识别完全正确，模型也可能自行选择相同的中文日期格式；
- 只修改自然语言说法不能替代工具执行保护；
- 安全边界不能建立在“模型通常会生成兼容命令”的假设上。

## 5. 异常机制分析

从 JiuwenSwarm 看到的是 Terminal Tool 的确定性失败：Git 子进程以非零退出码结束，并在 stderr 返回 OOM。当前证据最一致的底层机制如下：

```text
Git DATE_STRFTIME 日期模式
→ strbuf_addftime(...)
→ C Runtime strftime(...)
→ 当前环境中持续返回 0
→ Git 将 0 解释为缓冲区仍不够
→ 扩大缓冲区并重试
→ 缓冲区反复翻倍
→ xrealloc 最终 OOM
```

Git 的自定义 `format:` 日期路径会进入 `strbuf_addftime`。该实现调用 `strftime`，当返回值为 0 时扩大缓冲区。Microsoft CRT 文档说明，`strftime` 在缓冲区不足时返回 0，非法参数路径也可能返回 0。

如果当前 Git for Windows 的非 ASCII/locale 转换路径持续返回 0，而不是在缓冲区扩大后成功，Git 就会反复扩容，最终演变为 OOM。

### 5.1 已确认和未确认的边界

已确认：

- 异常命令在指定 Git for Windows 版本上可独立复现；
- ASCII 和 short-date 对照成功；
- Git 进程发生异常内存增长；
- 最终错误为 `fatal: Out of memory, realloc failed`。

源码支持的高概率解释：

- `strftime` 持续返回 0；
- `strbuf_addftime` 持续扩大缓冲区；
- 最终由 `xrealloc` 报告 OOM。

尚未确认：

- 持续返回 0 的具体内部位置；
- Microsoft CRT、MSYS/locale 转换和 Git for Windows 适配代码各自的责任比例；
- 每次 `strftime` 调用对应的 `errno` 和 locale 内部状态。

因此，准确表述应是“Git for Windows 非 ASCII 日期格式路径的可复现 OOM”。在完成调试器级取证前，不应把某一个更底层分支写成已经确认的唯一 upstream 根因。

## 6. 分层责任

| 层 | 在问题中的作用 | 应承担的处理 |
|---|---|---|
| 自然语言输入 / ASR | 可能改变模型理解和命令选择 | 改善关键术语识别、允许确认或编辑，但不能承担最终安全责任 |
| 模型 / Agent 决策 | 生成平台不兼容命令；失败后未改变策略 | 提示模型换策略、识别确定性失败，但不能只依赖提示词 |
| Git for Windows | 对该非 ASCII format 异常扩张内存并 OOM | 继续底层定位、准备最小复现并评估提交 upstream issue |
| Agent Runtime | 允许同工具、同参数、同失败连续重试 | 对确定性重复失败执行低阈值精确熔断 |
| Tool / Executor | 单个子进程缺少硬资源边界 | 增加超时、内存/CPU、输出和进程树限制 |

直接执行层故障属于 Git for Windows；事故被连续放大属于 Agent Runtime；单次异常进程能够冲击整机资源则属于 Tool/Executor 隔离不足。这三层不能互相替代。

## 7. 防护设计

### 7.1 立即规避

查询日期时优先使用跨平台格式：

```text
git log -1 --format=%ad --date=short
git log -1 --format=%ad --date=format:'%Y-%m-%d'
```

避免在 Git for Windows 的 `--date=format:` 中直接嵌入非 ASCII 字面量。需要本地化展示时，可以先取得 ASCII/ISO 日期，再由应用层格式化为“月/日”等本地化文本。

### 7.2 精确重复失败熔断

Agent Runtime 应在同一个 invoke 内识别以下连续尾段：

- tool name 相同；
- 去除 `description` 等非语义 metadata 后，执行参数相同；
- 结果明确失败；
- 完整失败签名相同，包括 `success/error/status/result_type/exit_code/nested data`。

低阈值熔断应只阻止相同确定性失败继续顺序执行，同时允许模型在前几次失败后改用不同命令或成功恢复。不同工具、不同参数、不同错误和成功结果不能被误判为同一失败。

这类熔断只能限制重复次数，不能让第一次执行变安全。

### 7.3 子进程资源边界

正式 Tool/Executor 至少需要：

1. 每次工具执行的硬 wall-clock deadline；
2. 按工具和权限档位配置的内存与 CPU 上限；
3. 可验证的 process-tree kill，覆盖子进程和孙进程；
4. stdout/stderr 大小与速率上限；
5. 取消、超时、OOM 和熔断后的唯一 terminal outcome；
6. 对同一模型响应中已发并行工具批次的停止或隔离策略；
7. command/failure fingerprint、attempt、耗时、峰值资源和 kill reason 的结构化观测。

## 8. 仅有重复失败熔断仍不足

| 仍然存在的缺口 | 可能后果 |
|---|---|
| 单个工具没有硬超时 | 第一次调用就可能无限挂起 |
| 子进程没有内存上限 | 第一次调用仍可能消耗数十 GB 内存 |
| 没有 CPU 配额 | 忙循环可能长期占满 CPU |
| 取消不覆盖进程树 | 孙进程可能在父命令结束后残留 |
| 输出没有上限和背压 | 无限输出可能耗尽内存、磁盘或消息队列 |
| 无法取消已并发发出的同批工具 | 顺序熔断触发前，多个调用可能已经在执行 |
| 缺少资源观测 | 无法快速区分 hang、OOM、输出洪泛和取消失效 |

因此，重复失败熔断是必要止损，但不是完整的工具执行安全方案。

## 9. 测试建议

### 9.1 重复失败保护

| 场景 | 期望 |
|---|---|
| 同工具、同参数、同失败达到阈值 | 只终止一次，阈值后的下一次顺序执行为 0 |
| 前几次失败后改用成功命令 | 不熔断，成功重置连续失败尾段 |
| 相同工具但命令不同 | 不熔断 |
| 相同命令但 error、nested data 或 exit code 不同 | 不熔断 |
| 只有 description 不同 | 仍识别为相同执行参数 |
| dict、JSON、ToolOutput、exception 等价表示 | 生成稳定等价的失败签名 |
| conversation、invoke、session 交错 | 状态隔离，不串计数 |
| protection disabled | 零新增行为 |
| 自定义或非法阈值 | 精确生效或明确拒绝 |

### 9.2 进程资源保护

- 命令超时后，整个进程树退出且只产生一个 terminal outcome；
- 内存或 CPU 超限后被确定性终止；
- stdout/stderr 超限时明确截断，不造成内存或队列失控；
- 覆盖取消与超时竞态、父子/孙进程以及 Windows/Linux 差异；
- 覆盖 Tool crash、OOM、hang、无限输出、拒绝取消和孤儿进程；
- 资源释放后，下一条正常请求可以成功，不需要重启 Agent 服务；
- 故障结果再次返回模型时，不继续执行相同高资源失败。

## 10. 建议的处理顺序

1. 立即使用 `--date=short` 或 ASCII format，避免继续触发已知平台路径。
2. 对相同确定性工具失败启用低阈值精确熔断。
3. 为所有 Terminal Tool 子进程增加硬超时和可靠的 process-tree kill。
4. 增加内存、CPU、输出上限和结构化资源观测。
5. 用故障注入覆盖 OOM、hang、无限输出、并行批次与取消竞态。
6. 准备独立最小复现，继续定位 Git for Windows/CRT/locale 的具体问题并评估 upstream issue。

## 11. 结论

这个问题不是单一组件能够完整解释的：

- Git for Windows 的非 ASCII 日期格式路径导致单次执行 OOM；
- 模型没有在失败后改变策略；
- Agent Runtime 允许相同确定性失败连续重试；
- Tool/Executor 没有把单个异常子进程限制在资源边界内。

正确的工程结论不是“以后不要这样问”或“这是 Git 的问题”，而是同时做到：使用兼容命令、精确终止无意义重试、限制单次进程资源，并让所有超时、OOM、取消和熔断产生可观察且唯一的终态。

## 12. 参考

### 项目内相关实现

- [CircuitBreakerRail](../../jiuwenswarm/agents/harness/common/rails/execution_guard/circuit_breaker_rail.py)
- [重复确定性失败测试](../../tests/unit_tests/agentserver/rails/test_circuit_breaker_repeated_failure.py)

### 上游实现与平台文档

- [Git `date.c`](https://github.com/git/git/blob/master/date.c)：自定义日期格式进入 `strbuf_addftime` 的路径。
- [Git `strbuf.c` 官方镜像](https://kernel.googlesource.com/pub/scm/git/git/+/a066a90db68da5262e81e74a50d18eaeddc6783f/strbuf.c)：`strbuf_addftime` 的 `strftime` 与缓冲区扩容逻辑。
- [Microsoft `strftime` / `wcsftime`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/strftime-wcsftime-strftime-l-wcsftime-l?view=msvc-170)：返回值、缓冲区不足和非法参数行为。
