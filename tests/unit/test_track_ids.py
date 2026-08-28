import pytest

from scripts.core.errors import ContractError
from scripts.core.records import canonical_track_id, parse_canonical_track_id


def test_camera_namespace_prevents_numeric_track_collisions():
    assert canonical_track_id("cam1", 0) != canonical_track_id("cam2", 0)


def test_round_trip():
    value = canonical_track_id("cam2", "upstream-19")
    assert parse_canonical_track_id(value) == ("cam2", "upstream-19")


@pytest.mark.parametrize("legacy", ["0", "person_0", "cam1_person_0"])
def test_legacy_ids_are_rejected(legacy):
    with pytest.raises(ContractError):
        parse_canonical_track_id(legacy)

