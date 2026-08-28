from __future__ import annotations

import json

import pytest

# train_classifier imports sklearn at module level. The contract test venv is
# deliberately minimal, so skip there rather than error; this runs wherever the full
# requirements are installed, which is where the training path actually matters.
pytest.importorskip("sklearn", reason="train_classifier requires scikit-learn")

from scripts.role_classification import train_classifier  # noqa: E402


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _person(person_id, role_embedding=True):
    value = {
        "person_id": person_id,
        "track_id": person_id + 10,
        "total_screen_time_seconds": 12.5 + person_id,
    }
    if role_embedding:
        value["embedding"] = [float(person_id)] * train_classifier.EMBEDDING_WIDTH
    return value


def test_explain_inputs_needs_no_private_artifacts(capsys):
    assert train_classifier.main(["--explain-inputs"]) == 0
    output = capsys.readouterr().out
    assert "not present in this repository" in output
    assert "Do not derive or fabricate clinical roles" in output
    assert "must not gate the retrained artifact" in output
    assert "capture_at_run" in output


def test_default_path_fails_closed_when_tracks_are_absent(tmp_path, capsys):
    result = train_classifier.main(
        ["--labels", str(tmp_path / "labels.json"), "--tracks-dir", str(tmp_path)]
    )
    assert result == 2
    assert "no person_tracks_*.json files found" in capsys.readouterr().err


def test_prepare_training_data_accepts_matching_authorized_inputs(tmp_path):
    labels = _write_json(
        tmp_path / "labels.json",
        {
            "person_labels": {
                "cam1_person_1": {"role": "Student Nurse (Primary)"},
                "cam1_person_2": {"role": "Supervising Nurse/Doctor"},
            }
        },
    )
    tracks = _write_json(
        tmp_path / "person_tracks_cam1.json",
        {"camera_id": "cam1", "persons": [_person(1), _person(2)]},
    )
    classifier = train_classifier.RoleClassifier()
    X, y, person_ids = classifier.prepare_training_data(str(labels), [str(tracks)])

    assert X.shape == (2, train_classifier.EMBEDDING_WIDTH + 10)
    assert list(y) == ["Student Nurse (Primary)", "Supervising Nurse/Doctor"]
    assert person_ids == ["cam1_person_1", "cam1_person_2"]


def test_prepare_training_data_requires_osnet_embeddings_by_default(tmp_path):
    labels = _write_json(
        tmp_path / "labels.json",
        {
            "person_labels": {
                "cam1_person_1": {"role": "Student Nurse (Primary)"},
                "cam1_person_2": {"role": "Supervising Nurse/Doctor"},
            }
        },
    )
    tracks = _write_json(
        tmp_path / "person_tracks_cam1.json",
        {"camera_id": "cam1", "persons": [_person(1, False), _person(2)]},
    )

    with pytest.raises(train_classifier.TrainingDataError, match="has no 512-value OSNet"):
        train_classifier.RoleClassifier().prepare_training_data(str(labels), [str(tracks)])


def test_prepare_training_data_rejects_labels_from_another_cohort(tmp_path):
    labels = _write_json(
        tmp_path / "labels.json",
        {
            "person_labels": {
                "other_person_1": {"role": "Student Nurse (Primary)"},
                "other_person_2": {"role": "Supervising Nurse/Doctor"},
            }
        },
    )
    tracks = _write_json(
        tmp_path / "person_tracks_cam1.json",
        {"camera_id": "cam1", "persons": [_person(1), _person(2)]},
    )

    with pytest.raises(train_classifier.TrainingDataError, match="absent from the supplied"):
        train_classifier.RoleClassifier().prepare_training_data(str(labels), [str(tracks)])


def test_prepare_training_data_rejects_roles_outside_labeling_taxonomy(tmp_path):
    labels = _write_json(
        tmp_path / "labels.json",
        {
            "person_labels": {
                "cam1_person_1": {"role": "Invented Role"},
                "cam1_person_2": {"role": "Supervising Nurse/Doctor"},
            }
        },
    )
    tracks = _write_json(
        tmp_path / "person_tracks_cam1.json",
        {"camera_id": "cam1", "persons": [_person(1), _person(2)]},
    )

    with pytest.raises(train_classifier.TrainingDataError, match="unsupported role"):
        train_classifier.RoleClassifier().prepare_training_data(str(labels), [str(tracks)])
