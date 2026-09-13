# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hmac
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from typing import Mapping

import pytest

from jiuwenswarm.server.live_voice.observability_correlation_contract import (
    OBSERVABILITY_CORRELATION_CONTRACT_VERSION,
    CORRELATION_TOKENIZATION_RECEIPT_VERSION,
    BoundedMetricDimensions,
    CorrelationCausationLink,
    CorrelationContractViolation,
    CorrelationEvaluationReason,
    CorrelationIdentityKind,
    CorrelationReplayReason,
    CorrelationTokenizationIssuer,
    CorrelationTokenizationMethod,
    CorrelationTokenizationReceipt,
    MAX_CORRELATION_IDENTITY_LENGTH,
    MAX_CORRELATION_LINKS,
    MAX_METRIC_DIMENSIONS,
    MetricDimension,
    MetricDimensionKey,
    ObservabilityCorrelationMap,
    PrivateCorrelationContent,
    evaluate_observability_correlation_map,
    evaluate_observability_correlation_replay,
)


_SCOPE_TAG = "a1b2c3d4e5f60718"
_TEST_TOKENIZATION_KEY = b"test-only-owner-key-not-a-product-secret"
_TOKEN_FIELDS = (
    "map_id",
    "correlation_id",
    "subject_id",
    "project_id",
    "session_id",
    "interaction_id",
    "response_id",
    "task_id",
    "attempt_id",
    "command_id",
    "event_id",
    "outbox_id",
    "executor_id",
    "checkpoint_id",
    "effect_id",
    "presentation_id",
)


def _token(
    kind: str,
    seed: str,
    *,
    scope_tag: str = _SCOPE_TAG,
    key: bytes = _TEST_TOKENIZATION_KEY,
) -> str:
    digest = hmac.new(
        key,
        f"{scope_tag}\0{kind}\0{seed}".encode(),
        sha256,
    ).hexdigest()
    return f"lvpub:{kind}:v1:{scope_tag}:{digest}"


def _receipt(
    token_values: dict[str, object],
    *,
    key: bytes = _TEST_TOKENIZATION_KEY,
) -> CorrelationTokenizationReceipt:
    encoded = "\n".join(
        f"{field_name}={token_values[field_name]}"
        for field_name in _TOKEN_FIELDS
        if token_values.get(field_name) is not None
    ).encode("ascii")
    token_set_digest = sha256(encoded).hexdigest()
    return CorrelationTokenizationReceipt(
        contract_version=CORRELATION_TOKENIZATION_RECEIPT_VERSION,
        receipt_id=_token("receipt", f"receipt:{token_set_digest}", key=key),
        issuer=CorrelationTokenizationIssuer.IDENTITY_PROJECTION_OWNER,
        method=CorrelationTokenizationMethod.HMAC_SHA256,
        scope_tag=_SCOPE_TAG,
        token_set_digest=token_set_digest,
    )


def _receipt_verifier(
    key: bytes,
):
    def verify(
        receipt: CorrelationTokenizationReceipt,
        token_values: Mapping[str, str | None],
    ) -> bool:
        encoded = "\n".join(
            f"{field_name}={value}"
            for field_name, value in token_values.items()
            if value is not None
        ).encode("ascii")
        token_set_digest = sha256(encoded).hexdigest()
        expected_receipt_id = _token(
            "receipt",
            f"receipt:{token_set_digest}",
            scope_tag=receipt.scope_tag,
            key=key,
        )
        return hmac.compare_digest(
            receipt.token_set_digest, token_set_digest
        ) and hmac.compare_digest(receipt.receipt_id, expected_receipt_id)

    return verify


_TRUSTED_RECEIPT_VERIFIER = _receipt_verifier(_TEST_TOKENIZATION_KEY)


def _dimensions() -> BoundedMetricDimensions:
    return BoundedMetricDimensions(
        labels=tuple(
            sorted(
                (
                    MetricDimension(
                        MetricDimensionKey.SEGMENT_NAME,
                        "speech.recognition",
                    ),
                    MetricDimension(
                        MetricDimensionKey.IMPLEMENTATION_CLASS,
                        "formal",
                    ),
                ),
                key=lambda label: label.key.value,
            )
        )
    )


