from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import derive_w2_policy_scaffold as helper
from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    create_observation,
)
from jiuwenswarm.server.live_voice.w2_demo_gate import (
    W2EvidenceKind,
    w2_artifact_signature_payload,
)


_SHA = "a" * 40


def _public_hex(key: Ed25519PrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex()
    )


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("ascii")


@dataclass
class Fixture:
    root: Path
    import_path: Path
    policy_path: Path
    policy_signature_path: Path
    root_public_path: Path
    root_sha256: str
    plan_path: Path
    outputs: tuple[Path, Path, Path]
    private_by_signer: dict[str, Ed25519PrivateKey]

    def derive(self) -> dict[str, object]:
        return helper.derive_scaffold(
            rehearsal_import_path=self.import_path,
            rehearsal_trust_policy_path=self.policy_path,
            rehearsal_trust_policy_signature_path=self.policy_signature_path,
            root_public_key_path=self.root_public_path,
            expected_root_sha256=self.root_sha256,
            next_attempt_plan_path=self.plan_path,
            unsigned_policy_output=self.outputs[0],
            subject_map_output=self.outputs[1],
            digest_output=self.outputs[2],
        )


def _observation_records(*, producer: str, token: str) -> list[dict[str, object]]:
    source, segment = (
        ("product.w2.media.capture", "speech.capture")
        if producer == "gateway"
        else ("product.w2.p2.activate", "runtime.queue")
    )
    binding = {"correlation_id": f"correlation-{token}"}
    if producer == "gateway":
        binding["interaction_id"] = f"interaction-{token}"
    route = {
        "implementation_class": "formal",
        "owner_module": "product.composition",
        "capability_provider": f"synthetic-{producer}",
        "contract_version": LIVE_VOICE_CONTRACT_VERSION,
        "reason_code": None,
    }
    common = {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "segment_name": segment,
        "observed_at": "2026-08-08T10:00:00Z",
        "monotonic_ms": 1.0,
        "binding": binding,
        "route": route,
        "source_component": source,
        "source_record_id": f"source-record-{token}",
    }
    return [
        create_observation(
            {**common, "event_id": f"route-{token}", "event_name": "route.selected"}
        ).to_dict(),
        create_observation(
            {
                **common,
                "event_id": f"complete-{token}",
                "event_name": "segment.completed",
                "state": "terminal",
                "outcome": "completed",
                "duration_ms": 1.0,
            }
        ).to_dict(),
    ]


