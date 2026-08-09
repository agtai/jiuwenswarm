# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from jiuwenswarm.server.live_voice.w2_demo_gate import (
    W2EvidenceKind,
    W2GateContractViolation,
    _required_absolute_path,
    w2_artifact_signature_payload,
)
from jiuwenswarm.server.live_voice.w2_gate_cli import (
    _load_trust_policy,
    _verify_root_authorized_scope,
    main,
)


def test_cli_generates_new_keys_and_signs_exact_artifact(tmp_path: Path) -> None:
    private = (tmp_path / "runtime.private").resolve()
    public = (tmp_path / "runtime.public").resolve()
    content = (tmp_path / "runtime.jsonl").resolve()
    signature = (tmp_path / "runtime.signature").resolve()
    content.write_bytes(b'{"closed":"artifact"}\n')

    assert (
        main(
            [
                "keygen",
                "--private-key",
                str(private),
                "--public-key",
                str(public),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "sign",
                "--private-key",
                str(private),
                "--input",
                str(content),
                "--signature",
                str(signature),
            ]
        )
        == 0
    )

    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(public.read_text().strip())
    ).verify(bytes.fromhex(signature.read_text().strip()), content.read_bytes())
    original_private = private.read_text()
    assert (
        main(
            [
                "keygen",
                "--private-key",
                str(private),
                "--public-key",
                str(public),
            ]
        )
        == 2
    )
    assert private.read_text() == original_private


def test_cli_rejects_non_closed_manifest_before_any_evaluation(
    tmp_path: Path,
) -> None:
    manifest = (tmp_path / "manifest.json").resolve()
    manifest.write_text(
        json.dumps({"schema": "live-voice.w2-gate-manifest.v1"}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as raised:
        main(["evaluate", "--manifest", str(manifest)])
    assert raised.value.code == 2


def test_cli_sign_artifact_binds_import_identity_and_sequence(tmp_path: Path) -> None:
    private = (tmp_path / "runtime.private").resolve()
    public = (tmp_path / "runtime.public").resolve()
    content = (tmp_path / "runtime.jsonl").resolve()
    signature = (tmp_path / "runtime.signature").resolve()
    content.write_bytes(b'{"closed":"artifact"}\n')
    assert (
        main(["keygen", "--private-key", str(private), "--public-key", str(public)])
        == 0
    )
    assert (
        main(
            [
                "sign-artifact",
                "--private-key",
                str(private),
                "--input",
                str(content),
                "--signature",
                str(signature),
                "--kind",
                "assisted_receipt",
                "--artifact-id",
                "runtime-gateway-1",
                "--sequence",
                "7",
            ]
        )
        == 0
    )
    payload = w2_artifact_signature_payload(
        kind="assisted_receipt",
        artifact_id="runtime-gateway-1",
        sequence=7,
        source_label=None,
        content=content.read_bytes(),
    )
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(public.read_text().strip())
    ).verify(bytes.fromhex(signature.read_text().strip()), payload)
    with pytest.raises(Exception):
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(public.read_text().strip())
        ).verify(
            bytes.fromhex(signature.read_text().strip()),
            w2_artifact_signature_payload(
                kind="runtime_jsonl",
                artifact_id="runtime-gateway-1",
                sequence=8,
                source_label=None,
                content=content.read_bytes(),
            ),
        )
    with pytest.raises(SystemExit):
        main(
            [
                "sign-artifact",
                "--private-key",
                str(private),
                "--input",
                str(content),
                "--signature",
                str(tmp_path / "offline-runtime.signature"),
                "--kind",
                "runtime_jsonl",
                "--artifact-id",
                "offline-runtime",
                "--sequence",
                "8",
            ]
        )


