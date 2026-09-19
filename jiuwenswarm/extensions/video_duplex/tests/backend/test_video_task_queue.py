"""Video adapter regressions over the persisted task service (no private queue mirrors)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.extensions.video_duplex.backend import video_search
from jiuwenswarm.extensions.video_duplex.backend.task_adapter import task_identity


def test_voice_query_excludes_unbounded_progress_and_preserves_control_identity():
    job = {
        "id": "task-a", "job_id": "task-a", "status": "running", "revision": 4,
        "queue_version": 9, "question": "生成行程", "query": "生成行程",
        "progress_history": [{"reasoning": "私有执行详情" * 100000}],
        "progress": {"reasoning": "不要转发"}, "result": "结论" * 10000,
        "interaction": {"id": "question-a", "state": "pending", "questions": [{"question": "预算？"}]},
    }
    result = video_search.VideoSearchManager.voice_job(job)
    assert result["job_id"] == "task-a"
    assert result["revision"] == 4 and result["queue_version"] == 9
    assert result["interaction"] == job["interaction"]
    assert "progress_history" not in result and "progress" not in result
    assert result["result_truncated"] is True
    assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) < 8000
    assert job["progress_history"], "The UI still owns the full history"


def test_oversized_interaction_requires_ui_instead_of_corrupting_answer_identity():
    result = video_search.VideoSearchManager.voice_job({"interaction": {"questions": ["长问题" * 10000]}})
    assert result["interaction_requires_ui"] is True
    assert "interaction" not in result


def test_voice_job_has_a_total_bound_even_with_many_large_fields():
    job = {"job_id": "a", "question": "详" * 4000, "query": "详" * 4000,
           "error": "详" * 4000, "result": "详" * 4000,
           "adjustments": [{"id": "a", "instruction": "详" * 4000} for _ in range(20)]}
    result = video_search.VideoSearchManager.voice_job(job)
    assert result["job_id"] == "a"
    assert result["details_omitted"] is True
    assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) < 12000


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.005)


@pytest.fixture
async def queue(monkeypatch, tmp_path):
    events, responses, executed, cancels = [], [], [], []
    gates = {name: asyncio.Event() for name in "ABC"}
    stop_ack = asyncio.Event()
    stop_ack.set()
    stopped = set()
    reject = [False]

    async def execute(_client, **kwargs):
        name = kwargs["question"]
        executed.append(name)
        await gates[name].wait()
        with manager.service.store.transaction() as db:
            task = next(
                t
                for t in manager.service.store.rows(db)
                if t["request_id"] == kwargs["request_id"]
            )
        manager.service.store.update(
            task["id"], lambda t: t.update(execution_settled=True)
        )
        if name in stopped:
            raise RuntimeError("Stopped")
        return {"answer": name}

    async def send_event(ws, name, payload):
        events.append((name, payload))

    async def send_response(ws, req_id, **kwargs):
        responses.append(kwargs)

    async def send_request(env):
        cancels.append(env)
        await stop_ack.wait()
        if reject[0]:
            return SimpleNamespace(ok=False, payload={})
        with manager.service.store.transaction() as db:
            task = next(
                t
                for t in manager.service.store.rows(db)
                if t["core_session_id"] == env.session_id
            )
        stopped.add(task["instruction"])
        gates[task["instruction"]].set()
        return SimpleNamespace(ok=True, payload={})

    monkeypatch.setattr(video_search, "execute_core_agent", execute)
    manager = video_search.VideoSearchManager(
        SimpleNamespace(send_event=send_event, send_response=send_response),
        SimpleNamespace(send_request=send_request),
        log_event=lambda _: None,
        qwen_active=lambda: True,
        path=tmp_path / "tasks.sqlite",
        authorize=lambda ws, scope: ("alice", scope),
    )

    def start(name, scope="scope"):
        return manager.start(
            None, question=name, query=name, search_session_id=scope, command_id=name
        )["id"]

    def record(task_id):
        return manager.service.get("alice", "scope", task_id)

    async def control(task_id, action, **extra):
        await manager.handle_control(
            None,
            "control-" + action + task_id,
            {
                "search_session_id": "scope",
                "job_id": task_id,
                "action": action,
                "queue_version": manager.snapshot("alice", "scope")["queue_version"],
                **extra,
            },
            None,
        )
        return responses[-1]

    yield SimpleNamespace(**locals())
    await manager.close()


async def test_reorder_and_cancel_waiter(queue):
    q = queue
    q.start("A")
    await until(lambda: q.executed == ["A"])
    b, c = q.start("B"), q.start("C")
    assert (await q.control(c, "next"))["ok"]
    assert (await q.control(b, "cancel"))["ok"]
    q.gates["A"].set()
    q.gates["C"].set()
    await until(lambda: q.record(c)["status"] == "completed")
    assert q.executed == ["A", "C"] and not q.cancels
    assert q.record(b)["status"] == "cancelled"


async def test_preempt_stays_pending_until_exact_stop_ack(queue):
    q = queue
    a = q.start("A")
    await until(lambda: q.executed == ["A"])
    q.start("B")
    c = q.start("C")
    q.stop_ack.clear()
    assert (await q.control(c, "preempt"))["ok"]
    await until(lambda: q.cancels)
    assert q.cancels[0].session_id == q.record(a)["core_session_id"]
    assert q.record(a)["status"] == "cancelling" and q.executed == ["A"]
    q.stop_ack.set()
    q.gates["C"].set()
    await until(lambda: len(q.executed) == 3)
    assert q.executed == ["A", "C", "B"]
    assert q.record(a)["status"] == "cancelled"
    assert not any(
        event == "video.search.completed" and data["job_id"] == a
        for event, data in q.events
    )


async def test_rejected_stop_is_not_falsely_reported_stopped(queue):
    q = queue
    a = q.start("A")
    await until(lambda: q.executed)
    q.start("B")
    q.reject[0] = True
    assert (await q.control(a, "cancel"))["ok"]  # durable admission only
    await until(lambda: q.record(a)["error"])
    assert q.record(a)["status"] == "cancelling" and q.executed == ["A"]


async def test_wrong_scope_and_stale_queue_have_no_effect(queue):
    q = queue
    a = q.start("A")
    await until(lambda: q.executed)
    b = q.start("B")
    assert not (await q.control(b, "next", queue_version=-1))["ok"]
    assert not (await q.control(a, "cancel", search_session_id="other"))["ok"]
    assert q.record(b)["status"] == "queued" and not q.cancels


async def test_query_control_tools_return_receipts_without_creating_work(queue):
    q = queue
    a = q.start("A")
    for call, name, arguments in [
        ("find", "jiuwen_task_query", {"job_id": a}),
        (
            "edit",
            "jiuwen_task_modify",
            {"job_id": a, "revision": 1, "instruction": "French"},
        ),
        ("stop", "jiuwen_task_cancel", {"job_id": a}),
    ]:
        await q.manager.handle_qwen_tool(
            None,
            call,
            {
                "search_session_id": "scope",
                "name": name,
                "call_id": call,
                "arguments": arguments,
            },
            None,
        )
        assert q.responses[-1]["ok"]
        assert "tool_result" in q.responses[-1]["payload"]
    assert len(q.manager.snapshot("alice", "scope")["jobs"]) == 1
    await asyncio.sleep(0.02)
    assert q.executed == q.cancels == []


async def test_voice_query_pages_large_history_without_forwarding_it(queue):
    q = queue
    for index in range(7):
        task_id = q.start(f"pending-{index}")
        q.manager.service.store.update(task_id, lambda t: t.update(
            progress=[{"reasoning": "PRIVATE-HISTORY" * 30000}],
        ))
    found = []
    for offset in (0, 5):
        await q.manager.handle_qwen_tool(None, f"query-{offset}", {
            "search_session_id": "scope", "name": "jiuwen_task_query",
            "call_id": f"query-{offset}", "arguments": {"offset": offset},
        }, None)
        reply = q.responses[-1]
        assert reply["ok"]
        result = reply["payload"]["tool_result"]
        found.extend(t["job_id"] for t in result["jobs"])
        serialized = json.dumps(result, ensure_ascii=False)
        assert "PRIVATE-HISTORY" not in serialized
        assert len(serialized.encode("utf-8")) < 64000
        assert result["next_offset"] == (5 if offset == 0 else None)
    assert len(set(found)) == 7


@pytest.mark.parametrize(
    "remote,origin",
    [
        ("192.0.2.1", "http://127.0.0.1:5173"),
        ("127.0.0.1", "https://untrusted.example"),
        ("127.0.0.1", ""),
    ],
)
def test_untrusted_connections_cannot_claim_local_identity(remote, origin):
    ws = SimpleNamespace(
        remote_address=(remote, 1234),
        request_headers={"Origin": origin},
        _web_connection_user_id="admin",
    )
    with pytest.raises(ValueError):
        task_identity(ws, "scope")


@pytest.mark.parametrize(
    "scope", ["task-duplex:..", "task-duplex:C:other", "task-duplex:alias."]
)
def test_saved_conversation_rejects_filesystem_aliases(scope):
    ws = SimpleNamespace(
        remote_address=("127.0.0.1", 1234),
        request_headers={"Origin": "http://127.0.0.1:5173"},
    )
    with pytest.raises(ValueError, match="Invalid saved conversation"):
        task_identity(ws, scope)

async def test_qwen_independent_submission_and_exact_cancel_share_native_adapter(queue):
    q = queue
    a = q.start('A')
    await until(lambda: q.executed == ['A'])
    await q.manager.handle_qwen_tool(None, 'parallel', {
        'name': 'jiuwen_delegate', 'call_id': 'weather', 'search_session_id': 'scope',
        'arguments': {'task': 'B', 'independent': True, 'resources': []}}, None)
    assert q.responses[-1]['ok']
    b = q.responses[-1]['payload']['search_job']['id']
    await until(lambda: q.executed == ['A', 'B'])
    assert q.record(a)['core_session_id'] != q.record(b)['core_session_id']
    assert (await q.control(b, 'cancel'))['ok']
    await until(lambda: q.record(b)['status'] == 'cancelled')
    assert q.record(a)['status'] == 'running'
    assert len(q.cancels) == 1 and q.cancels[0].session_id == q.record(b)['core_session_id']


async def test_query_summary_covers_unfinished_tasks_beyond_first_page(tmp_path):
    from jiuwenswarm.runtime.tasks.service import TaskService
    from jiuwenswarm.runtime.tasks.store import TaskStore
    service = TaskService(TaskStore(tmp_path / "summary.sqlite"), None)
    service.started = True  # No executions: use isolated persisted records only.
    service.kick = lambda: None
    manager = object.__new__(video_search.VideoSearchManager)
    manager._service, manager.concurrency = service, 2
    for i in range(7):
        task = service.submit("alice", "scope", str(i), str(i))
        service.store.update(task["id"], lambda t, i=i: t.update(status="completed" if i < 5 else "running"))
    call = SimpleNamespace(name="jiuwen_task_query", arguments={})
    result = await manager.operate("alice", "scope", call)
    assert len(result["jobs"]) == 5 and result["next_offset"] == 5
    assert result["summary"]["unfinished"] == 2
    assert result["summary"]["all_finished"] is False
    assert result["summary"]["status_counts"] == {"completed": 5, "running": 2}
    call.arguments = {"status": "unfinished"}
    filtered = await manager.operate("alice", "scope", call)
    assert len(filtered["jobs"]) == 2 and filtered["next_offset"] is None
    assert filtered["summary"] == result["summary"]
    call.arguments = {"query": "不存在的名称 文件"}
    missing = await manager.operate("alice", "scope", call)
    assert missing["jobs"] == [] and missing["summary"]["all_finished"] is False
    assert "不能据此推断" in missing["message"]
    call.arguments = {"job_id": result["jobs"][0]["id"]}
    with pytest.raises(ValueError, match="not found"):
        await manager.operate("mallory", "scope", call)


def test_voice_artifacts_use_file_events_not_answer_claims():
    result = video_search.VideoSearchManager.voice_job({"result": "已保存 /workspace/杭州.md"})
    assert result["artifact_status"] == "not_confirmed" and result["files"] == []
    result = video_search.VideoSearchManager.voice_job({"files": [{"name": "杭州.md", "path": "C:/work/杭州.md", "download_token": "secret"}]})
    assert result["files"] == [{"name": "杭州.md", "path": "C:/work/杭州.md"}]
    assert "secret" not in json.dumps(result)


async def test_native_file_history_is_bound_to_exact_execution(queue, monkeypatch):
    from jiuwenswarm.server.runtime.session import session_history

    q = queue
    task_id = q.start("A")
    await until(lambda: q.executed == ["A"])
    task = q.record(task_id)
    seen = []

    def history(session_id):
        seen.append(session_id)
        return [
            {"request_id": task["request_id"], "event_type": "chat.file",
             "files": [{"name": "current.md", "path": "C:/work/current.md"}]},
            {"request_id": "previous-execution", "event_type": "chat.file",
             "files": [{"name": "old.md", "path": "C:/work/old.md"}]},
            {"request_id": task["request_id"], "event_type": "chat.final",
             "files": [{"name": "claimed.md", "path": "C:/work/claimed.md"}]},
        ]

    monkeypatch.setattr(session_history, "load_history_records", history)
    q.gates["A"].set()
    await until(lambda: q.record(task_id)["status"] == "completed")
    public = q.manager.public(q.record(task_id))
    assert seen == [task["core_session_id"]]
    assert [f["name"] for f in public["files"]] == ["current.md"]


async def test_voice_reorder_refreshes_stale_targets_and_returns_actual_neighbours(tmp_path):
    from jiuwenswarm.runtime.tasks.service import TaskService
    from jiuwenswarm.runtime.tasks.store import TaskStore
    service = TaskService(TaskStore(tmp_path / "reorder.sqlite"), None)
    service.started = True
    service.kick = lambda: None
    manager = object.__new__(video_search.VideoSearchManager)
    manager._service, manager.concurrency = service, 2
    jobs = [service.submit("alice", "scope", str(i), str(i)) for i in range(8)]
    for task in jobs[:5]:
        service.store.update(task["id"], lambda t: t.update(status="completed"))
    call = SimpleNamespace(name="jiuwen_task_reorder", call_id="move-last", arguments={
        "job_id": jobs[7]["id"], "action": "before", "before_job_id": jobs[5]["id"], "queue_version": 0})
    result = await manager.operate("alice", "scope", call)
    assert [t["id"] for t in result["jobs"]] == [jobs[7]["id"], jobs[5]["id"], jobs[6]["id"]]
    assert result["target"]["queue_position"] == 1

    service.store.update(jobs[7]["id"], lambda t: t.update(status="completed"))
    replay = await manager.operate("alice", "scope", call)
    assert replay["operation"] == result["operation"]
    assert replay["target"]["status"] == "completed"


async def test_stale_voice_modification_returns_current_version_without_applying(queue):
    q = queue
    task_id = q.start("A")
    await until(lambda: q.executed == ["A"])
    q.manager.service.store.update(task_id, lambda t: t.update(revision=3))
    call = SimpleNamespace(name="jiuwen_task_modify", call_id="old", arguments={
        "job_id": task_id, "revision": 1, "instruction": "new requirements"})
    result = await q.manager.operate("alice", "scope", call)
    assert result["state"] == "rejected" and result["applied"] is False
    assert result["current_task"]["revision"] == 3
    assert q.record(task_id)["changes"] == []
    call.call_id = "fresh"
    call.arguments["revision"] = 3
    accepted = await q.manager.operate("alice", "scope", call)
    assert accepted["state"] == "pending"
    assert len(q.record(task_id)["changes"]) == 1
