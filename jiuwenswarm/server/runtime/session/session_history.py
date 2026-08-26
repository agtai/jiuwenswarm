from __future__ import annotations

import datetime
import hashlib
import logging
import json
import os
import queue
import re
import threading
import time
import weakref
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from jiuwenswarm.common.utils import get_agent_sessions_dir


logger = logging.getLogger(__name__)
_WRITE_QUEUE: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=20000)
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()
_LEGACY_HISTORY_FILENAME = "history.json"
_JSONL_HISTORY_FILENAME = "history.jsonl"
_LEGACY_HISTORY_ENV = "JIUWENSWARM_USE_LEGACY_HISTORY_JSON"
_HEARTBEAT_OK = "HEARTBEAT_OK"
_SESSION_STATE_RECENT_LIMIT = 128
_VALID_SESSION_ID = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,78}[A-Za-z0-9])?$"
)


class _SessionHistoryState:
    """Process-local lock and rebuildable formal-idempotency acceleration."""

    __slots__ = ("lock", "formal_index", "formal_index_path", "__weakref__")

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.formal_index: dict[str, str | None] | None = None
        self.formal_index_path: Path | None = None


_SESSION_STATE_REGISTRY_LOCK = threading.Lock()
_SESSION_STATE_WEAK: weakref.WeakValueDictionary[str, _SessionHistoryState] = (
    weakref.WeakValueDictionary()
)
_SESSION_STATE_RECENT: OrderedDict[str, _SessionHistoryState] = OrderedDict()


def _get_session_history_state(session_id: str) -> _SessionHistoryState:
    """Return one exact state while retaining only a bounded recent working set.

    The weak registry prevents an active state from being duplicated if it is evicted
    from the bounded strong LRU.  Eviction only loses acceleration; JSONL remains the
    business source of truth and the index is rebuilt on the next formal append.
    """

    with _SESSION_STATE_REGISTRY_LOCK:
        state = _SESSION_STATE_WEAK.get(session_id)
        if state is None:
            state = _SessionHistoryState()
            _SESSION_STATE_WEAK[session_id] = state
        _SESSION_STATE_RECENT.pop(session_id, None)
        _SESSION_STATE_RECENT[session_id] = state
        while len(_SESSION_STATE_RECENT) > _SESSION_STATE_RECENT_LIMIT:
            _SESSION_STATE_RECENT.popitem(last=False)
        return state


@contextmanager
def _session_history_lock(
    session_id: str,
) -> Iterator[_SessionHistoryState]:
    """Serialize every in-process mutation of one normalized Session history."""

    sid = str(session_id or "").strip()
    state = _get_session_history_state(sid)
    with state.lock:
        yield state
# Gateway may inline @path as <file-content>...</file-content> before chat.send.
# History should keep the short @path form so jsonl rows stay one physical line
# and refresh UI does not load megabytes of file body.
_FILE_CONTENT_BLOCK_RE = re.compile(
    r"\n?<file-content\s+path=\"([^\"]*)\">.*?</file-content>\n?",
    re.DOTALL,
)


def collapse_file_content_blocks(content: str) -> str:
    """Replace inlined ``<file-content>`` bodies with ``@path`` references.

    Used when persisting / serving user history so the agent-facing inline
    expansion is not stored as the user-visible transcript.
    """
    if not content or "<file-content" not in content:
        return content

    def _replacer(match: re.Match[str]) -> str:
        path = match.group(1) or ""
        if not path:
            return "\n"
        ref = f'@"{path}"' if any(ch.isspace() for ch in path) else f"@{path}"
        return f"\n{ref}\n"

    collapsed = _FILE_CONTENT_BLOCK_RE.sub(_replacer, content)
    return re.sub(r"\n{3,}", "\n\n", collapsed).strip()


def is_valid_session_id(session_id: str) -> bool:
    """Return whether a session id is safe to use as one path component."""

    return _VALID_SESSION_ID.fullmatch(session_id) is not None
