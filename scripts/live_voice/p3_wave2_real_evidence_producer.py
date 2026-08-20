# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Content-free producer for the private P3 Wave-2 real run.

The module imports no JiuwenSwarm module at import time.  Its closed CLI first
binds an already ACL-restricted private root, loads the two expected private
configuration basenames without inspecting them, and only then imports the
production registry, Agent, model, confirmation and composition owners.  The
fixed CLI owns the complete A1/A2/B1 sequence; callers cannot inject results.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import inspect
import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

try:
    from scripts.live_voice.p3_wave2_real_evidence_validator import (
        EvidenceValidationError,
        MAX_EVIDENCE_BYTES,
        observation_counts,
        validate_evidence_bytes,
    )
except ModuleNotFoundError as import_error:
    if import_error.name not in {"scripts", "scripts.live_voice"}:
        raise
    from p3_wave2_real_evidence_validator import (  # type: ignore[no-redef]
        EvidenceValidationError,
        MAX_EVIDENCE_BYTES,
        observation_counts,
        validate_evidence_bytes,
    )


class ClosedEvidenceFailure(RuntimeError):
    """A closed machine reason safe for stdout and reports."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ScenarioSummary:
    run_id: str
    source_sha256: str
    private_output_basename: str
    data_dir_basename: str
    database_basename: str
    project_basenames: tuple[str, str]
    task_refs: tuple[str, str, str]
    attempt_refs: tuple[str, str, str]
    profile_sha256: str
    requirements_sha256: str
    production_factory_used: bool
    production_registration_used: bool
    profile_persisted: bool
    requirements_persisted: bool
    two_projects_concurrent: bool
    a2_busy_queued: bool
    a2_zero_pre_release_effect: bool
    same_attempt_dequeued: bool
    adjustment_applied: bool
    cancel_a1_exact: bool
    cancel_b1_exact: bool
    reopen_matched: bool
    cleanup_complete: bool
    source_untouched: bool
    real_agent_observed: bool
    real_tool_observed: bool


class ObservationCollector:
    """Bounded synchronous observer; loss is recorded and later fails closed."""

    def __init__(self, *, capacity: int = 96) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 128:
            raise ValueError("capacity must be between 1 and 128")
        self._capacity = capacity
        self._observations: list[dict[str, object]] = []
        self._observer_failures = 0
        self._dropped_observations = 0
        self._lock = Lock()

    def __call__(self, observation: object) -> None:
        try:
            from jiuwenswarm.server.live_voice.project_code_executor import (
                DirectStreamObservation,
            )

            if type(observation) is not DirectStreamObservation:
                raise TypeError("observation type is not closed")
            closed = asdict(observation)
            with self._lock:
                if len(self._observations) >= self._capacity:
                    self._dropped_observations += 1
                    return
                self._observations.append(closed)
        except BaseException:  # noqa: BLE001 -- collection cannot affect execution
            with self._lock:
                self._observer_failures += 1

    def snapshot(self) -> tuple[list[dict[str, object]], int, int]:
        with self._lock:
            return (
                [dict(item) for item in self._observations],
                self._observer_failures,
                self._dropped_observations,
            )

    def record_observer_failures(self, count: int) -> None:
        if type(count) is not int or not 0 <= count <= 1_000_000:
            raise ClosedEvidenceFailure("EVIDENCE_OBSERVER_HEALTH_INVALID")
        with self._lock:
            self._observer_failures += count


def _checks(summary: ScenarioSummary) -> dict[str, bool]:
    return {
        name: bool(getattr(summary, name))
        for name in (
            "production_factory_used",
            "production_registration_used",
            "profile_persisted",
            "requirements_persisted",
            "two_projects_concurrent",
            "a2_busy_queued",
            "a2_zero_pre_release_effect",
            "same_attempt_dequeued",
            "adjustment_applied",
            "cancel_a1_exact",
            "cancel_b1_exact",
            "reopen_matched",
            "cleanup_complete",
            "source_untouched",
            "real_agent_observed",
            "real_tool_observed",
        )
    }


def _encode(document: dict[str, object]) -> bytes:
    try:
        return json.dumps(document, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClosedEvidenceFailure("EVIDENCE_JSON_INVALID") from exc


def build_evidence_document(
    summary: ScenarioSummary,
    collector: ObservationCollector,
) -> dict[str, object]:
    observations, observer_failures, dropped = collector.snapshot()
    counts = {
        **observation_counts(observations),
        "observer_failures": observer_failures,
        "dropped_observations": dropped,
    }
    document: dict[str, object] = {
        "schema_version": "live-voice.p3-wave2-real-evidence.v1",
        "source_sha256": summary.source_sha256,
        "run_id": summary.run_id,
        "private_output_basename": summary.private_output_basename,
        "environment": {
            "data_dir_basename": summary.data_dir_basename,
            "database_basename": summary.database_basename,
            "project_basenames": list(summary.project_basenames),
        },
        "bindings": {
            "task_refs": dict(zip(("A1", "A2", "B1"), summary.task_refs)),
            "attempt_refs": dict(zip(("A1", "A2", "B1"), summary.attempt_refs)),
            "profile_sha256": summary.profile_sha256,
            "requirements_sha256": summary.requirements_sha256,
        },
        "checks": _checks(summary),
        "counts": counts,
        "observations": observations,
    }
    encoded = _encode(document)
    if len(encoded) > MAX_EVIDENCE_BYTES:
        raise ClosedEvidenceFailure("EVIDENCE_TOO_LARGE")
    try:
        validate_evidence_bytes(encoded)
    except EvidenceValidationError as exc:
        raise ClosedEvidenceFailure(exc.reason) from None
    return document


def write_private_evidence(path: Path, document: dict[str, object]) -> None:
    if not path.is_absolute():
        raise ClosedEvidenceFailure("PRIVATE_OUTPUT_NOT_ABSOLUTE")
    encoded = _encode(document)
    if len(encoded) > MAX_EVIDENCE_BYTES:
        raise ClosedEvidenceFailure("EVIDENCE_TOO_LARGE")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ClosedEvidenceFailure("PRIVATE_OUTPUT_EXISTS") from exc
    except OSError as exc:
        raise ClosedEvidenceFailure("PRIVATE_OUTPUT_UNAVAILABLE") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise ClosedEvidenceFailure("PRIVATE_OUTPUT_WRITE_FAILED") from exc


def sanitized_aggregate_line(aggregate: dict[str, object]) -> str:
    expected = {
        "ok",
        "observation_count",
        "paired_file_tool_count",
        "write_edit_pair_count",
    }
    if set(aggregate) != expected or aggregate.get("ok") is not True:
        raise ClosedEvidenceFailure("EVIDENCE_AGGREGATE_INVALID")
    return json.dumps(aggregate, separators=(",", ":"), sort_keys=True) + "\n"


_IN_PROCESS_LIMIT_SECONDS = 12 * 60
_POLL_SECONDS = 0.25
_ROOT_ENVIRONMENT = {
    "JIUWENSWARM_DATA_DIR",
    "JIUWENSWARM_HOME",
    "JIUWENSWARM_CONFIG_DIR",
}


@dataclass(frozen=True, slots=True)
class _RegisteredScenario:
    run_id: str
    principal_id: str
    token: str
    database: Path
    projects: dict[str, object]
    project_paths: dict[str, Path]
    sessions: dict[str, str]


@dataclass(frozen=True, slots=True)
class _RealScenarioFacts:
    task_refs: tuple[str, str, str]
    attempt_refs: tuple[str, str, str]
    scopes: tuple[object, object, object]
    selections: tuple[object, object, object]
    two_projects_concurrent: bool
    a2_busy_queued: bool
    a2_zero_pre_release_effect: bool
    same_attempt_dequeued: bool
    adjustment_applied: bool
    cancel_a1_exact: bool
    cancel_b1_exact: bool
    real_agent_observed: bool
    real_tool_observed: bool


def _utc_text(value: datetime | None = None) -> str:
    current = value or datetime.now(UTC)
    return current.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _closed_basename(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 128
        and value[0].isalnum()
        and all(character.isalnum() or character in "._-" for character in value)
    )


def _validated_private_paths(
    private_root: Path,
    output_path: Path,
) -> tuple[Path, Path]:
    if not private_root.is_absolute():
        raise ClosedEvidenceFailure("PRIVATE_ROOT_NOT_ABSOLUTE")
    if not output_path.is_absolute():
        raise ClosedEvidenceFailure("PRIVATE_OUTPUT_NOT_ABSOLUTE")
    try:
        root = private_root.resolve(strict=True)
    except OSError as exc:
        raise ClosedEvidenceFailure("PRIVATE_ROOT_UNAVAILABLE") from exc
    if not root.is_dir() or not _closed_basename(root.name):
        raise ClosedEvidenceFailure("PRIVATE_ROOT_INVALID")
    output = output_path.resolve(strict=False)
    if not output.is_relative_to(root) or output.parent != root:
        raise ClosedEvidenceFailure("PRIVATE_OUTPUT_OUTSIDE_ROOT")
    if not _closed_basename(output.name):
        raise ClosedEvidenceFailure("PRIVATE_OUTPUT_BASENAME_INVALID")
    if output.exists():
        raise ClosedEvidenceFailure("PRIVATE_OUTPUT_EXISTS")
    config = root / "config" / "config.yaml"
    dotenv = root / ".env"
    if (
        config.name != "config.yaml"
        or dotenv.name != ".env"
        or not config.is_file()
        or not dotenv.is_file()
        or config.is_symlink()
        or dotenv.is_symlink()
    ):
        raise ClosedEvidenceFailure("PRIVATE_CONFIGURATION_UNAVAILABLE")
    return root, output


def _set_private_roots(private_root: Path) -> None:
    values = {
        "JIUWENSWARM_DATA_DIR": str(private_root),
        "JIUWENSWARM_HOME": str(private_root),
        "JIUWENSWARM_CONFIG_DIR": str(private_root / "config"),
    }
    for name in _ROOT_ENVIRONMENT:
        os.environ[name] = values[name]


def _load_private_configuration(private_root: Path) -> None:
    _set_private_roots(private_root)
    from jiuwenswarm.dotenv_early import load_dotenv_runtime

    load_dotenv_runtime(private_root / ".env", override=False)
    _set_private_roots(private_root)
    expected = {
        "JIUWENSWARM_DATA_DIR": private_root,
        "JIUWENSWARM_HOME": private_root,
        "JIUWENSWARM_CONFIG_DIR": private_root / "config",
    }
    if any(
        Path(os.environ[name]).resolve(strict=False) != value
        for name, value in expected.items()
    ):
        raise ClosedEvidenceFailure("PRIVATE_ROOT_BINDING_FAILED")


def _git(
    root: Path,
    *arguments: str,
    timeout: float = 20,
) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClosedEvidenceFailure("PRIVATE_GIT_UNAVAILABLE") from exc
    if completed.returncode != 0:
        raise ClosedEvidenceFailure("PRIVATE_GIT_OPERATION_FAILED")
    return completed.stdout


def _git_snapshot(root: Path) -> tuple[bytes, bytes]:
    return (
        _git(root, "rev-parse", "HEAD").strip(),
        _git(root, "status", "--porcelain=v1", "--untracked-files=all"),
    )


def _initialize_private_project(path: Path, *, title: str) -> None:
    try:
        path.mkdir()
        (path / "README.md").write_text(f"# {title}\n", encoding="utf-8")
    except OSError as exc:
        raise ClosedEvidenceFailure("PRIVATE_PROJECT_UNAVAILABLE") from exc
    _git(path, "init", "--initial-branch=main")
    _git(path, "config", "user.name", "Live Voice Evidence")
    _git(path, "config", "user.email", "live-voice-evidence@invalid")
    _git(path, "add", "--", "README.md")
    _git(path, "commit", "-m", "Initialize private evidence project")
    if _git(path, "remote") or _git_snapshot(path)[1]:
        raise ClosedEvidenceFailure("PRIVATE_PROJECT_INVALID")


def _successful_pair(
    collector: ObservationCollector,
    task_ref: str,
    *,
    stream_kind: str,
) -> bool:
    observations, _failures, _dropped = collector.snapshot()
    pending: dict[str, tuple[str, str]] = {}
    for observation in observations:
        if (
            observation.get("task_ref") != task_ref
            or observation.get("stream_kind") != stream_kind
        ):
            continue
        pair = (
            str(observation.get("tool_name_digest")),
            str(observation.get("file_tool_kind")),
        )
        call_id = str(observation.get("call_id_digest"))
        if observation.get("event_kind") == "tool_call":
            pending[call_id] = pair
        elif (
            pending.pop(call_id, None) == pair
            and observation.get("result_status") == "success"
            and pair[1] in {"write", "edit"}
        ):
            return True
    return False


async def _wait_stage(
    predicate: Callable[[], object],
    *,
    deadline: float,
    reason: str,
) -> None:
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if inspect.isawaitable(result):
                result = await result
            if result is True:
                return
        except ClosedEvidenceFailure:
            raise
        except BaseException:  # noqa: BLE001 -- private state never reaches output
            pass
        await asyncio.sleep(_POLL_SECONDS)
    raise ClosedEvidenceFailure(reason)


async def _await_before_deadline(awaitable: object, *, deadline: float):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
        raise ClosedEvidenceFailure("REAL_SCENARIO_DEADLINE_EXCEEDED")
    try:
        return await asyncio.wait_for(awaitable, timeout=remaining)
    except TimeoutError as exc:
        raise ClosedEvidenceFailure("REAL_SCENARIO_DEADLINE_EXCEEDED") from exc


async def _confirmed_mutation(
    *,
    composition: object,
    confirmation_owner: object,
    confirmation_forwarder: object,
    operation: str,
    params: dict[str, object],
    request_id: str,
    session_id: str,
    run_id: str,
    deadline: float,
) -> dict[str, object]:
    from jiuwenswarm.server.live_voice.p3_confirmation import (
        P3ConfirmationOwnerContext,
        TrustedP3ConfirmationIssue,
    )

    confirmation_id = hashlib.sha256(
        f"{run_id}:{request_id}:confirmation".encode("utf-8")
    ).hexdigest()
    forwarded = {**params, "confirmation_id": confirmation_id}
    prepared = await _await_before_deadline(
        composition.prepare_mutation_confirmation(
            operation=operation,
            params=forwarded,
            session_id=session_id,
        ),
        deadline=deadline,
    )
    owner_context = P3ConfirmationOwnerContext(
        session_id=session_id,
        correlation_id=prepared.correlation_id,
        owner_generation=1,
    )
    observed = datetime.fromisoformat(prepared.observed_at.replace("Z", "+00:00"))
    receipt = await _await_before_deadline(
        asyncio.to_thread(
            confirmation_owner.issue,
            TrustedP3ConfirmationIssue(
                binding=prepared.binding,
                owner=owner_context,
                expires_at=_utc_text(observed + timedelta(minutes=2)),
                confirmation_id=confirmation_id,
            ),
            now=prepared.observed_at,
        ),
        deadline=deadline,
    )
    validated = await _await_before_deadline(
        asyncio.to_thread(
            confirmation_owner.validate_for_forwarding,
            receipt.confirmation_id,
            prepared.binding,
            owner_context,
            now=prepared.observed_at,
        ),
        deadline=deadline,
    )
    with confirmation_forwarder.permit(validated):
        result = await _await_before_deadline(
            composition.handle(
                operation=operation,
                params={**forwarded, "confirmation_id": receipt.confirmation_id},
                request_id=request_id,
                session_id=session_id,
            ),
            deadline=deadline,
        )
    payload = getattr(result, "payload", None)
    routed = payload.get("result") if isinstance(payload, dict) else None
    if getattr(result, "ok", None) is not True or not isinstance(routed, dict):
        raise ClosedEvidenceFailure("REAL_MUTATION_REJECTED")
    return routed


def _create_params(
    scenario: _RegisteredScenario,
    *,
    label: str,
) -> dict[str, object]:
    issued_at = _utc_text()
    return {
        "auth_token": scenario.token,
        "session_id": scenario.sessions[label],
        "command_id": f"command-create-{label}-{scenario.run_id}",
        "issued_at": issued_at,
        "correlation_id": f"correlation-create-{label}-{scenario.run_id}",
        "name": "Three-day itinerary",
        "instruction": (
            "Create a concrete three-day itinerary in itinerary.md and keep "
            "the result ready for one bounded follow-up adjustment."
        ),
        "source": "structured",
    }


def _targeted_params(
    scenario: _RegisteredScenario,
    *,
    operation: str,
    label: str,
    task_id: str,
) -> dict[str, object]:
    command_kind = operation.rsplit(".", 1)[-1]
    params: dict[str, object] = {
        "auth_token": scenario.token,
        "session_id": scenario.sessions[label],
        "command_id": f"command-{command_kind}-{label}-{scenario.run_id}",
        "issued_at": _utc_text(),
        "correlation_id": f"correlation-{command_kind}-{label}-{scenario.run_id}",
        "task_id": task_id,
        "source": "structured",
    }
    if operation == "task.adjust":
        params["instruction"] = (
            "Move the museum visit to 09:30 and update only itinerary.md."
        )
    return params


def _created_refs(result: dict[str, object]) -> tuple[str, str]:
    task_id = result.get("task_id")
    attempt_id = result.get("attempt_id")
    if type(task_id) is not str or not task_id or type(attempt_id) is not str or not attempt_id:
        raise ClosedEvidenceFailure("REAL_CREATE_RESULT_INVALID")
    return task_id, attempt_id


async def _run_fixed_scenario(
    *,
    composition: object,
    confirmation_owner: object,
    confirmation_forwarder: object,
    agent_manager: object,
    agent_manager_type: type,
    scenario: _RegisteredScenario,
    collector: ObservationCollector,
    deadline: float,
) -> _RealScenarioFacts:
    from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
    from jiuwenswarm.server.live_voice.formal_task_models import (
        FormalAttemptState,
        FormalTaskState,
    )
    from jiuwenswarm.common.schema.live_voice_contract_v2 import TerminalOutcome

    store = composition._core.store
    scopes = {
        label: ScopeRef(
            scenario.principal_id,
            scenario.projects[label].project_id,
            scenario.sessions[label],
            Assurance.AUTHENTICATED,
        )
        for label in ("A1", "A2", "B1")
    }

    async def create(label: str) -> tuple[str, str]:
        result = await _confirmed_mutation(
            composition=composition,
            confirmation_owner=confirmation_owner,
            confirmation_forwarder=confirmation_forwarder,
            operation="task.create",
            params=_create_params(scenario, label=label),
            request_id=f"request-create-{label}-{scenario.run_id}",
            session_id=scenario.sessions[label],
            run_id=scenario.run_id,
            deadline=deadline,
        )
        return _created_refs(result)

    (task_a1, attempt_a1), (task_b1, attempt_b1) = await asyncio.gather(
        create("A1"), create("B1")
    )

    def a1_b1_ready() -> bool:
        records = (
            store.get_task(task_a1, scopes["A1"]),
            store.get_task(task_b1, scopes["B1"]),
        )
        attempts = (
            store.get_attempt(attempt_a1),
            store.get_attempt(attempt_b1),
        )
        return (
            all(record.state is FormalTaskState.RUNNING for record in records)
            and all(record.state is FormalAttemptState.RUNNING for record in attempts)
            and _successful_pair(collector, task_a1, stream_kind="initial")
            and _successful_pair(collector, task_b1, stream_kind="initial")
        )

    await _wait_stage(
        a1_b1_ready,
        deadline=deadline,
        reason="REAL_CONCURRENT_INITIAL_TIMEOUT",
    )
    formal_agents = getattr(agent_manager, "agents", {}).get(
        "live_voice_formal_task", {}
    )
    two_projects_concurrent = (
        type(agent_manager) is agent_manager_type
        and isinstance(formal_agents, dict)
        and len(formal_agents) >= 2
    )
    project_a_before_queue = _git_snapshot(scenario.project_paths["A1"])

    task_a2, attempt_a2 = await create("A2")

    def a2_busy() -> bool:
        admission = store.admission_projection(task_a2, scopes["A2"])
        return bool(
            admission is not None
            and admission.queued
            and admission.reason == "EXECUTOR_PROJECT_BUSY"
            and admission.attempt_count >= 1
            and admission.attempt_id == attempt_a2
            and admission.priority.value == "normal"
            and not admission.reconciliation_required
        )

    await _wait_stage(
        a2_busy,
        deadline=deadline,
        reason="REAL_A2_BUSY_TIMEOUT",
    )
    observations_before_release, failures_before_release, dropped_before_release = (
        collector.snapshot()
    )
    a2_zero_pre_release_effect = (
        not any(item.get("task_ref") == task_a2 for item in observations_before_release)
        and failures_before_release == 0
        and dropped_before_release == 0
        and _git_snapshot(scenario.project_paths["A1"])
        == project_a_before_queue
    )

    await _confirmed_mutation(
        composition=composition,
        confirmation_owner=confirmation_owner,
        confirmation_forwarder=confirmation_forwarder,
        operation="task.cancel",
        params=_targeted_params(
            scenario,
            operation="task.cancel",
            label="A1",
            task_id=task_a1,
        ),
        request_id=f"request-cancel-A1-{scenario.run_id}",
        session_id=scenario.sessions["A1"],
        run_id=scenario.run_id,
        deadline=deadline,
    )

    def a1_cancelled_a2_running() -> bool:
        first = store.get_task(task_a1, scopes["A1"])
        second = store.get_task(task_a2, scopes["A2"])
        return (
            first.state is FormalTaskState.TERMINAL
            and first.outcome is TerminalOutcome.CANCELLED
            and first.cancel_requested
            and second.state is FormalTaskState.RUNNING
            and second.attempt_id == attempt_a2
            and store.get_attempt(attempt_a2).state is FormalAttemptState.RUNNING
        )

    await _wait_stage(
        a1_cancelled_a2_running,
        deadline=deadline,
        reason="REAL_A1_CANCEL_A2_DEQUEUE_TIMEOUT",
    )

    await _wait_stage(
        lambda: _successful_pair(collector, task_a2, stream_kind="initial"),
        deadline=deadline,
        reason="REAL_A2_INITIAL_TOOL_TIMEOUT",
    )
    formal_agents_after_dequeue = getattr(agent_manager, "agents", {}).get(
        "live_voice_formal_task", {}
    )
    real_agent_observed = (
        two_projects_concurrent
        and isinstance(formal_agents_after_dequeue, dict)
        and len(formal_agents_after_dequeue) >= 2
    )

    await _confirmed_mutation(
        composition=composition,
        confirmation_owner=confirmation_owner,
        confirmation_forwarder=confirmation_forwarder,
        operation="task.adjust",
        params=_targeted_params(
            scenario,
            operation="task.adjust",
            label="A2",
            task_id=task_a2,
        ),
        request_id=f"request-adjust-A2-{scenario.run_id}",
        session_id=scenario.sessions["A2"],
        run_id=scenario.run_id,
        deadline=deadline,
    )

    def a2_adjusted() -> bool:
        task = store.get_task(task_a2, scopes["A2"])
        events = store.events(task_a2, scopes["A2"], attempt_id=attempt_a2)
        return (
            task.state is FormalTaskState.TERMINAL
            and task.outcome is TerminalOutcome.COMPLETED
            and any(event.event_type == "task.adjust_applied" for event in events)
            and _successful_pair(collector, task_a2, stream_kind="adjustment")
            and (scenario.project_paths["A2"] / "itinerary.md").is_file()
        )

    await _wait_stage(
        a2_adjusted,
        deadline=deadline,
        reason="REAL_A2_ADJUST_TIMEOUT",
    )

    await _confirmed_mutation(
        composition=composition,
        confirmation_owner=confirmation_owner,
        confirmation_forwarder=confirmation_forwarder,
        operation="task.cancel",
        params=_targeted_params(
            scenario,
            operation="task.cancel",
            label="B1",
            task_id=task_b1,
        ),
        request_id=f"request-cancel-B1-{scenario.run_id}",
        session_id=scenario.sessions["B1"],
        run_id=scenario.run_id,
        deadline=deadline,
    )

    await _wait_stage(
        lambda: (
            store.get_task(task_b1, scopes["B1"]).state
            is FormalTaskState.TERMINAL
            and store.get_task(task_b1, scopes["B1"]).outcome
            is TerminalOutcome.CANCELLED
            and store.get_task(task_b1, scopes["B1"]).cancel_requested
        ),
        deadline=deadline,
        reason="REAL_B1_CANCEL_TIMEOUT",
    )
    records = tuple(
        store.get_task(task_id, scope)
        for task_id, scope in zip(
            (task_a1, task_a2, task_b1),
            (scopes["A1"], scopes["A2"], scopes["B1"]),
        )
    )
    attempts = tuple(store.get_attempt(record.attempt_id) for record in records)
    return _RealScenarioFacts(
        task_refs=(task_a1, task_a2, task_b1),
        attempt_refs=(attempt_a1, attempt_a2, attempt_b1),
        scopes=(scopes["A1"], scopes["A2"], scopes["B1"]),
        selections=tuple(attempt.selection for attempt in attempts),
        two_projects_concurrent=two_projects_concurrent,
        a2_busy_queued=True,
        a2_zero_pre_release_effect=a2_zero_pre_release_effect,
        same_attempt_dequeued=records[1].attempt_id == attempt_a2,
        adjustment_applied=True,
        cancel_a1_exact=(
            records[0].attempt_id == attempt_a1
            and records[0].outcome is TerminalOutcome.CANCELLED
        ),
        cancel_b1_exact=(
            records[2].attempt_id == attempt_b1
            and records[2].outcome is TerminalOutcome.CANCELLED
        ),
        real_agent_observed=real_agent_observed,
        real_tool_observed=(
            _successful_pair(collector, task_a1, stream_kind="initial")
            and _successful_pair(collector, task_b1, stream_kind="initial")
            and _successful_pair(collector, task_a2, stream_kind="initial")
            and _successful_pair(collector, task_a2, stream_kind="adjustment")
        ),
    )


def _register_private_scenario(private_root: Path) -> _RegisteredScenario:
    from jiuwenswarm.server.runtime.session.project_store import (
        create_or_restore_project,
    )
    from jiuwenswarm.server.runtime.session.session_metadata import (
        init_session_metadata,
    )

    run_id = secrets.token_hex(8)
    projects_root = private_root / "projects"
    try:
        projects_root.mkdir()
    except OSError as exc:
        raise ClosedEvidenceFailure("PRIVATE_PROJECT_UNAVAILABLE") from exc
    paths = {
        "A1": projects_root / f"wave2-project-a-{run_id}",
        "A2": projects_root / f"wave2-project-a-{run_id}",
        "B1": projects_root / f"wave2-project-b-{run_id}",
    }
    _initialize_private_project(paths["A1"], title="Wave 2 Project A")
    _initialize_private_project(paths["B1"], title="Wave 2 Project B")
    try:
        project_a, restored_a = create_or_restore_project(
            f"wave2-project-a-{run_id}", str(paths["A1"]), work_mode="code"
        )
        project_b, restored_b = create_or_restore_project(
            f"wave2-project-b-{run_id}", str(paths["B1"]), work_mode="code"
        )
    except BaseException as exc:  # noqa: BLE001 -- registry detail stays private
        raise ClosedEvidenceFailure("PRODUCTION_REGISTRATION_FAILED") from exc
    if restored_a or restored_b:
        raise ClosedEvidenceFailure("PRODUCTION_REGISTRATION_REUSED")
    principal_id = f"wave2-principal-{run_id}"
    sessions = {label: f"wave2-{label}-{run_id}" for label in ("A1", "A2", "B1")}
    for label in ("A1", "A2", "B1"):
        project = project_b if label == "B1" else project_a
        init_session_metadata(
            session_id=sessions[label],
            channel_id="web",
            user_id=principal_id,
            mode="code",
            project_dir=str(paths[label]),
            project_id=project.project_id,
            work_mode="code",
        )
    return _RegisteredScenario(
        run_id=run_id,
        principal_id=principal_id,
        token=secrets.token_urlsafe(48),
        database=private_root / "p3-wave2.sqlite3",
        projects={"A1": project_a, "A2": project_a, "B1": project_b},
        project_paths=paths,
        sessions=sessions,
    )


def _configure_product_environment(scenario: _RegisteredScenario) -> None:
    project_ids = {
        scenario.projects[label].project_id for label in ("A1", "A2", "B1")
    }
    values = {
        "JIUWENSWARM_LIVE_VOICE_P3_ENABLED": "1",
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN": scenario.token,
        "JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID": scenario.principal_id,
        "JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS": ",".join(sorted(project_ids)),
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT": _utc_text(
            datetime.now(UTC) + timedelta(minutes=20)
        ),
        "JIUWENSWARM_LIVE_VOICE_P3_DATABASE": str(scenario.database),
        "JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS": "0.25",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED": "1",
        "JIUWENSWARM_LIVE_VOICE_DEMO_ADJUSTMENT_CHECKPOINT_ENABLED": "1",
    }
    os.environ.update(values)


async def _run_production_cli(
    private_root: Path,
    output_path: Path,
) -> dict[str, object]:
    source_root = Path(__file__).resolve().parents[2]
    if private_root.is_relative_to(source_root) or source_root.is_relative_to(
        private_root
    ):
        raise ClosedEvidenceFailure("PRIVATE_ROOT_SOURCE_OVERLAP")
    source_before = _git_snapshot(source_root)
    _load_private_configuration(private_root)

    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
    from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
        create_p3_composition_from_environment,
    )
    from jiuwenswarm.server.live_voice.p3_confirmation import (
        BoundedP3ConfirmationOwner,
    )
    from jiuwenswarm.server.live_voice.p3_model_resolution import (
        ServerModelCatalogResolver,
    )
    from jiuwenswarm.server.live_voice.p3_product_confirmation import (
        ProductP3ConfirmationForwarder,
    )
    from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
    from jiuwenswarm.server.runtime.agent_manager import AgentManager

    scenario = _register_private_scenario(private_root)
    _configure_product_environment(scenario)
    collector = ObservationCollector(capacity=96)
    manager = AgentManager()
    model_resolver = ServerModelCatalogResolver(
        catalog_reader=AgentWebSocketServer._live_voice_p3_model_catalog,
        model_builder=AgentWebSocketServer._build_live_voice_p3_model,
    )
    owner = BoundedP3ConfirmationOwner(
        private_root / "p3-wave2-confirmations.sqlite3",
        enabled=True,
    )
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = create_p3_composition_from_environment(
        agent_manager=manager,
        model_resolver=model_resolver,
        confirmation_verifier=forwarder,
        stream_observer=collector,
    )
    if composition is None:
        raise ClosedEvidenceFailure("PRODUCT_FACTORY_DISABLED")
    executor = composition._core.executor
    health_before = getattr(executor, "stream_observer_failure_count", None)
    if type(health_before) is not int or health_before < 0:
        raise ClosedEvidenceFailure("EVIDENCE_OBSERVER_HEALTH_INVALID")
    facts: _RealScenarioFacts | None = None
    primary: BaseException | None = None
    deadline = time.monotonic() + _IN_PROCESS_LIMIT_SECONDS
    try:
        await _await_before_deadline(composition.start(), deadline=deadline)
        facts = await _run_fixed_scenario(
            composition=composition,
            confirmation_owner=owner,
            confirmation_forwarder=forwarder,
            agent_manager=manager,
            agent_manager_type=AgentManager,
            scenario=scenario,
            collector=collector,
            deadline=deadline,
        )
    except BaseException as exc:  # noqa: BLE001 -- cleanup still owns every resource
        primary = exc
    try:
        await composition.stop()
    except BaseException as exc:  # noqa: BLE001 -- cleanup failure is closed
        raise ClosedEvidenceFailure("REAL_SCENARIO_CLEANUP_FAILED") from exc
    if primary is not None:
        if isinstance(primary, ClosedEvidenceFailure):
            raise primary
        raise ClosedEvidenceFailure("REAL_SCENARIO_FAILED") from primary
    assert facts is not None
    health_after = getattr(executor, "stream_observer_failure_count", None)
    if (
        type(health_after) is not int
        or health_after < health_before
        or health_after > 1_000_000
    ):
        raise ClosedEvidenceFailure("EVIDENCE_OBSERVER_HEALTH_INVALID")
    collector.record_observer_failures(health_after - health_before)

    reopened = SqliteTaskStore(scenario.database)
    reopened_tasks = tuple(
        reopened.get_task(task_id, scope)
        for task_id, scope in zip(facts.task_refs, facts.scopes)
    )
    reopened_attempts = tuple(
        reopened.get_attempt(task.attempt_id) for task in reopened_tasks
    )
    a2_result_availability, a2_result, _a2_result_reason = reopened.task_result(
        facts.task_refs[1], facts.scopes[1]
    )
    reopened_a2_events = reopened.events(
        facts.task_refs[1],
        facts.scopes[1],
        attempt_id=facts.attempt_refs[1],
    )
    reopened_selections = tuple(attempt.selection for attempt in reopened_attempts)
    if any(selection is None for selection in reopened_selections):
        raise ClosedEvidenceFailure("EVIDENCE_SELECTION_UNAVAILABLE")
    first_selection = reopened_selections[0]
    profile_sha256 = "sha256:" + first_selection.capability_profile_digest
    requirements_sha256 = "sha256:" + hashlib.sha256(
        first_selection.execution_requirements_json
    ).hexdigest()
    profile_persisted = (
        reopened_selections == facts.selections
        and all(
            selection.capability_profile_digest
            == first_selection.capability_profile_digest
            for selection in reopened_selections
        )
    )
    requirements_persisted = all(
        selection.execution_requirements_json
        == first_selection.execution_requirements_json
        for selection in reopened_selections
    )
    cleanup_complete = (
        not executor.has_live_workers
        and not getattr(manager, "agents", {}).get("live_voice_formal_task")
    )
    source_after = _git_snapshot(source_root)
    source_untouched = source_after == source_before
    source_sha256 = "sha256:" + hashlib.sha256(source_before[0]).hexdigest()
    summary = ScenarioSummary(
        run_id=f"wave2-run-{scenario.run_id}",
        source_sha256=source_sha256,
        private_output_basename=output_path.name,
        data_dir_basename=private_root.name,
        database_basename=scenario.database.name,
        project_basenames=(
            scenario.project_paths["A1"].name,
            scenario.project_paths["B1"].name,
        ),
        task_refs=facts.task_refs,
        attempt_refs=facts.attempt_refs,
        profile_sha256=profile_sha256,
        requirements_sha256=requirements_sha256,
        production_factory_used=True,
        production_registration_used=True,
        profile_persisted=profile_persisted,
        requirements_persisted=requirements_persisted,
        two_projects_concurrent=facts.two_projects_concurrent,
        a2_busy_queued=facts.a2_busy_queued,
        a2_zero_pre_release_effect=facts.a2_zero_pre_release_effect,
        same_attempt_dequeued=facts.same_attempt_dequeued,
        adjustment_applied=facts.adjustment_applied,
        cancel_a1_exact=facts.cancel_a1_exact,
        cancel_b1_exact=facts.cancel_b1_exact,
        reopen_matched=(
            tuple(task.attempt_id for task in reopened_tasks) == facts.attempt_refs
            and all(
                attempt.attempt_id == expected
                for attempt, expected in zip(reopened_attempts, facts.attempt_refs)
            )
            and tuple(task.state.value for task in reopened_tasks)
            == ("terminal", "terminal", "terminal")
            and tuple(task.outcome.value for task in reopened_tasks)
            == ("cancelled", "completed", "cancelled")
            and a2_result_availability.value == "available"
            and a2_result is not None
            and a2_result.attempt_id == facts.attempt_refs[1]
            and any(
                event.event_type == "task.adjust_applied"
                for event in reopened_a2_events
            )
        ),
        cleanup_complete=cleanup_complete,
        source_untouched=source_untouched,
        real_agent_observed=facts.real_agent_observed,
        real_tool_observed=facts.real_tool_observed,
    )
    document = build_evidence_document(summary, collector)
    write_private_evidence(output_path, document)
    return validate_evidence_bytes(_encode(document))


def emit_sanitized_result(
    aggregate: dict[str, object] | None,
    failure: ClosedEvidenceFailure | None = None,
) -> None:
    if failure is not None:
        sys.stdout.write(
            json.dumps(
                {"ok": False, "reason": failure.reason},
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        return
    if aggregate is None:
        raise ClosedEvidenceFailure("EVIDENCE_AGGREGATE_INVALID")
    sys.stdout.write(sanitized_aggregate_line(aggregate))


def _cli_paths(argv: list[str]) -> tuple[Path, Path]:
    if (
        len(argv) != 4
        or argv[0] != "--private-root"
        or argv[2] != "--output"
    ):
        raise ClosedEvidenceFailure("PRIVATE_CLI_INVALID")
    return _validated_private_paths(Path(argv[1]), Path(argv[3]))


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        private_root, output_path = _cli_paths(arguments)
        with open(os.devnull, "w", encoding="utf-8") as quiet:
            with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                aggregate = asyncio.run(
                    _run_production_cli(private_root, output_path)
                )
    except ClosedEvidenceFailure as exc:
        emit_sanitized_result(None, exc)
        return 2
    except BaseException:  # noqa: BLE001 -- never render private runtime details
        emit_sanitized_result(
            None,
            ClosedEvidenceFailure("REAL_PRODUCER_FAILED"),
        )
        return 2
    try:
        emit_sanitized_result(aggregate)
    except ClosedEvidenceFailure as exc:
        emit_sanitized_result(None, exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
