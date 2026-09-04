# Live Voice 语义 t=0 受控并行：同基线 A/B 实测 — 2026-09-04

> 分支 `hx/0903_live_voice_latency`（w3 `2aef1f533` + 4 项 P0/P1 + t=0 受控并行 `2f2b5ef8e`）。
> 对照组与处理组同一部署源 `855fcf8bf`，只差运维开关 `LIVE_VOICE_DIALOGUE_SPECULATION`（off / 默认 on）。
> 数字不是 SLO；n=5，p99≈max；同一小时内 Provider 波动 ±0.3s。

## 1. 设计（按用户定义的受控版）

- **推理提前、执行不提前**：submit 通过身份/权限/重复请求检查后，候选对话推理与语义决策同时启动。候选在 runtime 之外以影子推理运行（自有 `lv-formal-spec-*` 会话），其工具调用在下层适配器的 stream-event rail 上按会话暂停，暂停先于第一次模型调用；候选不存在于 CR 响应、Bridge 派发、journal 效果、history、通知中的任何一处。
- **语义决策仍是最终路由**：对话决策照常派发正式回合；回合预约钉住"接入候选"的 facade，正式回合把候选的缓冲前缀与实时尾巴接过来并恢复工具。任务、澄清、失败、commit/context/工具策略不一致、候选超限或失败、runtime 关闭、回合提前关闭 → 丢弃候选：取消模型工作、中止暂停中的工具，迟到输出无法生效。
- **首批范围**：无待决语义上下文、作用域无 Task（Store 级计数，不增加鉴权读）、非 native 提交；runtime 每会话 2、registry 全局 4 的并发上限，满则串行；任何启动失败都是原串行路径；`LIVE_VOICE_DIALOGUE_SPECULATION=off` 强制串行。
- 理想节省 `min(S, A)`：S 为完整语义决策耗时，A 为 Agent 产出首个可 TTS 片段的耗时。

## 2. 验证

- 单测 19 条（模块 9、runtime 4、registry 6）；两个反向变异体（丢弃不中止工具 → 5 条变红；未使用候选不丢弃 → 1 条变红）。
- 回归：受影响 11 个套件 496 通过，registry 的 61 个既有失败同集合、零新增。

## 3. 方法

- 停服务 → 还原一次性项目 → 部署 `855fcf8bf`，`LIVE_VOICE_DIALOGUE_SPECULATION=off` → 6 档 × 5 轮（short / medium / long / tool / task / clarify）→ 重新部署（开关默认 on）→ 同样 6 档 × 5 轮。
- 口径同前：说完（最后一个非静音帧）→ 下行首帧；浏览器尾巴另算。
- 新增 `clarify` 档："帮我后台处理一下。"，语义契约要求走澄清，是投机的丢弃路径。
- 投机信号由 `scripts/live_voice/latency_speculation_report.py` 从 swarm 日志统计：启动/接入/按原因丢弃、接入时首块提前量、丢弃调用的 completion token（best-effort）。

## 4. 结果

【待填：两组的总用时表、分段表、路由正确率、投机报表、错误分支副作用检查】
