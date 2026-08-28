

def test_shorter_score_sequence_pairs_by_index_and_drops_tail(tmp_path):
    """Light-ASD emits fewer scores than frames; scores align to the frame PREFIX.

    Columbia_test.py slices video features [:round(length*25)] where length is capped by
    audio duration, so score[i] belongs to frame[i] and the trailing frames are unscored.
    Real tracks showed 106/105, 23/22, 46/45. Pairing from the wrong end would shift every
    score by one frame (~33 ms at 29.97 fps).
    """
    import pickle
    from scripts.focal.pipeline_stages import assemble_asd_artifact

    camera_pywork, fps_by_camera = {}, {}
    for camera in ("cam1", "cam2", "cam3"):
        pywork = tmp_path / f"asd_{camera}" / "pywork"
        pywork.mkdir(parents=True)
        tracks = [{"track": {"frame": list(range(10)), "bbox": [[0, 0, 1, 1]] * 10}}]
        scores = [[float(i) for i in range(9)]]      # one fewer, as upstream produces
        (pywork / "tracks.pckl").write_bytes(pickle.dumps(tracks))
        (pywork / "scores.pckl").write_bytes(pickle.dumps(scores))
        camera_pywork[camera] = pywork
        fps_by_camera[camera] = 29.97002997

    result = assemble_asd_artifact(camera_pywork, fps_by_camera)
    samples = result["cam1"]["tracks"][0]["samples"]
    assert len(samples) == 9, "the unscored trailing frame must be dropped, not paired"
    assert samples[0]["frame_index"] == 0 and samples[0]["score"] == 0.0
    assert samples[-1]["frame_index"] == 8 and samples[-1]["score"] == 8.0
