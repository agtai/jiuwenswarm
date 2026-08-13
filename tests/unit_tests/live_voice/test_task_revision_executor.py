# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CommandEnvelope,
    ErrorCode,
    OriginRef,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskSpec,
    FormalTaskViolation,
    OutboxKind,
    OutboxState,
    PersistentOutboxItem,
    ResolvedTaskContext,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    FORMAL_PROJECT_EXECUTOR_ID,
    ProjectExecutionBinding,
    _git_head,
    _project_content_fingerprint,
    _project_tree_fingerprint,
)
from jiuwenswarm.server.live_voice.task_revision import (
    RevisionFenceRequest,
    TaskRevisionCommand,
    TaskRevisionConstraints,
    TaskRevisionGrant,
    TaskRevisionOperation,
    TaskRevisionVerifierState,
)
from jiuwenswarm.server.live_voice.task_revision_executor import (
    S8_5_FIXTURE_MARKER,
    S8_5_FIXTURE_PROFILE,
    TaskRevisionExecutionCoordinator,
    TaskRevisionFixtureVerifier,
    TrustedRevisionFixtureManifest,
    TrustedRevisionFixtureRegistry,
    TrustedVerifierCommand,
)
from jiuwenswarm.server.live_voice.task_revision_store import (
    SqliteTaskRevisionStore,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _fixture(tmp_path: Path) -> tuple[Path, TrustedRevisionFixtureManifest]:
    parent = tmp_path / "fixtures"
    root = parent / "fixture-a"
    root.mkdir(parents=True)
    _git(root, "init")
    _git(root, "config", "user.name", "S8.5 Test")
    _git(root, "config", "user.email", "s8-5@example.invalid")
    (root / "src").mkdir()
    (root / "src" / "base.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / "public.py").write_text("API = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    marker = (
        b'{"fixture_id":"fixture-a","profile":"' + S8_5_FIXTURE_PROFILE.encode() + b'"}'
    )
    (root / S8_5_FIXTURE_MARKER).write_bytes(marker)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture baseline")
    manifest = TrustedRevisionFixtureManifest(
        fixture_id="fixture-a",
        project_id="project-1",
        fixture_parent=str(parent.resolve()),
        project_root=str(root.resolve()),
        baseline_head=_git_head(root),
        baseline_tree=_project_tree_fingerprint(root),
        baseline_content=_project_content_fingerprint(root),
        write_scope=("src",),
        immutable_paths=("src/public.py",),
        verifier_id="python-check",
    )
    manifest.require_original_clean_base()
    return root, manifest


def _scope() -> ScopeRef:
    return ScopeRef("user-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def _spec(root: Path) -> FormalTaskSpec:
    return FormalTaskSpec(
        name="S8.5 fixture task",
        instruction="Make one bounded fixture change.",
        origin=OriginRef("structured", None, None),
        context=ResolvedTaskContext(
            source="gateway.project_registry",
            stable_id="project-1",
            uri=root.resolve().as_uri(),
            revision_kind="version",
            revision_value="fixture-baseline",
            scope=_scope(),
            permissions=("task.execute", "project.write"),
            expires_at="2026-08-13T15:00:00Z",
            redaction_policy_id="live_voice.project.v1",
        ),
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        required_capabilities=("task.create",),
        side_effect_class="project_mutation",
        attributes=(
            ("model_config_version", "catalog-v1"),
            ("model_identity", "default#0"),
        ),
    )


def _item(root: Path, *, attempt_id: str = "attempt-1") -> PersistentOutboxItem:
    return PersistentOutboxItem(
        outbox_id=f"outbox-{attempt_id}",
        kind=OutboxKind.ATTEMPT_DISPATCH,
        task_id="task-1",
        attempt_id=attempt_id,
        command_id="command-1",
        scope=_scope(),
        spec=_spec(root),
        executor_ref=None,
        source_seq=-1,
        state=OutboxState.CLAIMED,
        delivery_count=1,
    )


class _Resolver:
    def __init__(self, binding: ProjectExecutionBinding) -> None:
        self.binding = binding

    async def resolve(self, _spec: FormalTaskSpec, *, for_dispatch: bool):
        assert for_dispatch
        return self.binding


class _AttemptExecutor:
    def __init__(self, behavior: str) -> None:
        self.behavior = behavior
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancel_signals = 0
        self.checkout: Path | None = None

    async def process_background_code_task_stream(self, request):
        self.checkout = Path(request.params["project_dir"])
        self.started.set()
        if self.behavior in {"wait", "noncooperative"}:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancel_signals += 1
                if self.behavior == "noncooperative":
                    await self.release.wait()
                else:
                    raise
        (self.checkout / "src" / "result.py").write_text(
            "RESULT = 2\n", encoding="utf-8"
        )
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={"event_type": "chat.final", "content": "done"},
            is_complete=True,
        )


async def _dispatching_adapter(
    tmp_path: Path,
    root: Path,
    executor: _AttemptExecutor,
    *,
    timeout: float = 1.0,
    item: PersistentOutboxItem | None = None,
) -> DirectProjectCodeExecutorAdapter:
    async def dispatch_fence() -> None:
        return None

    binding = ProjectExecutionBinding(
        service=None,
        execution_agent=object(),
        project_executor=executor,
        effective_execution_root=str(root.resolve()),
        execution_target={
            "project_dir": str(root.resolve()),
            "project_id": "project-1",
            "origin_session_id": "session-1",
            "origin_channel_id": "web",
        },
        owner_scope={
            "channel_id": "formal-task-core",
            "session_id": "session-1",
            "app_id": "live-voice",
        },
        resolved_revision_kind="version",
        resolved_revision_value="fixture-baseline",
        model_identity="default#0",
        model_config_version="catalog-v1",
        dispatch_fence=dispatch_fence,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),  # type: ignore[arg-type]
        tmp_path / "executor.sqlite3",
        cancel_timeout=timeout,
    )
    await adapter.dispatch(item or _item(root))
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    return adapter


def _fence_request() -> RevisionFenceRequest:
    return RevisionFenceRequest("revision-1", "task-1", 1, "attempt-1")


async def _fence(
    adapter: DirectProjectCodeExecutorAdapter,
    manifest: TrustedRevisionFixtureManifest,
):
    return await adapter.fence_revision(
        _fence_request(),
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        executor_ref="d0-project:attempt-1",
        expected_project_root=manifest.project_root,
        expected_before_head=manifest.baseline_head,
        expected_before_tree=manifest.baseline_tree,
        expected_before_content=manifest.baseline_content,
        checkout_identity=manifest.checkout_identity,
    )


@pytest.mark.asyncio
async def test_revision_fence_discards_running_predecessor_and_acks_exact_base(
    tmp_path: Path,
) -> None:
    root, manifest = _fixture(tmp_path)
    executor = _AttemptExecutor("wait")
    adapter = await _dispatching_adapter(tmp_path, root, executor)

    ack = await _fence(adapter, manifest)

    assert ack.checkout_identity == manifest.checkout_identity
    assert ack.unapplied_changes_discarded is True
    assert ack.cleanup_id.startswith("revision-cleanup-")
    assert not (root / "src" / "result.py").exists()
    assert executor.checkout is not None and not executor.checkout.exists()
    record = adapter._journal.get("attempt-1")
    assert record is not None
    assert record.outcome is TerminalOutcome.INTERRUPTED
    assert record.error == "TASK_REVISION_PREDECESSOR_FENCED"
    await adapter.close()


@pytest.mark.asyncio
async def test_revision_fence_never_acks_noncooperative_live_worker(
    tmp_path: Path,
) -> None:
    root, manifest = _fixture(tmp_path)
    executor = _AttemptExecutor("noncooperative")
    adapter = await _dispatching_adapter(tmp_path, root, executor, timeout=0.01)

    with pytest.raises(FormalTaskViolation) as pending:
        await _fence(adapter, manifest)
    assert pending.value.reason == "TASK_REVISION_FENCE_PENDING"
    assert pending.value.code is ErrorCode.UNAVAILABLE
    assert adapter.has_live_workers
    assert not (root / "src" / "result.py").exists()

    executor.release.set()
    for _ in range(200):
        if not adapter.has_live_workers:
            break
        await asyncio.sleep(0.01)
    ack = await _fence(adapter, manifest)
    assert ack.unapplied_changes_discarded is True
    assert not (root / "src" / "result.py").exists()
    assert executor.checkout is not None and not executor.checkout.exists()
    await adapter.close()


@pytest.mark.asyncio
async def test_revision_fence_rejects_attempt_that_already_applied(
    tmp_path: Path,
) -> None:
    root, manifest = _fixture(tmp_path)
    executor = _AttemptExecutor("success")
    adapter = await _dispatching_adapter(tmp_path, root, executor)
    for _ in range(200):
        if not adapter.has_live_workers:
            break
        await asyncio.sleep(0.01)

    with pytest.raises(FormalTaskViolation) as unknown:
        await _fence(adapter, manifest)

    assert unknown.value.reason == "TASK_REVISION_PREDECESSOR_RESULT_UNKNOWN"
    assert unknown.value.code is ErrorCode.RESULT_UNKNOWN
    assert (root / "src" / "result.py").exists()
    await adapter.close()


def test_fixture_manifest_rejects_dirty_remote_and_unmarked_targets(
    tmp_path: Path,
) -> None:
    root, manifest = _fixture(tmp_path)
    (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(FormalTaskViolation) as dirty:
        manifest.require_original_clean_base()
    assert dirty.value.reason == "TASK_REVISION_DIRTY_FIXTURE_FORBIDDEN"
    (root / "dirty.txt").unlink()

    (root / "ignored").mkdir()
    (root / "ignored" / "hidden.txt").write_text("hidden\n", encoding="utf-8")
    with pytest.raises(FormalTaskViolation) as ignored:
        manifest.require_original_clean_base()
    assert (
        ignored.value.reason
        == "TASK_REVISION_IGNORED_FIXTURE_CONTENT_FORBIDDEN"
    )
    (root / "ignored" / "hidden.txt").unlink()
    (root / "ignored").rmdir()

    _git(root, "remote", "add", "origin", "https://example.invalid/repo.git")
    with pytest.raises(FormalTaskViolation) as remote:
        manifest.require_original_clean_base()
    assert remote.value.reason == "TASK_REVISION_REMOTE_FIXTURE_FORBIDDEN"
    _git(root, "remote", "remove", "origin")

    (root / S8_5_FIXTURE_MARKER).write_text("wrong", encoding="utf-8")
    with pytest.raises(FormalTaskViolation) as marker:
        manifest.require_original_clean_base()
    assert marker.value.reason == "TASK_REVISION_FIXTURE_MARKER_MISMATCH"


def _delivery(item: PersistentOutboxItem) -> ExecutorDeliveryResult:
    executor_ref = f"d0-project:{item.attempt_id}"
    return ExecutorDeliveryResult(
        executor_ref,
        (
            ExecutorObservation(
                ExecutorResolution.KNOWN,
                FORMAL_PROJECT_EXECUTOR_ID,
                executor_ref,
                item.task_id,
                item.attempt_id,
                "event-terminal",
                2,
                FormalAttemptState.TERMINAL,
                TerminalOutcome.COMPLETED,
                "2026-08-13T10:00:00Z",
                "completed",
                "done",
                None,
            ),
        ),
    )


def _registry(
    manifest: TrustedRevisionFixtureManifest,
    *,
    argv: tuple[str, ...],
    timeout: float = 2.0,
) -> TrustedRevisionFixtureRegistry:
    return TrustedRevisionFixtureRegistry(
        (manifest,),
        (TrustedVerifierCommand("python-check", argv, timeout),),
    )


@pytest.mark.asyncio
async def test_trusted_verifier_reports_bound_success_and_sanitizes_output(
    tmp_path: Path,
) -> None:
    root, manifest = _fixture(tmp_path)
    result = root / "src" / "result.py"
    result.write_text("RESULT = 2\n", encoding="utf-8")
    command = (
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "assert Path('src/result.py').read_text() == 'RESULT = 2\\n'; "
            "print(str(Path.cwd())); print('api_key=private-value')"
        ),
    )
    verifier = TaskRevisionFixtureVerifier(
        _registry(manifest, argv=command), cleanup_proof=lambda *_args: True
    )
    item = _item(root, attempt_id="attempt-2")

    ack = await verifier.verify(
        item=item,
        delivery=_delivery(item),
        task_revision=2,
        constraints=TaskRevisionConstraints(
            ("src",), regression_verifier_required=True
        ),
    )

    assert ack.execution_ack is True
    assert ack.changed_paths == ("src/result.py",)
    assert ack.forbidden_side_effect_count == 0
    assert ack.verifier.result is TaskRevisionVerifierState.PASSED
    assert ack.verified_success is True
    assert str(root) not in ack.verifier.output_summary
    assert "private-value" not in ack.verifier.output_summary
    assert "<fixture>" in ack.verifier.output_summary
    assert "api_key=<redacted>" in ack.verifier.output_summary


@pytest.mark.asyncio
async def test_verifier_never_infers_success_while_executor_cleanup_is_unknown(
    tmp_path: Path,
) -> None:
    root, manifest = _fixture(tmp_path)
    (root / "src" / "result.py").write_text("RESULT = 2\n", encoding="utf-8")
    verifier = TaskRevisionFixtureVerifier(
        _registry(manifest, argv=(sys.executable, "-c", "raise SystemExit(0)")),
        cleanup_proof=lambda *_args: False,
    )
    item = _item(root, attempt_id="attempt-2")

    with pytest.raises(FormalTaskViolation) as unknown:
        await verifier.verify(
            item=item,
            delivery=_delivery(item),
            task_revision=2,
            constraints=TaskRevisionConstraints(("src",)),
        )

    assert unknown.value.reason == "TASK_REVISION_SUCCESSOR_CLEANUP_UNKNOWN"
    assert unknown.value.code is ErrorCode.RESULT_UNKNOWN


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected"),
    [("fail", "failed"), ("timeout", "timeout"), ("mutate", "mutated_fixture")],
)
async def test_trusted_verifier_fail_timeout_and_mutation_never_report_success(
    tmp_path: Path, mode: str, expected: str
) -> None:
    root, manifest = _fixture(tmp_path)
    (root / "src" / "result.py").write_text("RESULT = 2\n", encoding="utf-8")
    scripts = {
        "fail": "raise SystemExit(7)",
        "timeout": "import time; time.sleep(1)",
        "mutate": "from pathlib import Path; Path('src/verifier.py').write_text('x')",
    }
    verifier = TaskRevisionFixtureVerifier(
        _registry(
            manifest,
            argv=(sys.executable, "-c", scripts[mode]),
            timeout=0.01 if mode == "timeout" else 2.0,
        ),
        cleanup_proof=lambda *_args: True,
    )
    item = _item(root, attempt_id="attempt-2")

    ack = await verifier.verify(
        item=item,
        delivery=_delivery(item),
        task_revision=2,
        constraints=TaskRevisionConstraints(
            ("src",), regression_verifier_required=True
        ),
    )

    assert ack.verifier.result is TaskRevisionVerifierState(expected)
    assert ack.verified_success is False
    assert ack.forbidden_side_effect_count == int(mode == "mutate")


