# 按需生成可执行脚本

只在教程包含编程实现、成段代码、API/批处理/数据转换/算法或 CLI 组合时使用。純 GUI 操作不进入代码流程，也不安排固定访谈。

- 需要判断生成边界时读 [code-detector](../agents/code-detector.md)。
- 确认有必要后读 [code-writer](../agents/code-writer.md)，把代码写入 save_images 打印的目标 SKILL_DIR/scripts/。
- 按 [code-verifier](../agents/code-verifier.md) 对真实脚本验证，记录通过名单。只运行范围内可执行的检查，不为验证开放新凭据或外部写入。
- 调用：
```bash
{python} "{skill_directory}/scripts/finalize_scripts.py" <slug> --skills-dir <verified-output-root> --keep scripts/verified_a.py
```

该脚本删除目标生成目录中未列入 keep 的脚本，只针对本次确定的生成物执行，不能作用于未知既有技能。零通过时保留同一 --skills-dir 参数并传空 --keep，输出 text_images_only；有通过脚本输出 with_scripts，两者可输出 SKILL_MD_ALLOWED: true。

最终只引用幸存脚本。验证失败不必阻塞文本/图片主产物，但若用户要求可执行自动化，应明确该部分未完成，不将纯文字技能称作完整自动化。
