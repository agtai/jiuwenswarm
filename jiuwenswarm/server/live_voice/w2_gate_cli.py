# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Operational signer, importer, and evaluator for the W2 Demo Gate."""

from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from jiuwenswarm.server.live_voice.w2_demo_gate import (
    MAX_W2_ARTIFACT_BYTES,
    W2AutomatedVerificationEvidence,
    W2CandidateEvidence,
    W2CapabilityPlane,
    W2EvidenceArtifact,
    W2EvidenceArtifactSlot,
    W2EvidenceKind,
    W2EvidenceTrustPolicy,
    W2FaultEvidence,
    W2GateResult,
    W2Invariant,
    W2InvariantEvidence,
    W2JourneyStep,
    W2JourneyStepEvidence,
    W2LedgerAward,
    W2LedgerItem,
    W2ReconciliationOutcome,
    W2RestartEvidence,
    W2RouteClass,
    W2RuntimeArtifactSlot,
    W2ShowcaseRun,
    W2TaskReconciliationEvidence,
    evaluate_w2_demo_gate,
    verify_w2_assisted_receipt_content,
    verify_w2_evidence_content,
    verify_w2_planned_product_faults,
    verify_w2_runtime_jsonl_content,
    w2_artifact_signature_payload,
)
from jiuwenswarm.server.live_voice.w2_evidence_exporter import (
    verify_w2_candidate_checkout,
)


_MANIFEST_SCHEMA = "live-voice.w2-gate-manifest.v1"
_TRUST_POLICY_SCHEMA = "live-voice.w2-trust-policy.v2"
_ARTIFACT_KINDS = frozenset({"runtime_jsonl", "automated_report", "assisted_receipt"})
_OFFLINE_SIGNABLE_ARTIFACT_KINDS = frozenset({"automated_report", "assisted_receipt"})


