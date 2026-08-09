"""Derive an unsigned W2 trust-policy scaffold from signed rehearsal JSONL.

This machine-private helper deliberately has no key-generation or signing
surface.  It verifies a root-authorized rehearsal, derives the exact public
runtime subjects through the candidate's Gate implementation, and writes a
new unsigned policy scaffold plus sanitized digests using exclusive creates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from jiuwenswarm.server.live_voice.w2_demo_gate import (
    MAX_W2_ARTIFACT_BYTES,
    W2EvidenceArtifactSlot,
    W2EvidenceKind,
    W2EvidenceTrustPolicy,
    W2RuntimeArtifactSlot,
    verify_w2_runtime_jsonl_content,
)
from jiuwenswarm.server.live_voice.w2_evidence_exporter import (
    verify_w2_candidate_checkout,
)
from jiuwenswarm.server.live_voice.w2_gate_cli import (
    _load_trust_policy,
    _trust_policy,
)


_IMPORT_SCHEMA = "machine-private.w2-rehearsal-import.v1"
_PLAN_SCHEMA = "machine-private.w2-next-attempt-plan.v1"
_SUBJECT_MAP_SCHEMA = "machine-private.w2-runtime-subject-map.v1"
_DIGEST_SCHEMA = "machine-private.w2-scaffold-digest.v1"
_POLICY_SCHEMA = "live-voice.w2-trust-policy.v2"
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE = re.compile(r"^[0-9a-f]{128}$")
_ALLOWED_RUNTIME_SUBJECT_PREFIXES = ("runtime:", "fact:", "candidate:")


class ScaffoldError(ValueError):
    """The rehearsal or next-attempt plan is unsafe or contradictory."""


def _closed_dict(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ScaffoldError(f"{label} fields are not closed")
    return value


def _records(
    value: object, label: str, *, allow_empty: bool = False
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or len(value) > 4_096
        or any(not isinstance(item, dict) for item in value)
    ):
        raise ScaffoldError(f"{label} must be a bounded JSON record list")
    return value


def _label(value: object, field: str) -> str:
    if not isinstance(value, str) or _LABEL.fullmatch(value) is None:
        raise ScaffoldError(f"{field} is not a bounded opaque label")
    return value


def _absolute_existing_file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ScaffoldError(f"{label} is required")
    path = Path(value)
    if not path.is_absolute():
        raise ScaffoldError(f"{label} must be absolute")
    resolved = path.resolve()
    if not resolved.is_file():
        raise ScaffoldError(f"{label} must identify an existing regular file")
    return resolved


def _absolute_output(value: object, label: str) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ScaffoldError(f"{label} is required")
    path = Path(value)
    if not path.is_absolute():
        raise ScaffoldError(f"{label} must be absolute")
    resolved = path.resolve()
    if not resolved.parent.is_dir():
        raise ScaffoldError(f"{label} parent must already exist")
    return resolved


def _read_bounded(path: Path, label: str) -> bytes:
    size = path.stat().st_size
    if not 0 < size <= MAX_W2_ARTIFACT_BYTES:
        raise ScaffoldError(f"{label} is empty or exceeds the artifact limit")
    return path.read_bytes()


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    content = _read_bounded(path, label)
    try:
        value = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError) as exc:
        raise ScaffoldError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ScaffoldError(f"{label} must be a JSON object")
    return value, content


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _digest_subjects(subjects: Sequence[str]) -> str:
    return hashlib.sha256(_canonical(list(subjects))).hexdigest()


def _resolve_under(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ScaffoldError(f"{label} is required")
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ScaffoldError(f"{label} must stay within the rehearsal root")
    return resolved


def _signature(path: Path) -> str:
    try:
        value = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise ScaffoldError("runtime signature is unreadable") from exc
    if _SIGNATURE.fullmatch(value) is None:
        raise ScaffoldError("runtime signature is not one Ed25519 signature")
    return value


def _parse_imports(value: object) -> tuple[Path, list[dict[str, Any]]]:
    data = _closed_dict(
        value,
        {"schema", "rehearsal_root", "runtime_imports"},
        "rehearsal import descriptor",
    )
    if data["schema"] != _IMPORT_SCHEMA:
        raise ScaffoldError("rehearsal import schema is unsupported")
    if not isinstance(data["rehearsal_root"], str):
        raise ScaffoldError("rehearsal_root must be an absolute directory")
    root = Path(data["rehearsal_root"])
    if not root.is_absolute() or not root.resolve().is_dir():
        raise ScaffoldError("rehearsal_root must be an existing absolute directory")
    root = root.resolve()
    result: list[dict[str, Any]] = []
    logical_slots: set[str] = set()
    artifact_ids: set[str] = set()
    for raw in _records(data["runtime_imports"], "runtime imports"):
        item = _closed_dict(
            raw,
            {
                "logical_slot",
                "artifact_id",
                "content_file",
                "signature_file",
                "expected_subjects_sha256",
            },
            "runtime import",
        )
        logical_slot = _label(item["logical_slot"], "runtime logical_slot")
        artifact_id = _label(item["artifact_id"], "runtime artifact_id")
        if logical_slot in logical_slots or artifact_id in artifact_ids:
            raise ScaffoldError("runtime import identity is duplicated")
        logical_slots.add(logical_slot)
        artifact_ids.add(artifact_id)
        expected_digest = item["expected_subjects_sha256"]
        if expected_digest is not None and (
            not isinstance(expected_digest, str)
            or _SHA256.fullmatch(expected_digest) is None
        ):
            raise ScaffoldError("expected_subjects_sha256 is invalid")
        result.append(
            {
                "logical_slot": logical_slot,
                "artifact_id": artifact_id,
                "content_path": _resolve_under(
                    root, item["content_file"], "runtime content_file"
                ),
                "signature_path": _resolve_under(
                    root, item["signature_file"], "runtime signature_file"
                ),
                "expected_subjects_sha256": expected_digest,
            }
        )
    return root, result


def _parse_plan(value: object) -> dict[str, Any]:
    data = _closed_dict(
        value,
        {
            "schema",
            "policy_id",
            "repository_path",
            "candidate",
            "evidence_set_id",
            "runtime_slots",
            "non_runtime_artifact_slots",
            "signers",
        },
        "next-attempt plan",
    )
    if data["schema"] != _PLAN_SCHEMA:
        raise ScaffoldError("next-attempt plan schema is unsupported")
    _label(data["policy_id"], "policy_id")
    _label(data["evidence_set_id"], "evidence_set_id")
    if not isinstance(data["repository_path"], str):
        raise ScaffoldError("repository_path must be absolute")
    repository = Path(data["repository_path"])
    if not repository.is_absolute() or not repository.resolve().is_dir():
        raise ScaffoldError("repository_path must be an existing absolute directory")
    candidate = _closed_dict(
        data["candidate"],
        {"candidate_sha", "environment_id", "session_id", "mode_id"},
        "next candidate",
    )
    if (
        not isinstance(candidate["candidate_sha"], str)
        or re.fullmatch(r"[0-9a-f]{40}", candidate["candidate_sha"]) is None
    ):
        raise ScaffoldError("next candidate SHA is invalid")
    for field in ("environment_id", "session_id", "mode_id"):
        _label(candidate[field], f"next candidate {field}")
    runtime_slots = _records(data["runtime_slots"], "next runtime slots")
    for raw in runtime_slots:
        _closed_dict(
            raw,
            {
                "logical_slot",
                "artifact_id",
                "artifact_sequence",
                "producer_id",
                "process_epoch",
                "predecessor_artifact_id",
                "showcase_run",
                "signer_id",
            },
            "next runtime slot",
        )
    non_runtime = _records(
        data["non_runtime_artifact_slots"],
        "next non-runtime artifact slots",
        allow_empty=True,
    )
    for raw in non_runtime:
        _closed_dict(
            raw,
            {
                "artifact_id",
                "artifact_sequence",
                "evidence_kind",
                "signer_id",
                "source_label",
                "expected_subjects",
            },
            "next non-runtime artifact slot",
        )
    signers = _records(data["signers"], "next signers")
    for raw in signers:
        _closed_dict(
            raw,
            {"signer_id", "principal_id", "public_key_hex", "role", "producer_id"},
            "next signer",
        )
    return {
        **data,
        "repository_path": str(repository.resolve()),
        "candidate": candidate,
        "runtime_slots": runtime_slots,
        "non_runtime_artifact_slots": non_runtime,
        "signers": signers,
    }


def _derive_templates(
    *,
    imports: Sequence[dict[str, Any]],
    trust_policy: W2EvidenceTrustPolicy,
) -> list[dict[str, Any]]:
    runtime_by_id = {slot.artifact_id: slot for slot in trust_policy.runtime_slots}
    artifact_by_id = {
        slot.artifact_id: slot
        for slot in trust_policy.artifact_slots
        if slot.evidence_kind is W2EvidenceKind.REAL_RUNTIME
    }
    import_ids = {item["artifact_id"] for item in imports}
    if import_ids != set(runtime_by_id) or import_ids != set(artifact_by_id):
        raise ScaffoldError(
            "rehearsal imports must exactly cover every root-authorized runtime slot"
        )
    templates: list[dict[str, Any]] = []
    assert trust_policy.candidate_binding is not None
    for item in imports:
        artifact_id = item["artifact_id"]
        runtime_slot = runtime_by_id[artifact_id]
        artifact_slot = artifact_by_id[artifact_id]
        content = _read_bounded(item["content_path"], "runtime JSONL")
        artifact = verify_w2_runtime_jsonl_content(
            artifact_id=artifact_id,
            sequence=runtime_slot.artifact_sequence,
            content=content,
            trust_policy=trust_policy,
            signer_id=artifact_slot.signer_id,
            signature_hex=_signature(item["signature_path"]),
        )
        actual_binding = (
            artifact.candidate_sha,
            artifact.environment_id,
            artifact.session_id,
            artifact.mode_id,
        )
        if actual_binding != trust_policy.candidate_binding:
            raise ScaffoldError("runtime candidate differs from rehearsal policy")
        if (
            artifact.runtime_format_version != 2
            or artifact.evidence_set_id != trust_policy.evidence_set_id
            or artifact.producer_id != runtime_slot.producer_id
            or artifact.process_epoch != runtime_slot.process_epoch
            or artifact.predecessor_artifact_id != runtime_slot.predecessor_artifact_id
            or artifact.signer_id != artifact_slot.signer_id
        ):
            raise ScaffoldError("runtime identity differs from its authorized slot")
        subjects = sorted(artifact.proven_subjects)
        if not subjects or any(
            not subject.startswith(_ALLOWED_RUNTIME_SUBJECT_PREFIXES)
            for subject in subjects
        ):
            raise ScaffoldError("runtime produced an unsafe scaffold subject namespace")
        subject_digest = _digest_subjects(subjects)
        expected_digest = item["expected_subjects_sha256"]
        if expected_digest is not None and expected_digest != subject_digest:
            raise ScaffoldError("runtime subject set differs from its expected digest")
        rehearsal_expected = sorted(artifact_slot.expected_subjects)
        templates.append(
            {
                "logical_slot": item["logical_slot"],
                "rehearsal_artifact_id": artifact_id,
                "rehearsal_content_sha256": artifact.content_sha256,
                "producer_id": artifact.producer_id,
                "subjects": subjects,
                "subjects_sha256": subject_digest,
                "rehearsal_expected_subjects": rehearsal_expected,
                "rehearsal_expected_subjects_match": rehearsal_expected == subjects,
            }
        )
    return templates


def _build_policy(
    *,
    plan: Mapping[str, Any],
    templates: Sequence[dict[str, Any]],
    rehearsal_root_public_key: bytes,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    template_by_logical = {item["logical_slot"]: item for item in templates}
    rehearsal_artifact_ids = {item["rehearsal_artifact_id"] for item in templates}
    planned_logical: set[str] = set()
    runtime_slots: list[W2RuntimeArtifactSlot] = []
    artifact_slots: list[W2EvidenceArtifactSlot] = []
    subject_map: list[dict[str, Any]] = []
    runtime_signers: dict[str, str] = {}
    for raw in plan["runtime_slots"]:
        logical_slot = _label(raw["logical_slot"], "next runtime logical_slot")
        if logical_slot in planned_logical or logical_slot not in template_by_logical:
            raise ScaffoldError(
                "next runtime logical-slot mapping is incomplete or duplicated"
            )
        planned_logical.add(logical_slot)
        template = template_by_logical[logical_slot]
        if raw["producer_id"] != template["producer_id"]:
            raise ScaffoldError("next runtime producer differs from rehearsal template")
        if raw["artifact_id"] in rehearsal_artifact_ids:
            raise ScaffoldError("next attempt cannot reuse a rehearsal artifact_id")
        slot = W2RuntimeArtifactSlot(
            artifact_id=raw["artifact_id"],
            artifact_sequence=raw["artifact_sequence"],
            producer_id=raw["producer_id"],
            process_epoch=raw["process_epoch"],
            predecessor_artifact_id=raw["predecessor_artifact_id"],
            showcase_run=raw["showcase_run"],
        )
        signer_id = _label(raw["signer_id"], "next runtime signer_id")
        previous_signer = runtime_signers.setdefault(slot.producer_id, signer_id)
        if previous_signer != signer_id:
            raise ScaffoldError("one runtime producer cannot switch signer identity")
        runtime_slots.append(slot)
        artifact_slots.append(
            W2EvidenceArtifactSlot(
                artifact_id=slot.artifact_id,
                artifact_sequence=slot.artifact_sequence,
                evidence_kind=W2EvidenceKind.REAL_RUNTIME,
                signer_id=signer_id,
                source_label=None,
                expected_subjects=tuple(template["subjects"]),
            )
        )
        subject_map.append(
            {
                **template,
                "next_artifact_id": slot.artifact_id,
                "next_artifact_sequence": slot.artifact_sequence,
                "next_process_epoch": slot.process_epoch,
            }
        )
    if planned_logical != set(template_by_logical):
        raise ScaffoldError(
            "next runtime plan does not consume every rehearsal template"
        )
    for raw in plan["non_runtime_artifact_slots"]:
        kind = W2EvidenceKind(raw["evidence_kind"])
        if kind is W2EvidenceKind.REAL_RUNTIME:
            raise ScaffoldError(
                "real runtime slots must use a rehearsal logical mapping"
            )
        artifact_slots.append(
            W2EvidenceArtifactSlot(
                artifact_id=raw["artifact_id"],
                artifact_sequence=raw["artifact_sequence"],
                evidence_kind=kind,
                signer_id=raw["signer_id"],
                source_label=raw["source_label"],
                expected_subjects=tuple(raw["expected_subjects"]),
            )
        )
    public_keys: dict[str, bytes] = {}
    roles: dict[str, frozenset[W2EvidenceKind]] = {}
    principals: dict[str, str] = {}
    producers: dict[str, str | None] = {}
    signer_json: list[dict[str, Any]] = []
    for raw in plan["signers"]:
        signer_id = _label(raw["signer_id"], "next signer_id")
        if signer_id in public_keys:
            raise ScaffoldError("next signer_id is duplicated")
        key_hex = raw["public_key_hex"]
        if (
            not isinstance(key_hex, str)
            or re.fullmatch(r"[0-9a-f]{64}", key_hex) is None
        ):
            raise ScaffoldError("next signer public key is invalid")
        public_keys[signer_id] = bytes.fromhex(key_hex)
        if public_keys[signer_id] == rehearsal_root_public_key:
            raise ScaffoldError("rehearsal root cannot be reused as a leaf signer")
        role = W2EvidenceKind(raw["role"])
        roles[signer_id] = frozenset({role})
        principals[signer_id] = _label(raw["principal_id"], "next principal_id")
        producer = raw["producer_id"]
        if producer is not None:
            producer = _label(producer, "next producer_id")
        producers[signer_id] = producer
        signer_json.append(dict(raw))
    for slot in artifact_slots:
        if slot.evidence_kind is not W2EvidenceKind.REAL_RUNTIME:
            continue
        runtime_slot = next(
            item for item in runtime_slots if item.artifact_id == slot.artifact_id
        )
        if producers.get(slot.signer_id) != runtime_slot.producer_id:
            raise ScaffoldError("next runtime signer does not own the mapped producer")
    candidate = plan["candidate"]
    policy_object = W2EvidenceTrustPolicy(
        public_keys=public_keys,
        signer_roles=roles,
        principal_ids=principals,
        producer_ids=producers,
        candidate_binding=(
            candidate["candidate_sha"],
            candidate["environment_id"],
            candidate["session_id"],
            candidate["mode_id"],
        ),
        evidence_set_id=plan["evidence_set_id"],
        runtime_slots=tuple(runtime_slots),
        artifact_slots=tuple(artifact_slots),
        policy_id=plan["policy_id"],
        repository_path=plan["repository_path"],
    )
    policy_json = {
        "schema": _POLICY_SCHEMA,
        "policy_id": policy_object.policy_id,
        "repository_path": policy_object.repository_path,
        "candidate": dict(candidate),
        "evidence_set_id": policy_object.evidence_set_id,
        "runtime_slots": [
            {
                "artifact_id": slot.artifact_id,
                "artifact_sequence": slot.artifact_sequence,
                "producer_id": slot.producer_id,
                "process_epoch": slot.process_epoch,
                "predecessor_artifact_id": slot.predecessor_artifact_id,
                "showcase_run": slot.showcase_run,
            }
            for slot in sorted(runtime_slots, key=lambda value: value.artifact_sequence)
        ],
        "artifact_slots": [
            {
                "artifact_id": slot.artifact_id,
                "artifact_sequence": slot.artifact_sequence,
                "evidence_kind": slot.evidence_kind.value,
                "signer_id": slot.signer_id,
                "source_label": slot.source_label,
                "expected_subjects": list(slot.expected_subjects),
            }
            for slot in sorted(
                artifact_slots, key=lambda value: value.artifact_sequence
            )
        ],
        "signers": signer_json,
    }
    round_trip = _trust_policy(policy_json, base=Path(plan["repository_path"]))
    if (
        round_trip.candidate_binding != policy_object.candidate_binding
        or round_trip.evidence_set_id != policy_object.evidence_set_id
        or round_trip.runtime_slots != policy_object.runtime_slots
        or round_trip.artifact_slots != policy_object.artifact_slots
        or dict(round_trip.public_keys) != dict(policy_object.public_keys)
        or dict(round_trip.signer_roles) != dict(policy_object.signer_roles)
        or dict(round_trip.principal_ids or {})
        != dict(policy_object.principal_ids or {})
        or dict(round_trip.producer_ids or {}) != dict(policy_object.producer_ids or {})
    ):
        raise ScaffoldError("unsigned policy failed a lossless Gate parser round-trip")
    return policy_json, subject_map


def _write_exclusive(outputs: Mapping[Path, bytes]) -> None:
    if len(outputs) != len(set(outputs)):
        raise ScaffoldError("output paths must be distinct")
    descriptors: dict[Path, int] = {}
    created: list[Path] = []
    try:
        for path in outputs:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            descriptors[path] = descriptor
            created.append(path)
        for path, content in outputs.items():
            descriptor = descriptors.pop(path)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for descriptor in descriptors.values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def derive_scaffold(
    *,
    rehearsal_import_path: Path,
    rehearsal_trust_policy_path: Path,
    rehearsal_trust_policy_signature_path: Path,
    root_public_key_path: Path,
    expected_root_sha256: str,
    next_attempt_plan_path: Path,
    unsigned_policy_output: Path,
    subject_map_output: Path,
    digest_output: Path,
) -> dict[str, Any]:
    """Verify one rehearsal and exclusively write an unsigned next-attempt plan."""

    if _SHA256.fullmatch(expected_root_sha256) is None:
        raise ScaffoldError("expected root SHA-256 is invalid")
    import_json, import_content = _read_json(
        _absolute_existing_file(str(rehearsal_import_path), "rehearsal import"),
        "rehearsal import",
    )
    plan_json, plan_content = _read_json(
        _absolute_existing_file(str(next_attempt_plan_path), "next-attempt plan"),
        "next-attempt plan",
    )
    rehearsal_root, imports = _parse_imports(import_json)
    plan = _parse_plan(plan_json)
    policy_path = _absolute_existing_file(
        str(rehearsal_trust_policy_path), "rehearsal trust policy"
    )
    trust_policy, rehearsal_policy_sha256, verified_root_sha256 = _load_trust_policy(
        policy_path,
        _absolute_existing_file(
            str(rehearsal_trust_policy_signature_path),
            "rehearsal trust-policy signature",
        ),
        _absolute_existing_file(str(root_public_key_path), "root public key"),
        expected_root_sha256=expected_root_sha256,
    )
    if trust_policy.repository_path is None or trust_policy.candidate_binding is None:
        raise ScaffoldError("rehearsal policy lacks a closed candidate scope")
    if (
        Path(trust_policy.repository_path).resolve()
        != Path(plan["repository_path"]).resolve()
    ):
        raise ScaffoldError("next plan repository differs from rehearsal candidate")
    if plan["candidate"]["candidate_sha"] != trust_policy.candidate_binding[0]:
        raise ScaffoldError("next plan candidate SHA differs from rehearsal candidate")
    if plan["evidence_set_id"] == trust_policy.evidence_set_id:
        raise ScaffoldError("next attempt must use a new evidence_set_id")
    if plan["policy_id"] == trust_policy.policy_id:
        raise ScaffoldError("next attempt must use a new policy_id")
    verify_w2_candidate_checkout(
        repository_path=plan["repository_path"],
        candidate_sha=plan["candidate"]["candidate_sha"],
        bind_loaded_source=True,
    )
    templates = _derive_templates(imports=imports, trust_policy=trust_policy)
    root_hex = root_public_key_path.resolve().read_text(encoding="ascii").strip()
    if re.fullmatch(r"[0-9a-f]{64}", root_hex) is None:
        raise ScaffoldError("root public key is invalid")
    policy_json, subject_map = _build_policy(
        plan=plan,
        templates=templates,
        rehearsal_root_public_key=bytes.fromhex(root_hex),
    )
    policy_content = _canonical(policy_json)
    subject_json = {
        "schema": _SUBJECT_MAP_SCHEMA,
        "candidate_sha": plan["candidate"]["candidate_sha"],
        "repository_path": plan["repository_path"],
        "rehearsal_evidence_set_id": trust_policy.evidence_set_id,
        "next_evidence_set_id": plan["evidence_set_id"],
        "rehearsal_policy_not_gate_eligible": any(
            not item["rehearsal_expected_subjects_match"] for item in subject_map
        ),
        "templates": sorted(
            subject_map, key=lambda value: value["next_artifact_sequence"]
        ),
    }
    subject_content = _canonical(subject_json)
    digest_json = {
        "schema": _DIGEST_SCHEMA,
        "status": "VALID_UNSIGNED",
        "candidate_sha": plan["candidate"]["candidate_sha"],
        "rehearsal_policy_sha256": rehearsal_policy_sha256,
        "trust_root_sha256": verified_root_sha256,
        "rehearsal_import_sha256": hashlib.sha256(import_content).hexdigest(),
        "next_attempt_plan_sha256": hashlib.sha256(plan_content).hexdigest(),
        "unsigned_policy_sha256": hashlib.sha256(policy_content).hexdigest(),
        "subject_map_sha256": hashlib.sha256(subject_content).hexdigest(),
        "runtime_slot_count": len(policy_json["runtime_slots"]),
        "artifact_slot_count": len(policy_json["artifact_slots"]),
        "rehearsal_policy_not_gate_eligible": subject_json[
            "rehearsal_policy_not_gate_eligible"
        ],
    }
    digest_content = _canonical(digest_json)
    unsigned_path = _absolute_output(unsigned_policy_output, "unsigned policy output")
    subject_path = _absolute_output(subject_map_output, "subject map output")
    digest_path = _absolute_output(digest_output, "digest output")
    if len({unsigned_path, subject_path, digest_path}) != 3:
        raise ScaffoldError("output paths must be distinct")
    repository_root = Path(plan["repository_path"]).resolve()
    if any(
        path.is_relative_to(repository_root) or path.is_relative_to(rehearsal_root)
        for path in (unsigned_path, subject_path, digest_path)
    ):
        raise ScaffoldError(
            "next-attempt outputs must stay outside the candidate and rehearsal roots"
        )
    output_paths = {
        unsigned_path: policy_content,
        subject_path: subject_content,
        digest_path: digest_content,
    }
    _write_exclusive(output_paths)
    return digest_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="derive-w2-policy-scaffold")
    parser.add_argument("--rehearsal-import", required=True, type=Path)
    parser.add_argument("--rehearsal-trust-policy", required=True, type=Path)
    parser.add_argument("--rehearsal-trust-policy-signature", required=True, type=Path)
    parser.add_argument("--root-public-key", required=True, type=Path)
    parser.add_argument("--expected-root-sha256", required=True)
    parser.add_argument("--next-attempt-plan", required=True, type=Path)
    parser.add_argument("--unsigned-policy-output", required=True, type=Path)
    parser.add_argument("--subject-map-output", required=True, type=Path)
    parser.add_argument("--digest-output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = derive_scaffold(
            rehearsal_import_path=args.rehearsal_import,
            rehearsal_trust_policy_path=args.rehearsal_trust_policy,
            rehearsal_trust_policy_signature_path=args.rehearsal_trust_policy_signature,
            root_public_key_path=args.root_public_key,
            expected_root_sha256=args.expected_root_sha256,
            next_attempt_plan_path=args.next_attempt_plan,
            unsigned_policy_output=args.unsigned_policy_output,
            subject_map_output=args.subject_map_output,
            digest_output=args.digest_output,
        )
        print(
            json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - stable machine-private boundary
        print(f"derive-w2-policy-scaffold: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
