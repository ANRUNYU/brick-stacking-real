from brick_stacking.execution.t2_touch_lift_package import (
    T2Limits,
    T2Stage,
    build_t2_package,
)


def test_t2_mock_requires_attestations():
    r = build_t2_package(mock=True)
    assert r.stage == T2Stage.SAFE_HALT
    assert "attestation" in (r.reason or "")


def test_t2_mock_passes_with_attestations():
    r = build_t2_package(
        mock=True,
        block_present_attested=True,
        clear_workspace_attested=True,
        e_stop_reachable_attested=True,
    )
    assert r.stage == T2Stage.DONE
    assert r.control_ready is False
    assert r.executable is False
    assert r.live_motion_allowed is False
    assert r.stages[0] == "PRECHECK"
    assert r.stages[-1] == "DONE"
    assert "CLOSE" in r.stages and "MICRO_LIFT" in r.stages


def test_t2_refuses_live_inside_package():
    r = build_t2_package(
        mock=False,
        live_motion=True,
        block_present_attested=True,
        clear_workspace_attested=True,
        e_stop_reachable_attested=True,
    )
    assert r.stage == T2Stage.SAFE_HALT
    assert "live path not auto-started" in (r.reason or "")


def test_t2_refuses_weak_lift_limit():
    r = build_t2_package(
        mock=True,
        limits=T2Limits(micro_lift_min_m=0.01),
        block_present_attested=True,
        clear_workspace_attested=True,
        e_stop_reachable_attested=True,
    )
    assert r.stage == T2Stage.SAFE_HALT
