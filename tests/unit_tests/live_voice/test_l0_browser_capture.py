from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import scripts.live_voice.l0_browser_capture as l0_browser_capture

from scripts.live_voice.l0_browser_capture import (
    ACCEPTANCE_VERSION,
    SESSION_VERSION,
    _aggregate_cold_evidence,
    _browser_round_complete,
    _configured_run_labels,
    _correlated_success_counts,
    _discover_page,
    _invalidate_cold_eligibility,
    _labels,
    _load_session,
    _loopback_websocket,
    _scenario_matrix_complete,
    _select_cases,
    _validate_temperature_capture_policy,
    _warmup_case,
)
from jiuwenswarm.server.live_voice.latency_measurement import (
    L0_RUN_LABELS_VERSION,
    load_l0_corpus_manifest,
)


CORPUS = Path("scripts/live_voice/l0_fixed_corpus.json")
LAUNCHER = Path("scripts/live_voice/start_hands_free_demo.ps1")
SOURCE_HEAD = "c31e85ade1a69e934d05bfb9c277568a1238663c"
ENVIRONMENT_REF = "environment-physical-formal-web-test-room"
CONFIGURATION_SHA256 = "b" * 64


def _session(tmp_path: Path, **updates: object) -> Path:
    path = tmp_path / "browser-session.json"
    value: dict[str, object] = {
        "schema_version": SESSION_VERSION,
        "source_head": SOURCE_HEAD,
        "runtime_profile": "formal-web-validation",
        "evidence_directory": str(tmp_path),
        "run_labels_file": str(tmp_path / "run-labels.json"),
        "browser_endpoint": "http://127.0.0.1:9223",
        "browser_page_origin": "http://localhost:5173",
        "temperature_epoch_id": "1" * 32,
        "cold_sample_available": True,
        "environment_ref": ENVIRONMENT_REF,
        "configuration_sha256": CONFIGURATION_SHA256,
        "physical_evidence": "pending-user-run",
        "raw_audio_retained": False,
        "transcript_retained": False,
    }
    value.update(updates)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _cold_shard(
    root: Path,
    *,
    sample_index: int,
    epoch: str,
    scenario_id: str = "short-no-tool-zh",
    environment_ref: str = ENVIRONMENT_REF,
    configuration_sha256: str = CONFIGURATION_SHA256,
    corpus_sha256: str | None = None,
) -> Path:
    evidence = root / f"cold-{sample_index}"
    evidence.mkdir()
    _session(
        evidence,
        temperature_epoch_id=epoch,
        environment_ref=environment_ref,
        configuration_sha256=configuration_sha256,
    )
    acceptance = {
        "schema_version": ACCEPTANCE_VERSION,
        "profile_id": "physical-formal-web-cold",
        "scenario_id": scenario_id,
        "sample_index": sample_index,
        "temperature_epoch_id": epoch,
        "temperature_state": "fresh_launcher_epoch",
        "operator_confirmation": "pass",
        "browser_record_count": 2,
        "browser_dropped_record_count": 0,
        "automated_browser_complete": True,
        "physical_microphone": "operator_observed",
        "physical_speaker": "operator_observed",
        "subjective_audio": "operator_confirmed",
    }
    (evidence / "physical-acceptance.jsonl").write_text(
        json.dumps(acceptance) + "\n",
        encoding="utf-8",
    )
    (evidence / "cold-sample-consumed.json").write_text(
        json.dumps(
            {
                "schema_version": SESSION_VERSION,
                "temperature_epoch_id": epoch,
                "sample_index": sample_index,
            }
        ),
        encoding="utf-8",
    )
    (evidence / "browser.jsonl").write_text("{}\n", encoding="utf-8")
    _, expected_corpus_sha256 = load_l0_corpus_manifest(CORPUS)
    (evidence / "physical-report.json").write_text(
        json.dumps(
            {
                "source_head": SOURCE_HEAD,
                "corpus_sha256": corpus_sha256 or expected_corpus_sha256,
                "environment_ref": environment_ref,
                "physical_configuration_sha256": configuration_sha256,
                "physical_capture_kind": "cold_epoch_shard",
                "physical_temperature_epoch_id": epoch,
            }
        ),
        encoding="utf-8",
    )
    return evidence


