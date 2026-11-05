from dataclasses import replace
from pathlib import Path
import pytest
from brick_stacking.app.task_runner import compose_mock_task, main
from brick_stacking.models.task_state import TaskStage
from brick_stacking.models.scene_state import SlotState
from brick_stacking.runtime.config_loader import load_config


@pytest.fixture
def task_config():
    return load_config(Path(__file__).resolve().parents[2] / "config/offline_task.yaml")


def test_ten_block_transaction_loop(task_config):
    events = []
    executor, world, manager = compose_mock_task(task_config, lambda k, d: events.append((k, d)))
    result = executor.run()
    assert result.stage == TaskStage.DONE and len(result.verified_slots) == 10
    assert all(state == SlotState.PLACED_VERIFIED for state in manager.states.values())
    assert world.payload is None and result.manual_intervention_count == 0
    assert not result.hardware_tested and all(not e["physical_execution"] for e in world.events)


def test_bounded_retry_requires_reobservation(task_config):
    events = []
    executor, world, manager = compose_mock_task(task_config, lambda k, d: events.append((k, d)), fault="one_grasp_failure")
    result = executor.run()
    assert result.stage == TaskStage.DONE and result.recovery_attempts == 1
    assert any(d.get("stage") == "REOBSERVE" for k, d in events)
    assert sum(e["stage"] == "GRASP" for e in world.events) == 11


def test_retry_exhaustion_halts_without_automatic_reset(task_config):
    executor, world, manager = compose_mock_task(task_config, lambda *_: None, fault="grasp_exhaustion")
    result = executor.run()
    assert result.stage == TaskStage.SAFE_HALT and not result.verified_slots
    assert result.recovery_attempts == 2
    assert sum(e["stage"] == "GRASP" for e in world.events) == 3
    assert world.events[-1]["stage"] == "MOCK_STOP"


def test_misplacement_does_not_commit_or_continue(task_config):
    executor, world, manager = compose_mock_task(task_config, lambda *_: None, fault="misplaced")
    result = executor.run()
    assert result.stage == TaskStage.SAFE_HALT
    assert manager.states["L0_0"] == SlotState.UNVERIFIED
    assert not manager.occupants and manager.reservations
    assert sum(e["stage"] == "GRASP" for e in world.events) == 1


def test_ambiguous_supply_does_not_generate_actions(task_config):
    executor, world, _ = compose_mock_task(task_config, lambda *_: None)
    world.blocks = {key: replace(block, ambiguous=True) for key, block in world.blocks.items()}
    assert executor.run().stage == TaskStage.SAFE_HALT
    assert not any(e["stage"] == "GRASP" for e in world.events)


def test_clock_reset_prevents_following_action(task_config):
    executor, world, _ = compose_mock_task(task_config, lambda *_: None)
    original = world.observe
    def repeated_stamp():
        snapshot = original()
        return snapshot if world._counter == 1 else replace(snapshot, stamp_s=0.)
    world.observe = repeated_stamp
    result = executor.run()
    assert result.stage == TaskStage.SAFE_HALT
    assert sum(e["stage"] == "GRASP" for e in world.events) == 1
    assert not any(e["stage"] == "PLACE" for e in world.events)


def test_device_adapter_refused_without_observation_or_stop(task_config):
    executor, _, _ = compose_mock_task(task_config, lambda *_: None)
    class ForbiddenDevice:
        backend = "real"
        hardware_enabled = True
        def observe(self): raise AssertionError("must not touch device")
        def stop(self): raise AssertionError("must not send command")
    executor.port = ForbiddenDevice()
    assert executor.run().stage == TaskStage.SAFE_HALT


def test_competition_has_zero_manual_recovery(task_config):
    task_config["operation"] = {"mode": "COMPETITION_AUTONOMOUS", "manual_intervention_allowed": False}
    executor, _, _ = compose_mock_task(task_config, lambda *_: None, fault="one_grasp_failure")
    result = executor.run()
    assert result.stage == TaskStage.DONE and result.manual_intervention_count == 0


def test_task_cli_retains_report(tmp_path):
    config = str(Path(__file__).resolve().parents[2] / "config/offline_task.yaml")
    assert main(["--config", config, "--output-root", str(tmp_path)]) == 0
    assert next(tmp_path.rglob("metrics.json")).is_file()
