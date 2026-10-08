"""Style checks for rules that ruff and mypy cannot express."""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
STYLE_DIRS = ("app", "tests")

_DocstringOwner = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def _python_files(*directories: str) -> list[Path]:
    """Return every Python file under ``directories``, sorted for stable output."""

    return sorted(path for directory in directories for path in (BACKEND_DIR / directory).rglob("*.py"))


def _docstring_statement(*, node: _DocstringOwner) -> ast.Expr | None:
    """Return the docstring statement when ``node`` opens with a string literal."""

    if not node.body:
        return None
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first
    return None


def test_docstrings_are_followed_by_a_blank_line() -> None:
    """Fail when a docstring is not separated from the following statement by a blank line."""

    offenders: list[str] = []
    for path in _python_files(*STYLE_DIRS):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            stmt = _docstring_statement(node=node)
            # A docstring that is the whole body has nothing following it.
            if stmt is None or len(node.body) < 2:
                continue
            end = stmt.end_lineno
            # Typeshed keeps end_lineno optional, but parsed trees always populate it.
            if end is None or end >= len(lines):
                continue
            if lines[end].strip():
                offenders.append(f"{path.relative_to(BACKEND_DIR)}:{end + 1}")
    assert not offenders, "docstrings must be followed by a blank line:\n" + "\n".join(offenders)


def test_private_functions_and_methods_have_docstrings() -> None:
    """Fail when a private function or method opens without a docstring."""

    offenders: list[str] = []
    for path in _python_files(*STYLE_DIRS):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Dunder names are Python's public interface hooks, not private definitions.
            is_dunder = node.name.startswith("__") and node.name.endswith("__")
            if not node.name.startswith("_") or is_dunder:
                continue
            if _docstring_statement(node=node) is None:
                offenders.append(f"{path.relative_to(BACKEND_DIR)}:{node.lineno}: {node.name}")
    assert not offenders, "private functions and methods need a docstring:\n" + "\n".join(offenders)