def _closed_dict(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields are not closed")
    return value


def _records(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 4_096:
        raise ValueError(f"{label} must be a bounded list")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} contains an invalid record")
    return value


def _tuple(value: object, label: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return tuple(value)


def _manifest_path(base: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    candidate = Path(value)
    resolved = candidate if candidate.is_absolute() else base / candidate
    resolved = resolved.resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} must identify an existing file")
    return resolved


def _read_bounded(path: Path) -> bytes:
    size = path.stat().st_size
    if not 0 < size <= MAX_W2_ARTIFACT_BYTES:
        raise ValueError("evidence content is empty or exceeds the artifact limit")
    return path.read_bytes()


def _signature(path: Path) -> str:
    value = path.read_text(encoding="ascii").strip()
    if re.fullmatch(r"[0-9a-f]{128}", value) is None:
        raise ValueError("signature file must contain one Ed25519 signature")
    return value


def _dataclass_keys(owner: type[object]) -> set[str]:
    return {item.name for item in fields(owner) if not item.name.startswith("_")}


def _candidate(value: object) -> W2CandidateEvidence:
    data = _closed_dict(value, _dataclass_keys(W2CandidateEvidence), "candidate")
    return W2CandidateEvidence(
        **{
            **data,
            "model_labels": _tuple(data["model_labels"], "candidate model_labels"),
            "provider_labels": _tuple(
                data["provider_labels"], "candidate provider_labels"
            ),
            "active_planes": frozenset(
                W2CapabilityPlane(item)
                for item in _tuple(data["active_planes"], "candidate active_planes")
            ),
        }
    )


def _trust_policy(value: object, *, base: Path) -> W2EvidenceTrustPolicy:
    policy = _closed_dict(
        value,
        {
            "schema",
            "policy_id",
            "repository_path",
            "candidate",
            "evidence_set_id",
            "runtime_slots",
            "artifact_slots",
            "signers",
        },
        "trust policy",
    )
    if policy["schema"] != _TRUST_POLICY_SCHEMA:
        raise ValueError("trust policy schema is unsupported")
    if not isinstance(policy["policy_id"], str) or not policy["policy_id"]:
        raise ValueError("trust policy_id is required")
    public_keys: dict[str, bytes] = {}
    roles: dict[str, frozenset[W2EvidenceKind]] = {}
    principals: dict[str, str] = {}
    producers: dict[str, str | None] = {}
    for raw in _records(policy["signers"], "trust signers"):
        data = _closed_dict(
            raw,
            {
                "signer_id",
                "principal_id",
                "public_key_hex",
                "role",
                "producer_id",
            },
            "trust signer",
        )
        signer_id = data["signer_id"]
        if not isinstance(signer_id, str) or signer_id in public_keys:
            raise ValueError("trust signer_id is invalid or duplicated")
        key_hex = data["public_key_hex"]
        if (
            not isinstance(key_hex, str)
            or re.fullmatch(r"[0-9a-f]{64}", key_hex) is None
        ):
            raise ValueError("trust signer must embed one raw Ed25519 public key")
        public_keys[signer_id] = bytes.fromhex(key_hex)
        principal_id = data["principal_id"]
        if not isinstance(principal_id, str) or not principal_id:
            raise ValueError("trust principal_id is required")
        principals[signer_id] = principal_id
        role = W2EvidenceKind(data["role"])
        roles[signer_id] = frozenset({role})
        producer_id = data["producer_id"]
        if producer_id is not None and (
            not isinstance(producer_id, str) or not producer_id
        ):
            raise ValueError("trust producer_id is invalid")
        producers[signer_id] = producer_id
    candidate = _closed_dict(
        policy["candidate"],
        {"candidate_sha", "environment_id", "session_id", "mode_id"},
        "trust candidate",
    )
    candidate_binding = tuple(
        candidate[field_name]
        for field_name in ("candidate_sha", "environment_id", "session_id", "mode_id")
    )
    slots: list[W2RuntimeArtifactSlot] = []
    for raw in _records(policy["runtime_slots"], "runtime slots"):
        data = _closed_dict(
            raw,
            {
                "artifact_id",
                "artifact_sequence",
                "producer_id",
                "process_epoch",
                "predecessor_artifact_id",
                "showcase_run",
            },
            "runtime slot",
        )
        slots.append(W2RuntimeArtifactSlot(**data))
    artifact_slots: list[W2EvidenceArtifactSlot] = []
    for raw in _records(policy["artifact_slots"], "artifact slots"):
        data = _closed_dict(
            raw,
            {
                "artifact_id",
                "artifact_sequence",
                "evidence_kind",
                "signer_id",
                "source_label",
                "expected_subjects",
            },
            "artifact slot",
        )
        artifact_slots.append(
            W2EvidenceArtifactSlot(
                artifact_id=data["artifact_id"],
                artifact_sequence=data["artifact_sequence"],
                evidence_kind=W2EvidenceKind(data["evidence_kind"]),
                signer_id=data["signer_id"],
                source_label=data["source_label"],
                expected_subjects=tuple(
                    _tuple(data["expected_subjects"], "artifact slot subjects")
                ),
            )
        )
    repository_path = Path(policy["repository_path"])
    if not repository_path.is_absolute():
        repository_path = (base / repository_path).resolve()
    return W2EvidenceTrustPolicy(
        public_keys=public_keys,
        signer_roles=roles,
        principal_ids=principals,
        producer_ids=producers,
        candidate_binding=candidate_binding,  # type: ignore[arg-type]
        evidence_set_id=policy["evidence_set_id"],
        runtime_slots=tuple(slots),
        artifact_slots=tuple(artifact_slots),
        policy_id=policy["policy_id"],
        repository_path=str(repository_path.resolve()),
    )


def _load_trust_policy(
    policy_path: Path,
    signature_path: Path,
    root_public_key_path: Path,
    *,
    expected_root_sha256: str,
) -> tuple[W2EvidenceTrustPolicy, str, str]:
    resolved_policy = policy_path.resolve()
    content = _read_bounded(resolved_policy)
    root_hex = root_public_key_path.resolve().read_text(encoding="ascii").strip()
    if re.fullmatch(r"[0-9a-f]{64}", root_hex) is None:
        raise ValueError("root public key file must contain one raw Ed25519 key")
    root_key = bytes.fromhex(root_hex)
    root_sha256 = hashlib.sha256(root_key).hexdigest()
    if re.fullmatch(
        r"[0-9a-f]{64}", expected_root_sha256
    ) is None or not hmac.compare_digest(root_sha256, expected_root_sha256):
        raise ValueError("trust root does not match the expected fingerprint")
    try:
        Ed25519PublicKey.from_public_bytes(root_key).verify(
            bytes.fromhex(_signature(signature_path.resolve())), content
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("trust policy root signature verification failed") from exc
    try:
        raw = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("trust policy must be valid JSON") from exc
    policy = _trust_policy(raw, base=resolved_policy.parent)
    if root_key in policy.public_keys.values():
        raise ValueError("trust root cannot also sign Gate evidence")
    return (
        policy,
        hashlib.sha256(content).hexdigest(),
        root_sha256,
    )


def _artifacts(
    value: object,
    *,
    base: Path,
    candidate: W2CandidateEvidence,
    trust_policy: W2EvidenceTrustPolicy,
) -> tuple[W2EvidenceArtifact, ...]:
    artifacts: list[W2EvidenceArtifact] = []
    for raw in _records(value, "artifacts"):
        common = _closed_dict(
            raw,
            {
                "kind",
                "artifact_id",
                "sequence",
                "content_file",
                "signature_file",
                "signer_id",
                "source_label",
            },
            "artifact import",
        )
        kind = common["kind"]
        if kind not in _ARTIFACT_KINDS:
            raise ValueError("artifact import kind is unsupported")
        if kind != "automated_report" and common["source_label"] is not None:
            raise ValueError("runtime and assisted source_label must be null")
        content = _read_bounded(
            _manifest_path(base, common["content_file"], "artifact content file")
        )
        signature_hex = _signature(
            _manifest_path(base, common["signature_file"], "artifact signature file")
        )
        if kind == "runtime_jsonl":
            artifact = verify_w2_runtime_jsonl_content(
                artifact_id=common["artifact_id"],
                sequence=common["sequence"],
                content=content,
                trust_policy=trust_policy,
                signer_id=common["signer_id"],
                signature_hex=signature_hex,
            )
        elif kind == "assisted_receipt":
            if common["source_label"] is not None:
                raise ValueError("assisted receipt source_label must be null")
            artifact = verify_w2_assisted_receipt_content(
                content,
                trust_policy=trust_policy,
                signer_id=common["signer_id"],
                signature_hex=signature_hex,
            )
            if (
                artifact.artifact_id != common["artifact_id"]
                or artifact.sequence != common["sequence"]
            ):
                raise ValueError("assisted receipt identity differs from its import")
        else:
            artifact = verify_w2_evidence_content(
                artifact_id=common["artifact_id"],
                sequence=common["sequence"],
                candidate_sha=candidate.candidate_sha,
                environment_id=candidate.environment_id,
                session_id=candidate.session_id,
                mode_id=candidate.mode_id,
                evidence_kinds=frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}),
                source_label=common["source_label"],
                content=content,
                trust_policy=trust_policy,
                signer_id=common["signer_id"],
                signature_hex=signature_hex,
            )
        artifacts.append(artifact)
    return tuple(artifacts)


def _verification(value: object) -> W2AutomatedVerificationEvidence:
    data = _closed_dict(
        value, _dataclass_keys(W2AutomatedVerificationEvidence), "verification"
    )
    return W2AutomatedVerificationEvidence(
        **{
            **data,
            "evidence_ids": _tuple(data["evidence_ids"], "verification evidence_ids"),
        }
    )


def _awards(value: object) -> tuple[W2LedgerAward, ...]:
    result = []
    for raw in _records(value, "awards"):
        data = _closed_dict(raw, _dataclass_keys(W2LedgerAward), "award")
        result.append(
            W2LedgerAward(
                **{
                    **data,
                    "item": W2LedgerItem(data["item"]),
                    "route_class": W2RouteClass(data["route_class"]),
                    "evidence_kinds": frozenset(
                        W2EvidenceKind(item)
                        for item in _tuple(
                            data["evidence_kinds"], "award evidence_kinds"
                        )
                    ),
                    "evidence_ids": _tuple(data["evidence_ids"], "award evidence_ids"),
                }
            )
        )
    return tuple(result)


def _invariants(value: object) -> tuple[W2InvariantEvidence, ...]:
    result = []
    for raw in _records(value, "invariants"):
        data = _closed_dict(raw, _dataclass_keys(W2InvariantEvidence), "invariant")
        result.append(
            W2InvariantEvidence(
                invariant=W2Invariant(data["invariant"]),
                passed=data["passed"],
                evidence_ids=_tuple(data["evidence_ids"], "invariant evidence_ids"),
            )
        )
    return tuple(result)


def _showcase(value: object) -> tuple[W2ShowcaseRun, ...]:
    result = []
    for raw in _records(value, "showcase_runs"):
        data = _closed_dict(raw, _dataclass_keys(W2ShowcaseRun), "showcase run")
        result.append(
            W2ShowcaseRun(
                **{
                    **data,
                    "evidence_ids": _tuple(
                        data["evidence_ids"], "showcase evidence_ids"
                    ),
                }
            )
        )
    return tuple(result)


def _journey(value: object) -> tuple[W2JourneyStepEvidence, ...]:
    result = []
    for raw in _records(value, "journey_steps"):
        data = _closed_dict(raw, _dataclass_keys(W2JourneyStepEvidence), "journey step")
        result.append(
            W2JourneyStepEvidence(
                step=W2JourneyStep(data["step"]),
                passed=data["passed"],
                evidence_ids=_tuple(data["evidence_ids"], "journey evidence_ids"),
            )
        )
    return tuple(result)


def _faults(value: object) -> tuple[W2FaultEvidence, ...]:
    result = []
    for raw in _records(value, "faults"):
        data = _closed_dict(raw, _dataclass_keys(W2FaultEvidence), "fault")
        result.append(
            W2FaultEvidence(
                **{
                    **data,
                    "plane": W2CapabilityPlane(data["plane"]),
                    "retriable_evidence_ids": _tuple(
                        data["retriable_evidence_ids"], "retriable evidence_ids"
                    ),
                    "non_retriable_evidence_ids": _tuple(
                        data["non_retriable_evidence_ids"],
                        "non-retriable evidence_ids",
                    ),
                    "zero_effect_evidence_ids": _tuple(
                        data["zero_effect_evidence_ids"], "zero-effect evidence_ids"
                    ),
                }
            )
        )
    return tuple(result)


def _restart(value: object) -> W2RestartEvidence:
    data = _closed_dict(value, _dataclass_keys(W2RestartEvidence), "restart")
    reconciliations = []
    for raw in _records(data["reconciliations"], "restart reconciliations"):
        item = _closed_dict(
            raw, _dataclass_keys(W2TaskReconciliationEvidence), "reconciliation"
        )
        reconciliations.append(
            W2TaskReconciliationEvidence(
                task_id=item["task_id"],
                outcome=W2ReconciliationOutcome(item["outcome"]),
                evidence_ids=_tuple(
                    item["evidence_ids"], "reconciliation evidence_ids"
                ),
            )
        )
    return W2RestartEvidence(
        performed=data["performed"],
        inflight_task_ids=_tuple(data["inflight_task_ids"], "inflight task_ids"),
        reconciliations=tuple(reconciliations),
        evidence_ids=_tuple(data["evidence_ids"], "restart evidence_ids"),
    )


def _verify_root_authorized_scope(
    *,
    repository: Path,
    candidate: W2CandidateEvidence,
    artifacts: tuple[W2EvidenceArtifact, ...],
    showcase_runs: tuple[W2ShowcaseRun, ...],
    trust_policy: W2EvidenceTrustPolicy,
) -> None:
    candidate_binding = (
        candidate.candidate_sha,
        candidate.environment_id,
        candidate.session_id,
        candidate.mode_id,
    )
    if trust_policy.candidate_binding != candidate_binding:
        raise ValueError("manifest candidate differs from root-authorized scope")
    if (
        trust_policy.repository_path != str(repository.resolve())
        or trust_policy.evidence_set_id is None
        or not trust_policy.runtime_slots
        or not trust_policy.artifact_slots
    ):
        raise ValueError("root-authorized evidence scope is required")
    imported_plan = {
        (
            artifact.artifact_id,
            artifact.sequence,
            (kind := next(iter(artifact.evidence_kinds))),
            artifact.signer_id,
            (
                artifact.source_label
                if kind is W2EvidenceKind.AUTOMATED_CONFORMANCE
                else None
            ),
        )
        for artifact in artifacts
    }
    authorized_plan = {
        (
            slot.artifact_id,
            slot.artifact_sequence,
            slot.evidence_kind,
            slot.signer_id,
            slot.source_label,
        )
        for slot in trust_policy.artifact_slots
    }
    if len(artifacts) != len(imported_plan) or imported_plan != authorized_plan:
        raise ValueError("imported artifacts differ from the root-authorized plan")
    artifact_by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    if any(
        artifact_by_id[slot.artifact_id].proven_subjects
        != frozenset(slot.expected_subjects)
        for slot in trust_policy.artifact_slots
    ):
        raise ValueError("artifact subjects differ from the root-authorized plan")
    runtime = [
        artifact
        for artifact in artifacts
        if W2EvidenceKind.REAL_RUNTIME in artifact.evidence_kinds
    ]
    imported_slots = {
        (
            artifact.artifact_id,
            artifact.sequence,
            artifact.producer_id,
            artifact.process_epoch,
            artifact.predecessor_artifact_id,
        )
        for artifact in runtime
        if artifact.runtime_format_version == 2
        and artifact.evidence_set_id == trust_policy.evidence_set_id
    }
    authorized_slots = {
        (
            slot.artifact_id,
            slot.artifact_sequence,
            slot.producer_id,
            slot.process_epoch,
            slot.predecessor_artifact_id,
        )
        for slot in trust_policy.runtime_slots
    }
    if len(runtime) != len(imported_slots) or imported_slots != authorized_slots:
        raise ValueError(
            "imported runtime artifacts differ from the root-authorized slots"
        )
    runtime_ids = {artifact.artifact_id for artifact in runtime}
    runs = {run.run_number: run for run in showcase_runs}
    for run_number in (1, 2, 3):
        run = runs.get(run_number)
        if run is None:
            raise ValueError("root-authorized showcase mapping is incomplete")
        authorized_ids = {
            slot.artifact_id
            for slot in trust_policy.runtime_slots
            if slot.showcase_run == run_number
        }
        imported_ids = set(run.evidence_ids) & runtime_ids
        if imported_ids != authorized_ids:
            raise ValueError(
                f"showcase {run_number} differs from root-authorized runtime slots"
            )


def evaluate_w2_gate_manifest(
    path: Path, *, trust_policy: W2EvidenceTrustPolicy
) -> W2GateResult:
    """Import, cryptographically verify, Git-bind, and evaluate one manifest."""

    manifest_path = path.resolve()
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "schema",
        "repository_path",
        "candidate",
        "artifacts",
        "verification",
        "awards",
        "invariants",
        "showcase_runs",
        "journey_steps",
        "faults",
        "restart",
    }
    data = _closed_dict(raw, expected, "gate manifest")
    if data["schema"] != _MANIFEST_SCHEMA:
        raise ValueError("gate manifest schema is unsupported")
    base = manifest_path.parent
    candidate = _candidate(data["candidate"])
    repository = Path(data["repository_path"])
    if not repository.is_absolute():
        repository = (base / repository).resolve()
    verify_w2_candidate_checkout(
        repository_path=repository,
        candidate_sha=candidate.candidate_sha,
        bind_loaded_source=True,
    )
    artifacts = _artifacts(
        data["artifacts"],
        base=base,
        candidate=candidate,
        trust_policy=trust_policy,
    )
    showcase_runs = _showcase(data["showcase_runs"])
    faults = _faults(data["faults"])
    _verify_root_authorized_scope(
        repository=repository,
        candidate=candidate,
        artifacts=artifacts,
        showcase_runs=showcase_runs,
        trust_policy=trust_policy,
    )
    verify_w2_planned_product_faults(
        artifacts=artifacts,
        faults=faults,
        trust_policy=trust_policy,
    )
    return evaluate_w2_demo_gate(
        candidate=candidate,
        artifacts=artifacts,
        verification=_verification(data["verification"]),
        awards=_awards(data["awards"]),
        invariants=_invariants(data["invariants"]),
        showcase_runs=showcase_runs,
        journey_steps=_journey(data["journey_steps"]),
        faults=faults,
        restart=_restart(data["restart"]),
    )


