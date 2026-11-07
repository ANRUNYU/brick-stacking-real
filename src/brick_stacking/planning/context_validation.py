"""Version/time consistency checks only, not a safety gate or motion permit."""
import math

CONTEXT_KEYS=('arm_role','binding_version','model_version','joint_mapping_version',
              'camera_serial','camera_profile_version','camera_mount_version',
              'calibration_version','tcp_version','grasp_version','scene_version','clock_domain','epoch')


def validate_plan_context(planned,current,*,created_stamp_s,expires_stamp_s,now_s):
    reasons=[]
    for key in CONTEXT_KEYS:
        a,b=planned.get(key),current.get(key)
        if not isinstance(a,str) or not a.strip() or not isinstance(b,str) or not b.strip():
            reasons.append('UNKNOWN:'+key)
        elif a!=b: reasons.append('CHANGED:'+key)
    values=(created_stamp_s,expires_stamp_s,now_s)
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in values):
        reasons.append('INVALID_TIME')
    elif expires_stamp_s<=created_stamp_s or now_s<created_stamp_s or now_s>=expires_stamp_s:
        reasons.append('EXPIRED_OR_FUTURE')
    return dict(schema_version='c-context-check-1',context_consistency='PASS' if not reasons else 'FAIL',
                reasons=reasons,motion_enabled=False,
                scope='context comparison only; no hardware identity, stop or collision verification')
