"""Greedy IoU matching for explicit manual image annotations, not 3D truth."""


def bbox_iou(a,b):
    ax,ay,aw,ah=a; bx,by,bw,bh=b
    intersection=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
    union=aw*ah+bw*bh-intersection
    return intersection/union if union>0 else 0.


def evaluate_candidates(candidates,labels,*,min_iou):
    if not 0 < min_iou <= 1:
        raise ValueError("valid annotation match threshold required")
    accepted=[c for c in candidates if c["status"]=="SINGLE_CUBE_CANDIDATE"]
    edges=sorted(((bbox_iou(c["bbox_xywh"],g["bbox_xywh"]),i,j)
                  for i,c in enumerate(accepted) for j,g in enumerate(labels) if c["color"]==g["color"]),reverse=True)
    used_candidates,used_labels=set(),set()
    matches=[]
    for iou,i,j in edges:
        if iou>=min_iou and i not in used_candidates and j not in used_labels:
            used_candidates.add(i);used_labels.add(j)
            matches.append({"candidate_id":accepted[i]["candidate_id"],"label_id":labels[j]["id"],"iou":iou})
    tp=len(matches)
    return dict(true_positives=tp,false_positives=len(accepted)-tp,false_negatives=len(labels)-tp,
        ambiguous=sum(c["status"]=="AMBIGUOUS" for c in candidates),total_candidates=len(candidates),
        accepted_candidates=len(accepted),matches=matches,
        precision=tp/len(accepted) if accepted else None,recall=tp/len(labels) if labels else None)