def test_capture_session_is_loopback_closed_and_cannot_escape_evidence_directory(
    tmp_path: Path,
) -> None:
    session = _load_session(_session(tmp_path))
    assert session["browser_endpoint"] == "http://127.0.0.1:9223"

    for endpoint in (
        "http://127.0.0.1:9223@evil.example",
        "http://localhost:9223",
        "https://127.0.0.1:9223",
        "http://127.0.0.1:9000",
        "http://127.0.0.1:9223/path",
    ):
        with pytest.raises(ValueError, match="loopback-only"):
            _load_session(_session(tmp_path, browser_endpoint=endpoint))
    for page_origin in (
        "http://localhost:6173",
        "https://localhost:5173",
        "http://evil.example:5173",
        "http://localhost:5173@evil.example",
    ):
        with pytest.raises(ValueError, match="local Formal Web origin"):
            _load_session(_session(tmp_path, browser_page_origin=page_origin))

    assert (
        _loopback_websocket(
            "ws://127.0.0.1:9223/devtools/page/exact",
            expected_port=9223,
        )
        == "ws://127.0.0.1:9223/devtools/page/exact"
    )
    for websocket_url in (
        "ws://127.0.0.1:9223@evil.example/devtools/page/exact",
        "ws://localhost:9223/devtools/page/exact",
        "ws://127.0.0.1:9224/devtools/page/exact",
        "wss://127.0.0.1:9223/devtools/page/exact",
    ):
        with pytest.raises(RuntimeError, match="non-loopback"):
            _loopback_websocket(websocket_url, expected_port=9223)

    with pytest.raises(ValueError, match="loopback"):
        _load_session(
            _session(tmp_path, browser_endpoint="http://example.test:9223")
        )
    with pytest.raises(ValueError, match="escaped"):
        _load_session(
            _session(tmp_path, run_labels_file=str(tmp_path.parent / "labels.json"))
        )
    with pytest.raises(ValueError, match="closed shape"):
        _load_session(_session(tmp_path, credential="forbidden"))
    with pytest.raises(ValueError, match="environment reference"):
        _load_session(_session(tmp_path, environment_ref="Lab:1"))
    with pytest.raises(ValueError, match="environment reference"):
        _load_session(_session(tmp_path, environment_ref="a" * 65))


def test_cdp_discovery_rejects_redirected_or_remote_websocket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        def __init__(
            self, *, final_url: str, page_url: str, websocket_url: str
        ) -> None:
            self._final_url = final_url
            self._page_url = page_url
            self._websocket_url = websocket_url

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return self._final_url

        def read(self) -> bytes:
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": self._page_url,
                        "webSocketDebuggerUrl": self._websocket_url,
                    }
                ]
            ).encode("utf-8")

    class _Opener:
        response: _Response

        def open(self, *_args: object, **_kwargs: object) -> _Response:
            return self.response

    opener = _Opener()
    monkeypatch.setattr(
        l0_browser_capture.urllib.request,
        "build_opener",
        lambda *_args: opener,
    )
    opener.response = _Response(
        final_url="http://evil.example/json",
        page_url="http://localhost:5173/chat/new",
        websocket_url="ws://127.0.0.1:9223/devtools/page/exact",
    )
    with pytest.raises(ValueError, match="loopback-only"):
        _discover_page(
            "http://127.0.0.1:9223", page_origin="http://localhost:5173"
        )

    opener.response = _Response(
        final_url="http://127.0.0.1:9223/json",
        page_url="http://localhost:5173/chat/new",
        websocket_url="ws://evil.example:9223/devtools/page/exact",
    )
    with pytest.raises(RuntimeError, match="non-loopback"):
        _discover_page(
            "http://127.0.0.1:9223", page_origin="http://localhost:5173"
        )

    opener.response = _Response(
        final_url="http://127.0.0.1:9223/json",
        page_url="http://localhost:5173/chat/session-after-spa-navigation",
        websocket_url="ws://127.0.0.1:9223/devtools/page/exact",
    )
    assert _discover_page(
        "http://127.0.0.1:9223", page_origin="http://localhost:5173"
    ) == "ws://127.0.0.1:9223/devtools/page/exact"

    opener.response = _Response(
        final_url="http://127.0.0.1:9223/json",
        page_url="http://evil.example/chat/new",
        websocket_url="ws://127.0.0.1:9223/devtools/page/exact",
    )
    with pytest.raises(RuntimeError, match="isolated Formal Web"):
        _discover_page(
            "http://127.0.0.1:9223", page_origin="http://localhost:5173"
        )

