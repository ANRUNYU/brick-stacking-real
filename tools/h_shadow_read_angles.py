"""Single raw P7 feedback read for stationary shadow snapshots."""
import json
import math
from datetime import datetime, timezone
from linkerbot import P7

if __name__=="__main__":
    arm=P7(side="left",interface_name="can2")
    try:
        q=list(map(float,arm.get_angles()))
        now=datetime.now(timezone.utc).isoformat()
    finally:
        arm.close()
    if len(q)!=7 or not all(map(math.isfinite,q)): raise ValueError("invalid seven-axis feedback")
    print(json.dumps(dict(q_rad=q,read_utc=now,side="left",interface="can2",joint_names=[f"J{i}" for i in range(1,8)])))
