# 输入与统计口径

## 输入要求
支持两种 trace 文件外层格式：
- `{ "traceEvents": [...] }`
- 直接以事件数组 `[...]` 作为文件内容

支持的事件类型：
- `ph == "X"`：完整区间事件，直接使用 `ts + dur` 得到结束时间。
- `ph == "B" / "E"`：按 `(pid, tid, name)` 栈式配对为完整区间。

每个可分析事件至少应包含：
- `name`：事件名称。
- `ts`：开始时间或 B/E 时间戳。
- `dur`：仅 `X` 事件需要。
- `pid` / `tid`：进程和线程维度，建议保留。
- `args`：可选，若包含 `core_type/core_id/rank_id/extra_id/event_id` 等字段，报告会一并保留。

不匹配 `--phase-map` 的事件当前不会进入 phase 统计表。分析非默认 trace 时，最重要的适配工作就是维护一份能覆盖目标 trace name 的 phase mapping。

分析时会同时保留：
- `name`：原始 trace name。
- `normalized_name`：去掉 `[extra:x] #seq` 后的归一化名称，便于把同一类事件合并统计。

## Phase 和 Category

本 skill 通过 `--phase-map` 指定的 YAML 配置把原始 trace name 映射到稳定 phase。配置包含两类信息：
- `phases`：phase 到正则 pattern 列表的映射。
- `phase_categories`：phase 到 category 的归因。

正则命中多个 phase 时，优先选择 pattern 字符串最长的更具体规则。

默认 category 包括：
- `container`
- `wait`
- `sync`
- `compute`
- `epilogue`
- `communication`
- `quant`
- `init`
- `cleanup`
- `other`

对于 UMDK FusedDeepMoe，默认配置已经覆盖 `processing`、`dispatch_gmm1`、`gmm2_combine` 及其子阶段。对于其他 trace，可以保留这套统计框架，只替换 phase/category 映射。

## Core Group

本 skill 会尽量为每个已映射事件补充：
- `core_type`
- `core_group`
- `core_kind`
- `core_id`

当前内置的核组解释来自 UMDK 1C2V trace：
- `type0 -> cube`
- `type1 -> vector_recv`
- `type2 -> vector_send`

如果 trace event args 中没有 `core_type/core_id`，本 skill 会尝试从 `tid` 推断，例如 `type1_core003 -> vector_recv/core_id=3`。

对于其他来源的 trace，如果没有这类 `core_type` 约定，事件会落到 `unknown` 核组。后续若要支持更多硬件或 runtime，可以把 core group 规则从当前内置逻辑中抽成配置。

## 指标口径
- `total_us`：同类事件时长直接求和，会重复累计并行 tid/core。
- `union_us`：同类事件时间区间并集长度，更接近 wall time 覆盖。
- `ratio_to_total_wall = union_us / trace_wall_time`。
- `ratio_to_core_group_wall = union_us / 当前 core_group 的 union_us`，用于判断某类耗时在该核组内部的覆盖比例。
- `ratio_to_core_group_wall` 是覆盖率，不是互斥占比；不同 category/phase 可以在同一时间重叠，因此同一核组下的百分比不要求加和为 100%。
- `overlap_summary.csv` 的 overlap 基于 phase 区间并集两两求交，避免逐事件重复累计。
- `bubble_summary.csv` 表示外层阶段中未被已知子阶段覆盖的时间空洞。这是“未归因时间”，不一定代表硬件空闲。

## 诊断策略
报告优先回答：
1. 哪些 phase 覆盖 wall time 最多。
2. 耗时类型更偏 wait、sync、compute、epilogue、communication 还是 quant。
3. 耗时主要落在哪些 core group 或 tid。
4. 关键 phase 之间的 overlap 是否不足。
5. 外层阶段内部是否存在明显未归因 bubble。
6. top raw names 中哪些原始事件应优先回查。

当前确定性诊断仍包含一部分 UMDK FusedDeepMoe 经验规则，例如 `dispatch_gmm1` 与 `gmm2_combine` 的 overlap 判断。分析其他 trace 时，这些规则可能只具备参考价值；通用统计表和图表仍然是主要输出。