def test_launcher_binds_l0_to_exact_environment_agent_config_and_project_revision() -> None:
    source = LAUNCHER.read_text(encoding="utf-8-sig")
    assert "^[a-z0-9][a-z0-9._-]{0,63}$" in source
    assert "Get-FileHash -LiteralPath $ConfigYamlPath -Algorithm SHA256" in source
    assert "agent_configuration_sha256 = $agentConfigurationSha256" in source
    assert "revision = $projectRevision" in source
    assert "$L0Measurement -and $projectStatus.Count -gt 0" in source
    assert "Join-Path $l0LogsRoot $L0MeasurementDirectory" in source
    assert "仓库内的 L0 证据目录必须位于已忽略的 logs 目录" in source
    assert "browser_page_origin = \"http://localhost:$FrontendPort\"" in source


def test_default_physical_cases_exclude_injected_and_degraded_profiles() -> None:
    manifest, _ = load_l0_corpus_manifest(CORPUS)
    selected = _select_cases(manifest, [])
    categories = {str(item["category"]) for item in selected}
    assert {"short_no_tool", "long_answer", "real_tool", "task_create"} <= categories
    assert "provider_slow" not in categories
    assert "provider_failure" not in categories
    assert "degraded_network" not in categories
    assert all(item["expected_classification"] == "success" for item in selected)

    with pytest.raises(ValueError, match="non-injected nominal success"):
        _select_cases(manifest, ["provider-failure-zh"])


def test_dynamic_labels_have_no_free_form_or_private_fields() -> None:
    labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature="warm",
    )
    assert labels == {
        "schema_version": L0_RUN_LABELS_VERSION,
        "profile_id": "physical-formal-web-warm",
        "scenario_id": "short-no-tool-zh",
        "sample_index": 3,
        "temperature": "warm",
        "evidence_source": "physical",
    }


def test_browser_round_requires_exact_labels_no_drops_and_one_success_terminal() -> None:
    labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature="warm",
    )
    browser_labels = dict(labels)
    browser_labels.pop("schema_version")
    records = [
        {
            **browser_labels,
            "milestone": "browser_eot_receipt",
            "classification": "unknown",
        },
        {
            **browser_labels,
            "milestone": "playout_completed",
            "classification": "success",
        },
    ]
    snapshot = {
        "enabled": True,
        "configured": True,
        "accepted_records": 2,
        "dropped_records": 0,
        "records": records,
    }
    assert _browser_round_complete(snapshot, browser_labels)

    dropped = {**snapshot, "dropped_records": 1}
    assert not _browser_round_complete(dropped, browser_labels)
    partial = {**snapshot, "accepted_records": 1, "records": records[:1]}
    assert not _browser_round_complete(partial, browser_labels)
    wrong = {
        **snapshot,
        "records": [{**records[0], "sample_index": 4}, records[1]],
    }
    assert not _browser_round_complete(wrong, browser_labels)
    fallback = {
        **snapshot,
        "accepted_records": 3,
        "records": [
            *records,
            {
                **browser_labels,
                "milestone": "fallback",
                "classification": "fallback",
            },
        ],
    }
    assert not _browser_round_complete(fallback, browser_labels)


def test_correlated_success_count_intersects_operator_browser_and_aggregate() -> None:
    report = {
        "rounds": [
            {
                "profile_id": "physical-formal-web-warm",
                "scenario_id": "short-no-tool-zh",
                "sample_index": 1,
                "success_eligible": True,
            },
            {
                "profile_id": "physical-formal-web-warm",
                "scenario_id": "long-answer-zh",
                "sample_index": 2,
                "success_eligible": True,
            },
        ]
    }
    accepted = {
        ("physical-formal-web-warm", "short-no-tool-zh", 1),
        ("physical-formal-web-warm", "task-status-zh", 3),
    }
    assert _correlated_success_counts(
        report,
        accepted,
        {"short-no-tool-zh", "task-status-zh"},
    ) == {"short-no-tool-zh": 1, "task-status-zh": 0}


