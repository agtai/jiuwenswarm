---
name: harmonyos-dev-suite
description: 为 HarmonyOS/OpenHarmony 项目提供 ArkTS、ArkUI、构建、设备调试和专项技能路由。
---

# HarmonyOS Dev Suite

用于实际 HarmonyOS/OpenHarmony 开发任务；普通 app、日志、模拟器或测试请求不会仅凭关键词进入此技能。

从用户路径和 `build-profile.json5`、`oh-package.json5`、`module.json5`、`.ets` 等识别目标工程。仅解释问题可直接回答；构建、修改、设备操作前需确定目标，复用已有上下文而不重复询问。

- 普通开发、构建或排障：按 [workflows.md](references/workflows.md) 选择相关段落。
- 只有需要专项能力时，搜索 [原子技能目录](references/atomic-skills-catalog.md) 的相关项；不默认通读或安装全目录。
- API 不确定时，优先使用可用的官方 `searchDocuments` / `getDocumentsById`；后者每次最多 10 篇，只取相关文档。缺失时用现有 `devecocli docs search/read`，并说明无法验证的部分。

构建、设备、模拟器和日志命令优先使用 `devecocli`，具体参数先查当前 help。长时间跟踪日志、启动模拟器和安装应用须在任务范围内。缺少 CLI 时可继续源码分析和文档工作；改用直接 hvigor/hdc 的实际执行沿用用户已有授权，否则明确所需替代步骤。

可选原子技能仅在用户请求安装该专项技能时安装。安装器为 [install_atomic_skill.py](scripts/install_atomic_skill.py)，其 `--source` 是已有技能源目录，`--target` 为实际技能根，`--skill` 为目录中的确切名称。源必须包含 SKILL.md，目标必须留在技能根内；不静默覆盖其他技能。安装后只在运行时不自动刷新时刷新索引。

交付代码/命令结果和验证范围；源码检查不能冒充设备运行、应用安装或稳定性验证。
