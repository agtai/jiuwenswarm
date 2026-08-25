# 把 strict-review 修复合入 hx/0812_live_voice_w3 — 作业书

> **状态：已执行。** 合并成果是分支 `codex/lv-w3-merge-37` 上的单个提交
> `0a82fe52e`，父提交为 w3 当时的 HEAD `4c6af2f74`，实测 cherry-pick 零冲突。
> 55 个文件、源码净 +4821 行、测试净 +17535 行，不含任何 `live-voice/` 文档。
> 验证结果：4028 passed（w3 基线 3674），12 项既有失败逐条不变；8 个变异体
> 7 杀 1 存活（存活那个已证明在源分支上同样无杀手测试）；Ruff 每条规则的增量
> 精确等于这批修复自身带来的增量。冲突处置与适配的理由写在该提交的信息里。
>
> 本文件保留为方法记录：若 w3 大幅推进后 `0a82fe52e` 不再能干净应用，按这里的
> 流程重做一遍即可。**文中所有数字都有时效性**，重做时第一步是重新测量，见 §2。

---

## 1. 目标与边界

把 `codex/live-voice-strict-review-20260819` 上已闭合的 37 项严格评审缺陷修复，
合入特性分支 `agtai/hx/0812_live_voice_w3`。

**只合代码与测试。文档留在本分支，不合。**

| 类别 | 处置 | 文件 |
|---|---|---|
| 源码 | **合** | `jiuwenswarm/**` |
| 测试 | **合** | `tests/**` |
| 文档 | **不合** | `live-voice/**`（5 个文件：`README.md`、`STATUS.md`、`reviews/` 下三份） |

测试必须一起合，理由不是形式主义：那些测试是这批修复唯一的回归保护，
其中一部分是专门设计来防止修复被后续编辑无意撤销的（见 §5）。
把源码合过去而不带测试，等于把修复的半衰期缩短到下一次重构。

**不要 push，不要动任何 remote ref**，除非用户明确要求。

---

## 2. 开工第一步：重新测量

作业书写就时（2026-08-22）的测量值列在下面，**仅作量级参考**。
w3 每前进一批提交，冲突面就会变化 —— 撰写期间它就从 5 个冲突文件涨到了 7 个。

```bash
cd "D:/XGG AI/openjiuwen/jiuwenswarm-review-20260819"
MB=$(git merge-base HEAD agtai/hx/0812_live_voice_w3)

# 冲突文件清单（排除 doc）
git merge-tree --write-tree --name-only HEAD agtai/hx/0812_live_voice_w3 \
  | awk 'NR>1 && /^$/{exit} NR>1{print}' | grep -v '^live-voice/'

# 各冲突的 hunk 数与行数
T=$(git merge-tree --write-tree HEAD agtai/hx/0812_live_voice_w3 | head -1)
git show "$T:<冲突文件路径>" | grep -c '^<<<<<<<'
```

撰写时的测量值：

- 本分支自 merge-base 改动 **32 个源码文件 + 23 个测试文件 + 5 个文档文件**
- 本 session 共 138 个提交：**87 个含代码**（= 30 个 packet 的全部提交）、**51 个纯文档**
- 冲突 7 个文件，其中 1 个是 `live-voice/STATUS.md`（不合，直接忽略）
- **需处理 6 个文件、8 处 hunk、约 151 行**：

  | 文件 | hunk | 行 |
  |---|---:|---:|
  | `persistent_task_core.py` | 2 | 22 |
  | `product_composition_registry.py` | 1 | 11 |
  | `product_p2_interaction_adapter.py` | 1 | 10 |
  | `task_progress_return.py` | 1 | 6 |
  | `test_p3_authenticated_composition.py` | 1 | 5 |
  | `test_product_composition_registry.py` | 2 | 97 |

---

## 3. 这批修复是什么

完整逐条记录见 `LIVE_VOICE_STRICT_REVIEW_CLOSED_DEFECTS_2026-08-22.md`（本分支）：
37 项缺陷，按根因分五组，每条展开为「此前 / 后果 / 修法 / 此后」，并附该 packet 的全部提交。

权威台账在 `LIVE_VOICE_STRICT_REVIEW_REPAIR_EXECUTION_2026-08-20.md` §7。
原始缺陷描述在 `LIVE_VOICE_STRICT_REVIEW_REVALIDATION_2026-08-19.md`。

按 w3 是否也改过其源文件分两类，处置强度不同：

