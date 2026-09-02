#!/usr/bin/env python3
"""Reduce one physical C019 Browser snapshot into per-unit gap timings."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


_SCHEMA_VERSION = "live-voice.c019-gap-report.v1"
_PREFETCH_PROFILE = "c019-physical-prefetch-v1"
_UNIT_MILESTONES = (
    "unit_tts_requested",
    "unit_playout_started",
    "unit_playout_completed",
    "successor_tts_requested",
    "successor_downlink_attached",
    "successor_first_frame_buffered",
    "successor_promoted_to_playout",
    "successor_park_requested",
    "successor_parked",
    "successor_promotion_requested",
    "successor_promoted",
    "successor_promoted_unparked",
)
_REASON_ORDER = (
    "measurement_not_enabled",
    "measurement_not_configured",
    "accepted_record_count_mismatch",
    "dropped_records_present",
    "non_physical_unit_evidence",
    "browser_failure_present",
    "duplicate_unit_milestone",
    "mixed_response_population",
    "mixed_identity_population",
    "mixed_unit_identity",
    "activation_identity_incomplete",
    "unit_identity_incomplete",
    "unit_sequence_gap",
    "unit_milestones_incomplete",
    "unit_clock_order_invalid",
    "successor_predecessor_order_invalid",
    "successor_transition_family_mixed",
    "successor_transition_family_incomplete",
    "successor_transition_order_invalid",
)


class C019GapReportError(ValueError):
    """Raised when a snapshot cannot be safely parsed at all."""


def _object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise C019GapReportError(f"{field} is not an object")
    return value


def _clock(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise C019GapReportError("milestone clock is invalid")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise C019GapReportError("milestone clock is invalid")
    return parsed


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def build_c019_gap_report(payload: object) -> dict[str, object]:
    root = _object(payload, "snapshot")
    snapshot = _object(root.get("l0"), "snapshot.l0") if "l0" in root else root
    records_value = snapshot.get("records")
    if not isinstance(records_value, list):
        raise C019GapReportError("snapshot records are invalid")
    records: Sequence[object] = records_value
    reasons: set[str] = set()
    if snapshot.get("enabled") is not True:
        reasons.add("measurement_not_enabled")
    if snapshot.get("configured") is not True:
        reasons.add("measurement_not_configured")
    accepted = snapshot.get("accepted_records")
    if (
        isinstance(accepted, bool)
        or not isinstance(accepted, int)
        or accepted != len(records)
    ):
        reasons.add("accepted_record_count_mismatch")
    dropped = snapshot.get("dropped_records")
    if isinstance(dropped, bool) or not isinstance(dropped, int) or dropped != 0:
        reasons.add("dropped_records_present")

    response_keys: set[tuple[str, int]] = set()
    identity_keys: set[tuple[str, str, str, str, int, str, int]] = set()
    unit_ids: dict[tuple[str, int, int], set[str]] = {}
    unit_sequences_by_id: dict[tuple[str, int, str], set[int]] = {}
    clocks: dict[tuple[str, int], dict[int, dict[str, float]]] = {}
    duplicate = False
    browser_failure = False
    non_physical = False
    prefetch_required = False
    for raw_record in records:
        record = _object(raw_record, "record")
        if record.get("profile_id") == _PREFETCH_PROFILE:
            prefetch_required = True
        milestone = record.get("milestone")
        if milestone == "browser_failure":
            browser_failure = True
            continue
        if milestone not in _UNIT_MILESTONES:
            continue
        if record.get("evidence_source") != "physical":
            non_physical = True
        binding = _object(record.get("binding"), "record.binding")
        correlation_id = binding.get("correlation_id")
        session_id = binding.get("session_id")
        interaction_id = binding.get("interaction_id")
        activation_id = binding.get("activation_id")
        activation_generation = binding.get("activation_generation")
        response_id = binding.get("response_id")
        generation = binding.get("response_generation")
        unit_id = binding.get("unit_id")
        unit_seq = binding.get("unit_seq")
        if (
            not isinstance(correlation_id, str)
            or not correlation_id
            or not isinstance(session_id, str)
            or not session_id
            or not isinstance(interaction_id, str)
            or not interaction_id
            or isinstance(activation_generation, bool)
            or not isinstance(activation_generation, int)
            or activation_generation <= 0
            or not isinstance(response_id, str)
            or not response_id
            or isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 0
            or isinstance(unit_seq, bool)
            or not isinstance(unit_seq, int)
            or unit_seq < 0
        ):
            raise C019GapReportError("unit binding is invalid")
        activation_identity_complete = isinstance(activation_id, str) and bool(
            activation_id
        )
        unit_identity_complete = isinstance(unit_id, str) and bool(unit_id)
        if not activation_identity_complete:
            reasons.add("activation_identity_incomplete")
        if not unit_identity_complete:
            reasons.add("unit_identity_incomplete")
        observation = _object(record.get("observation"), "record.observation")
        response_key = (response_id, generation)
        response_keys.add(response_key)
        if activation_identity_complete:
            identity_keys.add(
                (
                    correlation_id,
                    session_id,
                    interaction_id,
                    activation_id,
                    activation_generation,
                    response_id,
                    generation,
                )
            )
        if unit_identity_complete:
            unit_ids.setdefault((response_id, generation, unit_seq), set()).add(unit_id)
            unit_sequences_by_id.setdefault(
                (response_id, generation, unit_id), set()
            ).add(unit_seq)
        unit_clocks = clocks.setdefault(response_key, {}).setdefault(unit_seq, {})
        if milestone in unit_clocks:
            duplicate = True
        else:
            unit_clocks[milestone] = _clock(observation.get("monotonic_ms"))

    if non_physical:
        reasons.add("non_physical_unit_evidence")
    if browser_failure:
        reasons.add("browser_failure_present")
    if duplicate:
        reasons.add("duplicate_unit_milestone")
    if len(response_keys) != 1:
        reasons.add("mixed_response_population")
    if len(identity_keys) > 1:
        reasons.add("mixed_identity_population")
    if any(len(values) != 1 for values in unit_ids.values()) or any(
        len(values) != 1 for values in unit_sequences_by_id.values()
    ):
        reasons.add("mixed_unit_identity")

    selected_key = min(response_keys) if response_keys else None
    selected_units = clocks.get(selected_key, {}) if selected_key is not None else {}
    sequences = sorted(selected_units)
    if sequences and sequences != list(range(sequences[-1] + 1)):
        reasons.add("unit_sequence_gap")

    units: list[dict[str, object]] = []
    previous_completed: float | None = None
    for sequence in sequences:
        unit = selected_units[sequence]
        requested = unit.get("unit_tts_requested")
        started = unit.get("unit_playout_started")
        completed = unit.get("unit_playout_completed")
        successor_requested = unit.get("successor_tts_requested")
        successor_attached = unit.get("successor_downlink_attached")
        successor_buffered = unit.get("successor_first_frame_buffered")
        successor_promoted = unit.get("successor_promoted_to_playout")
        park_requested = unit.get("successor_park_requested")
        parked = unit.get("successor_parked")
        promotion_requested = unit.get("successor_promotion_requested")
        promoted = unit.get("successor_promoted")
        promoted_unparked = unit.get("successor_promoted_unparked")
        parked_family = (park_requested, parked, promotion_requested, promoted)
        has_parked_family = any(value is not None for value in parked_family)
        has_unparked_family = promoted_unparked is not None
        if has_parked_family and has_unparked_family:
            reasons.add("successor_transition_family_mixed")
        if (
            sequence > 0
            and prefetch_required
            and not (has_parked_family or has_unparked_family)
        ):
            reasons.add("successor_transition_family_incomplete")
        if has_parked_family and any(value is None for value in parked_family):
            reasons.add("successor_transition_family_incomplete")
        if has_parked_family and all(value is not None for value in parked_family):
            assert park_requested is not None
            assert parked is not None
            assert promotion_requested is not None
            assert promoted is not None
            if not (
                park_requested
                <= parked
                <= promotion_requested
                <= promoted
                <= (successor_promoted if successor_promoted is not None else -1)
            ):
                reasons.add("successor_transition_order_invalid")
        if has_unparked_family and successor_promoted is not None:
            if promoted_unparked > successor_promoted:
                reasons.add("successor_transition_order_invalid")
        complete = (
            requested is not None
            and started is not None
            and completed is not None
            and (
                sequence == 0
                or (
                    successor_requested is not None
                    and successor_attached is not None
                    and successor_buffered is not None
                    and successor_promoted is not None
                )
            )
        )
        if not complete:
            reasons.add("unit_milestones_incomplete")
        if complete and not requested <= started <= completed:
            reasons.add("unit_clock_order_invalid")
        if (
            sequence > 0
            and complete
            and not (
                successor_requested <= successor_attached <= successor_buffered
                and successor_buffered <= successor_promoted <= started
            )
        ):
            reasons.add("unit_clock_order_invalid")
        if (
            sequence > 0
            and complete
            and previous_completed is not None
            and not previous_completed <= successor_promoted <= started
        ):
            reasons.add("successor_predecessor_order_invalid")
        units.append(
            {
                "unit_seq": sequence,
                "tts_requested_ms": _rounded(requested),
                "playout_started_ms": _rounded(started),
                "playout_completed_ms": _rounded(completed),
                "tts_to_start_ms": _rounded(
                    None
                    if requested is None or started is None
                    else started - requested
                ),
                "playout_duration_ms": _rounded(
                    None
                    if started is None or completed is None
                    else completed - started
                ),
                "previous_to_start_gap_ms": _rounded(
                    None
                    if previous_completed is None or started is None
                    else started - previous_completed
                ),
                "preparation_overlap_ms": _rounded(
                    None
                    if previous_completed is None or requested is None
                    else previous_completed - requested
                ),
                "successor_tts_requested_ms": _rounded(successor_requested),
                "successor_downlink_attached_ms": _rounded(successor_attached),
                "successor_first_frame_buffered_ms": _rounded(successor_buffered),
                "successor_promoted_to_playout_ms": _rounded(successor_promoted),
                **(
                    {
                        "successor_park_requested_ms": _rounded(park_requested),
                        "successor_parked_ms": _rounded(parked),
                        "successor_promotion_requested_ms": _rounded(
                            promotion_requested
                        ),
                        "successor_promoted_ms": _rounded(promoted),
                        "successor_promoted_unparked_ms": _rounded(promoted_unparked),
                    }
                    if has_parked_family or has_unparked_family
                    else {}
                ),
                "tts_to_first_buffer_ms": _rounded(
                    None
                    if successor_requested is None or successor_buffered is None
                    else successor_buffered - successor_requested
                ),
                "predecessor_overlap_ms": _rounded(
                    None
                    if previous_completed is None or successor_buffered is None
                    else previous_completed - successor_buffered
                ),
                "local_handoff_ms": _rounded(
                    None
                    if previous_completed is None
                    or successor_buffered is None
                    or successor_promoted is None
                    else successor_promoted
                    - max(previous_completed, successor_buffered)
                ),
                "promotion_to_webaudio_ms": _rounded(
                    None
                    if successor_promoted is None or started is None
                    else started - successor_promoted
                ),
            }
        )
        previous_completed = completed

    if not units:
        reasons.add("unit_milestones_incomplete")
    ordered_reasons = [reason for reason in _REASON_ORDER if reason in reasons]
    return {
        "schema_version": _SCHEMA_VERSION,
        "eligible": not ordered_reasons,
        "reasons": ordered_reasons,
        "response": (
            None
            if selected_key is None
            else {
                "response_id": selected_key[0],
                "response_generation": selected_key[1],
            }
        ),
        "units": units,
    }


def _render_table(report: Mapping[str, object]) -> str:
    lines = [
        f"eligible={str(report['eligible']).lower()}",
        f"reasons={','.join(report['reasons']) if report['reasons'] else 'none'}",
        "unit  tts_request  attached    buffered    promoted    start       complete    tts->buffer  local       prev->start",
    ]
    for raw_unit in report["units"]:
        unit = _object(raw_unit, "report.unit")

        def cell(name: str) -> str:
            value = unit[name]
            return "-" if value is None else f"{value:.3f}"

        lines.append(
            f"{unit['unit_seq']:>4}  {cell('tts_requested_ms'):>11}  "
            f"{cell('successor_downlink_attached_ms'):>10}  "
            f"{cell('successor_first_frame_buffered_ms'):>10}  "
            f"{cell('successor_promoted_to_playout_ms'):>10}  "
            f"{cell('playout_started_ms'):>10}  {cell('playout_completed_ms'):>10}  "
            f"{cell('tts_to_first_buffer_ms'):>11}  {cell('local_handoff_ms'):>10}  "
            f"{cell('previous_to_start_gap_ms'):>11}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report C019 prefix/tail digital playout gaps from Browser L0",
    )
    parser.add_argument("--json", action="store_true", help="emit canonical JSON")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.snapshot.read_text(encoding="utf-8"))
        report = build_c019_gap_report(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, C019GapReportError):
        print(
            "ERROR: C019 snapshot is unreadable or structurally invalid",
            file=sys.stderr,
        )
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print(_render_table(report))
    return 0 if report["eligible"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
