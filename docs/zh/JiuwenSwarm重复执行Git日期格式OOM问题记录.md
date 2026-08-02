# JiuwenSwarm 重复执行 Git 日期格式 OOM 问题记录

## 1. 问题概述

在 JiuwenSwarm 中提交一次“查看最新提交日期”的自然语言请求后，Agent 生成并执行了以下命令：

```text
git log -1 --format=%ad --date=format:'%m月%d日'
```

Git for Windows 运行该命令时持续扩大内存，最终返回：

```text
fatal: Out of memory, realloc failed
```

第一次失败结果返回 JiuwenSwarm 后，Agent 没有更换命令或停止，而是再次执行相同工具和参数。最终，一次用户请求产生了 11 次 `tool_call`，其中 10 次返回相同 OOM 失败；第 11 次调用在执行过程中被人工取消，整个请求始终没有形成最终回答。

这个问题包含两个连续发生、但需要区分的现象：

1. 单次 Git 进程会在内部持续扩容，直到 OOM，然后以一次失败退出。
2. JiuwenSwarm 收到这次失败后，又启动新的 Git 进程重复相同命令，形成多次独立 OOM。

并不是前几次命令只普通失败、最后一次才 OOM。第一次执行已经 OOM，后面的调用是在重复同一个会 OOM 的命令。

## 2. 实际经过

用户的原始意图是查看提交日期。进入 Agent 的输入文本中，“年月日”曾变成“念月日”，随后模型选择了带中文字面量的 Git 日期格式。

完整过程是：

```text
用户提交一次日期查询
→ JiuwenSwarm 将请求交给 Agent
→ 模型生成带中文“月/日”的 Git 命令
→ Terminal Tool 启动 Git 子进程
→ Git 子进程内部不断扩大缓冲区
→ Git 进程 OOM，以非零退出码结束
→ Terminal Tool 将相同失败结果返回 Agent
→ 模型再次选择同一工具和相同参数
→ JiuwenSwarm 再次启动新的 Git 子进程
→ 相同 OOM 重复发生
→ 第 11 次调用在途时人工取消
```

观察结果：

- 用户请求数量：1；
- `tool_call` 数量：11；
- 已返回的相同失败结果：10；
- 最终回答数量：0；
- 单个异常 Git 子进程曾达到约 8.5 GB Working Set / 49 GB Private Memory；
- Git 进程退出后，其占用资源恢复；
- 命令没有修改仓库内容，工作区保持干净。

## 3. 单次 Git OOM 与 JiuwenSwarm 重复调用的区别

### 3.1 Git 进程内部

单独在 Terminal 中执行一次异常命令，也能复现同样的 OOM。一次命令对应一个 Git 进程；该进程在内部不断尝试扩大缓冲区，直至内存分配失败，然后输出一次 OOM 错误并退出。

```text
Git 进程 1
→ 内部多次扩容
→ OOM
→ 返回一次失败
→ 进程退出
```

### 3.2 JiuwenSwarm Agent 循环

JiuwenSwarm 收到上一个 Git 进程的失败结果后，模型再次发起相同工具调用。每一次 tool call 都会启动新的 Git 进程，每个进程都会独立经历内部扩容和 OOM。

```text
Git 进程 1：内部扩容 → OOM → 退出
Git 进程 2：内部扩容 → OOM → 退出
Git 进程 3：内部扩容 → OOM → 退出
……
```

因此，Git 的内部扩容解释“为什么一次命令会 OOM”，JiuwenSwarm 的外部重试解释“为什么相同 OOM 会重复发生十次”。

## 4. 独立复现与对照

异常命令：

```text
git log -1 --format=%ad --date=format:'%m月%d日'
```

对照命令：

```text
git log -1 --format=%ad --date=short
git log -1 --format=%ad --date=format:'%Y-%m-%d'
```

在 Git for Windows `2.47.1.windows.2` 上观察到：

| 项目 | 非 ASCII format | `--date=short` / ASCII format |
|---|---|---|
| 是否返回日期 | 否 | 是 |
| 进程内存 | 持续异常增长 | 正常 |
| 最终结果 | `fatal: Out of memory, realloc failed` | 立即成功 |
| 脱离 JiuwenSwarm 是否复现 | 是 | 不发生异常 |

这说明第一次 OOM 的直接执行层原因不在 JiuwenSwarm：同一命令脱离 Agent 后仍会使 Git 子进程 OOM。JiuwenSwarm 的问题是收到明确、相同的失败以后仍然继续执行。

## 5. 输入文本在问题中的作用

“念月日”不会直接传给 Git，也不会直接触发异常。它只是模型生成命令时看到的自然语言上下文。

Git 实际收到的是：

```text
--date=format:'%m月%d日'
```

因此，“年月日”变成“念月日”只能视为命令选择的诱因，不能视为 OOM 根因。即使输入文本完全正确，模型仍可能主动选择相同的中文日期格式。

## 6. Git OOM 的机制判断

当前证据最符合以下路径：

