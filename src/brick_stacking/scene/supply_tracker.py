"""Run-local identities for already localized supply observations."""
from collections import Counter
from dataclasses import replace
from math import dist, isfinite

from brick_stacking.models.scene_state import BlockLocation, SceneSnapshot


def _group(block):
    return block.frame_id, block.color


class SupplyTracker:
    def __init__(self, max_match_distance_m: float):
        if not isfinite(max_match_distance_m) or max_match_distance_m <= 0:
            raise ValueError("positive supply association distance required")
        self._radius = max_match_distance_m
        self._tracks = {}
        self._ambiguous = set()
        self._next_id = 1
        self._last = None

    def update(self, observation: SceneSnapshot, placed_ids: set[str]) -> SceneSnapshot:
        if self._last is not None:
            previous = self._last
            if (observation.epoch, observation.clock_domain, observation.source) != (
                previous.epoch, previous.clock_domain, previous.source
            ) or observation.stamp_s <= previous.stamp_s:
                raise ValueError("supply observations require an increasing stamp in the same stream")

        tracks = {key: block for key, block in self._tracks.items() if key not in placed_ids}
        candidates = sorted(
            (b for b in observation.blocks if b.location == BlockLocation.SUPPLY and b.visible),
            key=lambda b: (_group(b), tuple(b.center_m), b.object_id),
        )
        neighbors = {
            b.object_id: [key for key, old in tracks.items()
                          if _group(old) == _group(b) and dist(old.center_m, b.center_m) <= self._radius]
            for b in candidates
        }
        claims = Counter(key for keys in neighbors.values() for key in keys)
        ambiguous = self._ambiguous.intersection(tracks)
        for candidate in candidates:
            keys = neighbors[candidate.object_id]
            if candidate.ambiguous or len(keys) > 1 or any(claims[key] > 1 for key in keys):
                ambiguous.update(keys)

        matched = {}
        for candidate in candidates:
            keys = neighbors[candidate.object_id]
            if len(keys) == 1 and keys[0] not in ambiguous:
                matched[keys[0]] = replace(candidate, object_id=keys[0])

        # An out-of-range candidate could be a missing same-color block.
        unresolved_groups = {_group(block) for key, block in tracks.items() if key not in matched}
        positions = Counter((_group(b), tuple(b.center_m)) for b in candidates)
        for candidate in candidates:
            group = _group(candidate)
            if (not candidate.ambiguous and not neighbors[candidate.object_id]
                    and group not in unresolved_groups and positions[group, tuple(candidate.center_m)] == 1):
                key = f"block-{self._next_id:06d}"
                self._next_id += 1
                matched[key] = replace(candidate, object_id=key)

        tracks.update(matched)
        blocks = tuple(
            replace(block, visible=key in matched, ambiguous=key in ambiguous)
            for key, block in sorted(tracks.items())
        )
        snapshot = replace(observation, blocks=blocks)
        self._tracks = tracks
        self._ambiguous = ambiguous
        self._last = observation
        return snapshot
