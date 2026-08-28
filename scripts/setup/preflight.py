#!/usr/bin/env python3
"""Fail-closed setup gate for model assets and tests."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    from .fetch_models import blocking_components, load_components
except ImportError:  # Direct invocation: python scripts/setup/preflight.py
    from fetch_models import blocking_components, load_components


ROOT = Path(__file__).resolve().parent.parent.parent


def pytest_status() -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return result.returncode, output


def collect_failures(*, run_tests: bool = True) -> list[str]:
    failures = [
        f"MODEL {component_id}: {state} — {detail}"
        for component_id, state, detail in blocking_components(load_components())
    ]
    if run_tests:
        returncode, output = pytest_status()
        if returncode:
            summary = output.splitlines()[-1] if output else "no pytest output"
            failures.append(f"PYTEST exit {returncode}: {summary}")
    return failures


def main() -> int:
    failures = collect_failures()
    if failures:
        print("PREFLIGHT FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PREFLIGHT PASSED: all model assets verify and pytest passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
