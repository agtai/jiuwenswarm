# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import base64
import traceback
from dataclasses import FrozenInstanceError

import pytest

import jiuwenswarm.server.live_voice.alpha_privacy_conformance as privacy_module
from jiuwenswarm.server.live_voice.alpha_privacy_conformance import (
    ALPHA_PRIVACY_SURFACES,
    MAX_BYTES_PER_OBSERVATION,
    MAX_CANARY_PATTERN_UNITS,
    MAX_CHUNKS_PER_OBSERVATION,
    MAX_CHUNKS_PER_RECORD,
    MAX_CHUNK_BYTES,
    MAX_BOUNDED_TEXT_ENCODE_BYTES,
    MAX_OBSERVATIONS,
    MAX_RECORDS_PER_OBSERVATION,
    MAX_RECORD_BYTES,
    MAX_TOTAL_BYTES,
    MAX_TOTAL_CHUNKS,
    MAX_TOTAL_RECORDS,
    AlphaPrivacyCaptureRecord,
    AlphaPrivacyCaptureRecordBuildResult,
    AlphaPrivacyCaptureSource,
    AlphaPrivacyChunkKind,
    AlphaPrivacyConformancePlan,
    AlphaPrivacyConformanceStatus,
    AlphaPrivacyConformanceViolation,
    AlphaPrivacySurface,
    AlphaPrivacySurfaceObservation,
    AlphaPrivacyRecordBuildReason,
    CanaryFamily,
    CanaryRepresentation,
    SyntheticSecretKind,
    build_alpha_privacy_capture_record,
    compute_alpha_privacy_capture_receipt,
    evaluate_alpha_privacy_conformance,
)


_CANDIDATE = "1" * 40
_OTHER_CANDIDATE = "2" * 40
_RUN_REF = "alpha-privacy-run:" + ("a" * 64)
_OTHER_RUN_REF = "alpha-privacy-run:" + ("b" * 64)
_SOURCE = AlphaPrivacyCaptureSource.CONTROLLED_ALPHA_PRIVACY_CAPTURE_V1


@pytest.fixture()
def plan() -> AlphaPrivacyConformancePlan:
    return AlphaPrivacyConformancePlan(
        declared_candidate_sha=_CANDIDATE,
        declared_run_ref=_RUN_REF,
        declared_capture_source=_SOURCE,
    )


def _record(*chunks: str | bytes) -> AlphaPrivacyCaptureRecord:
    return build_alpha_privacy_capture_record(tuple(chunks)).require_record()


def _exception_from_build_result(
    result: AlphaPrivacyCaptureRecordBuildResult,
) -> AlphaPrivacyConformanceViolation:
    try:
        result.require_record()
    except AlphaPrivacyConformanceViolation as error:
        return error
    raise AssertionError("rejected record unexpectedly became ready")


def _exception_from_evaluation(
    *,
    plan: AlphaPrivacyConformancePlan,
    observations: tuple[AlphaPrivacySurfaceObservation, ...],
) -> AlphaPrivacyConformanceViolation:
    try:
        evaluate_alpha_privacy_conformance(
            enabled=True, plan=plan, observations=observations
        )
    except AlphaPrivacyConformanceViolation as error:
        return error
    raise AssertionError("forged capture unexpectedly evaluated")


def _traceback_with_locals(error: BaseException) -> str:
    captured = traceback.TracebackException.from_exception(error, capture_locals=True)
    return "".join(captured.format())


def _observation(
    plan: AlphaPrivacyConformancePlan,
    surface: AlphaPrivacySurface,
    *records: AlphaPrivacyCaptureRecord,
    complete: bool = True,
    candidate_sha: str | None = None,
    run_ref: str | None = None,
    capture_receipt: str | None = None,
) -> AlphaPrivacySurfaceObservation:
    immutable_records = tuple(records)
    normalized_candidate = candidate_sha or plan.declared_candidate_sha
    normalized_run_ref = run_ref or plan.declared_run_ref
    receipt = capture_receipt or compute_alpha_privacy_capture_receipt(
        surface=surface,
        declared_candidate_sha=normalized_candidate,
        declared_run_ref=normalized_run_ref,
        declared_capture_source=plan.declared_capture_source,
        capture_complete=complete,
        records=immutable_records,
    )
    return AlphaPrivacySurfaceObservation(
        surface=surface,
        declared_candidate_sha=normalized_candidate,
        declared_run_ref=normalized_run_ref,
        declared_capture_source=plan.declared_capture_source,
        capture_complete=complete,
        records=immutable_records,
        capture_receipt=receipt,
    )