def test_physical_profile_requires_target_total_and_every_selected_scenario() -> None:
    assert not _scenario_matrix_complete(
        {"short-no-tool-zh": 20, "task-status-zh": 0},
        20,
    )
    assert _scenario_matrix_complete(
        {"short-no-tool-zh": 19, "task-status-zh": 1},
        20,
    )


def test_temperature_policy_separates_one_fresh_cold_sample_from_warmed_matrix() -> None:
    manifest, _ = load_l0_corpus_manifest(CORPUS)
    profiles = {
        str(item["profile_id"]): item
        for item in manifest["profiles"]
        if type(item) is dict
    }
    one_case = _select_cases(manifest, ["short-no-tool-zh"])
    all_cases = _select_cases(manifest, [])
    assert (
        _validate_temperature_capture_policy(
            profile=profiles["physical-formal-web-cold"],
            cases=one_case,
            temperature="cold",
            successful_rounds=1,
            sample_index_start=12,
        )
        == 12
    )
    with pytest.raises(ValueError, match="one scenario and one sample"):
        _validate_temperature_capture_policy(
            profile=profiles["physical-formal-web-cold"],
            cases=all_cases,
            temperature="cold",
            successful_rounds=20,
            sample_index_start=0,
        )
    with pytest.raises(ValueError, match="explicit unique"):
        _validate_temperature_capture_policy(
            profile=profiles["physical-formal-web-cold"],
            cases=one_case,
            temperature="cold",
            successful_rounds=1,
            sample_index_start=None,
        )
    assert (
        _validate_temperature_capture_policy(
            profile=profiles["physical-formal-web-warm"],
            cases=all_cases,
            temperature="warm",
            successful_rounds=20,
            sample_index_start=None,
        )
        == 0
    )


def test_any_capture_invalidates_cold_epoch_before_browser_interaction(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "cold-sample-consumed.json"
    _invalidate_cold_eligibility(
        marker_path=marker,
        temperature_epoch_id="1" * 32,
        sample_index=4,
        cold_capture=False,
    )
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "schema_version": SESSION_VERSION,
        "temperature_epoch_id": "1" * 32,
        "sample_index": 4,
    }
    with pytest.raises(RuntimeError, match="already consumed"):
        _invalidate_cold_eligibility(
            marker_path=marker,
            temperature_epoch_id="1" * 32,
            sample_index=4,
            cold_capture=True,
        )


def test_targeted_warm_capture_uses_one_non_mutating_dialogue_warmup() -> None:
    manifest, _ = load_l0_corpus_manifest(CORPUS)
    warmup = _warmup_case(manifest)
    assert warmup["case_id"] == "short-no-tool-zh"
    assert warmup["expected_route"] == "dialogue"
    assert warmup["action_sequence"] == ["submit", "await-audio"]


def test_twenty_unique_cold_launcher_epochs_complete_one_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_directories = [
        _cold_shard(
            tmp_path,
            sample_index=index,
            epoch=f"{index + 1:032x}",
        )
        for index in range(20)
    ]

    def aggregate(**kwargs: object) -> dict[str, object]:
        inputs = kwargs["inputs"]
        assert isinstance(inputs, list)
        assert len(inputs) == 20
        assert kwargs["accepted_round_keys"] == frozenset(
            {
                ("physical-formal-web-cold", "short-no-tool-zh", index)
                for index in range(20)
            }
        )
        return {
            "environment_ref": kwargs["environment_ref"],
            "rounds": [
                {
                    "profile_id": "physical-formal-web-cold",
                    "scenario_id": "short-no-tool-zh",
                    "sample_index": index,
                    "success_eligible": True,
                }
                for index in range(20)
            ]
        }

    monkeypatch.setattr(
        l0_browser_capture,
        "clean_source_head",
        lambda: SOURCE_HEAD,
    )
    monkeypatch.setattr(l0_browser_capture, "aggregate_jsonl", aggregate)
    output = tmp_path / "cold-aggregate.json"
    result = _aggregate_cold_evidence(
        argparse.Namespace(
            corpus=CORPUS,
            scenario=["short-no-tool-zh"],
            successful_rounds=20,
            evidence_directory=evidence_directories,
            output=output,
        )
    )

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["physical_capture_kind"] == "cold_epoch_aggregate"
    assert report["physical_cold_epoch_count"] == 20
    assert report["physical_accepted_cold_epoch_count"] == 20
    assert len(report["physical_cold_temperature_epoch_ids"]) == 20
    assert report["physical_correlated_successes"] == 20
    assert report["physical_profile_complete"] is True
    assert report["environment_ref"] == ENVIRONMENT_REF
    assert report["physical_configuration_sha256"] == CONFIGURATION_SHA256


