"""`serve` has no refresh or upstream path (F011 FR-012, FR-017; constitution I)."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src" / "score_docs_assistant"
FORBIDDEN = (
    "score_docs_assistant.refresh",
    "score_docs_assistant.sources.sync",
    "score_docs_assistant.sources.http_fetch",
    "score_docs_assistant.sources.git_client",
    "score_docs_assistant.cli.refresh",
)


def _serve_modules() -> list[Path]:
    return [*sorted((SRC / "api").rglob("*.py")), SRC / "cli" / "serve.py"]


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_serve_modules_import_no_refresh_or_acquisition_code() -> None:
    offenders = {
        str(path.relative_to(SRC)): sorted(
            name for name in _imports(path) if name.startswith(FORBIDDEN)
        )
        for path in _serve_modules()
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_no_http_route_mentions_refresh() -> None:
    for path in _serve_modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            is_path = isinstance(node, ast.Constant) and isinstance(node.value, str)
            if is_path and node.value.startswith("/"):  # type: ignore[attr-defined]
                assert "refresh" not in node.value.lower(), (path, node.value)  # type: ignore[attr-defined]


def test_server_app_does_not_load_refresh_modules_transitively() -> None:
    """`cli/serve.py` itself is covered by the AST check above; importing it also loads `cli.main`,
    which registers every subcommand (loading is not executing), so only the app is checked here."""
    import subprocess
    import sys

    code = (
        "import sys, score_docs_assistant.api.app\n"
        f"bad = sorted(m for m in sys.modules if m.startswith({FORBIDDEN!r}))\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
