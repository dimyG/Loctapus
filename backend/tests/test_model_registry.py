"""Tests for the entry-point model registry, mostly in fresh interpreters.

The pytest process has already imported every module through conftest, so the
registry's completeness is checked through subprocesses where the import state
is honest.
"""

import ast
import pkgutil
import subprocess
import sys
from pathlib import Path

import pytest

import app

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENTRY_POINTS = ("app.main", "app.workers.celery_app", "app.workers.dispatcher")


def _registry_imports() -> set[str]:
    """Return the dotted module names app/models.py imports."""

    path = BACKEND_DIR / "app" / "models.py"
    assert path.is_file(), f"missing model registry: {path}"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _run_fresh(*, code: str) -> None:
    """Run ``code`` in a fresh interpreter from BACKEND_DIR and require success."""

    subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, check=True)


def test_registry_imports_every_models_module() -> None:
    """Check that app/models.py imports every models module under app/."""

    found = {
        name
        for _, name, _ in pkgutil.walk_packages(app.__path__, "app.")
        if name.endswith(".models") and name != "app.models"
    }
    missing = found - _registry_imports()
    assert not missing, f"app/models.py must import the models modules: {sorted(missing)}"


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_entry_point_loads_the_registry(*, entry_point: str) -> None:
    """Check in a fresh interpreter that the entry point pulls in the registry."""

    _run_fresh(code=f"import sys, {entry_point}; assert 'app.models' in sys.modules")


def test_every_foreign_key_target_resolves() -> None:
    """Check in a fresh interpreter that every FK target table is registered."""

    _run_fresh(
        code=(
            "import app.models; "
            "from app.core.models import Base; "
            "assert all("
            "fk.column is not None "
            "for table in Base.metadata.tables.values() "
            "for fk in table.foreign_keys"
            ")"
        )
    )
