from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from validate_w2_rehearsal_choreography import ChoreographyError, validate


HERE = Path(__file__).resolve().parents[1]
CONTRACT = HERE / "w2_rehearsal_choreography.v1.json"


def _write(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_candidate_unbound_choreography_is_structurally_complete() -> None:
    result = validate(CONTRACT)
    assert result == {
        "status": "PREPARED",
        "runtime_slots": 7,
        "journey_steps_per_showcase": 7,
        "fault_matrix_entries": 12,
        "unresolved_runtime_probes": [],
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("candidate_sha", "0" * 40),
        lambda value: value["runtime_slots"].pop(),
        lambda value: value["runtime_slots"][6].__setitem__(
            "task_database_symbol", "pair4"
        ),
        lambda value: value["fault_matrix"].pop(),
        lambda value: value["fault_matrix"][0].__setitem__("pair", 2),
        lambda value: value["fault_matrix"][0].__setitem__(
            "request_identity", "random"
        ),
        lambda value: value["fault_matrix"][9].__setitem__(
            "driver", "gateway_rpc"
        ),
        lambda value: value["environment_names"]["fault_plan_non_secret"].pop(),
        lambda value: value["environment_names"]["gateway_secret"].__setitem__(
            1, "JIUWENSWARM_LIVE_VOICE_SPEECH_API_KEY"
        ),
        lambda value: value["environment_names"]["gateway_secret"].append(
            "raw-secret-value"
        ),
    ],
)
def test_choreography_drift_fails_closed(tmp_path: Path, mutate: object) -> None:
    value = copy.deepcopy(_contract())
    mutate(value)
    with pytest.raises(ChoreographyError):
        validate(_write(tmp_path, value))
