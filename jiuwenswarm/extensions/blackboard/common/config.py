"""Blackboard settings in ``config.yaml`` under ``blackboard:``.

Only non-secret settings live there. Member tokens and host secrets are kept in
Blackboard's own files under ``<data root>/blackboard`` (see ``client/hosts.py``
and ``host/secrets.py``), so they never show up where config is displayed.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from jiuwenswarm.extensions.blackboard.common.errors import invalid
from jiuwenswarm.extensions.blackboard.common.origins import normalize_origin


@dataclass(frozen=True)
class HostSettings:
    enabled: bool = False
    # What members see in their list of Blackboards; empty means "<operator>'s Blackboard".
    name: str = ""
    # Loopback by default; serving other machines is an explicit choice.
    bind: str = "127.0.0.1"
    port: int = 19011
    doc_port: int = 19010
    doc_api_port: int = 19012
    public_url: str = ""
    doc_public_url: str = ""
    node_path: str = ""
    operator_name: str = ""
    max_upload_mb: int = 25
    # Web pages besides loopback ones whose browsers may open the host's WebSockets (live documents
    # and events), such as a web app served at https://jiuwen.example.com; see common/origins.py.
    allowed_origins: tuple[str, ...] = ()
    allow_any_origin: bool = False
    # Versions older than this many days are removed, except named ones and each document's
    # latest; 0 keeps every version.
    version_retention_days: int = 0

    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def base_url(self) -> str:
        """The address members use; this machine's loopback when none is set."""
        return self.public_url.rstrip("/") if self.public_url else self.local_url()

    def doc_url(self) -> str:
        """The WebSocket address browsers use for live documents."""
        if self.doc_public_url:
            return self.doc_public_url.rstrip("/")
        if self.public_url:
            parsed = urlparse(self.public_url)
            scheme = "wss" if parsed.scheme == "https" else "ws"
            return f"{scheme}://{parsed.hostname}:{self.doc_port}"
        return f"ws://127.0.0.1:{self.doc_port}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_BOOL_FIELDS = {"enabled", "allow_any_origin"}
_INT_FIELDS = {"port", "doc_port", "doc_api_port", "max_upload_mb", "version_retention_days"}
_STR_FIELDS = {"name", "bind", "public_url", "doc_public_url", "node_path", "operator_name"}
_LIST_FIELDS = {"allowed_origins"}
MAX_NAME_LENGTH = 60
EDITABLE_FIELDS = _BOOL_FIELDS | _INT_FIELDS | _STR_FIELDS | _LIST_FIELDS
# BLACKBOARD_HOST_<FIELD> in the environment overrides config.yaml, for containers
# (BLACKBOARD_HOST_ENABLED=1, BLACKBOARD_HOST_BIND=0.0.0.0, ...).
ENV_PREFIX = "BLACKBOARD_HOST_"


def _origins(name: str, value: Any) -> tuple[str, ...]:
    items = value.split(",") if isinstance(value, str) else value
    if not isinstance(items, (list, tuple)):
        raise invalid(f"{name} must be a list of origins", field=name)
    origins: list[str] = []
    for item in items:
        text = normalize_origin(str(item or ""))
        if not text:
            continue
        parsed = urlparse(text)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path or parsed.query:
            raise invalid(f"{name}: {item!r} is not an origin such as https://jiuwen.example.com", field=name)
        origins.append(text)
    return tuple(dict.fromkeys(origins))


