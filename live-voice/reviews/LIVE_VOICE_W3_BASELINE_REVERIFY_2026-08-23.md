# 以 w3 最新代码为基线重验并修复 88 项严格评审缺陷 — 作业书

> 本文件是给执行会话的完整交接。读完这一份即可开工，不需要原始会话的上下文。
> **文中所有数字都有时效性** —— w3 在持续推进，开工第一步必须重新测量。

---

## 1. 目标

以 `agtai/hx/0812_live_voice_w3` 的**最新代码**为唯一基线，把 88 项严格评审确认
缺陷全部过一遍，凡在该基线上仍然存在的，逐一修复。

这与之前的做法不同。之前是在独立分支上修复、再合入 w3；本次不预设任何一项"已经
修好"，一切以 w3 当前代码的实测为准。

分三个阶段：

1. **重验已闭合的 37 项** —— 它们的修复代码和测试都是现成的，但尚未落到 w3 上
2. **重验未闭合的 51 项** —— 从原始审计描述出发，在 w3 代码上定位并复现
3. **逐一修复**仍存在的缺陷

---

## 2. 起点与既有材料

| 材料 | 位置 | 用途 |
|---|---|---|
| w3 特性分支 | `agtai/hx/0812_live_voice_w3` | **唯一基线** |
| 37 项修复（代码+测试） | `agtai/codex/lv-w3-merge-37` 的 `0a82fe52e` | 阶段一的现成材料 |
| 修复来源分支与全部文档 | `agtai/codex/live-voice-strict-review-20260819` | 台账、契约、缺陷描述 |

**关键事实：`0a82fe52e` 已经不能干净 cherry-pick 了。** 它的父提交是 w3 的
`4c6af2f74`；截至本文撰写，w3 已前进到 `acd873d0e`，多出 37 个提交、动了 44 个源
文件，cherry-pick 会在 5 个文件上冲突：

```
jiuwenswarm/common/e2a/wire_codec.py
jiuwenswarm/gateway/live_voice/dedicated_media_route.py
jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py
tests/unit_tests/e2a/test_wire_codec.py
tests/unit_tests/gateway/test_dedicated_media_registration.py
```

这个清单本身也会变，开工时重新测：

```bash
git fetch agtai hx/0812_live_voice_w3
git worktree add --detach <临时树> agtai/hx/0812_live_voice_w3
cd <临时树> && git cherry-pick 0a82fe52e   # 看冲突清单，然后 --abort
```

必读文档（都在 `codex/live-voice-strict-review-20260819` 上）：

- `LIVE_VOICE_STRICT_REVIEW_REPAIR_EXECUTION_2026-08-20.md` —— **主契约**。
  §2.2 是复核裁决线（什么能驳回、什么只能路由、两轮上限），§2.3 是推进规则，
  §6 是 51 项未闭合缺陷的队列，§6.1 是历史路由项，§7 是 37 项的闭合台账。
- `LIVE_VOICE_STRICT_REVIEW_REVALIDATION_2026-08-19.md` —— 88 项的**原始描述**，
  每条含缺陷位置、Change（怎么改）、Verify（怎么验）。阶段二从这里出发。
- `LIVE_VOICE_STRICT_REVIEW_CLOSED_DEFECTS_2026-08-22.md` —— 37 项逐条展开为
  「此前/后果/修法/此后」，附每个 packet 的完整提交列表。阶段一用它理解修法。
- `LIVE_VOICE_W3_MERGE_PLAN_2026-08-22.md` —— 上一次合并的方法记录，双树对照和
  集成缝检查的做法写在 §4、§5，本次仍然适用。

---

## 3. 阶段一：重验已闭合的 37 项

**不要假设它们已经修好。**`0a82fe52e` 还没进 w3，所以除非 w3 自己独立修过，
这 37 项在 w3 上仍然存在。

### 做法：双树对照

对每个 packet，把**它的测试文件**（从 `0a82fe52e` 取）放到 w3 代码上跑：

```bash
git -C <仓库> show 0a82fe52e:tests/unit_tests/live_voice/<test_file> \
  > <w3树>/tests/unit_tests/live_voice/<test_file>
python -m pytest tests/unit_tests/live_voice/<test_file> --no-cov -q
```

判读规则（这一步最容易出错，逐条对照）：