@pytest.mark.asyncio
async def test_forbidden_path_blocks_verifier_and_commit_or_remote_is_rejected(
    tmp_path: Path,
) -> None:
    root, manifest = _fixture(tmp_path)
    (root / "requirements.txt").write_text("unsafe==1\n", encoding="utf-8")
    verifier = TaskRevisionFixtureVerifier(
        _registry(manifest, argv=(sys.executable, "-c", "raise SystemExit(99)")),
        cleanup_proof=lambda *_args: True,
    )
    item = _item(root, attempt_id="attempt-2")

    ack = await verifier.verify(
        item=item,
        delivery=_delivery(item),
        task_revision=2,
        constraints=TaskRevisionConstraints(
            ("src",), regression_verifier_required=True
        ),
    )
    assert ack.verifier.result is TaskRevisionVerifierState.NOT_RUN
    assert ack.forbidden_side_effect_count == 1
    assert ack.verified_success is False

    (root / "requirements.txt").unlink()
    (root / "src" / "result.py").write_text("RESULT = 2\n", encoding="utf-8")
    _git(root, "add", "src/result.py")
    _git(root, "commit", "-m", "forbidden successor commit")
    with pytest.raises(FormalTaskViolation) as committed:
        await verifier.verify(
            item=item,
            delivery=_delivery(item),
            task_revision=2,
            constraints=TaskRevisionConstraints(
                ("src",), regression_verifier_required=True
            ),
        )
    assert committed.value.reason == "TASK_REVISION_FORBIDDEN_GIT_MUTATION"


