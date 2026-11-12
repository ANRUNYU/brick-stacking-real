"""Snapshot comparison only. No trajectory execution API."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import cv2
import numpy as np
from h_shadow_path import plan, load, root

evidence = root / "docs/team/B/evidence/line_h"
sys.path.insert(0,str(evidence/"left_preshape_20261112_100523_review"))
from h_shadow_localizer import localize

def read_arm(python):
    output = subprocess.check_output([python, str(root/"tools/h_shadow_read_angles.py")], text=True)
    return json.loads(output.strip().splitlines()[-1])

def run(args, report):
    cal = root/"calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json"
    candidate = load(evidence/"readonly_shadow/candidate_preshape_relative.json")
    if args.capture:
        capture = args.capture
        q = load(args.record)
    else:
        capture = args.output/"rgbd"
        before = read_arm(args.arm_python)
        report["before"] = before
        subprocess.run([sys.executable,str(args.probe),"--capture","--serial","CP2L863000KL",
            "--width","640","--height","480","--fps","15","--warmup-frames","30",
            "--allow-unstable-warmup","--fixed-color-exposure","24","--fixed-color-gain","12",
            "--frames","10","--seconds","30","--output",str(capture)],check=True)
        q = read_arm(args.arm_python)
        report["after"] = q
        drift = np.max(np.abs(np.asarray(q["q_rad"])-before["q_rad"]))
        report["max_endpoint_joint_change_rad"] = float(drift)
        if drift > .01: raise ValueError("arm feedback changed across capture")
    if q["joint_names"] != [f"J{i}" for i in range(1,8)] or q["side"]!="left" or q["interface"]!="can2":
        raise ValueError("unexpected joint feedback identity")
    cam = load(capture/"camera_report.json")
    if cam["result"]!="CAPTURED" or cam["captured_pairs"]!=10 or cam["selected"]["serial"]!="CP2L863000KL":
        raise ValueError("incomplete or wrong capture")
    observations=[]
    files=sorted(capture.glob("frame_*.npz"))
    if len(files)!=10: raise ValueError("expected ten frame files")
    for frame in files:
        dest=args.output/(frame.stem+".json")
        localize(argparse.Namespace(capture_dir=capture,frame=frame.name,edge_m=.05,calibration=cal,output=dest))
        observations.append(load(dest))
    path=plan(observations,q,candidate)
    report["plan"]=path
    if path["status"]!="MODEL_PATH_ONLY": raise ValueError(path["status"])
    with np.load(capture/path["observation"],allow_pickle=False) as data:
        image=cv2.cvtColor(data["rgb"],cv2.COLOR_RGB2BGR)
        k=data["k"]
    cam_from_base=np.linalg.inv(load(cal)["T_base_camera"])
    pixels=[]
    for row in path["waypoints"]:
        xyz=(cam_from_base @ np.r_[row["achieved_xyz_m"],1])[:3]
        if xyz[2]<=0:
            pixels.append(None)
        else:
            pixels.append(np.rint((k@xyz)[:2]/xyz[2]).astype(int).tolist())
    for a,b in zip(pixels,pixels[1:]):
        if a is not None and b is not None: cv2.arrowedLine(image,tuple(a),tuple(b),(0,200,255),2)
    if pixels[-1] is not None: cv2.drawMarker(image,tuple(pixels[-1]),(255,0,255),cv2.MARKER_CROSS,18,2)
    (args.output/"wrist_projection.png").write_bytes(cv2.imencode(".png",image)[1].tobytes())
    report["projected_wrist_pixels"]=pixels

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True,type=Path)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--capture",type=Path); g.add_argument("--live-readonly",action="store_true")
    p.add_argument("--record",type=Path); p.add_argument("--arm-python",type=Path)
    p.add_argument("--probe",type=Path)
    a=p.parse_args()
    if a.capture and not a.record: p.error("--capture requires --record")
    if a.live_readonly and not (a.arm_python and a.probe): p.error("specify --arm-python and --probe")
    a.output.mkdir(parents=True,exist_ok=False)
    report=dict(mode="live_stationary_snapshot" if a.live_readonly else "archived_replay",
                utc=datetime.now(timezone.utc).isoformat(),control_ready=False,motion_commanded=False)
    try:
        run(a,report); report["status"]="REVIEW_ONLY"
    except Exception as exc:
        report["status"]="INCOMPLETE"; report["reason"]=str(exc)
    finally:
        (a.output/"shadow_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    print(report["status"],a.output)
    sys.exit(0 if report["status"]=="REVIEW_ONLY" else 1)