def _map() -> ObservabilityCorrelationMap:
    token_values: dict[str, object] = {
        "map_id": _token("map", "map-1"),
        "correlation_id": _token("correlation", "correlation-1"),
        "subject_id": _token("subject", "subject-1"),
        "project_id": _token("project", "project-1"),
        "session_id": _token("session", "session-1"),
        "interaction_id": _token("interaction", "interaction-1"),
        "response_id": _token("response", "response-1"),
        "task_id": _token("task", "task-1"),
        "attempt_id": _token("attempt", "attempt-1"),
    }
    links = (
        CorrelationCausationLink(
            CorrelationIdentityKind.SUBJECT,
            token_values["subject_id"],
            CorrelationIdentityKind.PROJECT,
            token_values["project_id"],
        ),
        CorrelationCausationLink(
            CorrelationIdentityKind.PROJECT,
            token_values["project_id"],
            CorrelationIdentityKind.SESSION,
            token_values["session_id"],
        ),
        CorrelationCausationLink(
            CorrelationIdentityKind.INTERACTION,
            token_values["interaction_id"],
            CorrelationIdentityKind.RESPONSE,
            token_values["response_id"],
        ),
        CorrelationCausationLink(
            CorrelationIdentityKind.SESSION,
            token_values["session_id"],
            CorrelationIdentityKind.INTERACTION,
            token_values["interaction_id"],
        ),
        CorrelationCausationLink(
            CorrelationIdentityKind.SESSION,
            token_values["session_id"],
            CorrelationIdentityKind.TASK,
            token_values["task_id"],
        ),
        CorrelationCausationLink(
            CorrelationIdentityKind.TASK,
            token_values["task_id"],
            CorrelationIdentityKind.ATTEMPT,
            token_values["attempt_id"],
        ),
    )
    return ObservabilityCorrelationMap(
        contract_version=OBSERVABILITY_CORRELATION_CONTRACT_VERSION,
        map_id=token_values["map_id"],
        correlation_id=token_values["correlation_id"],
        subject_id=token_values["subject_id"],
        project_id=token_values["project_id"],
        session_id=token_values["session_id"],
        tokenization_receipt=_receipt(token_values),
        interaction_id=token_values["interaction_id"],
        response_id=token_values["response_id"],
        response_generation=2,
        task_id=token_values["task_id"],
        attempt_id=token_values["attempt_id"],
        metric_dimensions=_dimensions(),
        causation=tuple(sorted(links, key=lambda link: link.sort_key())),
    )


def _minimal(**overrides: object) -> ObservabilityCorrelationMap:
    values: dict[str, object] = {
        "contract_version": OBSERVABILITY_CORRELATION_CONTRACT_VERSION,
        "map_id": _token("map", "minimal-map"),
        "correlation_id": _token("correlation", "minimal-correlation"),
        "subject_id": _token("subject", "minimal-subject"),
        "project_id": _token("project", "minimal-project"),
        "session_id": _token("session", "minimal-session"),
        "metric_dimensions": BoundedMetricDimensions(labels=()),
    }
    values.update(overrides)
    if "tokenization_receipt" not in overrides:
        values["tokenization_receipt"] = _receipt(values)
    if "causation" not in overrides:
        root_links = (
            CorrelationCausationLink(
                CorrelationIdentityKind.SUBJECT,
                values["subject_id"],
                CorrelationIdentityKind.PROJECT,
                values["project_id"],
            ),
            CorrelationCausationLink(
                CorrelationIdentityKind.PROJECT,
                values["project_id"],
                CorrelationIdentityKind.SESSION,
                values["session_id"],
            ),
        )
        values["causation"] = tuple(
            sorted(root_links, key=lambda link: link.sort_key())
        )
    return ObservabilityCorrelationMap(**values)


