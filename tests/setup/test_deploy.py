"""deploy.sh must never guess where it is deploying."""
from pathlib import Path
import subprocess


def test_deploy_refuses_to_run_without_an_explicit_target():
    """Deployment must never guess its destination."""
    script = Path("scripts/setup/deploy.sh")

    completed = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, cwd=Path.cwd()
    )

    assert completed.returncode == 4
    assert "no target given" in completed.stderr
    # No default target may be assigned.
    assert "DEFAULT_TARGET=" not in script.read_text(encoding="utf-8")
