# 素材审核与技能输出

## 首次写入前的目标核对

`save_images.py` 默认写入本技能的同级 `skills/<slug>/`，不是临时草稿目录；
同名图片会被覆盖。先解析完整目标，确认 slug 是单个目录名且目标在用户指定
的输出根内。新建任务遇到既有技能时另选名称；指定名称或更新任务的替换范围
仍不明确时，先完成独立可做的材料整理，再只询问缺失的替换授权。已有明确授权
不重复询问。不要覆盖无关文件或仅凭同名目录推断授权。

用户选择其他输出根时，用 `--skills-dir <absolute-output-root>`，并在后续
`finalize_scripts.py` 中传同一根。写入前核对，脚本打印路径后的检查不能撤回覆盖。

## 网页图片

```bash
{python} "{skill_directory}/scripts/prepare_images.py" <slug>
{python} "{skill_directory}/scripts/image_review.py" <slug> --first-pass KEEP SKIP SKIP
{python} "{skill_directory}/scripts/save_images.py" <slug> --skills-dir <verified-output-root> --keep <returned-paths>
{python} "{skill_directory}/scripts/print_blocks.py" <slug> --stage stage03
```

prepare_images 串行下载完成再打印 stage02。只根据代表视图的 alt 和周围文字一次标记 KEEP/SKIP，数量必须匹配；上下文不能证明价值时 SKIP。不要读/列举 raw_images、原始 stage JSON 或用 bytes/base64 绕过限制，也不要把 alt 筛选称为图片视觉核验。

image_review 输出 KEEP_PATHS_ARGS，原样传给 save_images。无图片时用 save_images.py <slug> --skills-dir <verified-output-root> --keep；仍须门禁成功。它生成 stage03，打印 SKILL_MD_PATH 及真实图片路径。视频选中帧也经 save_images，不能直接引用审核 JPEG。

## 输出

最终写入脚本打印的 SKILL_MD_PATH。输出文件从 YAML frontmatter 开始，name 使用当前流水线约定的小写 snake_case，description 简短描述能力/触发；正文默认简体中文，用户指定其他语言时遵从用户。

将已证实步骤按实际主题组织：网页可沿 h2/h3，视频多子功能可分组，单一流程用连续步骤。合并重复步骤和选项演示，不把展示所有选项误写成全部执行。保留完成任务必要的前提、条件分支、警示、故障处理；不添加源材料没有的平台/参数/工具。

图片只引用 stage03 或 save_images 的真实 path。网页已保留的有效图片按原文关联位置使用；视频帧放相关步骤后，不要求每步配图。图片独占一行并留空行，不缩进到列表项中，不发明/改名路径。不加无关来源导航或广告；需要出处/使用权说明时保留真实来源，不声称不存在的许可。

是否需要可执行脚本由材料和任务决定。只引用已验证并经 finalize_scripts 保留的脚本；无幸存脚本则写文本/图片版并说明执行能力缺口。文件内不加对话前言，交付消息可简述结果和限制。
