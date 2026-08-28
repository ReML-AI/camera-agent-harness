"""The overlay identifies people from tracking ids, with hand-labelled roles optional."""
from scripts.analytics.compute_video_overlay import (
    ROLE_COLORS,
    derive_roles_from_tracks,
    identity_color,
    load_roles,
)


def _tracks():
    return {"persons": [{"person_id": 1}, {"person_id": 2}, {"person_id": 3}]}


def test_roles_are_derived_from_tracking_identities():
    """No annotation file exists for the current recordings, but the tracker has ids."""
    assert derive_roles_from_tracks(_tracks()) == {
        "cam1_person_1": {"role": "Person 1", "notes": ""},
        "cam1_person_2": {"role": "Person 2", "notes": ""},
        "cam1_person_3": {"role": "Person 3", "notes": ""},
    }


def test_derived_keys_match_the_bbox_index_key_format():
    """build_person_bbox_index keys on cam1_person_<id>; a mismatch renders no one."""
    assert set(derive_roles_from_tracks(_tracks())) == {
        f"cam1_person_{n}" for n in (1, 2, 3)
    }


def test_hand_labelled_roles_still_win_when_present():
    roles = load_roles({"person_labels": {"cam1_person_1_frame_0": {"role": "Patient/Mannequin"}}})
    assert roles["cam1_person_1"]["role"] == "Patient/Mannequin"


def test_known_roles_keep_their_palette_colour():
    assert identity_color("cam1_person_1", "Patient/Mannequin") == ROLE_COLORS["Patient/Mannequin"]


def test_identity_labels_get_a_stable_colour_per_person():
    first = identity_color("cam1_person_2", "Person 2")
    assert first == identity_color("cam1_person_2", "Person 2")
    assert first != identity_color("cam1_person_3", "Person 3")
