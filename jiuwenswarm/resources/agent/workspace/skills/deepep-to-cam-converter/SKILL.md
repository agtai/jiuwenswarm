---
name: deepep-to-cam-converter
description: 将指定 DeepEP MoE dispatch/combine 调用迁移至 Ascend CAM，并校验实际参数、通信域和资源生命周期。
---

# DeepEP 到 CAM 迁移

先确认目标代码存在 DeepEP/MoE 调用，并跟进受影响的本地初始化和调用方。没有匹配时报告检查范围，不改无关代码。默认就地修改已授权文件，保留无关变更。

用用户已提供的环境、启动参数和策略直接推进，只询问决定兼容性而仍缺失的信息：
- 目标 A2/A3 优先取用户指定环境；本机硬件探测不能替代交叉编译目标。
- hidden_size、top_k、expert_num 等须追踪到实际运行配置。argparse 默认值只有在确认无覆盖时才可作为实际值；未知值保留为阻塞该替换的条件。
- A2 使用对应接口。A3 普通/Shmem/fused 模式按已接受约束选择；多个模式存在实质初始化、功能或部署取舍且无偏好时，说明差异并询问，不声称某一模式普遍最快。
- 低延迟、显式调优 Config、Event/wait 等能力不能静默删除。明确不兼容项，沿用户已授权策略保留、局部迁移或删除；未授权语义降级时保留原行为并报告阻塞。

按实际路线读对应参考，不通读全部：
- NCCL/CUDA 初始化受影响：[通信与设备转换](references/nccl_to_hccl_converter.md)。
- [A2](references/cam_dispatch_and_combine_a2.md)、[普通 A3](references/cam_dispatch_and_combine_a3.md)、[Shmem](references/cam_dispatch_and_combine_shmem.md)、[fused deep moe](references/cam_fused_deep_moe.md)。
- fused 路线需跟进 dispatch/combine 最终调用方，校验其融合范式。

迁移时先 import torch_npu，再 import umdk_cam_op_lib；参数顺序、shape、dtype 以所选接口为准。受影响的通信域转换为 HCCL，设备操作转换为 NPU，但不全仓盲替换字符串。Shmem 和通信域释放必须在算子完成并同步后，使用目标库实际导出的清理 API。

交付简洁的决策依据、改动文件、运行参数约束和已执行检查。语法/静态检查不能证明数值一致、通信控制流或 NPU 运行成功；保留这些未验证项。