**A 类 — w3 未碰过其源文件（13 个 packet）**

`SRR-02/A21`、`SRR-03/B41`、`SRR-06/A8+B6`、`SRR-07/A3`、`SRR-09/B7`、`SRR-10/A2+B2`、
`SRR-11/A4`、`SRR-15/A16`、`SRR-19/L14`、`SRR-21/B36+L20+L21`、`SRR-24/A1`、
`SRR-25/A17`、`SRR-29/B24`

这些 packet 的每一个源文件，w3 版本与 merge-base **逐字节相同**（撰写时已验证）。
合并不产生新代码。但**仍要做 §4 的双树对照** —— 文件没变不代表缺陷在系统层面还可触发，
w3 可能在调用方或上游把它挡住了。

**B 类 — w3 也改过其源文件（17 个 packet）**

`SRR-01/C5`、`SRR-04/B9`、`SRR-05/B10`、`SRR-08/A20`、`SRR-12/A18`、`SRR-13/A11`、
`SRR-14/A12`、`SRR-16/B16`、`SRR-17/A25`、`SRR-18/A23`、`SRR-20/B12+B13+B14`、
`SRR-22/A6+B4`、`SRR-23/A13`、`SRR-26/A15`、`SRR-27/B42`、`SRR-28/A7`、`SRR-30/L7`

这些需要 §4 双树对照 **加** §5 集成缝检查。

---

## 4. 双树对照：判断缺陷在 w3 上是否真的还在

这是本作业书的核心手段。它同时回答两个问题：
缺陷在 w3 上还存在吗？我们的测试在 w3 上还有效吗？

### 做法

建两棵探针工作树（**不要在候选分支或 w3 分支上直接操作**）：

```bash
MB=$(git merge-base HEAD agtai/hx/0812_live_voice_w3)
git worktree add --detach "D:/XGG AI/openjiuwen/jw-mbprobe" $MB
git worktree add --detach "D:/XGG AI/openjiuwen/jw-w3probe" agtai/hx/0812_live_voice_w3
```

对每个 packet，把**候选的测试文件**分别放进两棵树（源码保持各树原样），各跑一次：

```bash
# 取候选的测试文件（<sha> 用该 packet 最后一个提交）
git -C "<候选仓库>" show <sha>:tests/unit_tests/live_voice/<test_file> > <树>/tests/unit_tests/live_voice/<test_file>
python -m pytest tests/unit_tests/live_voice/<test_file> --no-cov -q
```

比对两棵树的**失败用例集合**与**断言内容**。断言内容比对前要归一化掉内存地址
（`at [0-9A-Fa-f]{4,}` → `at ADDR`）与单调时钟（`deadline=[\d.]+`），否则全是假差异。

### 判读规则

| 两树结果 | 含义 | 处置 |
|---|---|---|
| 失败集合与断言内容**逐条一致** | w3 未以任何方式碰过这个问题 | 直接合，合入后重跑即"绿" |
| 失败集合不同 | w3 动过影响这条路径的东西 | **人工看那条差异**，判断是部分修复、别处拦截还是行为调整 |
| w3 绿、merge-base 红 | w3 已经自己修了 | **人工看**：我们的修复可能冗余，也可能与它冲突（两套逻辑叠加）|
| **两树都绿** | 要么都修好了，要么测试失效了 | **必须种变异体区分**（见下） |
| 收集/导入错误 | w3 重构了该模块 | 人工分析，可能需要适配 |

### 失败还要再分类

**不是所有红都算数。** 失败必须是**业务断言**，不能是 `AttributeError` / `ImportError`
——后者只证明"修复引入的新 API 不存在"，不证明缺陷存在。

实例（SRR-10/A2+B2 在 w3 上实测 21 failed）：

- 真 RED：`StreamingSpeechViolation: recognition cannot accept input or output after terminal`
  —— 这正是 A2/B2 的确切原始机制
- 假 RED：`'_RecognitionSession' object has no attribute 'retirement_claimed'` ×7
  —— `retirement_claimed` 是修复才引入的字段

### 「两树都绿」时怎么种变异体

光看绿分不出"w3 修好了"和"测试在 w3 上不起作用了"。
在 w3 树的源码上种一个针对该性质的变异体，再跑：

- 杀得死 → 测试有效，w3 确实修好了 → 该 packet 可以不合源码（但测试值得合）
- 杀不死 → 测试在 w3 上失效 → **该 packet 必须人工重新分析**

