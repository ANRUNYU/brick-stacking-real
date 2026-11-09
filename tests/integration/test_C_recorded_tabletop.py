"""Actual cropped RGB-D replay: preserve observed failure, never grant motion."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from brick_stacking.localization.camera_projection import backproject


ROOT=Path(__file__).parents[2]
FIXTURE=ROOT/'tests/fixtures/real/C_20261108_tabletop'
s=importlib.util.spec_from_file_location('recorded_table_observe',ROOT/'tools/observe_table_cube.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def test_cropped_real_capture_preserves_rays_and_rejection_evidence():
    manifest=json.loads((FIXTURE/'sample_manifest.json').read_text())
    for name,digest in manifest['files_sha256'].items():
        assert hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest()==digest
    config=json.loads((FIXTURE/'roi_config.json').read_text())
    path=FIXTURE/'camera/frame_000.npz'
    with np.load(path,allow_pickle=False) as data:
        meta=json.loads(str(data['metadata'].item()));uv=np.array([[20.,30.],[300.,100.]])
        original_uv=uv+np.asarray(meta['crop_source_xywh'][:2])
        np.testing.assert_allclose(backproject(uv,np.array([.8,.9]),data['k']),
                                   backproject(original_uv,np.array([.8,.9]),meta['original_k']),atol=1e-14)
    report=m.observe(path,config)
    assert report['checks']['consistency']=='FAIL'
    assert report['checks']['table_max_abs_m']>.7  # Real isolated depth outlier must survive holdout.
    assert report['T_base_camera'] is None and report['T_base_table'] is None
    assert not report['approved'] and not report['motion_enabled'] and not report['block_pose']['control_ready']