_FORMAL_LIVE_VOICE_SESSION_PREFIX = "lv-formal-"
_FORMAL_NO_HISTORY_LOCK = threading.Lock()
_FORMAL_NO_HISTORY_SESSIONS: dict[str, int] = {}


def _is_ephemeral_heartbeat_session(session_id: str) -> bool:
    """Heartbeat sessions are one-shot and should not pollute history.json(l)."""
    return (session_id or "").startswith("heartbeat")


def _is_formal_live_voice_no_history_session(session_id: str) -> bool:
    with _FORMAL_NO_HISTORY_LOCK:
        return _FORMAL_NO_HISTORY_SESSIONS.get(session_id, 0) > 0


def register_formal_no_history_session(session_id: str) -> None:
    """Register one trusted formal execution across Agent/tool task contexts."""

    sid = str(session_id or "").strip()
    if not sid.startswith(_FORMAL_LIVE_VOICE_SESSION_PREFIX):
        raise ValueError("formal no-history session must use the internal namespace")
    with _FORMAL_NO_HISTORY_LOCK:
        _FORMAL_NO_HISTORY_SESSIONS[sid] = _FORMAL_NO_HISTORY_SESSIONS.get(sid, 0) + 1


def unregister_formal_no_history_session(session_id: str) -> None:
    """Release one trusted formal execution registration."""

    sid = str(session_id or "").strip()
    with _FORMAL_NO_HISTORY_LOCK:
        retained = _FORMAL_NO_HISTORY_SESSIONS.get(sid, 0)
        if retained <= 1:
            _FORMAL_NO_HISTORY_SESSIONS.pop(sid, None)
        else:
            _FORMAL_NO_HISTORY_SESSIONS[sid] = retained - 1


def _has_persistable_assistant_payload(
    *,
    content_text: str,
    event_type: str | None,
    extra: dict[str, Any] | None,
) -> bool:
    """Return False for blank assistant shells that would show as empty history rows."""
    content = (content_text or "").strip()
    if content.upper() == _HEARTBEAT_OK:
        return False

    et = str(event_type or "").strip()
    payload = extra if isinstance(extra, dict) else {}
    if content:
        return True
    if str(payload.get("reasoning_content") or "").strip():
        return True
    if et == "chat.file" and payload.get("files"):
        return True
    if et == "chat.tool_call" and (payload.get("tool_call") or payload.get("tool_calls")):
        return True
    if et == "chat.tool_result" and (payload.get("tool_result") or payload.get("tool_call_id")):
        return True
    if payload.get("error") or payload.get("files"):
        return True
    if payload.get("tool_call") or payload.get("tool_calls"):
        return True
    # Empty chat.final / chat.* status shells and other blank assistants: skip.
    if et.startswith("chat.") or et in {"", "chat.final"}:
        return False
    # team.* / context.* monitor events may carry structured extras without content.
    return bool(payload)