def _full_map() -> ObservabilityCorrelationMap:
    identities = {
        kind.value: _token(kind.value, f"full-{kind.value}")
        for kind in CorrelationIdentityKind
    }
    edge_kinds = (
        ("subject", "project"),
        ("project", "session"),
        ("session", "interaction"),
        ("session", "task"),
        ("interaction", "response"),
        ("task", "attempt"),
        ("task", "command"),
        ("task", "event"),
        ("command", "event"),
        ("command", "outbox"),
        ("attempt", "event"),
        ("attempt", "outbox"),
        ("attempt", "executor"),
        ("outbox", "executor"),
        ("executor", "event"),
        ("executor", "checkpoint"),
        ("executor", "effect"),
        ("response", "presentation"),
        ("event", "presentation"),
    )
    links = tuple(
        sorted(
            (
                CorrelationCausationLink(
                    CorrelationIdentityKind(cause),
                    identities[cause],
                    CorrelationIdentityKind(effect),
                    identities[effect],
                )
                for cause, effect in edge_kinds
            ),
            key=lambda link: link.sort_key(),
        )
    )
    dimensions = BoundedMetricDimensions(
        labels=tuple(
            sorted(
                (
                    MetricDimension(MetricDimensionKey.CANCEL_SCOPE, "task.cancel"),
                    MetricDimension(MetricDimensionKey.ERROR_CODE, "CONFLICT"),
                    MetricDimension(
                        MetricDimensionKey.IMPLEMENTATION_CLASS,
                        "formal",
                    ),
                    MetricDimension(MetricDimensionKey.OUTCOME, "completed"),
                    MetricDimension(MetricDimensionKey.REASON_CODE, "RECOVERED"),
                    MetricDimension(
                        MetricDimensionKey.SEGMENT_NAME,
                        "speech.recognition",
                    ),
                    MetricDimension(MetricDimensionKey.STATE, "terminal"),
                ),
                key=lambda label: label.key.value,
            )
        )
    )
    return ObservabilityCorrelationMap(
        contract_version=OBSERVABILITY_CORRELATION_CONTRACT_VERSION,
        map_id=_token("map", "full-map"),
        correlation_id=_token("correlation", "full-correlation"),
        subject_id=identities["subject"],
        project_id=identities["project"],
        session_id=identities["session"],
        tokenization_receipt=_receipt(
            {
                "map_id": _token("map", "full-map"),
                "correlation_id": _token("correlation", "full-correlation"),
                "subject_id": identities["subject"],
                "project_id": identities["project"],
                "session_id": identities["session"],
                "interaction_id": identities["interaction"],
                "response_id": identities["response"],
                "task_id": identities["task"],
                "attempt_id": identities["attempt"],
                "command_id": identities["command"],
                "event_id": identities["event"],
                "outbox_id": identities["outbox"],
                "executor_id": identities["executor"],
                "checkpoint_id": identities["checkpoint"],
                "effect_id": identities["effect"],
                "presentation_id": identities["presentation"],
            }
        ),
        interaction_id=identities["interaction"],
        response_id=identities["response"],
        response_generation=9_007_199_254_740_991,
        task_id=identities["task"],
        attempt_id=identities["attempt"],
        command_id=identities["command"],
        event_id=identities["event"],
        outbox_id=identities["outbox"],
        executor_id=identities["executor"],
        checkpoint_id=identities["checkpoint"],
        effect_id=identities["effect"],
        presentation_id=identities["presentation"],
        metric_dimensions=dimensions,
        causation=links,
    )


def _assert_zero_effect(result: object) -> None:
    for name in (
        "exporter_called",
        "network_changed",
        "persistence_changed",
        "lifecycle_authority_exercised",
        "business_result_changed",
        "agent_effect",
        "tool_effect",
        "task_effect",
        "audio_effect",
        "history_effect",
    ):
        assert getattr(result, name) is False


def _replace_tokens(
    candidate: ObservabilityCorrelationMap,
    **changes: str,
) -> ObservabilityCorrelationMap:
    token_values = {
        field_name: changes.get(field_name, getattr(candidate, field_name))
        for field_name in _TOKEN_FIELDS
    }
    return replace(
        candidate,
        tokenization_receipt=_receipt(token_values),
        **changes,
    )