```text
Git DATE_STRFTIME 日期模式
→ strbuf_addftime(...)
→ C Runtime strftime(...)
→ 当前环境中持续返回 0
→ Git 将 0 解释为缓冲区仍不够
→ 扩大缓冲区并再次调用 strftime
→ 缓冲区反复翻倍
→ xrealloc 最终 OOM
```

Git 的自定义 `format:` 日期路径会进入 `strbuf_addftime`。该实现调用 `strftime`；当返回值为 0 时扩大缓冲区。Microsoft CRT 文档说明，`strftime` 在缓冲区不足时返回 0，非法参数路径也可能返回 0。

如果 Git for Windows 的非 ASCII/locale 转换在当前环境中持续返回 0，而不是在缓冲区扩大后成功，Git 就会不断扩容，最终由 `xrealloc` 报告 OOM。

这一机制可以解释为什么单独执行一次命令也会发生 OOM，但还没有定位持续返回 0 的具体底层分支。

## 7. 从 JiuwenSwarm 角度暴露的问题

Git OOM 是直接执行层故障，但在 JiuwenSwarm 中造成严重影响的是故障没有及时收敛：

- 同一个用户请求在第一次确定性失败后继续产生相同工具调用；
- tool name、执行参数和完整失败结果均没有变化；
- 重复执行没有增加新信息，也没有让 Agent 接近正确答案；
- 每一次重试都会重新启动一个可能消耗大量内存的 Git 子进程；
- 请求在 10 次失败后仍没有结束，也没有返回可读的最终错误；
- 最终必须依靠人工取消第 11 次调用。

项目当时已经存在工具循环检测器，但默认配置没有启用通用 Circuit Breaker；已有默认错误阈值即使启用，对这种单次就可能消耗大量资源的失败也过晚。同时，Terminal Tool 对单个子进程没有足够强的内存、超时和进程树限制，因此第一次调用本身就能对整机资源造成明显压力。

从 JiuwenSwarm 角度看，这不是“Git 出错后正常返回失败”这么简单，而是：一个外部工具的可复现 OOM 被 Agent 循环连续放大，并且系统没有在合理次数内结束请求。

## 8. 分层判断

| 层 | 本次实际表现 | 与 JiuwenSwarm 问题的关系 |
|---|---|---|
| 输入文本 | “年月日”变成“念月日” | 可能影响模型选命令，不直接触发 OOM |
| 模型 | 生成非 ASCII 日期格式；收到失败后继续选择相同命令 | 决定了触发条件和重复策略 |
| Git for Windows | 单个进程内部扩容直至 OOM | 第一次及每次独立 OOM 的直接执行层原因 |
| Terminal Tool | 返回明确失败，但单进程可消耗大量资源 | 暴露子进程资源边界不足 |
| Agent Runtime | 相同工具、参数、失败连续发生仍未终止 | 将一次外部工具故障放大为多次 OOM |

## 9. 已确认与仍未确认

### 已确认

- 异常 Git 命令脱离 JiuwenSwarm 后仍可复现 OOM；
- `--date=short` 和 ASCII 日期格式正常；
- 单个 Git 子进程会异常扩大内存并以 OOM 退出；
- 一次 JiuwenSwarm 用户请求产生了 11 次相同工具调用；
- 已完成的 10 次调用返回相同失败，第 11 次由人工取消；
- JiuwenSwarm 没有在重复确定性失败后及时形成最终回答；
- 进程退出后资源恢复，仓库没有被修改。

### 仍未确认

- `strftime` 持续返回 0 的具体内部位置；
- Microsoft CRT、MSYS/locale 转换和 Git for Windows 适配代码各自的责任比例；
- 每次 `strftime` 调用的 `errno` 和 locale 内部状态；
- 如果不人工取消，Agent 最终会在何种条件或次数下自行停止。

## 10. 结论

本次情况可以准确概括为：

> 一次 JiuwenSwarm 自然语言请求触发了一个在 Git for Windows 上可独立复现的非 ASCII 日期格式 OOM。第一次 Git 调用已经 OOM；JiuwenSwarm 在收到相同失败后又重复启动相同命令，使一次外部工具故障被放大为十次已完成 OOM 和一次在途调用，并且始终没有产生最终回答。

直接 OOM 属于 Git for Windows 的执行路径问题；重复相同失败并持续启动高资源子进程，是这次情况在 JiuwenSwarm 中暴露出的核心问题。

## 11. 参考

- [Git `date.c`](https://github.com/git/git/blob/master/date.c)：自定义日期格式进入 `strbuf_addftime` 的路径。
- [Git `strbuf.c` 官方镜像](https://kernel.googlesource.com/pub/scm/git/git/+/a066a90db68da5262e81e74a50d18eaeddc6783f/strbuf.c)：`strbuf_addftime` 的 `strftime` 与缓冲区扩容逻辑。
- [Microsoft `strftime` / `wcsftime`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/strftime-wcsftime-strftime-l-wcsftime-l?view=msvc-170)：返回值、缓冲区不足和非法参数行为。
