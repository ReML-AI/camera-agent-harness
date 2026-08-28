#!/usr/bin/env python3
"""Attach author-supplied participant roles to canonical speaker identities.

The paper path does not infer cross-camera identity from appearance or invent a role.
"""

import argparse
import json
from pathlib import Path

from scripts.core.errors import ContractError


def attach_authorized_roles(identity_map: dict, role_manifest: dict) -> dict:
    if role_manifest.get("schema_version") != "1.0.0":
        raise ContractError("role manifest must declare schema_version 1.0.0")
    roles = role_manifest.get("speaker_roles", {})
    output = []
    for speaker in identity_map.get("speakers", []):
        speaker_id = speaker["speaker_id"]
        if speaker_id not in roles:
            raise ContractError(f"author-supplied role missing for speaker {speaker_id}")
        output.append({"speaker_id": speaker_id, "role": roles[speaker_id]})
    unknown = set(roles) - {item["speaker_id"] for item in identity_map.get("speakers", [])}
    if unknown:
        raise ContractError(f"role manifest contains unknown speakers: {sorted(unknown)}")
    return {"schema_version": "1.0.0", "speaker_roles": output}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and attach authorized roles")
    parser.add_argument("--identity-map", required=True)
    parser.add_argument("--role-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with Path(args.identity_map).open("r", encoding="utf-8") as handle:
        identity_map = json.load(handle)
    with Path(args.role_manifest).open("r", encoding="utf-8") as handle:
        role_manifest = json.load(handle)
    output = attach_authorized_roles(identity_map, role_manifest)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)


if __name__ == "__main__":
    main()
