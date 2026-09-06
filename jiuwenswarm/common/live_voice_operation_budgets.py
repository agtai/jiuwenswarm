# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Failure ceilings for the sole semantic path, not intended response latency.

The Web semantic transport mirrors SEMANTIC_TRANSPORT_TIMEOUT_SECONDS in
unifiedCommittedInputOwner.ts; the cross-boundary test checks that mirror.
Ordinary media/control RPCs retain their shorter independent deadlines.
"""

SEMANTIC_MODEL_TIMEOUT_SECONDS = 45.0
SEMANTIC_ANALYSIS_RECOVERY_TIMEOUT_SECONDS = 50.0
SEMANTIC_INPUT_TIMEOUT_SECONDS = 100.0
SEMANTIC_TRANSPORT_TIMEOUT_SECONDS = 150.0

# Native waits for the full Agent/tool answer after semantic admission. Keep
# that work bounded independently of normal interactive latency targets. The
# transport covers semantic admission (100 s), the supported Agent ceiling
# (180 s), and settlement overhead (20 s); speech interruption remains immediate.
NATIVE_AGENT_TIMEOUT_SECONDS = 120.0
NATIVE_AGENT_MAX_TIMEOUT_SECONDS = 180.0
NATIVE_DELEGATE_TRANSPORT_TIMEOUT_SECONDS = 300.0
