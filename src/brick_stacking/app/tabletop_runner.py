"""Recorded tabletop prototype + explicit, optional 2D scene-label evaluation."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import time
from pathlib import Path
import cv2
import numpy as np
from brick_stacking.hardware.mock_devices import RecordedCamera
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.runtime.run_recorder import RunRecorder
from brick_stacking.vision.tabletop_segmentation import TabletopDetector
from brick_stacking.vision.evaluation import evaluate_candidates
from brick_stacking.vision.scene_consistency import SceneConsistencyMonitor,static_sequence_acceptance


def render_overlay(frame,result,polygon):
    image_h,image_w=frame.rgb.shape[:2]
    image=np.full((max(image_h,100+len(result.candidates)*30),image_w+300,3),28,np.uint8)
    image[:image_h,:image_w]=cv2.cvtColor(frame.rgb,cv2.COLOR_RGB2BGR)
    contours,_=cv2.findContours(result.roi_mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(image,contours,-1,(255,255,0),2)
    cv2.putText(image,"Tabletop candidates",(image_w+12,30),cv2.FONT_HERSHEY_SIMPLEX,.55,(240,240,240),1)
    cv2.putText(image,"Camera frame / no world pose",(image_w+12,54),cv2.FONT_HERSHEY_SIMPLEX,.4,(180,180,180),1)
    for index,c in enumerate(result.candidates,1):
        x,y,w,h=c["bbox_xywh"]
        color=(0,220,0) if c["status"]=="SINGLE_CUBE_CANDIDATE" else (0,150,255)
        cv2.rectangle(image,(x,y),(x+w,y+h),color,1)
        cv2.putText(image,str(index),(x,max(10,y-3)),cv2.FONT_HERSHEY_SIMPLEX,.4,color,1)
        status="single" if c["status"]=="SINGLE_CUBE_CANDIDATE" else "ambiguous"
        cv2.putText(image,f"{index:02d}  {c['color']}  {status}",(image_w+12,85+(index-1)*30),
                    cv2.FONT_HERSHEY_SIMPLEX,.44,color,1)
    return image


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config",default="config/vision_profiles/head_sunlight_candidate.yaml")
    p.add_argument("--recordings",nargs="+",required=True)
    p.add_argument("--labels",type=Path)
    p.add_argument("--output-root",default="artifacts/test_runs")
    args=p.parse_args(argv)
    config=load_config(args.config)
    profile=config["tabletop"]
    detector=TabletopDetector(profile)
    monitor=SceneConsistencyMonitor(**profile['temporal']) if profile.get('temporal') else None
    labels=json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else None
    if labels and profile.get('surface_mode','fixed_roi')!='automatic' and labels["image_size_wh"]!=profile["image_size_wh"]:
        raise ValueError("label image dimensions mismatch")
    recorder=RunRecorder(args.output_root,"Perception","TabletopBlocks","RGBD",config)
    observations=[]
    try:
        for index,path in enumerate(args.recordings):
            frame=RecordedCamera([path]).get_synced_rgbd()
            if labels and labels['image_size_wh'] != [frame.rgb.shape[1],frame.rgb.shape[0]]:
                raise ValueError('label/frame image dimensions mismatch')
            started=time.perf_counter()
            result=detector.detect(frame)
            data={"recording":str(path),"processing_s":time.perf_counter()-started,"plane":asdict(result.plane),"diagnostics":result.diagnostics,"candidates":result.candidates,
                "accepted_color_counts":dict(Counter(c["color"] for c in result.candidates if c["status"]=="SINGLE_CUBE_CANDIDATE"))}
            if monitor:
                data['temporal']=monitor.update(frame,result)
            data['detection_s']=data['processing_s']
            data['processing_s']=time.perf_counter()-started
            if labels:
                data["evaluation"]=evaluate_candidates(result.candidates,labels["objects"],min_iou=labels["min_iou"])
            recorder.event("observation",data)
            observations.append(data)
            cv2.imwrite(str(recorder.path/f"overlay_{index:03d}.png"),render_overlay(frame,result,profile.get("roi_polygon_uv")))
            if index==0:
                heights=np.clip(np.nan_to_num(result.heights_m,nan=0.)/.1*255,0,255).astype(np.uint8)
                preview=cv2.applyColorMap(heights,cv2.COLORMAP_TURBO)
                preview[result.roi_mask==0]=0
                cv2.imwrite(str(recorder.path/"height_above_table.png"),preview)
        evaluations=[o["evaluation"] for o in observations if "evaluation" in o]
        matched=bool(evaluations) and all(e["false_positives"]==0 and e["false_negatives"]==0 and e["ambiguous"]==0 for e in evaluations)
        metrics={"frames":len(observations),"per_frame_color_counts":[o["accepted_color_counts"] for o in observations],
            "processing_s":[o['processing_s'] for o in observations],
            "temporal":[o['temporal'] for o in observations if 'temporal' in o],
            "evaluations":evaluations,"all_same_scene_labels_matched":matched,
            "annotation_source":labels["source"] if labels else None,"metric_accuracy_verified":False,
            "independent_scene_validation":False,"robot_control_accessed":False,"control_ready":False}
        # PASS is expressly a labelled recorded-scene smoke check only.
        verdict=("PASS" if matched else "FAIL") if labels else "INCONCLUSIVE"
        if monitor:
            sequence=static_sequence_acceptance(metrics['temporal'],monitor.required_frames)
            metrics['temporal_acceptance']=sequence
            if verdict=='PASS':
                verdict=sequence['result']
        recorder.finish(verdict,metrics,"Same-scene provisional 2D label test. First frame used for tuning; consecutive frames are not independent scenes. No world/pose accuracy acceptance.")
        print(json.dumps({"result":verdict,"output":str(recorder.path.resolve()),"frames":len(observations),
                          "counts":metrics["per_frame_color_counts"],"all_same_scene_labels_matched":matched}))
        return 0 if verdict!="FAIL" else 1
    except Exception as exc:
        recorder.finish("ABORTED",{"robot_control_accessed":False},str(exc))
        print(f"ABORTED: {exc}; {recorder.path}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
