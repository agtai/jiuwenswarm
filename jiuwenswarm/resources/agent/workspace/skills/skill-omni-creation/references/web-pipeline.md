# 网页采集

## 环境和权限

脚本使用 Python 3.11+。environment_gate 在创建/清理 stage/cache/images 前选择已激活/当前/最近项目虚拟环境，无环境时可能创建 .venv；重新执行到选定解释器，补 beautifulsoup4、requests、Pillow、playwright，并安装/启动 Chromium。Debian/Ubuntu 有 root 或免密 sudo 时还可能补系统库。这是实际脚本行为，执行前须满足当前授权/权限，不能通过文档扩大权限。

检查可用性而不安装依赖、Chromium 或创建虚拟环境：
```bash
{python} "{skill_directory}/scripts/environment_gate.py" --profile web-images --check --no-create-venv
```

该检查仍会尝试启动已有 Chromium，并写入 scripts/work/environment_status.json，不能当作完全只读命令。检查或自动修复失败输出 ENVIRONMENT_BLOCKED 并返回非零。停止这条链，不转网页 fallback 或空图最终化。相关脚本自动调用门禁，不需反复手工检查。

## 网页与 stage01

```bash
{python} "{skill_directory}/scripts/scrape_page.py" "<URL>" <slug>
{python} "{skill_directory}/scripts/print_blocks.py" <slug> --stage stage01
```

work/<slug>/stage01.json 包含 url、slug、title、blocks、video_urls；block 为 heading(level/text/source)、text(text/source) 或 image(url/alt/source/path)。小红书用 scrape_page 检测视频，视频平台可返回空 blocks 和 video_urls。

stage01/02/03 都通过 print_blocks 输出同一全局预算的代表视图，不直接读原始 JSON、分页或补读预算省略内容。必要信息不在视图中时如实说明，不能声称已读完整正文。

只有 ENVIRONMENT_READY 后遇到页面空内容/403/验证页，才可用可用的 web_fetch_webpage 获取已授权的公开正文，构造相同 schema 的 stage01（image 必须含 url），回到正常素材链。该工具不可用时说明页面未取到；不绕过登录、验证或访问控制。

网页含嵌入视频时，仅在教程步骤需要它时读取 [视频路线](video-pipeline.md)。素材接续 [输出契约](output-contract.md)。
