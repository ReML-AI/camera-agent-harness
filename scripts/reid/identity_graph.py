"""Constraint-preserving within- and cross-camera identity graph construction."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Mapping, Sequence

from .embeddings import average_then_l2_normalize


@dataclass(frozen=True)
class Tracklet:
    camera_id: str
    tracklet_id: str
    start_seconds: float
    end_seconds: float
    embedding: tuple[float, ...] | None

    def __post_init__(self) -> None:
        if self.start_seconds < 0 or self.end_seconds < self.start_seconds:
            raise ValueError("tracklet interval must be non-negative and ordered")


@dataclass(frozen=True)
class CanonicalTrack:
    camera_id: str
    canonical_track_id: str
    member_tracklet_ids: tuple[str, ...]
    active_intervals: tuple[tuple[float, float], ...]
    embedding: tuple[float, ...] | None


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity without a mandatory NumPy dependency."""
    import math

    if not left or len(left) != len(right):
        raise ValueError("embeddings must have one common non-zero length")
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    norm_left = math.sqrt(sum(float(value) ** 2 for value in left))
    norm_right = math.sqrt(sum(float(value) ** 2 for value in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


def intervals_overlap(
    left: tuple[float, float], right: tuple[float, float]
) -> bool:
    """Whether closed observation windows share any decoded presentation time."""
    return max(left[0], right[0]) <= min(left[1], right[1])


def overlap_seconds(
    left_intervals: Sequence[tuple[float, float]],
    right_intervals: Sequence[tuple[float, float]],
) -> float:
    return max(
        (
            min(left[1], right[1]) - max(left[0], right[0])
            for left in left_intervals
            for right in right_intervals
        ),
        default=float("-inf"),
    )


def _pair(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


def _group_conflict(
    left_members: Iterable[str],
    right_members: Iterable[str],
    cannot_links: set[tuple[str, str]],
) -> tuple[str, str] | None:
    for left in sorted(left_members):
        for right in sorted(right_members):
            if _pair(left, right) in cannot_links:
                return _pair(left, right)
    return None


def _gap_seconds(left: Tracklet, right: Tracklet) -> float:
    if intervals_overlap(
        (left.start_seconds, left.end_seconds),
        (right.start_seconds, right.end_seconds),
    ):
        return 0.0
    return max(left.start_seconds, right.start_seconds) - min(
        left.end_seconds, right.end_seconds
    )


def merge_within_camera(
    tracklets: Sequence[Tracklet],
    *,
    similarity_threshold: float,
    maximum_gap_seconds: float,
    cannot_links: Iterable[tuple[str, str]] = (),
) -> tuple[list[CanonicalTrack], list[dict[str, object]], set[tuple[str, str]]]:
    """Complete-link-safe agglomeration of non-overlapping local tracklets.

    Every possible pair receives an audit edge. A merge is accepted only if
    its direct pair passes appearance/time gates and no cannot-link exists
    between any members of the two prospective groups.
    """
    if not 0.0 <= similarity_threshold <= 1.0 or maximum_gap_seconds < 0.0:
        raise ValueError("invalid within-camera thresholds")
    if len({tracklet.camera_id for tracklet in tracklets}) > 1:
        raise ValueError("within-camera merging received multiple cameras")
    by_id = {tracklet.tracklet_id: tracklet for tracklet in tracklets}
    if len(by_id) != len(tracklets):
        raise ValueError("tracklet IDs must be unique")

    declared_blocked = {_pair(left, right) for left, right in cannot_links}
    temporal_blocked: set[tuple[str, str]] = set()
    for left, right in combinations(sorted(tracklets, key=lambda item: item.tracklet_id), 2):
        if intervals_overlap(
            (left.start_seconds, left.end_seconds),
            (right.start_seconds, right.end_seconds),
        ):
            temporal_blocked.add(_pair(left.tracklet_id, right.tracklet_id))
    blocked = declared_blocked | temporal_blocked

    groups = {tracklet.tracklet_id: {tracklet.tracklet_id} for tracklet in tracklets}
    owner = {tracklet.tracklet_id: tracklet.tracklet_id for tracklet in tracklets}
    candidates: list[tuple[float, str, str]] = []
    edges: dict[tuple[str, str], dict[str, object]] = {}

    for left, right in combinations(sorted(tracklets, key=lambda item: item.tracklet_id), 2):
        key = _pair(left.tracklet_id, right.tracklet_id)
        edge: dict[str, object] = {
            "edge_type": "within_camera",
            "camera_id": left.camera_id,
            "tracklet_a": key[0],
            "tracklet_b": key[1],
            "accepted": False,
        }
        if key in blocked:
            edge["similarity"] = (
                cosine_similarity(left.embedding, right.embedding)
                if left.embedding is not None and right.embedding is not None
                else None
            )
            edge["reason"] = (
                "cannot_link_temporal_overlap"
                if key in temporal_blocked
                else "cannot_link_declared"
            )
        elif left.embedding is None or right.embedding is None:
            edge["similarity"] = None
            edge["reason"] = "missing_embedding"
        else:
            similarity = cosine_similarity(left.embedding, right.embedding)
            gap = _gap_seconds(left, right)
            edge["similarity"] = similarity
            edge["gap_seconds"] = gap
            if gap > maximum_gap_seconds:
                edge["reason"] = "gap_exceeds_threshold"
            elif similarity < similarity_threshold:
                edge["reason"] = "below_similarity_threshold"
            else:
                edge["reason"] = "pending_group_constraint"
                candidates.append((similarity, key[0], key[1]))
        edges[key] = edge

    for _score, left_id, right_id in sorted(
        candidates, key=lambda item: (-item[0], item[1], item[2])
    ):
        edge = edges[_pair(left_id, right_id)]
        left_owner, right_owner = owner[left_id], owner[right_id]
        if left_owner == right_owner:
            edge["reason"] = "redundant_existing_group_path"
            continue
        conflict = _group_conflict(groups[left_owner], groups[right_owner], blocked)
        if conflict is not None:
            edge["reason"] = "cannot_link_group_conflict"
            edge["blocking_pair"] = list(conflict)
            continue

        new_owner = min(left_owner, right_owner)
        old_owner = max(left_owner, right_owner)
        groups[new_owner] |= groups[old_owner]
        for member in groups[old_owner]:
            owner[member] = new_owner
        del groups[old_owner]
        edge["accepted"] = True
        edge["reason"] = "accepted"

    canonical: list[CanonicalTrack] = []
    for canonical_id, members in sorted(groups.items()):
        ordered_members = tuple(sorted(members))
        member_tracklets = [by_id[member] for member in ordered_members]
        vectors = [item.embedding for item in member_tracklets if item.embedding is not None]
        embedding = average_then_l2_normalize(vectors) if vectors else None
        canonical.append(
            CanonicalTrack(
                camera_id=member_tracklets[0].camera_id,
                canonical_track_id=canonical_id,
                member_tracklet_ids=ordered_members,
                active_intervals=tuple(
                    sorted((item.start_seconds, item.end_seconds) for item in member_tracklets)
                ),
                embedding=embedding,
            )
        )
    return canonical, [edges[key] for key in sorted(edges)], blocked


def _hungarian_minimize(costs: Sequence[Sequence[float]]) -> list[tuple[int, int]]:
    """Deterministic O(n^3) square Hungarian assignment using only stdlib."""
    size = len(costs)
    if size == 0:
        return []
    if any(len(row) != size for row in costs):
        raise ValueError("Hungarian cost matrix must be square")
    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    p = [0] * (size + 1)
    way = [0] * (size + 1)
    for row in range(1, size + 1):
        p[0] = row
        column0 = 0
        minimum = [float("inf")] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[column0] = True
            row0 = p[column0]
            delta = float("inf")
            column1 = 0
            for column in range(1, size + 1):
                if used[column]:
                    continue
                current = costs[row0 - 1][column - 1] - u[row0] - v[column]
                if current < minimum[column]:
                    minimum[column] = current
                    way[column] = column0
                if minimum[column] < delta:
                    delta = minimum[column]
                    column1 = column
            for column in range(size + 1):
                if used[column]:
                    u[p[column]] += delta
                    v[column] -= delta
                else:
                    minimum[column] -= delta
            column0 = column1
            if p[column0] == 0:
                break
        while True:
            column1 = way[column0]
            p[column0] = p[column1]
            column0 = column1
            if column0 == 0:
                break
    return sorted((p[column] - 1, column - 1) for column in range(1, size + 1))


def _one_to_one_selected(
    left: Sequence[CanonicalTrack],
    right: Sequence[CanonicalTrack],
    eligible_scores: Mapping[tuple[str, str], float],
) -> set[tuple[str, str]]:
    """Maximum-weight camera-pair assignment with explicit unmatched dummies."""
    size = len(left) + len(right)
    if size == 0:
        return set()
    invalid_weight = -1_000_000.0
    weights = [[0.0 for _ in range(size)] for _ in range(size)]
    for row, left_track in enumerate(left):
        for column, right_track in enumerate(right):
            weights[row][column] = eligible_scores.get(
                (left_track.canonical_track_id, right_track.canonical_track_id),
                invalid_weight,
            )
    costs = [[-weight for weight in row] for row in weights]
    assignment = _hungarian_minimize(costs)
    selected: set[tuple[str, str]] = set()
    for row, column in assignment:
        if row < len(left) and column < len(right):
            key = (left[row].canonical_track_id, right[column].canonical_track_id)
            if key in eligible_scores:
                selected.add(key)
    return selected


def assert_one_simultaneous_track_per_camera(
    members: Sequence[CanonicalTrack],
) -> None:
    """Raise if one global identity contains co-active tracks from one camera."""
    for left, right in combinations(members, 2):
        if left.camera_id != right.camera_id:
            continue
        if any(
            intervals_overlap(left_interval, right_interval)
            for left_interval in left.active_intervals
            for right_interval in right.active_intervals
        ):
            raise ValueError(
                "global identity contains simultaneously active tracks from "
                f"camera {left.camera_id}: {left.canonical_track_id}, "
                f"{right.canonical_track_id}"
            )


def build_global_identities(
    tracks: Sequence[CanonicalTrack],
    *,
    similarity_threshold: float,
    minimum_copresence_seconds: float,
    cannot_links: Iterable[tuple[str, str]] = (),
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Pairwise one-to-one matching followed by constraint-safe global union."""
    if not 0.0 <= similarity_threshold <= 1.0 or minimum_copresence_seconds < 0.0:
        raise ValueError("invalid cross-camera thresholds")
    by_id = {track.canonical_track_id: track for track in tracks}
    if len(by_id) != len(tracks):
        raise ValueError("canonical track IDs must be globally unique")
    cameras: dict[str, list[CanonicalTrack]] = {}
    for track in tracks:
        cameras.setdefault(track.camera_id, []).append(track)
    for camera_tracks in cameras.values():
        camera_tracks.sort(key=lambda item: item.canonical_track_id)

    blocked = {_pair(left, right) for left, right in cannot_links}
    for left, right in combinations(sorted(tracks, key=lambda item: item.canonical_track_id), 2):
        if left.camera_id == right.camera_id and any(
            intervals_overlap(a, b) for a in left.active_intervals for b in right.active_intervals
        ):
            blocked.add(_pair(left.canonical_track_id, right.canonical_track_id))

    edges: dict[tuple[str, str], dict[str, object]] = {}
    selected_candidates: list[tuple[float, str, str]] = []
    for camera_a, camera_b in combinations(sorted(cameras), 2):
        left, right = cameras[camera_a], cameras[camera_b]
        eligible: dict[tuple[str, str], float] = {}
        for left_track in left:
            for right_track in right:
                key = (left_track.canonical_track_id, right_track.canonical_track_id)
                edge: dict[str, object] = {
                    "edge_type": "cross_camera",
                    "camera_a": camera_a,
                    "camera_b": camera_b,
                    "track_a": key[0],
                    "track_b": key[1],
                    "accepted": False,
                }
                copresence = overlap_seconds(
                    left_track.active_intervals, right_track.active_intervals
                )
                edge["copresence_seconds"] = max(0.0, copresence)
                if copresence < minimum_copresence_seconds:
                    edge["similarity"] = None
                    edge["reason"] = "no_temporal_copresence"
                elif left_track.embedding is None or right_track.embedding is None:
                    edge["similarity"] = None
                    edge["reason"] = "missing_embedding"
                else:
                    similarity = cosine_similarity(left_track.embedding, right_track.embedding)
                    edge["similarity"] = similarity
                    if similarity < similarity_threshold:
                        edge["reason"] = "below_similarity_threshold"
                    else:
                        edge["reason"] = "pending_one_to_one_assignment"
                        eligible[key] = similarity
                edges[_pair(*key)] = edge

        selected = _one_to_one_selected(left, right, eligible)
        for key, score in eligible.items():
            edge = edges[_pair(*key)]
            if key in selected:
                edge["reason"] = "pending_global_constraint"
                selected_candidates.append((score, key[0], key[1]))
            else:
                edge["reason"] = "rejected_one_to_one_assignment"

    groups = {track_id: {track_id} for track_id in by_id}
    owner = {track_id: track_id for track_id in by_id}
    for _score, left_id, right_id in sorted(
        selected_candidates, key=lambda item: (-item[0], item[1], item[2])
    ):
        edge = edges[_pair(left_id, right_id)]
        left_owner, right_owner = owner[left_id], owner[right_id]
        if left_owner == right_owner:
            edge["reason"] = "redundant_existing_global_path"
            continue
        conflict = _group_conflict(groups[left_owner], groups[right_owner], blocked)
        if conflict is not None:
            edge["reason"] = "cannot_link_global_conflict"
            edge["blocking_pair"] = list(conflict)
            continue
        proposed = [by_id[item] for item in groups[left_owner] | groups[right_owner]]
        try:
            assert_one_simultaneous_track_per_camera(proposed)
        except ValueError:
            edge["reason"] = "one_simultaneous_track_per_camera_conflict"
            continue

        new_owner = min(left_owner, right_owner)
        old_owner = max(left_owner, right_owner)
        groups[new_owner] |= groups[old_owner]
        for member in groups[old_owner]:
            owner[member] = new_owner
        del groups[old_owner]
        edge["accepted"] = True
        edge["reason"] = "accepted"

    identities: list[dict[str, object]] = []
    for index, (_owner, members) in enumerate(sorted(groups.items()), start=1):
        member_tracks = [by_id[member] for member in sorted(members)]
        assert_one_simultaneous_track_per_camera(member_tracks)
        identities.append(
            {
                "global_identity_id": f"global_person_{index:03d}",
                "tracks": [
                    {
                        "camera_id": track.camera_id,
                        "canonical_track_id": track.canonical_track_id,
                        "active_intervals": [list(interval) for interval in track.active_intervals],
                    }
                    for track in member_tracks
                ],
            }
        )
    return identities, [edges[key] for key in sorted(edges)]
