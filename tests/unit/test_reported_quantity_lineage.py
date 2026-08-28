"""Lineage must be backed by the artifact, not merely declared by a static map."""
import json

from scripts.run_manifest import RunManifest


def _manifest_with_artifact(tmp_path, document):
    artifact = tmp_path / "paper_metrics.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")
    manifest = RunManifest.create(
        tmp_path / "run" / "run_manifest.json", tmp_path,
        run_id="run-test", alignment_tolerance_seconds=0.05, tracking_sample_fps=None,
        project={}, environment={}, third_party={"components": []},
    )
    manifest.register_artifact(artifact, session_id="s", producer_stage="compute_paper_metrics")
    return manifest, artifact


def test_quantity_the_producer_declares_keeps_its_lineage(tmp_path):
    manifest, artifact = _manifest_with_artifact(
        tmp_path, {"quantity_artifact_map": {"tm_overlap": {}}, "tm_overlap": {"value": 0.875}}
    )

    manifest.set_reported_quantities({"tm_overlap": [artifact]})

    assert manifest.document["reported_quantities"]["tm_overlap"] == ["paper_metrics.json"]


def test_quantity_the_producer_does_not_declare_gets_no_lineage(tmp_path):
    """An incomplete artifact must not yield lineage for absent quantities."""
    manifest, artifact = _manifest_with_artifact(
        tmp_path, {"quantity_artifact_map": {"tm_overlap": {}}, "tm_overlap": {"value": 0.875}}
    )

    manifest.set_reported_quantities({"evidence_distribution": [artifact]})

    assert manifest.document["reported_quantities"]["evidence_distribution"] == []


def test_source_artifacts_making_no_declaration_are_unaffected(tmp_path):
    """asd_tracks.json does not name the quantities derived from it; that is not a defect."""
    manifest, artifact = _manifest_with_artifact(tmp_path, {"tracks": []})

    manifest.set_reported_quantities({"active_speaker_detection": [artifact]})

    assert manifest.document["reported_quantities"]["active_speaker_detection"] == [
        "paper_metrics.json"
    ]
