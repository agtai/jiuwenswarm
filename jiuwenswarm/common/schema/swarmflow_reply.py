# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""chat.swarmflow_reply 参数契约。

真人回复 swarmflow human_session 轮次的入站参数结构。回复经标准三层路由链
（TUI 空壳 ack → message_handler 转发 → process_message 分派）到达
共享 ``reply_swarmflow_request``，由既存 Team owner 调用 AgentCore 的
``Runner.reply_swarmflow_human``，原子消费精确 run/correlation 的等待输入。
"""

from typing import TypedDict


class SwarmflowReplyParams(TypedDict, total=False):
    """chat.swarmflow_reply 参数契约（TypedDict，供类型标注与文档）。"""

    session_id: str
    """必须与经过认证的请求 envelope session_id 一致，不能覆盖它。"""

    team_name: str
    """兼容字段；共享适配从既存 Team owner 解析真实 team_name。"""

    run_id: str
    """必需的精确 workflow run id；缺失时不退回广播或恢复 runtime。"""

    correlation_id: str
    """人机轮次关联号 ``{phase}:{label}:{turn}``，跨 resume 稳定。"""

    answer: str
    """真人原始回复正文。"""
