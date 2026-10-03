"""What the wiring promises: every configuration key is read, every tool is in the
permission table, and the hooks sit where the core files need them to sit."""

from __future__ import annotations

import ast
import dataclasses
import glob
import inspect
import pathlib
import re

import yaml

import jiuwenswarm
from jiuwenswarm.clouddoc.tools.toolkit import UNATTENDED_ALLOWLIST, UNATTENDED_DENYLIST
from jiuwenswarm.clouddoc.watch.triggers import TriggerConfig

REPO = pathlib.Path(jiuwenswarm.__file__).resolve().parents[1]
CONFIG = pathlib.Path(jiuwenswarm.__file__).parent / "resources" / "config.yaml"


def _clouddoc_config() -> dict:
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["clouddoc"]


def test_every_shipped_config_key_is_consumed():
    """Every key in config.yaml's clouddoc section must actually be read.

    The scan set is derived from the package directory, never a hard-coded file
    list, so a key read from any module counts. What it compares are string
    literals in the AST, excluding docstrings and write subscripts such as
    ``section["connections"] = ...``: a comment or a write-back is not a read.
    """
    cfg = _clouddoc_config()
    keys = {k for k in cfg if k != "rail"} | set(cfg.get("rail") or {})

    files = glob.glob(str(REPO / "jiuwenswarm" / "clouddoc" / "**" / "*.py"), recursive=True)
    used: set[str] = set()
    for f in files:
        with open(f, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        skip = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and n.body
            and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)
            and isinstance(n.body[0].value.value, str)
        }
        skip |= {
            id(n.slice)
            for n in ast.walk(tree)
            if isinstance(n, ast.Subscript) and not isinstance(n.ctx, ast.Load)
        }
        used |= {
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
        }

    unread = sorted(keys - used)
    assert not unread, f"no code reads these configuration keys: {unread}"


def test_trigger_config_fields_all_come_from_config():
    """The reverse: every configurable field of TriggerConfig needs a key in config.yaml.
    ``sa_address`` is derived per connection from the credentials, not read."""
    cfg = _clouddoc_config()
    fields = {f.name for f in dataclasses.fields(TriggerConfig)} - {"sa_address"}
    assert fields <= set(cfg), f"these fields have no configuration key: {sorted(fields - set(cfg))}"


def test_every_clouddoc_tool_is_registered_in_the_permission_table():
    """An unlisted tool is not "unconstrained": the permission layer falls to
    ``level is None`` and resolves that to deny. So a tool missing here works fine
    until a deployment sets permissions.enabled and then fails closed, silently."""
    text = CONFIG.read_text("utf-8")
    listed = set(re.findall(r"^\s+(clouddoc_\w+): ", text, re.M))
    actual = UNATTENDED_ALLOWLIST | UNATTENDED_DENYLIST
    assert actual - listed == set(), f"missing from the permission table: {sorted(actual - listed)}"
    assert listed - actual == set(), f"in the permission table but gone: {sorted(listed - actual)}"


def test_the_unattended_decision_precedes_the_ask_user_bypass():
    """ask_user is let through unconditionally outside avatar scenarios, and calling
    it in an unattended session hangs until the turn times out; the ``perm_ctx is
    None`` early return would likewise leave the decision unreachable."""
    from jiuwenswarm.agents.harness.common.rails.interrupt import interrupt_helpers

    src = inspect.getsource(interrupt_helpers)
    i_scene = src.index("unattended_scene(inp.normalized_tool_name")
    i_askuser = src.index('inp.normalized_tool_name == "ask_user"')
    i_permctx = src.index("if perm_ctx is None:")
    assert i_scene < i_askuser
    assert i_scene < i_permctx


def test_the_adapter_refreshes_the_snapshot_on_every_session_update():
    """The call sits at the end of the session-tools update, on the path every
    request takes, so a chat turn empties the snapshot."""
    from jiuwenswarm.server.runtime.agent_adapter import interface_deep

    src = inspect.getsource(interface_deep.JiuWenSwarmDeepAdapter._update_session_tools)
    assert "self._clouddoc.update(" in src
    assert "config_base=config_base" in src.split("self._clouddoc.update(")[1]


def test_the_gateway_prepares_binds_starts_and_stops_the_service():
    from jiuwenswarm.gateway import app_gateway

    src = inspect.getsource(app_gateway)
    order = [src.index(s) for s in (
        "await clouddoc.prepare(agent_client=client)",
        "clouddoc_panel=clouddoc.panel",
        "await clouddoc.start()",
        "await clouddoc.stop()",
        "await client.disconnect()",
    )]
    assert order == sorted(order)


def test_the_team_whitelist_carries_every_toolkit_tool():
    """The team runtime filters inherited abilities against the whitelist and logs a
    miss at debug, so a tool left out of it disappears with no error anywhere."""
    from jiuwenswarm.agents.harness.team.team_runtime_inheritance import TOOL_WHITELIST
    from jiuwenswarm.clouddoc.tools.toolkit import ALL_TOOL_NAMES

    assert set(ALL_TOOL_NAMES) <= TOOL_WHITELIST


def test_run_span_cleanup_is_bound_outside_the_try_block():
    """A name used in ``finally`` must be bound in the same function, before the
    ``try``: imported inside the try, it fails the finally with UnboundLocalError on
    every earlier exception and swallows the real one. Checked on the AST, since the
    defect shows only on exceptional paths."""
    from jiuwenswarm.server.runtime.agent_adapter import interface_deep

    NAME = "close_agent_run_span"

    def binds(node) -> bool:
        return isinstance(node, ast.ImportFrom) and any(a.name == NAME for a in node.names)

    def calls(stmts) -> bool:
        return any(
            isinstance(n, ast.Call) and getattr(n.func, "id", "") == NAME
            for stmt in stmts
            for n in ast.walk(stmt)
        )

    tree = ast.parse(inspect.getsource(interface_deep))
    checked = 0
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bind_lines = [n.lineno for n in ast.walk(func) if binds(n)]
        for node in ast.walk(func):
            if not isinstance(node, ast.Try) or not calls(node.finalbody):
                continue
            checked += 1
            assert any(line < node.lineno for line in bind_lines), (
                f"{func.name} calls {NAME} in a finally without binding it before the try"
            )
    assert checked
