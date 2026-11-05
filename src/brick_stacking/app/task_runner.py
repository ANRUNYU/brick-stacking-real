"""Ten-block mock scene/state workflow, independent of camera/physics/SDK."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from brick_stacking.models.scene_state import SceneBlock
from brick_stacking.models.task_state import TaskStage
from brick_stacking.scene.stacking_slots import build_stacking_slots
from brick_stacking.scene.scene_manager import SceneManager
from brick_stacking.hardware.mock_task_world import MockTaskWorld
from brick_stacking.execution.execution_manager import OfflineExecutionManager
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.runtime.run_recorder import RunRecorder


def compose_mock_task(config, event_sink, *, fault="none"):
    c, t = config["scene"], config["task"]
    if c["provenance"] != "synthetic" or t["handoff_enabled"] is not False:
        raise ValueError("this runner supports synthetic single-arm workflow only")
    if fault not in {"none", "one_grasp_failure", "grasp_exhaustion", "misplaced"}:
        raise ValueError("unknown synthetic fault")
    slots = build_stacking_slots(edge_m=c["nominal_edge_m"], layers=c["layers"],
        colors_by_layer=c["colors_by_layer"], center_xy_m=c["center_xy_m"],
        yaw_rad=c["yaw_rad"], frame_id=c["frame_id"])
    blocks = tuple(SceneBlock(f"synthetic_block_{i:02d}", slot.required_color,
        (.5 + i * .08, .4, c["nominal_edge_m"] / 2), c["frame_id"]) for i, slot in enumerate(slots))
    world = MockTaskWorld(blocks, tick_s=t["synthetic_tick_s"],
        fail_first_grasps={"one_grasp_failure": 1, "grasp_exhaustion": t["max_grasp_retries"] + 1}.get(fault, 0),
        placement_error_m=.1 if fault == "misplaced" else 0.)
    manager = SceneManager(slots)
    executor = OfflineExecutionManager(config=config, scene_manager=manager, port=world, event_sink=event_sink)
    return executor, world, manager


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="config/offline_task.yaml")
    p.add_argument("--output-root", default="artifacts/test_runs")
    p.add_argument("--fault", choices=["none", "one_grasp_failure", "grasp_exhaustion", "misplaced"], default="none")
    args = p.parse_args(argv)
    config = load_config(args.config)
    recorder = RunRecorder(args.output_root, "Verification", "TenBlocks", "MOCK", config)
    recorder.manifest["scenario_fault"] = args.fault
    try:
        executor, world, manager = compose_mock_task(config, recorder.event, fault=args.fault)
        result = executor.run()
        metrics = {**asdict(result), "scenario_fault": args.fault,
            "target_slots": len(manager.slots), "slot_states": manager.states,
            "stage_calls": dict(Counter(e["stage"] for e in world.events)),
            "synthetic": True, "vision_pipeline_exercised": False,
            "physical_grasp_verified": False, "control_ready": False}
        # For injected-fault scenarios, SAFE_HALT is an observed outcome, not
        # automatically a passing task. Unit tests assert expected fault behavior.
        verdict = "PASS" if result.stage == TaskStage.DONE else "FAIL"
        recorder.finish(verdict, metrics, result.reason)
        print(json.dumps({"result": verdict, "output": str(recorder.path.resolve()), **metrics}))
        return 0 if verdict == "PASS" else 1
    except Exception as exc:
        recorder.finish("ABORTED", {"hardware_tested": False}, str(exc))
        print(f"ABORTED: {exc}; report: {recorder.path}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
