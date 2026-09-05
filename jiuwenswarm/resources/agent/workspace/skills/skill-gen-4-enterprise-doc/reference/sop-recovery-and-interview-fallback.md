# 来源恢复与意图草稿

本参考仅在指定来源不可读或用户请求从意图生成技能时使用。

## 来源恢复

区分目标：
- 要求忠实转换某份 SOP：先核对已提供路径、授权位置及已知替代链接/正文；可做一次有依据的恢复。仍缺正文时简洁说明失败并请用户提供可读材料，不能把意图模板称为该 SOP 的转换。
- 已明确接受从聊天意图起草：直接复用现有背景，不需要先表演一次文件恢复或访谈。
- 只缺非关键细节：以标明的合理假设继续；涉及政策、审批、账户权限或业务关键字段的缺口不猜填。

澄清聚焦会改变结果的信息，可一起询问；不要求固定问答次数。已有回答和授权持续有效。用户暂未回复不等于同意替换来源、降级权威或安装覆盖。

## 意图结构

生成意图模板使用 `await skill_gen.sop_fallback.build_intent_fallback_sop(user_intent=..., skill_name_hint=..., invoke_llm_json=...)`。有模型时执行内部 enrich；不可调用模型时使用 None 或 `build_fallback_sop_structure`。这一路仍需实际 SOPStructure 和 extraction_meta，不手写假结果。

模板说明目标、已知输入/输出、角色、步骤/知识规则、分支和例外；仅补执行所需信息，不填造政策。保留 fallback_sop 标记，在 `reference/intent-sop-snapshot.md` 写警示和原始 raw_text。未解决的关键业务决策留作待确认边界。

## 来源说明

生成技能保留 `## Source and provenance`，清楚说明实际依据及限制，可用一个主来源标记：
`source:document_file`、`source:document_url`、`source:document_paste`、`source:interview_surrogate` 或 `source:intent_only_chat`。若先前读取失败再用其他材料，标记最终实际用于起草的来源。

这是写作及审阅要求，不是当前脚本已实现的 provenance 检查：本目录 CLI 目前只有 sop-text/url-fetch；不要调用不存在的 validate-skill 子命令或 skill_gen.provenance。使用实际 `skill_gen.validator.validate_skill` 作元数据检查，人工核对来源、关键规则和链接。
