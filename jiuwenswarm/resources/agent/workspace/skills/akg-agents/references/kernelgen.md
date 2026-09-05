# AKG 仓库与 kernelgen 契约

## 仓库和环境

默认仓库 `https://gitcode.com/mindspore/akg/`，分支 `br_agents`，目录 `~/.jiuwenswarm/agent/workspace/akg`；用户明确指定位置时使用该位置。先检查已有目录是否是 Git 仓库、当前分支和工作区状态；缺失时可在任务授权范围内克隆 `br_agents`。异常目录或不匹配分支不能静默覆盖或切换。

从目标仓库读取 `akg_agents/workspace/.opencode/skills/akg-env-setup/SKILL.md`。若 `~/.akg/check_env.md` 不存在，环境工作流使用 `FULL_SETUP=true`；存在时复用缓存检查路径，不把该文件的存在单独当作环境就绪证据。忽略下游遗留的 `akg_cli` 检查。需要依赖时优先使用工程 requirements 文件。

缺少 `~/.akg/settings.json` 时，可说明从 `akg_agents/examples/settings.example.json` 建立配置的方法；`base_url`、`api_key`、`model_name` 由用户本机填写。已完成的配置不要求用户重复操作。无法继续生成时仍可完成范围内的源码/任务分析。

## 任务与命令

读取 `akg_agents/workspace/.opencode/skills/op-task-extractor/SKILL.md`，产出标准任务文件及 torch 标杆并按其契约验证。使用实际绝对路径调用：

```bash
python <AKG_AGENTS_DIR>/workspace/.opencode/skills/search-workflow/scripts/run_workflow.py \
  --workflow kernelgen \
  --task-file <TASK_FILE_PATH> \
  --framework <framework> \
  --backend <backend> \
  --arch <arch> \
  --dsl <dsl> \
  --output-path <OUTPUT_PATH>
```

按需增加 `--devices <ids>`。优先采用用户参数；Ascend/NPU 对应 `ascend/triton_ascend`，NVIDIA 对应 `cuda/triton_cuda`，CPU 对应 `cpu/cpp`。不根据不可见设备猜测 arch。

工作流通常需 5–20 分钟；给予足够运行时间，通过当前工具的会话/轮询能力跟踪前台进程，不做无人跟踪的后台执行。脚本失败后保留错误和已有产物状态；未经用户明确要求，不换生成命令或绕过该流程。