变异体的写法见 §5 的电池。

---

## 5. 集成缝检查：本次合并最大的实质风险

**自动合并成功 ≠ 语义正确。**这批修复里有大量"保护包装"——
w3 从 merge-base 分出去之后新增的代码路径**不知道它们存在**，
于是合并后 w3 的新代码会绕过保护，把已修复的缺陷在新路径上原样复活，**而且测试全绿**。

### 已确认的一例

`jiuwenswarm/server/live_voice/persistent_task_core.py`（SRR-13/A11，事件循环阻塞）：

- 本分支引入 `_run_store` / `_claim_outbox` 等 async 包装，把同步 SQLite 调用挪出事件循环
- 本分支该文件有 36 个 `self.store.` 调用，其中 24 个走包装
- **w3 版本里 `_run_store` 出现 0 次，却新增了 23 个 `self.store.` 直接调用**

合并后那 23 个调用点全部在事件循环线程上跑同步 SQLite —— 正是 A11 修复要消灭的东西。

冲突 hunk 本身也体现了这一点：w3 新增了一整段 `mark_reconciliation_pending` 逻辑，
正确的合并是**把 w3 的新逻辑也套上 `await self._run_store(...)` 包装**，不是二选一。

### 扫描办法

对每个两边都改过的源文件，列出本分支新增的私有方法，检查 w3 版本里是否出现：

```python
# 对每个文件：ast 解析 merge-base / HEAD / w3 三个版本
added = {本分支的私有方法} - {merge-base 的私有方法}
unknown = [s for s in added if s not in w3源码文本]
```

撰写时的扫描结果（7 个文件，54 个保护符号，w3 **全部未知**）：

| 文件 | 新增私有方法 | w3 未知 |
|---|---:|---:|
| `agent_conversation_runtime.py` | 21 | 21 |
| `p3_confirmation.py` | 10 | 10 |
| `product_composition_registry.py` | 7 | 7 |
| `product_p2_interaction_adapter.py` | 6 | 6 |
| `conversation_runtime_loop.py` | 5 | 5 |
| `persistent_task_core.py` | 4 | 4 |
| `task_progress_return.py` | 1 | 1 |

「w3 未知」本身正常（它没见过这些代码）。**要判断的是：w3 在该文件新增的代码路径
是否需要走这些保护。**逐个看 w3 相对 merge-base 的 diff，找出新增的调用点。

### 合并后必须重跑的变异体电池

这是普通测试查不出来的一层。这批修复里至少有两条守卫，
**一行编辑即可撤销、且撤销后全套测试仍然全绿**：

| 变异 | 位置 | 撤销后果 |
|---|---|---|
| `except BaseException` → `except Exception` | `agent_conversation_runtime.py` 的 `_teardown_failure_name` | A7 缺陷复活：名字查找抛出后，后续 teardown owner 一个都不跑 |
| `if preserve_settled_reason: return` 上移跨过 join | `task_progress_return.py` 的 `_close_impl` | L7 核心不变式失效：close 返回时 worker 仍停泊 |
| `type(x) is C` → `isinstance(x, C)` | `conversation_runtime_loop.py` 分类逻辑 | B42 隐私边界重开：安全类的子类可带攻击者文本重放 |
| `type(name) is str` → `isinstance(name, str)` | `agent_conversation_runtime.py:663` | 攻击者选定内容进入公开 shutdown detail |

**合并是最典型的"无意撤销"场景**：若 w3 改过附近的行，git 可能自动合出一个把守卫吃掉的结果。
合并完成后，在合并结果上逐个种入这些变异体，确认对应用例仍然死掉。

注意 Ruff 会主动报 `BLE001`，恰好诱导下一个人去"清理"前两条 —— 那三处 `# noqa: BLE001`
不是装饰，是承重的。

---

## 6. 建议的执行顺序

1. **重新测量**（§2），拿到当前的冲突清单
2. **双树对照**（§4），30 个 packet 全跑一遍，产出分流表：
   哪些确认可直接合、哪些 w3 已动过需人工看、哪些测试可能失效
3. **人工处理分流表里的例外**，逐条给出判断与依据
4. **执行合并**：在一棵专用工作树上做，不要直接在 w3 上操作
   - 合并时**排除 `live-voice/**`**（doc 留本分支）
   - 解那 6 个文件的冲突 —— `persistent_task_core.py` 与 `task_progress_return.py`
     需要**语义合并**，不是二选一