def _serialize_value_with_flag(obj: Any) -> tuple[Any, bool]:
    """将对象转换为 JSON 可序列化的格式，并返回是否发生降级处理."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj, False
    if isinstance(obj, datetime.datetime):
        return obj.isoformat(), True
    if isinstance(obj, datetime.date):
        return obj.isoformat(), True
    if callable(obj):
        name = getattr(obj, "__qualname__", None) or getattr(obj, "__name__", None) or type(obj).__name__
        return f"<callable:{name}>", True
    if isinstance(obj, dict):
        changed = False
        serialized: dict[Any, Any] = {}
        for k, v in obj.items():
            serialized_value, value_changed = _serialize_value_with_flag(v)
            serialized[k] = serialized_value
            changed = changed or value_changed
        return serialized, changed
    if isinstance(obj, (list, tuple, set, frozenset)):
        changed = not isinstance(obj, list)
        serialized_items = []
        for item in obj:
            serialized_item, item_changed = _serialize_value_with_flag(item)
            serialized_items.append(serialized_item)
            changed = changed or item_changed
        return serialized_items, changed
    try:
        json.dumps(obj, ensure_ascii=False)
    except TypeError:
        return repr(obj), True
    return obj, False


def _serialize_value(obj: Any) -> Any:
    return _serialize_value_with_flag(obj)[0]


def _session_dir(session_id: str, *, create: bool = True) -> Path:
    session_dir = get_agent_sessions_dir() / session_id
    if create:
        session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def resolve_session_dir(
    session_id: str, *, create: bool = False, sessions_root: Path | None = None,
) -> tuple[Path | None, str | None]:
    """安全解析 session 目录路径（防路径遍历）。

    采用严格白名单判据：session id 只能包含 ASCII 字母、数字、点、横线和下划线，
    长度不超过 80，且首尾必须是字母或数字。不合法输入直接拒绝，根本不拼路径。

    再用 ``resolve()`` + ``relative_to`` 做纵深防御，兜底白名单逻辑被绕过的极端情况。

    Args:
        session_id: 待校验的 session id（调用方应先 ``.strip()``）。
        create: 是否创建目录（delete 流程传 False）。
        sessions_root: sessions 根目录。由调用方传入

    Returns:
        ``(resolved_path, None)`` —— 合法，返回解析后的绝对路径（确认在 sessions 目录内）。
        ``(None, error_reason)`` —— 非法，根本未触碰磁盘路径。
    """
    if not session_id or not is_valid_session_id(session_id):
        return None, "invalid session_id"

    if sessions_root is None:
        sessions_root = get_agent_sessions_dir()
    session_dir = sessions_root / session_id
    # 纵深防御必须在 mkdir 之前：先 resolve + relative_to 确认路径仍在 sessions
    # 目录内，通过后才允许创建。否则白名单一旦被绕过，mkdir(parents=True) 会
    # 先在 sessions 根目录之外越界创建目录，relative_to 才事后检测到——此时
    # 副作用已发生，越界空目录残留在磁盘上（虽不触发 rmtree，但仍是文件系统泄漏）。
    try:
        resolved = session_dir.resolve(strict=False)
        resolved.relative_to(sessions_root.resolve(strict=False))
    except (ValueError, OSError):
        return None, "invalid session_id"
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved, None


def _history_file(session_id: str, *, create: bool = True) -> Path:
    return _session_dir(session_id, create=create) / _LEGACY_HISTORY_FILENAME


def _history_jsonl_file(session_id: str, *, create: bool = True) -> Path:
    return _session_dir(session_id, create=create) / _JSONL_HISTORY_FILENAME


def use_legacy_history_json() -> bool:
    raw = str(os.environ.get(_LEGACY_HISTORY_ENV, "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_write_history_path(session_id: str) -> Path:
    """Return the JSONL business source of truth for new mutations."""
    return _history_jsonl_file(session_id)


def get_read_history_path(session_id: str) -> Path:
    """Return JSONL when present, falling back to the legacy migration input."""
    jsonl_path = _history_jsonl_file(session_id, create=False)
    if jsonl_path.exists():
        return jsonl_path
    legacy_path = _history_file(session_id, create=False)
    if legacy_path.exists():
        return legacy_path
    return jsonl_path


def history_exists(session_id: str) -> bool:
    return get_read_history_path(session_id).exists()


def get_history_mtime(session_id: str) -> float | None:
    path = get_read_history_path(session_id)
    if not path.exists():
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _read_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 history.json 失败，已忽略并重建: %s", exc)
        return []
    if isinstance(data, list):
        return data
    return []


def _read_history_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    try:
        # JSONL records are delimited by "\n" only. Do NOT use str.splitlines():
        # inlined file bodies may contain Unicode line separators (U+2028 etc.)
        # that splitlines() treats as breaks, corrupting a single JSON object
        # into fragments and dropping the user turn on refresh.
        text = path.read_text(encoding="utf-8")
        for lineno, raw_line in enumerate(text.split("\n"), start=1):
            line = raw_line.rstrip("\r").strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception as exc:  # noqa: BLE001
                logger.warning("读取 history.jsonl 第 %d 行失败，已跳过: %s", lineno, exc)
                continue
            if isinstance(item, dict):
                content = item.get("content")
                if (
                    item.get("role") in {"user", "human"}
                    and isinstance(content, str)
                    and "<file-content" in content
                ):
                    item = dict(item)
                    item["content"] = collapse_file_content_blocks(content)
                records.append(item)
            else:
                logger.warning(
                    "读取 history.jsonl 第 %d 行不是对象记录，已跳过: %s",
                    lineno,
                    type(item).__name__,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 history.jsonl 失败，已忽略: %s", exc)
        return []
    return records


def load_history_records(session_id: str) -> list[dict[str, Any]]:
    path = get_read_history_path(session_id)
    if path.suffix.lower() == ".jsonl":
        return _read_history_jsonl(path)
    return _read_history(path)


def _write_records_to_path(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".jsonl":
        payload = "\n".join(
            json.dumps(record, ensure_ascii=False) for record in records
        )
        if payload:
            payload += "\n"
        path.write_text(payload, encoding="utf-8")
        return

    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_record_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False))
        fh.write("\n")


def _invalidate_formal_index(state: _SessionHistoryState) -> None:
    state.formal_index = None
    state.formal_index_path = None


def _canonical_record_digest(record: dict[str, Any]) -> str:
    # Digest the JSON value that a later reader observes, not Python-only key types.
    normalized = json.loads(json.dumps(record, ensure_ascii=False))
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _record_formal_digest(
    index: dict[str, str | None], record: dict[str, Any]
) -> None:
    record_id = record.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        return
    digest = _canonical_record_digest(record)
    if record_id not in index:
        index[record_id] = digest
    elif index[record_id] != digest:
        # A pre-existing conflicting duplicate must never be accepted as an exact replay.
        index[record_id] = None


def _read_jsonl_records_for_formal_index(path: Path) -> list[dict[str, Any]]:
    """Read exact persisted objects once without presentation-time normalization."""

    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("formal history index rebuild failed") from exc
    for lineno, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.rstrip("\r").strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"formal history index line {lineno} is invalid"
            ) from exc
        if not isinstance(item, dict):
            raise ValueError(
                f"formal history index line {lineno} is not an object"
            )
        records.append(item)
    return records


def _build_formal_history_index(path: Path) -> dict[str, str | None]:
    index: dict[str, str | None] = {}
    for record in _read_jsonl_records_for_formal_index(path):
        _record_formal_digest(index, record)
    return index


def _repair_jsonl_tail(path: Path) -> bool:
    """Repair one interrupted final JSONL row before a later append.

    A complete JSON object missing only its delimiter is preserved by adding ``\n``.
    An invalid partial row is truncated to the previous delimiter.  The operation is
    intentionally process-local and makes no fsync or multi-process durability claim.
    """

    if not path.exists() or path.stat().st_size == 0:
        return False

    with path.open("r+b") as fh:
        end = fh.seek(0, os.SEEK_END)
        fh.seek(end - 1)
        if fh.read(1) == b"\n":
            return False

        cursor = end
        chunks: list[bytes] = []
        truncate_at = 0
        while cursor > 0:
            start = max(0, cursor - 64 * 1024)
            fh.seek(start)
            chunk = fh.read(cursor - start)
            newline = chunk.rfind(b"\n")
            if newline >= 0:
                truncate_at = start + newline + 1
                chunks.append(chunk[newline + 1 :])
                break
            chunks.append(chunk)
            cursor = start

        tail = b"".join(reversed(chunks))
        try:
            decoded = tail.rstrip(b"\r").decode("utf-8")
            item = json.loads(decoded)
            complete_object = isinstance(item, dict)
        except (UnicodeDecodeError, json.JSONDecodeError):
            complete_object = False

        if complete_object:
            fh.seek(end)
            fh.write(b"\n")
        else:
            fh.truncate(truncate_at)
    return True


def _ensure_jsonl_bootstrap(session_id: str) -> Path:
    with _session_history_lock(session_id) as state:
        jsonl_path = _history_jsonl_file(session_id)
        if jsonl_path.exists():
            return jsonl_path

        legacy_path = _history_file(session_id)
        if legacy_path.exists():
            legacy_records = _read_history(legacy_path)
            _write_records_to_path(jsonl_path, legacy_records)
            _invalidate_formal_index(state)
        else:
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        return jsonl_path


def _ensure_legacy_json_bootstrap(session_id: str) -> Path:
    with _session_history_lock(session_id) as state:
        legacy_path = _history_file(session_id)
        if legacy_path.exists():
            return legacy_path

        jsonl_path = _history_jsonl_file(session_id)
        if jsonl_path.exists():
            jsonl_records = _read_history_jsonl(jsonl_path)
            _write_records_to_path(legacy_path, jsonl_records)
            _invalidate_formal_index(state)
        else:
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
        return legacy_path


def _rewrite_session_history_records(
    session_id: str, records: list[dict[str, Any]]
) -> Path:
    """Rewrite the JSONL truth under the Session mutation lock."""

    sid = str(session_id or "").strip()
    with _session_history_lock(sid) as state:
        path = _ensure_jsonl_bootstrap(sid)
        _write_records_to_path(path, records)
        _invalidate_formal_index(state)
        return path


def write_history_records(
    session_id: str,
    records: list[dict[str, Any]],
    *,
    preserve_existing_format: bool = True,
) -> Path:
    """Rewrite JSONL history; ``preserve_existing_format`` is compatibility-only."""

    del preserve_existing_format
    return _rewrite_session_history_records(session_id, records)


_TEAM_RELEVANT_EVENT_TYPES = frozenset({
    "team.message",
    "team.member",
    "team.task",
    "team.event",
    "chat.tool_call", "chat.tracer_agent",
    "chat.final", "chat.tool_result", "chat.file",
})


def _is_team_relevant(item: dict[str, Any]) -> bool:
    et = item.get("event_type")
    if not isinstance(et, str):
        return False
    if et in _TEAM_RELEVANT_EVENT_TYPES:
        if et == "chat.file":
            role = item.get("role")
            return isinstance(role, str) and role.strip().lower() in {
                "assistant",
                "teammate",
            }
        if et in ("chat.tool_call", "chat.tracer_agent"):
            mode = item.get("mode")
            return isinstance(mode, str) and mode.strip().lower() == "team"
        if et in ("chat.final", "chat.tool_result"):
            role = item.get("role")
            return isinstance(role, str) and role.strip().lower() == "teammate"
        return True
    return False


def read_team_history_records(session_id: str) -> list[dict[str, Any]]:
    """读取指定会话的历史记录，仅返回 team 模式相关的记录。"""
    fpath = get_read_history_path(session_id)
    all_records = load_history_records(session_id)
    # write_text 非原子写入（先截断再写入），读取可能命中截断窗口，
    # 用递增间隔重试最多 5 次等待写入完成
    if not all_records and fpath.exists():
        for attempt in range(1, 6):
            time.sleep(0.2 * attempt)
            all_records = load_history_records(session_id)
            if all_records:
                logger.info("read_team_history_records: recovered on retry %d", attempt)
                break
        if not all_records:
            logger.warning(
                "read_team_history_records: all retries exhausted, file_size=%d",
                fpath.stat().st_size,
            )

    return [item for item in all_records if isinstance(item, dict) and _is_team_relevant(item)]


def _read_history_by_path(path: Path) -> list[dict[str, Any]]:
    """根据文件扩展名选择正确的读取函数。"""
    if path.suffix.lower() == ".jsonl":
        return _read_history_jsonl(path)
    return _read_history(path)


def _is_member_relevant(item: dict[str, Any], member_name: str) -> bool:
    """判断一条 team 历史记录是否与指定 member 相关（用于飞书 /join 历史推送）。

    与实时 fan_out 投递语义一致：每个 member 只看到"涉及自己的对话"：
    - team.message.p2p 且 to_member 或 from_member == member_name →
      发给/由该成员发出的私聊（与 fan_out
      [godview, mention(to_member), private(from_member)] 对齐：收件人和
      发送方都能看到 P2P 卡片）
    - team.message.broadcast → @all 广播，所有人都能看到
    - chat.* teammate 流式输出 且 member_name == 该成员 →
      该成员扮演的 agent 的输出（与 fan_out [godview, private(member)] 对齐）

    不含 team.member/team.task 上下文事件（不会发给飞书，避免刷屏）。
    """
    et = item.get("event_type")
    if not isinstance(et, str):
        return False

    if et == "team.message":
        inner = item.get("event", {}) if isinstance(item.get("event"), dict) else {}
        msg_type = inner.get("type", "") or item.get("type", "")
        if msg_type == "team.message.broadcast":
            return True
        if msg_type == "team.message.p2p":
            to_m = item.get("to_member", "") or inner.get("to_member", "")
            from_m = item.get("from_member", "") or inner.get("from_member", "")
            return member_name in {to_m, from_m}
        return False

    # chat.* teammate outputs: 已在 _is_team_relevant 中按 role/mode 过滤。
    # 实时投递只发给该 member 的 private 席位，历史同样只对该 member 可见。
    if et in {"chat.final", "chat.tool_call", "chat.tool_result", "chat.file", "chat.tracer_agent"}:
        src_member = str(item.get("member_name", "") or "").strip()
        return bool(src_member) and src_member == member_name

    # 注意：team.member / team.task / team.event 不包含，
    # 这些是上下文事件，飞书端不需要看到，避免刷屏。
    return False


def read_member_history_records(session_id: str, member_name: str) -> list[dict[str, Any]]:
    """读取 team 历史记录，仅返回与指定 member 相关的记录。

    与实时 fan_out 投递语义一致：
    - 发给/由该 member 发出的 p2p 消息
    - @all 广播消息
    - 该 member 扮演的 teammate 的流式输出

    不含 team.member/team.task 上下文事件，也不含其他 member 的输出。
    无 member_name 时回退到 read_team_history_records（供 web 前端面板恢复用）。
    """
    if not member_name or not isinstance(member_name, str):
        return read_team_history_records(session_id)
    all_team_records = read_team_history_records(session_id)
    mn = member_name.strip()
    return [item for item in all_team_records if _is_member_relevant(item, mn)]


def read_session_history_records(session_id: str) -> list[dict[str, Any]]:
    """读取指定会话的历史记录，返回所有记录。

    用于 auto memory 功能提取对话消息。
    """
    fpath = get_read_history_path(session_id)
    all_records = _read_history_by_path(fpath)
    # write_text 非原子写入（先截断再写入），读取可能命中截断窗口，
    # 用递增间隔重试最多 5 次等待写入完成
    if not all_records and fpath.exists():
        for attempt in range(1, 6):
            time.sleep(0.2 * attempt)
            all_records = _read_history_by_path(fpath)
            if all_records:
                logger.info("read_session_history_records: recovered on retry %d", attempt)
                break
        if not all_records:
            logger.warning(
                "read_session_history_records: all retries exhausted, file_size=%d",
                fpath.stat().st_size,
            )

    return [item for item in all_records if isinstance(item, dict)]


def _write_item(session_id: str, item: dict[str, Any]) -> None:
    with _session_history_lock(session_id) as state:
        target_path = _ensure_jsonl_bootstrap(session_id)
        if _repair_jsonl_tail(target_path):
            _invalidate_formal_index(state)
        _append_record_jsonl(target_path, item)
        if (
            state.formal_index is not None
            and state.formal_index_path == target_path.resolve(strict=False)
        ):
            _record_formal_digest(state.formal_index, item)


def append_formal_history_record_idempotent(
    *, session_id: str, record: dict[str, Any]
) -> bool:
    """Synchronously append one exact formal-route history fact.

    The record ``id`` is the idempotency key.  Unlike the legacy Chat writer,
    this seam intentionally performs no session metadata, cloud, or memory
    hooks; Live Voice CR owns the commit and PresentationAck boundaries.

    JSONL is the business source of truth.  The digest index is only a bounded,
    rebuildable single-process accelerator.  External file mutation and multiple
    process writers are unsupported, and this seam makes no fsync durability promise.
    """

    sid = str(session_id or "").strip()
    resolved, error_reason = resolve_session_dir(sid, create=False)
    if resolved is None:
        raise ValueError(error_reason or "invalid session_id")
    serialized = _serialize_value(record)
    if not isinstance(serialized, dict):
        raise TypeError("formal history record must be an object")
    record_id = serialized.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        raise ValueError("formal history record id must be non-empty")

    with _session_history_lock(sid) as state:
        target_path = _ensure_jsonl_bootstrap(sid)
        resolved_path = target_path.resolve(strict=False)
        if _repair_jsonl_tail(target_path):
            _invalidate_formal_index(state)
        if (
            state.formal_index is None
            or state.formal_index_path != resolved_path
        ):
            state.formal_index = _build_formal_history_index(target_path)
            state.formal_index_path = resolved_path

        digest = _canonical_record_digest(serialized)
        if record_id in state.formal_index:
            if state.formal_index[record_id] == digest:
                return False
            raise ValueError("formal history idempotency conflict")

        _append_record_jsonl(target_path, serialized)
        state.formal_index[record_id] = digest
    return True


def _ensure_worker_started() -> None:
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return

        def _worker() -> None:
            while True:
                sid, item = _WRITE_QUEUE.get()
                try:
                    _write_item(sid, item)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("history 异步写入失败: %s", exc)
                finally:
                    _WRITE_QUEUE.task_done()

        t = threading.Thread(target=_worker, name="session-history-writer", daemon=True)
        t.start()
        _WORKER_STARTED = True


def append_history_record(
    *,
    session_id: str,
    request_id: str,
    channel_id: str,
    role: str,
    content: Any,
    timestamp: float,
    event_type: str | None = None,
    extra: dict[str, Any] | None = None,
    channel_metadata: dict[str, Any] | None = None,
    mode: str | None = None,
) -> None:
    """向指定 session 的当前激活历史文件异步追加一条记录."""
    sid = (session_id or "default").strip() or "default"
    if _is_formal_live_voice_no_history_session(sid):
        logger.debug(
            "skip formal Live Voice implicit history: session_id=%s event_type=%s",
            sid,
            event_type or "",
        )
        return
    if _is_ephemeral_heartbeat_session(sid):
        logger.debug("skip heartbeat session history: session_id=%s event_type=%s", sid, event_type)
        return
    rid = str(request_id or "").strip()
    cid = str(channel_id or "").strip()
    role_norm = "assistant" if role == "assistant" else "user"
    content_text = content if isinstance(content, str) else str(content)
    if role_norm == "assistant" and not _has_persistable_assistant_payload(
        content_text=content_text,
        event_type=event_type,
        extra=extra,
    ):
        logger.debug(
            "skip empty assistant history: session_id=%s event_type=%s",
            sid,
            event_type or "",
        )
        return

    item: dict[str, Any] = {
        "id": f"{rid}:{role_norm}",
        "role": role_norm,
        "request_id": rid,
        "channel_id": cid,
        "timestamp": float(timestamp),
        "content": content_text,
    }
    if role_norm == "assistant" and event_type:
        item["event_type"] = event_type
    if isinstance(extra, dict) and extra:
        serialized_extra, extra_changed = _serialize_value_with_flag(extra)
        if isinstance(serialized_extra, dict):
            item.update(serialized_extra)
            if extra_changed:
                logger.debug(
                    "history payload sanitized: session_id=%s request_id=%s event_type=%s extra_keys=%s",
                    sid,
                    rid,
                    event_type or "",
                    list(serialized_extra.keys()),
                )
    if mode:
        item["mode"] = str(mode)

    _ensure_worker_started()
    try:
        _WRITE_QUEUE.put_nowait((sid, item))
    except queue.Full:
        # 队列满时退化为同步写，避免丢历史记录。
        _write_item(sid, item)

    # 更新会话元数据
    try:
        from jiuwenswarm.server.runtime.session.session_metadata import (
            set_session_delivery_context,
            update_session_metadata,
        )
        update_session_metadata(
            session_id=sid,
            channel_id=cid,
            increment_message_count=True,
            # 传入用户消息内容,用于自动生成标题
            user_content=content_text if role_norm == "user" else None,
            # 传入渠道元数据,首次写入时持久化
            channel_metadata=channel_metadata,
            mode=mode,
            # 用户消息时刷新 last_user_message_at(用消息时间戳,比请求到达时刻更精确;
            # 与 AgentServer 的 _sync_chat_request_metadata 互补,覆盖所有记录用户消息的路径)
            last_user_message_at=float(timestamp) if role_norm == "user" else None,
        )
        if role_norm == "user":
            set_session_delivery_context(
                session_id=sid,
                channel_id=cid,
                source_request_id=rid,
                route_metadata=channel_metadata,
            )
    except Exception as exc:
        logger.warning("更新会话元数据失败: %s", exc)


def append_compact_history_records(
    *,
    session_id: str,
    request_id: str,
    channel_id: str,
    summary: str | None,
    timestamp: float,
    trigger: str = "auto",
    stats: dict[str, Any] | None = None,
    mode: str | None = None,
) -> None:
    """Persist a compact boundary and optional transcript-only summary."""
    clean_summary = (summary or "").strip()
    metadata = {
        "compact_metadata": {
            "trigger": trigger,
            **(_serialize_value(stats) if isinstance(stats, dict) else {}),
        },
    }

    append_history_record(
        session_id=session_id,
        request_id=request_id,
        channel_id=channel_id,
        role="assistant",
        event_type="context.compact_boundary",
        content="Conversation compacted",
        timestamp=timestamp,
        extra=metadata,
        mode=mode,
    )

    if not clean_summary:
        return

    append_history_record(
        session_id=session_id,
        request_id=request_id,
        channel_id=channel_id,
        role="assistant",
        event_type="context.compact_summary",
        content=clean_summary,
        timestamp=timestamp + 0.001,
        extra={
            **metadata,
            "is_compact_summary": True,
            "transcript_only": True,
        },
        mode=mode,
    )


def truncate_history_records(*, session_id: str, cut_index: int) -> dict[str, Any]:
    """截断会话历史到指定位置（线程安全）。

    先等待异步写入队列刷盘，再持锁截断当前激活的历史文件。
    返回截断结果 dict，包含 remaining / removed 计数。
    """
    sid = (session_id or "default").strip() or "default"
    _WRITE_QUEUE.join()

    with _session_history_lock(sid) as state:
        fpath = get_read_history_path(sid)
        if not fpath.exists():
            return {"remaining_records": 0, "removed_records": 0}
        history = load_history_records(sid)
        if not isinstance(history, list):
            return {"remaining_records": 0, "removed_records": 0}
        total = len(history)
        if cut_index < 0:
            cut_index = 0
        if cut_index > total:
            cut_index = total
        truncated = history[:cut_index]
        target_path = _ensure_jsonl_bootstrap(sid)
        _write_records_to_path(target_path, truncated)
        _invalidate_formal_index(state)
        return {
            "remaining_records": len(truncated),
            "removed_records": total - len(truncated),
        }
