"""A guardrail, not proof: this only catches the easy mistake of a router
bypassing app.permissions.resolver and querying models/ACL tables itself.
The load-bearing evidence that unauthorized data can't reach a client is
the behavioral tests in test_accounts_api.py, test_commitments_api.py and
test_chunks_api.py, which exercise the real HTTP routes end to end."""

import ast
from pathlib import Path

ROUTERS_DIR = Path(__file__).resolve().parent.parent / "src" / "app" / "routers"
FORBIDDEN_MODULES = ("app.models", "sqlalchemy")

# Routers may type-hint the injected db session as `Session` for FastAPI's
# `Depends(get_db)` — that's plumbing, not query construction. Anything
# else from sqlalchemy (select, exists, joinedload, ORM models, ...) means
# a router is building its own query instead of going through the resolver.
ALLOWED_SQLALCHEMY_IMPORT = ("sqlalchemy.orm", frozenset({"Session"}))


def _forbidden_import(source: str) -> str | None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name == mod or alias.name.startswith(mod + ".") for mod in FORBIDDEN_MODULES):
                    return alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            if not any(node.module == mod or node.module.startswith(mod + ".") for mod in FORBIDDEN_MODULES):
                continue
            allowed_module, allowed_names = ALLOWED_SQLALCHEMY_IMPORT
            imported_names = {alias.name for alias in node.names}
            if node.module == allowed_module and imported_names <= allowed_names:
                continue
            return node.module
    return None


def test_routers_do_not_import_models_or_sqlalchemy_directly():
    router_files = sorted(ROUTERS_DIR.glob("*.py"))
    assert router_files, "expected router files to exist"

    for path in router_files:
        forbidden = _forbidden_import(path.read_text())
        assert forbidden is None, (
            f"{path.name} imports {forbidden!r} directly; it must go through "
            "app.permissions.resolver instead of touching models/ACL tables itself"
        )