def _runtime_bytes(
    *,
    repository: Path,
    artifact_id: str,
    sequence: int,
    producer: str,
    process_epoch: str,
    predecessor: str | None,
    closed: bool = True,
) -> bytes:
    records = _observation_records(producer=producer, token=artifact_id)
    candidate = {
        "candidate_sha": _SHA,
        "environment_id": "rehearsal-environment",
        "session_id": "rehearsal-session",
        "mode_id": "integrated-formal",
    }
    header = {
        "evidence_schema": "live-voice.w2-jsonl-evidence.v2",
        "record_kind": "header",
        "evidence_set_id": "rehearsal-evidence-set",
        "artifact_id": artifact_id,
        "artifact_sequence": sequence,
        "producer_id": producer,
        "process_epoch": process_epoch,
        "predecessor_artifact_id": predecessor,
        "repository_path": str(repository.resolve()),
        "candidate": candidate,
    }
    envelopes = [
        {
            "evidence_schema": "live-voice.w2-jsonl-evidence.v2",
            "candidate": candidate,
            "record_kind": "observation",
            "sequence": index,
            "record": record,
        }
        for index, record in enumerate(records)
    ]
    footer = {
        "evidence_schema": "live-voice.w2-jsonl-evidence.v2",
        "record_kind": "footer",
        "artifact_id": artifact_id,
        "record_count": len(records),
        "last_sequence": len(records) - 1,
        "accepted_observations": len(records),
        "accepted_metrics": 0,
        "rejected_invalid": 0,
        "rejected_capacity": 0,
        "failed_writes": 0,
        "closed": True,
    }
    values = [header, *envelopes, *([footer] if closed else [])]
    return b"".join(_canonical(value) for value in values)


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_canonical(value))


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fixture:
    repository = tmp_path / "candidate"
    repository.mkdir()
    evidence = tmp_path / "rehearsal"
    evidence.mkdir()
    root_key = Ed25519PrivateKey.generate()
    role_keys = {
        "runtime-gateway": Ed25519PrivateKey.generate(),
        "runtime-agentserver": Ed25519PrivateKey.generate(),
        "automated": Ed25519PrivateKey.generate(),
        "review": Ed25519PrivateKey.generate(),
        "fault": Ed25519PrivateKey.generate(),
        "human": Ed25519PrivateKey.generate(),
    }
    roles = {
        "runtime-gateway": (W2EvidenceKind.REAL_RUNTIME, "gateway"),
        "runtime-agentserver": (W2EvidenceKind.REAL_RUNTIME, "agentserver"),
        "automated": (W2EvidenceKind.AUTOMATED_CONFORMANCE, None),
        "review": (W2EvidenceKind.INDEPENDENT_REVIEW, None),
        "fault": (W2EvidenceKind.FAULT_INJECTION, None),
        "human": (W2EvidenceKind.HUMAN_OBSERVATION, None),
    }
    signers = [
        {
            "signer_id": signer_id,
            "principal_id": f"principal-{signer_id}",
            "public_key_hex": _public_hex(role_keys[signer_id]),
            "role": role.value,
            "producer_id": producer,
        }
        for signer_id, (role, producer) in roles.items()
    ]
    runtime_slots = []
    artifact_slots = []
    imports = []
    previous: dict[str, str] = {}
    sequence = 1
    for run in (1, 2, 3):
        for producer in ("gateway", "agentserver"):
            artifact_id = f"reh-{producer}-showcase-{run}"
            epoch = f"reh-{producer}-epoch-{run}"
            predecessor = previous.get(producer)
            runtime_slots.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_sequence": sequence,
                    "producer_id": producer,
                    "process_epoch": epoch,
                    "predecessor_artifact_id": predecessor,
                    "showcase_run": run,
                }
            )
            signer_id = f"runtime-{producer}"
            artifact_slots.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_sequence": sequence,
                    "evidence_kind": "real_runtime",
                    "signer_id": signer_id,
                    "source_label": None,
                    "expected_subjects": ["rehearsal:derive-only"],
                }
            )
            content = _runtime_bytes(
                repository=repository,
                artifact_id=artifact_id,
                sequence=sequence,
                producer=producer,
                process_epoch=epoch,
                predecessor=predecessor,
            )
            content_path = evidence / f"{artifact_id}.jsonl"
            signature_path = evidence / f"{artifact_id}.signature"
            content_path.write_bytes(content)
            payload = w2_artifact_signature_payload(
                kind="runtime_jsonl",
                artifact_id=artifact_id,
                sequence=sequence,
                source_label=None,
                content=content,
            )
            signature_path.write_text(
                role_keys[signer_id].sign(payload).hex(), encoding="ascii"
            )
            imports.append(
                {
                    "logical_slot": f"showcase-{run}-{producer}",
                    "artifact_id": artifact_id,
                    "content_file": content_path.name,
                    "signature_file": signature_path.name,
                    "expected_subjects_sha256": None,
                }
            )
            previous[producer] = artifact_id
            sequence += 1
    policy = {
        "schema": "live-voice.w2-trust-policy.v2",
        "policy_id": "rehearsal-policy",
        "repository_path": str(repository.resolve()),
        "candidate": {
            "candidate_sha": _SHA,
            "environment_id": "rehearsal-environment",
            "session_id": "rehearsal-session",
            "mode_id": "integrated-formal",
        },
        "evidence_set_id": "rehearsal-evidence-set",
        "runtime_slots": runtime_slots,
        "artifact_slots": artifact_slots,
        "signers": signers,
    }
    policy_path = evidence / "trust-policy.json"
    policy_path.write_bytes(_canonical(policy))
    policy_signature = evidence / "trust-policy.signature"
    policy_signature.write_text(
        root_key.sign(policy_path.read_bytes()).hex(), encoding="ascii"
    )
    root_public = evidence / "root.public"
    root_public.write_text(_public_hex(root_key), encoding="ascii")
    root_sha = hashlib.sha256(bytes.fromhex(root_public.read_text())).hexdigest()
    import_path = evidence / "imports.json"
    _write_json(
        import_path,
        {
            "schema": "machine-private.w2-rehearsal-import.v1",
            "rehearsal_root": str(evidence.resolve()),
            "runtime_imports": imports,
        },
    )
    next_slots = []
    previous.clear()
    for index, item in enumerate(imports, start=1):
        producer = (
            "gateway" if item["logical_slot"].endswith("gateway") else "agentserver"
        )
        run = (index + 1) // 2
        artifact_id = f"formal-{producer}-showcase-{run}"
        next_slots.append(
            {
                "logical_slot": item["logical_slot"],
                "artifact_id": artifact_id,
                "artifact_sequence": index,
                "producer_id": producer,
                "process_epoch": f"formal-{producer}-epoch-{run}",
                "predecessor_artifact_id": previous.get(producer),
                "showcase_run": run,
                "signer_id": f"runtime-{producer}",
            }
        )
        previous[producer] = artifact_id
    plan_path = evidence / "next-plan.json"
    _write_json(
        plan_path,
        {
            "schema": "machine-private.w2-next-attempt-plan.v1",
            "policy_id": "formal-policy",
            "repository_path": str(repository.resolve()),
            "candidate": {
                "candidate_sha": _SHA,
                "environment_id": "formal-environment",
                "session_id": "formal-session",
                "mode_id": "integrated-formal",
            },
            "evidence_set_id": "formal-evidence-set",
            "runtime_slots": next_slots,
            "non_runtime_artifact_slots": [],
            "signers": signers,
        },
    )
    monkeypatch.setattr(
        helper,
        "verify_w2_candidate_checkout",
        lambda **kwargs: kwargs["candidate_sha"],
    )
    formal_staging = tmp_path / "formal-staging"
    formal_staging.mkdir()
    outputs = (
        formal_staging / "unsigned-policy.json",
        formal_staging / "subject-map.json",
        formal_staging / "digest.json",
    )
    return Fixture(
        root=evidence,
        import_path=import_path,
        policy_path=policy_path,
        policy_signature_path=policy_signature,
        root_public_path=root_public,
        root_sha256=root_sha,
        plan_path=plan_path,
        outputs=outputs,
        private_by_signer=role_keys,
    )


