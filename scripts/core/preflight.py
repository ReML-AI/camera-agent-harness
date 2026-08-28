"""Validate a new-run manifest without starting extraction."""

import argparse
import json
from pathlib import Path

from scripts.core.schema import validate_record


def validate_paper_preflight(session_manifest: Path) -> dict:
    with session_manifest.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    validate_record("session", manifest)
    return {"status": "ready", "session_id": manifest["session_id"]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail-closed preflight for a new authorized paper-mode run"
    )
    parser.add_argument("--session-manifest", type=Path, required=True)
    args = parser.parse_args()
    result = validate_paper_preflight(args.session_manifest)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