5. **集成缝检查**（§5），补适配提交（把 w3 新增路径套上保护）
6. **验证**：
   - 跑全部相关测试套件 → 缺陷是否复活
   - 跑变异体电池 → 保护是否还在
   - 静态检查绑 scope 逐 rev 对比，确认零新增
7. **产出报告**：分流表、冲突处置说明、适配提交清单、验证结果

第 2 步可以按 packet 并行。第 5 步可以按文件并行。

---

## 7. 环境

```
PYTHONPATH=D:/XGG AI/openjiuwen/jiuwenswarm/.venv/Lib/site-packages
```

主仓库的 `.venv` 已包含跑这批测试所需的全部依赖 —— httpx、websockets、aiohttp、
loguru、pyyaml、portalocker、opentelemetry、pytest-asyncio、ruff、mcp，以及
`openjiuwen`（pyproject 指定的是 gitcode 上的 git 版本，不是 PyPI 版本）。
**实测：只用这一项，三个代表性套件 412 项全过。**

不要用 conda base，它缺上述多数包，症状是一堆 collect error 看起来像代码坏了。
早期会话曾用 `pip install --target <scratchpad>/deps` 装过一份隔离依赖，那份是
`.venv` 就绪前的临时手段，**已确认冗余**；scratchpad 路径还含会话 id，换个会话
就失效，不要沿用。

### 本机陷阱（都踩过）

- **PowerShell 5.1 会给仓库文件写 BOM 并按 CP936 读坏 UTF-8。**
  一切文本编辑走 Python 脚本或 Edit 工具，不要用 PowerShell 重定向写文件。
- **`core.autocrlf=true`，工作树是 CRLF。**做锚点替换用纯 bytes 读写 + `\r\n↔\n` 归一化。
  用 `read_text`/`write_text` 会把 CRLF 全转成 LF 让 `git status` 报 modified；
  用 `io.open(..., newline="")` 会让全部锚点 `count=0` 而变异体齐刷刷 ANCHOR-ERROR。
  **把锚点不符当错误处理，不要打印 SKIPPED 后继续。**
- **`ruff` 不在 PATH**，用 `python -m ruff`。`jiuwenswarm/` 下**没有** `[tool.ruff]` 配置
  （唯一一处在 `jiuwenbox/`），跑的是默认规则集，不同 ruff 版本默认启用的规则组不同 ——
  **只看候选与基线的差值，不要看绝对数**。
- **`pytest` 不要加 `-o addopts=''`**，那会清掉 `--asyncio-mode=auto`，凭空制造几十个假失败。
- **无 `pytest-timeout` 插件**：会死锁的变异体会挂死整个 session，要在 subprocess 层加超时。
- **`git stash` 是仓库级的**，跨工作树共享 —— 并行作业时禁用，做基线对照请建临时工作树。
- Git Bash 无 `grep -P`。
- 长路径会让 scratchpad 下的 `git worktree add` 失败（"Filename too long"），
  临时工作树建在 `D:/XGG AI/openjiuwen/` 同级。

### 已披露的既有失败（不是你引入的）

- `tests/unit_tests/live_voice/test_p3_authenticated_composition.py::test_p3_model_builder_uses_the_shared_module_level_entry_builder`
  —— `ModuleNotFoundError: No module named 'pywintypes'`，隔离环境缺 pywin32，基线同样失败。
- `tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_cancel_api_caller_cancel_retries_cleanup_then_rethrows`
  —— 六次独立复核在基线上确认过，**必须保持不变，不要顺手修**。
- `test_never_started_close_timeout_retains_retryable_leaf_teardown` 有 3% 量级的 flake，
  根因是 `close()` 既有的 `remaining <= 0` 提前返回，基线同样 flake。

---

## 8. 交付要求

- **不要 push，不要动 remote ref**，除非用户明确要求
- 合并在专用工作树上做，`live-voice/**` 不进合并结果
- 每一处冲突的处置要有书面理由，语义合并的两处尤其要说明为什么不是二选一
- 适配提交（把 w3 新增路径套上保护）单独成提交，不要混进合并提交
- 报告要包含：分流表、冲突处置、适配清单、测试计数前后对比、变异体电池结果、静态检查差值
- 如果发现本作业书里的某条结论不成立，**给出证据并说明**，不要盲从
