"""Eye-in-hand calibration solvers (Mode R center/corners & Mode H head-camera bridge).

Mode R (center): Fixed board center b, camera-to-reference X, measured base-to-reference A:
A X c = b, hence inverse(A) b = X c. Board orientation labels are unnecessary.

Mode R (multi-corner): Fixed board with known planar grid geometry on table, observed
across multiple arm poses. Simultaneously solves X = T_reference_wrist and
B = T_base_board from all N corners per pose, automatically resolving 180-deg symmetry.

Mode H (head bridge): Head camera observes all N chessboard corners in base frame (via known
T_base_head), while wrist camera observes the same N corners in wrist frame.
"""
import cv2
import numpy as np
from brick_stacking.localization.calibration import solve_point_pairs
from brick_stacking.localization.point_target_calibration import solve_point_target
from brick_stacking.localization.rigid_transforms import RigidTransform


def _skew(v):
    x,y,z=v
    return np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])


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


def solve_wrist_camera_from_head_bridge(training,validation=(),*,camera_frame,candidate_id,
                                        max_residual_m=.01,min_center_span_m=.04,diagnostic_fit_only=False):
    """Solve T_reference_camera (X) from paired head-camera & wrist-camera chessboard corners."""
    training,validation=tuple(training),tuple(validation)
    if type(diagnostic_fit_only) is not bool:
        raise ValueError('explicit boolean fit-only mode required')
    if len(training)<2 or (not diagnostic_fit_only and len(validation)<1) or (diagnostic_fit_only and validation):
        raise ValueError('>=2 training poses (and >=1 validation unless diagnostic_fit_only) required')
    if not candidate_id or not camera_frame:
        raise ValueError('candidate_id and camera_frame required')
    rows=training+validation
    ids=[r[0] for r in rows]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('unique sample IDs required')
    base,reference,clock_domain=training[0][1].target_frame,training[0][1].source_frame,training[0][1].clock_domain
    if len({base,reference,camera_frame})!=3:
        raise ValueError('distinct base/reference/camera frames required')

    def prepare(group):
        prepared=[]
        for sample_id,a,pts_base,pts_wrist,stamp,clock in group:
            if (a.target_frame,a.source_frame,a.clock_domain)!=(base,reference,clock_domain):
                raise ValueError('frame or clock_domain mismatch')
            if a.stamp_s is None or stamp!=a.stamp_s or clock!=clock_domain:
                raise ValueError('capture timestamp or clock mismatch')
            pb=np.asarray(pts_base,dtype=float)
            pw=np.asarray(pts_wrist,dtype=float)
            if pb.ndim!=2 or pw.ndim!=2 or pb.shape!=pw.shape or pb.shape[1]!=3 or len(pb)<4:
                raise ValueError('paired (N, 3) corner arrays with N>=4 required')
            if not np.isfinite(pb).all() or not np.isfinite(pw).all() or (pw[:,2]<=0).any():
                raise ValueError('finite positive-Z optical camera points required')
            pts_ref=a.inverse().apply(pb)
            prepared.append((sample_id,pts_ref,pw))
        return prepared

    train_prep=prepare(training)
    val_prep=prepare(validation) if validation else []

    wrist_centers=np.array([pw.mean(axis=0) for _,_,pw in train_prep])
    center_span=float(np.linalg.norm(wrist_centers.max(axis=0)-wrist_centers.min(axis=0)))
    if center_span<min_center_span_m:
        raise ValueError(f'insufficient board-to-wrist center translation span ({center_span:.4f} m < {min_center_span_m:.4f} m) to disambiguate 180-deg symmetry')

    best_transform=None
    best_flips=None
    best_rmse=float('inf')

    for seed_idx in range(len(train_prep)):
        for seed_flip in (False,True):
            flips=[False]*len(train_prep)
            flips[seed_idx]=seed_flip
            src_init=[train_prep[seed_idx][2][::-1] if seed_flip else train_prep[seed_idx][2]]
            dst_init=[train_prep[seed_idx][1]]
            n_pts=len(train_prep[seed_idx][1])
            for j,(_,pr,pw) in enumerate(train_prep):
                if j!=seed_idx:
                    src_init.append(np.repeat(pw.mean(axis=0,keepdims=True),n_pts,axis=0))
                    dst_init.append(np.repeat(pr.mean(axis=0,keepdims=True),n_pts,axis=0))
            cand_tf=solve_point_pairs(np.vstack(src_init),np.vstack(dst_init),
                                      source_frame=camera_frame,target_frame=reference,candidate_id=candidate_id)
            for _ in range(5):
                new_flips=[]
                for _,pr,pw in train_prep:
                    e_keep=np.mean(np.sum((cand_tf.apply(pw)-pr)**2,axis=1))
                    e_flip=np.mean(np.sum((cand_tf.apply(pw[::-1])-pr)**2,axis=1))
                    new_flips.append(bool(e_flip<e_keep))
                src_all=np.vstack([pw[::-1] if f else pw for (_,_,pw),f in zip(train_prep,new_flips)])
                dst_all=np.vstack([pr for _,pr,_ in train_prep])
                cand_tf=solve_point_pairs(src_all,dst_all,
                                          source_frame=camera_frame,target_frame=reference,candidate_id=candidate_id)
                if new_flips==flips:
                    break
                flips=new_flips
            residuals=np.linalg.norm(cand_tf.apply(src_all)-dst_all,axis=1)
            rmse=float(np.sqrt(np.mean(residuals**2)))
            if rmse<best_rmse:
                best_rmse=rmse
                best_transform=cand_tf
                best_flips=flips

    def evaluate_group(prep_group,fixed_flips=None):
        all_norms=[]
        center_norms=[]
        pose_rows=[]
        used_flips=[]
        for idx,(sample_id,pr,pw) in enumerate(prep_group):
            if fixed_flips is not None:
                flip=fixed_flips[idx]
            else:
                e_keep=np.mean(np.sum((best_transform.apply(pw)-pr)**2,axis=1))
                e_flip=np.mean(np.sum((best_transform.apply(pw[::-1])-pr)**2,axis=1))
                flip=bool(e_flip<e_keep)
            used_flips.append(flip)
            pw_aligned=pw[::-1] if flip else pw
            pred=best_transform.apply(pw_aligned)
            diff=pred-pr
            norms=np.linalg.norm(diff,axis=1)
            c_err=pred.mean(axis=0)-pr.mean(axis=0)
            c_norm=float(np.linalg.norm(c_err))
            all_norms.append(norms)
            center_norms.append(c_norm)
            pose_rows.append(dict(
                sample_id=sample_id,
                flipped_180=flip,
                center_error_reference_m=c_err.tolist(),
                center_norm_m=c_norm,
                corner_rmse_m=float(np.sqrt(np.mean(norms**2))),
                corner_max_m=float(norms.max()),
            ))
        flat=np.concatenate(all_norms)
        c_arr=np.asarray(center_norms)
        summary=dict(
            n_poses=len(prep_group),
            n_points=int(len(flat)),
            rmse_m=float(np.sqrt(np.mean(flat**2))),
            p95_m=float(np.percentile(flat,95)),
            max_m=float(flat.max()),
            center_rmse_m=float(np.sqrt(np.mean(c_arr**2))),
            center_max_m=float(c_arr.max()),
        )
        return summary,pose_rows,used_flips

    fit_summary,train_poses,train_flips=evaluate_group(train_prep,best_flips)
    val_summary,val_poses,val_flips=evaluate_group(val_prep) if val_prep else (None,[],[])
    fit_quality='PASS' if fit_summary['center_max_m']<=max_residual_m else 'FAIL'
    consistency='INCOMPLETE' if diagnostic_fit_only else (
        'PASS' if max(fit_summary['center_max_m'],val_summary['center_max_m'])<=max_residual_m else 'FAIL'
    )
    report=dict(
        schema_version='c-wrist-camera-head-bridge-1',
        candidate_id=candidate_id,
        base_frame=base,
        camera_mount_frame=reference,
        camera_frame=camera_frame,
        wrist_center_span_m=center_span,
        fit=fit_summary,
        validation=val_summary,
        training_residuals=train_poses,
        validation_residuals=val_poses,
        training_ids=ids[:len(training)],
        validation_ids=ids[len(training):],
        fit_quality=fit_quality,
        diagnostic_fit_only=diagnostic_fit_only,
        independent_validation='NOT_PERFORMED' if diagnostic_fit_only else 'PERFORMED',
        consistency=consistency,
        approved=False,
        motion_enabled=False,
        scope='head-bridge multi-corner eye-in-hand calibration; not hand TCP or execution approval',
    )
    return best_transform,report