def test_registry_rejects_missing_or_shell_verifier(tmp_path: Path) -> None:
    _root, manifest = _fixture(tmp_path)
    with pytest.raises(ValueError, match="registered verifier"):
        TrustedRevisionFixtureRegistry((manifest,), ())
    with pytest.raises(ValueError, match="not allowlisted"):
        TrustedVerifierCommand("python-check", ("git", "status"))


def _create_command() -> CommandEnvelope:
    return CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-create",
            "command_id": "command-create",
            "command_type": "task.create",
            "issued_at": "2026-08-13T10:00:00Z",
            "scope": _scope().to_dict(),
            "correlation_id": "correlation-1",
            "causation_id": None,
            "origin": {
                "kind": "structured",
                "turn_id": None,
                "commit_id": None,
            },
            "target_ref": {"kind": "task", "id": "create:command-create"},
            "context_refs": [],
            "required_capabilities": ["task.create"],
            "payload": {},
            "extensions": {},
        }
    )


@pytest.mark.asyncio
async def test_coordinator_runs_exact_fence_clean_successor_and_persisted_verifier(
    tmp_path: Path,
) -> None:
    root, manifest = _fixture(tmp_path)
    agent = _AttemptExecutor("wait")
    task_store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    created = task_store.create(
        _create_command(), _spec(root), observed_at="2026-08-13T10:00:00Z"
    )
    assert created.result is not None
    task_id = str(created.result["task_id"])
    predecessor_id = str(created.result["attempt_id"])
    initial = task_store.claim_outbox("initial-dispatch")
    assert initial is not None
    adapter = await _dispatching_adapter(
        tmp_path, root, agent, item=initial
    )
    initial_delivery = await adapter.dispatch(initial)
    task_store.complete_outbox(
        initial,
        executor_ref=initial_delivery.executor_ref,
        observations=initial_delivery.observations,
    )

    revisions = SqliteTaskRevisionStore(task_store)
    command = TaskRevisionCommand(
        "revision-1",
        TaskRevisionOperation.PROVIDE_INPUT,
        _scope(),
        task_id,
        1,
        predecessor_id,
        "voice-commit-1",
        ("negative inputs retain their behavior",),
    )
    grant = TaskRevisionGrant(
        "user-1",
        _scope(),
        command.operation,
        command.command_id,
        task_id,
        1,
        predecessor_id,
        command.fingerprint(),
        "confirmation-1",
        True,
        "2026-08-13T10:05:00Z",
    )
    revisions.request_revision(
        command,
        grant,
        initial_constraints=TaskRevisionConstraints(("src",)),
        observed_at="2026-08-13T10:01:00Z",
    )
    registry = _registry(
        manifest,
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; assert Path('src/result.py').exists()",
        ),
    )
    coordinator = TaskRevisionExecutionCoordinator(
        revisions, adapter, registry, worker_id="revision-worker"
    )

    applied = await coordinator.fence_once()
    assert applied is not None and applied.successor_attempt_id is not None
    dispatched = await coordinator.dispatch_once()
    assert dispatched is not None
    agent.release.set()
    for _ in range(300):
        if not adapter.has_live_workers:
            break
        await asyncio.sleep(0.01)
    truth = revisions.truth(task_id, _scope())
    terminal = await adapter.status(truth.task, truth.attempt)
    assert isinstance(terminal, ExecutorDeliveryResult)
    task_store.apply_observations(terminal.observations)
    truth = revisions.truth(task_id, _scope())
    ack = await TaskRevisionFixtureVerifier(
        registry, cleanup_proof=adapter.revision_cleanup_resolved
    ).verify(
        item=dispatched.item,
        delivery=terminal,
        task_revision=truth.current_revision.task_revision,
        constraints=truth.current_revision.constraints,
    )
    revisions.record_execution_ack(_scope(), ack)

    final = revisions.truth(task_id, _scope())
    assert final.current_revision.task_revision == 2
    assert final.execution_ack is not None
    assert final.execution_ack.verified_success is True
    assert final.execution_ack.changed_paths == ("src/result.py",)
    assert final.cleanup_ack is not None
    assert final.cleanup_ack.checkout_identity == manifest.checkout_identity
    await adapter.close()