def _root_signed_policy(tmp_path: Path, *, repository_path: Path | None = None):
    root = Ed25519PrivateKey.generate()
    root_public = tmp_path / "root.public"
    root_public.write_text(
        root.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex(),
        encoding="ascii",
    )
    signers = []
    for index, kind in enumerate(W2EvidenceKind, start=1):
        key = Ed25519PrivateKey.generate()
        public_hex = (
            key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            .hex()
        )
        signers.append(
            {
                "signer_id": f"signer-{index}",
                "principal_id": f"principal-{index}",
                "public_key_hex": public_hex,
                "role": kind.value,
                "producer_id": (
                    "gateway" if kind is W2EvidenceKind.REAL_RUNTIME else None
                ),
            }
        )
    agentserver_key = Ed25519PrivateKey.generate()
    agentserver_public_hex = (
        agentserver_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex()
    )
    signers.append(
        {
            "signer_id": "signer-runtime-agentserver",
            "principal_id": "principal-runtime-agentserver",
            "public_key_hex": agentserver_public_hex,
            "role": W2EvidenceKind.REAL_RUNTIME.value,
            "producer_id": "agentserver",
        }
    )
    runtime_slots = []
    artifact_slots = []
    prior_by_producer: dict[str, str] = {}
    sequence = 1
    for run_number in (1, 2, 3):
        for producer_id in ("gateway", "agentserver"):
            artifact_id = f"{producer_id}-showcase-{run_number}"
            runtime_slots.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_sequence": sequence,
                    "producer_id": producer_id,
                    "process_epoch": f"{producer_id}-epoch-{run_number}",
                    "predecessor_artifact_id": prior_by_producer.get(producer_id),
                    "showcase_run": run_number,
                }
            )
            artifact_slots.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_sequence": sequence,
                    "evidence_kind": W2EvidenceKind.REAL_RUNTIME.value,
                    "signer_id": (
                        next(
                            signer["signer_id"]
                            for signer in signers
                            if signer["producer_id"] == producer_id
                        )
                    ),
                    "source_label": None,
                    "expected_subjects": ["runtime:runtime.turn"],
                }
            )
            prior_by_producer[producer_id] = artifact_id
            sequence += 1
    policy = tmp_path / "trust-policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema": "live-voice.w2-trust-policy.v2",
                "policy_id": "w2-policy-1",
                "repository_path": str((repository_path or tmp_path).resolve()),
                "candidate": {
                    "candidate_sha": "a" * 40,
                    "environment_id": "environment-1",
                    "session_id": "session-1",
                    "mode_id": "integrated-formal",
                },
                "evidence_set_id": "evidence-set-1",
                "runtime_slots": runtime_slots,
                "artifact_slots": artifact_slots,
                "signers": signers,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    signature = tmp_path / "trust-policy.signature"
    signature.write_text(root.sign(policy.read_bytes()).hex(), encoding="ascii")
    return policy, signature, root_public