def _coerce(name: str, value: Any) -> Any:
    if name in _LIST_FIELDS:
        return _origins(name, value)
    if name in _BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0"}:
            return value.strip().lower() in {"true", "1"}
        raise invalid(f"{name} must be true or false", field=name)
    if name in _INT_FIELDS:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise invalid(f"{name} must be a number", field=name) from exc
        if name == "max_upload_mb":
            if not 1 <= number <= 1024:
                raise invalid("max_upload_mb must be between 1 and 1024", field=name)
        elif name == "version_retention_days":
            if not 0 <= number <= 36500:
                raise invalid("version_retention_days must be between 0 (keep all) and 36500", field=name)
        elif not 1 <= number <= 65535:
            raise invalid(f"{name} must be a port between 1 and 65535", field=name)
        return number
    text = "" if value is None else str(value).strip()
    if name in {"public_url", "doc_public_url"} and text:
        parsed = urlparse(text)
        allowed = ("http", "https") if name == "public_url" else ("ws", "wss")
        if parsed.scheme not in allowed or not parsed.netloc:
            raise invalid(f"{name} must start with {allowed[0]}:// or {allowed[1]}://", field=name)
    if name == "bind" and not text:
        raise invalid("bind must not be empty", field=name)
    if name in {"name", "operator_name"}:
        text = " ".join(text.split())
        if len(text) > MAX_NAME_LENGTH:
            raise invalid(f"{name} must be at most {MAX_NAME_LENGTH} characters", field=name)
    return text


def host_settings_from(config: Any, env: Mapping[str, str] | None = None) -> HostSettings:
    """Settings from a parsed config, then ``BLACKBOARD_HOST_*`` variables in ``env``; unknown or
    broken values fall back to defaults."""
    section = config.get("blackboard") if isinstance(config, dict) else None
    host = section.get("host") if isinstance(section, dict) else None
    sources: dict[str, Any] = dict(host) if isinstance(host, dict) else {}
    for name in env_overrides(env):
        sources[name] = (env or {})[ENV_PREFIX + name.upper()]
    values: dict[str, Any] = {}
    for name in EDITABLE_FIELDS:
        if name in sources and sources[name] is not None:
            try:
                values[name] = _coerce(name, sources[name])
            except Exception:  # noqa: BLE001 - a broken value falls back to its default
                continue
    return replace(HostSettings(), **values)


def env_overrides(env: Mapping[str, str] | None) -> list[str]:
    """The settings that environment variables fix, whatever config.yaml says."""
    if not env:
        return []
    return sorted(name for name in EDITABLE_FIELDS if env.get(ENV_PREFIX + name.upper(), "") != "")


def im_owner_ids_from(config: Any) -> list[str]:
    """``blackboard.im_owner_ids``: the IM accounts (``<platform>:<user id>`` or a bare user id) that
    read Blackboard through this personal jiuwenswarm; empty means whoever its IM channels let in."""
    section = config.get("blackboard") if isinstance(config, dict) else None
    ids = section.get("im_owner_ids") if isinstance(section, dict) else None
    return [str(i).strip() for i in ids if str(i).strip()] if isinstance(ids, list) else []


def load_im_owner_ids() -> list[str]:
    from jiuwenswarm.common.config import get_config

    return im_owner_ids_from(get_config())


def load_host_settings() -> HostSettings:
    from jiuwenswarm.common.config import get_config

    return host_settings_from(get_config(), os.environ)


def validate_updates(updates: dict[str, Any]) -> dict[str, Any]:
    unknown = set(updates) - EDITABLE_FIELDS
    if unknown:
        raise invalid(f"unknown settings: {', '.join(sorted(unknown))}", fields=sorted(unknown))
    return {name: _coerce(name, value) for name, value in updates.items()}


def save_host_settings(
    updates: dict[str, Any],
    update_config: Callable[[Callable[[Any], Any]], Any] | None = None,
) -> HostSettings:
    """Write validated values under ``blackboard.host`` with the core config writer."""
    clean = validate_updates(updates)
    if update_config is None:
        from jiuwenswarm.common.config import update_config as core_update_config

        update_config = core_update_config

    def mutate(data: Any) -> Any:
        if data is None:
            data = {}
        section = data.get("blackboard")
        if not isinstance(section, dict):
            data["blackboard"] = {}
            section = data["blackboard"]
        host = section.get("host")
        if not isinstance(host, dict):
            section["host"] = {}
            host = section["host"]
        for name, value in clean.items():
            host[name] = list(value) if isinstance(value, tuple) else value
        return data

    written = update_config(mutate)
    return host_settings_from(written, os.environ)
