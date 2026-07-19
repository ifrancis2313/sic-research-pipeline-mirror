"""Proves, via static analysis of the actual source tree, that the private
executor implementation classes never leak outside trade_execution/.

executors.py's own docstring says "Python privacy is a convention, not a
security boundary" -- true, but that means the convention needs something
stronger than a docstring backing it. This walks every module in src/qepm/
(outside trade_execution/ itself) and fails if any of them import or
reference _AdvisorPassthroughExecutor or _WalkingSkeletonDemoExecutor by
name, so the "advisor formatter is private, nothing else touches it" claim
in README.md is an enforced invariant, not just an assertion. Mirrors the
same pattern as tests/trade_execution/test_execute.py's __all__/dir() checks,
but at the whole-codebase level rather than one module's public surface.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "qepm"
_PRIVATE_EXECUTOR_NAMES = {"_AdvisorPassthroughExecutor", "_WalkingSkeletonDemoExecutor"}
_ALLOWED_MODULE_PREFIX = "trade_execution"


def _names_referenced(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_private_executor_classes_are_never_referenced_outside_trade_execution():
    offending: dict[str, set[str]] = {}

    for path in _SRC_ROOT.rglob("*.py"):
        relative = path.relative_to(_SRC_ROOT)
        if relative.parts[0] == _ALLOWED_MODULE_PREFIX:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        hits = _names_referenced(tree) & _PRIVATE_EXECUTOR_NAMES
        if hits:
            offending[str(relative)] = hits

    assert offending == {}, (
        f"Private executor classes referenced outside trade_execution/: {offending}. "
        "Only trade_execution/ may construct or call these directly -- every other "
        "module must go through execute_proposed_trade()/execute_live_proposed_trade()."
    )


def test_this_check_actually_detects_a_real_violation():
    """A pure static-analysis test can silently stop testing anything if the
    AST-walking logic itself has a bug (e.g. a typo in the class name). This
    confirms the detector fires on a source string that genuinely contains
    the exact violation the test above is guarding against."""
    violating_source = "from qepm.trade_execution.executors import _AdvisorPassthroughExecutor\n"

    hits = _names_referenced(ast.parse(violating_source)) & _PRIVATE_EXECUTOR_NAMES

    assert hits == {"_AdvisorPassthroughExecutor"}
