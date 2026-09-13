# D107 W3 develop 换基线迁移审核与收口 — 2026-08-12

> 本文是一次性迁移与审核记录，记录 `hx/0803_live_voice` →
> `hx/0812_live_voice_w3` 的 develop 换基线结果、迁移后纠偏和验证边界。
> 当前可变状态仍只由 [STATUS.md](STATUS.md) 拥有。

## 1. 结论

`hx/0812_live_voice_w3` 已经是完成过历史重放的 W3 迁移候选。本次工作是在该候选上审核和收口，**没有重新执行第二次迁移**。

初始附件对分支拓扑、8 个提交的分层和主要冲突类型总体描述正确，但不能作为最终完成记录直接接受，主要原因是：

1. 把 develop 删除或替代的不同对象统一归类为“补回”，违反了其中两个删除决策和一个 API 迁移方向；
2. 把公共 `start_interaction` 从 develop 的失败传播契约收窄为非严格模式；
3. 依赖环境未同步，7 个目标模块不能收集，却同时宣称最终状态通过完整测试；
4. `810 passed` 只可能是当时可运行的子集，不是完整 Live Voice 目标集；
5. “12 个冲突文件、84 个冲突块”等过程统计没有随可复核日志进入仓库，当前 merge-tree 重建也不能完整复现；
6. 将现有任务子系统概括为“三个调度器”过强。准确说法是三个任务/存储概念并存，它们不都是同等性质的调度器。

完成本记录的本地提交所包含源码即迁移收口树；最终 SHA 在提交后由 Git 解析，不在同一提交内预写不可自证的 commit id。

## 2. 初始迁移候选

| 项 | 可复核事实 |
|---|---|
| W3 分支 | `hx/0812_live_voice_w3` |
| 迁移候选 | `3d5409830a96f7ebd419cf234c780e68f05cf6b7` |
| develop 基线 | `3f3cdbb7f` |
| 拓扑 | 相对该 develop 基线 `8 ahead / 0 behind` |
| 候选变更量 | 324 files, +186,017 / −602 |
| 旧特性冻结点 | `a97005786` |

候选的 8 层提交保持原有顺序：shared v2、Gateway Speech/Media、Server/Observability、Runtime Session、AutoHarness/Task、Web、Registration、Documentation。该历史不是本次重做的对象；本次只修正最终树与当前 develop/agent-core 的不一致。

## 3. “develop 删除了 4 个对象”的逐项判定

| 对象 | develop 的真实变化 | W3 初始做法 | 收口处理 |
|---|---|---|---|
| `resolve_project_coding_memory_workspace_path` | 已迁移/替代。develop 用 `resolve_project_coding_memory_dir(agent_workspace_dir, project_dir)` 将 Coding Memory 放到 Agent application workspace | 恢复旧 helper，并为 ordinary/formal 路径保留两套行为 | 删除恢复的 helper；所有 Code Adapter 路径统一调用当前 API |
| `get_prompt_attachment_dir` | 有意彻底删除。develop 不再创建未使用的 `prompt_attachment` workspace 目录 | 恢复 3 行 helper | 删除 helper；不再创建该目录 |
| `prompt_attachment_loader.py` 及其测试 | 有意彻底删除旧文件热加载能力；当前 `PromptAttachmentManager` 是另一套内存上下文能力，不是该 loader 的迁移目标 | 整个模块和旧测试被恢复 | 删除恢复的模块、调用点和测试，不用名称相似的新组件冒充等价替代 |
| `ReqMethod.SYMPHONY_*` → `SKILLS_GRAPH_*` | 枚举改名迁移 | 合并时已正确吸收新名称 | 保持 `SKILLS_GRAPH_*`，不恢复旧枚举 |

因此，问题的答案不是统一的“完全删除”或“全部迁移”：

- 文件热加载相关两项是彻底删除，Live Voice 不应继续依赖；
- Coding Memory helper 是迁移到新的 application-owned 路径 API，应改调用方，而不是补回旧接口；
- 请求枚举是改名迁移，应使用新名称。

