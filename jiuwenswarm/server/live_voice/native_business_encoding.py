# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Lossless string encoding for an already-authorized Native Provider receipt.

The original receipt remains the Runtime and replay/digest authority. This
optional transport representation neither admits an output nor changes its facts.
"""

from __future__ import annotations

import json
import re


_MAX_OUTPUT_UTF8_BYTES = 524_288
# Consume ordinary text in runs, avoiding a regex repetition per character in
# large receipts. Grammar validation below precedes this string-only scan.
_JSON_STRING = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"')


def _reject_nonstandard_number(value: str) -> None:
    raise ValueError("Nonstandard JSON numeric constant")


def _compact_string(match: re.Match[str]) -> str:
    token = match.group()
    if "\\u" not in token:
        return token
    return json.dumps(json.loads(token), ensure_ascii=False)


def compact_native_business_output(output: str) -> str:
    """Return smaller UTF-8 string encoding, or the exact original on fallback.

Only JSON string tokens may change. Numeric lexemes, duplicate object keys,
ordering and all other source text remain exact. Do not use the return value
instead of the original receipt for authorization, bounds, digest or replay.
"""
    if "\\u" not in output:
        return output
    try:
        original_size = len(output.encode("utf-8"))
        if original_size > _MAX_OUTPUT_UTF8_BYTES:
            return output
        # Validate grammar without converting numeric values: large integers,
        # decimal precision and exponent spellings must remain untouched.
        json.loads(output, parse_int=lambda _: None, parse_float=lambda _: None,
                   parse_constant=_reject_nonstandard_number)
        candidate = _JSON_STRING.sub(_compact_string, output)
        candidate_size = len(candidate.encode("utf-8"))
    except (ValueError, UnicodeEncodeError, RecursionError):
        return output
    return candidate if candidate_size < original_size else output
