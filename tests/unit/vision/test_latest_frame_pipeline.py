from dataclasses import replace
from threading import Event, Thread

import pytest

from brick_stacking.app.offline_runner import synthetic_frame
from brick_stacking.vision.latest_frame_pipeline import LatestFramePipeline
from brick_stacking.vision.observation_exchange import CaptureContext


class Detector:
    def __init__(self, *, on_detect=lambda: None):
        self.on_detect = on_detect
        self.stamps = []

    def detect(self, frame):
        self.stamps.append(frame.stamp_s)
        self.on_detect()
        return ()


def make_pipeline(detector=None):
    now = [100.]
    detector = detector or Detector()
    pipeline = LatestFramePipeline(detector, nominal_edge_m=.05, max_receive_age_s=1.,
                                   max_pair_skew_s=.02, clock=lambda: now[0])
    return pipeline, detector, now


def pair(stamp, *, epoch="a", profile="profile", host=100., skew=.001):
    frame = replace(synthetic_frame(), stamp_s=stamp, clock_domain=epoch)
    context = CaptureContext(
        f"capture-{epoch}-{stamp}.npz", profile, "hash", epoch, host,
        "process_monotonic", stamp, stamp + skew,
    )
    return frame, context


def start(pipeline, epoch="a", profile="profile"):
    pipeline.start_session(camera_id="synthetic_head", epoch=epoch, profile=profile, profile_hash="hash")


def test_latest_pair_replaces_backlog_and_keeps_matching_image_reference():
    pipeline, detector, now = make_pipeline()
    start(pipeline)
    for stamp in range(1, 101):
        assert pipeline.offer(*pair(float(stamp)))
    result = pipeline.process_latest()
    assert detector.stamps == [100.]
    assert result["rgbd"]["rgb_ref"] == "capture-a-100.0.npz#rgb"
    assert pipeline.get_observation() == result
    assert pipeline.metrics()["counts"]["overwritten_pending"] == 99
    assert pipeline.metrics()["receive_to_output_s"] == {"p50": 0., "p95": 0., "max": 0.}
    assert result["timing"]["exposure_to_output_s"] is None
    now[0] += 2
    assert pipeline.get_observation() is None


def test_bad_pair_profile_reversed_stamp_and_reconnect_reset():
    pipeline, _, _ = make_pipeline()
    start(pipeline)
    assert not pipeline.offer(*pair(1., profile="another"))
    assert not pipeline.offer(*pair(1., skew=.05))
    assert pipeline.offer(*pair(2.))
    assert pipeline.process_latest()
    assert not pipeline.offer(*pair(1.))
    assert pipeline.get_observation() is None
    assert not pipeline.offer(*pair(3.))
    with pytest.raises(ValueError, match="fresh capture epoch"):
        start(pipeline)
    start(pipeline, epoch="b")
    assert not pipeline.offer(*pair(3.))
    assert pipeline.offer(*pair(.01, epoch="b"))
    assert pipeline.process_latest()["rgbd"]["epoch"] == "b"


def test_stale_input_and_slow_detection_do_not_publish():
    pipeline, detector, now = make_pipeline()
    start(pipeline)
    assert not pipeline.offer(*pair(1., host=98.))
    assert pipeline.offer(*pair(1.))
    now[0] = 102.
    assert pipeline.process_latest() is None
    assert pipeline.offer(*pair(2., host=102.))
    detector.on_detect = lambda: now.__setitem__(0, 104.)
    assert pipeline.process_latest() is None
    assert pipeline.metrics()["counts"]["expired_before_detection"] == 1
    assert pipeline.metrics()["counts"]["expired_after_detection"] == 1


def test_scene_invalidation_discards_in_flight_result():
    entered, release = Event(), Event()

    def slow_detect():
        entered.set()
        assert release.wait(5)

    pipeline, _, _ = make_pipeline(Detector(on_detect=slow_detect))
    start(pipeline)
    assert pipeline.offer(*pair(1.))
    result = []
    thread = Thread(target=lambda: result.append(pipeline.process_latest()))
    thread.start()
    try:
        assert entered.wait(5)
        assert pipeline.process_latest() is None
        pipeline.invalidate()
        start(pipeline, epoch="b")
        assert pipeline.offer(*pair(.01, epoch="b"))
    finally:
        release.set()
        thread.join(5)
    assert result == [None]
    assert pipeline.get_observation() is None
    assert pipeline.process_latest()["rgbd"]["epoch"] == "b"
