# SOP 结构化提取

有 SOP 正文时，使用 `skill_gen.sop_parser.parse_sop_file` 或 `parse_sop_raw_text`，传入可用的 `invoke_llm_json`。实现根据 parse_options 选择单次/分块 map-reduce 和 reconcile，参数以当前函数签名为准。

字段与提取提示词只在 `scripts/skill_gen/sop_parser.py`、`sop_chunk_merge.py` 中维护，不另造竞争性提取 schema。输出应包含真实 SOPStructure 的 title、purpose、scope、roles、steps、knowledge_items、sections、decision points、exceptions、references、raw_text 与 extraction_meta。

CLI 的 `sop-text` 只提取文本，`url-fetch` 返回页面文本和元数据；两者都不产出 SOPStructure。模型接口不可用时，说明结构化提取尚未执行，不把正文或手写 JSON 称为解析器结果。

没有正文时按 [恢复与意图草稿](sop-recovery-and-interview-fallback.md) 判断是否能从已授权意图起草。该路线使用真实 `build_intent_fallback_sop`；有模型时传 invoke_llm_json 进行内部 enrich，无模型时可用 None 或同步 `build_fallback_sop_structure`。不要把空文本传给 parse_sop_raw_text。

fallback_sop 始终表示意图模板，即使经过 LLM 润色也不是权威 SOP。起草时保留 `reference/intent-sop-snapshot.md`，包括警示和同一对象的逐字 raw_text。随后按 [生成规范](generator-worker-spec.md) 起草，按 [操作说明](operator-playbook.md) 验证并导入可用运行时。
