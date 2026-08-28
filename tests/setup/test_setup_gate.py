from __future__ import annotations

from pathlib import Path

from scripts.setup import preflight


ROOT = Path(__file__).resolve().parents[2]


def test_deploy_is_one_additive_rsync_with_required_excludes():
    source = (ROOT / "scripts" / "setup" / "deploy.sh").read_text(encoding="utf-8")
    command_lines = [line for line in source.splitlines() if line.startswith("rsync ")]
    assert len(command_lines) == 1
    command = command_lines[0]
    for excluded in (
        ".venv/",
        "__pycache__/",
        ".git/",
        "data/sessions/",
        "models/",
        "node_modules/",
        "*.bak-*",
    ):
        assert f"--exclude='{excluded}'" in command
    assert "--" + "delete" not in command


def test_scheduler_scripts_do_not_pin_private_cluster_names():
    for script in (ROOT / "scripts").glob("*.sbatch"):
        source = script.read_text(encoding="utf-8")
        assert "#SBATCH --partition=" not in source
        assert "#SBATCH --nodelist=" not in source


def test_collect_failures_lists_every_non_ok_model(monkeypatch):
    monkeypatch.setattr(preflight, "load_components", lambda: [{"component_id": "unused"}])
    monkeypatch.setattr(
        preflight,
        "blocking_components",
        lambda _components: [
            ("missing_model", "MISSING", "missing models/model.bin"),
            ("unresolved_model", "STAGED", "present but SHA-256 is unresolved"),
        ],
    )
    assert preflight.collect_failures(run_tests=False) == [
        "MODEL missing_model: MISSING — missing models/model.bin",
        "MODEL unresolved_model: STAGED — present but SHA-256 is unresolved",
    ]
