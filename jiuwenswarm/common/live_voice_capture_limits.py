# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Transport bounds for the existing Web P1 capture, not semantic policy."""

# P1 allows 30 s before speech begins, 30 s of speech and 1.5 s rotation grace.
# Keep compatible with productP1VoiceRoute's absolute capture frame bound.
MAX_CAPTURE_DURATION_SECONDS = 61.5
# 48 kHz mono PCM16 at the full capture bound is 5,904,044 WAV bytes.
# One shared ceiling covers Gateway retention and the exact-digest Batch input.
MAX_CAPTURE_WAV_BYTES = 6 * 1024 * 1024
