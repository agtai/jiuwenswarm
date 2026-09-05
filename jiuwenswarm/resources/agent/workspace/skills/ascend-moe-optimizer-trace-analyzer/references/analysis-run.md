# 运行与产物

## 执行命令

在 `<ASCEND_MOE_OPTIMIZER_SKILL>` 目录下执行（以下 `<ASCEND_MOE_OPTIMIZER_SKILL>` 为本技能实际安装目录或仓库资源目录）：

基础命令模板：

```bash
cd <ASCEND_MOE_OPTIMIZER_SKILL>
python3 app.py \
  --trace <TRACE_JSON> \
  --phase-map <PHASE_MAP> \
  --output-dir <OUTPUT_DIR>
```

常用参数：
- `--trace PATH`：输入 trace JSON，必填。
- `--phase-map PATH`：phase/category 映射配置，默认 `config/phase_map.yaml`。
- `--output-dir DIR`：输出目录，默认 `output`。
- `--top-n 20`：控制 `report.md` 中各表展示的行数。
- `--llm-analysis`：启用 LLM Analysis 章节。
- `--llm-command "<cmd>"`：外部 LLM 命令，命令从 stdin 读取 prompt，并把分析文本写到 stdout。
- `--llm-timeout 120`：LLM 命令超时时间，单位秒。

如果使用默认 phase map，可以省略 `--phase-map`：

```bash
cd <ASCEND_MOE_OPTIMIZER_SKILL>
python3 app.py \
  --trace <TRACE_JSON> \
  --output-dir <OUTPUT_DIR>
```

如果本机安装了 `matplotlib`，运行时会默认生成统计分析总图 `analysis_charts.png`，并嵌入 `report.md`。未安装时会跳过图表，其他输出不受影响。

LLM 命令也可以用环境变量配置：

```bash
export TRACE_ANALYSIS_LLM_CMD="<your-llm-cli>"
cd <ASCEND_MOE_OPTIMIZER_SKILL>
python3 app.py \
  --trace <TRACE_JSON> \
  --phase-map <PHASE_MAP> \
  --output-dir <OUTPUT_DIR> \
  --llm-analysis
```

如果未启用 `--llm-analysis`，仍会生成 `llm_prompt.md`，方便后续手动交给 Codex 或其他模型复核。

## 输出文件
- `phase_instances.csv`：每个已映射区间事件，包含 phase/category/name/core_group/core_id/timing。
- `phase_summary.csv`：按 phase 聚合。
- `category_summary.csv`：按 category 聚合。
- `core_group_summary.csv`：按 core group 聚合。
- `phase_core_group_summary.csv`：按 `(core_group, phase)` 聚合。
- `category_core_group_summary.csv`：按 `(core_group, category)` 聚合。
- `name_summary.csv`：按原始 trace name 聚合。
- `phase_tid_summary.csv`：按 `(phase, pid, tid)` 聚合，用于看单线程或单核长尾。
- `overlap_summary.csv`：phase 两两 overlap。
- `bubble_summary.csv`：外层阶段内部 bubble。
- `summary.json`：整体概览。
- `diagnosis.json`：确定性自动诊断结果。
- `statistical_summary.md`：确定性统计摘要，文字化说明图表和关键统计信号。
- `llm_prompt.md`：交给 LLM 的完整统计上下文，总是生成。
- `llm_analysis_meta.json`：LLM 调用状态、命令和错误信息，总是生成。
- `llm_analysis.md`：启用 LLM 且命令成功时生成。
- `report.md`：可读报告，包含 Overview、Visualizations、Statistical Highlights、Automatic Diagnosis、可选 LLM Analysis 和各类汇总表。
- `analysis_charts.png`：安装 `matplotlib` 时默认生成。单图包含 core group wall 覆盖、非 container category 的 `total_us` 饼图和 top phase。完整 trace 时间线建议继续使用 Perfetto UI 查看。

## 依赖和验证
默认运行只使用 Python 标准库，不需要安装第三方包。

可选能力：
- `matplotlib`：用于自动生成 `analysis_charts.png`。
- 外部 LLM CLI：用于 `--llm-analysis`，协议是 stdin 输入 prompt、stdout 输出分析文本。

基础验证：

```bash
cd <ASCEND_MOE_OPTIMIZER_SKILL>
python3 app.py --trace <TRACE_JSON> --phase-map <PHASE_MAP> --output-dir <OUTPUT_DIR> --top-n 20
```

## 当前限制
- 默认只分析单个 trace 文件，不做多 trace 对比。
- 当前没有显式 `--profile` 机制；不同 trace 来源主要通过 `--phase-map` 适配。
- 未映射到 phase 的事件会被过滤，通用 fallback 统计仍有改进空间。
- core group 规则目前仍以内置 UMDK 1C2V 约定为主，尚未完全配置化。
- 部分自动诊断规则仍偏 FusedDeepMoe，需要继续拆分为通用规则和领域规则。
- LLM Analysis 是可选外部命令，不内置具体模型、API key 或网络调用。