def test_root_signed_policy_accepts_absolute_repository_path_with_spaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = tmp_path / "candidate with spaces"
    repository.mkdir()
    policy, signature, root_public = _root_signed_policy(
        tmp_path, repository_path=repository
    )
    expected_root = hashlib.sha256(
        bytes.fromhex(root_public.read_text(encoding="ascii"))
    ).hexdigest()

    trust, _, _ = _load_trust_policy(
        policy,
        signature,
        root_public,
        expected_root_sha256=expected_root,
    )

    assert trust.repository_path == str(repository.resolve())
    assert (
        main(
            [
                "validate-policy",
                "--trust-policy",
                str(policy),
                "--trust-policy-signature",
                str(signature),
                "--root-public-key",
                str(root_public),
                "--expected-root-sha256",
                expected_root,
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["repository_path"] == str(repository.resolve())


@pytest.mark.parametrize("control", ("\x00", "\t", "\r", "\n", "\x7f"))
def test_root_authorized_repository_path_rejects_control_characters(
    tmp_path: Path, control: str
) -> None:
    with pytest.raises(W2GateContractViolation, match="control character"):
        _required_absolute_path(
            f"{tmp_path.resolve()}{control}candidate",
            "root-authorized repository_path",
        )


def test_root_authorized_repository_path_still_requires_absolute() -> None:
    with pytest.raises(W2GateContractViolation, match="must be absolute"):
        _required_absolute_path(
            "candidate with spaces", "root-authorized repository_path"
        )


def test_external_root_signed_policy_loads_and_tampering_fails_closed(
    tmp_path: Path,
) -> None:
    policy, signature, root_public = _root_signed_policy(tmp_path)
    expected_root = hashlib.sha256(
        bytes.fromhex(root_public.read_text(encoding="ascii"))
    ).hexdigest()
    trust, policy_digest, root_digest = _load_trust_policy(
        policy,
        signature,
        root_public,
        expected_root_sha256=expected_root,
    )
    assert len(trust.public_keys) == len(W2EvidenceKind) + 1
    assert trust.candidate_binding == (
        "a" * 40,
        "environment-1",
        "session-1",
        "integrated-formal",
    )
    assert len(trust.runtime_slots) == 6
    assert all(
        "public_key_hex" in signer and "public_key_file" not in signer
        for signer in json.loads(policy.read_text("utf-8"))["signers"]
    )
    assert len(policy_digest) == 64
    assert len(root_digest) == 64
    with pytest.raises(ValueError, match="expected fingerprint"):
        _load_trust_policy(
            policy,
            signature,
            root_public,
            expected_root_sha256="0" * 64,
        )

    candidate = SimpleNamespace(
        candidate_sha="a" * 40,
        environment_id="environment-1",
        session_id="session-1",
        mode_id="integrated-formal",
    )
    artifacts = tuple(
        SimpleNamespace(
            artifact_id=slot.artifact_id,
            sequence=slot.artifact_sequence,
            producer_id=slot.producer_id,
            process_epoch=slot.process_epoch,
            predecessor_artifact_id=slot.predecessor_artifact_id,
            evidence_set_id="evidence-set-1",
            runtime_format_version=2,
            evidence_kinds=frozenset({W2EvidenceKind.REAL_RUNTIME}),
            signer_id=next(
                planned.signer_id
                for planned in trust.artifact_slots
                if planned.artifact_id == slot.artifact_id
            ),
            source_label="runtime-jsonl",
            proven_subjects=frozenset({"runtime:runtime.turn"}),
        )
        for slot in trust.runtime_slots
    )
    showcase_runs = tuple(
        SimpleNamespace(
            run_number=run_number,
            evidence_ids=tuple(
                slot.artifact_id
                for slot in trust.runtime_slots
                if slot.showcase_run == run_number
            ),
        )
        for run_number in (1, 2, 3)
    )
    _verify_root_authorized_scope(
        repository=tmp_path.resolve(),
        candidate=candidate,  # type: ignore[arg-type]
        artifacts=artifacts,  # type: ignore[arg-type]
        showcase_runs=showcase_runs,  # type: ignore[arg-type]
        trust_policy=trust,
    )
    with pytest.raises(ValueError, match="root-authorized plan"):
        _verify_root_authorized_scope(
            repository=tmp_path.resolve(),
            candidate=candidate,  # type: ignore[arg-type]
            artifacts=artifacts[:-1],  # type: ignore[arg-type]
            showcase_runs=showcase_runs,  # type: ignore[arg-type]
            trust_policy=trust,
        )

    policy.write_text(policy.read_text("utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="root signature"):
        _load_trust_policy(
            policy,
            signature,
            root_public,
            expected_root_sha256=expected_root,
        )


def test_validate_policy_reports_pinned_root_and_complete_artifact_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy, signature, root_public = _root_signed_policy(tmp_path)
    expected_root = hashlib.sha256(
        bytes.fromhex(root_public.read_text(encoding="ascii"))
    ).hexdigest()

    assert (
        main(
            [
                "validate-policy",
                "--trust-policy",
                str(policy),
                "--trust-policy-signature",
                str(signature),
                "--root-public-key",
                str(root_public),
                "--expected-root-sha256",
                expected_root,
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "VALID"
    assert result["trust_root_sha256"] == expected_root
    assert result["repository_path"] == str(tmp_path.resolve())
    assert len(result["artifact_slots"]) == 6
    assert all(
        slot["expected_subjects"] == ["runtime:runtime.turn"]
        for slot in result["artifact_slots"]
    )