该规则由 D-073 固化，防止下一次换基线再次恢复已退役对象。

`project_code_executor.py` 中的 `ProjectCodeExecutorAdapter` 不属于上述 4 项。当前生产 P3 组合使用 `DirectProjectCodeExecutorAdapter`；前者仍是有测试覆盖的兼容 Adapter。本次不把“非生产组合”误判为“无引用即可删除”，后续如要移除应单独做调用方与兼容范围审核。

## 4. 迁移后源码纠偏

除第 3 节的对象处置外，本次还完成以下兼容性修正：

1. 公共 `start_interaction` 恢复 develop 的 fail-closed 行为，启动失败继续向上传播；内部按名调用所需的 `_start_interaction` seam 保留。
2. 最新 agent-core 已用 `ModelAnomalyDetectionRail` 替代 `LLMRetryRail`。JiuwenSwarm 保留现有 `execution_guard.llm_retry_rail` 配置键作为自身兼容面，但构建当前 rail 类型，并关闭 factory 的默认同名 rail，避免重复安装或 feature-off 被绕过。
3. Deep 与 Code 两种模式都显式安装上述兼容配置所构建的异常检测 rail；同时把 agent-core factory 默认项关闭，避免 Code 模式在去重时意外丢失保护。
4. Code Agent 的 `.agent_history` 治理改用 agent-core 公共 `get_agent_history_root()`，不再修改已不存在的工具私有 `_workspace_path`，也不再复活 develop 已删除的项目 `.gitignore` 自动写入行为。
5. formal/ordinary Code Agent 的 Coding Memory 都遵循 develop 的 application-owned workspace 规则。
6. D90 集成夹具补齐与 committed ledger 完全一致的 `interaction_id`，继续保持 voice mutation 的精确 origin 校验。
7. Windows 满载回归中的 worker-settle 测试等待保持有界，并从 2 秒放宽到 5 秒，避免把健康但稍慢的后台清理误判为产品失败。
8. Task Store 的并发初始化在切换 SQLite WAL 时执行有界 lock 重试；成功必须确认实际模式为 `wal`，超时或其他数据库错误仍 fail closed。
9. ordinary Session 启动失败继续按 develop 契约向调用方传播，同时在清理成功时撤销预发布 child，使下一次调用可重试；formal profile 或清理自身失败时仍保留精确 child owner，等待严格清理，避免孤儿运行时。
10. `uv.lock` 将 openjiuwen develop 快照从 `3a6deda8` 同步到 `94e10cb6`；该快照提供当前 `rsi`、`symphony`、rail 和 history-root API。

## 5. 验证

所有命令在迁移收口树上执行：

| 检查 | 结果 |
|---|---|
| `pytest tests/unit_tests/live_voice tests/integration/live_voice` | **1211 passed, 2 skipped**；1213 项全部成功收集 |
| 最终受影响的 Code/Deep Adapter、ACP Chat Tool、Agent history、formal executor 测试 | **49 passed**，1 个第三方 deprecation warning |
| Task Store 并发初始化重复验证 | **20/20 processes passed** |
| 前端 `test:live-voice-*` | **14/14 脚本通过，579 tests passed** |
| 前端 `tsc && vite build` | **PASS**，4638 modules transformed |
| 迁移失败点的单独复验 | **3 passed** |

完整目标集第一轮暴露 3 个问题：一个 Windows 负载相关测试窗口和两个 D90 旧 origin 夹具。最终审查后的全量复跑又暴露 SQLite WAL 并发初始化竞态；修复后该场景连续 20 次跨进程 pytest 通过，并再次完成上述 `1211 passed, 2 skipped` 全量复跑。

构建仍报告仓库既有的 i18n 重复 `empty` key、动态/静态 import、large chunk 警告；`npm ci` 报告 5 个 moderate 和 11 个 high 依赖审计项。它们未导致测试或构建失败，也不由本迁移引入，不能在本记录中宣称已解决。

