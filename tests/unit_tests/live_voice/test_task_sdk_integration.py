"""One SDK task authority with application-owned speech evidence and ledgers."""
from pathlib import Path

from openjiuwen.core.application.tasks import PersistentTaskCore, SqliteTaskStore
from openjiuwen.core.application.tasks import contracts
from openjiuwen.core.application.tasks.source import TaskSourceError, source_from_payload
from jiuwenswarm.common.schema import live_voice_contract_v2 as voice
from jiuwenswarm.common.schema.native_task_source import NativeTaskSourceError


def test_task_kernel_has_single_sdk_owner_and_shared_type_identity():
    assert PersistentTaskCore.__module__.startswith("openjiuwen.")
    assert SqliteTaskStore.__module__.startswith("openjiuwen.")
    for name in ["ScopeRef", "CommandEnvelope", "ContractViolation", "ResultEnvelope", "TerminalOutcome"]:
        assert getattr(voice, name) is getattr(contracts, name)
    assert voice.TurnCommitLedger.__module__ == voice.__name__
    assert voice.IdentityRegistry.__module__ == voice.__name__
    root = Path(__file__).resolve().parents[3]
    for name in ["persistent_task_core", "task_store", "formal_task_models", "task_adjustment_queue"]:
        assert not (root / "jiuwenswarm/server/runtime/formal_tasks" / f"{name}.py").exists()


def test_legacy_source_error_identity_is_preserved_across_sdk_and_host():
    assert NativeTaskSourceError is TaskSourceError
    try:
        source_from_payload({"native_source": None})
    except NativeTaskSourceError as error:
        assert error.reason == "NATIVE_TASK_SOURCE_INVALID"
    else:
        raise AssertionError("present malformed source became legacy")