def test_derives_exact_subjects_and_writes_only_unsigned_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = fixture.derive()
    assert result["status"] == "VALID_UNSIGNED"
    policy = json.loads(fixture.outputs[0].read_text())
    assert len(policy["runtime_slots"]) == 6
    assert all(
        slot["expected_subjects"]
        and "rehearsal:derive-only" not in slot["expected_subjects"]
        for slot in policy["artifact_slots"]
    )
    subject_map = json.loads(fixture.outputs[1].read_text())
    assert subject_map["rehearsal_policy_not_gate_eligible"] is True
    assert all(
        all(
            subject.startswith(("runtime:", "fact:", "candidate:"))
            for subject in item["subjects"]
        )
        for item in subject_map["templates"]
    )


def test_tampered_signature_fails_without_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    descriptor = json.loads(fixture.import_path.read_text())
    signature = fixture.root / descriptor["runtime_imports"][0]["signature_file"]
    signature.write_text("0" * 128, encoding="ascii")
    with pytest.raises(Exception, match="signature"):
        fixture.derive()
    assert not any(path.exists() for path in fixture.outputs)


def test_unclosed_runtime_fails_without_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    descriptor = json.loads(fixture.import_path.read_text())
    item = descriptor["runtime_imports"][0]
    content_path = fixture.root / item["content_file"]
    lines = content_path.read_bytes().splitlines(keepends=True)
    content = b"".join(lines[:-1])
    content_path.write_bytes(content)
    signature_path = fixture.root / item["signature_file"]
    signature_path.write_text(
        fixture.private_by_signer["runtime-gateway"]
        .sign(
            w2_artifact_signature_payload(
                kind="runtime_jsonl",
                artifact_id=item["artifact_id"],
                sequence=1,
                source_label=None,
                content=content,
            )
        )
        .hex(),
        encoding="ascii",
    )
    with pytest.raises(Exception, match="not closed"):
        fixture.derive()
    assert not any(path.exists() for path in fixture.outputs)


def test_candidate_and_producer_mismatch_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    plan = json.loads(fixture.plan_path.read_text())
    plan["candidate"]["candidate_sha"] = "b" * 40
    _write_json(fixture.plan_path, plan)
    with pytest.raises(helper.ScaffoldError, match="candidate SHA differs"):
        fixture.derive()
    plan["candidate"]["candidate_sha"] = _SHA
    plan["runtime_slots"][0]["producer_id"] = "agentserver"
    _write_json(fixture.plan_path, plan)
    with pytest.raises(helper.ScaffoldError, match="producer differs"):
        fixture.derive()
    assert not any(path.exists() for path in fixture.outputs)


def test_subject_digest_and_slot_mismatch_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    descriptor = json.loads(fixture.import_path.read_text())
    descriptor["runtime_imports"][0]["expected_subjects_sha256"] = "0" * 64
    _write_json(fixture.import_path, descriptor)
    with pytest.raises(helper.ScaffoldError, match="subject set differs"):
        fixture.derive()
    descriptor["runtime_imports"][0]["expected_subjects_sha256"] = None
    descriptor["runtime_imports"].pop()
    _write_json(fixture.import_path, descriptor)
    with pytest.raises(helper.ScaffoldError, match="exactly cover"):
        fixture.derive()
    assert not any(path.exists() for path in fixture.outputs)


def test_existing_output_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    fixture.outputs[1].write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        fixture.derive()
    assert fixture.outputs[1].read_text(encoding="utf-8") == "keep"
    assert not fixture.outputs[0].exists()
    assert not fixture.outputs[2].exists()


def test_duplicate_outputs_and_wrong_signer_producer_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    with pytest.raises(helper.ScaffoldError, match="output paths must be distinct"):
        helper.derive_scaffold(
            rehearsal_import_path=fixture.import_path,
            rehearsal_trust_policy_path=fixture.policy_path,
            rehearsal_trust_policy_signature_path=fixture.policy_signature_path,
            root_public_key_path=fixture.root_public_path,
            expected_root_sha256=fixture.root_sha256,
            next_attempt_plan_path=fixture.plan_path,
            unsigned_policy_output=fixture.outputs[0],
            subject_map_output=fixture.outputs[0],
            digest_output=fixture.outputs[2],
        )
    plan = json.loads(fixture.plan_path.read_text())
    for slot in plan["runtime_slots"]:
        if slot["producer_id"] == "gateway":
            slot["signer_id"] = "runtime-agentserver"
    _write_json(fixture.plan_path, plan)
    with pytest.raises(helper.ScaffoldError, match="does not own"):
        fixture.derive()
    assert not any(path.exists() for path in fixture.outputs)
