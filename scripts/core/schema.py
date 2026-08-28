"""JSON Schema validation helpers for versioned paper contracts."""

from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError
from jsonschema import Draft202012Validator


SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "v1"


def load_schema(name: str) -> dict[str, Any]:
    import json

    path = SCHEMA_ROOT / f"{name}.schema.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_record(name: str, record: dict[str, Any]) -> None:
    """Validate and, on failure, say WHERE.

    jsonschema's default message is the value alone -- "None is not of type 'string'" --
    with no path, so a failure inside a nested list of resolved evidence gives no way to
    find the offending field without bisecting the record by hand. The instance path and
    schema path are cheap to attach and turn that into a direct lookup.
    """
    validator = Draft202012Validator(load_schema(name))
    errors = sorted(validator.iter_errors(record), key=lambda error: list(error.absolute_path))
    if not errors:
        return
    first = errors[0]
    location = "/".join(str(part) for part in first.absolute_path) or "<root>"
    schema_location = "/".join(str(part) for part in first.absolute_schema_path)
    raise ValidationError(
        f"{name} record is invalid at {location}: {first.message} "
        f"(schema {schema_location}; {len(errors)} error(s) total)"
    )

