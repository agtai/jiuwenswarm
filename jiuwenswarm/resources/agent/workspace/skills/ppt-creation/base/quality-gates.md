# PPTX 质量检查

检查服务于文件可用性、用户要求和来源保真，不规定统一版式或字数。

## 检查范围

- FULL：结构/文本/几何检查及实际渲染查看。
- TEXT-ONLY：渲染工具不可用时完成可执行的结构/文本/几何检查，交付明确未视觉核验。不能把未查看的缩略图算视觉检查。
- 狭窄编辑检查受改动页面和布局依赖，并确认保留要求；新建/重设计检查整套结构与逐页视觉可读性。未变页面已有有效证据可复用。

## 必须处理的问题

PPTX 损坏、页数错误、资源/关系缺失、placeholder/示例数据残留、用户要求保留的 Master/Layout/备注/批注丢失；模板画布和继承不符；封面标题为空；真实文本重叠、遮挡、越界、截断、不可读或图片拉伸；数据/引用失真或 AI 视觉冒充事实。

当前模板结构以 references/template.pptx 实测为准，不套旧模板 4 Master/7 Layout 或右下 Logo 数量规则。默认模板不含 Logo，固定总结条/页码不得重复。

新建契约流程需 validate-evidence-plan 和 validate-execution-lock 的对应阶段通过；所用资产应 ready/used 且审核状态真实。paper-figure 已使用时 audit_pptx --evidence-plan 按图像哈希检查同页来源文字；使用 addSourceNote，不删除检查参数规避。

qa_geometry.py 的 text-collision/occlusion/duplicate-chrome/out-of-bounds error 必须处理；axis-drift/summary-intrusion warning 结合实际页内容核对。结构检查和缩略图不能替代细小几何检查。

## 可选设计诊断

稀疏度、构图重复、Hero 页、字数和骨架使用是设计判断。qa_density.py 仍保留旧的 <300 EMPTY、300–400 LOW、400–700 目标及非零退出行为；它是可选内部密度启发，不代表几何错误或本任务未完成。若使用它，报告真实结果及适用性，不把失败输出改称通过，也不为凑字数编造事实。

## 命令

使用实际技能/项目绝对路径。依需要运行：

```bash
node <skill>/scripts/validate-execution-lock.js <project>/execution-lock.json --phase deliver
node <skill>/scripts/validate-evidence-plan.js <project>/evidence-plan.json --phase deliver
python <skill>/scripts/audit_pptx.py <output.pptx> --template <template.pptx> --lock <execution-lock.json> --evidence-plan <evidence-plan.json> --report <qa-report.json>
python <skill>/scripts/qa_geometry.py <output.pptx>
python <skill>/scripts/opc/thumbnail.py <output.pptx> <qa-prefix> --cols 4
```

实际生成/打包沿 [工程安全](pptx-safety.md) 的 XSD/关系检查；不使用 --validate false。有 soffice/pdftoppm 时渲染并查看相关页面，修复后只重验受影响范围。

交付所需 PPTX，说明实际 QA 模式、素材来源、未完成验证和影响使用的缺口；不额外输出用户没要求的中间产物。