def _complete_capture(
    plan: AlphaPrivacyConformancePlan,
    *,
    replacement: AlphaPrivacySurfaceObservation | None = None,
) -> tuple[AlphaPrivacySurfaceObservation, ...]:
    return tuple(
        replacement
        if replacement is not None and replacement.surface is surface
        else _observation(plan, surface)
        for surface in ALPHA_PRIVACY_SURFACES
    )


def _evaluate_records(
    plan: AlphaPrivacyConformancePlan,
    *records: AlphaPrivacyCaptureRecord,
    surface: AlphaPrivacySurface = AlphaPrivacySurface.RUNTIME_FILESYSTEM,
):
    replacement = _observation(plan, surface, *records)
    return evaluate_alpha_privacy_conformance(
        enabled=True,
        plan=plan,
        observations=_complete_capture(plan, replacement=replacement),
    )


def test_closed_surface_vocabulary_covers_alpha_privacy_boundaries() -> None:
    assert ALPHA_PRIVACY_SURFACES == (
        AlphaPrivacySurface.RUNTIME_FILESYSTEM,
        AlphaPrivacySurface.EVIDENCE_FILESYSTEM,
        AlphaPrivacySurface.BROWSER_LOCAL_STORAGE,
        AlphaPrivacySurface.BROWSER_SESSION_STORAGE,
        AlphaPrivacySurface.BROWSER_INDEXED_DB,
        AlphaPrivacySurface.BROWSER_CACHE_STORAGE,
        AlphaPrivacySurface.BROWSER_COOKIES,
        AlphaPrivacySurface.BROWSER_OPFS,
        AlphaPrivacySurface.BROWSER_ADDRESS_HISTORY,
        AlphaPrivacySurface.BROWSER_NETWORK_URLS,
        AlphaPrivacySurface.BROWSER_CONSOLE,
        AlphaPrivacySurface.WEB_RUNTIME_LOGS,
        AlphaPrivacySurface.GATEWAY_RUNTIME_LOGS,
        AlphaPrivacySurface.AGENT_SERVER_RUNTIME_LOGS,
        AlphaPrivacySurface.CONTEXT,
        AlphaPrivacySurface.TASK_EVENT,
        AlphaPrivacySurface.WORK_PROGRESS,
        AlphaPrivacySurface.SPEECH_EVIDENCE,
        AlphaPrivacySurface.X_OBSERVABILITY_EVIDENCE,
    )


