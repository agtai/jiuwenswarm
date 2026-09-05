---
name: ascend-moe-optimizer-trace-analyzer
description: 分析 Ascend/MoE 算子导出的 Chrome 或 Perfetto trace，统计阶段、核组、overlap 和未归因时间。
---

# Ascend Trace 分析

从用户指定的 trace 输出统计与诊断，不自动修改算子。已有 trace 可独立分析；只有任务提供源码或需要解释点位时才读对应源码。

- 运行 CLI、输出目录和可选图表/LLM：[运行与产物](references/analysis-run.md)。
- 输入格式、phase 规则、核组和指标解释：[指标口径](references/metrics.md)。

使用本目录 `app.py`，将输入/输出路径替换为实际绝对路径。默认 `config/phase_map.yaml` 面向 UMDK FusedDeepMoe，不把它当作所有 trace 的通用语义。非默认 trace 优先采用用户已有映射；未映射事件会被过滤，需说明覆盖缺口。

`total_us` 累加可重复计入并发；`union_us` 表示时间覆盖。覆盖率不要求总和为 100%；bubble 是未归因时间，不证明硬件空闲。默认核组/部分诊断有 1C2V 和 FusedDeepMoe 假设。

先交付确定性统计；matplotlib 或外部 LLM 不可用不阻塞已成功生成的 CSV/Markdown。外部 LLM 仅在请求/授权范围内启用，记录状态，不把推断写成测量事实。缺少真实结果时不得声称优化收益或硬件验证完成。
