from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from brick_stacking.models.scene_state import SceneBlock, SceneSnapshot, Slot, SlotState
from brick_stacking.planning.task_scheduler import choose_task
from brick_stacking.scene.scene_manager import SceneManager
from brick_stacking.scene.stacking_slots import build_stacking_slots


def candidate(name, x, color="red"):
    return SceneBlock(name, color, (x, .4, .025), "table")


def frame(stamp, *blocks, epoch="run-1"):
    return SceneSnapshot(f"frame-{stamp}", epoch, stamp, "test-clock", blocks, True, "synthetic")


def test_same_color_ids_survive_candidate_reorder_and_occlusion():
    manager = SceneManager((), supply_match_distance_m=.03)
    first = manager.update_supply(frame(1., candidate("a", .2), candidate("b", .4)))
    left, right = [block.object_id for block in first.blocks]
    assert left != right
    second = manager.update_supply(frame(2., candidate("a", .41), candidate("b", .21)))
    assert [(block.object_id, block.center_m[0]) for block in second.blocks] == [
        (left, .21), (right, .41),
    ]
    third = manager.update_supply(frame(3., candidate("reappearing", .22), candidate("too-far", .8)))
    assert [(block.object_id, block.visible) for block in third.blocks] == [(left, True), (right, False)]
    fourth = manager.update_supply(frame(4., candidate("left", .23), candidate("right", .42)))
    assert [(block.object_id, block.visible) for block in fourth.blocks] == [(left, True), (right, True)]


def test_ambiguous_same_color_tracks_are_not_reassigned():
    slot = Slot("target", 0, "red", (0., 0., .025), "table", ())
    manager = SceneManager((slot,), supply_match_distance_m=.04)
    first = manager.update_supply(frame(1., candidate("a", .2), candidate("b", .26)))
    assert choose_task(first, manager) is not None
    merged = manager.update_supply(frame(2., candidate("merged", .23)))
    assert len(merged.blocks) == 2 and all(block.ambiguous for block in merged.blocks)
    assert choose_task(merged, manager) is None
    split = manager.update_supply(frame(3., candidate("a", .2), candidate("b", .26)))
    assert choose_task(split, manager) is None


def test_stale_and_cross_epoch_frames_leave_tracks_unchanged():
    manager = SceneManager((), supply_match_distance_m=.03)
    first = manager.update_supply(frame(2., candidate("a", .2)))
    with pytest.raises(ValueError, match="same stream"):
        manager.update_supply(frame(1., candidate("a", .8)))
    with pytest.raises(ValueError, match="same stream"):
        manager.update_supply(frame(3., candidate("a", .8), epoch="reset"))
    later = manager.update_supply(frame(3., candidate("b", .21)))
    assert later.blocks[0].object_id == first.blocks[0].object_id and later.blocks[0].visible


def test_support_dag_rejects_missing_slots_and_cycles():
    base = Slot("base", 0, "red", (0., 0., .025), "table", ())
    upper = Slot("upper", 1, "yellow", (0., 0., .075), "table", ("base",))
    with pytest.raises(ValueError, match="unknown slot"):
        SceneManager((upper,))
    with pytest.raises(ValueError, match="cycle"):
        SceneManager((upper, replace(base, supports=("upper",))))
    manager = SceneManager((upper, base))
    manager.reserve("base", "red-1")
    manager.mark_unverified("base")
    assert not manager.ready_slots()
    manager.commit_verified("base", "red-1")
    assert manager.ready_slots() == (upper,)


@pytest.mark.parametrize(("slots", "blocks"), [(("a", "a"), ("x", "y")), (("a", "b"), ("x", "x"))])
def test_competing_reservations_allow_one_owner(slots, blocks):
    manager = SceneManager(tuple(Slot(s, 0, "red", (0., 0., .025), "table", ()) for s in ("a", "b")))
    barrier = Barrier(2, timeout=5)

    def reserve(slot, block):
        barrier.wait()
        try:
            manager.reserve(slot, block)
        except ValueError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(reserve, slots, blocks)) == 1
    assert len(manager.reservations) == 1


def test_scheduler_skips_reserved_block_and_reuses_it_after_pre_pick_cancel():
    slots = tuple(Slot(s, 0, "red", (0., 0., .025), "table", ()) for s in ("a", "b"))
    manager = SceneManager(slots, supply_match_distance_m=.03)
    snapshot = manager.update_supply(frame(1., candidate("a", .2), candidate("b", .4)))
    block, slot = choose_task(snapshot, manager)
    manager.reserve(slot.slot_id, block.object_id)
    other, _ = choose_task(snapshot, manager)
    assert other.object_id != block.object_id
    manager.cancel_before_pick(slot.slot_id)
    assert choose_task(snapshot, manager) == (block, slot)


def test_scheduler_waits_for_current_layer_even_when_upper_support_is_ready():
    slots = build_stacking_slots(edge_m=.05, layers=[2, 1], colors_by_layer=["red", "yellow"],
                                 center_xy_m=(0., 0.), yaw_rad=0., frame_id="table")
    upper = replace(slots[-1], supports=(slots[0].slot_id,))
    manager = SceneManager((*slots[:-1], upper))
    manager.reserve(slots[0].slot_id, "red-1")
    manager.mark_unverified(slots[0].slot_id)
    manager.commit_verified(slots[0].slot_id, "red-1")
    assert upper in manager.ready_slots()
    assert choose_task(frame(1., candidate("yellow-1", .3, "yellow")), manager) is None


def test_ten_block_plan_tracks_entities_and_respects_color_and_support_order():
    colors = ["red", "yellow", "blue", "green"]
    counts = [4, 3, 2, 1]
    slots = build_stacking_slots(edge_m=.05, layers=counts, colors_by_layer=colors,
                                 center_xy_m=(0., 0.), yaw_rad=0., frame_id="table")
    manager = SceneManager(reversed(slots), supply_match_distance_m=.02)
    supply = [(color, (i + 1) * .1) for color, count in zip(colors, counts) for i in range(count)]
    identities = {}
    ordered_colors = []
    for stamp in range(1, 11):
        observations = [candidate(f"candidate-{stamp}-{i}", x, color)
                        for i, (color, x) in enumerate(reversed(supply))]
        snapshot = manager.update_supply(frame(float(stamp), *observations))
        for block in snapshot.blocks:
            key = block.color, block.center_m[0]
            assert identities.setdefault(key, block.object_id) == block.object_id
        block, slot = choose_task(snapshot, manager)
        assert all(manager.states[key] == SlotState.PLACED_VERIFIED for key in slot.supports)
        ordered_colors.append(block.color)
        manager.reserve(slot.slot_id, block.object_id)
        manager.mark_unverified(slot.slot_id)
        manager.commit_verified(slot.slot_id, block.object_id)
        supply.remove((block.color, block.center_m[0]))
    assert ordered_colors == [color for color, count in zip(colors, counts) for _ in range(count)]
    assert len(set(manager.occupants.values())) == 10
    assert Counter(manager.states.values()) == {SlotState.PLACED_VERIFIED: 10}
