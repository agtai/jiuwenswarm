"""Production dependency boundaries for the integrated speech channel."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return [name for node in ast.walk(tree) for name in (
        [alias.name for alias in node.names] if isinstance(node, ast.Import)
        else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
    )]


def test_host_services_do_not_depend_on_voice_channel_or_test_support():
    paths = list((ROOT / "jiuwenswarm/server/runtime").rglob("*.py"))
    paths += list((ROOT / "jiuwenswarm/common/schema").glob("native_*.py"))
    paths += list((ROOT / "jiuwenswarm/common/telemetry").rglob("*.py"))
    for path in paths:
        for module in imports(path):
            assert not module.startswith(("jiuwenswarm.channels.live_voice", "tests.")), (path, module)


def test_old_voice_production_package_is_retired():
    assert not list((ROOT / "jiuwenswarm/server/live_voice").glob("*.py"))
    assert not list((ROOT / "live-voice").rglob("*.py"))


def test_common_telemetry_has_no_host_task_dependency():
    for path in (ROOT / "jiuwenswarm/common/telemetry").rglob("*.py"):
        assert not any(module.startswith("jiuwenswarm.server") for module in imports(path))
