from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest

from brick_stacking.verification.visual_transition import VerificationRequest, VisualSample, verify


GOLDEN = Path(__file__).resolve().parents[2] / "fixtures/vision_exchange/verification_v0.1.json"


def examples():
    request = VerificationRequest(
        "post_place", "block-1", "slot-1", "red", "scene-v1", "config-v1",
        "calibration-v1", "geometry-v1", "mock-clock", "epoch-v1", .5, "mock",
        expected_center_camera_m=(0., 0., .5), table_normal_camera=(0., 0., 1.),
        action_started_s=1.1, action_finished_s=1.4, min_stable_s=.1, max_stable_shift_m=.004,
    )
    before = VisualSample(
        request.object_id, "before", "mock://before", "mock-head", "head_optical",
        1., request.clock_domain, request.epoch, request.source, request.scene_version,
        request.config_hash, request.calibration_hash, request.geometry_version,
        True, "supply", "VISIBLE", "red", (.4, 0., .5),
    )
    first = replace(before, observation_id="first", image_ref="mock://first", stamp_s=1.5,
                    region_id="slot-1", center_camera_m=(.005, 0., .5), released=True)
    last = replace(first, observation_id="last", image_ref="mock://last", stamp_s=1.7,
                   center_camera_m=(.006, 0., .5))
    pick = replace(request, phase="post_grasp", region_id="gripper")
    held = replace(last, region_id="gripper", held=True, released=None)
    pre = replace(request, phase="pre_grasp", region_id="supply",
                  expected_center_camera_m=before.center_camera_m)
    return {
        "pre_grasp": (pre, None, (before,), 1.1),
        "pick_held": (pick, before, (held,), 1.8),
        "pick_empty": (pick, before, (replace(held, held=False, visibility="EMPTY"),), 1.8),
        "pick_disappearance_only": (pick, before, (replace(held, held=None, visibility="EMPTY"),), 1.8),
        "place_stable": (request, before, (first, last), 1.8),
        "place_offset": (request, before, (first, replace(last, center_camera_m=(.016, 0., .5))), 1.8),
        "place_wrong_color": (request, before, (first, replace(last, color="blue")), 1.8),
        "place_moving": (request, before, (first, replace(last, center_camera_m=(.012, 0., .5))), 1.8),
        "place_occluded": (request, before, (first, replace(last, visibility="OCCLUDED")), 1.8),
        "place_invalid_depth": (request, before, (first, replace(last, visibility="INVALID_DEPTH")), 1.8),
        "place_timeout": (request, before, (first, last), 2.5),
        "place_no_image": (request, before, (), 1.8),
        "place_camera_moved": (request, before, (first, replace(last, geometry_version="changed")), 1.8),
        "place_reference_unconfirmed": (request, before, (first, replace(last, reference_confirmed=False)), 1.8),
        "place_reused": (request, before, (first, first), 1.8),
        "place_wrong_object": (request, before, (first, replace(last, object_id="different")), 1.8),
        "place_position_only": (request, before, (first, replace(last, released=None)), 1.8),
        "place_single_sample": (request, before, (last,), 1.8),
    }


def example_json():
    rows = {}
    for name, (request, before, after, now) in examples().items():
        evidence = verify(request, before=before, after=after, now_s=now)
        evidence.pop("sample_id")
        rows[name] = dict(request=asdict(request), before=asdict(before) if before else None,
                          after=[asdict(sample) for sample in after], now_s=now, expected=evidence)
    return json.loads(json.dumps(rows, allow_nan=False))


@pytest.mark.parametrize(("name", "verdict"), [
    ("pre_grasp", "PASS"), ("pick_held", "PASS"), ("pick_empty", "FAIL"),
    ("pick_disappearance_only", "UNKNOWN"), ("place_stable", "PASS"),
    ("place_offset", "FAIL"), ("place_wrong_color", "FAIL"), ("place_moving", "FAIL"),
    ("place_occluded", "UNKNOWN"), ("place_invalid_depth", "UNKNOWN"), ("place_timeout", "UNKNOWN"),
    ("place_no_image", "UNKNOWN"), ("place_camera_moved", "UNKNOWN"),
    ("place_reference_unconfirmed", "UNKNOWN"), ("place_reused", "UNKNOWN"),
    ("place_wrong_object", "UNKNOWN"), ("place_position_only", "UNKNOWN"),
    ("place_single_sample", "UNKNOWN"),
])
def test_verify_golden(name, verdict):
    row = json.loads(GOLDEN.read_text(encoding="utf-8"))[name]
    request = VerificationRequest(**row["request"])
    before = VisualSample(**row["before"]) if row["before"] else None
    after = tuple(VisualSample(**sample) for sample in row["after"])
    result = verify(request, before=before, after=after, now_s=row["now_s"])
    assert result["verdict"] == verdict
    assert result.pop("sample_id")
    assert json.loads(json.dumps(result, allow_nan=False)) == row["expected"]


def test_real_visual_evidence_requires_validated_exposure_clock():
    request, before, after, now = examples()["place_stable"]
    request = replace(request, source="real")
    before = replace(before, source="real")
    after = tuple(replace(view, source="real") for view in after)
    result = verify(request, before=before, after=after, now_s=now)
    assert (result["verdict"], result["reason"]) == ("UNKNOWN", "real_exposure_clock_unvalidated")
    bounded = replace(request, clock_error_bound_s=.01, clock_evidence_ref="mock-clock-validation")
    assert verify(bounded, before=before, after=after, now_s=now)["verdict"] == "PASS"
