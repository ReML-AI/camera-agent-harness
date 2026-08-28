import math

import pytest

from scripts.reid.identity_graph import (
    CanonicalTrack,
    Tracklet,
    assert_one_simultaneous_track_per_camera,
    build_global_identities,
    merge_within_camera,
)


def tracklet(name, start, end, embedding=(1.0, 0.0)):
    return Tracklet("cam1", name, start, end, embedding)


def canonical(camera, name, start, end, embedding):
    return CanonicalTrack(camera, name, (name,), ((start, end),), embedding)


def test_non_overlapping_similar_tracklets_merge_and_edges_are_complete():
    tracks = [
        tracklet("track:cam1:1", 0.0, 1.0),
        tracklet("track:cam1:2", 2.0, 3.0),
        tracklet("track:cam1:3", 0.5, 2.5),
    ]
    merged, edges, cannot_links = merge_within_camera(
        tracks, similarity_threshold=0.8, maximum_gap_seconds=10.0
    )

    assert len(edges) == math.comb(len(tracks), 2)
    assert any(edge["accepted"] for edge in edges)
    groups = {frozenset(item.member_tracklet_ids) for item in merged}
    assert frozenset({"track:cam1:1", "track:cam1:2"}) in groups
    assert ("track:cam1:1", "track:cam1:3") in cannot_links
    assert all("reason" in edge and "accepted" in edge for edge in edges)


def test_cannot_link_blocks_a_transitive_within_camera_merge():
    a, b, c = (tracklet(f"track:cam1:{index}", 2.0 * index, 2.0 * index + 1.0)
               for index in range(3))
    merged, edges, _cannot_links = merge_within_camera(
        [a, b, c],
        similarity_threshold=0.8,
        maximum_gap_seconds=10.0,
        cannot_links=[(a.tracklet_id, c.tracklet_id)],
    )

    assert max(len(item.member_tracklet_ids) for item in merged) == 2
    assert not any(
        {a.tracklet_id, c.tracklet_id} <= set(item.member_tracklet_ids)
        for item in merged
    )
    assert any(edge["reason"] == "cannot_link_group_conflict" for edge in edges)


def test_cross_camera_global_union_enforces_simultaneous_same_camera_invariant():
    tracks = [
        canonical("camA", "track:camA:1", 0.0, 10.0, (1.0, 0.0)),
        canonical("camA", "track:camA:2", 5.0, 15.0, (0.8, 0.6)),
        canonical("camB", "track:camB:1", 0.0, 15.0, (1.0, 0.0)),
        canonical("camC", "track:camC:1", 0.0, 15.0, (0.8, 0.6)),
    ]
    identities, edges = build_global_identities(
        tracks, similarity_threshold=0.75, minimum_copresence_seconds=0.0
    )

    assert len(edges) == 5
    by_id = {track.canonical_track_id: track for track in tracks}
    for identity in identities:
        assert_one_simultaneous_track_per_camera(
            [by_id[item["canonical_track_id"]] for item in identity["tracks"]]
        )
    assert any(
        edge["reason"] in {
            "cannot_link_global_conflict",
            "one_simultaneous_track_per_camera_conflict",
        }
        for edge in edges
    )
    assert all("reason" in edge and "accepted" in edge for edge in edges)


def test_cross_camera_assignment_is_one_to_one_and_requires_copresence():
    tracks = [
        canonical("camA", "track:camA:1", 0.0, 5.0, (1.0, 0.0)),
        canonical("camA", "track:camA:2", 0.0, 5.0, (0.99, 0.01)),
        canonical("camB", "track:camB:1", 0.0, 5.0, (1.0, 0.0)),
        canonical("camB", "track:camB:2", 8.0, 9.0, (1.0, 0.0)),
    ]
    _identities, edges = build_global_identities(
        tracks, similarity_threshold=0.75, minimum_copresence_seconds=0.0
    )

    accepted = [edge for edge in edges if edge["accepted"]]
    assert len(accepted) == 1
    assert any(edge["reason"] == "rejected_one_to_one_assignment" for edge in edges)
    assert any(edge["reason"] == "no_temporal_copresence" for edge in edges)


def test_invariant_checker_rejects_overlapping_tracks_from_one_camera():
    with pytest.raises(ValueError, match="simultaneously active"):
        assert_one_simultaneous_track_per_camera(
            [
                canonical("cam1", "track:cam1:1", 0.0, 2.0, (1.0, 0.0)),
                canonical("cam1", "track:cam1:2", 1.0, 3.0, (0.0, 1.0)),
            ]
        )