| 结果 | 含义 | 处置 |
|---|---|---|
| **业务断言失败** | 缺陷在 w3 上仍在，测试仍有效 | 需要修复 → 阶段三 |
| **只有 `AttributeError` / `ImportError`** | 只证明修复引入的新 API 不存在，**不证明缺陷存在** | 回到原始描述，人工在 w3 代码上确认机制是否还在 |
| **全绿** | 要么 w3 已修，要么测试在 w3 上失效 | **必须种变异体区分**，见下 |
| 收集错误 | w3 重构了该模块 | 人工分析 |

实例（上一轮实测 SRR-10/A2+B2）：21 个失败里 14 个是真 RED
（`StreamingSpeechViolation: recognition cannot accept input or output after terminal`
—— A2/B2 的确切原始机制），7 个是假 RED
（`'_RecognitionSession' object has no attribute 'retirement_claimed'` ——
`retirement_claimed` 是修复才引入的字段）。

### 「全绿」时怎么区分

在 w3 源码上种一个针对该性质的变异体再跑：

- 杀得死 → 测试有效，w3 确实自己修好了 → 记录并跳过该项
- 杀不死 → 测试在 w3 上失效 → 人工重新分析该缺陷

### 修复材料是现成的

确认仍存在后，**不要重新实现**。`0a82fe52e` 里有经独立复核的源码与测试，直接取用
并按 w3 当前代码适配。上一轮的适配经验（`LIVE_VOICE_W3_MERGE_PLAN` §5）：

- 冲突可能需要**语义合并**而非二选一。例如 w3 给某个调用加了新参数、而修复把该
  调用包进了 off-loop 包装，正确做法是让包装转发新参数。
- w3 新增的代码路径可能**绕过修复引入的保护**，且测试全绿查不出来。上一轮实测：
  `persistent_task_core.py` 里 w3 新增 9 个 async 路径上的同步 SQLite 调用，全部
  需要接进 `_run_store`。用 AST 扫描找这类点。
- w3 可能**有意改变了行为**并有自己的测试。上一轮遇到一例：w3 让更高 generation
  在前驱 CLOSING 时直接分配，与 A15 的一条测试直接矛盾。判据是看该缺陷的**核心
  性质**是否另有测试覆盖 —— 有，就按 w3 的新语义调整场景构造，核心断言不动。

---

## 4. 阶段二：重验未闭合的 51 项

从 `LIVE_VOICE_STRICT_REVIEW_REVALIDATION_2026-08-19.md` 出发。每条记录形如：

> **A5 — confirmed, HIGH.** `<文件>:<行号>` 描述机制。**Change:** 怎么改。
> **Verify:** 怎么验。

行号是对**审计当时**的基线而言，w3 已经大幅演进，必须按机制而非行号定位。

对每一项判定三种结果之一：

| 判定 | 依据 | 处置 |
|---|---|---|
| **仍存在** | 在 w3 代码上写出复现，失败是业务断言 | → 阶段三修复 |
| **已消失** | w3 的演进使该机制不可达或已修 | 记录证据（哪个提交、怎么改的），标注为不再适用 |
| **形态改变** | 机制还在但位置/条件变了 | 按新形态重新描述，再修 |

**"已消失"必须有证据，不能靠读代码得出。**最低要求是：写出原本能复现该缺陷的
用例，在 w3 上跑绿，再种一个变异体证明该用例确实在检验那条性质。

51 项按 §6 的分组：

| 分组 | 数量 | 缺陷 ID |
|---|---:|---|
| 协议 / 状态 / 兼容性 | 29 | B1、B3、B5、B8、B19、B20、B22、B28、B29、B30、B33、B34、B35、B40、L1–L4、L6、L8–L13、L15–L17、L22 |
| generation / 后继 / 权威清理 | 7 | B18、B32、B37、B38、B39、D2、L19 |
| 取消 / 拆除 / 保留清理 | 6 | A19、A22、B21、B23、D1、D3 |
| 容量 / 生命周期 / 重放 | 5 | A5、A9、B11、L5、L18 |
| 事件循环 / 锁 / 文件系统 | 4 | A14、B15、B25、B27 |

最大一组是协议/状态/兼容性，多为单点校验与状态转换，通常比容量与关停类简单。

---

## 5. 阶段三：逐一修复

沿用契约 §2 的闭合序列，但基线换成 w3：

1. 在 w3 代码上**先复现**，失败必须是业务断言而非 `AttributeError`
2. owner 范围内的**最小修复**，不新增产品策略、协议字段或 reason code
3. 补上能杀死反向变异体的测试（契约里的 standing evidence rule）
4. **独立复核**，由没有实现该 packet 的人执行
5. 集成后复跑受影响范围

