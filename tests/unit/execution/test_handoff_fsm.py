import pytest
from brick_stacking.execution.handoff_fsm import HandoffFsm, ZoneEvidence


def evidence(stamp, occupied, **kw):
    return ZoneEvidence(f"obs{stamp}", stamp, "fixture_clock", occupied,
                        kw.get("left_clear", True), kw.get("right_clear", True))


def test_serial_handoff_requires_clearance_and_visual_occupancy():
    f = HandoffFsm(clock_domain="fixture_clock", max_age_s=.5)
    left = f.reserve("left", evidence(1, False), now_s=1)
    f.enter(left)
    with pytest.raises(ValueError): f.reserve("right", evidence(2, True), now_s=2)
    with pytest.raises(ValueError): f.complete(left, evidence(2, True, left_clear=False), now_s=2)
    f.complete(left, evidence(2, True), now_s=2)
    assert f.state == "OCCUPIED"
    right = f.reserve("right", evidence(3, True), now_s=3)
    f.enter(right)
    with pytest.raises(ValueError): f.complete(left, evidence(4, False), now_s=4)
    f.complete(right, evidence(4, False), now_s=4)
    assert f.state == "EMPTY" and f.owner is None


def test_fault_retains_lock_until_new_clear_observation():
    f = HandoffFsm(clock_domain="fixture_clock", max_age_s=.5)
    token = f.reserve("left", evidence(1, False), now_s=1)
    f.fault()
    assert f.owner == "left" and f.token == token
    with pytest.raises(ValueError): f.reserve("right", evidence(2, True), now_s=2)
    with pytest.raises(ValueError): f.recover_after_observation(evidence(1, False), now_s=1)
    with pytest.raises(ValueError): f.recover_after_observation(evidence(2, None), now_s=2)
    f.recover_after_observation(evidence(3, True), now_s=3)
    assert f.state == "OCCUPIED" and f.owner is None


def test_stale_zone_evidence_rejected():
    f = HandoffFsm(clock_domain="fixture_clock", max_age_s=.5)
    with pytest.raises(ValueError): f.reserve("left", evidence(1, False), now_s=2)
