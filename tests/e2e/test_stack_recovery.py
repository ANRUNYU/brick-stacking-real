from dataclasses import replace
from pathlib import Path

import pytest

from brick_stacking.app.task_runner import compose_mock_task
from brick_stacking.execution.execution_manager import OfflineExecutionManager
from brick_stacking.hardware.mock_task_world import MockCommand
from brick_stacking.models.scene_state import BlockLocation, SlotState
from brick_stacking.models.task_state import TaskStage
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.scene.scene_manager import SceneManager


@pytest.fixture
def stack():
    config = load_config(Path(__file__).resolve().parents[2] / "config/offline_task.yaml")
    events = []
    executor, world, manager = compose_mock_task(config, lambda *event: events.append(event))
    return executor, world, manager, events


def test_reobserve_occluded_pick_without_repeating_grasp(stack):
    executor, world, _, _ = stack
    observe = world.observe
    first_block = next(iter(world.blocks))

    def occluded():
        snapshot = observe()
        if world._counter != 2:
            return snapshot
        return replace(snapshot, blocks=tuple(
            block for block in snapshot.blocks if block.object_id != first_block
        ))

    world.observe = occluded
    result = executor.run()
    assert result.stage == TaskStage.DONE and result.reobservations == 1
    assert sum(e["stage"] == "GRASP" and e["block_id"] == first_block for e in world.events) == 1


@pytest.mark.parametrize("persistent", [False, True])
def test_reobserve_occluded_placement_without_repeating_action(stack, persistent):
    executor, world, manager, _ = stack
    observe = world.observe
    first_block = next(iter(world.blocks))

    def occluded():
        snapshot = observe()
        if world._counter == 3 or (persistent and world._counter >= 3):
            return replace(snapshot, blocks=tuple(
                replace(block, visible=False) if block.object_id == first_block else block
                for block in snapshot.blocks
            ))
        return snapshot

    world.observe = occluded
    result = executor.run()
    placements = [event["block_id"] for event in world.events if event["stage"] == "PLACE"]
    assert placements.count(first_block) == 1
    if persistent:
        assert result.stage == TaskStage.SAFE_HALT
        assert result.reobservations == executor.max_reobservations
        assert manager.states["L0_0"] == SlotState.UNVERIFIED and len(placements) == 1
    else:
        assert result.stage == TaskStage.DONE and result.reobservations == 1
        assert len(result.verified_slots) == 10


def test_collapse_invalidates_descendants_and_halts_without_retreat(stack):
    executor, world, manager, events = stack
    seeded = {"L0_0": "synthetic_block_00", "L0_1": "synthetic_block_01", "L1_0": "synthetic_block_04"}
    for slot_id, block_id in seeded.items():
        world.blocks[block_id] = replace(
            world.blocks[block_id], location=BlockLocation.PLACED, center_m=manager.slots[slot_id].center_m,
        )
    observe = world.observe

    def collapse():
        if world.payload is not None:
            failed = seeded["L0_0"]
            world.blocks[failed] = replace(world.blocks[failed], center_m=(.4, .4, .025))
        return observe()

    world.observe = collapse
    result = executor.run()
    assert result.stage == TaskStage.SAFE_HALT and "collapsed" in result.reason
    assert result.verified_slots == ("L0_1",)
    assert manager.states["L0_0"] == manager.states["L1_0"] == SlotState.UNVERIFIED
    assert manager.reservations["L1_0"] == seeded["L1_0"]
    assert [e["stage"] for e in world.events] == ["PRE_GRASP", "GRASP", "MOCK_STOP"]
    assert world.payload is not None
    invalidated = next(data for name, data in events if name == "structure_invalidated")
    assert set(invalidated["slots"]) == {"L0_0", "L1_0"}


def test_restart_rescans_partial_stack_and_rejects_old_command(stack):
    executor, world, manager, _ = stack
    observe = world.observe

    def interrupted():
        if world._counter == 3:
            raise TimeoutError("mock sensor interrupted between transactions")
        return observe()

    world.observe = interrupted
    assert executor.run().verified_slots == ("L0_0",)
    with pytest.raises(RuntimeError, match="restart"):
        executor.run()
    old = world.events[0]
    replay = MockCommand(old["epoch"], old["sequence"], old["stage"], old["block_id"], old["slot_id"])
    first_run_event_count = len(world.events)
    new_manager = SceneManager(manager.slots.values())
    events = []
    restarted = OfflineExecutionManager(
        config=executor.config, scene_manager=new_manager, port=world, event_sink=lambda *e: events.append(e),
    )

    def check_replay():
        if world._counter == 3:
            with pytest.raises(ValueError, match="old run"):
                world.dispatch(replay, manager.slots[replay.slot_id])
        return observe()

    world.observe = check_replay
    result = restarted.run()
    assert result.stage == TaskStage.DONE and len(result.verified_slots) == 10
    assert next(data for name, data in events if name == "rescan")["verified"] == manager.occupants
    actions = world.events[first_run_event_count:]
    assert sum(action["stage"] == "GRASP" for action in actions) == 9
    assert actions[0]["sequence"] == 1 and actions[0]["epoch"] != replay.epoch
    assert not any(action["block_id"] == replay.block_id for action in actions)


def test_command_replay_rejected_within_session(stack):
    _, world, manager, _ = stack
    slot = manager.slots["L0_0"]
    with world.session() as epoch:
        command = MockCommand(epoch, 1, "PRE_GRASP", "synthetic_block_00", slot.slot_id)
        assert world.dispatch(command, slot)
        with pytest.raises(ValueError, match="out of sequence"):
            world.dispatch(command, slot)
    assert len(world.events) == 1


def test_restart_rejects_old_observation_before_dispatch(stack):
    executor, world, _, _ = stack
    old = world.observe()
    world.observe = lambda: old
    assert "epoch" in executor.run().reason
    assert [event["stage"] for event in world.events] == ["MOCK_STOP"]


def test_rescan_with_unverified_support_fails_without_partial_commit(stack):
    executor, world, manager, _ = stack
    for block_id, slot_id in (("synthetic_block_00", "L0_0"), ("synthetic_block_04", "L1_0")):
        world.blocks[block_id] = replace(
            world.blocks[block_id], location=BlockLocation.PLACED, center_m=manager.slots[slot_id].center_m,
        )
    result = executor.run()
    assert result.stage == TaskStage.SAFE_HALT and "unverified support" in result.reason
    assert not manager.occupants and not manager.reservations
    assert [event["stage"] for event in world.events] == ["MOCK_STOP"]


def test_rescan_does_not_act_when_hand_holds_a_block(stack):
    executor, world, _, _ = stack
    world.payload = "synthetic_block_00"
    world.hand_clear = False
    assert "clear hand" in executor.run().reason
    assert world.payload == "synthetic_block_00"
    assert [event["stage"] for event in world.events] == ["MOCK_STOP"]
