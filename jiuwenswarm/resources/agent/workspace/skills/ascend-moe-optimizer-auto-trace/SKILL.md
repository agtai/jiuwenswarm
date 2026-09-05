---
name: ascend-moe-optimizer-auto-trace
description: 为 Ascend 算子接入 TRACE_POINT/MoeTracing 插桩及 profiling 到 Chrome trace 的采集链路。
---

# Ascend 算子插桩

处理目标算子的 profiling，不改业务计算或通信语义。普通性能讨论、已有 trace 解读或经验记录不自动触发代码插桩/技能自修改。

先从请求和工程确定目标算子、当前构建源码树和交付范围：
- 完整采集链路：包括点位、profiling 输出、预处理、构建和既有 sample/UT 的落盘对接。
- 明确仅源码点位或本次局部修复：只改约定边界，并注明尚未证明完整采集。不要为完成局部任务静默扩大 Op/pybind 变更。

实现时读 [插桩与集成](references/integration.md)。只有需要缓冲区模板、硬件参数、命令细节或故障解释时，查 [reference.md](reference.md) 的对应章节，不整本顺读。

保留以下不变量：
- 同一 Op / `torch.ops` 注册名，不新增 `xxx_profiling` / `*_with_profiling` 第二入口。
- 根标签 `processing`、最大深度 7、稳定且嵌套正确的 B/E。跟进同算子实际编译的 AIC/AIV 与角色调用路径；阶段循环和热点保留点位，tile 内层不堆点。
- profiling 是最后一路 Tensor 数据输出，host/infer/tiling/核/aclnn/pregen/pybind 顺序一致。
- OPTIONAL 模式可保持返回 arity；REQUIRED 模式必须传实张量，禁止 nullptr 绕过。设备写入开关用 `ENABLE_MOE_PROFILING` 并重编核。
- 采集先同步设备，再落盘；`point_map.json` 与当前 OPP/核同源；路径在 spawn 前 expanduser/resolve。
- 优先扩展现有编译脚本和 sample，保留数值测试主路径。

完整链路完成须有 G1 同源预处理、G2 输出对齐、G3 实际完整构建、G4 同步后保存/解析、G5 绝对路径证据。局部任务只验证受影响边界；未执行的构建、硬件运行或 Chrome 解析明确列为未验证，静态检查通过不等于完整闭环。