def test_plan_generates_separate_hidden_secret_and_audio_canaries(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    assert tuple(canary.kind for canary in plan.synthetic_secret_canaries) == tuple(
        SyntheticSecretKind
    )
    audio = plan.deterministic_audio_canary
    assert audio.raw_bytes != audio.utf8_bytes
    assert base64.b64decode(audio.base64_bytes) == audio.raw_bytes
    assert (
        max(len(canary.utf8_text) for canary in plan.synthetic_secret_canaries)
        <= MAX_CANARY_PATTERN_UNITS
    )
    assert all(
        canary.utf8_text not in repr(plan) for canary in plan.synthetic_secret_canaries
    )
    assert repr(audio.raw_bytes) not in repr(plan)
    with pytest.raises(FrozenInstanceError):
        plan.declared_run_ref = _OTHER_RUN_REF  # type: ignore[misc]


def test_complete_empty_record_capture_is_only_supplied_capture_clear(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    report = evaluate_alpha_privacy_conformance(
        enabled=True,
        plan=plan,
        observations=_complete_capture(plan),
    )

    assert (
        report.status
        is AlphaPrivacyConformanceStatus.SUPPLIED_CAPTURE_EXACT_MATCH_CLEAR
    )
    assert report.evaluated_surfaces == ALPHA_PRIVACY_SURFACES
    assert report.records_examined == 0
    assert report.chunks_examined == 0
    assert report.capture_receipts_consistent is True
    assert report.supplied_capture_coverage_complete is True
    assert report.supplied_capture_exact_match_clear is True
    assert report.binding_verified is False
    assert report.capture_verified is False
    assert report.coverage_is_caller_declared is True
    assert report.real_route_verified is False
    assert report.alpha_gate_pass is False
    assert report.raw_audio_default_persistence_verified is False
    assert report.unknown_secret_absence_verified is False
    assert report.default_product_configuration_verified is False
    assert report.evidence_scope == (
        "caller_supplied_capture_synthetic_exact_canaries_only"
    )
    assert report.excluded_audio_transformations == (
        "transformed_audio_bytes",
        "unlisted_audio_encodings",
        "resampled_audio",
    )


@pytest.mark.parametrize(
    ("attribute", "representation"),
    (
        ("utf8_text", CanaryRepresentation.UTF8_TEXT),
        ("utf8_bytes", CanaryRepresentation.UTF8_BYTES),
        ("base64_text", CanaryRepresentation.BASE64_TEXT),
        ("base64_bytes", CanaryRepresentation.BASE64_BYTES),
    ),
)
def test_every_secret_exact_representation_is_detected_without_value_echo(
    plan: AlphaPrivacyConformancePlan,
    attribute: str,
    representation: CanaryRepresentation,
) -> None:
    canary = next(
        item
        for item in plan.synthetic_secret_canaries
        if item.kind is SyntheticSecretKind.PROVIDER_CREDENTIAL
    )
    value = getattr(canary, attribute)
    report = _evaluate_records(plan, _record(value))

    assert report.status is AlphaPrivacyConformanceStatus.LEAK_DETECTED
    assert len(report.findings) == 1
    assert report.findings[0].family is CanaryFamily.SECRET
    assert report.findings[0].classification == "provider_credential"
    assert report.findings[0].representation is representation
    rendered = repr(report)
    assert (repr(value) if type(value) is bytes else value) not in rendered


@pytest.mark.parametrize(
    ("attribute", "representation"),
    (
        ("raw_bytes", CanaryRepresentation.RAW_BYTES),
        ("utf8_text", CanaryRepresentation.UTF8_TEXT),
        ("utf8_bytes", CanaryRepresentation.UTF8_BYTES),
        ("base64_text", CanaryRepresentation.BASE64_TEXT),
        ("base64_bytes", CanaryRepresentation.BASE64_BYTES),
    ),
)
def test_every_audio_exact_representation_is_detected(
    plan: AlphaPrivacyConformancePlan,
    attribute: str,
    representation: CanaryRepresentation,
) -> None:
    value = getattr(plan.deterministic_audio_canary, attribute)
    report = _evaluate_records(plan, _record(value))

    assert report.status is AlphaPrivacyConformanceStatus.LEAK_DETECTED
    assert len(report.findings) == 1
    assert report.findings[0].family is CanaryFamily.AUDIO_BYTES
    assert report.findings[0].classification == "raw_audio"
    assert report.findings[0].representation is representation


@pytest.mark.parametrize("surface", ALPHA_PRIVACY_SURFACES)
def test_exact_canary_is_detected_on_every_required_surface(
    plan: AlphaPrivacyConformancePlan,
    surface: AlphaPrivacySurface,
) -> None:
    canary = next(
        item
        for item in plan.synthetic_secret_canaries
        if item.kind is SyntheticSecretKind.UNAUTHORIZED_CONTENT
    )
    report = _evaluate_records(
        plan,
        _record(f"prefix:{canary.utf8_text}:suffix"),
        surface=surface,
    )

    assert report.status is AlphaPrivacyConformanceStatus.LEAK_DETECTED
    assert report.findings[0].surface is surface
    assert report.findings[0].classification == "unauthorized_content"


@pytest.mark.parametrize(
    ("kind", "surface"),
    (
        (
            SyntheticSecretKind.PROVIDER_CREDENTIAL,
            AlphaPrivacySurface.AGENT_SERVER_RUNTIME_LOGS,
        ),
        (
            SyntheticSecretKind.MEDIA_TICKET,
            AlphaPrivacySurface.BROWSER_NETWORK_URLS,
        ),
        (
            SyntheticSecretKind.DEVICE_IDENTITY,
            AlphaPrivacySurface.BROWSER_LOCAL_STORAGE,
        ),
        (
            SyntheticSecretKind.UNAUTHORIZED_CONTENT,
            AlphaPrivacySurface.TASK_EVENT,
        ),
    ),
)
def test_each_secret_class_is_detected_on_its_representative_surface(
    plan: AlphaPrivacyConformancePlan,
    kind: SyntheticSecretKind,
    surface: AlphaPrivacySurface,
) -> None:
    canary = next(item for item in plan.synthetic_secret_canaries if item.kind is kind)
    report = _evaluate_records(plan, _record(canary.utf8_text), surface=surface)

    assert report.findings[0].surface is surface
    assert report.findings[0].classification == kind.value


def test_text_canary_split_across_adjacent_chunks_in_one_record_is_detected(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    marker = plan.synthetic_secret_canaries[0].utf8_text
    first = len(marker) // 3
    second = (2 * len(marker)) // 3
    record = _record(
        "prefix:" + marker[:first],
        marker[first:second],
        marker[second:] + ":suffix",
    )

    report = _evaluate_records(plan, record)

    assert report.status is AlphaPrivacyConformanceStatus.LEAK_DETECTED
    assert report.findings[0].representation is CanaryRepresentation.UTF8_TEXT
    assert report.chunks_examined == 3


def test_raw_audio_split_across_adjacent_byte_chunks_in_one_record_is_detected(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    marker = plan.deterministic_audio_canary.raw_bytes
    points = (7, len(marker) // 2, len(marker) - 5)
    record = _record(
        b"prefix" + marker[: points[0]],
        marker[points[0] : points[1]],
        marker[points[1] : points[2]],
        marker[points[2] :] + b"suffix",
    )

    report = _evaluate_records(plan, record)

    assert report.status is AlphaPrivacyConformanceStatus.LEAK_DETECTED
    assert report.findings[0].family is CanaryFamily.AUDIO_BYTES
    assert report.findings[0].representation is CanaryRepresentation.RAW_BYTES


@pytest.mark.parametrize("as_bytes", (False, True))
def test_record_boundary_never_reassembles_a_canary(
    plan: AlphaPrivacyConformancePlan,
    as_bytes: bool,
) -> None:
    marker: str | bytes = plan.synthetic_secret_canaries[0].utf8_text
    if as_bytes:
        marker = marker.encode("utf-8")
    split = len(marker) // 2

    report = _evaluate_records(
        plan,
        _record(marker[:split]),
        _record(marker[split:]),
    )

    assert (
        report.status
        is AlphaPrivacyConformanceStatus.SUPPLIED_CAPTURE_EXACT_MATCH_CLEAR
    )
    assert report.findings == ()


def test_rolling_overlap_detects_canary_at_large_chunk_boundary(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    marker = plan.synthetic_secret_canaries[0].utf8_text
    split = len(marker) - 1
    record = _record(
        ("x" * 8_192) + marker[:split],
        marker[split:] + ("y" * 8_192),
    )

    report = _evaluate_records(plan, record)

    assert report.status is AlphaPrivacyConformanceStatus.LEAK_DETECTED


def test_near_match_does_not_become_a_fuzzy_leak_claim(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    marker = plan.synthetic_secret_canaries[0].utf8_text
    near_match = marker[:-1] + ("x" if marker[-1] != "x" else "y")

    report = _evaluate_records(plan, _record(near_match))

    assert (
        report.status
        is AlphaPrivacyConformanceStatus.SUPPLIED_CAPTURE_EXACT_MATCH_CLEAR
    )
    assert report.findings == ()


def test_transformed_unlisted_encoded_and_resampled_audio_are_out_of_scope(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    raw = plan.deterministic_audio_canary.raw_bytes
    report = _evaluate_records(
        plan,
        _record(raw[::-1]),
        _record(base64.b85encode(raw)),
        _record(raw[::2]),
    )

    assert (
        report.status
        is AlphaPrivacyConformanceStatus.SUPPLIED_CAPTURE_EXACT_MATCH_CLEAR
    )
    assert report.real_route_verified is False
    assert set(report.excluded_audio_transformations) == {
        "transformed_audio_bytes",
        "unlisted_audio_encodings",
        "resampled_audio",
    }


@pytest.mark.parametrize(
    ("chunks", "reason"),
    (
        ([], AlphaPrivacyRecordBuildReason.INVALID_CONTAINER),
        ((), AlphaPrivacyRecordBuildReason.EMPTY),
        (("text", b"bytes"), AlphaPrivacyRecordBuildReason.MIXED_CHUNK_TYPES),
        ((object(),), AlphaPrivacyRecordBuildReason.INVALID_CHUNK_TYPE),
    ),
)
def test_record_contract_rejects_mutable_empty_mixed_and_custom_chunks(
    chunks: object,
    reason: AlphaPrivacyRecordBuildReason,
) -> None:
    result = build_alpha_privacy_capture_record(chunks)

    assert result.reason is reason
    assert result.record is None
    assert result.ready is False


def test_record_contract_rejects_scalar_subclasses() -> None:
    class TextSubclass(str):
        pass

    result = build_alpha_privacy_capture_record((TextSubclass("private"),))

    assert result.reason is AlphaPrivacyRecordBuildReason.INVALID_CHUNK_TYPE


def test_chunk_record_and_observation_limits_are_fail_closed() -> None:
    assert _record("x" * MAX_CHUNK_BYTES).total_bytes == MAX_CHUNK_BYTES
    result = build_alpha_privacy_capture_record(("x" * (MAX_CHUNK_BYTES + 1),))
    assert result.reason is AlphaPrivacyRecordBuildReason.CHUNK_BYTES_EXCEEDED

    result = build_alpha_privacy_capture_record(
        tuple("" for _ in range(MAX_CHUNKS_PER_RECORD + 1))
    )
    assert result.reason is AlphaPrivacyRecordBuildReason.CHUNK_COUNT_EXCEEDED

    chunks_for_record_limit = tuple("x" * MAX_CHUNK_BYTES for _ in range(5))
    exact_record_limit = tuple("x" * MAX_CHUNK_BYTES for _ in range(4))
    assert _record(*exact_record_limit).total_bytes == MAX_RECORD_BYTES
    assert sum(len(chunk) for chunk in chunks_for_record_limit) > MAX_RECORD_BYTES
    result = build_alpha_privacy_capture_record(chunks_for_record_limit)
    assert result.reason is AlphaPrivacyRecordBuildReason.RECORD_BYTES_EXCEEDED


def test_overlength_text_is_rejected_before_bounded_utf8_encode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encode_calls: list[int] = []

    def forbidden_encode(chunk: str) -> bytes:
        encode_calls.append(len(chunk))
        raise AssertionError("overlength text reached bounded UTF-8 encode")

    monkeypatch.setattr(privacy_module, "_encode_bounded_text_chunk", forbidden_encode)
    overlength_chunks = (
        "OVERLONG_ASCII_PRIVATE_SENTINEL" + ("x" * MAX_CHUNK_BYTES),
        "OVERLONG_SURROGATE_PRIVATE_SENTINEL" + ("x" * MAX_CHUNK_BYTES) + "\ud800",
    )

    for chunk in overlength_chunks:
        result = build_alpha_privacy_capture_record((chunk,))
        assert result.reason is AlphaPrivacyRecordBuildReason.CHUNK_BYTES_EXCEEDED

    assert encode_calls == []


def test_bounded_utf8_encode_still_enforces_actual_byte_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_encode = privacy_module._encode_bounded_text_chunk
    encode_calls: list[int] = []

    def tracking_encode(chunk: str) -> bytes:
        encode_calls.append(len(chunk))
        return original_encode(chunk)

    monkeypatch.setattr(privacy_module, "_encode_bounded_text_chunk", tracking_encode)
    text = "\U0001f600" * ((MAX_CHUNK_BYTES // 4) + 1)

    result = build_alpha_privacy_capture_record((text,))

    assert result.reason is AlphaPrivacyRecordBuildReason.CHUNK_BYTES_EXCEEDED
    assert encode_calls == [len(text)]
    assert encode_calls[0] <= MAX_CHUNK_BYTES
    assert MAX_BOUNDED_TEXT_ENCODE_BYTES == 4 * MAX_CHUNK_BYTES


def test_observation_record_chunk_and_byte_limits_are_fail_closed(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    too_many_records = tuple(
        _record("") for _ in range(MAX_RECORDS_PER_OBSERVATION + 1)
    )
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        _observation(plan, AlphaPrivacySurface.RUNTIME_FILESYSTEM, *too_many_records)
    assert raised.value.reason == (
        AlphaPrivacyRecordBuildReason.OBSERVATION_RECORD_COUNT_EXCEEDED.value
    )

    too_many_chunks = tuple(
        _record(*("" for _ in range(MAX_CHUNKS_PER_RECORD)))
        for _ in range((MAX_CHUNKS_PER_OBSERVATION // MAX_CHUNKS_PER_RECORD) + 1)
    )
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        _observation(plan, AlphaPrivacySurface.RUNTIME_FILESYSTEM, *too_many_chunks)
    assert raised.value.reason == (
        AlphaPrivacyRecordBuildReason.OBSERVATION_CHUNK_COUNT_EXCEEDED.value
    )

    byte_heavy = tuple(
        _record("x" * MAX_CHUNK_BYTES)
        for _ in range((MAX_BYTES_PER_OBSERVATION // MAX_CHUNK_BYTES) + 1)
    )
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        _observation(plan, AlphaPrivacySurface.RUNTIME_FILESYSTEM, *byte_heavy)
    assert raised.value.reason == (
        AlphaPrivacyRecordBuildReason.OBSERVATION_BYTES_EXCEEDED.value
    )


def test_evaluator_global_record_chunk_byte_and_observation_limits(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    empty_record = _record("")
    max_records = tuple(empty_record for _ in range(MAX_RECORDS_PER_OBSERVATION))
    record_heavy_observations = tuple(
        _observation(plan, surface, *max_records)
        for surface in (
            *ALPHA_PRIVACY_SURFACES,
            ALPHA_PRIVACY_SURFACES[0],
            ALPHA_PRIVACY_SURFACES[1],
        )
    )
    assert len(record_heavy_observations) * len(max_records) > MAX_TOTAL_RECORDS
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        evaluate_alpha_privacy_conformance(
            enabled=True, plan=plan, observations=record_heavy_observations
        )
    assert raised.value.reason == "CAPTURE_LIMIT_EXCEEDED"

    max_chunk_record = _record(*("" for _ in range(MAX_CHUNKS_PER_RECORD)))
    chunks_per_observation = tuple(
        max_chunk_record
        for _ in range(MAX_CHUNKS_PER_OBSERVATION // MAX_CHUNKS_PER_RECORD)
    )
    chunk_heavy_observations = tuple(
        _observation(plan, surface, *chunks_per_observation)
        for surface in ALPHA_PRIVACY_SURFACES[:17]
    )
    assert len(chunk_heavy_observations) * MAX_CHUNKS_PER_OBSERVATION > MAX_TOTAL_CHUNKS
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        evaluate_alpha_privacy_conformance(
            enabled=True, plan=plan, observations=chunk_heavy_observations
        )
    assert raised.value.reason == "CAPTURE_LIMIT_EXCEEDED"

    max_byte_record = _record(*(b"x" * MAX_CHUNK_BYTES for _ in range(4)))
    byte_heavy_observations = tuple(
        _observation(plan, surface, max_byte_record)
        for surface in ALPHA_PRIVACY_SURFACES[:5]
    )
    assert len(byte_heavy_observations) * MAX_RECORD_BYTES > MAX_TOTAL_BYTES
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        evaluate_alpha_privacy_conformance(
            enabled=True, plan=plan, observations=byte_heavy_observations
        )
    assert raised.value.reason == "CAPTURE_LIMIT_EXCEEDED"

    one_observation = _observation(plan, AlphaPrivacySurface.RUNTIME_FILESYSTEM)
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        evaluate_alpha_privacy_conformance(
            enabled=True,
            plan=plan,
            observations=tuple(one_observation for _ in range(MAX_OBSERVATIONS + 1)),
        )
    assert raised.value.reason == "CAPTURE_LIMIT_EXCEEDED"


def test_public_capture_contract_has_no_mutable_nested_aba_path(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    caller_list = ["safe"]
    rejected = build_alpha_privacy_capture_record(caller_list)
    assert rejected.reason is AlphaPrivacyRecordBuildReason.INVALID_CONTAINER

    immutable_record = build_alpha_privacy_capture_record(
        tuple(caller_list)
    ).require_record()
    observation = _observation(
        plan, AlphaPrivacySurface.RUNTIME_FILESYSTEM, immutable_record
    )
    caller_list[0] = plan.synthetic_secret_canaries[0].utf8_text

    report = evaluate_alpha_privacy_conformance(
        enabled=True,
        plan=plan,
        observations=_complete_capture(plan, replacement=observation),
    )

    assert immutable_record.chunks == ("safe",)
    assert report.findings == ()
    with pytest.raises(FrozenInstanceError):
        immutable_record.chunks = ("changed",)  # type: ignore[misc]

    forged_record = object.__new__(AlphaPrivacyCaptureRecord)
    object.__setattr__(forged_record, "chunks", ("FORGED_PRIVATE_SENTINEL",))
    clean_observation = _observation(
        plan, AlphaPrivacySurface.RUNTIME_FILESYSTEM, immutable_record
    )
    object.__setattr__(clean_observation, "records", (forged_record,))
    error = _exception_from_evaluation(
        plan=plan,
        observations=_complete_capture(plan, replacement=clean_observation),
    )
    rendered = _traceback_with_locals(error)
    assert error.reason == AlphaPrivacyRecordBuildReason.FORGED_RECORD.value
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "FORGED_PRIVATE_SENTINEL" not in repr(forged_record)
    assert "FORGED_PRIVATE_SENTINEL" not in rendered


@pytest.mark.parametrize(
    ("chunks", "sentinel", "reason"),
    (
        (
            ("UTF8_PRIVATE_SENTINEL_\ud800_DO_NOT_ECHO",),
            "UTF8_PRIVATE_SENTINEL",
            AlphaPrivacyRecordBuildReason.INVALID_UTF8,
        ),
        (
            ("OVERSIZE_PRIVATE_SENTINEL" + ("x" * (MAX_CHUNK_BYTES + 1)),),
            "OVERSIZE_PRIVATE_SENTINEL",
            AlphaPrivacyRecordBuildReason.CHUNK_BYTES_EXCEEDED,
        ),
        (
            (
                "OVERSIZE_SURROGATE_PRIVATE_SENTINEL"
                + ("x" * MAX_CHUNK_BYTES)
                + "\ud800",
            ),
            "OVERSIZE_SURROGATE_PRIVATE_SENTINEL",
            AlphaPrivacyRecordBuildReason.CHUNK_BYTES_EXCEEDED,
        ),
        (
            ("MIXED_PRIVATE_SENTINEL", b"bytes"),
            "MIXED_PRIVATE_SENTINEL",
            AlphaPrivacyRecordBuildReason.MIXED_CHUNK_TYPES,
        ),
        (
            ["LIST_PRIVATE_SENTINEL"],
            "LIST_PRIVATE_SENTINEL",
            AlphaPrivacyRecordBuildReason.INVALID_CONTAINER,
        ),
    ),
)
def test_invalid_capture_traceback_locals_never_retain_raw_input(
    chunks: object,
    sentinel: str,
    reason: AlphaPrivacyRecordBuildReason,
) -> None:
    result = build_alpha_privacy_capture_record(chunks)
    assert result.reason is reason
    assert sentinel not in repr(result)

    error = _exception_from_build_result(result)
    rendered_traceback = _traceback_with_locals(error)

    assert error.reason == reason.value
    assert error.__cause__ is None
    assert error.__context__ is None
    assert sentinel not in repr(error)
    assert sentinel not in rendered_traceback


def test_forged_build_result_also_hides_its_record_field() -> None:
    sentinel = "FORGED_RESULT_PRIVATE_SENTINEL"
    result = AlphaPrivacyCaptureRecordBuildResult(
        reason=AlphaPrivacyRecordBuildReason.READY,
        record=sentinel,  # type: ignore[arg-type]
    )

    error = _exception_from_build_result(result)
    rendered_traceback = _traceback_with_locals(error)

    assert sentinel not in repr(result)
    assert sentinel not in repr(error)
    assert sentinel not in rendered_traceback


def test_record_and_observation_repr_hide_all_capture_chunks(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    private_capture = "REAL_OR_SYNTHETIC_PRIVATE_CAPTURE_SENTINEL"
    record = _record(private_capture)
    observation = _observation(
        plan, AlphaPrivacySurface.BROWSER_SESSION_STORAGE, record
    )

    assert private_capture not in repr(record)
    assert "chunks=" not in repr(record)
    assert private_capture not in repr(observation)
    assert "records=" not in repr(observation)


def test_receipt_binds_record_and_chunk_boundaries(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    common = {
        "surface": AlphaPrivacySurface.CONTEXT,
        "declared_candidate_sha": plan.declared_candidate_sha,
        "declared_run_ref": plan.declared_run_ref,
        "declared_capture_source": plan.declared_capture_source,
        "capture_complete": True,
    }
    split_chunks = compute_alpha_privacy_capture_receipt(
        **common, records=(_record("ab", "cd"),)
    )
    combined_chunk = compute_alpha_privacy_capture_receipt(
        **common, records=(_record("abcd"),)
    )
    split_records = compute_alpha_privacy_capture_receipt(
        **common, records=(_record("ab"), _record("cd"))
    )

    assert len({split_chunks, combined_chunk, split_records}) == 3


def test_receipt_mismatch_is_incomplete_and_never_capture_verified(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    original = _observation(
        plan, AlphaPrivacySurface.RUNTIME_FILESYSTEM, _record("before")
    )
    changed_record = _record("after")
    tampered = AlphaPrivacySurfaceObservation(
        surface=original.surface,
        declared_candidate_sha=original.declared_candidate_sha,
        declared_run_ref=original.declared_run_ref,
        declared_capture_source=original.declared_capture_source,
        capture_complete=original.capture_complete,
        records=(changed_record,),
        capture_receipt=original.capture_receipt,
    )

    report = evaluate_alpha_privacy_conformance(
        enabled=True,
        plan=plan,
        observations=_complete_capture(plan, replacement=tampered),
    )

    assert report.status is AlphaPrivacyConformanceStatus.INCOMPLETE
    assert report.capture_receipt_conflict_surfaces == (
        AlphaPrivacySurface.RUNTIME_FILESYSTEM,
    )
    assert report.capture_receipts_consistent is False
    assert report.capture_verified is False


def test_empty_surface_requires_a_canonical_integrity_receipt(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        AlphaPrivacySurfaceObservation(
            surface=AlphaPrivacySurface.BROWSER_LOCAL_STORAGE,
            declared_candidate_sha=plan.declared_candidate_sha,
            declared_run_ref=plan.declared_run_ref,
            declared_capture_source=plan.declared_capture_source,
            capture_complete=True,
            records=(),
            capture_receipt="",
        )

    assert raised.value.reason == "INVALID_CAPTURE_RECEIPT"


def test_receipt_changes_with_every_variable_binding_field(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    common = {
        "surface": AlphaPrivacySurface.CONTEXT,
        "declared_candidate_sha": plan.declared_candidate_sha,
        "declared_run_ref": plan.declared_run_ref,
        "declared_capture_source": plan.declared_capture_source,
        "capture_complete": True,
        "records": (_record("safe"),),
    }
    baseline = compute_alpha_privacy_capture_receipt(**common)

    assert baseline != compute_alpha_privacy_capture_receipt(
        **{**common, "surface": AlphaPrivacySurface.TASK_EVENT}
    )
    assert baseline != compute_alpha_privacy_capture_receipt(
        **{**common, "declared_candidate_sha": _OTHER_CANDIDATE}
    )
    assert baseline != compute_alpha_privacy_capture_receipt(
        **{**common, "declared_run_ref": _OTHER_RUN_REF}
    )
    assert baseline != compute_alpha_privacy_capture_receipt(
        **{**common, "capture_complete": False}
    )


def test_missing_duplicate_incomplete_and_conflicting_surfaces_fail_closed(
    plan: AlphaPrivacyConformancePlan,
) -> None:
    observations = list(_complete_capture(plan))
    observations = [
        item
        for item in observations
        if item.surface is not AlphaPrivacySurface.BROWSER_LOCAL_STORAGE
    ]
    observations.append(_observation(plan, AlphaPrivacySurface.BROWSER_SESSION_STORAGE))
    observations[
        next(
            index
            for index, item in enumerate(observations)
            if item.surface is AlphaPrivacySurface.CONTEXT
        )
    ] = _observation(plan, AlphaPrivacySurface.CONTEXT, complete=False)
    observations[
        next(
            index
            for index, item in enumerate(observations)
            if item.surface is AlphaPrivacySurface.TASK_EVENT
        )
    ] = _observation(
        plan,
        AlphaPrivacySurface.TASK_EVENT,
        candidate_sha=_OTHER_CANDIDATE,
    )

    report = evaluate_alpha_privacy_conformance(
        enabled=True, plan=plan, observations=tuple(observations)
    )

    assert report.status is AlphaPrivacyConformanceStatus.INCOMPLETE
    assert report.missing_surfaces == (AlphaPrivacySurface.BROWSER_LOCAL_STORAGE,)
    assert report.duplicate_surfaces == (AlphaPrivacySurface.BROWSER_SESSION_STORAGE,)
    assert report.incomplete_surfaces == (AlphaPrivacySurface.CONTEXT,)
    assert report.binding_conflict_surfaces == (AlphaPrivacySurface.TASK_EVENT,)
    assert report.supplied_capture_coverage_complete is False


class _ExplodingInput:
    def __getattribute__(self, name: str):
        raise AssertionError(f"disabled mode read {name}")


def test_disabled_mode_does_not_read_plan_or_observations() -> None:
    report = evaluate_alpha_privacy_conformance(
        enabled=False,
        plan=_ExplodingInput(),  # type: ignore[arg-type]
        observations=_ExplodingInput(),
    )

    assert report.status is AlphaPrivacyConformanceStatus.DISABLED
    assert report.observations_examined == 0
    assert report.records_examined == 0
    assert report.chunks_examined == 0
    assert report.binding_verified is False
    assert report.capture_verified is False
    assert report.real_route_verified is False
    assert report.alpha_gate_pass is False


def test_plan_and_observation_binding_inputs_are_strict() -> None:
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        AlphaPrivacyConformancePlan(
            declared_candidate_sha="not-a-sha",
            declared_run_ref=_RUN_REF,
            declared_capture_source=_SOURCE,
        )
    assert raised.value.reason == "INVALID_CANDIDATE_SHA"

    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        AlphaPrivacyConformancePlan(
            declared_candidate_sha=_CANDIDATE,
            declared_run_ref="sk-" + "live-looks-like-a-secret",
            declared_capture_source=_SOURCE,
        )
    assert raised.value.reason == "INVALID_RUN_REF"

    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        AlphaPrivacyConformancePlan(
            declared_candidate_sha=_CANDIDATE,
            declared_run_ref=_RUN_REF,
            declared_capture_source="caller-string",  # type: ignore[arg-type]
        )
    assert raised.value.reason == "INVALID_CAPTURE_SOURCE"


def test_record_kind_and_byte_binding_are_derived_and_immutable() -> None:
    text_record = _record("é")
    bytes_record = _record(b"\x00\xff")

    assert text_record.chunk_kind is AlphaPrivacyChunkKind.TEXT
    assert text_record.total_bytes == len("é".encode("utf-8"))
    assert bytes_record.chunk_kind is AlphaPrivacyChunkKind.BYTES
    assert bytes_record.total_bytes == 2
    with pytest.raises(FrozenInstanceError):
        text_record.total_bytes = 0  # type: ignore[misc]


def test_record_direct_construction_is_safely_blocked_and_partial_repr_is_constant() -> (
    None
):
    with pytest.raises(AlphaPrivacyConformanceViolation) as raised:
        AlphaPrivacyCaptureRecord()

    assert raised.value.reason == "CAPTURE_RECORD_FACTORY_REQUIRED"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    partial = object.__new__(AlphaPrivacyCaptureRecord)
    assert repr(partial) == "AlphaPrivacyCaptureRecord(<capture-redacted>)"
