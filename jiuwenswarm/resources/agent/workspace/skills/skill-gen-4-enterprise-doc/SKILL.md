---
name: skill-gen-4-enterprise-doc
description: 将企业 SOP、文档、链接或明确的业务流程意图生成可用技能包，并在可用且已授权时导入运行时。
---

# 企业文档生成技能

从用户材料生成可执行技能，而不是仅写文档摘要。保留来源里的角色、输入、规则、例外与交付物；不得将聊天推测冒充企业政策。

按当前输入选择路线：
- 有文件/粘贴正文/网页文本：读 [结构化提取](reference/sop-structure-pipeline.md)，生成真实 SOPStructure。
- 来源缺失或只有意图：读 [恢复与意图草稿](reference/sop-recovery-and-interview-fallback.md)。已有上下文足够时不安排固定访谈；忠实复现指定但不可读 SOP 所需正文不能靠猜测替代。
- 起草目标包：读 [生成规范](reference/generator-worker-spec.md)。
- 路径、CLI 或导入：读 [操作说明](reference/operator-playbook.md)。

默认将包写到实际 Agent workspace 的 `skills-draft/<name>`，保持 YAML frontmatter 的 name/description 和明确完成条件。目标是可加载包：运行时提供 `skills.import_local` 且任务授权安装时在同一流程导入；只要求草稿时不安装。已有同名技能仅在授权替换时用 force。

缺少提取、模型或导入能力时，继续能完成的材料整理/草稿工作，清楚标明结构化提取或安装未完成，不伪造工具结果。不修改本元技能、脚本或其他现有技能来绕过限制。
