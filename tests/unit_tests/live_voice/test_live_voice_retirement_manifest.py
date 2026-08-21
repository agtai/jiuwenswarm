# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = (
    ROOT / "tests" / "fixtures" / "live_voice_retirement_manifest_v1" / "manifest.json"
)
EXPECTED_B1_FILES = {
    "jiuwenswarm/server/live_voice/observability_correlation_contract.py",
    "jiuwenswarm/server/live_voice/live_voice_configuration_declaration.py",
    "tests/unit_tests/live_voice/test_observability_correlation_contract.py",
    "tests/unit_tests/live_voice/test_live_voice_configuration_declaration.py",
    "tests/fixtures/live_voice_retirement_manifest_v1/manifest.json",
    "tests/unit_tests/live_voice/test_live_voice_retirement_manifest.py",
    "live-voice/reviews/P3_8B_PREPARATION_RETIREMENT_MANIFEST_2026-08-21.md",
}
REQUIRED_MANIFEST_IDS = {
    "legacy_web_task_lane",
    "legacy_project_scheduler_adapter",
    "legacy_task_models",
    "legacy_ticket_media",
    "legacy_demo_entrypoints",
    "retired_snapshot_helper",
    "exact_demo_profile_and_fixtures",
    "current_configuration_and_intent_retained",
    "w2_dotenv_preservation_flags",
    "w2_rehearsal_assets",
    "retired_s7_s8_runners",
    "retired_wave2_evidence_gate",
    "duplicate_frontend_validators",
    "duplicate_exact_object_validators",
    "duplicate_operation_allowlists",
    "frontend_formal_test_support",
    "formal_task_result_route_retained",
    "test_support_rehome",
    "p3_8a_accepted_observability_assets",
    "product_composition_contract_retained_boundary",
    "historical_document_batches",
}
EXPECTED_AUDIT_MAPPING_IDS = {
    "branch_w2_dotenv",
    "branch_ticket_path",
    "branch_snapshot",
    "branch_s7",
    "branch_s8",
    "backend_alpha_benchmark",
    "backend_alpha_privacy",
    "backend_exporter",
    "backend_fault_harness",
    "backend_observability_adapter",
    "backend_p2_readiness",
    "backend_realtime_media",
    "frontend_runtime_replica",
    "frontend_fake_vertical",
    "frontend_task_result",
    "frontend_v2_contract",
    "frontend_observability",
    "frontend_product_contract",
    "frontend_lifecycle_recorder",
    "replace_legacy_web",
    "replace_task_core",
    "replace_executor",
    "replace_demo_profile",
    "replace_launcher",
    "replace_demo_fixture",
    "replace_w2_rehearsal",
    "duplicate_strict_record",
    "duplicate_exact_object",
    "duplicate_binding_equality",
    "duplicate_task_clone",
    "duplicate_generation_traversal",
    "duplicate_operation_drift",
    "retained_product_roots",
    "retained_independent_validation",
    "excluded_local_artifacts",
}
EXPECTED_LATER_TWENTY_PATHS = {
    "live-voice/evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md",
    "live-voice/evidence/P3_G0_PRODUCT_READINESS_FAIL_20260819_f24dd17d.md",
    "live-voice/evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md",
    "live-voice/evidence/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_EVIDENCE_20260821.md",
    "live-voice/reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md",
    "live-voice/reviews/P3_1_CANONICAL_MULTI_TASK_IMPLEMENTATION_REVIEW_2026-08-19.md",
    "live-voice/reviews/P3_2_P3_5A_ACTIVATION_PREPARATION_2026-08-18.md",
    "live-voice/reviews/P3_3_CAPABILITY_ADMISSION_ACTIVATION_PREPARATION_2026-08-18.md",
    "live-voice/reviews/P3_4_DURABILITY_RECOVERY_ACTIVATION_PREPARATION_2026-08-18.md",
    "live-voice/reviews/P3_4_DURABILITY_RECOVERY_IMPLEMENTATION_REVIEW_2026-08-21.md",
    "live-voice/reviews/P3_5B_P3_6_ACTIVATION_PREPARATION_2026-08-18.md",
    "live-voice/reviews/P3_5B_PRESENTATION_CONSUMPTION_IMPLEMENTATION_REVIEW_2026-08-21.md",
    "live-voice/reviews/P3_8A_OBSERVABILITY_ASSETS_REVIEW_2026-08-19.md",
    "live-voice/reviews/P3_HISTORICAL_SOURCE_ASSET_EXTRACTION_MANIFEST_2026-08-18.md",
    "live-voice/reviews/P3_IMPLEMENTATION_COVERAGE_AND_HISTORICAL_REUSE_AUDIT_2026-08-18.md",
    "live-voice/reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md",
    "live-voice/reviews/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_EXECUTION_PACKET_2026-08-20.md",
    "live-voice/reviews/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_IMPLEMENTATION_REVIEW_2026-08-21.md",
    "live-voice/roadmap/FULL_P3_EXECUTION_PLAN.md",
    "live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md",
}
EXPECTED_POST_NOTE_PATHS = {
    "live-voice/evidence/P1_P2_W3_INTEGRATION_EVIDENCE_20260821.md",
    "live-voice/evidence/P1_T1_POST_TTS_CAPTURE_ROTATION_REPAIR_2026-08-19.md",
    "live-voice/evidence/P1_T2_HANDS_FREE_PHYSICAL_VALIDATION_AND_LATENCY_FINDING_2026-08-20.md",
    "live-voice/evidence/P1_T2_POST_PLAYOUT_RECEIPT_DECOUPLING_2026-08-20.md",
    "live-voice/evidence/P1_T2_SUCCESSOR_CAPTURE_ACK_DECOUPLING_2026-08-20.md",
}
EXPECTED_B1_ADDED_PATHS = {
    "live-voice/reviews/P3_8B_PREPARATION_RETIREMENT_MANIFEST_2026-08-21.md",
}
INVENTORY_BASELINE = "965fc827fb409b97d791f64febc7d32f0aaf71d3"


