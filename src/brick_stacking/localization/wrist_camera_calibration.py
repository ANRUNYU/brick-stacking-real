"""Eye-in-hand point calibration using the existing joint point solver.

Fixed board center b, camera-to-reference X, measured base-to-reference A:
A X c = b, hence inverse(A) b = X c. Board orientation labels are unnecessary.
"""
from brick_stacking.localization.point_target_calibration import solve_point_target


def solve_wrist_camera(training,validation,*,camera_frame,candidate_id,
                       max_residual_m,max_condition_number,diagnostic_fit_only=False):
    training,validation=tuple(training),tuple(validation)
    if not training:raise ValueError('measured reference poses required')
    base,reference=training[0][1].target_frame,training[0][1].source_frame
    def invert(rows):
        result=[]
        for sample_id,a,c,stamp,clock in rows:
            if (a.target_frame,a.source_frame)!=(base,reference):raise ValueError('base/reference frame changed')
            result.append((sample_id,a.inverse(),c,stamp,clock))
        return result
    transform,report=solve_point_target(invert(training),invert(validation),camera_frame=camera_frame,
        candidate_id=candidate_id,max_residual_m=max_residual_m,max_condition_number=max_condition_number,
        diagnostic_fit_only=diagnostic_fit_only)
    report=dict(report)
    report['target_center_base_m']=report.pop('point_offset_reference_m')
    report.update(schema_version='c-wrist-camera-point-1',base_frame=base,camera_mount_frame=reference,
                  scope='fixed table board center / camera rigid to declared arm reference; not hand TCP or execution approval')
    return transform,report