def test_valid_map_keeps_high_cardinality_identifiers_out_of_metric_dimensions() -> (
    None
):
    candidate = _map()
    result = evaluate_observability_correlation_map(
        candidate,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )

    assert result.ready is True
    assert result.reason is CorrelationEvaluationReason.READY
    assert result.correlation_map == candidate
    assert result.correlation_map.trace_identities()["task_id"] == _token(
        "task", "task-1"
    )
    assert tuple(result.correlation_map.trace_identities()) == (
        "map_id",
        "tokenization_receipt_id",
        "correlation_id",
        "subject_id",
        "project_id",
        "session_id",
        "interaction_id",
        "response_id",
        "task_id",
        "attempt_id",
        "response_generation",
    )
    assert result.correlation_map.metric_dimensions.to_dict() == {
        "live_voice.implementation_class": "formal",
        "live_voice.segment_name": "speech.recognition",
    }
    assert not set(result.correlation_map.metric_dimensions.to_dict()).intersection(
        {"task_id", "session_id", "response_id"}
    )
    _assert_zero_effect(result)
    with pytest.raises(FrozenInstanceError):
        candidate.task_id = _token("task", "task-2")  # type: ignore[misc]


@pytest.mark.parametrize(
    "labels",
    [
        (MetricDimension(MetricDimensionKey.SEGMENT_NAME, "speech.recognition"),) * 2,
        (
            MetricDimension(
                MetricDimensionKey.SEGMENT_NAME,
                "speech.recognition",
            ),
            MetricDimension(MetricDimensionKey.IMPLEMENTATION_CLASS, "formal"),
        ),
    ],
)
def test_metric_dimensions_reject_duplicates_and_noncanonical_order(
    labels: tuple,
) -> None:
    with pytest.raises(CorrelationContractViolation):
        BoundedMetricDimensions(labels=labels)


def test_metric_dimensions_reject_open_keys_and_values() -> None:
    with pytest.raises(CorrelationContractViolation):
        MetricDimension("task_id", "task-1")  # type: ignore[arg-type]
    with pytest.raises(CorrelationContractViolation):
        MetricDimension(MetricDimensionKey.SEGMENT_NAME, "customer-id")


