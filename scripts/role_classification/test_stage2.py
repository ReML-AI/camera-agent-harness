#!/usr/bin/env python3
"""Manual setup check for canonical identity and author-supplied role manifests."""

import argparse
import json
from pathlib import Path

from scripts.role_classification.predict_roles import attach_authorized_roles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-map", required=True)
    parser.add_argument("--role-manifest", required=True)
    args = parser.parse_args()
    with Path(args.identity_map).open("r", encoding="utf-8") as handle:
        identity = json.load(handle)
    with Path(args.role_manifest).open("r", encoding="utf-8") as handle:
        roles = json.load(handle)
    result = attach_authorized_roles(identity, roles)
    print(f"Validated {len(result['speaker_roles'])} canonical speaker roles")


if __name__ == "__main__":
    main()
