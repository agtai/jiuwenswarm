# 插桩与集成

仅在实施相应边界时读取对应部分。缓冲区、MoeTracing ABI、密度与工具链参数见 [技术参考](../reference.md)。

## 点位

从目标算子入口沿参与当前构建的 include 和模板调用跟进实际实现，包含 `operator()<AIC/AIV>`、通信、gemm、epilogue、send/recv/compute 等角色路径。不要仅修改外层转发头，也不扫描无关算子或历史源码树。

根节点为 `processing`；L2–L7 按真实阶段命名，用空格分隔层级路径。AIC/AIV 可用阶段后缀区分。expert group/stage 循环传实际索引；超过七层折叠至 L7，薄 helper 可合并，wait/sync/send/recv/copy/quant/dequant 热点保留语义点位。粗粒度阶段入口/出口成对打点，不在 matmul K 迭代或单 tile 搬运紧循环逐次打点。

使用 `validate_trace_points.py` 检查命名/配对，`check_compile_safety.py <operator_dir>` 检查源码静态风险。只对受改动影响的当前源码树运行；镜像/金标树是否更新由任务范围决定。静态脚本不覆盖工程完整编译、aclnn ABI 或安装/import。

## Profiling 输出契约

- 模式 A：OpDef 中 profiling 为 OPTIONAL，可保持公开返回值数；仅在真实 optional 契约允许时传空 optional。
- 模式 B：原 Op/torch.ops 名不变，返回元组末尾增加 profiling；所有调用方按新 arity 解包。
- REQUIRED profiling 与主输出同级：OpDef、infer shape/dtype 与空值检查、tiling 输出描述、pybind 分配、aclnnInner/手写 pregen、EXEC_NPU_CMD、核入口和 Init 的槽位顺序一致；profiling 为第 N+1 个 Tensor 数据输出。
- workspace/tiling 等非 Tensor 参数沿工程约定排列，不能插错主输出槽。
- 禁止用环境变量、nullopt、nullptr 省掉 REQUIRED GM；用 base 头中的 `ENABLE_MOE_PROFILING` 控制写入并重编核。完整接入默认启用该宏。
- 核入口栈 buffer、SetMoeProfilePtr、GM 写回与缓冲区容量必须匹配。缓存一致性和混合核屏障依实际平台及算子语义处理，不盲加同步。
- 改变输出顺序后重编实际 OPP/pybind 并验证运行，不能与旧二进制混用。

## 构建工具链

复用团队现有 compile/build 入口，在拷贝源码到构建树之后、真正编译之前插入 `trace_preprocessor.py`，使用 `TRACE_PREPROCESSOR_HOOK_START/END` 标记，生成当次 `point_map.json`。

已有仓内工具链直接引用；缺少时按需用本技能 scripts 下的：
- `bootstrap_trace_toolchain.py --build-dir <build-dir>` 补齐工具链；
- `patch_build_pipeline.py` 接入已有脚本，anchor 不匹配时人工编辑同一入口；
- `verify_trace_scaffold.py` 检查部署；
- `apply_trace_scaffold.sh` 仅作首次接入助手。

UMDK 常见入口为 `umdk/build/cam/comm_operator/compile_ascend_proj.sh`，以当前工程查证为准。保留用户脚本，不用平行编译入口绕过真实构建。完整链路需跑项目常用 OPP 及 pybind wheel 构建；相关打包问题查技术参考。

## Sample 与采集

扩展已有 sample/driver 的 profiling_dir、point_map、chrome_trace 参数，先查它的实际 CLI。REQUIRED 返回多一路时更新 wrapper/forward/调用方；数值对拍仍只比较主输出，baseline 不返回 profiling 时保持其原 arity。不要把纯数值 UT 变成必须写 trace 的主路径。

在启动 `multiprocessing.spawn` 前将 profiling_dir、chrome_trace、point_map 全部 `Path(...).expanduser().resolve()`。子进程调用算子后设备 synchronize，再 `trace_utils.save_profiling_data` 写 rank 文件；父进程 join 后用 `trace_collector.py` 和同源 point_map 生成 Chrome trace。base_h_path 指向本算子的 base 头。

导入 trace_utils 使用实际工具链目录；不可用时说明采集未执行，不把跳过当作成功。rank 文件非空而 skipped_no_mapping 高时先核对 mapping/二进制同源性。

交付受影响文件、点位层级、检查/构建结果、产物与实际可复用命令。完整链路按 G1–G5 报告证据；仅源码修复说明剩余集成边界。