### 复核裁决线（契约 §2.2，必读）

上一轮 Wave 11/12 的教训：同样的 24 小时，前期关 31 项、后期只关 6 项，差距全在
复核轮次。六份复核报告**没有一份在源码里找到缺陷**，全部是证据缺口。所以：

**只能驳回**：源码有缺陷 / 变异体能复活刚关闭的 finding / 声称的性质从**出厂输入**
可达 / 新测试是假闸门（空断言、同义反复、在未修复基线上照样通过、只透过替身断言）。

**其余一律路由**到 §6.1，不挡集成：只在敌意注入或替身下可达的性质、packet 没碰过
的代码里的缺口、存活但等价或不可达的变异体、报告的措辞问题。

**两轮上限**：到第三轮，集成方直接按这条线裁决收口。

### 分支与集成

- 每个 packet 一个 worker 分支 + 独立工作树，只改自己 owner 的文件
- 集成方是唯一能合入的角色，只合经复核的提交
- **不要 push，不要动 remote ref**，除非用户明确要求
- 基线随 w3 推进而移动：每冻结一波，从 w3 当时的最新提交切出

---

## 6. 环境

```
PYTHONPATH=D:/XGG AI/openjiuwen/jiuwenswarm/.venv/Lib/site-packages
python -m pytest <path> --no-cov -q
```

主仓库的 `.venv` 已含全部依赖，包括 `openjiuwen`（pyproject 指定的是 gitcode 上的
git 版本，不是 PyPI 版本）。实测只用这一项，三个代表性套件 412 项全过。

**不要用 conda base**，它缺多数包，症状是一堆 collect error 看起来像代码坏了。

### 本机陷阱（都踩过，逐条避开）

- **PowerShell 5.1 写 BOM 并按 CP936 读坏 UTF-8** —— 一切文本编辑走 Python 或
  编辑器工具，绝不用 PowerShell 重定向写文件。
- **`core.autocrlf=true`，工作树是 CRLF** —— 锚点替换用纯 bytes 读写 + `\r\n↔\n`
  归一化。`read_text`/`write_text` 会改写全部行尾让 `git status` 报 modified；
  `newline=""` 会让所有锚点落空，症状是变异体齐刷刷 ANCHOR-ERROR。**把锚点不符当
  错误处理，不要打印 SKIPPED 后继续。**
- **`subprocess(text=True)` 在 Windows 上默认 GBK 解码** —— 遇 UTF-8 输出直接抛
  `UnicodeDecodeError`。显式 `encoding="utf-8", errors="replace"`。
- **含空格路径不能用 `for` 循环分词** —— `D:/XGG AI/...` 会被切成两半。用
  `while IFS= read -r`。
- **`ruff` 不在 PATH**，用 `python -m ruff`。`jiuwenswarm/` 无 `[tool.ruff]` 配置，
  只有**相对基线的差值**有意义；且 `--stdin-filename` 模式与真实文件模式的配置发现
  不同，做基线对比必须两边同模式，最好都用真实工作树上的文件。
- **`pytest` 不要加 `-o addopts=''`** —— 会清掉 `--asyncio-mode=auto`，凭空制造
  几十个假失败。
- **无 per-test 超时插件** —— 死锁的变异体会挂死整个 session 而不是报失败，变异
  运行要在 subprocess 层加超时。
- **`git stash` 是仓库级的**，跨工作树共享 —— 并行作业时禁用，基线对照建临时工作树。
- **长路径**会让 scratchpad 下的 `git worktree add` 失败，临时工作树建在
  `D:/XGG AI/openjiuwen/` 同级。
- Git Bash 无 `grep -P`。
- **测试跑完不要用 `tail -N` 截断输出**再存基线 —— 上一轮因此把 9 个失败截成 5 个，
  差点用错基线。完整存文件再解析。

---

## 7. 交付要求

- 三个阶段各产出一张表：37 项的重验判定、51 项的重验判定、修复清单与证据
- 每一项判定都要有**实测依据**（用例名 + 失败断言，或变异体 + 结果），不接受
  "读代码得出"
- "已消失"的判定要有证据，最低要求见 §4
- 每个修复的闭合遵守契约 §2 的序列与 §2.2 的裁决线
- 台账（`LIVE_VOICE_STRICT_REVIEW_REPAIR_EXECUTION_2026-08-20.md` §7）与
  `STATUS.md` 的分子同步更新
- 如果发现本作业书里某条结论不成立，**给出证据并说明**，不要盲从
