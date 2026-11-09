from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from brick_stacking.models.camera_frame import CameraFrame
from brick_stacking.localization.table_plane import TablePlane
from brick_stacking.vision.scene_consistency import SceneConsistencyMonitor,static_sequence_acceptance


def sample(stamp=1.,clock='epoch',position=(0,0,.975)):
    frame=CameraFrame(np.full((64,64,3),120,np.uint8),np.ones((64,64)),
        np.array([[200,0,32],[0,200,32],[0,0,1.]]),'fixture','optical',stamp,clock,'synthetic',True,True)
    observation=SimpleNamespace(plane=TablePlane((0,0,-1),1.,.9,.001),
        roi_mask=np.full((64,64),255,np.uint8),candidates=[{'candidate_id':'frame_specific',
        'color':'red','status':'SINGLE_CUBE_CANDIDATE','center_camera_m':list(position),
        'bbox_xywh':[27,27,11,11]}])
    return frame,observation


def ready():
    monitor=SceneConsistencyMonitor()
    for stamp in [1.,1.1,1.2]:state=monitor.update(*sample(stamp))
    assert state['state']=='CONFIRMED'
    return monitor


def test_confirmation_uses_current_frames_without_predicting_positions():
    monitor=ready()
    state=monitor.update(*sample(1.3))
    assert state['scene_consistent'] and not state['positions_predicted']
    assert not state['control_ready'] and not state['reference_stationarity_verified']


@pytest.mark.parametrize('stamp',[1.2,1.1])
def test_duplicate_or_backward_frame_cannot_confirm(stamp):
    monitor=ready();state=monitor.update(*sample(stamp))
    assert state['state']=='REJECTED' and state['reason']=='non_increasing_timestamp'
    assert monitor.update(*sample(1.3))['consecutive_frames']==1


def test_long_gap_requires_fresh_confirmation():
    state=ready().update(*sample(3.))
    assert state['state']=='WARMING_UP' and state['reason']=='source_gap'


def test_move_or_remove_block_invalidates_old_scene_immediately():
    monitor=ready();state=monitor.update(*sample(1.3,position=(.05,0,.975)))
    assert state['state']=='WARMING_UP' and state['reason']=='observed_positions_changed'
    frame,obs=sample(1.4);obs.candidates=[]
    assert monitor.update(frame,obs)['state']=='REJECTED'


def test_plane_and_background_changes_reset_confirmation():
    monitor=ready();frame,obs=sample(1.3)
    obs.plane=TablePlane((0,0,-1),1.03,.9,.001)
    assert monitor.update(frame,obs)['reason']=='support_plane_changed'
    monitor=ready();frame,obs=sample(1.3)
    frame=replace(frame,rgb=np.full(frame.rgb.shape,180,np.uint8))
    assert monitor.update(frame,obs)['reason']=='background_appearance_changed'


def test_source_epoch_changes_and_old_epoch_replay_rejected():
    monitor=ready();state=monitor.update(*sample(.1,clock='new_epoch'))
    assert state['reason']=='source_reference_changed' and state['consecutive_frames']==1
    assert monitor.update(*sample(1.4))['reason']=='retired_source_epoch'


def test_ambiguity_does_not_get_hidden_by_previous_confirmation():
    monitor=ready();frame,obs=sample(1.3)
    obs.candidates[0]['status']='AMBIGUOUS'
    assert monitor.update(frame,obs)['state']=='REJECTED'


def test_candidate_order_and_per_frame_ids_do_not_define_identity():
    monitor=SceneConsistencyMonitor()
    for i in range(3):
        frame,obs=sample(1.+i*.1)
        other=deepcopy(obs.candidates[0]);other.update(center_camera_m=[.1,0,.975],candidate_id=str(i))
        obs.candidates.append(other)
        if i%2:obs.candidates.reverse()
        state=monitor.update(frame,obs)
    assert state['state']=='CONFIRMED'


@pytest.mark.parametrize('config',[{'required_frames':1},{'max_gap_s':0},{'max_shift_m':float('nan')}])
def test_invalid_configuration_rejected(config):
    with pytest.raises(ValueError):SceneConsistencyMonitor(**config)


def test_mutating_reused_observation_does_not_rewrite_previous_evidence():
    monitor=SceneConsistencyMonitor();frame,obs=sample()
    monitor.update(frame,obs)
    obs.candidates[0]['center_camera_m'][0]=.05
    frame=replace(frame,stamp_s=1.1)
    state=monitor.update(frame,obs)
    assert state['reason']=='observed_positions_changed'
    assert state['consecutive_frames']==1


def test_malformed_position_cannot_be_confirmed():
    monitor=ready();frame,obs=sample(1.3)
    obs.candidates[0]['center_camera_m']=[0,0]
    assert monitor.update(frame,obs)['reason']=='missing_current_position'


def test_final_confirmation_does_not_hide_mid_sequence_reset():
    states=[{'state':s,'scene_consistent':s=='CONFIRMED'} for s in
        ['WARMING_UP','WARMING_UP','CONFIRMED','WARMING_UP','CONFIRMED']]
    result=static_sequence_acceptance(states,3)
    assert result['result']=='FAIL' and result['unstable_frame_indices']==[3]


def test_static_sequence_requires_sufficient_frames_and_stability():
    states=[{'state':s,'scene_consistent':s=='CONFIRMED'} for s in
        ['WARMING_UP','WARMING_UP','CONFIRMED','CONFIRMED']]
    assert static_sequence_acceptance(states[:2],3)['result']=='INCONCLUSIVE'
    assert static_sequence_acceptance(states,3)['result']=='PASS'