def _exclusive_text(path: Path, value: str, *, private: bool) -> None:
    if not path.is_absolute() or not path.parent.is_dir():
        raise ValueError("output must be a new absolute file in an existing directory")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600 if private else 0o644,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
            stream.write(value)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _keygen(private_path: Path, public_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    _exclusive_text(private_path.resolve(), private.hex(), private=True)
    try:
        _exclusive_text(public_path.resolve(), public.hex(), private=False)
    except BaseException:
        private_path.resolve().unlink(missing_ok=True)
        raise


def _sign(private_path: Path, input_path: Path, signature_path: Path) -> None:
    private_hex = private_path.read_text(encoding="ascii").strip()
    if re.fullmatch(r"[0-9a-f]{64}", private_hex) is None:
        raise ValueError("private key file must contain one raw Ed25519 key")
    content = _read_bounded(input_path.resolve())
    signature = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex)).sign(
        content
    )
    _exclusive_text(signature_path.resolve(), signature.hex(), private=False)


def _sign_artifact(
    private_path: Path,
    input_path: Path,
    signature_path: Path,
    *,
    kind: str,
    artifact_id: str,
    sequence: int,
    source_label: str | None,
) -> None:
    private_hex = private_path.read_text(encoding="ascii").strip()
    if re.fullmatch(r"[0-9a-f]{64}", private_hex) is None:
        raise ValueError("private key file must contain one raw Ed25519 key")
    content = _read_bounded(input_path.resolve())
    payload = w2_artifact_signature_payload(
        kind=kind,
        artifact_id=artifact_id,
        sequence=sequence,
        source_label=source_label,
        content=content,
    )
    signature = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex)).sign(
        payload
    )
    _exclusive_text(signature_path.resolve(), signature.hex(), private=False)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="live-voice-w2-gate")
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen")
    keygen.add_argument("--private-key", required=True, type=Path)
    keygen.add_argument("--public-key", required=True, type=Path)
    sign = commands.add_parser("sign")
    sign.add_argument("--private-key", required=True, type=Path)
    sign.add_argument("--input", required=True, type=Path)
    sign.add_argument("--signature", required=True, type=Path)
    sign_artifact = commands.add_parser("sign-artifact")
    sign_artifact.add_argument("--private-key", required=True, type=Path)
    sign_artifact.add_argument("--input", required=True, type=Path)
    sign_artifact.add_argument("--signature", required=True, type=Path)
    sign_artifact.add_argument(
        "--kind", required=True, choices=sorted(_OFFLINE_SIGNABLE_ARTIFACT_KINDS)
    )
    sign_artifact.add_argument("--artifact-id", required=True)
    sign_artifact.add_argument("--sequence", required=True, type=int)
    sign_artifact.add_argument("--source-label")
    validate_policy = commands.add_parser("validate-policy")
    validate_policy.add_argument("--trust-policy", required=True, type=Path)
    validate_policy.add_argument("--trust-policy-signature", required=True, type=Path)
    validate_policy.add_argument("--root-public-key", required=True, type=Path)
    validate_policy.add_argument("--expected-root-sha256", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--manifest", required=True, type=Path)
    evaluate.add_argument("--trust-policy", required=True, type=Path)
    evaluate.add_argument("--trust-policy-signature", required=True, type=Path)
    evaluate.add_argument("--root-public-key", required=True, type=Path)
    evaluate.add_argument("--expected-root-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "keygen":
            _keygen(args.private_key, args.public_key)
            return 0
        if args.command == "sign":
            _sign(args.private_key, args.input, args.signature)
            return 0
        if args.command == "sign-artifact":
            _sign_artifact(
                args.private_key,
                args.input,
                args.signature,
                kind=args.kind,
                artifact_id=args.artifact_id,
                sequence=args.sequence,
                source_label=args.source_label,
            )
            return 0
        trust_policy, policy_sha256, root_sha256 = _load_trust_policy(
            args.trust_policy,
            args.trust_policy_signature,
            args.root_public_key,
            expected_root_sha256=args.expected_root_sha256,
        )
        if args.command == "validate-policy":
            print(
                json.dumps(
                    {
                        "status": "VALID",
                        "policy_id": trust_policy.policy_id,
                        "policy_sha256": policy_sha256,
                        "trust_root_sha256": root_sha256,
                        "repository_path": trust_policy.repository_path,
                        "candidate_binding": list(trust_policy.candidate_binding or ()),
                        "evidence_set_id": trust_policy.evidence_set_id,
                        "leaf_key_sha256": {
                            signer_id: hashlib.sha256(key).hexdigest()
                            for signer_id, key in trust_policy.public_keys.items()
                        },
                        "artifact_slots": [
                            {
                                "artifact_id": slot.artifact_id,
                                "artifact_sequence": slot.artifact_sequence,
                                "evidence_kind": slot.evidence_kind.value,
                                "signer_id": slot.signer_id,
                                "source_label": slot.source_label,
                                "expected_subjects": list(slot.expected_subjects),
                            }
                            for slot in trust_policy.artifact_slots
                        ],
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0
        result = evaluate_w2_gate_manifest(args.manifest, trust_policy=trust_policy)
        print(
            json.dumps(
                {
                    "status": result.status.value,
                    "total_score": result.total_score,
                    "section_scores": {
                        section.value: score
                        for section, score in result.section_scores.items()
                    },
                    "failures": list(result.failures),
                    "trust_policy_sha256": policy_sha256,
                    "trust_root_sha256": root_sha256,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0 if result.status.value == "PASS" else 1
    except Exception as exc:  # noqa: BLE001 - stable CLI boundary
        print(f"live-voice-w2-gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["evaluate_w2_gate_manifest", "main"]
