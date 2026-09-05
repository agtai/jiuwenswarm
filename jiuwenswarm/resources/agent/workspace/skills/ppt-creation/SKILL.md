---
name: ppt-creation
description: 创建、读取、编辑或检查 PPTX 演示文稿，保留所选模板、可编辑内容和来源证据。
---

# PPT Creation

按用户要的产物选择路线，读取/问答不启动整套制作：

- 读取/提取：检查已有文件的相关页面、文字和图表，回答实际问题。
- 新建：[创建流程](workflows/create-deck.md)；选择模板时读 [模板契约](base/template-contract.md)。
- 编辑既有文件：[编辑流程](workflows/edit-existing.md)，以用户文件为结构事实来源。
- 实际生成 PPTX：[工程安全](base/pptx-safety.md)；外部事实/素材才读 [来源规范](base/sourcing.md) 和 [素材获取](workflows/acquire-visuals.md)。
- 交付前按范围读 [质量检查](base/quality-gates.md)。

用户模板、页数、结构与用途优先。默认 template-master 路线在 10×5.625 兼容坐标创作内容，再由 finalize_deck.py 合并；当前默认空白内容布局是 slideLayout7.xml，模板的 Master/Layout 数量以实际文件为准。不要重复缩放或重画母版已继承元素。

硬约束是结构有效、可编辑、几何/文字可读性和来源保真。默认模板内容页的主题色总结条与页码只出现一次，不自行加 Logo；用户模板另按其契约。论文原图保持比例/内容，真实数据可追溯，不用 AI 插画冒充证据。当前 audit_pptx 的论文原图检查要求页面来源注记，不能用“页面默认无来源行”覆盖实际检查。

版式、组件、Hero 页、固定字数、区域数与叙事模式是设计选项，不是普遍交付门槛。不为满足配额填充空话或改用户结构；只读取与本页内容有关的版式/组件参考。

交付 PPTX 与必要的来源/限制说明，明确 QA 模式。缺渲染工具可交付通过结构/文本检查的文件但标明未视觉核验；文件损坏、缺关键素材或真实几何错误不能用降级标签掩盖。