def _load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _assert_existing_relative_path(value: str) -> None:
    path = Path(value)
    assert not path.is_absolute()
    assert ".." not in path.parts
    assert "\\" not in value
    assert (ROOT / path).exists(), value


def _path_set_digest(paths: set[str]) -> str:
    canonical = "\n".join(sorted(paths)) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _git_object_exists(tree: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{tree}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def test_manifest_records_exact_b1_scope_and_b2_scoped_retirement() -> None:
    manifest = _load()
    assert manifest["schema_version"] == "live-voice.retirement-manifest.v1"
    assert manifest["phase"] == "b2_scoped_retirement_executed"
    assert manifest["deletion_authorized"] is False
    assert manifest["deleted_paths"] == ["scripts/live_voice_snapshot.ps1"]
    assert manifest["b2_execution_baseline"] == (
        "cc42098163bf6e9d7cec303f37551d3526997eb4"
    )
    assert manifest["retirement_commits"] == [
        "4e207faa",
        "ddde7b87",
        "7b283898",
    ]
    assert manifest["accepted_interface_freeze"] == {
        "p3_7_implementation_commit": ("98e063f084c140cb6eb0042de32f3695c89c7279"),
        "p3_7_freeze_commit": "d9a18c06f02b293b1aed4625a7ed84665f475b57",
        "review": (
            "live-voice/reviews/"
            "P3_7_FORMAL_INTEGRATED_WEB_IMPLEMENTATION_REVIEW_2026-08-21.md"
        ),
        "evidence": (
            "live-voice/evidence/P3_7_FORMAL_INTEGRATED_WEB_EVIDENCE_20260821.md"
        ),
    }
    _assert_existing_relative_path(manifest["accepted_interface_freeze"]["review"])
    _assert_existing_relative_path(manifest["accepted_interface_freeze"]["evidence"])
    assert set(manifest["b1_add_only_files"]) == EXPECTED_B1_FILES
    for path in manifest["source_audits"] + manifest["b1_add_only_files"]:
        _assert_existing_relative_path(path)
    assert any(
        "Generic non-Live-Voice" in item for item in manifest["explicit_exclusions"]
    )


def test_every_retirement_item_has_owner_oracle_preconditions_tests_and_rollback() -> (
    None
):
    entries = _load()["entries"]
    assert {entry["id"] for entry in entries}.issuperset(REQUIRED_MANIFEST_IDS)
    assert len(entries) == len({entry["id"] for entry in entries})
    expected_keys = {
        "id",
        "category",
        "phase",
        "disposition",
        "deletion_authorized",
        "paths",
        "replacement_owner",
        "oracle_migration",
        "delete_preconditions",
        "affected_tests",
        "rollback",
    }
    for entry in entries:
        assert set(entry) == expected_keys
        assert entry["phase"] in {"inventory", "retired"}
        assert entry["deletion_authorized"] is (entry["phase"] == "retired")
        for field in (
            "paths",
            "oracle_migration",
            "delete_preconditions",
            "affected_tests",
        ):
            assert entry[field], (entry["id"], field)
        assert entry["replacement_owner"]
        assert entry["rollback"]
        for path in entry["paths"]:
            if path in _load()["deleted_paths"]:
                assert not (ROOT / path).exists()
                assert _git_object_exists(_load()["b2_execution_baseline"], path)
            else:
                _assert_existing_relative_path(path)
        for path in entry["affected_tests"]:
            _assert_existing_relative_path(path)


def test_frozen_requirements_and_b2_manifest_are_dependency_gated() -> None:
    manifest = _load()
    assert {item["id"] for item in manifest["frozen_interface_requirements"]} == {
        "panel_formal_route_io",
        "registry_agentserver_composition",
        "task_projection",
        "feature_off",
    }
    stages = {
        item["id"]: item["after"] for item in manifest["second_stage_integration"]
    }
    assert stages == {
        "compose_correlation": "p3_7_gate_pass",
        "compose_configuration": "p3_7_gate_pass",
        "compose_p3_8a_assets": "p3_7_gate_pass",
        "retirement_execution_candidate": "replacement_oracles_pass",
    }
    registry_requirement = next(
        item["requirement"]
        for item in manifest["frozen_interface_requirements"]
        if item["id"] == "registry_agentserver_composition"
    )
    correlation_intent = next(
        item["intent"]
        for item in manifest["second_stage_integration"]
        if item["id"] == "compose_correlation"
    )
    assert "keyed-HMAC receipt-verifier trust anchor" in registry_requirement
    assert "receipt assertion alone cannot make correlation ready" in (
        registry_requirement
    )
    assert "mandatory root causation" in correlation_intent
    assert "verifier is missing, rejects, raises" in correlation_intent
    assert "unreceipted, self-signed or cross-scope token set" in correlation_intent


def test_every_audit_object_has_a_live_source_locator_and_current_disposition() -> None:
    manifest = _load()
    entries = {entry["id"] for entry in manifest["entries"]}
    mappings = manifest["audit_object_mappings"]
    assert {mapping["id"] for mapping in mappings} == EXPECTED_AUDIT_MAPPING_IDS
    assert len(mappings) == len(EXPECTED_AUDIT_MAPPING_IDS)
    source_cache: dict[str, str] = {}
    for mapping in mappings:
        source = mapping["source_audit"]
        _assert_existing_relative_path(source)
        source_text = source_cache.setdefault(
            source,
            (ROOT / source).read_text(encoding="utf-8"),
        )
        assert mapping["locator_token"] in source_text, mapping["id"]
        assert set(mapping["manifest_entry_ids"]).issubset(entries)
        assert mapping["current_disposition"]
        assert mapping["retained_owner"]
        assert mapping["excluded_scope"]


def test_shared_files_are_symbol_scoped_and_retain_current_authority() -> None:
    manifest = _load()
    boundaries = manifest["shared_file_boundaries"]
    required_paths = {
        "jiuwenswarm/server/live_voice/project_code_executor.py",
        "jiuwenswarm/server/live_voice/product_p3_text_adapter.py",
        "jiuwenswarm/gateway/live_voice/dedicated_media_registration.py",
        "jiuwenswarm/gateway/channel_manager/web/web_connect.py",
        "jiuwenswarm/dotenv_early.py",
        "jiuwenswarm/server/live_voice/voice_task_bridge.py",
        "jiuwenswarm/server/live_voice/batch_speech.py",
        "jiuwenswarm/server/live_voice/p3_authenticated_composition.py",
        "jiuwenswarm/server/live_voice/product_composition_registry.py",
        "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts",
        "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3ProgressGenerationJournal.ts",
        "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts",
        "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts",
    }
    assert {boundary["path"] for boundary in boundaries} == required_paths
    for boundary in boundaries:
        assert boundary["whole_file_deletion_target"] is False
        assert boundary["retained_symbols"]
        assert boundary["retained_owner"]
        assert boundary["delete_precondition"]
        if not boundary["candidate_symbols"]:
            assert boundary["path"] in {
                "jiuwenswarm/gateway/live_voice/dedicated_media_registration.py",
                "jiuwenswarm/gateway/channel_manager/web/web_connect.py",
                "jiuwenswarm/dotenv_early.py",
            }
            assert "Completed in" in boundary["delete_precondition"]
        path = ROOT / boundary["path"]
        source = path.read_text(encoding="utf-8")
        for symbol in boundary["candidate_symbols"] + boundary["retained_symbols"]:
            assert symbol in source, (boundary["path"], symbol)
    by_path = {boundary["path"]: boundary for boundary in boundaries}
    assert (
        "handle_registered_media_socket"
        in by_path["jiuwenswarm/gateway/live_voice/dedicated_media_registration.py"][
            "retained_symbols"
        ]
    )
    assert (
        "_is_dedicated_media_route"
        in by_path["jiuwenswarm/gateway/channel_manager/web/web_connect.py"][
            "retained_symbols"
        ]
    )
    executor_entry = next(
        entry
        for entry in manifest["entries"]
        if entry["id"] == "legacy_project_scheduler_adapter"
    )
    assert "DirectProjectCodeExecutorAdapter" in executor_entry["replacement_owner"]
    assert "DirectProjectCodeExecutorAdapter" in (
        ROOT / "jiuwenswarm/server/live_voice/project_code_executor.py"
    ).read_text(encoding="utf-8")


def test_legacy_ticket_media_targets_only_prefix_compatibility_symbols() -> None:
    manifest = _load()
    boundaries = {
        boundary["path"]: boundary for boundary in manifest["shared_file_boundaries"]
    }
    registration = boundaries[
        "jiuwenswarm/gateway/live_voice/dedicated_media_registration.py"
    ]
    web_channel = boundaries["jiuwenswarm/gateway/channel_manager/web/web_connect.py"]
    assert registration["candidate_symbols"] == []
    assert {
        "MEDIA_ROUTE_PATH",
        "DedicatedMediaProductRegistry",
        "handle_registered_media_socket",
    }.issubset(registration["retained_symbols"])
    assert web_channel["candidate_symbols"] == []
    assert {
        "_DEDICATED_MEDIA_ROUTE_PATH",
        "_is_dedicated_media_route",
        "WebChannel",
    }.issubset(web_channel["retained_symbols"])
    entry = next(
        item for item in manifest["entries"] if item["id"] == "legacy_ticket_media"
    )
    assert entry["phase"] == "retired"
    assert entry["deletion_authorized"] is True
    assert entry["disposition"] == "exact_symbols_removed_7b283898"
    assert entry["replacement_owner"] == (
        "Current fixed-route DedicatedMediaProductRegistry and WebChannel authority"
    )
    assert set(entry["affected_tests"]) == {
        "tests/unit_tests/gateway/test_dedicated_media_registration.py",
        "tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py",
        "jiuwenswarm/channels/web/frontend/tests/liveVoiceBrowserDedicatedMediaRoute.test.mjs",
    }
    combined_source = "\n".join(
        (ROOT / path).read_text(encoding="utf-8") for path in entry["paths"]
    )
    for retired in (
        "MEDIA_ROUTE_PREFIX",
        "legacy_path_ticket_compat",
        "_DEDICATED_MEDIA_ROUTE_PREFIX",
    ):
        assert retired not in combined_source


def test_executed_retirements_and_retained_current_owners_are_exact() -> None:
    manifest = _load()
    entries = {entry["id"]: entry for entry in manifest["entries"]}

    snapshot = entries["retired_snapshot_helper"]
    assert snapshot["phase"] == "retired"
    assert snapshot["deletion_authorized"] is True
    assert snapshot["paths"] == ["scripts/live_voice_snapshot.ps1"]
    assert not (ROOT / snapshot["paths"][0]).exists()
    assert _git_object_exists(manifest["b2_execution_baseline"], snapshot["paths"][0])
    assert (
        "scripts/live_voice_snapshot.ps1"
        not in entries["legacy_demo_entrypoints"]["paths"]
    )

    dotenv = entries["w2_dotenv_preservation_flags"]
    assert dotenv["phase"] == "retired"
    assert dotenv["deletion_authorized"] is True
    dotenv_source = (ROOT / dotenv["paths"][0]).read_text(encoding="utf-8")
    for retired in (
        "W2_GATEWAY_PUBLIC_AGENT_ENV_FLAG",
        "W2_GATEWAY_PUBLIC_AGENT_ENV_KEYS",
        "W2_GATEWAY_AGENT_SECRET_ENV_KEYS",
        "W2_AGENT_PRIVATE_ENV_FLAG",
        "W2_AGENT_PRIVATE_ENV_KEYS",
    ):
        assert retired not in dotenv_source
    for retained in (
        "DESKTOP_PRESERVED_ENV_KEYS",
        "_should_preserve_session_ports",
        "load_dotenv_runtime",
    ):
        assert retained in dotenv_source

    legacy_web_paths = set(entries["legacy_web_task_lane"]["paths"])
    assert not {
        "jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx",
        "jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx",
    }.intersection(legacy_web_paths)
    retained_config_paths = set(
        entries["current_configuration_and_intent_retained"]["paths"]
    )
    assert retained_config_paths == {
        "jiuwenswarm/channels/web/frontend/.env.production",
        "jiuwenswarm/server/live_voice/production_task_intent.py",
    }
    assert not retained_config_paths.intersection(
        entries["exact_demo_profile_and_fixtures"]["paths"]
    )
    assert entries["formal_task_result_route_retained"]["paths"] == [
        "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/"
        "formalTaskResultRoute.ts"
    ]
    assert entries["retired_s7_s8_runners"]["disposition"] == (
        "retain_until_unique_oracles_migrate"
    )
    assert entries["retired_wave2_evidence_gate"]["disposition"] == (
        "retain_live_private_oracle_support"
    )


def test_product_p3_text_adapter_is_symbol_scoped_shared_authority() -> None:
    manifest = _load()
    boundary = next(
        item
        for item in manifest["shared_file_boundaries"]
        if item["path"] == "jiuwenswarm/server/live_voice/product_p3_text_adapter.py"
    )
    assert boundary["whole_file_deletion_target"] is False
    assert set(boundary["candidate_symbols"]) == {
        "_QUERY_OPERATIONS",
        "_MUTATION_OPERATIONS",
    }
    assert {
        "ProductP3TextAdapter",
        "ProductP3QueryRequest",
        "ProductP3ProgressRequest",
        "query",
        "activate_prepared_query",
        "activate_progress",
        "activate_prepared_text_progress",
        "MUTATION_CONFIRMATION_UNAVAILABLE",
    }.issubset(boundary["retained_symbols"])
    entry = next(
        item
        for item in manifest["entries"]
        if item["id"] == "duplicate_operation_allowlists"
    )
    assert entry["disposition"] == "symbol_scoped_await_p3_7_freeze"
    assert (
        "Only product_p3_text_adapter.py::_QUERY_OPERATIONS"
        in (entry["oracle_migration"][0])
    )
    assert "Only named allowlist symbols move" in entry["delete_preconditions"]
    assert set(entry["affected_tests"]) == {
        "tests/unit_tests/live_voice/test_p3_authenticated_composition.py",
        "tests/unit_tests/live_voice/test_product_p3_text_adapter.py",
        "tests/unit_tests/live_voice/test_product_composition_registry.py",
    }


def _audit_batch_paths(source: str, start: str, end: str) -> set[str]:
    section = source.split(start, 1)[1].split(end, 1)[0]
    return set(re.findall(r"^- `([^`]+)`", section, flags=re.MULTILINE))


def test_document_batches_and_later_rebaseline_are_complete_and_linked() -> None:
    manifest = _load()["document_rebaseline"]
    source_path = manifest["source_audit"]
    source = (ROOT / source_path).read_text(encoding="utf-8")
    batch_a = manifest["batch_a_completed"]
    batch_b = manifest["batch_b"]
    batch_c = manifest["batch_c"]

    source_a = _audit_batch_paths(source, "## 3. Batch A", "## 4. Batch B")
    source_b = _audit_batch_paths(source, "## 4. Batch B", "## 5. Batch C")
    source_c = _audit_batch_paths(source, "## 5. Batch C", "## 6. Twenty-file")
    assert len(source_a) == batch_a["audit_time_count"] == 19
    assert len(source_b) == batch_b["audit_time_count"] == 12
    assert len(source_c) == batch_c["audit_time_count"] == 43
    assert set(batch_a["paths"]) == source_a
    assert set(batch_b["paths"]) == source_b
    assert set(batch_c["paths"]) == source_c
    assert batch_a["expected_current_presence"] is False
    for path in batch_a["paths"]:
        assert not (ROOT / path).exists(), path

    later = manifest["later_twenty_rebaseline"]
    post_note = manifest["post_note_additions"]
    b1_added = manifest["b1_added_paths"]
    later_paths = {item["path"] for item in later}
    post_note_paths = {item["path"] for item in post_note}
    b1_added_paths = {item["path"] for item in b1_added}
    assert later_paths == EXPECTED_LATER_TWENTY_PATHS
    assert post_note_paths == EXPECTED_POST_NOTE_PATHS
    assert b1_added_paths == EXPECTED_B1_ADDED_PATHS
    later_provenance = manifest["later_twenty_provenance"]
    post_note_provenance = manifest["post_note_provenance"]
    assert later_provenance == {
        "method": (
            "frozen explicit path set reconstructed from the documentation-audit "
            "rebaseline boundary and revalidated at the B1 baseline"
        ),
        "inventory_baseline": INVENTORY_BASELINE,
        "path_set_sha256": _path_set_digest(EXPECTED_LATER_TWENTY_PATHS),
    }
    assert post_note_provenance == {
        "method": (
            "frozen explicit pre-B1 path set after the documentation-audit "
            "rebaseline note, verified in the inventory baseline Git tree"
        ),
        "inventory_baseline": INVENTORY_BASELINE,
        "path_set_sha256": _path_set_digest(EXPECTED_POST_NOTE_PATHS),
    }
    assert manifest["b1_candidate_provenance"] == {
        "method": (
            "B1 add-only path set, absent from the inventory baseline and verified "
            "in the candidate HEAD Git tree"
        ),
        "inventory_baseline": INVENTORY_BASELINE,
        "candidate_tree": "HEAD",
        "path_set_sha256": _path_set_digest(EXPECTED_B1_ADDED_PATHS),
    }
    all_paths = (
        batch_b["paths"]
        + batch_c["paths"]
        + [item["path"] for item in later + post_note + b1_added]
    )
    assert len(all_paths) == len(set(all_paths)) == 81
    for path in all_paths:
        _assert_existing_relative_path(path)
    for item in later + post_note + b1_added:
        assert item["current_disposition"]
        assert item["deletion_authorized"] is False
    assert len(manifest["audit_time_working_set"]) == 20
    for path in manifest["audit_time_working_set"]:
        _assert_existing_relative_path(path)


def test_rebaseline_provenance_matches_baseline_and_candidate_git_trees() -> None:
    manifest = _load()["document_rebaseline"]
    baseline_paths = {
        item["path"]
        for item in (
            manifest["later_twenty_rebaseline"] + manifest["post_note_additions"]
        )
    }
    assert baseline_paths == EXPECTED_LATER_TWENTY_PATHS | EXPECTED_POST_NOTE_PATHS
    for path in baseline_paths:
        assert _git_object_exists(INVENTORY_BASELINE, path), path
    b1_paths = {item["path"] for item in manifest["b1_added_paths"]}
    assert b1_paths == EXPECTED_B1_ADDED_PATHS
    for path in b1_paths:
        assert not _git_object_exists(INVENTORY_BASELINE, path), path
        assert _git_object_exists("HEAD", path), path
        diff = subprocess.run(
            [
                "git",
                "diff",
                "--name-status",
                f"{INVENTORY_BASELINE}..HEAD",
                "--",
                path,
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
        assert diff.returncode == 0
        assert diff.stdout.strip() == f"A\t{path}"


def test_stage_runner_and_rebaseline_gaps_cannot_regress() -> None:
    entries = {entry["id"]: entry for entry in _load()["entries"]}
    runner_paths = set(entries["retired_s7_s8_runners"]["paths"])
    expected_s7_scripts = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "scripts" / "live_voice").glob("s7_*.py")
    }
    assert expected_s7_scripts.issubset(runner_paths)
    assert {
        "tests/unit_tests/live_voice/test_s7_alpha_verification.py",
        "tests/unit_tests/live_voice/test_s7_real_probes.py",
        "tests/unit_tests/live_voice/test_s8_readiness.py",
        "tests/integration/live_voice/test_s8_readiness_cli.py",
    }.issubset(runner_paths)
    assert (
        "jiuwenswarm/server/live_voice/product_p2_readiness.py"
        in entries["test_support_rehome"]["paths"]
    )
    assert (
        "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/"
        "productWebActivation.ts"
        in entries["duplicate_exact_object_validators"]["paths"]
    )
    assert (
        "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/"
        "productCompositionContract.ts"
        in entries["product_composition_contract_retained_boundary"]["paths"]
    )
