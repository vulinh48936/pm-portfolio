"""Validate and load generated Strategy code.

Two checks:
  1. Top level may only contain import / def / class / literal assignment, so nothing
     executes at import time.
  2. EVERY import, at any depth, must be whitelisted, and names that load or run code
     dynamically (`__import__`, `eval`, `exec`, `open`) are rejected.

The second check matters: `allocate()` runs during the backtest, so an `import os`
inside a function body would escape a top-level-only scan.

This is not a real sandbox: the code still runs in the same Python process with the
same rights. It stops mistakes and raises the bar, not a determined attacker. That is
why the job runs backtests in a child process with a timeout, and why the app belongs
behind company authentication.
"""

from __future__ import annotations

import ast

from app.lab.strategy import Strategy

# Modules a strategy may import
_ALLOWED_IMPORT_ROOTS = {
    "numpy", "pandas", "math", "scipy", "sklearn",
    "app.lab.lib", "app.lab.strategy", "app.lab.features",
}

# Names that load or execute code dynamically; they would defeat the whitelist.
_FORBIDDEN_NAMES = {
    "__import__", "eval", "exec", "compile", "open", "globals", "locals",
    "vars", "input", "breakpoint", "memoryview",
}


def _is_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all((k is None or _is_literal(k)) and _is_literal(v)
                   for k, v in zip(node.keys, node.values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _is_literal(node.operand)
    return False


def _safe_constant_assign(node: ast.AST) -> bool:
    if isinstance(node, ast.Assign):
        return _is_literal(node.value)
    if isinstance(node, ast.AnnAssign):
        return node.value is None or _is_literal(node.value)
    return False


def _check_import(node: ast.Import | ast.ImportFrom) -> None:
    if isinstance(node, ast.ImportFrom):
        root = (node.module or "").split(".")[0]
        full = node.module or ""
        if full not in _ALLOWED_IMPORT_ROOTS and root not in _ALLOWED_IMPORT_ROOTS:
            raise ValueError(f"Import không được phép: from {full}")
    else:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if alias.name not in _ALLOWED_IMPORT_ROOTS and root not in _ALLOWED_IMPORT_ROOTS:
                raise ValueError(f"Import không được phép: import {alias.name}")


def validate_strategy_source(code: str) -> None:
    """Walk the AST; raise ValueError if either check above fails."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Cú pháp không hợp lệ: {exc}") from exc

    # Check 2: imports at any depth, plus forbidden names
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _check_import(node)
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise ValueError(f"Không được dùng {node.id!r} trong code chiến lược.")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_NAMES:
            raise ValueError(f"Không được dùng thuộc tính {node.attr!r} trong code chiến lược.")

    # Check 1: top level is import / def / class / literal assignment only
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # docstring
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _check_import(node)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.decorator_list:
                raise ValueError(f"Decorator không được phép trên {node.name!r}")
            continue
        if _safe_constant_assign(node):
            continue
        raise ValueError(
            f"Statement top-level không được phép: {type(node).__name__} "
            f"(chỉ cho import / def / class / gán hằng)"
        )


def load_strategy(code: str) -> type[Strategy]:
    """Validate, exec the code and return the Strategy subclass. No backtest here."""
    validate_strategy_source(code)
    ns: dict = {}
    exec(compile(code, "<strategy>", "exec"), ns)  # noqa: S102 - AST-checked above
    candidates = [
        v for v in ns.values()
        if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
    ]
    if not candidates:
        raise ValueError("Không tìm thấy subclass của Strategy trong code.")
    cls = candidates[-1]
    if cls.allocate is Strategy.allocate:
        raise ValueError("Strategy phải override allocate().")
    return cls