## 6. D-053 三轮 review

1. **实现 self-review**：逐项比对 develop 删除提交、W3 最终调用面和 agent-core `94e10cb6` 公共 API；删除旧 helper/loader、过时私有属性适配和无效 import/test monkeypatch，并确认所有删除对象均无生产调用残留。
2. **cold complete-diff review**：在最终语义修复后重新检查本地提交候选的 22 个文件（含本记录）完整 diff，重点复核 ordinary/formal Session 失败所有权、Code/Deep rail 去重、Task Store WAL 并发、application-owned runtime paths、D90 origin 和被删除模块。未留下未处置 finding。
3. **独立 review**：Codex CLI `0.111.0` 使用 `gpt-5.4` 对未提交完整 diff 执行只读 review。预修复检查发现 Code 模式关闭 factory 默认 rail 后未显式加入 replacement rail；该 finding 已修复并新增回归。最终检查给出两项 P1，处置如下：
   - “ordinary public start 应恢复吞掉失败”不接受：`origin/develop` 的公开方法、docstring 和 warm-pool 契约均要求失败传播。其背后的失败 child 可恢复性风险已通过“普通路径清理后允许重试、清理失败保留精确 owner；formal 始终保留至严格清理”处理，并由 RuntimeError/CancelledError/cleanup-failure 测试覆盖。
   - “当前锁定依赖没有 `ModelAnomalyDetectionRail`”不接受：该判断来自 review 子进程误用仓库外全局 Python；`uv.lock`、仓库 `.venv` 和实际收集/测试均解析到 `94e10cb6102c36fe78a64547957c0def97299273`，该符号和 `get_agent_history_root()` 均存在。为旧的未锁环境加 fallback 会重新依赖已移除 API，违反本次迁移目标。

独立 review 的工具限制已记录：默认 review 模型与旧 CLI 不兼容，首轮高强度检查终止过慢；最终使用显式 `gpt-5.4`/medium 完成并输出 findings。findings 均有代码修复或可复核证据处置，最终 cold review 与受影响测试随后重跑。

## 7. 审核判断与限制

- develop 与特性树在 Task 领域是多个有边界的任务/存储子系统并存，不应在迁移中“顺手统一”。P3alpha 的事务身份、outbox 和重启对账仍由其正式边界拥有；`schedule.*`、Cron 和兼容 Adapter 不因此自动升级或退役。
- 初始附件的“23 个自动合并 + 12 个手工文件 = 36 个重叠文件”算术本身缺 1，且当前直接 merge-tree 重建观察到的冲突文件数不同。因此保留“冲突主要集中于少数共享文件”的定性结论，不把 `12/84` 当作已复核完成证据。
- 本批次是源代码换基线与自动验证收口，不是新的 Alpha 人工产品验收。D-071 下既有 W2 人工结果保持历史有效；若后续 Alpha 源码发生用户可见语义变化，仍按 Alpha acceptance 执行相应人工旅程。
- Git LFS 远端缺少 `docs/assets/videos/JiuwenSwarm_Introduction.mp4` 对象，正常 smudge 返回 404；本地通过跳过 smudge 保留 pointer 完成分支切换。该远端资产问题不影响 Live Voice 源码测试，但仍是 fresh checkout 的外部仓库缺口。
- 凭据、模型/Provider 配置、项目注册、浏览器权限/设备、运行数据库和网络状态仍是机器私有条件，不由本次 Git 迁移恢复。

## 8. 最终判断

附件结论为**部分正确，但“补回删除对象”和“完整验证已完成”两点不正确**。经过本次迁移后审核与纠偏，W3 源码已对齐 develop 的删除/替代意图和当前 agent-core API，D-053 三轮 review 已完成，目标后端、受影响 Adapter、前端测试与生产构建均通过。形成包含本文的本地提交后，本次迁移关闭；远端推送不在本批次授权内。
