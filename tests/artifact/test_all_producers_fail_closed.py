"""Every metric producer must reach a definition gate.

Phase 7 requires that "any unresolved definition blocks output". The per-metric tests
cover the producers that existed when they were written; this test covers the set
itself, so a producer added later without a definition gate fails here instead of
silently emitting a number in paper mode.

This is a static call-graph check rather than a runtime one. Python binds arguments
before a function body executes, so calling a producer with no arguments raises
TypeError before any gate could run — a runtime probe would prove nothing.
"""

import ast
import inspect

import pytest

from scripts.metrics import definitions as metric_definitions


GATES = {"_require_metric_definition", "require_table3_definition"}
BLOCKING_ERROR = "MetricDefinitionUnresolvedError"

_MODULE = ast.parse(inspect.getsource(metric_definitions))
_FUNCTIONS = {
    node.name: node
    for node in _MODULE.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}


def _reaches_gate(name, seen=None):
    """True when this function calls a gate, raises the blocking error, or delegates to one."""
    seen = seen or set()
    if name in seen or name not in _FUNCTIONS:
        return False
    seen.add(name)
    node = _FUNCTIONS[name]

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            called = child.func
            called_name = getattr(called, "id", None) or getattr(called, "attr", None)
            if called_name in GATES:
                return True
            if called_name and called_name != name and _reaches_gate(called_name, seen):
                return True
        if isinstance(child, ast.Raise):
            if BLOCKING_ERROR in ast.dump(child):
                return True
    return False


def _producers():
    for name, function in vars(metric_definitions).items():
        if not name.startswith("compute_") or not inspect.isfunction(function):
            continue
        if "paper_mode" not in inspect.signature(function).parameters:
            continue
        yield name


def test_the_producer_set_is_not_empty():
    # Guards against the reflection matching nothing and vacuously passing.
    assert len(list(_producers())) >= 20


def test_the_gate_detector_rejects_an_ungated_function():
    # Guards against _reaches_gate returning True for everything.
    assert not _reaches_gate("_average_ranks")


@pytest.mark.parametrize("name", sorted(_producers()))
def test_every_producer_reaches_a_definition_gate(name):
    assert _reaches_gate(name), (
        f"{name} never reaches {' or '.join(sorted(GATES))} and never raises "
        f"{BLOCKING_ERROR}, so it can emit a value in paper mode with its "
        "definitions unresolved"
    )
