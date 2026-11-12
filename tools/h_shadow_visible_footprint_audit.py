"""Independently replay the first rejected flange interval; visible support only."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from h_shadow_path import fk

def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("frame","observation","plan","calibration","output"):
        parser.add_argument(key,type=Path)
    a=parser.parse_args()
    plan=load(a.plan)["plan"]; obs=load(a.observation)
    assert plan["observation"]==obs["source_frame"]==a.frame.name
    t=np.array(load(a.calibration)["T_base_camera"]); inv=np.linalg.inv(t)
    with np.load(a.frame) as f:
        z=f["depth_m"]; k=f["k"]; img=cv2.cvtColor(f["rgb"],cv2.COLOR_RGB2BGR)
    yy,xx=np.indices(z.shape)
    points=np.stack(((xx-k[0,2])*z/k[0,0],(yy-k[1,2])*z/k[1,1],z),axis=-1)
    n=np.array(obs["table_plane_camera"]["upward_normal_camera"])
    origin=np.array(obs["top_center_camera_m"])-n*obs["top_fit"]["height_m"]
    mask=(np.isfinite(z)&(z>0)&(np.abs((points-origin)@n)<.008)).astype("uint8")
    contours=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
    contour=max(contours,key=cv2.contourArea)
    cv2.drawContours(img,[contour],-1,(0,220,0),1)
    def pixel(p):
        if p[2]<=0: raise ValueError("behind camera")
        return (k@p)[:2]/p[2]
    img=cv2.copyMakeBorder(img,0,420,0,0,cv2.BORDER_CONSTANT,value=(40,40,40))
    cv2.putText(img,"Below here: outside the camera image",(10,z.shape[0]+24),0,.6,(230,230,230),1)
    start=fk(plan["seed"]).matrix[:3,3]
    up=t[:3,:3]@n
    target=np.asarray(plan["target_base_L8"])[:3,3]
    lift=start+up*(max(start@up,target@up)+.03-start@up)
    cv2.drawMarker(img,tuple(np.rint(pixel((inv@np.r_[lift,1])[:3])).astype(int)),(255,255,0))
    rows=[]
    for q in np.linspace(plan["seed"],plan["waypoints"][0]["ik"]["positions_rad"],9):
        base=fk(q).matrix[:3,3]; cam=(inv@np.r_[base,1])[:3]
        h=float((cam-origin)@n); uv=pixel(cam-h*n)
        dist=cv2.pointPolygonTest(contour,tuple(uv),True)
        rows.append(dict(base_m=base.tolist(),height_m=h,foot_uv=uv.tolist(),signed_edge_px=dist))
        cv2.circle(img,tuple(np.rint(uv).astype(int)),3,(0,140,255),-1)
    cv2.drawMarker(img,tuple(np.rint(pixel((inv@np.r_[rows[0]["base_m"],1])[:3])).astype(int)),(0,255,255))
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/"projection.png").write_bytes(cv2.imencode(".png",img)[1].tobytes())
    out=dict(full_lift_goal_m=lift.tolist(),frame=a.frame.name,method="normal foot projected onto largest visible contiguous 8 mm plane support exterior",samples=rows,below_inside=sum(r["height_m"]<0 and r["signed_edge_px"]>=0 for r in rows),phase="first lift subinterval",control_ready=False)
    (a.output/"samples.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf8")
    print(out["below_inside"],[(round(r["height_m"]*1000,1),round(r["signed_edge_px"],1)) for r in rows])
if __name__=="__main__":main()
