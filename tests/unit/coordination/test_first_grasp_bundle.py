import copy,json
from pathlib import Path
import pytest
from brick_stacking.planning.first_grasp_bundle import PHASES,validate_side_approach,diagnostic_bundle
ROOT=Path(__file__).resolve().parents[3]


def points():
    xyz=[[-.1,0,.2],[0,0,.2],[0,0,.05],[0,0,.2],[.2,0,.2],[.3,0,.2],[.3,0,.05],[.3,0,.2],[.4,0,.2]]
    return [dict(phase=n,position_m=p) for n,p in zip(PHASES,xyz)]


def validate(p):return validate_side_approach(p,table_point=[0,0,0],table_normal=[0,0,1],approach_height_m=.15,lift_clearance_m=.1,clearance_m=.02,alignment_tolerance_m=.001)


def test_valid_shape_not_collision_or_motion_permission():
    r=validate(points());assert r['shape']=='PASS' and r['full_collision']=='UNKNOWN' and not r['motion_enabled']


@pytest.mark.parametrize('fault',['no_lift','low_horizontal','side_sweep','missing_phase','direct_drop'])
def test_reject_bad_side_approach(fault):
    p=points()
    if fault=='no_lift':p[3]['position_m'][2]=.05
    if fault=='low_horizontal':p[4]['position_m'][2]=.06
    if fault=='side_sweep':p[3]['position_m'][0]=.08
    if fault=='missing_phase':p.pop(0)
    if fault=='direct_drop':p[0]['position_m']=p[1]['position_m'][:]
    assert validate(p)['shape']=='FAIL'


def test_real_sample_join_stays_blocked():
    load=lambda p:json.loads((ROOT/p).read_text(encoding='utf-8'))
    r=diagnostic_bundle(load('docs/team/M/evidence/H0_C35_single_red_20261110.json'),
       load('calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json'),
       load('calibration/candidates/C49_left_grasp_offset_candidate_20261109.json'),
       refs={'localized_report':'fixture'},h0=load('docs/team/B/evidence/first_grasp_h0_draft.json'))
    assert 'INDEPENDENT_RULER_REFERENCE_MISSING' in r['reasons']
    assert 'CLOCK_ERROR_BOUND_UNKNOWN' in r['reasons']
    assert r['permit'] is None and not r['permit_request_allowed'] and r['flange_targets'] is None
    assert not r['temporary_C35_point_offset_used_as_TCP'] and not r['motion_enabled']


def test_side_shape_uses_table_normal_not_base_z():
    p=points()
    for item in p:
        x,y,z=item['position_m'];item['position_m']=[z,x,y]
    r=validate_side_approach(p,table_point=[0,0,0],table_normal=[1,0,0],approach_height_m=.15,
                           lift_clearance_m=.1,clearance_m=.02,alignment_tolerance_m=.001)
    assert r['shape']=='PASS'


def test_C49_frame_composition_preserves_block_goal_and_stays_unapproved():
    import numpy as np
    from brick_stacking.localization.rigid_transforms import RigidTransform
    from brick_stacking.planning.first_grasp_bundle import flange_goal_from_declared_block_pose
    c=json.loads((ROOT/'calibration/candidates/C49_left_grasp_offset_candidate_20261109.json').read_text(encoding='utf-8'))
    matrix=np.eye(4);matrix[:3,3]=[.4,-.2,-.45]
    block=RigidTransform('L_arm_root','declared_block',matrix,'synthetic')
    r=flange_goal_from_declared_block_pose(block,c,declared_block_frame='declared_block',
            grasp_version=c['context']['grasp_version'],same_grasp_assumption_confirmed=True)
    assert np.allclose(np.array(r['matrix'])@np.array(c['T_flange_block']),matrix)
    assert r['source_frame']==c['target_frame'] and not r['approved'] and not r['motion_enabled']
    with pytest.raises(ValueError):flange_goal_from_declared_block_pose(block,c,declared_block_frame='declared_block',
            grasp_version='wrong',same_grasp_assumption_confirmed=True)
