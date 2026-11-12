"""Offline replay only. Run with the repository src on PYTHONPATH."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.localization.rigid_transforms import RigidTransform
from brick_stacking.planning.numerical_ik import solve_pose_ik

root = Path(__file__).resolve().parents[1]
def load(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def matrix(pose):
    x,y,z,w = pose["quaternion_xyzw"]
    rotation = np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                         [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                         [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])
    out = np.eye(4)
    out[:3,:3],out[:3,3] = rotation,pose["translation_m"]
    return out

model = root/"config/models/p7_left/p7__left.urdf"
lock = load(model.with_name("LOCK.json"))["urdf_sha256"]
assert hashlib.sha256(model.read_bytes()).hexdigest()==lock
names = [f"L{i}_Joint" for i in range(1,8)]
limits_xml = {j.get("name"):j.find("limit") for j in ET.parse(model).findall("joint")}
limits = SimpleNamespace(joint_names=names,model_version=lock,
    lower_rad=[float(limits_xml[n].get("lower")) for n in names],
    upper_rad=[float(limits_xml[n].get("upper")) for n in names])
def fk(q):
    return urdf_forward_kinematics(model,dict(zip(names,q,strict=True)),base_frame="L_arm_root",tip_frame="L8_Link")[0]

def plan(poses, record, candidate):
    relative = matrix(candidate["T_L8_block"])
    centers = np.array([p["model_center_base_m"] for p in poses])
    i = int(np.argmin(np.linalg.norm(centers-np.median(centers,axis=0),axis=1)))
    obs = poses[i]
    block = matrix(obs["base_block"])
    target = block@np.linalg.inv(relative)
    normal = block[:3,2]
    table_point = np.asarray(obs["top_center_base_m"])-obs["top_fit"]["height_m"]*normal
    q = np.array(record["q_rad"])
    start = fk(q).matrix
    # Raise both endpoints to a shared transit height for this isolated model test.
    height = max(start[:3,3]@normal,target[:3,3]@normal)+.03
    raised_start = start[:3,3]+(height-start[:3,3]@normal)*normal
    raised_end = target[:3,3]+(height-target[:3,3]@normal)*normal
    result = dict(observation=obs["source_frame"],target_base_L8=target.tolist(),seed=q.tolist(),
                  waypoints=[],status="MODEL_PATH_ONLY",control_ready=False,full_collision="UNKNOWN")
    prev = start[:3,3]
    for phase,end,rot in [("lift",raised_start,start[:3,:3]),("transfer",raised_end,target[:3,:3]),("descend",target[:3,3],target[:3,:3])]:
        count = max(1,int(np.ceil(np.linalg.norm(end-prev)/.015)))
        for xyz in np.linspace(prev,end,count+1)[1:]:
            goal=np.eye(4);goal[:3,:3]=rot;goal[:3,3]=xyz
            sol=solve_pose_ik(fk,RigidTransform("L_arm_root","L8_Link",goal,"offline"),
                q,limits,position_tolerance_m=.002,rotation_tolerance_rad=.02,
                orientation_weight_m_per_rad=.1,damping=.008,max_step_rad=.10,max_iterations=80,difference_step_rad=.0001)
            row=dict(phase=phase,ik=sol)
            result["waypoints"].append(row)
            if sol["ik"]!="PASS":
                result["status"]="REJECT_IK";return result
            next_q=np.array(sol["positions_rad"])
            row["achieved_xyz_m"]=fk(next_q).matrix[:3,3].tolist()
            clearance=[float((fk(v).matrix[:3,3]-table_point)@normal) for v in np.linspace(q,next_q,9)]
            row["min_sampled_flange_clearance_m"]=min(clearance)
            if min(clearance)<=0:
                result["status"]="REJECT_TABLE";return result
            q=next_q
        prev=end
    return result

