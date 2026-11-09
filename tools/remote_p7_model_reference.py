"""Run on robot host with p7_sdk_venv; pure model math, no linkerbot imports.
Outputs are model references, never joint feedback or hardware approval.
"""
import json,hashlib,pathlib
import pinocchio as pin
import numpy as np
p=pathlib.Path('/home/qwer/linkerbot-p7-unpack/linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/src/linkerbot/arm/kinetix/urdf/p7__left.urdf')
m=pin.buildModelFromUrdf(str(p));d=m.createData();f=m.getFrameId('L8_Link')
rows=[]
for q in ([0.0]*7,[0.2,0.3,-0.1,0.2,0.1,-0.2,0.15],[-0.1,0.4,0.2,-0.3,0.15,0.1,-0.2]):
 pin.forwardKinematics(m,d,np.array(q));pin.updateFramePlacements(m,d)
 rows.append(dict(q_rad=q,T_base_tip=d.oMf[f].homogeneous.tolist()))
r=dict(source='remote_pinocchio_model_reference_not_joint_feedback',urdf_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),joint_names=list(m.names)[1:],base_frame='L_arm_root',tip_frame='L8_Link',samples=rows,motion_enabled=False,hardware_match_verified=False)
out=pathlib.Path('/home/qwer/c_calibration_runs/left_p7_fk_reference_20261107_C10.json')
with out.open('x') as handle: json.dump(r,handle,indent=2)
print(json.dumps(r))