def solve_wrist_camera_from_fixed_board_corners(training,validation=(),*,board_object_points_m,camera_frame,
                                                candidate_id,max_residual_m=.01,diagnostic_fit_only=False):
    """Solve T_reference_camera (X) and fixed T_base_board (B) from multi-pose wrist corners.

    Each row in `training` and `validation` is:
        (sample_id, T_base_reference, corners_wrist_m, stamp_s, clock_domain)
    Does not depend on any head camera extrinsic. Automatically disambiguates 180-deg flips.
    """
    training,validation=tuple(training),tuple(validation)
    if type(diagnostic_fit_only) is not bool:
        raise ValueError('explicit boolean fit-only mode required')
    if len(training)<3 or (not diagnostic_fit_only and len(validation)<1) or (diagnostic_fit_only and validation):
        raise ValueError('>=3 training poses (and >=1 validation unless diagnostic_fit_only) required')
    obj=np.asarray(board_object_points_m,dtype=float)
    if obj.ndim!=2 or obj.shape[1]!=3 or len(obj)<4 or not np.isfinite(obj).all():
        raise ValueError('finite (N, 3) board_object_points_m with N>=4 required')
    obj_centered=obj-obj.mean(axis=0)
    rows=training+validation
    ids=[r[0] for r in rows]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('unique sample IDs required')
    base,reference,clock_domain=training[0][1].target_frame,training[0][1].source_frame,training[0][1].clock_domain
    if len({base,reference,camera_frame})!=3:
        raise ValueError('distinct base/reference/camera frames required')

    def prepare(group):
        prepared=[]
        for sample_id,a,pts_wrist,stamp,clock in group:
            if (a.target_frame,a.source_frame,a.clock_domain)!=(base,reference,clock_domain):
                raise ValueError('frame or clock_domain mismatch')
            if a.stamp_s is None or stamp!=a.stamp_s or clock!=clock_domain:
                raise ValueError('capture timestamp or clock mismatch')
            pw=np.asarray(pts_wrist,dtype=float)
            if pw.shape!=obj.shape or not np.isfinite(pw).all() or (pw[:,2]<=0).any():
                raise ValueError('matching finite positive-Z optical camera corner array required')
            prepared.append((sample_id,a,pw))
        return prepared

    train_prep=prepare(training)
    val_prep=prepare(validation) if validation else []

    # Step 1: Linear initialization for board center b_center and X via center equation A_i^{-1} b = R_x c_i + t_x
    design=np.vstack([np.hstack((a.inverse().matrix[:3,:3],-np.kron(pw.mean(0).reshape(1,3),np.eye(3)),-np.eye(3))) for _,a,pw in train_prep])
    rhs=np.concatenate([-a.inverse().matrix[:3,3] for _,a,_ in train_prep])
    sol=np.linalg.lstsq(design,rhs,rcond=None)[0]
    b_init=sol[:3]
    r_init=sol[3:12].reshape(3,3,order='F')
    u,_,vt=np.linalg.svd(r_init);fix=np.eye(3);fix[2,2]=np.linalg.det(u@vt);r_init=u@fix@vt
    t_init=np.mean([a.inverse().apply(b_init.reshape(1,3))[0]-r_init@pw.mean(0) for _,a,pw in train_prep],axis=0)
    m_x0=np.eye(4);m_x0[:3,:3]=r_init;m_x0[:3,3]=t_init
    x_init_tf=RigidTransform(reference,camera_frame,m_x0,'offline_candidate',candidate_id)

    best_x=None
    best_b=None
    best_flips=None
    best_rmse=float('inf')

    for seed_flip in (False,True):
        cand_x=x_init_tf
        pw0=train_prep[0][2][::-1] if seed_flip else train_prep[0][2]
        cand_b=solve_point_pairs(obj_centered,train_prep[0][1].apply(cand_x.apply(pw0)),
                                 source_frame='board',target_frame=base,candidate_id=candidate_id+'_board')
        flips=[seed_flip]+[False]*(len(train_prep)-1)
        for step in range(15):
            board_pts_base=cand_b.apply(obj_centered)
            new_flips=[]
            src_x=[];dst_x=[]
            for idx,(_,a,pw) in enumerate(train_prep):
                target_ref=a.inverse().apply(board_pts_base)
                if step>0 or idx>0:
                    e_keep=np.mean(np.sum((cand_x.apply(pw)-target_ref)**2,axis=1))
                    e_flip=np.mean(np.sum((cand_tf_apply(cand_x,pw[::-1])-target_ref)**2,axis=1)) if False else np.mean(np.sum((cand_x.apply(pw[::-1])-target_ref)**2,axis=1))
                    fl=bool(e_flip<e_keep)
                else:
                    fl=seed_flip
                new_flips.append(fl)
                src_x.append(pw[::-1] if fl else pw)
                dst_x.append(target_ref)
            cand_x=solve_point_pairs(np.vstack(src_x),np.vstack(dst_x),
                                     source_frame=camera_frame,target_frame=reference,candidate_id=candidate_id)
            src_b=np.tile(obj_centered,(len(train_prep),1))
            dst_b=np.vstack([a.apply(cand_x.apply(pw[::-1] if fl else pw)) for (_,a,pw),fl in zip(train_prep,new_flips)])
            cand_b=solve_point_pairs(src_b,dst_b,
                                     source_frame='board',target_frame=base,candidate_id=candidate_id+'_board')
            flips=new_flips

        # Joint Gauss-Newton refinement on SE(3) x SE(3) for (Rx, tx, Rb, tb)
        rx_mat,tx_vec=cand_x.matrix[:3,:3].copy(),cand_x.matrix[:3,3].copy()
        rb_mat,tb_vec=cand_b.matrix[:3,:3].copy(),cand_b.matrix[:3,3].copy()
        aligned_pws=[pw[::-1] if fl else pw for (_,_,pw),fl in zip(train_prep,flips)]
        a_mats=[a.matrix for _,a,_ in train_prep]

        def compute_res(rx_m,tx_v,rb_m,tb_v):
            b_pts=(rb_m@obj_centered.T).T+tb_v
            out=[]
            for am,pw in zip(a_mats,aligned_pws):
                p_ref=(rx_m@pw.T).T+tx_v
                p_base=(am[:3,:3]@p_ref.T).T+am[:3,3]
                out.append((p_base-b_pts).ravel())
            return np.concatenate(out)

        for _ in range(40):
            err=compute_res(rx_mat,tx_vec,rb_mat,tb_vec)
            b_rot_pts=(rb_mat@obj_centered.T).T
            j_rows=[]
            for am,pw in zip(a_mats,aligned_pws):
                ra=am[:3,:3]
                rx_pw=(rx_mat@pw.T).T
                for k in range(len(obj_centered)):
                    j_rx=-ra@_skew(rx_pw[k])
                    j_tx=ra
                    j_rb=_skew(b_rot_pts[k])
                    j_tb=-np.eye(3)
                    j_rows.append(np.hstack((j_rx,j_tx,j_rb,j_tb)))
            jac=np.vstack(j_rows)
            delta=np.linalg.lstsq(jac,-err,rcond=None)[0]
            if np.linalg.norm(delta)<1e-10:
                break
            for scale in (1.,.5,.25,.125,.0625,.03125):
                n_rx=cv2.Rodrigues(delta[:3]*scale)[0]@rx_mat
                n_tx=tx_vec+delta[3:6]*scale
                n_rb=cv2.Rodrigues(delta[6:9]*scale)[0]@rb_mat
                n_tb=tb_vec+delta[9:12]*scale
                n_err=compute_res(n_rx,n_tx,n_rb,n_tb)
                if n_err@n_err<err@err:
                    rx_mat,tx_vec,rb_mat,tb_vec=n_rx,n_tx,n_rb,n_tb
                    break
            else:
                break

        mx=np.eye(4);mx[:3,:3]=rx_mat;mx[:3,3]=tx_vec
        mb=np.eye(4);mb[:3,:3]=rb_mat;mb[:3,3]=tb_vec
        cand_x=RigidTransform(reference,camera_frame,mx,'offline_candidate',candidate_id)
        cand_b=RigidTransform(base,'board',mb,'offline_candidate',candidate_id+'_board')
        errs=compute_res(rx_mat,tx_vec,rb_mat,tb_vec).reshape(-1,3)
        rmse=float(np.sqrt(np.mean(np.sum(errs**2,axis=1))))
        if rmse<best_rmse:
            best_rmse=rmse;best_x=cand_x;best_b=cand_b;best_flips=flips

    board_pts_base=best_b.apply(obj_centered)

    def evaluate_group(prep_group,fixed_flips=None):
        all_norms=[];center_norms=[];pose_rows=[]
        for idx,(sample_id,a,pw) in enumerate(prep_group):
            if fixed_flips is not None:
                flip=fixed_flips[idx]
            else:
                e_keep=np.mean(np.sum((a.apply(best_x.apply(pw))-board_pts_base)**2,axis=1))
                e_flip=np.mean(np.sum((a.apply(best_x.apply(pw[::-1]))-board_pts_base)**2,axis=1))
                flip=bool(e_flip<e_keep)
            pw_aligned=pw[::-1] if flip else pw
            pred_base=a.apply(best_x.apply(pw_aligned))
            diff=pred_base-board_pts_base
            norms=np.linalg.norm(diff,axis=1)
            c_err=pred_base.mean(axis=0)-board_pts_base.mean(axis=0)
            c_norm=float(np.linalg.norm(c_err))
            all_norms.append(norms);center_norms.append(c_norm)
            pose_rows.append(dict(
                sample_id=sample_id,
                flipped_180=flip,
                residual_base_m=c_err.tolist(),
                norm_m=c_norm,
                corner_rmse_m=float(np.sqrt(np.mean(norms**2))),
                corner_max_m=float(norms.max()),
            ))
        flat=np.concatenate(all_norms)
        c_arr=np.asarray(center_norms)
        return dict(
            n_poses=len(prep_group),
            n_points=int(len(flat)),
            rmse_m=float(np.sqrt(np.mean(flat**2))),
            p95_m=float(np.percentile(flat,95)),
            max_m=float(flat.max()),
            center_rmse_m=float(np.sqrt(np.mean(c_arr**2))),
            center_max_m=float(c_arr.max()),
        ),pose_rows

    fit_summary,train_poses=evaluate_group(train_prep,best_flips)
    val_summary,val_poses=evaluate_group(val_prep) if val_prep else (None,[])
    fit_quality='PASS' if fit_summary['center_rmse_m']<=max_residual_m else 'FAIL'
    consistency='INCOMPLETE' if diagnostic_fit_only else (
        'PASS' if max(fit_summary['center_rmse_m'],val_summary['center_rmse_m'])<=max_residual_m else 'FAIL'
    )
    report=dict(
        schema_version='c-wrist-camera-fixed-board-corners-1',
        candidate_id=candidate_id,
        base_frame=base,
        camera_mount_frame=reference,
        camera_frame=camera_frame,
        target_center_base_m=board_pts_base.mean(axis=0).tolist(),
        T_base_board=best_b.matrix.tolist(),
        fit=fit_summary,
        validation=val_summary,
        training_residuals=train_poses,
        validation_residuals=val_poses,
        training_ids=ids[:len(training)],
        validation_ids=ids[len(training):],
        fit_quality=fit_quality,
        diagnostic_fit_only=diagnostic_fit_only,
        independent_validation='NOT_PERFORMED' if diagnostic_fit_only else 'PERFORMED',
        consistency=consistency,
        approved=False,
        motion_enabled=False,
        scope='fixed table board multi-corner eye-in-hand calibration; not hand TCP or execution approval',
    )
    return best_x,report