def test_cold_aggregate_rejects_reused_launcher_epoch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    epoch = "a" * 32
    evidence_directories = [
        _cold_shard(tmp_path, sample_index=0, epoch=epoch),
        _cold_shard(tmp_path, sample_index=1, epoch=epoch),
    ]
    monkeypatch.setattr(
        l0_browser_capture,
        "clean_source_head",
        lambda: SOURCE_HEAD,
    )

    with pytest.raises(ValueError, match="reused a launcher temperature epoch"):
        _aggregate_cold_evidence(
            argparse.Namespace(
                corpus=CORPUS,
                scenario=["short-no-tool-zh"],
                successful_rounds=20,
                evidence_directory=evidence_directories,
                output=tmp_path / "must-not-exist.json",
            )
        )


@pytest.mark.parametrize(
    ("shard_updates", "message"),
    [
        ({"environment_ref": "environment-physical-other-room"}, "do not share"),
        ({"configuration_sha256": "c" * 64}, "do not share"),
        ({"corpus_sha256": "d" * 64}, "conflicts with"),
    ],
)
def test_cold_aggregate_requires_one_corpus_environment_and_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shard_updates: dict[str, str],
    message: str,
) -> None:
    first = _cold_shard(tmp_path, sample_index=0, epoch="1" * 32)
    second = _cold_shard(
        tmp_path,
        sample_index=1,
        epoch="2" * 32,
        **shard_updates,
    )
    monkeypatch.setattr(l0_browser_capture, "clean_source_head", lambda: SOURCE_HEAD)

    with pytest.raises(ValueError, match=message):
        _aggregate_cold_evidence(
            argparse.Namespace(
                corpus=CORPUS,
                scenario=["short-no-tool-zh"],
                successful_rounds=20,
                evidence_directory=[first, second],
                output=tmp_path / "must-not-exist.json",
            )
        )


@pytest.mark.asyncio
async def test_configured_labels_disable_backend_and_browser_on_exception(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "run-labels.json"

    class _Cdp:
        def __init__(self) -> None:
            self.expressions: list[str] = []

        async def evaluate(self, expression: str) -> object:
            self.expressions.append(expression)
            return True

    cdp = _Cdp()
    run_labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=4,
        temperature="warm",
    )
    browser_labels = dict(run_labels)
    browser_labels.pop("schema_version")
    with pytest.raises(RuntimeError, match="operator interrupted"):
        async with _configured_run_labels(
            labels_path=labels_path,
            cdp=cdp,  # type: ignore[arg-type]
            run_labels=run_labels,
            browser_labels=browser_labels,
        ):
            raise RuntimeError("operator interrupted")

    assert json.loads(labels_path.read_text(encoding="utf-8")) == {
        "schema_version": L0_RUN_LABELS_VERSION,
        "measurement": "disabled",
    }
    assert "disable()" in cdp.expressions[-1]


@pytest.mark.asyncio
async def test_configured_labels_disable_backend_when_browser_configuration_raises(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "run-labels.json"

    class _Cdp:
        def __init__(self) -> None:
            self.expressions: list[str] = []

        async def evaluate(self, expression: str) -> object:
            self.expressions.append(expression)
            if len(self.expressions) == 1:
                raise RuntimeError("browser closed during configuration")
            return True

    cdp = _Cdp()
    run_labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=5,
        temperature="warm",
    )
    browser_labels = dict(run_labels)
    browser_labels.pop("schema_version")

    with pytest.raises(RuntimeError, match="browser closed"):
        async with _configured_run_labels(
            labels_path=labels_path,
            cdp=cdp,  # type: ignore[arg-type]
            run_labels=run_labels,
            browser_labels=browser_labels,
        ):
            pytest.fail("configuration failure must not enter the capture body")

    assert json.loads(labels_path.read_text(encoding="utf-8")) == {
        "schema_version": L0_RUN_LABELS_VERSION,
        "measurement": "disabled",
    }
    assert len(cdp.expressions) == 2
    assert "disable()" in cdp.expressions[-1]
