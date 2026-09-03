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