def test_parent_and_causation_invariants_fail_closed() -> None:
    candidate = _map()
    with pytest.raises(CorrelationContractViolation):
        replace(candidate, response_generation=None)
    with pytest.raises(CorrelationContractViolation):
        replace(candidate, causation=tuple(reversed(candidate.causation)))
    bad_link = CorrelationCausationLink(
        CorrelationIdentityKind.TASK,
        _token("task", "another-task"),
        CorrelationIdentityKind.ATTEMPT,
        _token("attempt", "attempt-1"),
    )
    with pytest.raises(CorrelationContractViolation):
        replace(candidate, causation=(bad_link,))
    with pytest.raises(CorrelationContractViolation):
        CorrelationCausationLink(
            CorrelationIdentityKind.RESPONSE,
            _token("response", "response-1"),
            CorrelationIdentityKind.TASK,
            _token("task", "task-1"),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "response_id": _token("response", "orphan-response"),
            "response_generation": 1,
        },
        {"attempt_id": _token("attempt", "orphan-attempt")},
        {"command_id": _token("command", "orphan-command")},
        {"event_id": _token("event", "orphan-event")},
        {"outbox_id": _token("outbox", "orphan-outbox")},
        {"executor_id": _token("executor", "orphan-executor")},
        {"checkpoint_id": _token("checkpoint", "orphan-checkpoint")},
        {"effect_id": _token("effect", "orphan-effect")},
        {"presentation_id": _token("presentation", "orphan-presentation")},
    ],
)
def test_every_optional_identity_requires_its_parent_context(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(CorrelationContractViolation):
        _minimal(**overrides)


def test_public_tokens_are_stable_field_scoped_and_reject_ordinary_pii() -> None:
    assert _token("task", "stable-id") == _token("task", "stable-id")
    assert _token("subject", "alice@example.com") != (
        f"lvpub:subject:v1:{_SCOPE_TAG}:{sha256(b'alice@example.com').hexdigest()}"
    )
    assert len(_token("presentation", "longest-kind")) == (
        MAX_CORRELATION_IDENTITY_LENGTH
    )
    with pytest.raises(CorrelationContractViolation):
        _minimal(project_id=_token("subject", "wrong-scope"))
    with pytest.raises(CorrelationContractViolation):
        _minimal(task_id=f"lvpub:task:v1:{_SCOPE_TAG}:" + "a" * 63)
    with pytest.raises(CorrelationContractViolation):
        _minimal(task_id=f"lvpub:task:v1:{_SCOPE_TAG}:" + "a" * 65)
    with pytest.raises(CorrelationContractViolation):
        _minimal(
            subject_id=_token(
                "subject",
                "tenant-b-subject",
                scope_tag="b1b2b3b4b5b60718",
            )
        )
    with pytest.raises(PrivateCorrelationContent, match="private content"):
        _minimal(subject_id="alice@example.com")
    with pytest.raises(PrivateCorrelationContent, match="private content"):
        _minimal(subject_id="+33 6 12 34 56 78")
    with pytest.raises(PrivateCorrelationContent, match="private content"):
        _minimal(subject_id="transcript-secret")

    candidate = _minimal()
    raw_hashed_pii = (
        f"lvpub:subject:v1:{_SCOPE_TAG}:{sha256(b'alice@example.com').hexdigest()}"
    )
    object.__setattr__(candidate, "subject_id", raw_hashed_pii)
    rejected = evaluate_observability_correlation_map(
        candidate,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )
    assert rejected.reason is CorrelationEvaluationReason.INVALID_MAP
    _assert_zero_effect(rejected)


def test_root_scope_causation_and_owner_receipt_are_mandatory() -> None:
    with pytest.raises(CorrelationContractViolation, match="mandatory root causation"):
        _minimal(causation=())
    with pytest.raises(CorrelationContractViolation, match="tokenization receipt"):
        _minimal(tokenization_receipt=object())


@pytest.mark.parametrize(
    "receipt_override",
    [
        {"issuer": "identity_projection_owner"},
        {"method": "sha256"},
        {"raw_identity_included": True},
        {"token_set_digest": "a" * 64},
    ],
)
def test_receipt_rejects_non_owner_non_hmac_raw_or_unbound_claims(
    receipt_override: dict[str, object],
) -> None:
    candidate = _minimal()
    with pytest.raises(CorrelationContractViolation):
        replace(
            candidate,
            tokenization_receipt=replace(
                candidate.tokenization_receipt,
                **receipt_override,
            ),
        )


def test_missing_false_non_bool_or_raising_trust_anchor_fails_closed() -> None:
    def raising_verifier(
        receipt: CorrelationTokenizationReceipt,
        token_values: Mapping[str, str | None],
    ) -> bool:
        raise RuntimeError((receipt.contract_version, len(token_values)))

    candidate = _minimal()
    for verifier in (
        None,
        lambda receipt, token_values: False,
        lambda receipt, token_values: 1,
        raising_verifier,
    ):
        result = evaluate_observability_correlation_map(
            candidate,
            enabled=True,
            trusted_receipt_verifier=verifier,
        )
        assert result.reason is CorrelationEvaluationReason.INVALID_MAP
        _assert_zero_effect(result)
        replay = evaluate_observability_correlation_replay(
            candidate,
            candidate,
            enabled=True,
            trusted_receipt_verifier=verifier,
        )
        assert replay.reason is CorrelationReplayReason.INVALID_MAP
        _assert_zero_effect(replay)


def test_trusted_anchor_rejects_bare_sha_with_matching_self_signed_receipt() -> None:
    candidate = _minimal()
    bare_hashed_pii = (
        f"lvpub:subject:v1:{_SCOPE_TAG}:{sha256(b'alice@example.com').hexdigest()}"
    )
    token_values = {
        field_name: getattr(candidate, field_name) for field_name in _TOKEN_FIELDS
    }
    token_values["subject_id"] = bare_hashed_pii
    root_links = (
        CorrelationCausationLink(
            CorrelationIdentityKind.SUBJECT,
            bare_hashed_pii,
            CorrelationIdentityKind.PROJECT,
            candidate.project_id,
        ),
        CorrelationCausationLink(
            CorrelationIdentityKind.PROJECT,
            candidate.project_id,
            CorrelationIdentityKind.SESSION,
            candidate.session_id,
        ),
    )
    attacker_key = b"attacker-controlled-self-signing-key"
    forged = replace(
        candidate,
        subject_id=bare_hashed_pii,
        tokenization_receipt=_receipt(token_values, key=attacker_key),
        causation=tuple(sorted(root_links, key=lambda link: link.sort_key())),
    )

    result = evaluate_observability_correlation_map(
        forged,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )
    assert result.reason is CorrelationEvaluationReason.INVALID_MAP
    _assert_zero_effect(result)


def test_maximum_links_dimensions_and_generation_are_exactly_bounded() -> None:
    candidate = _full_map()
    assert len(candidate.causation) == MAX_CORRELATION_LINKS
    assert len(candidate.metric_dimensions.labels) == MAX_METRIC_DIMENSIONS
    assert (
        evaluate_observability_correlation_map(
            candidate,
            enabled=True,
            trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
        ).ready
        is True
    )

    with pytest.raises(CorrelationContractViolation):
        replace(candidate, causation=candidate.causation + (candidate.causation[0],))
    with pytest.raises(CorrelationContractViolation):
        BoundedMetricDimensions(
            labels=candidate.metric_dimensions.labels
            + (candidate.metric_dimensions.labels[0],)
        )
    with pytest.raises(CorrelationContractViolation):
        replace(candidate, response_generation=9_007_199_254_740_992)


def test_revalidation_rejects_forged_private_and_invalid_maps_with_zero_effect() -> (
    None
):
    private = _map()
    object.__setattr__(private, "task_id", "alice@example.com")
    private_result = evaluate_observability_correlation_map(
        private,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )
    assert private_result.reason is CorrelationEvaluationReason.PRIVATE_CONTENT_REJECTED
    _assert_zero_effect(private_result)

    invalid = _map()
    object.__setattr__(invalid, "response_generation", -1)
    invalid_result = evaluate_observability_correlation_map(
        invalid,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )
    assert invalid_result.reason is CorrelationEvaluationReason.INVALID_MAP
    _assert_zero_effect(invalid_result)


@pytest.mark.parametrize(
    "field_name",
    ["metric_dimensions", "tokenization_receipt", "causation"],
)
def test_nested_duck_values_reject_before_any_getter_is_touched(
    field_name: str,
) -> None:
    class Poison:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(name)

    candidate = _map()
    forged: object = (Poison(),) if field_name == "causation" else Poison()
    object.__setattr__(candidate, field_name, forged)
    result = evaluate_observability_correlation_map(
        candidate,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )
    assert result.reason is CorrelationEvaluationReason.INVALID_MAP
    _assert_zero_effect(result)


def test_replay_is_idempotent_only_for_the_exact_map() -> None:
    candidate = _map()
    exact = evaluate_observability_correlation_replay(
        candidate,
        candidate,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )
    assert exact.accepted is True
    assert exact.reason is CorrelationReplayReason.IDEMPOTENT
    _assert_zero_effect(exact)

    different_identity = _replace_tokens(
        candidate,
        map_id=_token("map", "map-2"),
    )
    mismatch = evaluate_observability_correlation_replay(
        candidate,
        different_identity,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )
    assert mismatch.reason is CorrelationReplayReason.IDENTITY_MISMATCH
    _assert_zero_effect(mismatch)

    conflict = _replace_tokens(
        candidate,
        correlation_id=_token("correlation", "correlation-2"),
    )
    conflicted = evaluate_observability_correlation_replay(
        candidate,
        conflict,
        enabled=True,
        trusted_receipt_verifier=_TRUSTED_RECEIPT_VERIFIER,
    )
    assert conflicted.reason is CorrelationReplayReason.CONFLICT
    _assert_zero_effect(conflicted)


def test_feature_off_short_circuits_before_touching_candidate() -> None:
    class Poison:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(name)

    result = evaluate_observability_correlation_map(
        Poison(),
        enabled=False,
        trusted_receipt_verifier=Poison(),
    )
    assert result.reason is CorrelationEvaluationReason.FEATURE_DISABLED
    _assert_zero_effect(result)

    replay = evaluate_observability_correlation_replay(
        Poison(),
        Poison(),
        enabled=False,
        trusted_receipt_verifier=Poison(),
    )
    assert replay.reason is CorrelationReplayReason.FEATURE_DISABLED
    _assert_zero_effect(replay)
