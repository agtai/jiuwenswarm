# Task / Work 统一后的生产代码量

> 2026-09-13。统计源码，不统计测试、文档、配置、二进制、依赖或构建产物。物理行包括注释和空行；这不是可执行语句数。

## 1. 两阶段相同口径

官方兼容基线：JiuwenSwarm `8c7bfecdf0cc7607b07763fe687e08bf24f6ab83`；AgentCore `b5f189ba1054a338d8fa3e009b13053776340e44`。
“新增文件行数”只统计本分支引入文件的当前行数；“净增量”也包含原有文件的增加和删除。改过的整个上游文件不能算成新增代码。

| 阶段 | 分类 | 新增文件中的当前行数 | 相对官方基线净增量 | 所有受影响文件当前总行数 |
|---|---|---:|---:|---:|
| Task 统一后 | Voice 专属路径 | 113,424 | 113,424 | 113,424 |
| Task 统一后 | JiuwenSwarm 应用/共享 | 41,499 | 49,741 | 152,256 |
| Task 统一后 | AgentCore 新增 | 32,504 | 32,504 | 32,504 |
| Work 统一后 | Voice 专属路径 | 113,422 | 113,422 | 113,422 |
| Work 统一后 | JiuwenSwarm 应用/共享 | 40,235 | 48,477 | 150,992 |
| Work 统一后 | AgentCore 新增 | 33,781 | 33,781 | 33,781 |

Work 阶段相对 Task 阶段：Voice −2，JiuwenSwarm −1,264，AgentCore +1,277 行；三者合计净增 11 行。迁移、协议复用与应用依赖注入改变所有权，不意味着删除等量功能或总行数显著下降。

Voice 分类按专属目录/文件命名；公共 schema 和 `server/runtime` 归 JiuwenSwarm。它包含保留的 Native、Cascade、批量语音与诊断，不是只计算当前 Native 热路径。Host 适配中也有语音集成逻辑，因此该分法是可复现的文件所有权口径，不能解释成每行语义都完全通用。`live-voice/` 目录只有架构、验证与支持资料，没有该口径下的生产模块。

## 2. 合并后的模块统计

每个受影响生产文件按主要职责只归一组。AgentServer 是运行容器，不重复计数；云端模型代码不在仓库，不计数。横向公共层单列，避免把巨大共享文件硬塞给某个语音模块。

| 展示模块/归属组 | 新增文件当前行数 | 相对基线净增量 | 受影响文件当前总行数 |
|---|---:|---:|---:|
| 浏览器 M1+M2 | 45,086 | 45,931 | 70,775 |
| Gateway G | 18,198 | 19,581 | 38,416 |
| Realtime/语音适配 M3 | 14,427 | 14,427 | 14,427 |
| 会话与业务协调 M4+M5 | 39,647 | 39,647 | 39,647 |
| 工作管理 M6+M8 | 37,713 | 37,713 | 37,713 |
| Agent 与项目执行 M7+M9 | 12,875 | 17,009 | 51,029 |
| 公共契约、授权、配置、观测与 Host 装配 | 19,492 | 21,372 | 46,188 |

这些是文件粒度的职责分桶，不是逐函数测量。例如前端 Task UI 归浏览器，SDK file-effect/durability 归执行，SDK 状态和存储归工作管理；M3 同时包含保留的非 Native 语音适配。大型 Registry 主要归会话协调，实际同时承担装配。需要精确定位时查看逐文件清单，而不是把展示框大小理解为独立部署包大小。

## 3. 可复现证据

- [Task 阶段逐文件清单](../evidence/TASK_UNIFIED_CODE_COUNTS_20260913.json)：Task 阶段已冻结。
- [Work 阶段逐文件清单](../evidence/WORK_UNIFIED_CODE_COUNTS_20260913.json)：包含每文件基线/当前、增删与 SHA-256。
- [Work 阶段模块分桶](../evidence/WORK_UNIFIED_MODULE_COUNTS_20260913.json)：每个文件唯一归属，可汇总回同一个总数。
- [所有权统计脚本](../../scripts/live_voice/code_ownership_counts.py)与[模块分桶脚本](../../scripts/live_voice/module_code_counts.py)。

```powershell
python scripts/live_voice/code_ownership_counts.py --stage work-unified --output live-voice/evidence/WORK_UNIFIED_CODE_COUNTS_20260913.json
python scripts/live_voice/module_code_counts.py live-voice/evidence/WORK_UNIFIED_CODE_COUNTS_20260913.json live-voice/evidence/WORK_UNIFIED_MODULE_COUNTS_20260913.json
```
