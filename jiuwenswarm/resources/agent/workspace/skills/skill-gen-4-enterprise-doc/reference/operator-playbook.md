# CLI、路径与安装

所有脚本用实际技能目录的绝对路径调用。CLI 将 scripts/ 添加到 sys.path 并导入其 skill_gen，不要求导入完整 JiuwenSwarm 应用。

```bash
python3 <skill-directory>/scripts/skill_generator_cli.py sop-text --sop-file <absolute-file> --out-text <absolute-text-output>
python3 <skill-directory>/scripts/skill_generator_cli.py url-fetch --url <https-url> --out-json <absolute-json-output>
```

sop-text 的 --print-raw-chars 仅输出长度；未指定 --out-text 时输出正文。url-fetch 输出页面数组，含 text/title/source_url。httpx/beautifulsoup4 用于网页，富文档可依赖 openjiuwen AutoFileParser；能力缺失时可处理可读 MD/TXT，不把文件名当正文。

完整结构化对象通过 [结构化提取](sop-structure-pipeline.md) 的 Python API 获取；当前 CLI 没有 validate-skill 子命令。

## 路径

优先使用当前 host 暴露的 get_agent_workspace_dir()/get_agent_skills_dir() 或已明确的绝对根，不拼接历史机器路径。

| 路径 | 用途 |
|---|---|
| Agent workspace / skills-draft / name | 本次目标包草稿 |
| Agent skills dir / name | 导入后的运行时技能 |
| 本元技能目录 | 内置模板与工具，不在生成用户技能时修改 |

## 验证和导入

可使用实际 scripts/skill_gen/validator.py 中的 validate_skill(Path(draft)) 检查元数据与基础结构；它不证明来源保真或业务正确。核对引用文件、必要输入输出和来源说明；fallback 保留 intent-sop-snapshot。

任务要求安装且 host 提供 skills.import_local 时，用绝对草稿目录作为 path；该目录直接包含 SKILL.md。同名包存在且用户授权替换时才用 force: true。读取导入结果确认路径和索引刷新状态，不能以草稿存在代替已安装证据。

未提供导入工具或导入失败时，保留可审阅草稿、说明错误与所需动作，不擅自改配置/复制到未知 runtime 或宣称已加载。只要求草稿时交付草稿即可。
