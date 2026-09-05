# 新建 PPTX

## 工作区与计划

任务工作区放在技能目录之外，例如 workspace/projects/<task-name>。sources、analysis、assets、output、qa 均留在该工作区，不污染共享技能。

复用用户材料和已有上下文，确定受众、页数/时长、语言、结构和核心信息；只问影响内容或范围的缺口。design-spec.md 可简洁记录这些决定及逐页内容/来源/布局；参考 [设计记录](../base/design-spec-reference.md)，不强制七章或 Hero 配额。

## 机器契约

新建模板流程保留现有 evidence-plan.json 和 execution-lock.json schema。以 [证据模板](../base/evidence-plan.json)、[执行模板](../base/execution-lock-reference.json) 及相邻 schema 起步，记录实际页面、资产、来源、状态和 fallback。不用 YAML/Markdown 代替这两个 JSON。

逐页的 role/core_message/rhythm/visual_strategy/component_policy/composition/evidence_visual 等按当前 schema 填写；dense/anchor 内容页无 reference_ids 时，按现有校验器提供具体 reference_waiver，不伪造参考。素材通过 asset_ids 引用 evidence plan，状态使用 planned/acquiring/ready/used/needs-manual/skipped。

以下命令的 <skill> 和 <project> 都替换为实际绝对路径：

```bash
node <skill>/scripts/validate-execution-lock.js <project>/execution-lock.json --phase design
node <skill>/scripts/validate-evidence-plan.js <project>/evidence-plan.json --phase design
```

修正真实契约错误后再生成。选择骨架时只检查 references/index.yaml 的相关项；采用某项则查看它的 image 和规则。骨架不合适可按内容设计并如实记录 waiver。

## 素材与制作

需要素材时按 [素材获取](acquire-visuals.md) 执行 prepare_evidence.py；查看实际 contact sheet 后 --approve <id>，投入页面后 --used <id>。没有资产需求也保持符合 schema 的空计划，不虚构素材。获取失败时采用计划内可接受替代并同步两个契约；不能替代的必要证据留为缺口。

默认内置模板用 10×5.625 内容坐标，按 [工程安全](../base/pptx-safety.md) 保持可编辑对象和独立 options。可先试一张代表页以发现系统性问题，已验证路径不需重复试做。整套保持统一模板/字号语义，组件按需，不强制顺序写页或固定图文比例。内置模板标准内容页使用一次 Brand.addContentChrome(pres, slide, { summary, pageNum, footerMode: "master" })，内容结束在兼容坐标 y=4.65 以上。用户模板的坐标、母版元素与留白以实际模板契约为准。

内置模板默认 finalize_deck 顺序为 t1,s*,t5：模板封面、生成内容页、模板结尾。content.pptx 不重复生成模板封面/结尾，execution-lock.pages 包含实际最终页数。用户模板必须传实际 --template，并按其布局和页序选择 --template-layout / --order；不能因省略参数而合并回内置模板。用户要求其他顺序/无封面结尾时同步计划。

```bash
python3 <skill>/scripts/finalize_deck.py <project>/output/content.pptx <project>/output/final.pptx --template "<所选模板绝对路径>" --template-layout "<该模板的内容布局>" --order "<实际页序>" --cover-title "<实际标题>" --cover-meta "<部门>|<作者>|<日期>"
```

--cover-title 对包含模板封面的输出必填；--cover-meta 只填用户确认/提供的真实信息。内置模板默认 layout 是 slideLayout7.xml，source-layout-mode=template；其他模板先检查实际布局，不能机械套用 layout7。finalize 内部完成 unpack/merge/fill/clean/pack，失败定位时才 --keep-workdir，不重复手工缩放。

执行 --phase generate 和 --phase deliver 的两个契约校验；具体 [质量检查](../base/quality-gates.md)。修复实际缺陷后验证受影响页面，Hero 精修仅在确有表达收益时进行。
