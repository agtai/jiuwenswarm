---
name: skill-omni-creation
description: 将用户指定的网页教程或视频操作步骤转成带来源图片及必要脚本的可复用技能。
---

# 网页和视频生成技能

任务是创建可复用技能时使用；普通网页摘要或视频问答不自动写入技能目录。

从 skill_tool 返回的实际 skill_dir 定位工具，脚本用绝对路径调用；work 锚定在脚本目录，不能用当前 shell cwd 猜测输出。

只读所选路线：
- 网页抓取、环境门禁和 stage 契约：[网页采集](references/web-pipeline.md)。
- 视频下载、分批抽帧：[视频采集](references/video-pipeline.md)。
- 图片审核、保存及最终路径：[素材和输出](references/output-contract.md)。
- 教程确需可执行代码时：[脚本生成](references/code-generation.md)。

保留内容依据：步骤、参数、平台与结论必须来自已获取材料；网页图只按受限视图中的 alt/上下文筛选，不冒充已视觉检查。只引用脚本实际保存的图片和验证通过的脚本。

environment_gate 可能安装依赖/浏览器或准备环境；执行前按当前任务授权与 host 权限判断。ENVIRONMENT_BLOCKED 停止该脚本链，不能构造 stage、空图结果或最终化绕过门禁。仍可报告已取得的事实和待办，但不称技能已生成。

读取内容后判断是否需要脚本；纯 GUI 步骤无需代码角色。需要时按对应参考编写、验证、finalize，再一次写最终 SKILL.md。代码失败可交付明确不含可执行脚本的文本/图片技能，只说明真实剩余能力。

成功交付实际 SKILL_MD_PATH、素材/脚本范围和验证限制；不将下载成功、stage 生成或脚本启动单独称为技能完成。
