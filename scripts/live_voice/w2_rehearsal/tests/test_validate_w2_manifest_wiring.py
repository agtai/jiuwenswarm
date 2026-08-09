from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from validate_w2_manifest_wiring import WiringError, validate


HERE = Path(__file__).resolve().parents[1]
WIRING = HERE / "w2_manifest_wiring.v1.json"


def _value() -> dict[str, object]:
    return json.loads(WIRING.read_text(encoding="utf-8"))


def _write(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "wiring.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_candidate_unbound_manifest_wiring_is_closed() -> None:
    assert validate(WIRING) == {
        "status": "WIRED_CANDIDATE_UNBOUND",
        "artifacts": 38,
        "awards": 19,
        "invariants": 10,
        "showcases": 3,
        "journeys": 7,
        "fault_planes": 4,
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("candidate_binding", "sha"),
        lambda value: value["aliases"].__setitem__("F38", 37),
        lambda value: value["showcase_runs"]["2"].append("G1"),
        lambda value: value["journey_steps"]["route_telemetry_inspection"].remove("A1"),
        lambda value: value["faults"]["p3.task"]["zero_effect"].append("G2"),
        lambda value: value["restart"].__setitem__("evidence", ["A2", "A4"]),
        lambda value: value["awards"].pop("cross.feature_off_text_regression"),
    ],
)
def test_manifest_wiring_drift_fails_closed(tmp_path: Path, mutate: object) -> None:
    value = copy.deepcopy(_value())
    mutate(value)
    with pytest.raises(WiringError):
        validate(_write(tmp_path, value))
